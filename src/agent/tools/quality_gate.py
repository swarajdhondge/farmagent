from typing import Optional
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe
import datetime

@FunctionTool
def quality_gate_tool(crop_type: Optional[str] = None, soil_ph: Optional[float] = None) -> dict:
    """
    Lightweight validation: soil pH range and crop type presence.
    AFC-safe (no ToolContext in signature).
    """
    start = datetime.datetime.now()

    valid = True
    reasons = []

    if soil_ph is not None:
        if 5.5 <= soil_ph <= 7.5:
            reasons.append("pH in healthy range.")
        else:
            reasons.append("pH outside healthy range (5.5–7.5).")
            valid = False

    if crop_type:
        reasons.append(f"Crop '{crop_type}' accepted.")

    status = "success" if valid else "failed"
    out = {
        "valid": valid,
        "reasons": reasons or ["No checks applied."],
        "duration_ms": round((datetime.datetime.now() - start).total_seconds() * 1000, 2),
    }

    log_receipt_safe("quality_gate_tool", status, out, confidence=0.9 if valid else 0.6)
    return out
