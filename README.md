# Research Assistant (Perplexity API)

A minimal full-stack web app that lets you ask questions and get sourced answers using Perplexity's API.

## Features
- HTML/CSS/JS frontend with history sidebar
- Python Flask backend that calls Perplexity Chat Completions API
- CORS enabled for local development
- Shows answer and sources (citations)

## Prerequisites
- Python 3.10+
- A Perplexity API key

## Setup (Windows PowerShell)

1) Copy backend/.env.example to backend/.env and paste your API key

```
Copy-Item .\backend\.env.example .\backend\.env
notepad .\backend\.env
# set PPLX_API_KEY=your_key_here, save & close
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
- Default model can be overridden with environment variable PPLX_MODEL
- Backend listens on 127.0.0.1:5000

## Notes
- Do NOT expose your API key to the frontend. The key is only used on the backend.
- If you see CORS errors, ensure the backend is running and that you're using http://127.0.0.1 or a local file.

## Health Check
Visit http://127.0.0.1:5000/health to verify the server is up.
