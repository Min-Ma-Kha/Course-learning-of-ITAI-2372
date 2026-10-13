"""
Tests for triage_pipeline.py - how the rules and the AI are combined.

These tests use a FAKE AI client that returns answers we choose. That way we
can check the safety logic (e.g. "a low-confidence answer is moved up a level")
without an API key, without internet, and without depending on what the real
model happens to say today.
"""

import triage_pipeline as tp
from gemini_client import Assessment, FollowUpCheck, PossibleCondition
from levels import TriageLevel


def make_assessment(level="PRIMARY_CARE", confidence="high", red_flags=None, translation="mild cough"):
    return Assessment(
        detected_language="English",
        english_translation=translation,
        triage_level=level,
        confidence=confidence,
        reasoning_english="test reasoning",
        possible_conditions=[PossibleCondition(name_for_patient="cold", name_in_english="common cold",
                                               likelihood="more likely")],
        red_flags_noticed=red_flags or [],
        advice_for_patient="rest",
        warning_signs_to_watch=["trouble breathing"],
        clinician_summary_english="summary",
    )


class FakeClient:
    """Stands in for GeminiTriageClient and records how it was called."""

    def __init__(self, assessment=None, followup=None):
        self.assessment = assessment or make_assessment()
        self.followup = followup or FollowUpCheck(
            detected_language="English", english_translation="mild cough",
            enough_information=True, follow_up_questions=[], red_flags_noticed=[],
        )
        self.assess_calls = 0

    def check_followups(self, symptoms, age_group, duration, language):
        return self.followup

    def assess(self, symptoms, age_group, duration, language, followup_qa):
        self.assess_calls += 1
        return self.assessment


def intake(text, age="adult", lang="en"):
    return tp.PatientIntake(symptoms=text, age_group=age, duration="1_3_days", language=lang)


def test_emergency_rule_skips_the_ai_entirely():
    client = FakeClient()
    result = tp.triage_once(intake("sudden chest pain and sweating"), client)
    assert result.level == TriageLevel.EMERGENCY
    assert result.source == tp.SOURCE_RULES
    assert client.assess_calls == 0  # the AI was never asked


def test_crisis_text_goes_to_crisis_screen():
    result = tp.triage_once(intake("quiero morir", lang="es"), FakeClient())
    assert result.source == tp.SOURCE_CRISIS


def test_confident_ai_answer_is_kept():
    result = tp.triage_once(intake("mild cough for two days"), FakeClient())
    assert result.level == TriageLevel.PRIMARY_CARE
    assert result.safety_notes == []


def test_low_confidence_moves_result_up_one_level():
    client = FakeClient(make_assessment(level="SELF_CARE", confidence="low"))
    result = tp.triage_once(intake("I feel kind of off"), client)
    assert result.ai_level == TriageLevel.SELF_CARE
    assert result.level == TriageLevel.PRIMARY_CARE
    assert [n.code for n in result.safety_notes] == ["low_confidence"]


def test_ai_noticed_red_flags_raise_to_at_least_urgent():
    client = FakeClient(make_assessment(level="SELF_CARE", red_flags=["possible dehydration"]))
    result = tp.triage_once(intake("vomiting since this morning"), client)
    assert result.level == TriageLevel.URGENT


def test_infant_fever_rule_sets_a_minimum_of_urgent():
    client = FakeClient(make_assessment(level="SELF_CARE"))
    result = tp.triage_once(intake("my baby has a fever", age="infant"), client)
    assert client.assess_calls == 1          # the AI still ran...
    assert result.level == TriageLevel.URGENT  # ...but could not go below URGENT
    assert "rule_floor" in [n.code for n in result.safety_notes]


def test_rule_match_in_english_translation_forces_emergency():
    # Patient wrote in a way our Spanish list misses, but the AI's English
    # translation contains "shortness of breath" -> second safety net fires.
    client = FakeClient(make_assessment(level="URGENT", translation="I have shortness of breath when walking"))
    result = tp.triage_once(intake("me cuesta mucho jalar aire al caminar", lang="es"), client)
    assert result.level == TriageLevel.EMERGENCY
    assert "translation_rule" in [n.code for n in result.safety_notes]


def test_safety_rules_never_lower_the_ai_level():
    client = FakeClient(make_assessment(level="EMERGENCY", confidence="low"))
    result = tp.triage_once(intake("something feels very wrong"), client)
    assert result.level == TriageLevel.EMERGENCY


def test_red_flag_in_followup_answer_stops_the_flow():
    client = FakeClient()
    qa = [("Is it getting worse?", "yes and now I can't breathe")]
    result = tp.assess(intake("cough for two days"), client, qa)
    assert result.source == tp.SOURCE_RULES
    assert client.assess_calls == 0


def test_followup_translation_can_trigger_emergency_early():
    followup = FollowUpCheck(
        detected_language="Spanish", english_translation="My face is drooping on one side",
        enough_information=False, follow_up_questions=["¿Desde cuándo?"], red_flags_noticed=[],
    )
    check, early = tp.get_followups(intake("se me cayó la cara de un lado", lang="es"), FakeClient(followup=followup))
    assert early is not None and early.level == TriageLevel.EMERGENCY
