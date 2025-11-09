
# FarmAgent — Hackathon Build Guide

## Current Status

**Note:** The "Governor Log" and "Evidence Receipts" features on the dashboard are temporarily disabled as they are undergoing improvements.

## Overview

FarmAgent is an agentic crop helper built on the **Google Agent Development Kit (ADK)**. It features a transparent reasoning dashboard and a minimal chat UI to provide users with AI-driven agricultural advice.

The agent's core logic follows a **Planner → Tools → Governor → Orchestrator → Synthesizer** loop, with the agent's state managed on a per-turn basis. This allows for complex, multi-step reasoning to solve user queries.

## Architecture Deep Dive

The project is built around the Google ADK, which facilitates the creation of complex agentic workflows.

- **`agent_gateway.py`**: This module acts as a safe connector between the Flask frontend and the ADK server. It is designed to be Cloud Run-safe by avoiding proxy inheritance and managing session state explicitly.
- **`src/agent/orchestrator.py`**: This is the heart of the agent. It defines a `SequentialAgent` named `FarmAgent_Orchestrator` that composes the sub-agents responsible for planning, execution, and synthesis.
  - **`PlanningLoopAgent`**: A `LoopAgent` that iteratively calls the `planner_agent` to build a robust plan.
  - **`executor_agent`**: Executes the steps outlined in the plan, using the tools available to the agent.
  - **`synthesizer_agent`**: Takes the results from the executor and synthesizes a final, human-readable answer.
- **Frontend (`app.py` & `frontend/`)**: A Flask application serves the HTML, CSS, and JavaScript for the reasoning dashboard. It makes calls to the `agent_gateway` to interact with the agent and displays the state of the agent's reasoning process in real-time.

## How to Run Locally

### Prerequisites

- Python 3.10+
- A Google Cloud project with Vertex AI enabled.
- Authenticated `gcloud` CLI for Application Default Credentials (ADC). Run `gcloud auth application-default login`.

### 1. Setup and Installation

```bash
# Navigate to the farmagent directory
cd farmagent

# Create and activate a virtual environment
# (Windows)
python -m venv .venv
.venv\Scripts\activate

# (macOS/Linux)
# python3 -m venv .venv
# source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Create `.env` file

Create a file named `.env` in the `farmagent` directory with the following content, replacing `your-gcp-project-id` with your actual Google Cloud project ID.

```env
# ADK Server Configuration
ADK_SERVER_URL=http://127.0.0.1:8000
ADK_APP=src
ADK_USER_ID=user
ADK_SESSION_ID=s_local

# Flask UI Configuration
FLASK_PORT=5000
FLASK_DEBUG=True

# Google Cloud Configuration for ADK
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=True
```

### 3. Start the Servers (2 Terminals)

**Terminal 1: Start ADK API Server**

```bash
# In the farmagent directory
adk api_server . --port=8000
```

*Note: If you encounter a doc error, you may need to set an environment variable: `$env:ADK_DISABLE_DOCS = "true"` (PowerShell) or `export ADK_DISABLE_DOCS=true` (bash). You can safely ignore "app name mismatch" warnings.*

**Terminal 2: Start UI Server**

```bash
# In the farmagent directory
python app.py
```

### 4. Access the UI

Open your browser and go to **http://127.0.0.1:5000**.

## How to Deploy to Google Cloud

This application is designed to be deployed to a serverless environment like Google Cloud Run. The deployment will consist of two separate Cloud Run services: one for the ADK backend and one for the Flask frontend.

### Prerequisites

- A GCP project with Cloud Run, Artifact Registry, and Cloud Build APIs enabled.
- `gcloud` CLI installed and configured (`gcloud init`).
- Docker installed locally or Docker configured within Cloud Shell.

### Step 1: Create a `Procfile`

The `gunicorn` web server is already in `requirements.txt`. Create a `Procfile` in the `farmagent` directory to tell Cloud Run how to start the web server for the frontend.

```
web: gunicorn --bind :$PORT --workers 1 --threads 8 app:app
```

### Step 2: Deploy the ADK Backend Service

The ADK server can be deployed as a Cloud Run service.

```bash
# In the farmagent directory
gcloud run deploy farmagent-adk-backend \
    --source . \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=your-gcp-project-id,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=True" \
    --command="adk" \
    --args="api_server,.,--port,8080"
```

Take note of the URL produced for the ADK backend service.

### Step 3: Deploy the Flask Frontend Service

Now, deploy the frontend, making sure to point it to the ADK backend service you just deployed.

```bash
# Replace ADK_BACKEND_URL with the URL from the previous step
export ADK_BACKEND_URL="your-adk-backend-service-url"

gcloud run deploy farmagent-frontend \
    --source . \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars="ADK_SERVER_URL=$ADK_BACKEND_URL,ADK_APP=src,ADK_USER_ID=cloud_user,ADK_SESSION_ID=s_cloud"
```

### Step 4: Access Your Deployed App

Use the URL generated by the `farmagent-frontend` deployment to access your live application.

```

```
