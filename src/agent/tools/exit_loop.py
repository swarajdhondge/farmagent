from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

def exit_loop_tool_fn(tool_context: ToolContext):
    """
    Proper loop terminator for ADK 1.18.
    ADK passes `tool_context` automatically when invoking this FunctionTool.
    """
    if hasattr(tool_context, "actions"):
        tool_context.actions.escalate = True  # tells the LoopAgent to break
    return {"message": "Loop termination requested."}

exit_loop_tool = FunctionTool(exit_loop_tool_fn)
