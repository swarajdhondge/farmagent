from typing import Optional
from google.adk.tools import FunctionTool
from .utils import log_receipt_safe

@FunctionTool
def diagnose_leaf_tool(image_ref: Optional[str] = None) -> dict:
    """
    Stub leaf disease detector based on an image reference.
    """
    disease, conf = "unknown", 0.0
    if image_ref:
        disease, conf = "possible_leaf_spot", 0.4

    out = {"disease": disease, "confidence": conf, "image_ref": image_ref}
    log_receipt_safe("diagnose_leaf_tool", "success", out, confidence=conf)
    return out
