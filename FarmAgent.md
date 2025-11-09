# FarmAgent — Hackathon Build

## Overview

Agentic crop helper built on Google ADK with a transparent reasoning dashboard and a minimal chat UI.
Core loop = Planner → Tools → Governor → Orchestrator → Synthesizer with per-turn state.

---

## P0 (DONE)

Planner → plan JSON
LLM returns a strict plan; saved in state as current_plan (stringified JSON).
Fallback step: request_image when parse fails.

Tools → receipts
Every tool returns a value and a normalized Receipt {tool, summary, uri, cost_ms};
UI shows formatted + raw.

Governor (hard checks, no LLM)
Before-model callback writes entries to governor_log.
Blocks unsafe inputs (e.g., pesticide keywords) and missing required fields when a tool needs them;
replies with exact missing fields.

Orchestrator
Executes current_plan in order; degrades if a step fails; collects receipts; adjusts confidence.

Synthesizer
Produces the final explanation/recommendation grounded in receipts and plan.

UI
Single page showing: query, Plan, Evidence Receipts, Final Recommendation, Governor Log, and mini metrics (tool calls, receipts, latency).
Image attach supported. Unknown/transient errors suppressed if any output exists.

---

## P1 (NEXT)

Two tabs:

1. Chat (plain Q&A, Markdown)
2. Dashboard (Plan/Receipts/Log)

Message-level metrics + loader + cancel; toasts for failures/timeouts.

Tool hardening: client-side file guard (type/size), tool timeouts → receipt.summary="timeout", plan degrades gracefully.

Edge-case sweep (manual): text→image→text+image; missing location → ask/then unblock; non-English preserved; SSE fallback to non-stream call.

Light polish: clickable receipt uri, consistent formatting, no heavy frameworks.

---

## Repo layout (key files)

app.py                # Flask UI + calls ADK /run or /run_sse
templates/index.html  # Dashboard/Chat (current: single-page dashboard)
planner.py            # LLM planner -> PlanSchema JSON -> state.current_plan
governor.py           # before-model checks -> state.governor_log
orchestrator.py       # executes plan, collects receipts, handles degradation
synthesizer.py        # final recommendation based on receipts + plan
prompts.py            # prompt strings
agent_gateway.py      # tool adapters / receipt normalization
uploads/              # dev-only local image storage (file:// URIs)

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

## How to use (demo sweep)

Text only: ask “My tomato leaves are yellow and blotchy.”
Planner should request an image; Governor logs keep_model.

Attach image and re-run.
Plan advances; receipts include any tool outputs; final recommendation becomes specific.

Missing location when a weather/soil tool is used → Governor asks for it.
Provide “location: Seattle”, re-run, tool unblocks.

Large/unsupported image → UI message; server not hit.

Tool timeout → receipt shows timeout, plan degrades, synthesis hedges (still gives helpful next steps).

Non-English prompt → tools run; final output remains in the user language.

SSE down → UI falls back to non-stream call transparently.

---

## Known notes

Unknown error banners are suppressed when any model text or receipts exist.

In dev, images are stored under uploads/ and referenced as file://….
In Cloud Run, swap to gs://… in the tool layer.

409 on session create simply means the session already exists.

---

## Pitch (why this wins)

Deterministic, inspectable agent: plan/receipts/log make the agent auditable.
Safety by construction: Governor enforces concrete preconditions (no fragile prompt guards).
Degradation paths: timeouts/missing inputs don’t crash UX; users get actionable next steps.
Lightweight stack: ADK + Flask + vanilla JS → easy to deploy, easy to reason about.
