"""
document_reader.py - Reads numbers out of uploaded documents WITHOUT AI.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

This is the offline fallback. When no Gemini API key is set, the app still
reads text-based PDFs (most pay stubs and statements you download from a
website are text-based) and searches them with regular expressions - simple
text patterns such as "the dollar amount that comes after 'Net Pay'".

Limits (and why Gemini does better):
  * Photos and scanned PDFs contain no text layer, so nothing is found.
  * Every company lays out documents differently; patterns can miss.
The user always reviews the numbers before they are used.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime

from pypdf import PdfReader

MONEY = r"\$?\s*(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)"
PERCENT = r"(\d{1,2}(?:\.\d{1,3})?)\s*%"


def pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _to_float(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def _after(labels: list[str], text: str, pattern: str = MONEY, window: int = 60) -> float | None:
    """First value matching `pattern` within `window` characters after any label."""
    for label in labels:
        for m in re.finditer(label, text, flags=re.IGNORECASE):
            tail = text[m.end(): m.end() + window]
            v = re.search(pattern, tail)
            if v:
                return _to_float(v.group(1))
    return None


def _frequency(text: str) -> str | None:
    low = text.lower()
    for words, freq in ((("bi-weekly", "biweekly", "every two weeks"), "biweekly"),
                        (("semi-monthly", "semimonthly", "twice a month"), "semimonthly"),
                        (("weekly",), "weekly"), (("monthly",), "monthly")):
        if any(w in low for w in words):
            return freq
    m = re.search(r"pay period[^\d]{0,20}(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to|through)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
                  text, re.IGNORECASE)
    if m:
        try:
            fmt = "%m/%d/%Y" if len(m.group(1).split("/")[-1]) == 4 else "%m/%d/%y"
            days = (datetime.strptime(m.group(2), fmt) - datetime.strptime(m.group(1), fmt)).days + 1
            return "weekly" if days <= 8 else "biweekly" if days <= 14 else "semimonthly" if days <= 16 else "monthly"
        except ValueError:
            return None
    return None


DEDUCTION_LABELS = ["Federal Income Tax", "Social Security", "Medicare", "State Income Tax", "401(k)", "401k",
                    "Roth 401(k)", "Medical", "Dental", "Vision", "Health Insurance", "Life Insurance", "HSA"]


def parse_paystub(text: str) -> dict:
    deductions = []
    for label in DEDUCTION_LABELS:
        v = _after([re.escape(label)], text, window=40)
        if v is not None and not any(d["name"] == label for d in deductions):
            deductions.append({"name": label, "amount": v})
    return {
        "pay_frequency": _frequency(text),
        "gross_pay": _after([r"gross pay", r"total gross", r"gross earnings", r"gross wages"], text),
        "net_pay": _after([r"net pay", r"take[- ]home", r"net amount", r"direct deposit"], text),
        "deductions": deductions,
    }


def parse_credit_card(text: str) -> dict:
    fee = None
    if re.search(r"annual fee[:\s]*(none|\$0\b|0\.00)", text, re.IGNORECASE):
        fee = 0.0
    else:
        fee = _after([r"annual fee"], text, window=30)
    return {
        "balance": _after([r"new balance", r"statement balance", r"current balance"], text),
        "purchase_apr": _after([r"purchase(?:s)?\s*(?:apr|annual percentage rate)",
                                r"annual percentage rate \(apr\) for purchases", r"purchases"], text, PERCENT, 80),
        "penalty_apr": _after([r"penalty apr"], text, PERCENT, 60),
        "minimum_payment": _after([r"minimum payment due", r"minimum payment"], text),
        "credit_limit": _after([r"credit limit", r"credit line"], text),
        "annual_fee": fee,
        "late_fee": _after([r"late payment(?: fee)?", r"late fee"], text, window=40),
    }


def parse_loan(text: str) -> dict:
    remaining = _after([r"remaining term", r"payments remaining", r"months remaining"], text, r"(\d{1,3})", 30)
    if remaining is None:
        m = re.search(r"maturity date[:\s]*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if m:
            d = datetime.strptime(m.group(1), "%m/%d/%Y").date()
            today = date.today()
            remaining = max(0, (d.year - today.year) * 12 + d.month - today.month)
    return {
        "balance": _after([r"unpaid principal balance", r"principal balance", r"outstanding principal",
                           r"loan balance", r"current principal"], text),
        "interest_rate": _after([r"interest rate", r"annual percentage rate", r"\bapr\b"], text, PERCENT, 40),
        "monthly_payment": _after([r"regular monthly payment", r"monthly payment", r"payment amount",
                                   r"total amount due", r"amount due"], text),
        "escrow": _after([r"escrow(?: \(taxes and insurance\))?", r"escrow payment"], text, window=40),
        "remaining_months": remaining,
    }


PARSERS = {"paystub": parse_paystub, "credit_card": parse_credit_card, "mortgage": parse_loan,
           "car_loan": parse_loan, "loan": parse_loan}


def read_offline(data: bytes, mime_type: str, doc_type: str) -> dict:
    if mime_type != "application/pdf":
        return {"fields": {}, "source": "none",
                "message": "Photos need AI mode (add a Gemini API key), or type the numbers in."}
    text = pdf_text(data)
    if len(text.strip()) < 20:
        return {"fields": {}, "source": "none",
                "message": "This PDF looks scanned (no text layer). Add a Gemini API key or type the numbers in."}
    fields = PARSERS.get(doc_type, parse_loan)(text)
    found = sum(1 for k, v in fields.items() if v not in (None, [], ""))
    return {"fields": fields, "source": "pdf-text", "found": found,
            "message": f"Read {found} value(s) with text patterns (offline mode). Please check them."}
