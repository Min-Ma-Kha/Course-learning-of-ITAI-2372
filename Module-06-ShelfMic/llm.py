"""Model integration layer.

The Flask app never talks to a model directly. It calls generate_text(), and
the LLM_PROVIDER environment variable decides which backend answers. Every
backend receives exactly the same prompt, so outputs can be compared fairly.

Providers
  gemini  Google Gemini API (hosted). Key from GEMINI_API_KEY or GOOGLE_API_KEY.
  ollama  A local model served by Ollama (optional extension).

Only `requests` is used (no vendor SDKs), which keeps installs simple on
Windows ARM laptops.
"""

import logging
import os
import re
import time

import requests

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"  # Google's moving alias for its current Flash model
DEFAULT_OLLAMA_MODEL = "gemma4:e2b"
REQUEST_TIMEOUT = 60  # seconds


class LLMError(Exception):
    """A failure whose message is safe to show to the user (never contains the key)."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def provider():
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def model_name():
    if provider() == "ollama":
        return os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def provider_label():
    return f"{provider()} / {model_name()}"


def generate_text(system, user, temperature=0.7, max_output_tokens=4096):
    """Send one prompt to the configured provider and return plain text."""
    name = provider()
    if name == "gemini":
        return _gemini(system, user, temperature, max_output_tokens)
    if name == "ollama":
        return _ollama(system, user, temperature, max_output_tokens)
    raise LLMError(f'Unknown LLM_PROVIDER "{name}". Use "gemini" or "ollama".')


def _clean(text):
    """Remove reasoning tags, Markdown bold and stray labels the model adds."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = text.replace("**", "").strip()
    text = re.sub(r"^(?:product\s+)?description\s*:\s*", "", text, flags=re.I)
    return text.strip()


# --------------------------------------------------------------------------
# Gemini (hosted)
# --------------------------------------------------------------------------

def _gemini(system, user, temperature, max_output_tokens):
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise LLMError(
            "No Gemini API key found. Set GEMINI_API_KEY (or GOOGLE_API_KEY) "
            "in your environment or in a .env file."
        )
    model = model_name()
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # A generous token budget: newer Gemini models "think" first, and
        # thinking tokens count toward this limit. A small cap returns nothing.
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
    }
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    url = GEMINI_URL.format(model=model)

    resp = None
    for attempt in (1, 2):  # one bounded retry for network blips and 5xx errors
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            raise LLMError("The Gemini request timed out. Please try again.", retryable=True)
        except requests.ConnectionError:
            if attempt == 1:
                time.sleep(2)
                continue
            raise LLMError("Couldn't reach the Gemini API. Check your internet connection.", retryable=True)
        if resp.status_code >= 500 and attempt == 1:
            time.sleep(2)
            continue
        break

    if resp.status_code != 200:
        raise _gemini_http_error(resp, model)

    try:
        data = resp.json()
    except ValueError:
        raise LLMError("Gemini sent a response that couldn't be read. Please try again.", retryable=True)

    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason")
        if reason:
            raise LLMError(f"Gemini blocked this request ({reason}). Try rewording the product details.")
        raise LLMError("Gemini returned no answer. Please try again.", retryable=True)

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = _clean("".join(p.get("text", "") for p in parts if not p.get("thought")))
    if not text:
        finish = candidate.get("finishReason", "")
        if finish == "MAX_TOKENS":
            raise LLMError("The model used up its output budget before finishing. Please try again.", retryable=True)
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"):
            raise LLMError(f"Gemini stopped the answer ({finish}). Try rewording the product details.")
        raise LLMError("Gemini returned an empty description. Please try again.", retryable=True)
    return text


def _gemini_http_error(resp, model):
    try:
        detail = (resp.json().get("error") or {}).get("message", "")
    except ValueError:
        detail = ""
    code = resp.status_code
    logger.warning("Gemini returned HTTP %s: %s", code, detail[:300])
    if code == 400 and "api key" in detail.lower():
        return LLMError("Gemini rejected the API key. Check that GEMINI_API_KEY is correct.")
    if code in (401, 403):
        return LLMError("Gemini refused access with this API key. Check the key and that the Gemini API is enabled for it.")
    if code == 404:
        return LLMError(
            f'The model "{model}" isn\'t available for your key. '
            "Set GEMINI_MODEL to another model, for example gemini-2.5-flash."
        )
    if code == 429:
        return LLMError("Gemini's rate limit or free-tier quota was reached. Wait a minute and try again.", retryable=True)
    if code >= 500:
        return LLMError("Gemini is temporarily unavailable. Please try again shortly.", retryable=True)
    return LLMError(f"Gemini rejected the request (HTTP {code}). {detail[:160]}")


# --------------------------------------------------------------------------
# Ollama (local, optional)
# --------------------------------------------------------------------------

def _ollama(system, user, temperature, max_output_tokens):
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = model_name()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": False,  # keep a thinking model's reasoning out of the copy
        "options": {"temperature": temperature, "num_predict": min(max_output_tokens, 1024)},
    }
    try:
        resp = requests.post(f"{host}/api/chat", json=payload, timeout=180)
        if resp.status_code == 400 and "think" in resp.text.lower():
            payload.pop("think")  # model has no thinking mode; ask again without the flag
            resp = requests.post(f"{host}/api/chat", json=payload, timeout=180)
    except requests.Timeout:
        raise LLMError("The local model took over 3 minutes. Try a smaller model.", retryable=True)
    except requests.ConnectionError:
        raise LLMError(f"Couldn't reach Ollama at {host}. Start the Ollama app (or run `ollama serve`) and try again.")
    if resp.status_code == 404:
        return_msg = f'Ollama doesn\'t have the model "{model}". Run: ollama pull {model}'
        raise LLMError(return_msg)
    if resp.status_code != 200:
        raise LLMError(f"Ollama returned an error (HTTP {resp.status_code}).")
    text = _clean((resp.json().get("message") or {}).get("content", ""))
    if not text:
        raise LLMError("The local model returned an empty description.", retryable=True)
    return text
