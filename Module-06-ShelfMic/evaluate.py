"""Run the assignment's controlled experiments and save the results.

Usage (from the project folder, with your API key set):
    python evaluate.py              run every experiment (about 13 model calls, plus rewrites)
    python evaluate.py A F          run only experiments A and F (saves free-tier quota)

Writes results.csv (open in Excel; fill in the human score columns) and
results.md (a readable summary for the report).
"""

import csv
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from generator import create_description  # noqa: E402
from llm import LLMError, provider_label  # noqa: E402

BOOTS = "TrailRunner Leather Boots"
BASE = ["full-grain leather upper", "rubber outsole", "padded collar", "lace-up closure", "designed for day hikes"]
RICH = BASE + ["water-resistant finish", "cushioned EVA midsole", "weighs 2.1 lb per pair", "sizes 7-13"]
HIKERS = "Hikers and outdoor enthusiasts"

# (experiment, what changes, value, product, facts, audience, tone, channel)
EXPERIMENTS = [
    ("A", "tone", "casual", BOOTS, BASE, HIKERS, "casual", "product_page"),
    ("A", "tone", "formal", BOOTS, BASE, HIKERS, "formal", "product_page"),
    ("A", "tone", "humorous", BOOTS, BASE, HIKERS, "humorous", "product_page"),
    ("B", "audience", HIKERS, BOOTS, BASE, HIKERS, "neutral", "product_page"),
    ("B", "audience", "Beginner hikers", BOOTS, BASE, "Beginner hikers", "neutral", "product_page"),
    ("B", "audience", "Retail professionals", BOOTS, BASE, "Retail professionals", "neutral", "product_page"),
    ("C", "facts", "basic (5 facts)", BOOTS, BASE, HIKERS, "casual", "product_page"),
    ("C", "facts", "rich (9 facts)", BOOTS, RICH, HIKERS, "casual", "product_page"),
    ("D", "facts", "remove 'full-grain leather upper'", BOOTS, BASE[1:], HIKERS, "casual", "product_page"),
    ("E", "channel", "marketplace bullets", BOOTS, BASE, HIKERS, "casual", "marketplace"),
    ("E", "channel", "social caption", BOOTS, BASE, HIKERS, "casual", "social"),
    ("E", "channel", "shelf tag", BOOTS, BASE, HIKERS, "casual", "shelf_tag"),
    ("F", "claim trap", "water-resistant, not waterproof", "Weekender Rain Jacket",
     ["water-resistant shell", "packable hood", "zippered hand pockets", "machine washable"],
     "Daily commuters", "auto", "product_page"),
]
NAMES = {
    "A": "Tone (facts fixed)",
    "B": "Audience (tone fixed)",
    "C": "Basic vs. richer facts",
    "D": "Remove one fact (compare with C basic)",
    "E": "Sales channel (compare with C basic = product page)",
    "F": "Claim trap",
}
SCORE_COLUMNS = ["score_accuracy", "score_audience_fit", "score_tone", "score_readability", "score_keywords", "score_usefulness"]
DELAY = float(os.getenv("EVAL_DELAY", "6"))  # seconds between runs, to stay under free-tier rate limits


def run_one(exp):
    letter, variable, value, product, facts, audience, tone, channel = exp
    for attempt in (1, 2):
        try:
            return create_description(product, facts, audience, tone, channel), None
        except LLMError as exc:
            if exc.retryable and attempt == 1:
                print(f"    {exc}  Waiting 30 s and trying once more...")
                time.sleep(30)
                continue
            return None, str(exc)


def main():
    wanted = {a.upper() for a in sys.argv[1:]}
    runs = [e for e in EXPERIMENTS if not wanted or e[0] in wanted]
    print(f"Running {len(runs)} experiments with {provider_label()}\n")

    rows = []
    for i, exp in enumerate(runs, 1):
        letter, variable, value, product, facts, audience, tone, channel = exp
        print(f"[{i}/{len(runs)}] {letter} {variable} = {value}")
        result, error = run_one(exp)
        row = {
            "experiment": f"{letter}: {NAMES[letter]}",
            "variable": variable,
            "value": value,
            "product": product,
            "facts": "; ".join(facts),
            "audience": audience,
            "tone_requested": tone,
            "channel": channel,
            "model": provider_label(),
            "error": error or "",
        }
        if result:
            checks = result["checks"]
            row.update({
                "segment": result["plan"]["segment"],
                "tone_used": result["plan"]["tone"],
                "seconds": result["seconds"],
                "model_calls": result["calls"],
                "word_count": checks["word_count"],
                "target_words": f"{checks['min_words']}-{checks['max_words']}",
                "length_status": checks["length_status"],
                "keywords_used": f"{len(checks['keywords_used'])}/{len(facts)}",
                "keywords_missing": "; ".join(checks["keywords_missing"]),
                "flags_first_draft": "; ".join(f["term"] for f in result["first_flags"]),
                "rewrite": result["retry_note"] or "",
                "flags_final": "; ".join(f["term"] for f in checks["flags"]),
                "description": result["description"],
            })
            print(f"    {checks['word_count']} words, keywords {row['keywords_used']}, "
                  f"first-draft flags: {row['flags_first_draft'] or 'none'}, final flags: {row['flags_final'] or 'none'}")
        else:
            print(f"    FAILED: {error}")
        for col in SCORE_COLUMNS:
            row[col] = ""
        rows.append(row)
        if i < len(runs):
            time.sleep(DELAY)

    columns = list(dict.fromkeys(k for r in rows for k in r))
    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    write_markdown(rows)
    ok = sum(1 for r in rows if not r["error"])
    flagged = sum(1 for r in rows if r.get("flags_first_draft"))
    print(f"\nDone: {ok}/{len(rows)} succeeded; {flagged} first drafts were flagged by the claim checker.")
    print("Saved results.csv and results.md. Fill in the score_ columns (1-5) in results.csv.")


def write_markdown(rows):
    lines = [
        "# Evaluation results",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} with `{rows[0]['model'] if rows else ''}`.",
        "",
        "| Exp | Value | Words (target) | Keywords | First-draft flags | Final flags | Seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["error"]:
            lines.append(f"| {r['experiment'][:1]} | {r['value']} | failed: {r['error']} | | | | |")
            continue
        lines.append(
            f"| {r['experiment'][:1]} | {r['value']} | {r['word_count']} ({r['target_words']}) | {r['keywords_used']} "
            f"| {r['flags_first_draft'] or 'none'} | {r['flags_final'] or 'none'} | {r['seconds']} |"
        )
    lines += ["", "## Outputs", ""]
    for r in rows:
        if not r["error"]:
            lines += [f"### {r['experiment']} — {r['value']}", "", r["description"], ""]
    with open("results.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
