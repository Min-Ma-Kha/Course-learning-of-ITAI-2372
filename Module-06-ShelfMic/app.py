"""Flask web app: GenAI product description generator (ITAI 2372, Module 06, AI in Retail).

Run:  python app.py   then open http://127.0.0.1:5000/
"""

import logging

from dotenv import load_dotenv
from flask import Flask, render_template, request

load_dotenv()  # read an optional .env before llm.py looks for the API key

from generator import AUTO_TONE, CHANNELS, TONES, create_description, parse_keywords  # noqa: E402
from llm import LLMError, provider_label  # noqa: E402

APP_NAME = "ShelfMic"  # change the app's display name here

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # reject oversized requests before they reach the model

AUDIENCE_SUGGESTIONS = [
    "General shoppers",
    "Hikers and outdoor enthusiasts",
    "Beginner hikers",
    "Retail professionals",
    "Budget-conscious students",
    "Gift shoppers",
    "Young adults",
]

DEFAULT_FORM = {
    "product_name": "",
    "keywords": "",
    "audience": "General shoppers",
    "tone": AUTO_TONE,
    "channel": "product_page",
}

MAX_NAME = 120
MAX_KEYWORDS_TEXT = 600
MAX_KEYWORDS = 15
MAX_KEYWORD_LEN = 60
MAX_AUDIENCE = 120


def validate(form):
    """Server-side validation. Returns (errors, keywords)."""
    errors = []
    keywords = parse_keywords(form["keywords"])

    if not form["product_name"]:
        errors.append("Enter a product name.")
    elif len(form["product_name"]) > MAX_NAME:
        errors.append(f"Keep the product name under {MAX_NAME} characters.")

    if len(form["keywords"]) > MAX_KEYWORDS_TEXT:
        errors.append(f"Keep keywords under {MAX_KEYWORDS_TEXT} characters in total.")
    elif not keywords:
        errors.append("Enter at least one keyword or product fact, separated by commas.")
    elif len(keywords) > MAX_KEYWORDS:
        errors.append(f"Use at most {MAX_KEYWORDS} keywords (you entered {len(keywords)}).")
    elif any(len(k) > MAX_KEYWORD_LEN for k in keywords):
        errors.append(f"Keep each keyword under {MAX_KEYWORD_LEN} characters. Separate facts with commas.")

    if not form["audience"]:
        errors.append("Enter a target audience.")
    elif len(form["audience"]) > MAX_AUDIENCE:
        errors.append(f"Keep the audience under {MAX_AUDIENCE} characters.")

    if form["tone"] != AUTO_TONE and form["tone"] not in TONES:
        errors.append("Choose one of the listed tones.")
    if form["channel"] not in CHANNELS:
        errors.append("Choose one of the listed sales channels.")
    return errors, keywords


def render_page(form, result=None, errors=None, status=200):
    return render_template(
        "index.html",
        app_name=APP_NAME,
        form=form,
        result=result,
        errors=errors or [],
        tones=TONES,
        auto_tone=AUTO_TONE,
        channels=CHANNELS,
        audiences=AUDIENCE_SUGGESTIONS,
        model=provider_label(),
    ), status


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_page(dict(DEFAULT_FORM))

    form = {
        "product_name": " ".join(request.form.get("product_name", "").split()),
        "keywords": request.form.get("keywords", "").strip(),
        "audience": " ".join(request.form.get("audience", "").split()),
        "tone": request.form.get("tone", AUTO_TONE).strip(),
        "channel": request.form.get("channel", "product_page").strip(),
    }
    errors, keywords = validate(form)
    if errors:
        return render_page(form, errors=errors, status=400)

    try:
        result = create_description(form["product_name"], keywords, form["audience"], form["tone"], form["channel"])
    except LLMError as exc:
        logger.warning("Generation failed: %s", exc)
        return render_page(form, errors=[str(exc)], status=502)
    except Exception:  # never show a stack trace to the user
        logger.exception("Unexpected error during generation")
        return render_page(form, errors=["Something went wrong while generating. Please try again."], status=500)

    return render_page(form, result=result)


@app.errorhandler(413)
def too_large(_error):
    return render_page(dict(DEFAULT_FORM), errors=["That request was too large. Shorten the product details."], status=413)


if __name__ == "__main__":
    app.run(debug=False)
