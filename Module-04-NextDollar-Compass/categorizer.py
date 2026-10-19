"""
categorizer.py - Puts each expense into a category and subcategory.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

HOW IT DECIDES (a "hybrid" pipeline)
-----------------------------------
1. The trained ML model (model_training.py) guesses a subcategory and says
   how confident it is.
2. If it is at least 40% confident, the guess is accepted. On merchants it
   has never seen, guesses above that line were right about 80% of the time
   (see models/evaluation.json).
3. If it is less confident, the expense goes to Gemini (when an API key is
   set). Gemini may only answer with one of our subcategory names.
4. Anything still uncertain is marked "check" so the user can fix it with
   one click. The user always has the final say.

It also reads bank-export CSV files and works out a monthly amount.
"""

import csv
import io
from datetime import datetime
from pathlib import Path

import joblib

from categories import ALL_SUBCATEGORIES, describe

MODEL_PATH = Path(__file__).parent / "models" / "expense_categorizer.joblib"
CONFIDENCE_THRESHOLD = 0.40

PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12, "quarterly": 4, "yearly": 1}

_model = None


def _load_model():
    """Load the saved model once; train it first if it does not exist yet."""
    global _model
    if _model is None:
        try:
            _model = joblib.load(MODEL_PATH)
        except Exception:
            # Missing file, or saved with a different scikit-learn version: rebuild (~15 seconds).
            import build_training_data
            import model_training
            build_training_data.main()
            model_training.main()
            _model = joblib.load(MODEL_PATH)
    return _model


def to_monthly(amount: float, frequency: str) -> float:
    """Convert an amount paid weekly / yearly / etc. into a monthly amount."""
    periods = PERIODS_PER_YEAR.get((frequency or "monthly").lower(), 12)
    return float(amount) * periods / 12


def categorize(items: list[dict], gemini=None) -> list[dict]:
    """
    items: [{"description": str, "amount": float, "frequency": "monthly", ...}]
    Returns the same items with category, subcategory, type, confidence,
    method ("ml", "gemini", or "check") and monthly_amount added.
    """
    if not items:
        return []
    model = _load_model()
    descriptions = [str(i.get("description", "")).strip() for i in items]
    proba = model.predict_proba(descriptions)
    classes = model.classes_

    results = []
    unsure_idx = []
    for idx, item in enumerate(items):
        best = int(proba[idx].argmax())
        top3 = proba[idx].argsort()[::-1][:3]
        sub = str(classes[best])
        conf = float(proba[idx][best])
        out = dict(item)
        out.update(describe(sub))
        out["confidence"] = round(conf, 3)
        out["alternatives"] = [str(classes[j]) for j in top3]
        out["method"] = "ml" if conf >= CONFIDENCE_THRESHOLD else "check"
        out["monthly_amount"] = round(to_monthly(float(item.get("amount") or 0), item.get("frequency", "monthly")), 2)
        if item.get("monthly_amount") is not None:  # CSV rows arrive pre-converted
            out["monthly_amount"] = round(float(item["monthly_amount"]), 2)
        if conf < CONFIDENCE_THRESHOLD:
            unsure_idx.append(idx)
        results.append(out)

    # Second opinion from the LLM for the uncertain ones.
    if unsure_idx and gemini is not None and gemini.available:
        labels = gemini.categorize([descriptions[i] for i in unsure_idx], ALL_SUBCATEGORIES)
        for i, label in zip(unsure_idx, labels):
            if label in ALL_SUBCATEGORIES:
                results[i].update(describe(label))
                results[i]["method"] = "gemini"
    return results


# ---------------------------------------------------------------------------
# Bank CSV import
# ---------------------------------------------------------------------------
_DESC_COLS = ("description", "desc", "memo", "name", "merchant", "payee", "details", "transaction")
_AMOUNT_COLS = ("amount", "debit", "withdrawal", "withdrawals", "charge", "value")
_DATE_COLS = ("date", "posted", "transaction date", "posting date", "post date")


def _find(headers: list[str], options: tuple) -> str | None:
    lowered = {h.lower().strip(): h for h in headers}
    for opt in options:
        if opt in lowered:
            return lowered[opt]
    for opt in options:  # looser match: "Transaction Description"
        for low, orig in lowered.items():
            if opt in low:
                return orig
    return None


def _parse_amount(raw: str) -> float | None:
    if raw is None:
        return None
    text = str(raw).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def _parse_date(raw: str):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt)
        except ValueError:
            continue
    return None


def parse_bank_csv(file_bytes: bytes) -> dict:
    """
    Read a bank export. Spending rows become expenses; deposits are skipped.
    Amounts are averaged per month using the date range in the file.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    desc_col, amt_col, date_col = _find(headers, _DESC_COLS), _find(headers, _AMOUNT_COLS), _find(headers, _DATE_COLS)
    if not desc_col or not amt_col:
        raise ValueError("The CSV needs a description column and an amount column "
                         f"(found: {', '.join(headers) or 'no headers'}).")

    rows, dates = [], []
    for row in reader:
        amount = _parse_amount(row.get(amt_col))
        desc = (row.get(desc_col) or "").strip()
        if amount is None or not desc:
            continue
        rows.append((desc, amount))
        if date_col:
            d = _parse_date(row.get(date_col, ""))
            if d:
                dates.append(d)

    # Banks differ: some show spending as negative numbers, some as positive.
    has_negative = any(a < 0 for _, a in rows)
    spending = [(d, abs(a)) for d, a in rows if (a < 0 if has_negative else a > 0)]

    months = 1.0
    if len(dates) >= 2:
        span_days = (max(dates) - min(dates)).days + 1
        months = max(1.0, round(span_days / 30.44, 1))

    items = [{"description": d, "amount": round(a, 2), "frequency": "csv",
              "monthly_amount": round(a / months, 2)} for d, a in spending]
    return {"items": items, "months_covered": months, "rows_read": len(rows),
            "skipped_deposits": len(rows) - len(spending)}
