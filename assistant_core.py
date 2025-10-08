import json
import pickle
import re
import random
from fuzzywuzzy import fuzz

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
        self.accounts = {}  # will be populated from app.py

    def load_model(self, path=MODEL_PATH):
        with open(path, "rb") as f:
            self.model = pickle.load(f)
        with open(INTENTS_PATH, "r", encoding="utf-8") as f:
            self.intents = json.load(f)["intents"]
        self.intent_map = {it["tag"]: it for it in self.intents}

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

    def extract_account_number(self, text):
        match = re.search(r"\b(\d{6,12})\b", text)
        return match.group(1) if match else None

    def fallback_by_fuzzy(self, text):
        best, best_score = None, 0
        for intent in self.intents:
            for pattern in intent.get("patterns", []):
                if "{" in pattern:
                    continue
                score = fuzz.partial_ratio(text, pattern.lower())
                if score > best_score:
                    best_score = score
                    best = intent["tag"]
        return best if best_score > 60 else None

    def handle_input(self, text, session):
        text_clean = text.lower().strip()
        session.setdefault("slots", {})

        acct_in_text = self.extract_account_number(text)

        def with_tick(msg, tag):
            return f"{msg}\n✅ {tag}" if tag != "weather" else msg

        # Awaiting account input
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
                    lines = [f"{t['date']}: {t['type']} {'+' if t['amount']>0 else '-'}₹{abs(t['amount']):.2f}" for t in txs]
                    return with_tick("\n".join(lines), original_tag), original_tag, session
            else:
                return with_tick("Please provide a valid account number.", "check_balance"), "check_balance", session

        tag, conf = self.predict_intent(text_clean)
        if conf < 0.45:
            fuzzy = self.fallback_by_fuzzy(text_clean)
            tag = fuzzy if fuzzy else "fallback"

        # --- Handle intents ---
        if tag=="check_balance":
            acct = str(session.get("account_no") or acct_in_text) if (session.get("account_no") or acct_in_text) else None
            acct_info = self.accounts.get(acct) if acct else None
            if acct_info:
                session["account_no"] = acct
                return f"Your balance is ₹{acct_info['balance']:.2f}", tag, session
            else:
                session["awaiting_account_input"] = True
                session["awaiting_intent"] = "check_balance"
                return with_tick("Please provide your account number.", tag), tag, session

        elif tag=="recent_transactions":
            acct = str(session.get("account_no") or acct_in_text) if (session.get("account_no") or acct_in_text) else None
            acct_info = self.accounts.get(acct) if acct else None
            if acct_info:
                txs = acct_info.get("transactions", [])
                if not txs:
                    return "No recent transactions.", tag, session
                lines = [f"{t['date']}: {t['type']} {'+' if t['amount']>0 else '-'}₹{abs(t['amount']):.2f}" for t in txs]
                return with_tick("\n".join(lines), tag), tag, session
            else:
                session["awaiting_account_input"] = True
                session["awaiting_intent"] = "recent_transactions"
                return with_tick("Please provide a valid account number.", tag), tag, session

        elif tag=="card_services":
            if "credit" in text_clean: return "Your Credit Card request has been initiated.", tag, session
            if "debit" in text_clean: return "Your Debit Card request has been initiated.", tag, session
            return with_tick("Do you want a Credit Card or a Debit Card?", tag), tag, session

        elif tag=="weather":
            resp = random.choice(self.get_intent_responses("weather") or ["I can’t fetch live weather here — try a weather app."])
            return resp, tag, session

        elif tag=="loan":
            if "change loan" in text_clean or "new loan type" in text_clean:
                session.pop("loan_type", None)
                session["awaiting_loan_type"] = True
                return with_tick("Sure! Which type of loan are you interested in? Personal or Home?", tag), tag, session
            if session.get("awaiting_loan_type"):
                loan_type = text_clean.strip().lower()
                session["loan_type"] = loan_type.title()
                session.pop("awaiting_loan_type", None)
                return f"You selected {session['loan_type']}. I can guide you with the application process.", tag, session
            if "loan_type" in session:
                return f"You have already selected {session['loan_type']}. I can guide you with the application process.", tag, session
            session["awaiting_loan_type"] = True
            return with_tick("Which type of loan are you interested in? Personal or Home?", tag), tag, session

        elif tag=="chitchat":
            resp = random.choice(self.get_intent_responses("chitchat") or ["Hi there!"])
            return resp, tag, session

        elif tag=="greeting":
            resp = random.choice(self.get_intent_responses("greeting") or ["Hello!"])
            return with_tick(resp, tag), tag, session

        elif tag=="thanks":
            resp = random.choice(self.get_intent_responses("thanks") or ["You're welcome!"])
            return resp, tag, session

        elif tag=="goodbye":
            resp = random.choice(self.get_intent_responses("goodbye") or ["Goodbye!"])
            session["completed"] = True
            return resp, tag, session

        else:
            resp = random.choice(self.get_intent_responses("fallback") or ["Sorry, I didn’t understand. Could you rephrase?"])
            return resp, "fallback", session
