"""
levels.py - The four triage levels used everywhere in Mirror Triage.

Course: ITAI 2372 - Module 03 (AI in Healthcare)
Project: Mirror Triage - multilingual (English / Spanish) symptom triage

PLAIN-LANGUAGE SUMMARY
----------------------
"Triage" means deciding HOW SOON someone needs medical care, not WHAT
illness they have. Mirror Triage sorts every result into one of four levels,
from least to most serious:

    1. SELF_CARE     - can be handled at home, with signs to watch for
    2. PRIMARY_CARE  - see a regular doctor in the next few days
    3. URGENT        - needs medical care today (within hours, not days)
    4. EMERGENCY     - call 911 or go to the emergency room now

The levels are stored as numbers (1-4) so the code can easily compare them
("is this result MORE serious than that one?") and always keep the safer,
higher level when two parts of the app disagree.
"""

from enum import IntEnum


class TriageLevel(IntEnum):
    """Triage levels ordered from least (1) to most (4) serious.

    Because this is an IntEnum, normal comparisons work:
        TriageLevel.EMERGENCY > TriageLevel.URGENT  ->  True
        max(TriageLevel.URGENT, TriageLevel.SELF_CARE) -> TriageLevel.URGENT
    """

    SELF_CARE = 1
    PRIMARY_CARE = 2
    URGENT = 3
    EMERGENCY = 4


def escalate(level: TriageLevel) -> TriageLevel:
    """Move a level UP by one step (never past EMERGENCY).

    Used by the safety rules: when the AI is unsure, we round UP, because
    sending someone to care a little too early is much safer than too late.
    """
    return TriageLevel(min(level + 1, TriageLevel.EMERGENCY))


def level_from_name(name: str) -> TriageLevel:
    """Convert the text label the AI returns (e.g. "URGENT") into a level.

    The AI is forced to answer with one of the four exact names (see the
    schema in gemini_client.py), so this lookup should always succeed. If it
    ever gets something unexpected, we fail SAFE by returning EMERGENCY.
    """
    try:
        return TriageLevel[name.strip().upper()]
    except KeyError:
        return TriageLevel.EMERGENCY
