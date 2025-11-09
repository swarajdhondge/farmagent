from typing import Optional
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe

@FunctionTool
def get_soil_tool(location: Optional[str] = None) -> dict:
    """
    Stub soil composition provider. Replace with real datasource later.
    """
    out = {
        "location": location or "unknown",
        "ph": 6.2,
        "nitrogen": 0.0,
        "organic_matter_pct": 0.0,
    }
    log_receipt_safe("get_soil_tool", "success", out, confidence=0.6)
    return out
