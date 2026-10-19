"""
tests/test_app.py - Automatic checks for NextDollar Compass.

Course: ITAI 2372 - Module 04 (AI in Finance)

Run from the project folder:   python -m unittest -v
Uses only Python's built-in unittest, so nothing extra to install.
The Gemini tests use a FAKE Gemini, so no API key or internet is needed.
"""

import json
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import categorizer  # noqa: E402
import document_reader  # noqa: E402
import finance_engine as fe  # noqa: E402
import investments  # noqa: E402
from gemini_client import GeminiClient, PaystubFields  # noqa: E402

SAMPLES = ROOT / "data" / "sample_documents"


def sample_profile():
    p = json.loads((ROOT / "data" / "sample_profile.json").read_text())
    p["expenses"] = categorizer.categorize(p["expenses"])
    return p


class LoanMath(unittest.TestCase):
    def test_payoff_matches_textbook_formula(self):
        # $10,000 at 12% APR paying $200/month: n = -ln(1 - rB/P) / ln(1 + r) = 69.7 -> 70 months
        r = 0.01
        expected = math.ceil(-math.log(1 - r * 10000 / 200) / math.log(1 + r))
        self.assertEqual(fe.payoff_schedule(10000, 12, 200)["months"], expected)

    def test_annuity_payment_round_trip(self):
        pay = fe.annuity_payment(20000, 6, 60)
        self.assertAlmostEqual(pay, 386.66, places=1)
        self.assertEqual(fe.payoff_schedule(20000, 6, pay + 0.01)["months"], 60)

    def test_payment_below_interest_never_pays_off(self):
        self.assertTrue(fe.payoff_schedule(10000, 24, 150)["never"])  # interest is $200/month

    def test_zero_percent_loan(self):
        self.assertEqual(fe.payoff_schedule(1200, 0, 100)["months"], 12)

    def test_extra_payment_saves_time_and_interest(self):
        base = fe.payoff_schedule(16800, 7.4, 410)
        fast = fe.payoff_schedule(16800, 7.4, 410, extra=150)
        self.assertLess(fast["months"], base["months"])
        self.assertLess(fast["interest"], base["interest"])


class Budget(unittest.TestCase):
    def test_paycheck_frequency_to_monthly(self):
        inc = fe.summarize_income({"paychecks": [{"frequency": "biweekly", "net": 2000, "gross": 2600}],
                                   "other": [{"amount": 100, "frequency": "weekly"}]})
        self.assertAlmostEqual(inc["monthly_net"], 2000 * 26 / 12 + 100 * 52 / 12, places=1)

    def test_savings_transfer_is_not_double_counted(self):
        plan = fe.build_plan(sample_profile())
        cf = plan["cash_flow"]
        self.assertAlmostEqual(cf["free_cash"], cf["net_income"] - cf["spending"] - cf["debt_payments"], places=1)
        self.assertAlmostEqual(cf["free_for_goals"], max(0, cf["free_cash"]), places=1)

    def test_bad_input_does_not_crash(self):
        plan = fe.build_plan({"income": {"paychecks": [{"net": "abc"}]}, "expenses": [{"amount": "-5"}],
                              "debts": [{"balance": "lots"}], "goals": [{"type": "nonsense"}]})
        self.assertIn("Add your income first", " ".join(plan["warnings"]))

    def test_overspending_warning(self):
        plan = fe.build_plan({"income": {"paychecks": [{"net": 1000, "frequency": "monthly"}]},
                              "expenses": [{"description": "Rent", "monthly_amount": 1500, "type": "need",
                                            "category": "Housing", "subcategory": "Rent"}]})
        self.assertLess(plan["cash_flow"]["free_cash"], 0)
        self.assertTrue(any("more than you bring home" in w for w in plan["warnings"]))


class Plan(unittest.TestCase):
    def setUp(self):
        self.plan = fe.build_plan(sample_profile())

    def test_goals_finish_and_roll_over(self):
        goals = {g["type"]: g for g in self.plan["goals"]}
        self.assertIsNotNone(goals["pay_off_cards"]["done_month"])
        self.assertIsNotNone(goals["emergency_fund"]["done_month"])
        # first-month split follows the 40/30/20/10 priority weights
        free = self.plan["cash_flow"]["free_for_goals"]
        self.assertAlmostEqual(goals["emergency_fund"]["first_month_amount"], free * 0.4, places=1)

    def test_plan_beats_minimum_payments(self):
        t = self.plan["timeline"]
        self.assertLess(t["non_mortgage_free_month"], t["baseline_non_mortgage_free_month"])
        self.assertGreater(t["interest_saved"], 0)

    def test_avalanche_never_costs_more_interest_than_snowball(self):
        s = self.plan["strategies"]
        self.assertLessEqual(s["avalanche"]["interest"], s["snowball"]["interest"] + 0.01)
        self.assertLess(s["avalanche"]["interest"], s["minimums_only"]["interest"])

    def test_investing_ranked_above_cards_triggers_warning(self):
        p = sample_profile()
        p["goals"] = [{"type": "invest"}, {"type": "pay_off_cards"}]
        plan = fe.build_plan(p)
        self.assertTrue(any("Investing is ranked above your credit cards" in w for w in plan["warnings"]))


class Investing(unittest.TestCase):
    def test_shariah_screen_only_shows_shariah_options(self):
        inv = investments.build_investing({"risk": "moderate", "screen": "shariah", "assets": ["etfs"]}, 100, 10)
        for sleeve in inv["mix"]:
            for opt in sleeve["options"]:
                self.assertIn("shariah", opt["screens"], opt["ticker"])
        tickers = {o["ticker"] for s in inv["mix"] for o in s["options"]}
        self.assertTrue({"SPUS", "HLAL", "SPSK"} <= tickers)
        self.assertNotIn("BND", tickers)

    def test_mix_adds_to_100_and_crypto_is_capped(self):
        for risk in ("conservative", "moderate", "aggressive"):
            inv = investments.build_investing({"risk": risk, "assets": ["etfs", "crypto"]}, 100, 10)
            self.assertEqual(sum(s["pct"] for s in inv["mix"]), 100)
            crypto = sum(s["pct"] for s in inv["mix"] if s["key"] == "crypto")
            self.assertLessEqual(crypto, investments.CRYPTO_CAP[risk])

    def test_short_horizon_avoids_stocks(self):
        inv = investments.build_investing({"risk": "aggressive", "assets": ["etfs"]}, 100, 2)
        self.assertFalse(any(s["key"] in ("us_stocks", "intl_stocks", "crypto") for s in inv["mix"]))


class Categorizer(unittest.TestCase):
    def test_known_merchants(self):
        items = [{"description": d, "amount": 10} for d in
                 ("POS PURCHASE WHATABURGER #1043 KATY TX", "netflix", "electric bill", "car insurance", "rent")]
        subs = [r["subcategory"] for r in categorizer.categorize(items)]
        self.assertEqual(subs, ["Fast Food", "Streaming & Subscriptions", "Electricity", "Car Insurance", "Rent"])

    def test_bank_csv_import(self):
        r = categorizer.parse_bank_csv((SAMPLES / "sample_bank_export.csv").read_bytes())
        self.assertEqual(r["skipped_deposits"], 2)
        self.assertTrue(all(i["amount"] > 0 for i in r["items"]))

    def test_csv_with_positive_debits(self):
        csv_bytes = b"Posted Date,Payee,Debit\n10/01/2026,HEB GROCERY,54.20\n10/20/2026,SHELL OIL,40.00\n"
        r = categorizer.parse_bank_csv(csv_bytes)
        self.assertEqual(len(r["items"]), 2)


class Documents(unittest.TestCase):
    def test_offline_reading_of_sample_pdfs(self):
        stub = document_reader.read_offline((SAMPLES / "sample_paystub.pdf").read_bytes(), "application/pdf", "paystub")
        self.assertEqual(stub["fields"]["net_pay"], 2480.0)
        self.assertEqual(stub["fields"]["pay_frequency"], "biweekly")
        card = document_reader.read_offline((SAMPLES / "sample_credit_card_statement.pdf").read_bytes(),
                                            "application/pdf", "credit_card")
        self.assertEqual(card["fields"]["purchase_apr"], 24.99)
        self.assertEqual(card["fields"]["annual_fee"], 0.0)
        loan = document_reader.read_offline((SAMPLES / "sample_mortgage_statement.pdf").read_bytes(),
                                            "application/pdf", "mortgage")
        self.assertEqual(loan["fields"]["escrow"], 560.0)

    def test_photo_without_ai_explains_why(self):
        r = document_reader.read_offline(b"not really a png", "image/png", "paystub")
        self.assertEqual(r["source"], "none")
        self.assertIn("Gemini", r["message"])


class FakeGemini(unittest.TestCase):
    """Checks our Gemini code without calling Google: the SDK client is replaced by a stub."""

    def make(self, parsed=None, text=""):
        g = GeminiClient(api_key=None)
        calls = []

        def generate_content(model, contents, config):
            calls.append((model, contents, config))
            return SimpleNamespace(parsed=parsed, text=text)

        g._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        return g, calls

    def test_document_extraction_uses_structured_output(self):
        g, calls = self.make(parsed=PaystubFields(pay_frequency="biweekly", gross_pay=3250, net_pay=2480))
        out = g.extract_document(b"%PDF-1.4 fake", "application/pdf", "paystub")
        self.assertEqual(out["net_pay"], 2480)
        config = calls[0][2]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertIn("No investment advice", config.system_instruction)

    def test_categorize_ignores_made_up_labels(self):
        from gemini_client import CategoryLabel, CategoryLabels
        g, _ = self.make(parsed=CategoryLabels(labels=[CategoryLabel(index=0, subcategory="Groceries"),
                                                       CategoryLabel(index=1, subcategory="Yacht Fuel")]))
        self.assertEqual(g.categorize(["mystery store", "boat"], ["Groceries", "Fuel"]), ["Groceries", None])

    def test_api_error_falls_back_cleanly(self):
        g = GeminiClient(api_key=None)

        def boom(**_):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        g._client = SimpleNamespace(models=SimpleNamespace(generate_content=boom))
        self.assertIsNone(g.answer("hi", {}, []))
        self.assertIn("rate limit", g.last_error)


class Routes(unittest.TestCase):
    def setUp(self):
        import app as app_module
        app_module.gemini = GeminiClient(api_key=None)  # force offline mode for repeatable tests
        self.client = app_module.app.test_client()

    def test_page_and_api(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        profile = self.client.get("/api/sample").get_json()
        cats = self.client.post("/api/categorize", json={"items": profile["expenses"]}).get_json()
        profile["expenses"] = cats["items"]
        plan = self.client.post("/api/plan", json=profile).get_json()
        self.assertEqual(plan["narrative_source"], "template")
        reply = self.client.post("/api/ask", json={"question": "When will I be debt free?", "profile": profile})
        self.assertIn("mortgage", reply.get_json()["answer"])

    def test_upload_validation(self):
        r = self.client.post("/api/extract", data={"doc_type": "paystub"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
