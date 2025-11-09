# agent_gateway.py — ADK connector (Cloud Run–safe, no proxy inheritance)
import os, json, base64, mimetypes
from typing import Dict, Any, List, Optional
import requests
from pathlib import Path

ADK_SERVER_URL = os.getenv("ADK_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
APP_NAME   = os.getenv("ADK_APP", "src").split(".", 1)[0]
USER_ID    = os.getenv("ADK_USER_ID", "user")
SESSION_ID = os.getenv("ADK_SESSION_ID", "s_cloud")

SESSION = requests.Session()
SESSION.trust_env = False
SESSION.proxies = {"http": None, "https": None}
SESSION.headers.update({"Content-Type": "application/json"})

DEFAULT_STATE = {
    "core_context": "",
    "current_plan": "",
    "receipts": [],
    "governor_log": [],
    "loop_terminated": False,
    "governor_escalated": False,
    "confidence_score": 1.0,
}

def ensure_session() -> Dict[str, Any]:
    url = f"{ADK_SERVER_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions/{SESSION_ID}"
    r = SESSION.post(url, json={"state": DEFAULT_STATE}, timeout=10)
    r.raise_for_status()
    return r.json()

def _parse_sse(text: str) -> List[dict]:
    events, cur = [], {}
    for line in text.splitlines():
        if not line.strip():
            if cur: events.append(cur); cur = {}
            continue
        if line.startswith("event:"):
            cur["event"] = line[6:].strip()
        elif line.startswith("data:"):
            cur["data"] = (cur.get("data", "") + line[5:].strip())
    if cur: events.append(cur)

    out = []
    for e in events:
        d = e.get("data")
        if not d: continue
        try:
            out.append(json.loads(d))
        except json.JSONDecodeError:
            pass
    return out

def _normalize_events(events: List[dict]) -> dict:
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
        "tool_calls": tool_calls,
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

def _rows_from_state_receipts(state_receipts: Optional[List[dict]]) -> List[dict]:
    rows = []
    for r in state_receipts or []:
        out = (r or {}).get("output") or {}
        rows.append({
            "tool": r.get("tool", "tool"),
            "summary": f"{r.get('status','ok')}: {out.get('summary') or out.get('status') or out.get('result') or ''}".strip(),
            "uri": out.get("uri") or out.get("url"),
        })
    return rows

def _flatten_run_plan_receipts(tool_calls: List[dict]) -> List[dict]:
    rows = []
    for c in tool_calls or []:
        if (c.get("name") or c.get("tool")) != "run_plan_tool":
            continue
        payload = c.get("response") or {}
        m = payload.get("metrics") or {}
        if m:
            rows.append({
                "tool": "run_plan_tool",
                "summary": f"executed:{m.get('executed',0)}, skipped:{m.get('skipped',0)}, errors:{m.get('errors',0)}, total:{m.get('total_steps',0)}",
                "uri": None,
            })
        rows.extend(_rows_from_state_receipts(payload.get("receipts") or []))
    return rows

def _build_synth_receipts(norm: dict) -> List[dict]:
    rows = []
    for c in norm.get("tool_calls", []):
        resp = c.get("response")
        if not isinstance(resp, dict): continue
        uri = resp.get("uri") or resp.get("url")
        summary = (resp.get("summary") or resp.get("result") or resp.get("status") or "")
        rows.append({"tool": c.get("name") or "tool", "summary": str(summary)[:280], "uri": uri})
    return rows

def _aggregate(norm: dict) -> dict:
    plan_str, gov_log = "", []
    state_receipts = []

    for sd in norm.get("state_updates", []):
        if isinstance(sd.get("current_plan"), str) and sd["current_plan"].strip():
            plan_str = sd["current_plan"].strip()
        if isinstance(sd.get("governor_log"), list):
            gov_log.extend(sd["governor_log"])
        if isinstance(sd.get("receipts"), list):
            state_receipts = sd["receipts"]

    rows = _flatten_run_plan_receipts(norm.get("tool_calls", []))
    if not rows and state_receipts:
        rows = _rows_from_state_receipts(state_receipts)
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

def _new_message_parts(query: str, image_uri: Optional[str]) -> List[dict]:
    parts = [{"text": query or ""}]
    if not image_uri:
        return parts

    p: Optional[Path] = None
    if image_uri.startswith("file://"):
        p = Path(image_uri.replace("file://", ""))
    elif image_uri.startswith("/"):
        p = Path(image_uri)
    if p and p.exists():
        parts.append({
            "inlineData": {
                "mimeType": mimetypes.guess_type(str(p))[0] or "image/jpeg",
                "data": base64.b64encode(p.read_bytes()).decode("ascii"),
            }
        })
    else:
        parts.append({"text": f"(Attached: {image_uri})"})
    return parts

def _post_events(payload: dict, prefer_sse: bool) -> dict:
    try:
        r = SESSION.post(f"{ADK_SERVER_URL}/run", json=payload, timeout=120)
        if r.ok:
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else json.loads(r.text or "[]")
            return _aggregate(_normalize_events(data))
        if r.status_code not in (404, 405):
            r.raise_for_status()
    except Exception:
        pass

    try:
        rs = SESSION.post(f"{ADK_SERVER_URL}/run_sse", json=payload, stream=True, timeout=None)
        if rs.ok:
            text = "\n".join(line for line in rs.iter_lines(decode_unicode=True) if line)
            return _aggregate(_normalize_events(_parse_sse(text)))
    except Exception:
        pass

    r2 = SESSION.post(f"{ADK_SERVER_URL}/run", json=payload, timeout=240)
    if r2.ok:
        data = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else json.loads(r2.text or "[]")
        return _aggregate(_normalize_events(data))
    r2.raise_for_status()

def run_agent_once(query: str, image_uri: Optional[str] = None, prefer_sse: bool = False) -> dict:
    payload = {
        "app_name": APP_NAME,
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "new_message": {"role": "user", "parts": _new_message_parts(query, image_uri)},
        "streaming": False,
    }
    return _post_events(payload, prefer_sse=bool(image_uri) or prefer_sse)

def run_once(*, query: str, image_uri: Optional[str] = None, prefer_sse: bool = False) -> dict:
    return run_agent_once(query=query, image_uri=image_uri, prefer_sse=prefer_sse)

__all__ = ["ensure_session", "run_agent_once", "run_once"]
