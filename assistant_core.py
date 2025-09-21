import json
import pickle
import re
import random
from fuzzywuzzy import fuzz
from datetime import datetime

INTENTS_PATH = "intents.json"
MODEL_PATH = "intent_model.pkl"

class AssistantCore:
    def __init__(self):
        # Load intents
        with open(INTENTS_PATH, "r", encoding="utf-8") as f:
            self.intents = json.load(f)["intents"]

        # Load model
        with open(MODEL_PATH, "rb") as f:
            self.model = pickle.load(f)

        self.intent_map = {it["tag"]: it for it in self.intents}

        # Sample accounts for chatbot
        self.accounts = {
            "458293746": {"balance": 55432.78, "transactions": [
                {"date": "2025-08-20", "type": "Grocery", "amount": -45.20},
                {"date": "2025-08-18", "type": "Salary", "amount": 2500.00},
                {"date": "2025-08-14", "type": "Online Purchase", "amount": -120.50}
            ]}
        }

    # ---------- Intent Prediction ----------
    def predict_intent(self, text):
        tag = self.model.predict([text])[0]
        prob = 0.0
        if hasattr(self.model, "predict_proba"):
            try:
                prob = max(self.model.predict_proba([text])[0])
            except:
                prob = 0.0
        return tag, float(prob)

    def get_intent_responses(self, tag):
        return self.intent_map.get(tag, {}).get("responses", [])

    # ---------- Slot Extraction ----------
    def extract_account_number(self, text):
        m = re.search(r"\b(\d{6,12})\b", text)
        return m.group(1) if m else None

    # ---------- Fuzzy fallback ----------
    def fallback_by_fuzzy(self, text):
        best, best_score = None, 0
        for intent in self.intents:
            for pat in intent.get("patterns", []):
                if "{" in pat:
                    continue
                s = fuzz.partial_ratio(text, pat.lower())
                if s > best_score:
                    best_score = s
                    best = intent["tag"]
        return best if best_score > 60 else None

    # ---------- Handle Input ----------
    def handle_input(self, text, session):
        text_clean = text.lower().strip()
        session.setdefault("slots", {})

        # Extract slots
        acct_in_text = self.extract_account_number(text)

        # Helper to append tick
        def with_tick(msg, t):
            return f"{msg}\n✅ {t}" if t != "weather" else msg

        # ---------- Awaiting Account Number ----------
        if session.get("awaiting_account_input") and acct_in_text:
            acct = acct_in_text
            acct_info = self.accounts.get(acct)
            if acct_info:
                session["account_no"] = acct
                session.pop("awaiting_account_input", None)
                original_tag = session.pop("awaiting_intent", "check_balance")
                if original_tag == "check_balance":
                    return f"Your balance is ₹{acct_info['balance']:.2f}", original_tag, session
                elif original_tag == "recent_transactions":
                    txs = acct_info.get("transactions", [])
                    if not txs:
                        return "No recent transactions.", original_tag, session
                    lines = [f"{t['date']}: {t['type']} {'+' if t['amount']>0 else '-'}₹{abs(t['amount']):.2f}" for t in txs]
                    return with_tick("\n".join(lines), original_tag), original_tag, session
            else:
                return with_tick("Please provide a valid account number.", "check_balance"), "check_balance", session

        # ---------- Predict Intent ----------
        tag, conf = self.predict_intent(text_clean)
        if conf < 0.45:
            fuzzy = self.fallback_by_fuzzy(text_clean)
            if fuzzy:
                tag = fuzzy
            else:
                tag = "fallback"

        # ---------- Handle Intents ----------
        # Check Balance
        if tag == "check_balance":
            acct = str(session.get("account_no") or acct_in_text).strip() if (session.get("account_no") or acct_in_text) else None
            acct_info = self.accounts.get(acct) if acct else None
            if acct_info:
                session["account_no"] = acct
                return f"Your balance is ₹{acct_info['balance']:.2f}", "check_balance", session
            else:
                session["awaiting_account_input"] = True
                session["awaiting_intent"] = "check_balance"
                return with_tick("Please provide your account number.", tag), tag, session

        # Recent Transactions
        if tag == "recent_transactions":
            acct = str(session.get("account_no") or acct_in_text).strip() if (session.get("account_no") or acct_in_text) else None
            acct_info = self.accounts.get(acct) if acct else None
            if acct_info:
                txs = acct_info.get("transactions", [])
                if not txs:
                    return "No recent transactions.", "recent_transactions", session
                lines = [f"{t['date']}: {t['type']} {'+' if t['amount']>0 else '-'}₹{abs(t['amount']):.2f}" for t in txs]
                return with_tick("\n".join(lines), tag), "recent_transactions", session
            else:
                session["awaiting_account_input"] = True
                session["awaiting_intent"] = "recent_transactions"
                return with_tick("Please provide a valid account number.", tag), tag, session

        # Card Services
        if tag == "card_services":
            session["last_intent"] = "card_services"
            if "credit" in text_clean:
                session["slots"]["card_type"] = "Credit Card"
                session["last_intent"] = None
                return "Your Credit Card request has been initiated.", tag, session
            if "debit" in text_clean:
                session["slots"]["card_type"] = "Debit Card"
                session["last_intent"] = None
                return "Your Debit Card request has been initiated.", tag, session
            return with_tick("Do you want a Credit Card or a Debit Card?", tag), tag, session

        # Weather
        if tag == "weather":
            resp = random.choice(self.get_intent_responses("weather") or ["I can’t fetch live weather here — try a weather app or website."])
            session["last_intent"] = None
            return resp, "weather", session

        # Loan
        if tag == "loan":
            if "change loan" in text_clean or "new loan type" in text_clean:
                session["slots"].pop("loan_type", None)
                session["awaiting_loan_type"] = True
                return with_tick("Sure! Let's update your loan type. Which type of loan are you interested in? Personal or Home?", tag), tag, session

            if session.get("awaiting_loan_type"):
                loan_type = text_clean.strip().lower()
                session["slots"]["loan_type"] = loan_type.title()
                session.pop("awaiting_loan_type", None)
                return f"You selected {session['slots']['loan_type']}. I can guide you with the application process.", tag, session

            if "loan_type" in session["slots"]:
                return f"You have already selected {session['slots']['loan_type']}. I can guide you with the application process.", tag, session

            session["awaiting_loan_type"] = True
            return with_tick("Which type of loan are you interested in? Personal or Home?", tag), tag, session

        # Chitchat
        if tag == "chitchat":
            resp = random.choice(self.get_intent_responses("chitchat") or ["Hi there!"])
            session["last_intent"] = None
            return resp, "chitchat", session

        # Greeting
        if tag == "greeting":
            resp = random.choice(self.get_intent_responses("greeting") or ["Hello!"])
            session["last_intent"] = "greeting"
            return with_tick(resp, "greeting"), "greeting", session

        # Thanks
        if tag == "thanks":
            resp = random.choice(self.get_intent_responses("thanks") or ["You're welcome!"])
            session["last_intent"] = None
            return resp, "thanks", session

        # Goodbye
        if tag == "goodbye":
            resp = random.choice(self.get_intent_responses("goodbye") or ["Goodbye!"])
            session["last_intent"] = None
            session["completed"] = True
            return resp, "goodbye", session

        # Fallback
        resp = random.choice(self.get_intent_responses("fallback") or ["Sorry, I didn’t understand. Could you rephrase?"])
        session["last_intent"] = None
        return resp, "fallback", session
