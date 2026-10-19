"""
model_training.py - Trains and evaluates the expense categorizer
(the "traditional machine learning" part of the project).

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

WHAT IT DOES
------------
1. Loads data/training_transactions.csv (created by build_training_data.py).
2. Turns each description into numbers with TF-IDF, using two views:
     * word n-grams   - catches words like "insurance", "coffee", "rent"
     * character n-grams - catches partial and misspelled merchant names
       ("whataburgr", "chk-fil-a") and bank abbreviations ("amzn mktp").
3. Compares two classic models (the Assignment Aid uses Naive Bayes):
     * Multinomial Naive Bayes (baseline)
     * Logistic Regression
4. Runs TWO honest tests:
     * Test A "new rows":      random 80/20 split. Merchants in the test set
                               were also seen in training (just written
                               differently). Measures how well it handles
                               messy formatting.
     * Test B "new merchants": whole merchants are held out. The model has
                               never seen them, so it can only use clues like
                               "pharmacy" or "fitness". This is closer to real
                               life and gives a LOWER, more honest score.
5. Trains the winner on all the data and saves it to
   models/expense_categorizer.joblib with its scores in models/evaluation.json.

Run:  python model_training.py
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline

from preprocess import clean_text

BASE = Path(__file__).parent
DATA_PATH = BASE / "data" / "training_transactions.csv"
MODEL_PATH = BASE / "models" / "expense_categorizer.joblib"
EVAL_PATH = BASE / "models" / "evaluation.json"


def make_features() -> FeatureUnion:
    """TF-IDF on words + TF-IDF on character pieces, side by side."""
    return FeatureUnion([
        ("words", TfidfVectorizer(preprocessor=clean_text, ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
        ("chars", TfidfVectorizer(preprocessor=clean_text, analyzer="char_wb", ngram_range=(3, 5),
                                  min_df=2, sublinear_tf=True)),
    ])


def make_models() -> dict[str, Pipeline]:
    return {
        "Naive Bayes (baseline)": Pipeline([("features", make_features()), ("clf", MultinomialNB(alpha=0.1))]),
        "Logistic Regression": Pipeline([("features", make_features()),
                                         ("clf", LogisticRegression(C=8.0, max_iter=3000))]),
    }


def unseen_merchant_split(df: pd.DataFrame, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out ~25% of the merchants/phrases in each subcategory entirely."""
    rng = random.Random(seed)
    held_out = set()
    for _, group in df.groupby("label"):
        names = sorted(group["merchant"].unique())
        rng.shuffle(names)
        k = max(1, round(len(names) * 0.25))
        held_out.update(names[:k])
    test_mask = df["merchant"].isin(held_out)
    return df[~test_mask], df[test_mask]


def score(model: Pipeline, train: pd.DataFrame, test: pd.DataFrame) -> dict:
    model.fit(train["text"], train["label"])
    pred = model.predict(test["text"])
    return {
        "accuracy": round(accuracy_score(test["label"], pred), 4),
        "macro_f1": round(f1_score(test["label"], pred, average="macro"), 4),
        "n_test": int(len(test)),
    }


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit("No training data yet. Run:  python build_training_data.py")
    df = pd.read_csv(DATA_PATH)
    print(f"[INFO] Loaded {len(df):,} rows, {df['label'].nunique()} subcategories")

    # Show what cleaning does (handy for the write-up).
    print("\nExample of text cleaning:")
    for raw in df["text"].head(4):
        print(f"  {raw!r:55} -> {clean_text(raw)!r}")

    train_a, test_a = train_test_split(df, test_size=0.2, random_state=42, stratify=df["label"])
    train_b, test_b = unseen_merchant_split(df)

    results = {}
    for name, model in make_models().items():
        results[name] = {
            "test_a_new_rows": score(model, train_a, test_a),
            "test_b_new_merchants": score(make_models()[name], train_b, test_b),
        }

    print("\nModel comparison")
    print(f"  {'model':26} {'Test A acc':>11} {'Test A F1':>10} {'Test B acc':>11} {'Test B F1':>10}")
    for name, r in results.items():
        a, b = r["test_a_new_rows"], r["test_b_new_merchants"]
        print(f"  {name:26} {a['accuracy']:>11.1%} {a['macro_f1']:>10.3f} {b['accuracy']:>11.1%} {b['macro_f1']:>10.3f}")

    # Pick the model that generalizes best to merchants it has never seen.
    best_name = max(results, key=lambda n: results[n]["test_b_new_merchants"]["macro_f1"])
    print(f"\n[INFO] Best on unseen merchants: {best_name}")

    # Detailed report for the chosen model on the harder test.
    detail_model = make_models()[best_name]
    detail_model.fit(train_b["text"], train_b["label"])
    report = classification_report(test_b["label"], detail_model.predict(test_b["text"]), zero_division=0)
    print("\nPer-subcategory report (Test B - unseen merchants):")
    print(report)

    # How confident is the model when it is right? This picks the cut-off the
    # app uses: confident guesses are accepted, the rest go to Gemini or to
    # the user for review ("human in the loop").
    proba = detail_model.predict_proba(test_b["text"])
    guesses = detail_model.classes_[proba.argmax(axis=1)]
    confidence = proba.max(axis=1)
    truth = test_b["label"].to_numpy()
    threshold_table = []
    print("Confidence cut-off on unseen merchants:")
    for cut in (0.3, 0.4, 0.5, 0.6):
        keep = confidence >= cut
        acc = float((guesses[keep] == truth[keep]).mean()) if keep.any() else 0.0
        threshold_table.append({"threshold": cut, "share_auto_labeled": round(float(keep.mean()), 4),
                                "accuracy_when_auto_labeled": round(acc, 4)})
        print(f"  >= {cut:.0%} confident: auto-labels {keep.mean():.0%} of rows, {acc:.0%} of those correct")

    # Final model: train on everything so the app knows every merchant.
    final = make_models()[best_name]
    final.fit(df["text"], df["label"])
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, MODEL_PATH)

    EVAL_PATH.write_text(json.dumps({
        "chosen_model": best_name,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "subcategories": int(df["label"].nunique()),
        "results": results,
        "confidence_threshold_test_b": threshold_table,
        "app_threshold": 0.4,
        "notes": ("Test A = random 80/20 split (merchants seen in training, new formatting). "
                  "Test B = whole merchants held out (never seen). Data is synthetic."),
    }, indent=2))
    print(f"[INFO] Saved model -> {MODEL_PATH}")
    print(f"[INFO] Saved scores -> {EVAL_PATH}")


if __name__ == "__main__":
    main()
