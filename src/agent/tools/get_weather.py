from typing import Optional
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe

@FunctionTool
def get_weather_tool(location: Optional[str] = None) -> dict:
    """
    Stub weather data provider. Replace with real API later.
    """
    out = {
        "location": location or "unknown",
        "temp_c": 0.0,
        "rain_prob": 0.0,
        "summary": "unknown",
    }
    log_receipt_safe("get_weather_tool", "success", out, confidence=0.5)
    return out
