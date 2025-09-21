from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from assistant_core import AssistantCore
import json
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

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
assistant = AssistantCore()
for user in users.values():
    acct_no = user["account_no"]
    assistant.accounts[acct_no] = {
        "balance": user["balance"],
        "transactions": user["transactions"]
    }

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
    return render_template(
        "dashboard.html",
        user=user,
        transactions_json=json.dumps(user["transactions"]),
        account=user
    )

@app.route("/chatbot", methods=["POST"])
def chatbot():
    username = session.get("user")
    if not username:
        return jsonify({"reply": "Please login first."})
    
    message = request.json.get("message", "")
    session_state = session.get("chat_state", {})

    reply, tag, session_state = assistant.handle_input(message, session_state)
    session["chat_state"] = session_state
    return jsonify({"reply": reply})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
