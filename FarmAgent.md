# FarmAgent — Hackathon Build

## Overview

Agentic crop helper built on Google ADK with a transparent reasoning dashboard and a minimal chat UI.
Core loop = Planner → Tools → Governor → Orchestrator → Synthesizer with per-turn state.

---

## Run locally

### Prereqs

- Python 3.10+
- A Google ADK-compatible model setup (Vertex AI or AI Studio). Ensure your Google creds are available (ADC) or API key per ADK docs.

### Install

python -m venv .venv
. .venv/Scripts/activate   # (Windows)

# or

source .venv/bin/activate  # (macOS/Linux)

pip install --upgrade pip
pip install google-adk flask python-dotenv

---

### .env (project root)

ADK_SERVER_URL=http://127.0.0.1:8000
ADK_APP=src
ADK_USER_ID=user
ADK_SESSION_ID=s_local
FLASK_PORT=5000
FLASK_DEBUG=True
For Vertex AI (ADC) or AI Studio per your setup; keep as you currently use.
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=True
GOOGLE_API_KEY=... (if using AI Studio path)

---

### Start ADK API server (terminal 1)

adk api_server . --port=8000

$env:ADK_DISABLE_DOCS = "true" -  add this if u see a doc error

If you see an “app name mismatch … implies app name 'agents'” warning and the run still works, you can ignore it.

---

### Start UI (terminal 2)

python app.py

open http://127.0.0.1:5000

---
