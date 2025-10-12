# Research Assistant (OpenAI API)

A minimal full-stack web app that lets you ask questions and get sourced answers using OpenAI's Chat Completions API.

## Features
- HTML/CSS/JS frontend with history sidebar
- Python Flask backend that calls OpenAI's Chat Completions API
- Built-in personality switcher (default Sasu Jnr Pidgin vibes, optional Fluent English mode)
- CORS enabled for local development
- Shows answer and sources (citations)

## Prerequisites
- Python 3.10+
- An OpenAI API key

## Setup (Windows PowerShell)

1) Copy backend/.env.example to backend/.env and paste your API key

```
Copy-Item .\backend\.env.example .\backend\.env
notepad .\backend\.env
# set OPENAI_API_KEY=your_key_here, save & close
# optionally set OPENROUTER_API_KEY (and related OPENROUTER_* vars) if you prefer routing through OpenRouter
```

2) Create and activate a virtual environment, then install dependencies
```
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
pip install -r .\backend\requirements.txt
```

3) Run the backend (Flask)
```
$env:FLASK_APP = "backend/app.py"; python .\backend\app.py
```
The server will start at http://127.0.0.1:5000

4) Open the frontend
- Open the file .\frontend\index.html in your browser (double-click), or
- Serve it with a simple HTTP server and go to http://127.0.0.1:5500 (optional)

## Configuration
- Default model can be overridden with environment variable OPENAI_MODEL (defaults to `gpt-4o-mini`)
- OPENROUTER_API_KEY enables routing requests through OpenRouter as a fallback when an OpenAI key isn't provided. Optional companion variables: OPENROUTER_API_URL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME.
- Server host/port can be changed with APP_HOST and APP_PORT (defaults to 127.0.0.1:5000). APP_DEBUG toggles Flask debug mode.
- Frontend model picker now targets OpenAI models (`gpt-4o-mini`, `gpt-4o`, `o4-mini`, `gpt-4.1-mini`). Adjust the list in `frontend/index.html` if you prefer different options.
- Need the house style? Check `backend/sasu_jnr_prompt.md` for the full Sasu Jnr system prompt, ready to drop into Codex or any assistant runtime.
- Customize persona injection with `SYSTEM_PROMPT_PATH` (defaults to `backend/sasu_jnr_prompt.md`) and `INJECT_SYSTEM_PROMPT` (`true`/`false`). The backend falls back to an embedded Sasu Jnr summary if the file can't be read.
- Additional personality prompts:
	- `PERSONALITY_PIDGIN_PATH` (defaults to `SYSTEM_PROMPT_PATH`) feeds the Pidgin/Naija vibe.
	- `PERSONALITY_FLUENT_PATH` (defaults to `backend/fluent_persona_prompt.md`) feeds the fluent-English persona.
	- `DEFAULT_PERSONALITY` (`pidgin` or `fluent`) selects the startup mode; frontend still defaults to Pidgin.
- Backend listens on 127.0.0.1:5000

## Notes
- Do NOT expose your API key to the frontend. The key is only used on the backend.
- OpenAI responses do not include first-party web citations. The app surfaces any links present in the response body as "citations." 
- If you see CORS errors, ensure the backend is running and that you're using http://127.0.0.1 or a local file.

## Health Check
Visit http://127.0.0.1:5000/health to verify the server is up.
