"""
app.py - The Mirror Triage web app (the part people see and click).

Course: ITAI 2372 - Module 03 (AI in Healthcare)
Project: Mirror Triage - multilingual (English / Spanish) symptom triage
Run it:  streamlit run app.py

PLAIN-LANGUAGE SUMMARY
----------------------
This file builds the screens using Streamlit, a Python library that turns a
script into a web page. The app moves through three screens:

  1. INTAKE    - the patient picks a language, describes symptoms, age group
                 and how long it has been going on.
  2. FOLLOW-UP - (only if needed) Gemini asks up to 3 short questions.
  3. RESULT    - a color-coded triage level, advice in the patient's language,
                 and an English summary for the clinic (the "mirror").

All the decision-making lives in triage_pipeline.py; this file only handles
the screens. Streamlit re-runs this whole script on every click, so anything
we need to remember between clicks is stored in `st.session_state`.
"""

from __future__ import annotations

import html
import os
import traceback

import streamlit as st

import red_flags
import triage_pipeline as tp
from gemini_client import GeminiTriageClient, http_status_of
from levels import TriageLevel
from ui_text import LEVEL_COLORS, LEVEL_ICONS, TEXT

st.set_page_config(page_title="Mirror Triage", page_icon="🪞", layout="centered")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_api_key():
    """Read the Gemini API key WITHOUT ever storing it in the code.

    Order of preference:
      1. Streamlit secrets  (used when the app is hosted on Streamlit Cloud)
      2. Environment variable GEMINI_API_KEY (used on your own computer)
    """
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass  # No secrets file on this computer - that's fine, try the next option.
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


@st.cache_resource
def get_ai_client(api_key: str):
    """Create the Gemini client once and reuse it (faster than re-creating it)."""
    model = None
    try:
        model = st.secrets.get("GEMINI_MODEL")
    except Exception:
        pass
    return GeminiTriageClient(api_key=api_key, model=model)


def reset():
    """Clear the current case and go back to the first screen."""
    for key in ("stage", "intake", "followup", "result", "error"):
        st.session_state.pop(key, None)


def show_ai_error(error: Exception, t: dict):
    """Turn a technical error into a friendly, safe message.

    The patient sees a simple message; the full technical error is printed in
    the terminal window running Streamlit, so the developer can debug it.
    """
    traceback.print_exception(error)
    status = http_status_of(error)
    message = t["rate_limited"] if status == 429 else t["ai_error"]
    st.session_state.error = message
    st.session_state.stage = "intake"


def rule_label(rule_id: str, lang: str) -> str:
    """Patient-friendly name of a red-flag rule, in the chosen language."""
    rule = next((r for r in red_flags.RULES if r.rule_id == rule_id), None)
    return rule.label[lang] if rule else rule_id


def build_clinic_summary(result: tp.TriageResult, intake: tp.PatientIntake) -> str:
    """Plain-text English note the patient can download and show the clinic."""
    from prompts import AGE_GROUP_DESCRIPTIONS, DURATION_DESCRIPTIONS

    lines = [
        "MIRROR TRIAGE - PRELIMINARY TRIAGE NOTE (student demo, not a diagnosis)",
        f"Final triage level: {result.level.name}",
        f"Decided by: {'safety rules (AI not used)' if result.source != tp.SOURCE_AI else 'AI assessment + safety rules'}",
        f"Patient language: {'Spanish' if intake.language == 'es' else 'English'}",
        f"Age group: {AGE_GROUP_DESCRIPTIONS.get(intake.age_group, '?')}",
        f"Duration: {DURATION_DESCRIPTIONS.get(intake.duration, '?')}",
        "",
        "Patient's own words:",
        intake.symptoms.strip(),
    ]
    if result.red_flag_hits:
        lines += ["", "Red flags matched by rules: " + ", ".join(h.rule.label["en"] for h in result.red_flag_hits)]
    a = result.assessment
    if a is not None:
        lines += [
            "",
            "English translation: " + a.english_translation,
            f"AI level: {result.ai_level.name if result.ai_level else '?'} (confidence: {a.confidence})",
            "Possible causes: " + "; ".join(f"{c.name_in_english} ({c.likelihood})" for c in a.possible_conditions),
            "",
            "Clinical summary: " + a.clinician_summary_english,
            "",
            "Reasoning: " + a.reasoning_english,
        ]
    if result.safety_notes:
        lines += ["", "Automatic safety adjustments: " + "; ".join(
            TEXT["en"]["safety_notes"][n.code].format(label=rule_label(n.detail, "en")) for n in result.safety_notes
        )]
    if result.followup_qa:
        lines += ["", "Follow-up Q&A (patient's language):"]
        lines += [f"  Q: {q}\n  A: {ans or '(no answer)'}" for q, ans in result.followup_qa]
    lines += ["", "Offer a qualified medical interpreter for higher-stakes conversations if needed."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Screen pieces
# ---------------------------------------------------------------------------
def render_banner(level: TriageLevel, t: dict):
    """The big color-coded result banner."""
    bg, fg = LEVEL_COLORS[level]
    name = html.escape(t["level_name"][level])
    action = html.escape(t["level_action"][level])
    st.markdown(
        f"""<div style="background:{bg};color:{fg};padding:1.1rem 1.25rem;border-radius:12px;margin:0.5rem 0 1rem;">
              <div style="font-size:1.35rem;font-weight:700;">{LEVEL_ICONS[level]} {name}</div>
              <div style="font-size:1.05rem;margin-top:0.35rem;">{action}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def render_intake(t: dict, lang: str):
    """Screen 1: describe symptoms."""
    if st.session_state.get("error"):
        st.error(st.session_state.pop("error"))

    with st.form("intake_form"):
        symptoms = st.text_area(
            t["symptoms_label"], help=t["symptoms_help"], placeholder=t["symptoms_placeholder"], height=140
        )
        age_group = st.selectbox(
            t["age_label"], options=list(t["age_options"]), index=2,
            format_func=lambda k: t["age_options"][k],
        )
        duration = st.selectbox(
            t["duration_label"], options=list(t["duration_options"]),
            format_func=lambda k: t["duration_options"][k],
        )
        submitted = st.form_submit_button(t["submit"], type="primary", width="stretch")

    if not submitted:
        return
    if len(symptoms.strip()) < 8:
        st.warning(t["too_short"])
        return

    intake = tp.PatientIntake(symptoms=symptoms, age_group=age_group, duration=duration, language=lang)
    st.session_state.intake = intake

    # STEP 1 - safety rules run first, with no AI and no internet needed.
    stop = tp.screen_with_rules(intake.symptoms, intake.age_group)
    if stop is not None:
        st.session_state.result = stop
        st.session_state.stage = "result"
        st.rerun()

    api_key = get_api_key()
    if not api_key:
        st.error(t["no_key"])
        return

    # STEP 2 - ask Gemini whether follow-up questions are needed.
    try:
        with st.spinner(t["thinking"]):
            check, early = tp.get_followups(intake, get_ai_client(api_key))
    except Exception as error:  # network problems, rate limits, invalid output...
        show_ai_error(error, t)
        st.rerun()

    if early is not None:  # an emergency rule matched the English translation
        st.session_state.result = early
        st.session_state.stage = "result"
    elif check.follow_up_questions and not check.enough_information:
        st.session_state.followup = check
        st.session_state.stage = "followup"
    else:
        run_assessment(intake, [], t, api_key)
    st.rerun()


def run_assessment(intake: tp.PatientIntake, qa: list, t: dict, api_key: str):
    """STEPS 3 + 4 - Gemini assessment, then the safety rules."""
    try:
        with st.spinner(t["thinking"]):
            st.session_state.result = tp.assess(intake, get_ai_client(api_key), qa)
        st.session_state.stage = "result"
    except Exception as error:
        show_ai_error(error, t)


def render_followup(t: dict):
    """Screen 2: answer Gemini's follow-up questions (or skip them)."""
    check = st.session_state.followup
    intake = st.session_state.intake
    st.subheader(t["followup_title"])
    st.caption(t["followup_intro"])

    with st.form("followup_form"):
        answers = [
            st.text_input(f"{i}. {q}", key=f"answer_{i}", placeholder=t["followup_answer"])
            for i, q in enumerate(check.follow_up_questions, start=1)
        ]
        col1, col2 = st.columns(2)
        go = col1.form_submit_button(t["followup_submit"], type="primary", width="stretch")
        skip = col2.form_submit_button(t["followup_skip"], width="stretch")

    if go or skip:
        qa = [] if skip else list(zip(check.follow_up_questions, answers))
        run_assessment(intake, qa, t, get_api_key())
        st.rerun()


def render_result(t: dict, lang: str):
    """Screen 3: the result, mirrored for the patient and the clinic."""
    result: tp.TriageResult = st.session_state.result
    intake: tp.PatientIntake = st.session_state.intake
    st.subheader(t["result_title"])

    if result.source == tp.SOURCE_CRISIS:
        # Crisis screen: fixed, human-written text with the 988 lifeline.
        st.error(f"### {t['crisis_title']}\n\n{t['crisis_body']}")
    else:
        render_banner(result.level, t)

    if result.source == tp.SOURCE_RULES:
        st.markdown(f"**{t['rules_title']}**")
        st.write(t["rules_intro"])
        for label in dict.fromkeys(h.rule.label[lang] for h in result.red_flag_hits):
            st.markdown(f"- {label}")

    a = result.assessment
    if result.source == tp.SOURCE_AI and a is not None:
        st.markdown(f"#### {t['advice_title']}")
        st.write(a.advice_for_patient)

        st.markdown(f"#### {t['watch_title']}")
        for sign in a.warning_signs_to_watch:
            st.markdown(f"- {sign}")

        st.markdown(f"#### {t['conditions_title']}")
        st.caption(t["conditions_note"])
        for c in a.possible_conditions:
            st.markdown(f"- **{c.name_for_patient}** - {t['likelihood'].get(c.likelihood, c.likelihood)}")

    if result.safety_notes:
        with st.expander(t["safety_title"]):
            for note in result.safety_notes:
                st.markdown("- " + t["safety_notes"][note.code].format(label=rule_label(note.detail, lang)))

    # The "mirror": the same case summarized in English for the clinic.
    summary = build_clinic_summary(result, intake)
    with st.expander(t["clinic_title"], expanded=(lang == "es")):
        st.caption(t["clinic_help"])
        st.text(summary)
        st.download_button(t["download"], data=summary, file_name="mirror_triage_summary.txt", mime="text/plain")

    st.button(t["start_over"], on_click=reset, width="stretch")


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------
def main():
    # Language picker (stays at the top of every screen).
    lang = st.radio(
        "Language / Idioma", options=["en", "es"], horizontal=True,
        format_func=lambda k: "English" if k == "en" else "Español", key="lang",
    )
    t = TEXT[lang]

    st.title(f"🪞 {t['title']}")
    st.write(t["tagline"])
    st.warning(t["demo_warning"])
    st.caption(t["privacy_warning"])

    with st.sidebar:
        st.header(t["about_title"])
        st.markdown(t["about_body"])

    stage = st.session_state.get("stage", "intake")
    if stage == "followup":
        render_followup(t)
    elif stage == "result":
        render_result(t, lang)
    else:
        render_intake(t, lang)

    st.divider()
    st.caption(t["footer"])


main()
