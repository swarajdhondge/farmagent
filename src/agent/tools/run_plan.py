from __future__ import annotations
import json, time
from typing import Any, Dict, List
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

# Import ADK FunctionTool wrappers
from .crop_id import crop_id_tool
from .diagnose_leaf import diagnose_leaf_tool
from .get_weather import get_weather_tool
from .get_soil import get_soil_tool
from .quality_gate import quality_gate_tool
from .recommend_fertilizer import recommend_fertilizer_tool
from .market_insight import market_insight_tool

from .utils import log_receipt_safe

_TOOL_MAP: Dict[str, FunctionTool] = {
    "crop_id_tool": crop_id_tool,
    "diagnose_leaf_tool": diagnose_leaf_tool,
    "get_weather_tool": get_weather_tool,
    "get_soil_tool": get_soil_tool,
    "quality_gate_tool": quality_gate_tool,
    "recommend_fertilizer_tool": recommend_fertilizer_tool,
    "market_insight_tool": market_insight_tool,
}

def _safe_args(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}

def _call(ft: FunctionTool, args: Dict[str, Any]) -> Any:
    """Invoke the underlying function of a FunctionTool so state receipts are captured."""
    fn = getattr(ft, "func", None)
    if callable(fn):
        return fn(**args) if args else fn()
    # Fallback if ADK wrapper requires run()
    ctx = ToolContext.get_current()
    return ft.run(args=args, tool_context=ctx)

@FunctionTool
def run_plan_tool(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Execute the JSON plan in state['current_plan'] and echo per-step receipts for the UI.
    Skips 'exit_loop_tool_fn'. Adds a synthetic receipt if no tool executed.
    """
    state = tool_context.state or {}
    state.setdefault("receipts", [])

    raw = state.get("current_plan") or "{}"
    try:
        plan = json.loads(raw)
    except Exception:
        plan = {}

    steps = plan.get("steps") or []
    executed = skipped = errors = 0

    for step in steps:
        tname = step.get("tool")
        if not tname or tname == "exit_loop_tool_fn":
            skipped += 1
            continue

        ft = _TOOL_MAP.get(tname)
        if not isinstance(ft, FunctionTool):
            skipped += 1
            log_receipt_safe(tname or "unknown", "skipped:unknown_tool", {"args": step.get("args")})
            continue

        args = _safe_args(step.get("args"))
        start = time.perf_counter()
        try:
            result = _call(ft, args)
            cost_ms = int((time.perf_counter() - start) * 1000)
            # Synthetic record in case the tool didn't log one
            log_receipt_safe(
                tname,
                "executed",
                {"args": args, "result": result, "cost_ms": cost_ms, "synthetic": True},
            )
            executed += 1
        except Exception as e:
            cost_ms = int((time.perf_counter() - start) * 1000)
            log_receipt_safe(
                tname,
                f"error:{type(e).__name__}",
                {"args": args, "error": str(e), "cost_ms": cost_ms},
            )
            errors += 1

    # Fail-fast receipt if nothing executed
    if executed == 0:
        log_receipt_safe(
            "run_plan_tool",
            "no_tools_ran",
            {"reason": "all steps optional or missing required inputs"}
        )

    # Echo per-step receipts so UI can render a line per inner tool
    receipts_snapshot: List[Dict[str, Any]] = list(state.get("receipts", []))
    return {
        "metrics": {
            "executed": executed,
            "skipped": skipped,
            "errors": errors,
            "total_steps": len(steps),
        },
        "receipts": receipts_snapshot,
    }
