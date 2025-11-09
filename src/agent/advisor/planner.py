import json, re
from typing import Any, Dict, List, Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest

from .prompts import PLANNER_INSTRUCTION
from .governor import governor_callback
from ..tools import (
    quality_gate_tool, crop_id_tool, diagnose_leaf_tool,
    get_weather_tool, get_soil_tool,
    recommend_fertilizer_tool, market_insight_tool, exit_loop_tool
)

DEFAULT_STATE = {
    "core_context": "General farm advisory request",
    "current_plan": "",
    "governor_log": [],
    "receipts": [],
    "uploaded_image_uri": None,
    "location": None,
}

# Accept both spellings for the exit tool, and all real tools registered.
_ALLOWED_TOOLS = {
    "crop_id_tool",
    "diagnose_leaf_tool",
    "get_weather_tool",
    "get_soil_tool",
    "quality_gate_tool",
    "recommend_fertilizer_tool",
    "market_insight_tool",
    "exit_loop_tool",
    "exit_loop_tool_fn",
}

_json_re = re.compile(r"\{[\s\S]*\}", re.M)

def _extract_json_blob(text: str) -> Optional[str]:
    m = _json_re.search(text or "")
    return m.group(0) if m else None

def before_planner_callback(
    callback_context: CallbackContext,
    llm_request: Optional[LlmRequest] = None,
    **_: Any,
) -> None:
    """
    ADK passes llm_request to before_model callbacks. Accept it and forward to governor.
    """
    state = callback_context.state
    for k, v in DEFAULT_STATE.items():
        state.setdefault(k, v)

    # Run governor pre-checks
    governor_callback(callback_context, llm_request)

def _synth_fallback_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic plan when LLM plan is invalid/empty/exit-only."""
    has_image = bool(state.get("uploaded_image_uri"))
    loc = state.get("location")

    steps: List[Dict[str, Any]] = []
    # Vision path (first two). diagnose becomes optional if no image.
    steps.append({
        "id": "s1", "tool": "crop_id_tool",
        "args": {"hint_text": (state.get("core_context") or "")[:120]},
        "optional": False,
    })
    steps.append({
        "id": "s2", "tool": "diagnose_leaf_tool",
        "args": {"image_ref": state.get("uploaded_image_uri")},
        "optional": not has_image,
    })
    # Context enrichment (optional if inputs missing)
    steps.append({
        "id": "s3", "tool": "get_weather_tool",
        "args": {"location": loc} if loc else {},
        "optional": True,
    })
    steps.append({
        "id": "s4", "tool": "get_soil_tool",
        "args": {"location": loc} if loc else {},
        "optional": True,
    })
    # Mandatory quality gate = ensures ≥1 real tool runs every turn
    steps.append({"id": "s5", "tool": "quality_gate_tool", "args": {}, "optional": False})
    steps.append({"id": "s6", "tool": "recommend_fertilizer_tool", "args": {}, "optional": True})
    steps.append({"id": "sx", "tool": "exit_loop_tool_fn", "args": {}, "optional": False})

    return {"steps": steps, "notes": "Deterministic fallback to ensure tool execution."}

def _ensure_non_optional_quality_gate(plan_json_str: str) -> str:
    """Guarantee ≥1 non-exit, non-optional step; inject quality_gate_tool if needed."""
    try:
        plan = json.loads((plan_json_str or "{}").strip())
    except Exception:
        return plan_json_str

    steps = list(plan.get("steps") or [])
    has_non_optional = any(
        (s.get("tool") not in {"exit_loop_tool", "exit_loop_tool_fn"}) and (not s.get("optional", False))
        for s in steps
    )
    if has_non_optional:
        return json.dumps({**plan, "steps": steps})

    qg_step = {"id": "qg", "tool": "quality_gate_tool", "args": {}, "optional": False}
    exit_idx = next((i for i, s in enumerate(steps)
                     if s.get("tool") in {"exit_loop_tool", "exit_loop_tool_fn"}), None)
    if exit_idx is None:
        steps.append(qg_step)
        steps.append({"id": "sx", "tool": "exit_loop_tool_fn", "args": {}, "optional": False})
    else:
        steps.insert(exit_idx, qg_step)

    plan["steps"] = steps
    return json.dumps(plan)

def after_planner_callback(callback_context: CallbackContext, llm_response):
    """
    Parse assistant text into a strict plan and store as state.current_plan (string JSON).
    If the plan is missing/invalid/exit-only/unknown tools, synthesize a deterministic one.
    """
    state = callback_context.state

    # Extract assistant text
    text = ""
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", []) if content else []
    for p in parts:
        if getattr(p, "text", None):
            text += p.text + "\n"

    plan_obj: Optional[Dict[str, Any]] = None
    blob = _extract_json_blob(text)
    if blob:
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
                plan_obj = parsed
        except Exception:
            plan_obj = None

    def _invalid(plan: Optional[Dict[str, Any]]) -> bool:
        if not plan or not isinstance(plan.get("steps"), list) or len(plan["steps"]) == 0:
            return True
        tools = [str(s.get("tool", "")) for s in plan["steps"]]
        all_unknown = all(t not in _ALLOWED_TOOLS for t in tools)
        exit_only   = len([t for t in tools if t not in {"exit_loop_tool", "exit_loop_tool_fn"}]) == 0
        return all_unknown or exit_only

    if _invalid(plan_obj):
        plan_obj = _synth_fallback_plan(state)

    plan_json = json.dumps(plan_obj, ensure_ascii=False, indent=2)
    state["current_plan"] = _ensure_non_optional_quality_gate(plan_json)

planner_agent = LlmAgent(
    name="PlannerAgent",
    instruction=PLANNER_INSTRUCTION,
    model="gemini-2.5-pro",
    tools=[
        quality_gate_tool, crop_id_tool, diagnose_leaf_tool,
        get_weather_tool, get_soil_tool,
        recommend_fertilizer_tool, market_insight_tool, exit_loop_tool,
    ],
    before_model_callback=before_planner_callback,
    after_model_callback=after_planner_callback,
)
