"""
gemini_client.py - Everything that talks to Google's Gemini AI model
(the "Large Language Model" part of the project).

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

WHAT GEMINI DOES IN THIS APP (four jobs)
---------------------------------------
1. READ DOCUMENTS - pay stubs, credit-card statements, loan statements
   (PDF or photo) and fill in a fixed form ("structured output").
2. SECOND OPINION on expenses the ML model was unsure about.
3. EXPLAIN THE PLAN in plain language, using only numbers Python calculated.
4. ANSWER QUESTIONS about the user's own plan.

If there is no API key, or a call fails, every job has an offline fallback
(document_reader.py and offline_text.py), so the app never breaks.

API KEY SAFETY
--------------
The key is read from the GEMINI_API_KEY environment variable (or a local
.env file that .gitignore keeps off GitHub). It is never written in code.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from pydantic import BaseModel, Field

import prompts

# Default model; change it without editing code by setting GEMINI_MODEL.
DEFAULT_MODEL = "gemini-3.8-flash"


# ---------------------------------------------------------------------------
# Answer forms (schemas). Field descriptions are sent to Gemini too.
# ---------------------------------------------------------------------------
class Deduction(BaseModel):
    name: str = Field(description="Deduction name, e.g. 'Federal Income Tax', '401(k)', 'Medical'.")
    amount: float = Field(description="Amount for this pay period.")


class PaystubFields(BaseModel):
    pay_frequency: Optional[str] = Field(None, description="weekly, biweekly, semimonthly or monthly")
    gross_pay: Optional[float] = Field(None, description="Gross pay for this pay period (not YTD).")
    net_pay: Optional[float] = Field(None, description="Net / take-home pay for this pay period (not YTD).")
    deductions: list[Deduction] = Field(default_factory=list)
    notes: str = Field("", description="Anything unclear or worth checking.")


class CardFields(BaseModel):
    card_name: Optional[str] = Field(None, description="Card product or bank name, e.g. 'Chase Freedom'.")
    balance: Optional[float] = None
    purchase_apr: Optional[float] = Field(None, description="Purchase APR as a number, e.g. 24.99")
    penalty_apr: Optional[float] = None
    promo_apr: Optional[float] = None
    promo_ends: Optional[str] = None
    minimum_payment: Optional[float] = None
    credit_limit: Optional[float] = None
    annual_fee: Optional[float] = None
    late_fee: Optional[float] = None
    notes: str = ""


class LoanFields(BaseModel):
    lender_name: Optional[str] = None
    balance: Optional[float] = Field(None, description="Unpaid principal balance.")
    interest_rate: Optional[float] = Field(None, description="Interest rate as a number, e.g. 6.375")
    monthly_payment: Optional[float] = Field(None, description="Regular monthly payment (incl. escrow if any).")
    escrow: Optional[float] = Field(None, description="Escrow part of the payment (mortgages).")
    remaining_months: Optional[int] = None
    notes: str = ""


class CategoryLabel(BaseModel):
    index: int
    subcategory: str


class CategoryLabels(BaseModel):
    labels: list[CategoryLabel]


class PlanNarrative(BaseModel):
    headline: str
    summary: str
    this_month: list[str]
    watch_outs: list[str]
    encouragement: str


SCHEMAS = {"paystub": PaystubFields, "credit_card": CardFields, "loan": LoanFields}


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.last_error: str | None = None
        self._client = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:  # library missing or bad key format
                self.last_error = f"Could not start Gemini: {exc}"

    @property
    def available(self) -> bool:
        return self._client is not None

    # -- low-level call ---------------------------------------------------------
    def _generate(self, contents, schema=None, temperature: float = 0.2):
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=prompts.GUARDRAILS,
            temperature=temperature,
            response_mime_type="application/json" if schema else "text/plain",
            response_schema=schema,
        )
        try:
            response = self._client.models.generate_content(model=self.model, contents=contents, config=config)
        except Exception as exc:
            self.last_error = _short_error(exc)
            return None
        self.last_error = None
        if schema is None:
            return (response.text or "").strip()
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed
        try:
            return schema.model_validate(json.loads(response.text))
        except Exception as exc:
            self.last_error = f"Gemini returned an unexpected format: {exc}"
            return None

    # -- job 1: read a document -----------------------------------------------
    def extract_document(self, data: bytes, mime_type: str, doc_type: str) -> dict | None:
        if not self.available:
            return None
        from google.genai import types
        kind = "loan" if doc_type in ("mortgage", "car_loan", "loan") else doc_type
        schema = SCHEMAS.get(kind)
        if schema is None:
            return None
        part = types.Part.from_bytes(data=data, mime_type=mime_type)
        result = self._generate([part, prompts.EXTRACT_INSTRUCTIONS[kind]], schema=schema, temperature=0.0)
        return result.model_dump() if result else None

    # -- job 2: second opinion on unsure expenses -------------------------------
    def categorize(self, descriptions: list[str], allowed: list[str]) -> list[str | None]:
        if not self.available or not descriptions:
            return [None] * len(descriptions)
        lines = "\n".join(f"{i}. {d}" for i, d in enumerate(descriptions))
        prompt = prompts.CATEGORIZE_INSTRUCTIONS.format(allowed="\n".join(allowed), lines=lines)
        result = self._generate(prompt, schema=CategoryLabels, temperature=0.0)
        out: list[str | None] = [None] * len(descriptions)
        if result:
            for item in result.labels:
                if 0 <= item.index < len(out) and item.subcategory in allowed:
                    out[item.index] = item.subcategory
        return out

    # -- job 3: explain the plan ---------------------------------------------------
    def explain_plan(self, plan_summary: dict) -> dict | None:
        if not self.available:
            return None
        prompt = prompts.PLAN_INSTRUCTIONS.format(plan=json.dumps(plan_summary, indent=1))
        result = self._generate(prompt, schema=PlanNarrative, temperature=0.4)
        return result.model_dump() if result else None

    # -- job 4: answer a question --------------------------------------------------
    def answer(self, question: str, plan_summary: dict, history: list[dict]) -> str | None:
        if not self.available:
            return None
        hist = "\n".join(f"{h.get('role', 'user')}: {str(h.get('text', ''))[:600]}" for h in history[-6:]) or "(none)"
        prompt = prompts.QA_INSTRUCTIONS.format(plan=json.dumps(plan_summary, indent=1), history=hist,
                                                question=question[:1000])
        return self._generate(prompt, temperature=0.4)


def _short_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "api key" in low or "permission" in low or "401" in low or "403" in low:
        return "Gemini rejected the API key. Check GEMINI_API_KEY."
    if "429" in low or "quota" in low or "resource_exhausted" in low:
        return "Gemini rate limit reached. Wait a minute and try again."
    if "not found" in low and "model" in low:
        return "Gemini model name not found. Set GEMINI_MODEL to a current model."
    return f"Gemini error: {text[:160]}"
