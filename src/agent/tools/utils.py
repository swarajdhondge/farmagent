from typing import Any, Dict

def log_receipt_safe(tool: str, status: str, output: Dict[str, Any], confidence: float = 1.0):
    """
    Append a normalized receipt to the current ADK ToolContext if available.
    Safe when called outside agent context.
    """
    try:
        from google.adk.tools.tool_context import ToolContext
        context = ToolContext.get_current()
        if not context or not hasattr(context, "state"):
            return
        state = context.state
        state.setdefault("receipts", [])
        state["receipts"].append({
            "tool": tool,
            "status": status,
            "output": output,
            "confidence": confidence,
        })
        # Surface the latest confidence to the governor
        state["confidence_score"] = confidence
    except Exception:
        pass
