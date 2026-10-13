"""
triage_pipeline.py - The "brain" that combines the rules and the AI.

Course: ITAI 2372 - Module 03 (AI in Healthcare)
Project: Mirror Triage

PLAIN-LANGUAGE SUMMARY
----------------------
This file decides the final triage level. It never shows anything on screen
(that is app.py's job), which means the exact same logic is used by:
  * the web app (app.py), and
  * the evaluation script (evaluate.py) that scores the app on test cases.

THE FLOW
--------
  1. RULES FIRST   Check the patient's own words for emergency warning signs
                   (red_flags.py). Emergency or crisis -> stop, no AI needed.
  2. FOLLOW-UPS    Ask Gemini whether it needs more details. Also re-check the
                   rules on Gemini's English translation (a second safety net
                   for phrasings the Spanish/English keyword lists missed).
  3. ASSESSMENT    Gemini returns a structured triage assessment.
  4. SAFETY RULES  Plain code can only RAISE the AI's level, never lower it:
                     - AI says confidence is "low"         -> move up one level
                     - AI noticed red flags but chose a low level -> at least URGENT
                     - a rule set a minimum level (e.g. infant fever) -> respect it
                     - a rule matches the English translation -> EMERGENCY
                   Every adjustment is recorded so the patient and clinician can
                   see exactly what happened and why (transparency).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import red_flags
from gemini_client import Assessment, FollowUpCheck, TriageAIClient
from levels import TriageLevel, escalate, level_from_name

# Where a final result came from (shown in the clinician view).
SOURCE_RULES = "rules"    # emergency rule matched; AI was not used
SOURCE_CRISIS = "crisis"  # suicide / self-harm rule matched; AI was not used
SOURCE_AI = "ai"          # Gemini assessment + safety rules


@dataclass
class PatientIntake:
    """What the patient entered on the first screen."""

    symptoms: str
    age_group: str  # "infant" | "child" | "adult" | "older_adult"
    duration: str   # "lt_24h" | "1_3_days" | "4_7_days" | "gt_week"
    language: str   # "en" | "es"  (language for the patient-facing text)


@dataclass
class SafetyNote:
    """One automatic safety adjustment, stored as a code so app.py can explain
    it in English OR Spanish (see ui_text.py)."""

    code: str         # "low_confidence" | "ai_red_flags" | "rule_floor" | "translation_rule"
    detail: str = ""  # e.g. the rule id that caused it


@dataclass
class TriageResult:
    """Everything the results screen needs."""

    level: TriageLevel
    source: str
    red_flag_hits: list = field(default_factory=list)
    assessment: Assessment | None = None
    ai_level: TriageLevel | None = None
    safety_notes: list = field(default_factory=list)
    followup_qa: list = field(default_factory=list)


def _top_hit(hits: list):
    """The matched rule with the highest minimum level (crisis rules first)."""
    return max(hits, key=lambda h: (h.rule.kind == red_flags.CRISIS, h.rule.min_level))


# ---------------------------------------------------------------------------
# Step 1 - rules only
# ---------------------------------------------------------------------------
def screen_with_rules(text: str, age_group: str):
    """Run the red-flag rules on raw patient text.

    Returns a finished TriageResult if the app should stop right here
    (emergency or crisis); otherwise returns None so the AI steps can run.
    """
    hits = red_flags.check_red_flags(text, age_group)
    if red_flags.has_crisis(hits):
        return TriageResult(level=TriageLevel.EMERGENCY, source=SOURCE_CRISIS, red_flag_hits=hits)
    if red_flags.stops_the_flow(hits):
        return TriageResult(level=TriageLevel.EMERGENCY, source=SOURCE_RULES, red_flag_hits=hits)
    return None


# ---------------------------------------------------------------------------
# Step 2 - follow-up questions
# ---------------------------------------------------------------------------
def get_followups(intake: PatientIntake, client: TriageAIClient):
    """Ask the AI whether it needs more information.

    Returns (followup_check, early_result). `early_result` is a TriageResult if
    the English translation triggered an emergency rule, otherwise None.
    """
    check: FollowUpCheck = client.check_followups(
        intake.symptoms, intake.age_group, intake.duration, intake.language
    )
    # Second safety net: run the same rules on the AI's English translation.
    early = screen_with_rules(check.english_translation, intake.age_group)
    if early is not None:
        early.safety_notes.append(SafetyNote("translation_rule", _top_hit(early.red_flag_hits).rule.rule_id))
    return check, early


# ---------------------------------------------------------------------------
# Steps 3 + 4 - assessment and safety rules
# ---------------------------------------------------------------------------
def apply_safety_rules(ai_level: TriageLevel, assessment: Assessment, rule_hits: list, translation_hits: list):
    """Combine the AI's answer with the deterministic safety rules.

    The function can only make the level MORE urgent. Returns (level, notes).
    """
    level = ai_level
    notes = []

    # Rule A - the AI admits it is unsure -> round UP one level.
    if assessment.confidence == "low" and level < TriageLevel.EMERGENCY:
        level = escalate(level)
        notes.append(SafetyNote("low_confidence"))

    # Rule B - the AI itself noticed warning signs but still chose a low level.
    if assessment.red_flags_noticed and level < TriageLevel.URGENT:
        level = TriageLevel.URGENT
        notes.append(SafetyNote("ai_red_flags"))

    # Rule C - a non-emergency rule (e.g. infant fever) set a minimum level.
    floor = red_flags.highest_level(rule_hits)
    if floor is not None and level < floor:
        level = floor
        notes.append(SafetyNote("rule_floor", _top_hit(rule_hits).rule.rule_id))

    # Rule D - an emergency rule matched the AI's English translation.
    if red_flags.stops_the_flow(translation_hits) and level < TriageLevel.EMERGENCY:
        level = TriageLevel.EMERGENCY
        notes.append(SafetyNote("translation_rule", _top_hit(translation_hits).rule.rule_id))

    return level, notes


def assess(intake: PatientIntake, client: TriageAIClient, followup_qa: list | None = None) -> TriageResult:
    """Run the full assessment (after any follow-up questions were answered).

    Args:
        followup_qa: list of (question, answer) pairs; may be empty.
    """
    followup_qa = followup_qa or []

    # The follow-up ANSWERS are new patient words, so check them with the rules
    # too (e.g. a patient might answer "yes, and now I can't breathe").
    all_patient_text = intake.symptoms + "\n" + "\n".join(a for _, a in followup_qa if a)
    stop = screen_with_rules(all_patient_text, intake.age_group)
    if stop is not None:
        stop.followup_qa = followup_qa
        return stop

    # Non-stopping rule hits (like infant fever) become a minimum level.
    rule_hits = red_flags.check_red_flags(all_patient_text, intake.age_group)

    assessment: Assessment = client.assess(
        intake.symptoms, intake.age_group, intake.duration, intake.language, followup_qa
    )
    ai_level = level_from_name(assessment.triage_level)
    translation_hits = red_flags.check_red_flags(assessment.english_translation, intake.age_group)

    # If the translation reveals a suicide/self-harm crisis, show crisis help
    # instead of a normal triage result.
    if red_flags.has_crisis(translation_hits):
        return TriageResult(
            level=TriageLevel.EMERGENCY,
            source=SOURCE_CRISIS,
            red_flag_hits=translation_hits,
            assessment=assessment,
            ai_level=ai_level,
            safety_notes=[SafetyNote("translation_rule", _top_hit(translation_hits).rule.rule_id)],
            followup_qa=followup_qa,
        )

    level, notes = apply_safety_rules(ai_level, assessment, rule_hits, translation_hits)
    return TriageResult(
        level=level,
        source=SOURCE_AI,
        red_flag_hits=rule_hits + [h for h in translation_hits if h not in rule_hits],
        assessment=assessment,
        ai_level=ai_level,
        safety_notes=notes,
        followup_qa=followup_qa,
    )


def triage_once(intake: PatientIntake, client: TriageAIClient) -> TriageResult:
    """One-shot triage with no follow-up questions (used by evaluate.py).

    Same rules and safety logic as the app; the only difference is that a
    script cannot answer follow-up questions, so it goes straight to Step 3.
    """
    stop = screen_with_rules(intake.symptoms, intake.age_group)
    if stop is not None:
        return stop
    return assess(intake, client, followup_qa=[])
