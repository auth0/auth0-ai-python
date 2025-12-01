from datetime import datetime
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from src.agents.tools.check_user_calendar import check_user_calendar_tool
from src.agents.tools.list_repositories import list_github_repositories_tool
from src.agents.tools.list_channels import list_slack_channels_tool


class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


llm = ChatOpenAI(
    model="gpt-4o"
).bind_tools([check_user_calendar_tool, list_github_repositories_tool, list_slack_channels_tool])


async def call_llm(state: State):
    messages = state["messages"]
    system_prompt = f"""You are an assistant designed to answer random user's questions.
**Additional Guidelines**:
- Today’s date for reference: {datetime.now().isoformat()}
"""
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message] + messages

    response = await llm.ainvoke(messages)
    return {"messages": [response]}


def route_after_llm(state: State):
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


state_graph = (
    StateGraph(State)
    .add_node("call_llm", call_llm)
    .add_node(
        "tools",
        ToolNode(
            [check_user_calendar_tool, list_github_repositories_tool,
                list_slack_channels_tool],
            # The error handler should be disabled to allow interruptions to be triggered from within tools.
            handle_tool_errors=False
        )
    )
    .add_edge(START, "call_llm")
    .add_edge("tools", "call_llm")
    .add_conditional_edges("call_llm", route_after_llm, [END, "tools"])
)

graph = state_graph.compile()
