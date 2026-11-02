"""Offline tests: no API key or internet needed. The model is replaced by a fake.

Run from the project folder:  python -m unittest discover tests
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LLM_PROVIDER"] = "gemini"

import app as app_module  # noqa: E402
import generator  # noqa: E402
import llm  # noqa: E402
from claims import check_description  # noqa: E402

FACTS = ["full-grain leather upper", "rubber outsole", "padded collar", "lace-up closure", "water-resistant finish"]
CLEAN = (
    "Built for day hikes, the TrailRunner Leather Boots pair a full-grain leather upper with a "
    "rubber outsole that grips the trail. A padded collar keeps your ankles comfortable, the "
    "lace-up closure lets you dial in the fit, and a water-resistant finish shrugs off morning dew."
)
OVERCLAIM = "The best waterproof boots ever, with a 2-year warranty. Limited time only!"


def form(**overrides):
    data = {
        "product_name": "TrailRunner Leather Boots",
        "keywords": ", ".join(FACTS),
        "audience": "Beginner hikers",
        "tone": "auto",
        "channel": "product_page",
    }
    data.update(overrides)
    return data


class ClaimCheckerTests(unittest.TestCase):
    def test_upgraded_claim_number_and_hype_are_flagged(self):
        report = check_description(OVERCLAIM, "TrailRunner Leather Boots", FACTS, 90, 150)
        terms = {f["term"] for f in report["flags"]}
        self.assertIn("waterproof", terms)   # facts only say water-resistant
        self.assertIn("warranty", terms)
        self.assertIn("2", terms)            # invented number
        self.assertIn("best", terms)
        self.assertIn("limited time", terms)

    def test_supported_wording_is_not_flagged(self):
        report = check_description(CLEAN, "TrailRunner Leather Boots", FACTS, 30, 80)
        self.assertEqual(report["flags"], [])
        self.assertEqual(report["keywords_missing"], [])
        self.assertEqual(report["length_status"], "ok")

    def test_keyword_parsing_trims_and_dedupes(self):
        self.assertEqual(generator.parse_keywords(" a ,b,, A , c d "), ["a", "b", "c d"])


class DecisionRuleTests(unittest.TestCase):
    def test_segment_and_auto_tone(self):
        plan = generator.decide("Retail professionals", "auto", "marketplace")
        self.assertEqual(plan["segment"], "Professional / business buyer")
        self.assertEqual(plan["tone"], "professionals")
        self.assertEqual((plan["min_words"], plan["max_words"]), (60, 120))

    def test_beginner_wins_over_outdoor(self):
        self.assertEqual(generator.decide("Beginner hikers", "casual", "social")["segment"], "Beginner")

    def test_gift_buyer_is_not_professional(self):
        self.assertEqual(generator.decide("Gift buyers", "auto", "product_page")["segment"], "Gift shopper")


class FlaskRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_get_shows_form(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'name="product_name"', resp.data)

    def test_invalid_input_never_calls_model(self):
        with mock.patch.object(generator, "generate_text") as fake:
            resp = self.client.post("/", data=form(product_name="", keywords=" , ,"))
        fake.assert_not_called()
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"Enter a product name", resp.data)
        self.assertIn(b"at least one keyword", resp.data)

    def test_bad_tone_rejected(self):
        resp = self.client.post("/", data=form(tone="sarcastic"))
        self.assertEqual(resp.status_code, 400)

    def test_clean_generation(self):
        with mock.patch.object(generator, "generate_text", return_value=CLEAN) as fake:
            resp = self.client.post("/", data=form())
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No unsupported claims found", resp.data)
        self.assertIn(b"Decision trace", resp.data)

    def test_flagged_draft_triggers_one_rewrite(self):
        with mock.patch.object(generator, "generate_text", side_effect=[OVERCLAIM, CLEAN]) as fake:
            resp = self.client.post("/", data=form())
        self.assertEqual(fake.call_count, 2)
        self.assertIn(b"asked the model for one rewrite", resp.data)
        self.assertIn(b"No unsupported claims found", resp.data)

    def test_model_output_is_escaped(self):
        with mock.patch.object(generator, "generate_text", return_value="<script>alert(1)</script> rubber outsole"):
            resp = self.client.post("/", data=form())
        self.assertNotIn(b"<script>alert(1)</script>", resp.data)

    def test_llm_error_shows_friendly_message(self):
        err = llm.LLMError("Gemini's rate limit or free-tier quota was reached. Wait a minute and try again.")
        with mock.patch.object(generator, "generate_text", side_effect=err):
            resp = self.client.post("/", data=form())
        self.assertEqual(resp.status_code, 502)
        self.assertIn(b"rate limit", resp.data)


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class GeminiParsingTests(unittest.TestCase):
    def setUp(self):
        os.environ["GEMINI_API_KEY"] = "test-key-not-real"

    def test_thought_parts_are_ignored(self):
        payload = {"candidates": [{"content": {"parts": [
            {"text": "planning...", "thought": True},
            {"text": "Product description: **Sturdy** boots."},
        ]}, "finishReason": "STOP"}]}
        with mock.patch.object(llm.requests, "post", return_value=FakeResponse(200, payload)) as post:
            text = llm.generate_text("sys", "user")
        self.assertEqual(text, "Sturdy boots.")
        sent = post.call_args.kwargs
        self.assertEqual(sent["headers"]["x-goog-api-key"], "test-key-not-real")  # key in header, not URL
        self.assertNotIn("test-key-not-real", post.call_args.args[0])

    def test_rate_limit_message_hides_key(self):
        payload = {"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        with mock.patch.object(llm.requests, "post", return_value=FakeResponse(429, payload)):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.generate_text("sys", "user")
        self.assertIn("rate limit", str(ctx.exception))
        self.assertNotIn("test-key-not-real", str(ctx.exception))

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.generate_text("sys", "user")
        self.assertIn("No Gemini API key", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
