"""
Tests for red_flags.py - the keyword safety net.

Each test describes, in its name, one behavior we promise. If someone edits the
keyword lists later and breaks one of these promises, the test fails.
"""

import pytest

import red_flags
from levels import TriageLevel


def rule_ids(text, age_group="adult"):
    return {hit.rule.rule_id for hit in red_flags.check_red_flags(text, age_group)}


# --- Matching works in both languages and ignores accents / capital letters ---
@pytest.mark.parametrize(
    "text, expected_rule",
    [
        ("I have crushing chest pain", "chest_pain"),
        ("Tengo DOLOR DE PECHO desde anoche", "chest_pain"),
        ("siento presión en el pecho", "chest_pain"),          # accent on "presión"
        ("I can't breathe", "breathing"),                       # apostrophe
        ("I cant breathe", "breathing"),                        # no apostrophe
        ("me falta el aire", "breathing"),
        ("her speech is slurred", "stroke"),
        ("tiene la boca torcida", "stroke"),
        ("he had a seizure", "unconscious_or_seizure"),
        ("tuvo convulsiones", "unconscious_or_seizure"),
        ("my tongue is swollen", "allergic_swelling"),
        ("se me cierra la garganta", "allergic_swelling"),
        ("worst headache of my life", "sudden_severe_headache"),
        ("el peor dolor de cabeza de mi vida", "sudden_severe_headache"),
        ("estoy vomitando sangre", "severe_bleeding"),
    ],
)
def test_emergency_phrases_match_in_english_and_spanish(text, expected_rule):
    assert expected_rule in rule_ids(text)


def test_everyday_symptoms_do_not_trigger_rules():
    assert rule_ids("I have a runny nose and I'm sneezing a lot") == set()
    assert rule_ids("Tengo la nariz tapada y un poco de tos") == set()


def test_whole_words_only():
    # "fainting" should match, but a word merely containing it should not.
    assert "unconscious_or_seizure" in rule_ids("I keep fainting")
    assert rule_ids("the paint is faintingly old") == set()


# --- Combination rules need BOTH ingredients ---
def test_stiff_neck_alone_is_not_an_emergency():
    assert "fever_with_stiff_neck" not in rule_ids("I slept wrong and have a stiff neck")


def test_stiff_neck_with_fever_is_an_emergency():
    assert "fever_with_stiff_neck" in rule_ids("fever of 102 and a stiff neck")
    assert "fever_with_stiff_neck" in rule_ids("tiene fiebre y el cuello rígido")


def test_pregnancy_with_bleeding_is_an_emergency():
    assert "pregnancy_warning" in rule_ids("I'm 20 weeks pregnant and I'm bleeding")
    assert "pregnancy_warning" in rule_ids("estoy embarazada y tengo sangrado")
    assert "pregnancy_warning" not in rule_ids("I'm pregnant and a bit tired")


# --- Age-specific rule ---
def test_infant_fever_only_applies_to_babies():
    hits = red_flags.check_red_flags("my baby has a fever of 100.6", "infant")
    assert [h.rule.rule_id for h in hits] == ["infant_fever"]
    assert red_flags.highest_level(hits) == TriageLevel.URGENT
    assert not red_flags.stops_the_flow(hits)  # sets a floor; the AI still runs
    assert rule_ids("I have a fever of 100.6", "adult") == set()


# --- Crisis rules show crisis help instead of a normal result ---
def test_crisis_phrases_are_detected_in_both_languages():
    for text in ("I want to kill myself", "quiero quitarme la vida", "I've been thinking about self-harm"):
        hits = red_flags.check_red_flags(text, "adult")
        assert red_flags.has_crisis(hits), text
        assert red_flags.stops_the_flow(hits)


# --- Known, accepted limitation (documented in README) ---
def test_negation_is_not_understood_and_errs_on_the_safe_side():
    # "no chest pain" still matches. This is a deliberate trade-off: a false
    # alarm is safer than a missed emergency.
    assert "chest_pain" in rule_ids("no chest pain, just a cough")


def test_normalize_removes_accents_case_and_punctuation():
    assert red_flags.normalize("¡DOLOR de pécho!  can't") == "dolor de pecho cant"
