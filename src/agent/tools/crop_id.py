from typing import Optional
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe

@FunctionTool
def crop_id_tool(hint_text: Optional[str] = None) -> dict:
    """
    Heuristic crop identification from hint text (stub).
    """
    crop, conf = "unknown", 0.2
    if hint_text and isinstance(hint_text, str) and hint_text.strip():
        crop, conf = hint_text.strip().lower(), 0.5

    out = {"crop": crop, "confidence": conf}
    log_receipt_safe("crop_id_tool", "success", out, confidence=conf)
    return out
