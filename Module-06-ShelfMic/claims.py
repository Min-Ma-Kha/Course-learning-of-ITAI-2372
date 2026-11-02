"""Rule-based claim checker (stretch goal D: product-claim verification).

Compares the AI's copy with the approved facts the user typed. It does not
ask the LLM to grade itself: everything here is plain Python, so the same
input always gets the same verdict. Anything flagged goes to a person for
review; the checker never silently rewrites copy.

Known limits (worth discussing in the report):
  * It only knows the claim words listed below. An invented claim that uses
    other words ("breathable", "lightweight") slips through.
  * It can't read negation, so "not waterproof" is flagged too.
"""

import re

# (category, regex). A match is flagged only if the same words are NOT in the facts.
CLAIM_PATTERNS = [
    ("Unverified claim", r"\b[a-z]+-?proof\b"),  # waterproof, shockproof, scratch-proof
    ("Unverified claim", r"\bwater[- ]?resistant\b"),
    ("Unverified claim", r"\bslip[- ]?resistant\b|\bnon[- ]?slip\b"),
    ("Unverified claim", r"\bguarantee[sd]?\b"),
    ("Unverified claim", r"\bwarrant(?:y|ies)\b"),
    ("Unverified claim", r"\bcertifi(?:ed|cation)\b"),
    ("Unverified claim", r"\b(?:fda|ul|ce)[- ]?(?:approved|listed)\b"),
    ("Unverified claim", r"\bclinically\b|\bproven\b|\bdermatologist\b|\bdoctor[- ]recommended\b"),
    ("Unverified claim", r"\blifetime\b"),
    ("Unverified claim", r"\beco[- ]?friendly\b|\bsustainabl[ey]\b|\borganic\b|\brecycled\b|\bbiodegradable\b"),
    ("Unverified claim", r"\bhypoallergenic\b|\bnon[- ]?toxic\b|\bbpa[- ]?free\b"),
    ("Unverified claim", r"\bunbreakable\b|\bindestructible\b|\bmilitary[- ]grade\b"),
    ("Hype or urgency", r"\bbest(?:[- ]selling)?\b|#\s?1\b|\bnumber one\b|\baward[- ]winning\b|\b100\s?%"),
    ("Hype or urgency", r"\blimited[- ]time\b|\bhurry\b|\bwhile supplies last\b|\bonly \d+ left\b|\bact now\b"),
]

STOPWORDS = {"and", "the", "for", "with", "from", "that", "this", "your", "into", "are"}
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


def _norm(text):
    """Lowercase and drop spaces/punctuation so 'water resistant' == 'water-resistant'."""
    return re.sub(r"[^a-z0-9%#]+", "", text.lower())


def _context(text, start, end, width=40):
    left = max(0, start - width)
    right = min(len(text), end + width)
    return " ".join(text[left:right].split())


def _keyword_used(keyword, lower_text, words):
    """Exact phrase match, or every meaningful word of the keyword appears (allowing word endings)."""
    k = keyword.lower()
    if k in lower_text:
        return True
    tokens = [t for t in re.findall(r"[a-z0-9]+", k) if (len(t) > 2 or t.isdigit()) and t not in STOPWORDS]
    if not tokens:
        return False
    found = 0
    for token in tokens:
        if token.isdigit():
            found += token in words
        else:
            stem = token[: max(4, len(token) - 2)]
            found += any(w.startswith(stem) for w in words)
    # Longer phrases count as used if all but one meaningful word appears
    # ("designed for day hikes" -> "...for day hikes").
    needed = len(tokens) - 1 if len(tokens) >= 3 else len(tokens)
    return found >= needed


def check_description(text, product_name, keywords, min_words, max_words):
    """Return a report: word count, length status, keyword coverage and flagged claims."""
    facts_text = " ".join([product_name, *keywords])
    facts_norm = _norm(facts_text)
    lower = text.lower()

    flags, seen = [], set()
    for category, pattern in CLAIM_PATTERNS:
        for match in re.finditer(pattern, lower):
            term = match.group(0).strip()
            key = _norm(term)
            if key in seen or key in facts_norm:
                continue
            seen.add(key)
            flags.append({"type": category, "term": term, "context": _context(text, match.start(), match.end())})

    fact_numbers = set(re.findall(r"\d+(?:\.\d+)?", facts_text))
    for match in re.finditer(r"\d+(?:\.\d+)?", text):
        number = match.group(0)
        if number in fact_numbers or number in seen or any(number in f["term"] for f in flags):
            continue
        seen.add(number)
        flags.append({"type": "Number not in facts", "term": number, "context": _context(text, match.start(), match.end())})

    words = [w.lower() for w in re.findall(r"[a-z0-9]+", lower)]
    used = [k for k in keywords if _keyword_used(k, lower, words)]
    missing = [k for k in keywords if k not in used]

    word_count = len(WORD_RE.findall(text))
    if word_count < int(min_words * 0.8):
        length_status = "short"
    elif word_count > int(max_words * 1.15 + 0.5):
        length_status = "long"
    else:
        length_status = "ok"

    return {
        "word_count": word_count,
        "min_words": min_words,
        "max_words": max_words,
        "length_status": length_status,
        "keywords_used": used,
        "keywords_missing": missing,
        "flags": flags,
    }
