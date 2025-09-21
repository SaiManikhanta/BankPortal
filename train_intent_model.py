# train_intent_model.py
import json
import random
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

RANDOM_SEED = 42

def load_intents(path="intents.json"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    texts, labels = [], []
    for intent in data["intents"]:
        tag = intent["tag"]
        for p in intent.get("patterns", []):
            # remove placeholders like {account_number} so model trains on real words
            p_clean = p.replace("{account_number}", "").replace("{amount}", "").replace("{recipient}", "").replace("{card_type}", "").strip()
            if p_clean:
                texts.append(p_clean.lower())
                labels.append(tag)
    return texts, labels

def train_save(model_path="intent_model.pkl"):
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    X, y = load_intents()
    if not X:
        raise RuntimeError("No training data found in intents.json")

    # Small dataset — augment slightly by duplicating with minor shuffles
    X_ext, y_ext = [], []
    for _ in range(2):
        X_ext.extend(X)
        y_ext.extend(y)
    X = X + X_ext
    y = y + y_ext

    # Split into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_SEED)

    # Define pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), max_features=4000)),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))
    ])

    # Train
    pipeline.fit(X_train, y_train)

    # Evaluate
    preds = pipeline.predict(X_test)
    print("Accuracy:", accuracy_score(y_test, preds))
    print(classification_report(y_test, preds))

    # Save model
    with open(model_path, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"Saved model to {model_path}")

if __name__ == "__main__":
    train_save()
