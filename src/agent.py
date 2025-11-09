import sys, os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agent.orchestrator import orchestrator_agent

# expose it for ADK
root_agent = orchestrator_agent
