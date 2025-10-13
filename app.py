import os
import json
import re
import logging
import time
import hashlib
import secrets
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
import requests
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.getenv(
    "FRONTEND_DIR",
    os.path.normpath(os.path.join(BASE_DIR))
)

# Load environment variables from potential .env locations
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, "backend", ".env"))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

logger = logging.getLogger("sourcescout")

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Missing FLASK_SECRET_KEY environment variable for session security")

FEEDBACK_CSRF_SALT = os.getenv("FEEDBACK_CSRF_SALT", "feedback-form")
feedback_serializer = URLSafeTimedSerializer(app.secret_key, salt=FEEDBACK_CSRF_SALT)
# Allow CORS from local files (origin 'null') and localhost
CORS(
    app,
    resources={r"/api/*": {"origins": ["null", r"http://127.0.0.1:*", r"http://localhost:*", "https://sourcescout.onrender.com","*"]}},
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "https://sourcescout.local")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "SourceScout")
CHAT_DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
INCLUDE_RAW = os.getenv("OPENAI_INCLUDE_RAW", "false").lower() in {"1", "true", "yes"}
APP_HOST = os.getenv("APP_HOST", os.getenv("FLASK_RUN_HOST", "127.0.0.1"))
APP_PORT = int(os.getenv("APP_PORT", os.getenv("PORT", os.getenv("FLASK_RUN_PORT", "5000"))))
APP_DEBUG = os.getenv("APP_DEBUG", os.getenv("FLASK_DEBUG", "1")).lower() in {"1", "true", "yes"}
PPLX_API_KEY = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
PPLX_API_URL = os.getenv("PPLX_API_URL", os.getenv("PERPLEXITY_API_URL", "https://api.perplexity.ai/chat/completions"))
PPLX_MODEL = os.getenv("PPLX_MODEL", os.getenv("PERPLEXITY_MODEL", "llama-3.1-sonar-small-128k-online"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FEEDBACK_ENABLED = (
    os.getenv("ENABLE_TELEGRAM_FEEDBACK", "true").lower() in {"1", "true", "yes"}
    and bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
)
FEEDBACK_DUP_TTL = int(os.getenv("FEEDBACK_DUPLICATE_TTL", "180"))
FEEDBACK_COOKIE_SECURE = os.getenv("FEEDBACK_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
recent_feedback_cache: dict[str, float] = {}

if not FEEDBACK_ENABLED:
    logger.info("Telegram feedback disabled (provide TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable)")

WEB_SEARCH_DISABLED_MESSAGE = "Due to high demand Web SASU has turned off web search."

QUICK_QUESTIONS: list[dict[str, str]] = [
    {
        "title": "Summarize a topic",
        "prompt": "Give me a concise summary of the latest developments in Nigerian tech startups.",
    },
    {
        "title": "Compare perspectives",
        "prompt": "Compare the key policies of Nigeria and Ghana on renewable energy adoption.",
    },
    {
        "title": "Explain a concept",
        "prompt": "Explain blockchain as if I'm a secondary school student, with relatable examples.",
    },
    {
        "title": "Plan an action",
        "prompt": "Draft a one-week self-study plan to learn Python for data analysis from scratch.",
    },
]

MONTH_NAME_TO_INDEX = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

POST_CUTOFF_MONTHS_2023 = {11, 12}
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
MONTH_YEAR_PATTERN = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d{2})", re.IGNORECASE)
CUTOFF_PHRASES = [
    "after october 2023",
    "beyond october 2023",
    "since october 2023",
    "post october 2023",
]


def cutoff_message(personality_key: str) -> str:
    if personality_key == "fluent":
        return (
            "I’m still working with verified knowledge. "
            "SASU is already digging into fresh research to refill my databank, so I’ll serve you the update once it lands."
        )
    return (
        "Omo, this gist don pass the one wey I fit confirm reach ooo Killer. "
        "SASU don enter research mode to top up the databank, so hold on small make I drop the fresh update later."
    )


def references_post_cutoff(text: str | None) -> bool:
    if not text:
        return False

    lower = text.lower()
    if any(phrase in lower for phrase in CUTOFF_PHRASES):
        return True

    for month_name, year_str in MONTH_YEAR_PATTERN.findall(text):
        year = int(year_str)
        month = MONTH_NAME_TO_INDEX.get(month_name.lower())
        if year > 2023 or (year == 2023 and month in POST_CUTOFF_MONTHS_2023):
            return True

    for year_str in YEAR_PATTERN.findall(text):
        try:
            year = int(year_str)
        except ValueError:
            continue
        if year >= 2024:
            return True

    return False
PERSONALITY_PIDGIN_PATH = os.getenv(
    "PERSONALITY_PIDGIN_PATH" ,
    os.getenv("SYSTEM_PROMPT_PATH", os.path.join(BASE_DIR, "sasu_jnr_prompt.md")),
)
PERSONALITY_FLUENT_PATH = os.getenv(
    "PERSONALITY_FLUENT_PATH",
    os.path.join(BASE_DIR, "fluent_persona_prompt.md"),
)
DEFAULT_PERSONALITY = os.getenv("DEFAULT_PERSONALITY", "pidgin").lower()

PIDGIN_PROMPT_FALLBACK = (
    "You are Sasu Jnr, an AI created by Sasu out of boredom but now full of vibes. "
    "Speak in a lively blend of Nigerian Pidgin and casual English (roughly 40/60). "
    "Be playful, confident, street-smart, and helpful. Crack light jokes, keep energy high, "
    "and occasionally remind folks that Oga Sasu built you out of boredom. Never break character."
)

FLUENT_PROMPT_FALLBACK = (
    "You are Sasu Jnr, Sasu's AI companion with smooth, articulate English. "
    "Respond in clear, upbeat, professional English while keeping a friendly, witty tone. "
    "You still acknowledge Sasu as your creator, but focus on polished language, thoughtful explanations, "
    "and confident guidance without heavy slang."
)


def load_system_prompt(path: str | None, fallback: str) -> str:
    if not path:
        return fallback

    candidates: list[str] = []
    if not os.path.isabs(path):
        candidates.append(os.path.join(BASE_DIR, path))
        candidates.append(os.path.join(os.path.dirname(BASE_DIR), path))
    candidates.append(path)

    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                contents = handle.read().strip()
                if contents:
                    return contents
        except OSError:
            continue

    logger.info("Unable to read system prompt file %s (candidates: %s)", path, candidates)
    return fallback


PERSONALITY_PROMPTS = {
    "pidgin": load_system_prompt(PERSONALITY_PIDGIN_PATH, PIDGIN_PROMPT_FALLBACK),
    "fluent": load_system_prompt(PERSONALITY_FLUENT_PATH, FLUENT_PROMPT_FALLBACK),
}

if DEFAULT_PERSONALITY not in PERSONALITY_PROMPTS:
    logger.warning("Unknown DEFAULT_PERSONALITY %s, falling back to pidgin", DEFAULT_PERSONALITY)
    DEFAULT_PERSONALITY = "pidgin"


def resolve_personality(name: str | None) -> tuple[str, str]:
    key = (name or DEFAULT_PERSONALITY or "pidgin").strip().lower()
    prompt = PERSONALITY_PROMPTS.get(key)
    if not prompt:
        key = DEFAULT_PERSONALITY if DEFAULT_PERSONALITY in PERSONALITY_PROMPTS else "pidgin"
        prompt = PERSONALITY_PROMPTS.get(key, PIDGIN_PROMPT_FALLBACK)
    return key, prompt


INJECT_SYSTEM_PROMPT = os.getenv("INJECT_SYSTEM_PROMPT", "true").lower() in {"1", "true", "yes"}


def post_chat_completion(payload: dict):
    """Send chat completion request to OpenAI or OpenRouter."""
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        url = OPENAI_API_URL
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    elif OPENROUTER_API_KEY:
        url = OPENROUTER_API_URL
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL
        headers["X-Title"] = OPENROUTER_APP_NAME
    else:
        raise RuntimeError("missing_api_key")

    resp = requests.post(
        url,
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    )
    resp.raise_for_status()
    return resp


def perplexity_search(messages: list[dict[str, str]]):
    if not PPLX_API_KEY:
        raise RuntimeError("missing_perplexity_key")

    headers = {
        "Authorization": f"Bearer {PPLX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PPLX_MODEL,
        "messages": messages,
        "temperature": 0.65,
        "top_p": 0.9,
    }
    resp = requests.post(
        PPLX_API_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_citations(items):
    normalized = []
    if not items:
        return normalized
    for idx, item in enumerate(items, start=1):
        if isinstance(item, str):
            url = item
            domain = urlparse(url).netloc if url else ""
            normalized.append({
                "title": domain or f"Source {idx}",
                "url": url,
                "domain": domain,
                "snippet": "",
            })
            continue

        if not isinstance(item, dict):
            continue

        url = item.get("url") or item.get("source") or item.get("source_url")
        domain = item.get("domain")
        if not domain and url:
            domain = urlparse(url).netloc

        title = item.get("title") or item.get("name") or item.get("id")
        if title and isinstance(title, str) and title.lower().startswith("source #") and domain:
            title = domain
        if not title:
            title = domain or f"Source {idx}"

        snippet = (
            item.get("snippet")
            or item.get("description")
            or item.get("text")
            or ""
        )

        normalized.append({
            "title": title,
            "url": url,
            "domain": domain or "",
            "snippet": snippet,
        })
    return normalized


INLINE_CITATION_RE = re.compile(r"(\s*\[\s*(?:\d+|[a-z]{1,3}\d*|source\s*#?\d+)\s*\])+", re.IGNORECASE)


def strip_inline_citations(text: str | None) -> str:
    if not text:
        return ""
    cleaned = INLINE_CITATION_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", lambda m: "\n", cleaned)
    return cleaned.strip()


def generate_feedback_csrf() -> str:
    return feedback_serializer.dumps({"nonce": secrets.token_hex(8)})


def validate_feedback_csrf(token: str | None, cookie_token: str | None) -> bool:
    if not token or not cookie_token or token != cookie_token:
        return False
    try:
        feedback_serializer.loads(token, max_age=3600)
        return True
    except (BadSignature, SignatureExpired):
        return False


def is_duplicate_feedback(client_ip: str, message: str) -> bool:
    if not message:
        return False

    now = time.time()
    expired = [key for key, ts in recent_feedback_cache.items() if now - ts > FEEDBACK_DUP_TTL]
    for key in expired:
        recent_feedback_cache.pop(key, None)

    fingerprint = hashlib.sha256(f"{client_ip}|{message}".encode("utf-8")).hexdigest()
    if fingerprint in recent_feedback_cache:
        return True

    recent_feedback_cache[fingerprint] = now
    return False


def send_feedback_to_telegram(name: str, email: str, message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("missing_telegram_config")

    payload = {
        "chat_id": TELEGRAM_CHAT_ID.strip(),
        "text": (
            "\U0001F4E9 New Feedback Submission:\n"
            f"\U0001F464 Name: {name or 'Anonymous'}\n"
            f"\U0001F4E7 Email: {email or '(not provided)'}\n"
            f"\U0001F4AC Feedback: {message or '(empty message)'}"
        ),
    }

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(api_url, data=payload, timeout=10)
    resp.raise_for_status()

@app.get("/health")
def health():
    return {"status": "ok"}

# Serve frontend files for convenience during development
@app.get("/")
def index_html():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.get("/index.html")
def index_html_alias():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.get("/styles.css")
def styles_css():
    return send_from_directory(FRONTEND_DIR, "styles.css")

@app.get("/app.js")
def app_js():
    return send_from_directory(FRONTEND_DIR, "app.js")


@app.get("/api/feedback/csrf")
def feedback_csrf():
    if not FEEDBACK_ENABLED:
        resp = make_response(jsonify({"enabled": False}))
        resp.delete_cookie("feedback_csrf")
        return resp, 503

    token = generate_feedback_csrf()
    resp = make_response(jsonify({"token": token, "enabled": True}))
    resp.set_cookie(
        "feedback_csrf",
        token,
        max_age=3600,
        secure=FEEDBACK_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )
    return resp


@app.post("/api/feedback")
def submit_feedback():
    if not FEEDBACK_ENABLED:
        return jsonify({"error": "Feedback submission is currently disabled."}), 503

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    message = (data.get("message") or "").strip()
    csrf_token = data.get("csrf_token")
    cookie_token = request.cookies.get("feedback_csrf")

    if not validate_feedback_csrf(csrf_token, cookie_token):
        return jsonify({"error": "Invalid or missing CSRF token."}), 400

    if len(name) < 2:
        return jsonify({"error": "Please provide your name (at least 2 characters)."}), 400

    if email and ("@" not in email or email.count("@") != 1 or email.startswith("@")):
        return jsonify({"error": "Please provide a valid email address or leave it blank."}), 400

    if len(message) < 10:
        return jsonify({"error": "Feedback message is too short (minimum 10 characters)."}), 400

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if is_duplicate_feedback(client_ip, message):
        return jsonify({"error": "Duplicate feedback detected. Please wait before resubmitting."}), 409

    try:
        send_feedback_to_telegram(name, email, message)
    except requests.HTTPError as exc:
        err_resp = getattr(exc, "response", None)
        app.logger.error("Telegram HTTPError: %s", getattr(err_resp, "text", str(exc)))
        return jsonify({"error": "Failed to deliver feedback to Telegram."}), 502
    except requests.RequestException as exc:
        app.logger.error("Telegram RequestException: %s", exc)
        return jsonify({"error": "Network error while sending feedback."}), 502
    except RuntimeError as exc:
        if str(exc) == "missing_telegram_config":
            return jsonify({"error": "Server missing Telegram configuration."}), 500
        raise

    refreshed_token = generate_feedback_csrf()
    resp = make_response(jsonify({"ok": True, "message": "Feedback delivered", "csrf_token": refreshed_token}))
    resp.set_cookie(
        "feedback_csrf",
        refreshed_token,
        max_age=3600,
        secure=FEEDBACK_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )
    return resp


@app.post("/api/ask")
def ask():
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    history = data.get("history", [])  # [{role, content}]
    model = data.get("model") or CHAT_DEFAULT_MODEL
    requested_personality = data.get("personality")
    personality_key, system_prompt = resolve_personality(requested_personality)
    mode = (data.get("mode") or "chat").strip().lower()
    is_web_mode = mode in {"web", "web-search", "search", "perplexity"}

    if not is_web_mode and not OPENAI_API_KEY and not OPENROUTER_API_KEY:
        return jsonify({"error": "Server missing OPENAI_API_KEY or OPENROUTER_API_KEY"}), 500

    if not query or not isinstance(query, str):
        return jsonify({"error": "Query is required as a string"}), 400

    if not is_web_mode and references_post_cutoff(query):
        message = cutoff_message(personality_key)
        payload = {
            "answer": message,
            "citations": [],
            "personality": personality_key,
            "knowledge_cutoff": "October 2023",
        }
        return jsonify(payload)

    messages = []
    if INJECT_SYSTEM_PROMPT and system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.extend(
        m for m in history if isinstance(m, dict) and {"role", "content"} <= set(m.keys())
    )
    messages.append({"role": "user", "content": query})

    if is_web_mode:
        try:
            out = perplexity_search(messages)
            choice0 = (out.get("choices", []) or [None])[0] or {}
            message = choice0.get("message") or {}
            answer_text = message.get("content") or out.get("answer") or ""
            citations = (
                out.get("citations")
                or choice0.get("citations")
                or message.get("citations")
                or out.get("sources")
                or []
            )
            payload = {
                "answer": strip_inline_citations(answer_text),
                "citations": normalize_citations(citations),
                "personality": personality_key,
                "mode": "web",
            }
            if INCLUDE_RAW:
                payload["raw"] = out
            return jsonify(payload)
        except RuntimeError as exc:
            if str(exc) != "missing_perplexity_key":
                app.logger.error("Perplexity runtime error: %s", exc)
            else:
                app.logger.error("Perplexity key missing when web search requested")
        except requests.HTTPError as exc:
            err_resp = getattr(exc, "response", None)
            try:
                err_json = err_resp.json() if err_resp is not None else {"message": str(exc)}
            except Exception:
                err_json = {"message": str(exc), "text": getattr(err_resp, "text", "")}
            status_code = getattr(err_resp, "status_code", 502)
            app.logger.error("Perplexity HTTPError %s: %s", status_code, err_json)
        except requests.RequestException as exc:
            app.logger.error("Perplexity RequestException: %s", exc)

        payload = {
            "answer": WEB_SEARCH_DISABLED_MESSAGE,
            "citations": [],
            "personality": personality_key,
            "mode": "web",
            "web_search_disabled": True,
        }
        return jsonify(payload)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.65,
        "top_p": 0.9,
    }

    try:
        resp = post_chat_completion(payload)
    except requests.HTTPError as e:
        err_resp = getattr(e, "response", None)
        try:
            err_json = err_resp.json() if err_resp is not None else {"message": str(e)}
        except Exception:
            err_json = {
                "message": str(e),
                "text": getattr(err_resp, "text", ""),
            }
        status_code = getattr(err_resp, "status_code", 502)
        app.logger.error("Chat completion HTTPError %s: %s", status_code, err_json)
        return jsonify({"error": "Chat completion API error", "details": err_json}), status_code
    except requests.RequestException as e:
        app.logger.error("Chat completion RequestException: %s", str(e))
        return jsonify({"error": "Network error", "details": str(e)}), 502
    except RuntimeError as e:
        if str(e) == "missing_api_key":
            return jsonify({"error": "Server missing OpenAI/OpenRouter API key"}), 500
        raise

    out = resp.json()

    # Expected shape similar to OpenAI/OpenRouter chat completions
    answer_text = None
    citations = []
    try:
        first_choice = out.get("choices", [{}])[0]
        message = first_choice.get("message", {})
        answer_text = message.get("content")
        # Perplexity returns citations at top-level or within choice/message depending on model
        citations = (
            out.get("citations")
            or first_choice.get("citations")
            or message.get("citations")
            or out.get("sources")
            or []
        )
    except Exception:
        pass

    if not citations and answer_text:
        link_candidates = re.findall(r"https?://[^\s)]+", answer_text)
        if link_candidates:
            # Preserve order while de-duplicating
            citations = list(dict.fromkeys(link_candidates))

    payload = {
        "answer": strip_inline_citations(answer_text),
        "citations": normalize_citations(citations),
        "personality": personality_key,
    }
    if INCLUDE_RAW:
        payload["raw"] = out

    return jsonify(payload)

@app.post("/api/search")
def api_search():
    return jsonify({
        "error": "Search endpoint unavailable",
        "details": "OpenAI's Chat Completions API does not provide web search results."
    }), 501


@app.get("/api/quick-questions")
def quick_questions():
    return jsonify({"questions": QUICK_QUESTIONS})

@app.post("/api/chat")
def api_chat():
    if not OPENAI_API_KEY and not OPENROUTER_API_KEY:
        return jsonify({"error": "Server missing OPENAI_API_KEY or OPENROUTER_API_KEY"}), 500

    body = request.get_json(silent=True) or {}
    messages = body.get("messages")
    model = body.get("model") or CHAT_DEFAULT_MODEL
    requested_personality = body.get("personality")
    personality_key, system_prompt = resolve_personality(requested_personality)

    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Provide 'messages' array like [{role, content}]"}), 400

    if INJECT_SYSTEM_PROMPT and system_prompt and body.get("inject_system", True):
        first_role = messages[0].get("role") if messages else None
        if first_role != "system":
            messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        resp = post_chat_completion({
            "model": model,
            "messages": messages,
            "temperature": body.get("temperature", 0.7),
            "top_p": body.get("top_p", 1),
        })
        out = resp.json()
        choice0 = (out.get("choices", []) or [None])[0] or {}
        answer = (choice0.get("message") or {}).get("content") or ""
        payload = {
            "answer": strip_inline_citations(answer),
            "personality": personality_key,
        }
        if INCLUDE_RAW:
            payload["raw"] = out
        return jsonify(payload)
    except requests.HTTPError as e:
        err_resp = getattr(e, "response", None)
        try:
            err_json = err_resp.json() if err_resp is not None else {"message": str(e)}
        except Exception:
            err_json = {
                "message": str(e),
                "text": getattr(err_resp, "text", ""),
            }
        status_code = getattr(err_resp, "status_code", 502)
        app.logger.error("Chat completion HTTPError %s: %s", status_code, err_json)
        return jsonify({"error": "Chat completion API error", "details": err_json}), status_code
    except requests.RequestException as e:
        app.logger.error("Chat completion RequestException: %s", str(e))
        return jsonify({"error": "Network error", "details": str(e)}), 502
    except RuntimeError as e:
        if str(e) == "missing_api_key":
            return jsonify({"error": "Server missing OpenAI/OpenRouter API key"}), 500
        raise

if __name__ == "__main__":
    app.run( debug=True)
