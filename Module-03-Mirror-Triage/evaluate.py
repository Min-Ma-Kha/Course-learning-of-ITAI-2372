"""
evaluate.py - Score Mirror Triage on a set of made-up test cases.

Course: ITAI 2372 - Module 03 (AI in Healthcare)
Project: Mirror Triage

PLAIN-LANGUAGE SUMMARY
----------------------
How do we know if the app is any good? We give it test cases where we already
know the right answer (test_cases.csv) and count how often it agrees.

The test set has 12 situations, each written in BOTH English and Spanish
("mirror pairs"). Besides accuracy, we measure:
  * UNDER-TRIAGE - the app said "less urgent" than it should. This is the most
    dangerous mistake, and the one a 2026 study found in a consumer AI tool.
  * OVER-TRIAGE  - the app said "more urgent" than needed (safer, but costly).
  * CROSS-LANGUAGE AGREEMENT - did the English and Spanish versions of the
    SAME case get the SAME result? If not, Spanish speakers are being treated
    differently - a fairness (bias) problem.
  * AI-ONLY vs FINAL - accuracy of Gemini alone compared with Gemini plus the
    safety rules, to show what the safety layer adds.

All cases are invented. No real patient data is used.

HOW TO RUN
----------
  python evaluate.py --rules-only      # offline: only the keyword safety rules (no API key needed)
  python evaluate.py                   # full test: rules + Gemini (needs GEMINI_API_KEY)
  python evaluate.py --limit 4         # quick check on the first 4 cases

Results are saved to results/eval_results.csv and results/summary.md.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import red_flags
import triage_pipeline as tp
from gemini_client import http_status_of
from levels import TriageLevel


def load_cases(path: Path) -> list:
    """Read the test cases from the CSV file into a list of dictionaries."""
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def call_with_retry(func, retries: int = 3):
    """Run `func()`; if the free tier says "too many requests" (HTTP 429),
    wait and try again (30s, then 60s, then 90s)."""
    for attempt in range(retries + 1):
        try:
            return func()
        except Exception as error:
            if http_status_of(error) == 429 and attempt < retries:
                wait = 30 * (attempt + 1)
                print(f"    rate limited - waiting {wait}s before retrying...")
                time.sleep(wait)
                continue
            raise


def evaluate_rules_only(cases: list) -> list:
    """Offline check: which cases do the keyword rules catch on their own?"""
    rows = []
    for case in cases:
        hits = red_flags.check_red_flags(case["symptoms"], case["age_group"])
        rule_level = red_flags.highest_level(hits)
        rows.append({
            "case_id": case["case_id"],
            "expected": case["expected_level"],
            "rules_level": rule_level.name if rule_level else "(no rule matched)",
            "rules_matched": "; ".join(h.rule.rule_id for h in hits),
        })
    return rows


def evaluate_full(cases: list, client, delay: float) -> list:
    """Full check: run every case through the same pipeline the app uses."""
    rows = []
    for i, case in enumerate(cases, start=1):
        print(f"[{i}/{len(cases)}] {case['case_id']} ...", flush=True)
        intake = tp.PatientIntake(
            symptoms=case["symptoms"],
            age_group=case["age_group"],
            duration=case["duration"],
            language=case["language"],
        )
        try:
            result = call_with_retry(lambda: tp.triage_once(intake, client))
            used_ai = result.assessment is not None
            row = {
                "case_id": case["case_id"],
                "pair_id": case["pair_id"],
                "language": case["language"],
                "expected": case["expected_level"],
                "final": result.level.name,
                "ai_only": result.ai_level.name if result.ai_level else "",
                "decided_by": result.source,
                "confidence": result.assessment.confidence if used_ai else "",
                "safety_adjustments": "; ".join(n.code for n in result.safety_notes),
                "rules_matched": "; ".join(h.rule.rule_id for h in result.red_flag_hits),
                "error": "",
            }
        except Exception as error:
            row = {"case_id": case["case_id"], "pair_id": case["pair_id"], "language": case["language"],
                   "expected": case["expected_level"], "final": "ERROR", "ai_only": "", "decided_by": "",
                   "confidence": "", "safety_adjustments": "", "rules_matched": "",
                   "error": f"{type(error).__name__}: {error}"[:200]}
        rows.append(row)
        if result_used_ai(row) and i < len(cases):
            time.sleep(delay)  # be gentle with the free-tier rate limit
    return rows


def result_used_ai(row: dict) -> bool:
    return row.get("decided_by") == tp.SOURCE_AI


def summarize(rows: list) -> str:
    """Compute the metrics and return them as a Markdown table."""
    scored = [r for r in rows if r["final"] != "ERROR"]
    n = len(scored)
    if n == 0:
        return "No cases were scored (all errors)."

    def lvl(name):
        return TriageLevel[name]

    correct = sum(lvl(r["final"]) == lvl(r["expected"]) for r in scored)
    under = sum(lvl(r["final"]) < lvl(r["expected"]) for r in scored)
    over = sum(lvl(r["final"]) > lvl(r["expected"]) for r in scored)

    emergencies = [r for r in scored if r["expected"] == "EMERGENCY"]
    emergency_caught = sum(r["final"] == "EMERGENCY" for r in emergencies)

    # Cross-language agreement: both halves of a pair got the same final level.
    by_pair = {}
    for r in scored:
        by_pair.setdefault(r["pair_id"], {})[r["language"]] = r["final"]
    complete_pairs = [p for p in by_pair.values() if len(p) == 2]
    agree = sum(len(set(p.values())) == 1 for p in complete_pairs)

    # AI-only accuracy, for cases where the AI was actually used.
    ai_rows = [r for r in scored if r["ai_only"]]
    ai_correct = sum(lvl(r["ai_only"]) == lvl(r["expected"]) for r in ai_rows)
    ai_under = sum(lvl(r["ai_only"]) < lvl(r["expected"]) for r in ai_rows)
    final_correct_ai_rows = sum(lvl(r["final"]) == lvl(r["expected"]) for r in ai_rows)
    final_under_ai_rows = sum(lvl(r["final"]) < lvl(r["expected"]) for r in ai_rows)

    def pct(a, b):
        return f"{a}/{b} ({(100 * a / b):.0f}%)" if b else "n/a"

    errors = len(rows) - n
    lines = [
        "| Metric | Result |",
        "|---|---|",
        f"| Cases scored | {n}" + (f" ({errors} errored)" if errors else "") + " |",
        f"| Exact triage level correct | {pct(correct, n)} |",
        f"| **Under-triage** (less urgent than expected) | {pct(under, n)} |",
        f"| Over-triage (more urgent than expected) | {pct(over, n)} |",
        f"| Emergencies correctly sent to EMERGENCY | {pct(emergency_caught, len(emergencies))} |",
        f"| English/Spanish pairs with the same result | {pct(agree, len(complete_pairs))} |",
    ]
    if ai_rows:
        lines += [
            f"| Cases that reached the AI | {len(ai_rows)} |",
            f"| ...correct: Gemini alone -> after safety rules | {pct(ai_correct, len(ai_rows))} -> "
            f"{pct(final_correct_ai_rows, len(ai_rows))} |",
            f"| ...under-triage: Gemini alone -> after safety rules | {pct(ai_under, len(ai_rows))} -> "
            f"{pct(final_under_ai_rows, len(ai_rows))} |",
        ]
    return "\n".join(lines)


def write_csv(rows: list, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Evaluate Mirror Triage on test_cases.csv")
    parser.add_argument("--cases", default="test_cases.csv", help="path to the test-case CSV")
    parser.add_argument("--rules-only", action="store_true", help="only test the keyword rules (offline)")
    parser.add_argument("--model", default=None, help="Gemini model name (default: see gemini_client.py)")
    parser.add_argument("--delay", type=float, default=6.0, help="seconds to wait between AI cases")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N cases")
    parser.add_argument("--out", default="results", help="folder for the result files")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))[: args.limit]
    out_dir = Path(args.out)

    if args.rules_only:
        rows = evaluate_rules_only(cases)
        write_csv(rows, out_dir / "rules_only_results.csv")
        caught = sum(r["rules_level"] == "EMERGENCY" for r in rows if r["expected"] == "EMERGENCY")
        total = sum(r["expected"] == "EMERGENCY" for r in rows)
        false_alarms = sum(r["rules_level"] == "EMERGENCY" for r in rows if r["expected"] != "EMERGENCY")
        for r in rows:
            print(f"{r['case_id']:<7} expected={r['expected']:<13} rules={r['rules_level']:<18} {r['rules_matched']}")
        print(f"\nRules alone caught {caught}/{total} emergencies, with {false_alarms} false alarms.")
        print("(The AI steps are designed to catch the emergencies the keyword lists miss.)")
        return

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set. Set it, or run with --rules-only for the offline check.")

    from gemini_client import GeminiTriageClient

    client = GeminiTriageClient(api_key=api_key, model=args.model)
    print(f"Evaluating {len(cases)} cases with model {client.model} ...\n")
    rows = evaluate_full(cases, client, args.delay)
    write_csv(rows, out_dir / "eval_results.csv")

    summary = summarize(rows)
    (out_dir / "summary.md").write_text(
        f"# Mirror Triage evaluation\n\nModel: `{client.model}`\n\n{summary}\n", encoding="utf-8"
    )
    print("\n" + summary)
    print(f"\nSaved {out_dir / 'eval_results.csv'} and {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
