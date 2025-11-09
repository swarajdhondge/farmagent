from typing import Optional
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe

@FunctionTool
def market_insight_tool(crop: Optional[str] = None, region: Optional[str] = None) -> dict:
    """
    Stub market insight provider. Replace with actual datasource later.
    """
    out = {
        "crop": crop or "unknown",
        "region": region or "unknown",
        "avg_price": 0.0,
        "trend": "unknown",
    }
    log_receipt_safe("market_insight_tool", "success", out, confidence=0.5)
    return out
