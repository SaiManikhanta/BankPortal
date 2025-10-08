from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from assistant_core import AssistantCore
from train_intent_model import train_save
import json
import os
import csv
from datetime import datetime
import traceback

app = Flask(__name__)
app.secret_key = "supersecretkey"

# --- CONFIGURATION ---
QUERY_LOG_FILE = "user_queries_log.json"
SETTINGS_FILE = "settings.json"

# ---------------- FAKE USER DATABASE ----------------
users = {
    "user1": {
        "password": "pass123",
        "full_name": "Pamarthi Sai Mani Khanta",
        "account_no": "458293746",
        "balance": 55432.78,
        "loan": 50000,
        "debit_limit": 20000,
        "credit_limit": 100000,
        "transactions": [
            {"date": "2025-08-20", "type": "Grocery", "amount": -45.20},
            {"date": "2025-08-18", "type": "Salary", "amount": 2500.00},
            {"date": "2025-08-14", "type": "Online Purchase", "amount": -120.50},
        ]
    }
}

# ---------------- INITIALIZE ASSISTANT ----------------
MODEL_PATH = "intent_model.pkl"

if not os.path.exists(MODEL_PATH):
    print("Training model for the first time...")
    train_save()

assistant = AssistantCore()

# Map all user accounts to assistant
for username, user in users.items():
    if "account_no" in user:
        acct_no = user["account_no"]
        assistant.accounts[acct_no] = {
            "balance": user["balance"],
            "transactions": user["transactions"],
            "full_name": user["full_name"],
            "username": username
        }

# ---------------- HELPER FUNCTIONS ----------------
def log_user_query(username, message, tag):
    new_query = {
        "user": username,
        "query": message,
        "intent_tag": tag,
        "timestamp": datetime.now().isoformat()
    }
    logs = []
    if os.path.exists(QUERY_LOG_FILE):
        try:
            with open(QUERY_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
    logs.append(new_query)
    with open(QUERY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)

def get_query_logs():
    if os.path.exists(QUERY_LOG_FILE):
        try:
            with open(QUERY_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def get_current_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"confidence_threshold": 0.7, "max_response_length": 500}
    return {"confidence_threshold": 0.7, "max_response_length": 500}

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = users.get(username)
        if user and user["password"] == password:
            session["user"] = username
            session["chat_state"] = {}
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    username = session.get("user")
    if not username:
        return redirect(url_for("login"))
    user = users[username]
    is_admin = username == "user1"
    return render_template(
        "dashboard.html",
        user=user,
        transactions_json=json.dumps(user.get("transactions", [])),
        account=user,
        is_admin=is_admin
    )

# ---------------- CHATBOT ROUTE ----------------
@app.route("/chatbot", methods=["POST"])
def chatbot():
    username = session.get("user")
    if not username:
        return jsonify({"reply": "Please login first."})

    message = request.json.get("message", "")
    session_state = session.get("chat_state", {})

    try:
        reply, tag, new_session_state = assistant.handle_input(message, session_state)
        log_user_query(username, message, tag)
    except Exception:
        reply, tag = "I'm sorry, I encountered an error. Please try again.", "error"
        new_session_state = session_state
        log_user_query(username, message, tag)
        traceback.print_exc()

    session["chat_state"] = new_session_state
    return jsonify({"reply": reply})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---------------- STATIC PAGES ----------------
@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ---------------- ADMIN PAGE ----------------
@app.route("/admin")
def admin():
    if session.get("user") != "user1":
        return redirect(url_for("login"))
    return render_template("admin.html")

# ---------------- ADD INTENT ----------------
@app.route("/add_intent", methods=["POST"])
def add_intent():
    if session.get("user") != "user1":
        return jsonify({"error": "Unauthorized access."}), 403

    intent_name = request.form.get("intent", "").strip()
    patterns = [p.strip() for p in request.form.get("patterns", "").splitlines() if p.strip()]
    responses = [r.strip() for r in request.form.get("responses", "").splitlines() if r.strip()]
    if not intent_name or not patterns or not responses:
        return jsonify({"success": False, "message": "All fields must be filled."})

    try:
        with open("intents.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"intents": []}

    data["intents"].append({
        "tag": intent_name,
        "patterns": patterns,
        "responses": responses
    })

    with open("intents.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    train_save()
    assistant.load_model()
    return jsonify({"success": True, "message": "Intent added and model retrained successfully!"})

# ---------------- ADMIN DASHBOARD DATA ----------------
@app.route("/admin/dashboard_data")
def admin_dashboard_data():
    if session.get("user") != "user1":
        return jsonify({"error": "Unauthorized"}), 403

    logs = get_query_logs()
    total_queries = len(logs)
    successful_queries = sum(1 for log in logs if log['intent_tag'] not in ['fallback', 'error'])
    success_rate = round((successful_queries / total_queries) * 100, 1) if total_queries else 0

    # Count all defined intents
    try:
        with open("intents.json", "r", encoding="utf-8") as f:
            intent_data = json.load(f)
            intent_count = len(intent_data.get("intents", []))
    except:
        intent_count = 0

    recent_queries = [dict(
        query=q.get("query","N/A"),
        intent=q.get("intent_tag","N/A"),
        confidence=95 if q.get("intent_tag") not in ["fallback","error"] else 50,
        date=q.get("timestamp","")[:10]
    ) for q in logs[-10:][::-1]]

    return jsonify({
        "total_queries": total_queries,
        "success_rate": success_rate,
        "intent_count": intent_count,
        "entity_count": 0,
        "recent_queries": recent_queries
    })

# ---------------- USER QUERIES ----------------
@app.route("/admin/user_queries")
def admin_user_queries():
    if session.get("user") != "user1":
        return jsonify({"error": "Unauthorized"}), 403

    logs = get_query_logs()
    user_queries = [dict(
        user=log.get("user","Anonymous"),
        query=log.get("query","N/A"),
        date=log.get("timestamp","")[:16].replace("T"," ")
    ) for log in logs[::-1]]
    return jsonify({"queries": user_queries})

# ---------------- FAQS ----------------
@app.route("/admin/faqs")
def admin_faqs():
    if session.get("user") != "user1":
        return jsonify({"error": "Unauthorized"}), 403
    # Use your existing FAQ list
    faqs = [
        {"question": "How do I log in to my SkyBank account?", "answer": "Go to the login page, enter your username and password, and click 'Login' to access your account."},
        {"question": "How can I check my account balance?", "answer": "After logging in, click on 'Dashboard' → 'Account Summary' to view your current balance."},
        {"question": "How do I transfer money to another account?", "answer": "Go to 'Transfers' → 'New Transfer', enter the recipient details, and confirm the transaction."},
        {"question": "What should I do if I forget my password?", "answer": "Click on 'Forgot Password' on the login page and follow the steps to reset it securely."},
        {"question": "How can I download my transaction history?", "answer": "Navigate to 'Dashboard' → 'Transactions' and use the 'Download Statement' option to get a PDF copy."},
        {"question": "Is my data safe on SkyBank Portal?", "answer": "Yes, your data is protected with encryption and secure login authentication measures."},
        {"question": "What is the Bank Bot and how does it help?", "answer": "The Bank Bot is an AI assistant that answers your banking queries, helps you navigate the portal, and provides quick support."},
        {"question": "Why is the Bank Bot not understanding my question?", "answer": "The bot may not be trained for your query yet. You can report it or wait until the admin retrains the model with new data."},
        {"question": "Can the Bank Bot learn new queries?", "answer": "Yes, the admin can add new training queries and retrain the model to improve its responses."},
        {"question": "Does the Bank Bot need internet connectivity?", "answer": "Yes, an active internet connection is required for the bot to process queries and retrieve data."},
        {"question": "How can I add a new training query?", "answer": "In the admin dashboard, go to 'Add Training Query', enter the question and answer, and save it."},
        {"question": "What does the success rate in the dashboard mean?", "answer": "The success rate shows how many user queries were answered correctly based on the trained model’s responses."}
    ]
    return jsonify({"faqs": faqs})

# ---------------- ANALYTICS ----------------
@app.route("/admin/analytics_data")
def admin_analytics_data():
    if session.get("user") != "user1":
        return jsonify({"error": "Unauthorized"}), 403
    analytics_data = {
        "monthly_queries": [150, 220, 300, 250, 410, 350],
        "query_labels": ["May", "Jun", "Jul", "Aug", "Sep", "Oct"],
        "top_intents": [
            {"intent": "Check Balance", "count": 125},
            {"intent": "Transfer Funds", "count": 80},
            {"intent": "Loan Enquiry", "count": 65},
        ]
    }
    return jsonify(analytics_data)

# ---------------- SETTINGS ----------------
@app.route("/admin/settings", methods=["GET","POST"])
def admin_settings():
    if session.get("user") != "user1":
        return jsonify({"error":"Unauthorized"}),403
    if request.method=="GET":
        return jsonify(get_current_settings())
    else:
        try:
            new_threshold = float(request.form.get("confidence_threshold"))
            settings = get_current_settings()
            settings["confidence_threshold"] = new_threshold
            with open(SETTINGS_FILE,"w",encoding="utf-8") as f:
                json.dump(settings,f,indent=4)
            return jsonify({"success":True,"message":"Settings updated successfully."})
        except ValueError:
            return jsonify({"success":False,"message":"Invalid value for confidence threshold."})

# ---------------- EXPORT CSV ----------------
@app.route("/admin/export_csv")
def export_csv():
    if session.get("user") != "user1":
        return redirect(url_for("login"))
    logs = get_query_logs()
    output = [["Date","User","Query","Intent Tag"]]
    for log in logs:
        output.append([log.get("timestamp","")[:16].replace("T"," "),log.get("user","Anonymous"),log.get("query","N/A"),log.get("intent_tag","N/A")])
    # Use CSV module
    import io
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerows(output)
    response = make_response(si.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=recent_queries.csv"
    response.headers["Content-type"] = "text/csv"
    return response

# ---------------- RUN APP ----------------
if __name__=="__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=True)
