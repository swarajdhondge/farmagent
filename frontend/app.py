# app.py  — Flask UI ↔ ADK bridge (Cloud Run–ready)
import os, json, base64, mimetypes, pathlib, uuid, sys
from typing import List, Optional
from pathlib import Path
import requests
from flask import Flask, render_template, request, send_from_directory, jsonify
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException


# Local dev only; Cloud Run uses env vars set at deploy
load_dotenv()

sys.path.append(str(Path(__file__).resolve().parents[1]))

# ---- ADK wiring -------------------------------------------------------------
ADK_URL    = os.getenv("ADK_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
APP_NAME   = os.getenv("ADK_APP", "src").split(".", 1)[0]  # accepts "src.agent" -> "src"
USER_ID    = os.getenv("ADK_USER_ID", "user")
SESSION_ID = os.getenv("ADK_SESSION_ID", "s_cloud")

# ---- Paths ------------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).parent.resolve()
TEMPLATES_DIR = BASE_DIR  / "templates"
STATIC_DIR    = BASE_DIR  / "static"

# Cloud Run: only /tmp is writable
UPLOAD_DIR    = pathlib.Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---- Flask ------------------------------------------------------------------
app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))
@app.errorhandler(Exception)
def _json_errors(e):
    code = e.code if isinstance(e, HTTPException) else 500
    return jsonify(ok=False, error=str(e)), code

app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB

# ---- HTTP session (no proxy inheritance in prod) ----------------------------
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})
SESSION.trust_env = False
SESSION.proxies = {"http": None, "https": None}
SESSION.headers.update({"Content-Type": "application/json"})

# ---- Bootstrap (Flask 3-safe) ----------------------------------------------
_BOOTED = False

@app.before_request
def _boot_once():
    """Ensure the ADK session exists once per process."""
    global _BOOTED
    if _BOOTED:
        return
    try:
        url = f"{ADK_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions/{SESSION_ID}"
        SESSION.post(url, json={"state": {"receipts": [], "governor_log": []}}, timeout=8)
    except Exception as e:
        print(f"[WARN] ensure_session failed: {e}")
    _BOOTED = True

# ---- SSE helpers ------------------------------------------------------------
def _parse_sse(s: str):
    out, cur = [], {}
    for line in s.splitlines():
        if not line.strip():
            if cur: out.append(cur); cur = {}
            continue
        if line.startswith("event:"):
            cur["event"] = line[6:].strip()
        elif line.startswith("data:"):
            cur["data"] = (cur.get("data", "") + line[5:].strip())
    if cur: out.append(cur)

    evs = []
    for e in out:
        d = e.get("data")
        if not d: continue
        try:
            evs.append(json.loads(d))
        except json.JSONDecodeError:
            pass
    return evs

def _normalize_events(events):
    messages, tool_calls, errors, state_updates = [], [], [], []
    tokens_in = tokens_out = gen_time_ms = 0

    for e in events:
        # existing
        sd = (e.get("actions") or {}).get("stateDelta") or {}

        # new: if agent uses e["state"]["current_state"]
        if not sd and "state" in e:
            sd = e["state"].get("current_state", {})

        # new: if receipts/governor_log under debugInfo
        if not sd and "debugInfo" in e:
            sd = {
                "governor_log": e["debugInfo"].get("governor_log", []),
                "receipts": e["debugInfo"].get("receipts", [])
            }

        if sd:
            state_updates.append(sd)
    
    for e in events:
        um = e.get("usageMetadata") or {}
        tokens_in  += int(um.get("inputTokenCount", 0)  or um.get("promptTokenCount", 0) or 0)
        tokens_out += int(um.get("outputTokenCount", 0) or um.get("candidatesTokenCount", 0) or 0)
        gen_time_ms = max(gen_time_ms, int(um.get("totalLatencyMs", 0) or 0))

        # errors
        if ("errorMessage" in e) or ("errorCode" in e):
            errors.append({"code": e.get("errorCode"), "message": e.get("errorMessage") or e.get("errorCode")})

        # content/messages
        content = e.get("content"); author = e.get("author")
        if isinstance(content, dict):
            for p in content.get("parts", []):
                if isinstance(p, dict) and "text" in p:
                    messages.append({"who": "assistant", "author": author, "text": p["text"]})
                fc = p.get("functionCall")
                fr = p.get("functionResponse")
                if fc:
                    tool_calls.append({"id": fc.get("id"), "name": fc.get("name"), "args": fc.get("args", {}), "response": None})
                if fr:
                    tool_calls.append({"id": fr.get("id"), "name": fr.get("name"), "args": None, "response": fr.get("response")})

        # ---- ADK v1.17 and v1.18 compatibility ----
        sd = (e.get("actions") or {}).get("stateDelta") or {}
        if not sd:
            sd = (e.get("state") or {}).get("current_state") or {}
        if not sd and e.get("debugInfo"):
            sd = {"governor_log": e["debugInfo"].get("governor_log", [])}

        if sd:
            state_updates.append(sd)

    receipts_count = 0
    for sd in state_updates:
        if isinstance(sd.get("receipts"), list):
            receipts_count = max(receipts_count, len(sd["receipts"]))

    return {
        "messages": messages,
        "tool_calls": len(tool_calls),
        "errors": errors,
        "state_updates": state_updates,
        "metrics": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "tool_calls": len(tool_calls),
            "receipts": receipts_count,
            "gen_time_ms": gen_time_ms,
        },
    }

    messages, tool_calls, errors, state_updates = [], [], [], []
    tokens_in = tokens_out = gen_time_ms = 0
    for e in events:
        um = e.get("usageMetadata") or {}
        tokens_in  += int(um.get("inputTokenCount", 0)  or um.get("promptTokenCount", 0) or 0)
        tokens_out += int(um.get("outputTokenCount", 0) or um.get("candidatesTokenCount", 0) or 0)
        gen_time_ms = max(gen_time_ms, int(um.get("totalLatencyMs", 0) or 0))

        if ("errorMessage" in e) or ("errorCode" in e):
            errors.append({"code": e.get("errorCode"), "message": e.get("errorMessage") or e.get("errorCode")})

        content = e.get("content"); author = e.get("author")
        if isinstance(content, dict):
            for p in content.get("parts", []):
                if isinstance(p, dict) and "text" in p:
                    messages.append({"who": "assistant", "author": author, "text": p["text"]})
                fc = p.get("functionCall")
                if fc:
                    tool_calls.append({"id": fc.get("id"),
                                       "name": fc.get("name") or fc.get("n"),
                                       "args": fc.get("args", {}),
                                       "response": None,
                                       "author": author})
                fr = p.get("functionResponse")
                if fr:
                    tool_calls.append({"id": fr.get("id"),
                                       "name": fr.get("name") or fr.get("n"),
                                       "args": None,
                                       "response": fr.get("response"),
                                       "author": author})
        sd = (e.get("actions") or {}).get("stateDelta") or {}
        if sd: state_updates.append(sd)

    receipts_count = 0
    for sd in state_updates:
        if isinstance(sd.get("receipts"), list):
            receipts_count = max(receipts_count, len(sd["receipts"]))

    return {
        "messages": messages,
        "tool_calls": len(tool_calls),
        "errors": errors,
        "state_updates": state_updates,
        "metrics": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "tool_calls": len(tool_calls),
            "receipts": receipts_count,
            "gen_time_ms": gen_time_ms,
        },
    }

def _rows_from_state_receipts(state_receipts):
    rows = []
    for r in state_receipts or []:
        out = (r or {}).get("output") or {}
        rows.append({
            "tool": r.get("tool", "tool"),
            "summary": f"{r.get('status','ok')}: {out.get('summary') or out.get('status') or out.get('result') or ''}".strip(),
            "uri": out.get("uri") or out.get("url"),
        })
    return rows

def _flatten_run_plan_receipts(tool_calls):
    rows = []
    # tool_calls here is a count in metrics, but we collect receipts via state updates or synthesizer
    return rows

def _build_synth_receipts(norm):
    rows = []
    for c in norm.get("tool_calls_full", []) if isinstance(norm.get("tool_calls_full"), list) else []:
        resp = c.get("response")
        if not isinstance(resp, dict): continue
        uri = resp.get("uri") or resp.get("url")
        summary = (resp.get("summary") or resp.get("result") or resp.get("status") or "")
        rows.append({"tool": c.get("name") or "tool", "summary": str(summary)[:280], "uri": uri})
    return rows

def _aggregate(norm):
    plan_str, gov_log = "", []
    state_receipts = []

    for sd in norm.get("state_updates", []):
        if isinstance(sd.get("current_plan"), str) and sd["current_plan"].strip():
            plan_str = sd["current_plan"].strip()
        if isinstance(sd.get("governor_log"), list):
            gov_log.extend(sd["governor_log"])
        if isinstance(sd.get("receipts"), list):
            state_receipts = sd["receipts"]

    rows = _rows_from_state_receipts(state_receipts) if state_receipts else []
    if not rows:
        rows = _build_synth_receipts(norm)

    final_out = None
    for m in norm.get("messages", []):
        if m.get("author") == "SynthesizerAgent" and m.get("text"):
            final_out = m["text"]; break

    err = (norm.get("errors", [])[:1] or [{}])[0].get("message", "")
    if (final_out or rows or plan_str) and err:
        err = ""

    return {
        "plan": plan_str or "",
        "final_output": final_out or "...",
        "governor_log": gov_log or [],
        "receipts": rows or [],
        "metrics": norm.get("metrics", {}),
        "error": err,
    }

# ---- Build message with optional inline image -------------------------------
def _inline_bytes_from_uri(image_uri: str):
    """Support file:// and /tmp/uploads/ paths for inlineData."""
    p: Optional[pathlib.Path] = None
    if image_uri.startswith("file://"):
        p = pathlib.Path(image_uri.replace("file://", ""))
    elif image_uri.startswith("/"):
        p = pathlib.Path(image_uri)
    if p and p.exists():
        return {
            "inlineData": {
                "mimeType": mimetypes.guess_type(str(p))[0] or "image/jpeg",
                "data": base64.b64encode(p.read_bytes()).decode("ascii"),
            }
        }
    return None

def _new_message_with_optional_image(user_text: str, image_uri: Optional[str]):
    parts = [{"text": user_text or ""}]
    if image_uri:
        inline = _inline_bytes_from_uri(image_uri)
        if inline:
            parts.append(inline)
        else:
            parts.append({"text": f"(Attached: {image_uri})"})
    return {"role": "user", "parts": parts}

# ---- Wire to ADK ------------------------------------------------------------
def _post_events(payload: dict, *, prefer_sse: bool):
    """
    Prefer ADK's namespaced endpoints (local ADK) and fall back to flat /run (some deployments).
    Always raise on non-2xx so we never pass HTML back to the UI.
    """
    run_timeout = 180 if prefer_sse else 120

    base = f"{ADK_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions/{SESSION_ID}"

    # 1) Try namespaced JSON /run first
    try:
        r = SESSION.post(f"{base}:run", json=payload, timeout=run_timeout)
        if r.ok:
            ct = r.headers.get("content-type", "")
            if ct.startswith("application/json"):
                return _normalize_events(r.json())
            return _normalize_events(json.loads(r.text or "[]"))
        # if it's not 404/405, it's a real failure
        if r.status_code not in (404, 405):
            r.raise_for_status()
    except Exception:
        pass

    # 2) Try namespaced SSE stream
    try:
        rs = SESSION.post(f"{base}:run_sse", json=payload, stream=True, timeout=None)
        if rs.ok:
            text = "\n".join(line for line in rs.iter_lines(decode_unicode=True) if line)
            return _normalize_events(_parse_sse(text))
        if rs.status_code not in (404, 405):
            rs.raise_for_status()
    except Exception:
        pass

    # 3) Fall back to flat /run (what your Cloud Run ADK served)
    try:
        r2 = SESSION.post(f"{ADK_URL}/run", json=payload, timeout=240)
        if r2.ok:
            ct = r2.headers.get("content-type", "")
            if ct.startswith("application/json"):
                return _normalize_events(r2.json())
            return _normalize_events(json.loads(r2.text or "[]"))
        r2.raise_for_status()
    except Exception as e:
        # last resort flat SSE
        try:
            rs2 = SESSION.post(f"{ADK_URL}/run_sse", json=payload, stream=True, timeout=None)
            if rs2.ok:
                text = "\n".join(line for line in rs2.iter_lines(decode_unicode=True) if line)
                return _normalize_events(_parse_sse(text))
            rs2.raise_for_status()
        except Exception:
            # propagate the original error
            raise e

    """Primary: /run (JSON). Fallback: /run_sse (stream) → /run (retry)."""
    run_timeout = 180 if prefer_sse else 120

    try:
        r = SESSION.post(f"{ADK_URL}/run", json=payload, timeout=run_timeout)
        if r.ok:
            if r.headers.get("content-type", "").startswith("application/json"):
                return _normalize_events(r.json())
            return _normalize_events(json.loads(r.text or "[]"))
        if r.status_code not in (404, 405):
            r.raise_for_status()
    except Exception:
        pass

    try:
        rs = SESSION.post(f"{ADK_URL}/run_sse", json=payload, stream=True, timeout=None)
        if rs.ok:
            text = "\n".join(line for line in rs.iter_lines(decode_unicode=True) if line)
            return _normalize_events(_parse_sse(text))
    except Exception:
        pass

    r2 = SESSION.post(f"{ADK_URL}/run", json=payload, timeout=240)
    if r2.ok:
        if r2.headers.get("content-type", "").startswith("application/json"):
            return _normalize_events(r2.json())
        return _normalize_events(json.loads(r2.text or "[]"))
    r2.raise_for_status()

def _run_once(query: str, image_uri: Optional[str]):
    payload = {
        "app_name": APP_NAME,
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "new_message": _new_message_with_optional_image(query, image_uri),
        "streaming": False,
    }
    return _post_events(payload, prefer_sse=bool(image_uri))

def _rows_from_plan_receipts(tool_calls):
    return []

def _aggregate_for_ui(norm):
    return _aggregate(norm)

# ---- Routes -----------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    # If you don’t ship templates, you can return a simple JSON here.
    if not TEMPLATES_DIR.exists():
        return jsonify(ok=True, message="FarmAgent backend is running"), 200
    return render_template(
        "index.html",
        final_output="...",
        plan=[],
        receipts=[],
        governor_log=[],
        metrics={},
        last_query="",
        attached_image="",
    )

@app.route("/static/<path:path>")
def send_static(path: str):
    return send_from_directory(app.static_folder, path)

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("image")
    if not f:
        return jsonify(ok=False, error="No image field 'image'"), 400

    name = secure_filename(f.filename or "image")
    stem, ext = (name.rsplit(".", 1) + [""])[:2]
    ext = f".{ext}" if ext else ""
    fname = f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
    fpath = UPLOAD_DIR / fname
    try:
        f.save(str(fpath))
    except Exception as e:
        return jsonify(ok=False, error=f"Save failed: {e}"), 500

    # Return a file:// URI so it can be inlined on next call
    return jsonify(ok=True, uri="file://" + str(fpath))

@app.route("/run_plan", methods=["POST"])
def run_plan():
    query = (request.form.get("query") or "").strip()
    image_uri = None
    try:
        image_uris = json.loads(request.form.get("image_uris") or "[]")
        image_uri = image_uris[0] if image_uris else None
    except Exception:
        image_uri = (request.form.get("image_uri") or "").strip() or None

    try:
        norm = _aggregate_for_ui(_post_events({
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "session_id": SESSION_ID,
            "new_message": _new_message_with_optional_image(query, image_uri),
            "streaming": False,
        }, prefer_sse=bool(image_uri)))
        if not isinstance(norm, dict):
            raise ValueError("Aggregator returned non-dict result")

        return jsonify(
            ok=True,
            final_output=norm.get("final_output", "..."),
            plan=norm.get("plan", ""),
            receipts=norm.get("receipts", []),
            governor_log=norm.get("governor_log", []),
            metrics=norm.get("metrics", {}),
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify(ok=True)

@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__":
    # Cloud Run injects PORT; default to 8080 for local parity
    port = int(os.environ.get("PORT", 8080))
    print(f"UI http://0.0.0.0:{port}  ADK={ADK_URL} app={APP_NAME}")
    app.run(host="0.0.0.0", port=port, debug=False)
