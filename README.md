# SourceScout Research Assistant

A lightweight AI assistant that answers questions with citations. Choose between standard chat (OpenAI/OpenRouter) and a Perplexity-powered web search mode while keeping Sasu Jnr's personalities.

## Features
- HTML/CSS/JS frontend with history, theming, and persona picker
- Flask backend proxying requests to OpenAI/OpenRouter or Perplexity
- Web search mode that surfaces live sources (with graceful fallback messaging)
- Telegram-powered feedback form with CSRF protection and duplicate guards
- Personality-aware responses (Pidgin default + Fluent English)
- Knowledge-cutoff guardrails for chat mode (October 2023)

## Prerequisites
- Python 3.10+
- At least one of:
	- OpenAI API key (for chat mode)
	- OpenRouter API key (alternative chat provider)
	- Perplexity API key (exposed as `PPLX_API_KEY`) for web search mode
- Telegram bot token & chat ID (to deliver feedback into Telegram)

## Setup (Windows PowerShell)

1. Create your environment file

	```powershell
	Copy-Item .\.env.example .\.env -Force
	notepad .\.env
	```

	Populate the placeholders:
		```properties
		FLASK_SECRET_KEY=generate-a-long-random-string
		TELEGRAM_BOT_TOKEN=123456:your-bot-token
		TELEGRAM_CHAT_ID=your-target-chat-or-user-id
		OPENAI_API_KEY=your-openai-key          # optional if you use OpenRouter
		OPENROUTER_API_KEY=your-openrouter-key  # optional alternative
		PPLX_API_KEY=your-perplexity-key        # required for web search mode
		```

	For production deployments set `FEEDBACK_COOKIE_SECURE=true` to force HTTPS cookies.

2. Create a virtual environment and install dependencies

	```powershell
	python -m venv .\.venv
	.\.venv\Scripts\Activate.ps1
	pip install -r requirements.txt
	```

3. Run the Flask backend

	```powershell
	$env:FLASK_APP = "app.py"
	python app.py
	```

	The server listens on http://127.0.0.1:5000 by default.

4. Open the frontend
	- Double-click `index.html`, or
	- Serve the folder via any static server (optional) and browse to it.

## Using Web Search Mode
- Toggle the **Mode** selector (🌐 Web Search) in the header to route questions through Perplexity.
- Responses include live citations when available.
- If Perplexity is unreachable or the key is invalid, the assistant replies with: “Due to high demand Web SASU has turned off web search.”

## Feedback Inbox
- The **Share quick feedback** panel sends submissions straight to your Telegram chat ID.
- A CSRF token and duplicate guard protect the endpoint—drops are retried with a fresh token, and resubmissions within three minutes are blocked.
- Set `ENABLE_TELEGRAM_FEEDBACK=false` if you need to temporarily disable the form without redeploying.
- In production, set `FEEDBACK_COOKIE_SECURE=true` so CSRF cookies are only transmitted over HTTPS.

## Configuration Reference
- `OPENAI_MODEL` sets the default OpenAI/OpenRouter model (`gpt-4o-mini` by default).
- `PPLX_MODEL` controls which Perplexity model is queried (`llama-3.1-sonar-small-128k-online` by default).
- `SYSTEM_PROMPT_PATH`, `PERSONALITY_PIDGIN_PATH`, `PERSONALITY_FLUENT_PATH`, and `DEFAULT_PERSONALITY` tune persona behavior.
- `APP_HOST`, `APP_PORT`, and `APP_DEBUG` tweak the Flask server runtime.
- Set `INJECT_SYSTEM_PROMPT=false` to disable automatic persona injection.

## Tips
- API keys stay on the backend—never expose them to the frontend.
- Visit `http://127.0.0.1:5000/health` for a quick health check.
- History, persona, model, and mode preferences persist in local storage.

## License
MIT (see `LICENSE` if provided).
