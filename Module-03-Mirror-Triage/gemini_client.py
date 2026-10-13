"""
gemini_client.py - Everything that talks to Google's Gemini AI model.

Course: ITAI 2372 - Module 03 (AI in Healthcare)
Project: Mirror Triage

PLAIN-LANGUAGE SUMMARY
----------------------
This file sends the patient's description to Gemini (a large language model
made by Google) and gets back a structured answer.

"Structured" is the key idea. Instead of letting the AI reply with free-form
text that we would have to pick apart (the course example's weak spot), we
give Gemini an exact form to fill in - a JSON "schema" - with fields such as
triage_level, confidence and advice_for_patient. Gemini's structured-output
feature guarantees the reply matches the form, and Pydantic (a Python library)
double-checks it before the app uses it.

API KEY SAFETY
--------------
The Gemini API key is NEVER written in this code or uploaded to GitHub. The app
reads it at run time from either:
  * the GEMINI_API_KEY environment variable (on your own computer), or
  * Streamlit's secret storage (when the app is hosted online).
"""

from __future__ import annotations

import os
from typing import Literal, Protocol

from pydantic import BaseModel, Field

import prompts

# Default model. Gemini 3.8 Flash is listed with a free tier on Google's pricing
# page (checked October 2026). You can switch models without editing code by
# setting GEMINI_MODEL (e.g. "gemini-3.5-flash-lite" for faster bulk testing).
DEFAULT_MODEL = "gemini-3.8-flash"


# ---------------------------------------------------------------------------
# Answer "forms" (schemas) the AI must fill in.
# Each Field description is also sent to Gemini, so it doubles as instructions.
# ---------------------------------------------------------------------------
class FollowUpCheck(BaseModel):
    """STEP 1 answer: do we need to ask the patient anything else?"""

    detected_language: str = Field(
        description="The language the patient wrote in, e.g. 'English' or 'Spanish'."
    )
    english_translation: str = Field(
        description="The patient's description translated into clear English."
    )
    enough_information: bool = Field(
        description="True if a triage level can be chosen safely without more questions."
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 short questions in the patient's language. Empty if none are needed.",
    )
    red_flags_noticed: list[str] = Field(
        default_factory=list,
        description="Emergency warning signs noticed, in English. Empty if none.",
    )


class PossibleCondition(BaseModel):
    """One possible cause to discuss with a clinician (not a diagnosis)."""

    name_for_patient: str = Field(description="Plain-language name in the patient's language.")
    name_in_english: str = Field(description="Name in English for the clinician.")
    likelihood: Literal["more likely", "possible", "less likely"]


class Assessment(BaseModel):
    """STEP 2 answer: the full preliminary triage assessment."""

    detected_language: str = Field(description="Language the patient wrote in.")
    english_translation: str = Field(
        description="Everything the patient wrote (including follow-up answers), translated into English."
    )
    triage_level: Literal["EMERGENCY", "URGENT", "PRIMARY_CARE", "SELF_CARE"]
    confidence: Literal["high", "medium", "low"]
    reasoning_english: str = Field(description="2-4 sentences explaining the level, in English.")
    possible_conditions: list[PossibleCondition] = Field(min_length=1, max_length=3)
    red_flags_noticed: list[str] = Field(
        default_factory=list, description="Emergency warning signs noticed, in English."
    )
    advice_for_patient: str = Field(description="What to do and how soon, in the patient's language.")
    warning_signs_to_watch: list[str] = Field(
        description="2-4 signs that mean 'get help sooner', in the patient's language."
    )
    clinician_summary_english: str = Field(description="A short triage note for the clinic, in English.")


# ---------------------------------------------------------------------------
# A "Protocol" describes what any triage AI client must be able to do.
# The real Gemini client below follows it, and so do the fake clients used in
# the automated tests (tests/), which lets us test the app without the internet.
# ---------------------------------------------------------------------------
class TriageAIClient(Protocol):
    def check_followups(self, symptoms: str, age_group: str, duration: str, language: str) -> FollowUpCheck: ...

    def assess(
        self, symptoms: str, age_group: str, duration: str, language: str, followup_qa: list
    ) -> Assessment: ...


class GeminiTriageClient:
    """Calls the Gemini API and returns validated Pydantic objects."""

    def __init__(self, api_key: str, model: str | None = None):
        # Imported here so the rest of the app (and the offline tests) can run
        # even on a computer where the Gemini package isn't installed yet.
        from google import genai

        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        self._client = genai.Client(api_key=api_key)

    def _ask(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        """Send one prompt to Gemini and return its answer as a `schema` object.

        Uses Google's Interactions API with structured output
        (see https://ai.google.dev/gemini-api/docs/structured-output).
        """
        interaction = self._client.interactions.create(
            model=self.model,
            system_instruction=prompts.SYSTEM_INSTRUCTION,
            input=prompt,
            # The "form" Gemini must fill in: a JSON schema generated from Pydantic.
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
            # Privacy: ask Google not to keep this conversation for later retrieval.
            # (Note: on the FREE tier Google may still use requests to improve its
            # products - which is why users are told not to enter real personal data.)
            store=False,
        )
        # Pydantic validates the JSON. If anything is missing or the wrong type,
        # this raises an error, and the app shows a safe fallback message.
        return schema.model_validate_json(interaction.output_text)

    def check_followups(self, symptoms: str, age_group: str, duration: str, language: str) -> FollowUpCheck:
        prompt = prompts.build_followup_prompt(symptoms, age_group, duration, language)
        return self._ask(prompt, FollowUpCheck)

    def assess(
        self, symptoms: str, age_group: str, duration: str, language: str, followup_qa: list
    ) -> Assessment:
        prompt = prompts.build_assessment_prompt(symptoms, age_group, duration, language, followup_qa)
        return self._ask(prompt, Assessment)


def http_status_of(error: Exception):
    """Find the HTTP status code inside a Gemini error, if there is one.

    Useful for friendly messages: 429 = rate limit (free tier is busy),
    401/403 = bad or missing API key.
    """
    for attr in ("status_code", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    return None
