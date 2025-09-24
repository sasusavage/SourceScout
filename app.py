import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import requests
try:
    from perplexity import Perplexity as PplxClient  # optional SDK
except Exception:
    PplxClient = None

# Load environment variables from backend/.env if present
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
# Allow CORS from local files (origin 'null') and localhost
CORS(
    app,
    resources={r"/api/*": {"origins": ["null", r"http://127.0.0.1:*", r"http://localhost:*", "*"]}},
)

PPLX_API_KEY = os.getenv("PPLX_API_KEY")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = os.getenv("PPLX_MODEL", "sonar-pro")

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

@app.post("/api/ask")
def ask():
    if not PPLX_API_KEY:
        return jsonify({"error": "Server missing PPLX_API_KEY"}), 500

    data = request.get_json(silent=True) or {}
    query = data.get("query")
    history = data.get("history", [])  # [{role, content}]
    model = data.get("model") or DEFAULT_MODEL
    web_search_options = data.get("web_search_options")  # optional dict

    if not query or not isinstance(query, str):
        return jsonify({"error": "Query is required as a string"}), 400

    # Minimal messages payload: start with only the current user message
    # (You can re-enable multi-turn later once the basics are working.)
    messages = [{"role": "user", "content": query}]

    # Prefer SDK if available; otherwise fallback to HTTP
    out = None
    if PplxClient is not None:
        try:
            client = PplxClient(api_key=PPLX_API_KEY)
            kwargs = {"messages": messages, "model": model}
            if isinstance(web_search_options, dict) and web_search_options:
                kwargs["web_search_options"] = web_search_options
            completion = client.chat.completions.create(**kwargs)
            # Convert to dict (SDK objects often have model_dump or dict-like)
            out = getattr(completion, "model_dump", lambda: None)() or getattr(completion, "__dict__", {}) or {}
            if not out:
                # Fallback: build minimal dict from known fields
                choice0 = getattr(completion, "choices", [None])[0]
                content = None
                if choice0 and hasattr(choice0, "message"):
                    content = getattr(choice0.message, "content", None)
                out = {"choices": [{"message": {"content": content}}]}
        except Exception as e:
            app.logger.warning("Perplexity SDK failed, falling back to HTTP: %s", str(e))

    if out is None:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "top_p": 0.9,
            "return_citations": True,
            "stream": False,
        }
        if isinstance(web_search_options, dict) and web_search_options:
            payload["web_search_options"] = web_search_options

        try:
            resp = requests.post(
                PERPLEXITY_API_URL,
                headers={
                    "Authorization": f"Bearer {PPLX_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                data=json.dumps(payload),
                timeout=60,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            # Try to include API error if present
            try:
                err_json = resp.json()
            except Exception:
                err_json = {"message": str(e), "text": getattr(resp, "text", "")}
            # Log server-side for debugging
            app.logger.error("Perplexity API HTTPError %s: %s", getattr(resp, 'status_code', '?'), err_json)
            return jsonify({"error": "Perplexity API error", "details": err_json}), resp.status_code if 'resp' in locals() else 502
        except requests.RequestException as e:
            app.logger.error("Perplexity API RequestException: %s", str(e))
            return jsonify({"error": "Network error", "details": str(e)}), 502

        out = resp.json()

    # Expected shape similar to OpenAI chat.completions
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

    return jsonify({
        "answer": answer_text or "",
        "citations": citations,
        "raw": out,
    })

@app.post("/api/search")
def api_search():
    if not PPLX_API_KEY:
        return jsonify({"error": "Server missing PPLX_API_KEY"}), 500
    body = request.get_json(silent=True) or {}
    queries = body.get("query") or body.get("queries") or []
    if isinstance(queries, str):
        queries = [queries]
    if not isinstance(queries, list) or not queries:
        return jsonify({"error": "Provide 'query' as string or list of strings"}), 400
    if PplxClient is None:
        return jsonify({"error": "Perplexity SDK not installed on server"}), 501
    try:
        client = PplxClient(api_key=PPLX_API_KEY)
        search = client.search.create(query=queries)
        # Normalize results
        results = []
        for r in getattr(search, 'results', []) or []:
            results.append({
                "title": getattr(r, 'title', None),
                "url": getattr(r, 'url', None),
                "snippet": getattr(r, 'snippet', None),
                "domain": getattr(r, 'domain', None),
            })
        return jsonify({"results": results})
    except Exception as e:
        app.logger.error("/api/search error: %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.post("/api/chat")
def api_chat():
    if not PPLX_API_KEY:
        return jsonify({"error": "Server missing PPLX_API_KEY"}), 500
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")
    model = body.get("model") or DEFAULT_MODEL
    web_search_options = body.get("web_search_options")

    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Provide 'messages' array like [{role, content}]"}), 400

    # SDK preferred
    if PplxClient is not None:
        try:
            client = PplxClient(api_key=PPLX_API_KEY)
            kwargs = {"messages": messages, "model": model}
            if isinstance(web_search_options, dict) and web_search_options:
                kwargs["web_search_options"] = web_search_options
            completion = client.chat.completions.create(**kwargs)
            choice0 = (getattr(completion, 'choices', []) or [None])[0]
            content = None
            if choice0 and hasattr(choice0, 'message'):
                content = getattr(choice0.message, 'content', None)
            return jsonify({"answer": content or ""})
        except Exception as e:
            app.logger.warning("/api/chat SDK failed, falling back: %s", str(e))

    # Fallback to HTTP
    try:
        resp = requests.post(
            PERPLEXITY_API_URL,
            headers={
                "Authorization": f"Bearer {PPLX_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=json.dumps({
                "model": model,
                "messages": messages,
                "return_citations": True,
                "stream": False,
                **({"web_search_options": web_search_options} if isinstance(web_search_options, dict) and web_search_options else {}),
            }),
            timeout=60,
        )
        resp.raise_for_status()
        out = resp.json()
        choice0 = (out.get('choices', []) or [None])[0] or {}
        answer = (choice0.get('message') or {}).get('content') or ""
        return jsonify({"answer": answer, "raw": out})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    app.run( debug=False)
