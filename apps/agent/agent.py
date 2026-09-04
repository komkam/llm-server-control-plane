"""Tool-calling diagnostic agent built with LangGraph.

This module intentionally reuses the diagnostic functions in ``tools/``.  The
model chooses tools through OpenAI-compatible function calling rather than a
keyword router; LangGraph executes those calls and returns their structured
results to the model until it can answer the user.
"""

import json
import sys
from typing import Annotated, TypedDict
import re

import requests
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from tools.docker import get_docker_images, get_docker_info, get_docker_logs, get_docker_stats
from tools.gpu import get_gpu_info
from tools.llm import get_failed_services, get_llm_latency, get_llm_services
from tools.logs import get_system_logs
from tools.network import get_endpoint_health
from tools.system import (
    get_cpu_info,
    get_disk_info,
    get_llm_processes,
    get_memory_info,
    get_system_info,
    get_uptime_info,
)

# The user-facing router selects chat backends.  This agent needs direct
# tool-calling support, so it talks to the capable model endpoint itself.
AI_CORE_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "qwen2.5:7b"
REQUEST_TIMEOUT_SECONDS = 120
MAX_GRAPH_STEPS = 12
LANGUAGE_POLICY_VERSION = 2

# CJK output is prohibited by the agent's public language policy.  The model
# can occasionally ignore a prompt, so enforce the policy after generation too.
DISALLOWED_OUTPUT = re.compile(r"[\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")

SYSTEM_PROMPT = """You are an expert Linux LLM server diagnostician.
Use tools only when their data is relevant to the user's request.  Do not
invent measurements.  Distinguish facts, inferences, and possible root causes.
For LLM performance, prioritize inference latency, tokens/sec, GPU, CPU,
memory, process configuration, and router overhead.  A fast health endpoint
does not prove model inference is fast.  Keep the final answer concise and
technical.

Language policy: respond only in Thai or English.  Reply in the same language
as the user's latest message when it is Thai or English; otherwise use English.
Never respond in Chinese or any other language, including headings, labels, and
conclusions.  Translate or summarize tool output into the selected language."""

TOOL_DESCRIPTIONS = {
    "get_system_info": "Read the server uptime and load average.",
    "get_memory_info": "Read RAM and swap utilization.",
    "get_disk_info": "Read filesystem capacity and usage.",
    "get_llm_processes": "List processes ordered by CPU utilization.",
    "get_cpu_info": "Read CPU topology and current load.",
    "get_uptime_info": "Read human-readable server uptime.",
    "get_gpu_info": "Read NVIDIA GPU utilization, VRAM, power, and compute processes.",
    "get_docker_info": "List running Docker containers, images, states, and ports.",
    "get_docker_stats": "Read one non-streaming Docker CPU and memory snapshot.",
    "get_docker_logs": "Read a bounded number of recent lines from one Docker container.",
    "get_docker_images": "List locally available Docker images.",
    "get_failed_services": "List failed systemd services.",
    "get_llm_services": "Read status of Ollama, llama-server, and router services.",
    "get_llm_latency": "Run active, small LLM latency benchmarks. Use only when performance measurement is explicitly requested.",
    "get_endpoint_health": "Check local LLM endpoint health and response time.",
    "get_system_logs": "Read a bounded number of recent system journal entries.",
}

TOOL_FUNCTIONS = [
    get_system_info, get_memory_info, get_disk_info, get_llm_processes,
    get_cpu_info, get_uptime_info, get_gpu_info, get_docker_info,
    get_docker_stats, get_docker_logs, get_docker_images, get_failed_services,
    get_llm_services, get_llm_latency, get_endpoint_health, get_system_logs,
]

TOOLS = [
    StructuredTool.from_function(
        func=function,
        name=function.__name__,
        description=TOOL_DESCRIPTIONS[function.__name__],
    )
    for function in TOOL_FUNCTIONS
]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _json_content(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _as_openai_message(message: BaseMessage) -> dict:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": _json_content(message.content)}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": _json_content(message.content)}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": _json_content(message.content),
        }
    if isinstance(message, AIMessage):
        payload = {"role": "assistant", "content": _json_content(message.content)}
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"], ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return payload
    raise TypeError(f"Unsupported message type: {type(message)!r}")


def _tool_schema(tool: StructuredTool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_schema.model_json_schema(),
        },
    }


def response_language(messages: list[BaseMessage]) -> str:
    """Choose the only permitted response language from the latest user turn."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _json_content(message.content)
            return "Thai" if re.search(r"[\u0E00-\u0E7F]", text) else "English"
    return "English"


def enforce_output_language(answer: str, language: str) -> str:
    """Rewrite a non-compliant answer once, with a safe language-only fallback."""
    if not DISALLOWED_OUTPUT.search(answer):
        return answer

    rewrite_prompt = (
        f"Rewrite the following diagnostic answer in {language}. "
        f"Output only {language}; never output Chinese, Japanese, or Korean characters. "
        "Preserve facts, measurements, and uncertainty.\n\n"
        f"Answer to rewrite:\n{answer}"
    )
    try:
        response = requests.post(
            AI_CORE_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "You are a strict language rewriter."},
                    {"role": "user", "content": rewrite_prompt},
                ],
                "temperature": 0,
                "stream": False,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        rewritten = response.json()["choices"][0]["message"].get("content", "").strip()
        if rewritten and not DISALLOWED_OUTPUT.search(rewritten):
            return rewritten
    except Exception:
        pass

    if language == "Thai":
        return "โมเดลวิเคราะห์ส่งคำตอบเป็นภาษาที่ไม่รองรับ กรุณาลองส่งคำขออีกครั้ง"
    return "The diagnostic model returned a response in an unsupported language. Please try again."


def call_model(state: AgentState) -> dict:
    """Call the existing OpenAI-compatible backend and normalize tool calls."""
    language = response_language(state["messages"])
    language_instruction = (
        f"MANDATORY OUTPUT LANGUAGE: {language}. "
        f"Write every user-visible word only in {language}. "
        "Do not output Chinese characters or Chinese words. "
        "This requirement applies to the final answer, headings, labels, and summaries."
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=language_instruction),
        *state["messages"],
    ]
    response = requests.post(
        AI_CORE_URL,
        json={
            "model": MODEL,
            "messages": [_as_openai_message(message) for message in messages],
            "tools": [_tool_schema(tool) for tool in TOOLS],
            "tool_choice": "auto",
            "temperature": 0,
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    choice = response.json()["choices"][0]["message"]
    tool_calls = []
    for call in choice.get("tool_calls") or []:
        function = call["function"]
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        tool_calls.append({"id": call["id"], "name": function["name"], "args": arguments})

    return {"messages": [AIMessage(content=choice.get("content") or "", tool_calls=tool_calls)]}


def continue_or_finish(state: AgentState) -> str:
    last_message = state["messages"][-1]
    return "tools" if isinstance(last_message, AIMessage) and last_message.tool_calls else END


workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", continue_or_finish, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")
agent_graph = workflow.compile()


def run_agent(user_prompt: str) -> str:
    result = agent_graph.invoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": MAX_GRAPH_STEPS},
    )
    final_message = result["messages"][-1]
    return enforce_output_language(
        _json_content(final_message.content),
        response_language(result["messages"]),
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python3 agent.py "your question"')
        raise SystemExit(1)
    print(run_agent(" ".join(sys.argv[1:])))
