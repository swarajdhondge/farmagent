from typing import Optional, Any, Dict
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe

def _last_receipt(tool_name: str) -> Dict[str, Any]:
    try:
        from google.adk.tools.tool_context import ToolContext
        ctx = ToolContext.get_current()
        if not ctx or not hasattr(ctx, "state"):
            return {}
        for r in reversed(ctx.state.get("receipts", [])):
            if r.get("tool") == tool_name:
                return r.get("output") or r.get("receipt") or r
    except Exception:
        pass
    return {}

@FunctionTool
def recommend_fertilizer_tool(target_crop: Optional[str] = None) -> dict:
    """
    Suggest a simple NPK ratio using prior soil/crop receipts.
    """
    soil = _last_receipt("get_soil_tool")
    crop = _last_receipt("crop_id_tool")

    ph = soil.get("ph")
    crop_name = target_crop or crop.get("crop") or "unknown"

    ratio, conf = "10-10-10", 0.55
    if isinstance(ph, (int, float)):
        if ph < 5.8:
            ratio, conf = "12-6-6", 0.5
        elif ph > 7.2:
            ratio, conf = "6-12-12", 0.5

    out = {"crop": crop_name, "npk_ratio": ratio, "note": "heuristic"}
    log_receipt_safe("recommend_fertilizer_tool", "success", out, confidence=conf)
    return out
