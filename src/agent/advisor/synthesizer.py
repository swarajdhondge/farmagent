from google.adk.agents import LlmAgent
from .prompts import SYNTHESIZER_INSTRUCTION
from .governor import governor_callback

synthesizer_agent = LlmAgent(
    name="SynthesizerAgent",
    instruction=SYNTHESIZER_INSTRUCTION,
    model="gemini-2.5-pro",
    before_model_callback=governor_callback,
)
