"""
red_flags.py - The safety net that runs BEFORE any AI is used.

Course: ITAI 2372 - Module 03 (AI in Healthcare)
Project: Mirror Triage

PLAIN-LANGUAGE SUMMARY
----------------------
Large language models (LLMs) are powerful but not perfectly reliable. A 2026
study of a consumer AI health tool found it under-triaged (rated as less
serious) about half of clear emergency cases. So Mirror Triage does NOT let the
AI decide alone when a life may be at risk.

This file is a simple, predictable checklist of emergency warning signs,
written in BOTH English and Spanish. If a patient's words match one of these
signs, the app immediately says "call 911" (or shows crisis-line information)
WITHOUT waiting for the AI. Rules like this are boring on purpose: they behave
the same way every time, and anyone can read and check them.

WHERE THE WARNING SIGNS COME FROM (public health sources)
---------------------------------------------------------
- MedlinePlus (U.S. National Library of Medicine): "Recognizing medical
  emergencies" - chest pain, breathing problems, fainting, seizures, bleeding
  that won't stop, swelling of the face/eyes/tongue, poisoning, head injury,
  severe abdominal pain, bluish skin in children, fever with a stiff neck, and
  suicidal or homicidal feelings.
- CDC stroke signs ("BE FAST"): face drooping, arm/one-sided weakness or
  numbness, slurred speech, sudden vision trouble, sudden confusion, sudden
  severe headache.
- American Academy of Pediatrics (healthychildren.org): a baby younger than
  3 months with a fever of 100.4 F (38.0 C) or higher needs a doctor right away.
- CDC "Hear Her" urgent maternal warning signs: bleeding or fluid leaking during
  pregnancy, or severe belly pain, need medical care immediately.

KNOWN LIMITATION (stated honestly)
----------------------------------
Keyword rules cannot understand negation. "I have NO chest pain" still matches
"chest pain" and sends the user to the emergency screen. We accept this on
purpose: a false alarm costs a phone call, while a missed emergency can cost a
life. The AI-based steps later in the app handle the subtle cases.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from levels import TriageLevel

# The two kinds of rule:
#   "emergency" -> show the "call 911 now" screen
#   "crisis"    -> show suicide & crisis lifeline (988) information
EMERGENCY = "emergency"
CRISIS = "crisis"

# Age groups the app asks about (the same keys are used in app.py).
INFANT = "infant"            # younger than 3 months
CHILD = "child"              # 3 months to 17 years
ADULT = "adult"              # 18 to 64 years
OLDER_ADULT = "older_adult"  # 65 years and older


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Clean up text so small spelling differences don't break matching.

    Steps (each one makes matching more forgiving):
      1. lower-case everything            "Chest PAIN"  -> "chest pain"
      2. remove accents                   "presión"     -> "presion"
      3. remove apostrophes               "can't"       -> "cant"
      4. turn hyphens/punctuation into spaces  "self-harm" -> "self harm"
      5. squeeze repeated spaces into one

    Every keyword below is written in this same normalized form, so a user who
    types "Dolor de pecho", "dolor de pécho" or "DOLOR DE PECHO" is matched the
    same way.
    """
    text = text.lower()
    # "NFKD" splits letters like "ó" into "o" + an accent mark; we then drop the
    # accent marks (their Unicode category starts with "M").
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("M"))
    text = text.replace("'", "").replace("’", "").replace("`", "")
    # Anything that is not a letter, a number, or a decimal point becomes a space.
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(normalized_text: str, phrase: str) -> bool:
    """True if `phrase` appears in the text as whole words.

    "Whole words" matters: we want "seizure" to match "I had a seizure" but
    NOT accidentally match inside some longer, unrelated word.
    """
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RedFlagRule:
    """One emergency warning sign, with its trigger words in two languages.

    Attributes:
        rule_id:      short internal name, e.g. "chest_pain"
        kind:         EMERGENCY or CRISIS
        min_level:    the LOWEST triage level allowed once this rule matches
        label:        plain-language name shown to the patient, per language
        phrases:      trigger words/phrases (normalized English + Spanish)
        requires_any: for "combination" rules, at least one of these must ALSO
                      appear (e.g. stiff neck AND fever). Empty = not needed.
        age_groups:   only apply to these age groups. Empty = all ages.
        source:       which public guideline the rule is based on
    """

    rule_id: str
    kind: str
    min_level: TriageLevel
    label: dict
    phrases: tuple
    requires_any: tuple = ()
    age_groups: tuple = ()
    source: str = ""


# Words that mean "fever" - reused by two rules below.
FEVER_WORDS = (
    "fever", "feverish", "high temperature", "temperature of", "temp of",
    "fiebre", "calentura", "temperatura alta", "temperatura de",
)

RULES: tuple = (
    RedFlagRule(
        rule_id="chest_pain",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Chest pain or pressure", "es": "Dolor o presión en el pecho"},
        phrases=(
            # English
            "chest pain", "chest pains", "pain in my chest", "pain in the chest",
            "chest pressure", "pressure in my chest", "chest tightness",
            "tight chest", "tightness in my chest", "crushing chest",
            "my chest hurts", "chest hurts",
            # Spanish
            "dolor de pecho", "dolor en el pecho", "dolor en mi pecho",
            "me duele el pecho", "presion en el pecho", "opresion en el pecho",
            "pecho apretado",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="breathing",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Serious trouble breathing", "es": "Dificultad grave para respirar"},
        phrases=(
            "cant breathe", "cannot breathe", "can not breathe",
            "trouble breathing", "difficulty breathing", "struggling to breathe",
            "short of breath", "shortness of breath", "gasping for air", "choking",
            "no puedo respirar", "no puede respirar", "dificultad para respirar",
            "falta de aire", "me falta el aire", "me ahogo", "ahogandome",
            "atragantado", "atragantada",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="stroke",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Possible stroke signs", "es": "Posibles señales de derrame cerebral"},
        phrases=(
            "face drooping", "face is drooping", "drooping face", "face droop",
            "one side of my face", "one side of his face", "one side of her face",
            "slurred speech", "slurring", "speech is slurred",
            "cant speak", "cannot speak", "trouble speaking",
            "numb on one side", "numbness on one side", "weak on one side",
            "weakness on one side", "sudden numbness", "sudden weakness",
            "sudden vision", "suddenly cant see", "lost my vision",
            "sudden confusion", "suddenly confused",
            "cara caida", "cara torcida", "boca torcida", "un lado de la cara",
            "habla arrastrada", "arrastra las palabras", "arrastrando las palabras",
            "no puede hablar", "no puedo hablar", "dificultad para hablar",
            "entumecimiento de un lado", "adormecimiento de un lado",
            "debilidad de un lado", "debilidad en un lado", "se me durmio un lado",
            "perdi la vision", "confusion repentina",
            "confundido de repente", "confundida de repente",
        ),
        source="CDC - Stroke signs and symptoms (BE FAST)",
    ),
    RedFlagRule(
        rule_id="unconscious_or_seizure",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Fainting, unresponsiveness, or seizure",
               "es": "Desmayo, no responde, o convulsiones"},
        phrases=(
            "passed out", "fainted", "fainting", "lost consciousness",
            "unconscious", "unresponsive", "wont wake up",
            "seizure", "seizures", "convulsion", "convulsions",
            "me desmaye", "se desmayo", "desmayo", "desmayos",
            "perdi el conocimiento", "perdio el conocimiento", "inconsciente",
            "no responde", "no despierta", "convulsion", "convulsiones",
            "ataque epileptico",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="severe_bleeding",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Heavy bleeding or bleeding that won't stop",
               "es": "Sangrado abundante o que no para"},
        phrases=(
            "bleeding that wont stop", "wont stop bleeding", "cant stop the bleeding",
            "cant stop bleeding", "heavy bleeding", "bleeding heavily",
            "vomiting blood", "throwing up blood", "coughing up blood", "coughing blood",
            "sangrado que no para", "no para de sangrar", "no deja de sangrar",
            "sangrado abundante", "sangra mucho", "vomito sangre", "vomitando sangre",
            "vomitar sangre", "tos con sangre", "tosiendo sangre", "escupo sangre",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="allergic_swelling",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Swelling of the face, lips, tongue, or throat",
               "es": "Hinchazón de la cara, labios, lengua o garganta"},
        phrases=(
            "throat is closing", "throat closing", "throat swelling", "swollen throat",
            "tongue swelling", "swollen tongue", "tongue is swollen",
            "face swelling", "swollen face", "face is swelling",
            "lips swelling", "swollen lips", "anaphylaxis",
            "se me cierra la garganta", "garganta cerrada", "garganta hinchada",
            "lengua hinchada", "hinchazon de la lengua", "cara hinchada",
            "hinchazon de la cara", "labios hinchados", "anafilaxia",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="sudden_severe_headache",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Sudden, severe headache", "es": "Dolor de cabeza repentino y muy fuerte"},
        phrases=(
            "worst headache", "sudden severe headache", "thunderclap headache",
            "el peor dolor de cabeza", "peor dolor de cabeza de mi vida",
            "dolor de cabeza repentino y fuerte", "dolor de cabeza muy fuerte y repentino",
        ),
        source="CDC - Stroke signs and symptoms",
    ),
    RedFlagRule(
        rule_id="fever_with_stiff_neck",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Fever with a stiff neck", "es": "Fiebre con el cuello rígido"},
        phrases=(
            "stiff neck", "neck is stiff", "neck stiffness",
            "cuello rigido", "rigidez en el cuello", "cuello tieso",
        ),
        requires_any=FEVER_WORDS,  # combination rule: stiff neck AND fever
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="poisoning",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Poisoning or overdose", "es": "Envenenamiento o sobredosis"},
        phrases=(
            "swallowed poison", "poisoning", "poisoned", "overdose", "overdosed",
            "swallowed bleach", "drank bleach", "swallowed chemicals",
            "envenenamiento", "envenenado", "envenenada", "trague veneno",
            "se trago veneno", "sobredosis", "tomo cloro", "trago cloro",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="bluish_skin",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Blue or gray lips or skin", "es": "Labios o piel azulados o grises"},
        phrases=(
            "blue lips", "lips are blue", "lips turning blue", "turning blue",
            "skin is blue", "bluish skin", "gray skin",
            "labios azules", "labios morados", "se esta poniendo azul",
            "piel azulada", "piel morada", "piel gris",
        ),
        source="MedlinePlus - Recognizing medical emergencies (children)",
    ),
    RedFlagRule(
        rule_id="severe_abdominal_pain",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Severe abdominal pain", "es": "Dolor abdominal muy fuerte"},
        phrases=(
            "severe abdominal pain", "severe stomach pain", "severe belly pain",
            "unbearable stomach pain", "worst stomach pain",
            "dolor abdominal severo", "dolor abdominal fuerte",
            "dolor de estomago muy fuerte", "dolor de estomago insoportable",
            "dolor de barriga muy fuerte", "dolor muy fuerte en el estomago",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="head_injury",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Head injury", "es": "Golpe o lesión en la cabeza"},
        phrases=(
            "hit my head", "hit his head", "hit her head", "head injury",
            "fell and hit", "golpe en la cabeza", "me pegue en la cabeza",
            "se pego en la cabeza", "se golpeo la cabeza", "me golpee la cabeza",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="pregnancy_warning",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Bleeding, leaking fluid, or severe pain during pregnancy",
               "es": "Sangrado, salida de líquido o dolor fuerte durante el embarazo"},
        phrases=("pregnant", "pregnancy", "embarazada", "embarazo"),
        requires_any=(  # combination rule: pregnancy AND a warning sign
            "bleeding", "blood", "leaking fluid", "fluid leaking",
            "severe belly pain", "severe stomach pain", "severe abdominal pain",
            "sangrado", "sangre", "sangrando", "salida de liquido",
            "dolor fuerte", "dolor muy fuerte", "dolor severo",
        ),
        source="CDC Hear Her - Urgent maternal warning signs",
    ),
    RedFlagRule(
        rule_id="danger_to_others",
        kind=EMERGENCY,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Thoughts of hurting someone else", "es": "Pensamientos de hacer daño a otra persona"},
        phrases=(
            "kill someone", "hurt someone", "hurt somebody", "kill somebody",
            "matar a alguien", "lastimar a alguien", "hacerle dano a alguien",
        ),
        source="MedlinePlus - Recognizing medical emergencies",
    ),
    RedFlagRule(
        rule_id="infant_fever",
        kind=EMERGENCY,
        min_level=TriageLevel.URGENT,  # AAP: call the doctor RIGHT AWAY
        label={"en": "Fever in a baby younger than 3 months",
               "es": "Fiebre en un bebé menor de 3 meses"},
        phrases=FEVER_WORDS,
        age_groups=(INFANT,),
        source="American Academy of Pediatrics (healthychildren.org)",
    ),
    RedFlagRule(
        rule_id="suicide_or_self_harm",
        kind=CRISIS,
        min_level=TriageLevel.EMERGENCY,
        label={"en": "Thoughts of suicide or self-harm",
               "es": "Pensamientos de suicidio o de hacerse daño"},
        phrases=(
            "suicide", "suicidal", "kill myself", "end my life", "want to die",
            "wanna die", "take my own life", "hurt myself", "harm myself", "self harm",
            "suicidio", "suicidarme", "suicida", "matarme", "quitarme la vida",
            "quiero morir", "quiero morirme", "hacerme dano", "lastimarme", "autolesion",
        ),
        source="MedlinePlus - Recognizing medical emergencies; 988 Suicide & Crisis Lifeline",
    ),
)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RedFlagHit:
    """A rule that matched, plus the exact phrase that triggered it."""

    rule: RedFlagRule
    matched_phrase: str


def check_red_flags(text: str, age_group: str = "") -> list:
    """Return every red-flag rule that matches the patient's text.

    Args:
        text:      anything the patient wrote (symptoms, follow-up answers),
                   or the AI's English translation of it.
        age_group: one of INFANT, CHILD, ADULT, OLDER_ADULT (or "" if unknown).

    Returns:
        A list of RedFlagHit objects. An empty list means "no red flags found"
        (which does NOT mean the person is fine - the AI steps still run).
    """
    clean = normalize(text)
    hits = []
    for rule in RULES:
        # Skip age-specific rules that don't apply to this patient.
        if rule.age_groups and age_group not in rule.age_groups:
            continue

        matched = next((p for p in rule.phrases if contains_phrase(clean, p)), None)
        if matched is None:
            continue

        # Combination rules need a second ingredient (e.g. stiff neck + fever).
        if rule.requires_any and not any(contains_phrase(clean, p) for p in rule.requires_any):
            continue

        hits.append(RedFlagHit(rule=rule, matched_phrase=matched))
    return hits


def has_crisis(hits: list) -> bool:
    """True if any matched rule is a suicide / self-harm crisis rule."""
    return any(hit.rule.kind == CRISIS for hit in hits)


def highest_level(hits: list):
    """The most serious minimum level among the matched rules (or None)."""
    if not hits:
        return None
    return max(hit.rule.min_level for hit in hits)


def stops_the_flow(hits: list) -> bool:
    """Should the app skip the AI and show the emergency/crisis screen now?

    Yes if there is a crisis rule, or any rule whose minimum level is
    EMERGENCY. (The infant-fever rule is URGENT, so it does NOT stop the flow;
    instead it sets a floor the final answer can never go below.)
    """
    return has_crisis(hits) or highest_level(hits) == TriageLevel.EMERGENCY
