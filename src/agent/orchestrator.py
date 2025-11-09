from google.adk.agents import SequentialAgent, LoopAgent
from .advisor.planner import planner_agent
from .advisor.executor import executor_agent
from .advisor.synthesizer import synthesizer_agent

planning_loop_agent = LoopAgent(
    name="PlanningLoopAgent",
    sub_agents=[planner_agent],
    max_iterations=6,
)

root_agent = SequentialAgent(
    name="FarmAgent_Orchestrator",
    sub_agents=[planning_loop_agent, executor_agent, synthesizer_agent],
)

# Back-compat if something else imports it
orchestrator_agent = root_agent
