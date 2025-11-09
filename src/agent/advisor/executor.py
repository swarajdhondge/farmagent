from google.adk.agents import LlmAgent
from ..tools import run_plan_tool
from .governor import governor_callback

# Minimal executor: call run_plan_tool exactly once, then stop.
executor_agent = LlmAgent(
    name="PlanExecutor",
    instruction=(
        "Execute the current plan stored in state.current_plan by calling "
        "`run_plan_tool` exactly once, then finish. Do not add free text."
    ),
    model="gemini-2.5-flash",
    tools=[run_plan_tool],
    before_model_callback=governor_callback,
)
