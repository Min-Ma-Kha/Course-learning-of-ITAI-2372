"""
app.py - The Flask web server for NextDollar Compass.

Course: ITAI 2372 - Module 04 (AI in Finance)
Project: NextDollar Compass
Author: Min Ma Kha

HOW A FLASK APP WORKS (quick tour)
----------------------------------
* Flask is a small Python "web framework". Running `python app.py` starts a
  web server on your own computer at http://127.0.0.1:5000.
* A ROUTE connects a web address to a Python function. When the browser asks
  for "/", the index() function sends back templates/index.html - the page.
* The page's JavaScript (static/js/app.js) then talks to the /api/... routes
  below. Each one receives JSON (or an uploaded file), runs Python, and sends
  JSON back. This is a tiny "REST API".

    Browser (index.html + app.js)  --fetch-->  Flask route  -->  Python modules
         ^                                                          |
         +----------------------- JSON <---------------------------+

PRIVACY
-------
Nothing is saved on the server. Uploaded files are read in memory and
discarded; the plan lives only in the browser tab.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:  # optional: load GEMINI_API_KEY from a local .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import categorizer
import document_reader
import finance_engine
import offline_text
from categories import taxonomy_for_ui
from gemini_client import GeminiClient
from investments import SCREENS

BASE = Path(__file__).parent
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB upload limit

gemini = GeminiClient()

ALLOWED_DOC_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/heic"}
DOC_KINDS = {"paystub", "credit_card", "mortgage", "car_loan", "loan"}


def _evaluation() -> dict:
    path = BASE / "models" / "evaluation.json"
    return json.loads(path.read_text()) if path.exists() else {}


@app.route("/")
def index():
    return render_template("index.html", ai_enabled=gemini.available, model=gemini.model,
                           screens=SCREENS, evaluation=_evaluation())


@app.get("/api/status")
def status():
    return jsonify({"ai": gemini.available, "model": gemini.model, "last_error": gemini.last_error})


@app.get("/api/categories")
def categories():
    return jsonify(taxonomy_for_ui())


@app.get("/api/sample")
def sample():
    """A fictional demo household so anyone can try the app in one click."""
    return jsonify(json.loads((BASE / "data" / "sample_profile.json").read_text()))


@app.post("/api/extract")
def extract():
    """Read a pay stub / statement. Gemini first, text patterns as a fallback."""
    upload = request.files.get("file")
    doc_type = request.form.get("doc_type", "")
    if not upload or doc_type not in DOC_KINDS:
        return jsonify({"error": "Send a file and a doc_type."}), 400
    mime = upload.mimetype or ""
    if upload.filename.lower().endswith(".pdf"):
        mime = "application/pdf"
    if mime not in ALLOWED_DOC_TYPES:
        return jsonify({"error": "Please upload a PDF or a photo (PNG, JPG, WEBP)."}), 400
    data = upload.read()

    fields = gemini.extract_document(data, mime, doc_type) if gemini.available else None
    if fields:
        return jsonify({"fields": fields, "source": "gemini",
                        "message": "Read by Gemini. Please check every number before using it."})
    result = document_reader.read_offline(data, mime, doc_type)
    if gemini.available and gemini.last_error:
        result["message"] = f"{gemini.last_error} Used offline reading instead. " + result.get("message", "")
    return jsonify(result)


@app.post("/api/categorize")
def categorize():
    """Label expenses. Accepts JSON {items:[...]} or an uploaded bank CSV."""
    extra = {}
    if "file" in request.files:
        try:
            parsed = categorizer.parse_bank_csv(request.files["file"].read())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        items = parsed["items"]
        extra = {k: v for k, v in parsed.items() if k != "items"}
    else:
        items = (request.get_json(silent=True) or {}).get("items", [])
    items = [i for i in items if str(i.get("description", "")).strip()][:1000]
    results = categorizer.categorize(items, gemini=gemini if gemini.available else None)
    counts = {m: sum(1 for r in results if r["method"] == m) for m in ("ml", "gemini", "check")}
    return jsonify({"items": results, "counts": counts, **extra})


@app.post("/api/plan")
def plan():
    """Calculate the plan (Python), then explain it (Gemini or templates)."""
    profile = request.get_json(silent=True) or {}
    result = finance_engine.build_plan(profile)
    summary = offline_text.plan_summary(result)
    story = gemini.explain_plan(summary) if (gemini.available and profile.get("explain", True)) else None
    result["narrative"] = story or offline_text.narrative(result)
    result["narrative_source"] = "gemini" if story else "template"
    if gemini.available and not story and gemini.last_error:
        result["ai_notice"] = gemini.last_error
    return jsonify(result)


@app.post("/api/ask")
def ask():
    body = request.get_json(silent=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify({"error": "Type a question."}), 400
    plan_result = finance_engine.build_plan(body.get("profile", {}))
    reply = None
    if gemini.available:
        reply = gemini.answer(question, offline_text.plan_summary(plan_result), body.get("history", []))
    if not reply:
        reply = offline_text.answer(question, plan_result)
        if gemini.available and gemini.last_error:
            reply = f"({gemini.last_error}) " + reply
    return jsonify({"answer": reply, "source": "gemini" if gemini.available and not gemini.last_error else "offline"})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "That file is over 15 MB."}), 413


if __name__ == "__main__":
    print(f"Gemini: {'ON (' + gemini.model + ')' if gemini.available else 'OFF - running in offline mode'}")
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", "5000")))
