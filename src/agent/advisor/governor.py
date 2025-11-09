from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# --- lightweight rules ------------
_PESTICIDE_TERMS = re.compile(
    r"\b(pesticide|insecticide|fungicide|glyphosate|roundup|spray)\b", re.I
)
_WEATHER_HINTS = re.compile(
    r"\b(weather|rain|temperature|forecast|humidity|wind|conditions)\b", re.I
)
_SYMPTOM_HINTS = re.compile(
    r"\b(leaf|leaves|spot|spots|blotch|blotches|wilt|yellow|yellowing|mold|fungus|disease|rot)\b",
    re.I,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(state: Dict[str, Any], action: str, reason: str, confidence: float = 1.0) -> None:
    log: List[Dict[str, Any]] = state.setdefault("governor_log", [])
    log.append(
        {
            "action": action,
            "confidence_score": confidence,
            "reason": reason,
            "timestamp": _now_iso(),
        }
    )


def _ensure_state(callback_context: Any) -> Dict[str, Any]:
    """
    ADK passes a CallbackContext with a mutable 'state' dict. Be tolerant if it's missing.
    """
    state = getattr(callback_context, "state", None)
    if not isinstance(state, dict):
        state = {}
        try:
            # best-effort set back on context so later steps see it
            setattr(callback_context, "state", state)
        except Exception:
            pass
    return state


def governor_callback(callback_context: Any, llm_request: Optional[Any]) -> None:
    """
    Safe, side-effect-only callback:
      - Never raises (prevents HTTP 500s).
      - Always writes at least one log row (keep_model) so the UI shows a Governor Log every turn.
      - Blocks only for clear safety / missing hard prereqs, otherwise nudges.
    """
    try:
        state = _ensure_state(callback_context)

        # Baseline entry so every query shows a governor log row
        model_str = None
        try:
            model_str = getattr(llm_request, "model", None)
        except Exception:
            model_str = None
        if not model_str:
            model_str = state.get("model") or "gemini-2.5-pro"

        confidence = 1.0
        try:
            confidence = float(state.get("confidence_score", 1.0))
        except Exception:
            confidence = 1.0

        _log(state, "keep_model", f"using {model_str}", confidence)

        # Build a conservative text context from state 
        ctx_text = (
            (state.get("last_user_text") or "")
            or (state.get("query") or "")
            or (state.get("input_text") or "")
        ).lower()

        image_uris: List[str] = list(state.get("image_uris") or [])
        has_image = bool(image_uris)

        # --- Safety: pesticide / chemical usage -> block model this turn
        if _PESTICIDE_TERMS.search(ctx_text):
            state["awaiting_fields"] = ["safety_confirmation"]
            state["loop_terminated"] = False
            _log(state, "block", "Pesticide-related request; require explicit confirmation.", confidence)
            # cancel the LLM call for this turn (tool path can still proceed)
            try:
                if llm_request is not None:
                    setattr(llm_request, "model", None)
            except Exception:
                pass
            return

        # --- Hard precondition: weather asked but no location -> block model this turn
        if _WEATHER_HINTS.search(ctx_text) and not state.get("location"):
            state["awaiting_fields"] = ["location"]
            state["loop_terminated"] = False
            _log(state, "block", "Weather context requested but 'location' missing.", confidence)
            try:
                if llm_request is not None:
                    setattr(llm_request, "model", None)
            except Exception:
                pass
            return

        # --- Soft nudge: symptoms but no image -> ask for image (non-blocking)
        if _SYMPTOM_HINTS.search(ctx_text) and not has_image:
            _log(
                state,
                "ask_for_image",
                "Symptoms mentioned but no image provided; attach one for crop_id/diagnose.",
                confidence,
            )
            awaiting = set(state.get("awaiting_fields", []))
            awaiting.add("image")
            state["awaiting_fields"] = list(awaiting)

    except Exception as e:
        # Fail-safe: never propagate to HTTP layer
        try:
            state = _ensure_state(callback_context)
            _log(state, "governor_failed_safe", f"{type(e).__name__}: {e}", 1.0)
        except Exception:
            pass
