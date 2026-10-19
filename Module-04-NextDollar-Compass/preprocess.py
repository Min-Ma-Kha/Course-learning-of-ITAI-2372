"""
preprocess.py - Text cleaning for expense descriptions.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass

Bank descriptions are noisy. The same coffee purchase can show up as:
    "POS PURCHASE STARBUCKS #10423 HOUSTON TX 10/14"
    "Starbucks Store 10423 Houston Tx"
    "SQ *STARBUCKS"
Cleaning removes the parts that do not tell us WHAT was bought (store numbers,
dates, card-processing prefixes, city/state), so the model can focus on the
merchant name and words like "coffee" or "insurance".
"""

import re

# Card-processor and bank prefixes that appear before the merchant name.
_PREFIX_PATTERNS = [
    r"pos purchase", r"debit card purchase", r"checkcard", r"purchase authorized on \d{1,2}/\d{1,2}",
    r"recurring payment", r"ach debit", r"visa dda pur", r"paypal \*", r"sq \*", r"tst\* ?",
]
_PREFIX_RE = re.compile(r"^(?:" + "|".join(_PREFIX_PATTERNS) + r")\s*")

# Texas cities show up constantly in this region's statements; the state code
# "tx" (and other two-letter state codes at the end) carry no category signal.
_CITY_RE = re.compile(
    r"\b(houston|katy|cypress|sugar land|pearland|richmond|brookshire|waller|spring|austin|dallas|san antonio)\b"
)
_STATE_RE = re.compile(r"\b[a-z]{2}$")

_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_NUMBER_RE = re.compile(r"[#]?\d+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_PUNCT_RE = re.compile(r"[^a-z&+\s]")  # keep letters, & and + (AT&T, Disney+)
_SPACES_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Lowercase, strip bank noise, and return only the meaningful words."""
    if not isinstance(text, str):
        return ""
    t = text.lower().strip()
    t = _URL_RE.sub(" ", t)
    t = _PREFIX_RE.sub("", t)
    t = _DATE_RE.sub(" ", t)
    t = _NUMBER_RE.sub(" ", t)
    t = t.replace(".com", " ").replace("*", " ")
    t = _PUNCT_RE.sub(" ", t)
    t = _CITY_RE.sub(" ", t)
    t = _SPACES_RE.sub(" ", t).strip()
    # Only drop a trailing 2-letter state code when something else remains.
    if len(t.split()) > 1:
        t = _STATE_RE.sub("", t).strip()
    return t
