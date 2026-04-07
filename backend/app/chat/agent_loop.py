"""LLM-driven agent loop with OpenAI function calling.

Supports both synchronous and streaming execution. The loop calls the LLM,
checks for tool_calls in the response, executes them via ToolExecutor,
appends results, and loops until the LLM produces a final text response.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from openai import OpenAI

from app.chat.openai_client import usage_to_dict
from app.chat.tool_executor import ToolExecutor, ToolResult

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


@dataclass(slots=True)
class AgentLoopResult:
    reply: str
    sources: list[dict] = field(default_factory=list)
    usage: dict[str, int] | None = None
    action: dict | None = None
    used_tools: bool = False


def _accumulate_usage(
    total: dict[str, int] | None,
    new: dict[str, int] | None,
) -> dict[str, int] | None:
    if new is None:
        return total
    if total is None:
        return dict(new)
    return {
        "prompt_tokens": total.get("prompt_tokens", 0) + new.get("prompt_tokens", 0),
        "completion_tokens": total.get("completion_tokens", 0) + new.get("completion_tokens", 0),
        "total_tokens": total.get("total_tokens", 0) + new.get("total_tokens", 0),
    }


def run_agent_loop(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict],
    tool_executor: ToolExecutor,
) -> AgentLoopResult:
    """Run the agent loop synchronously until the LLM produces a text response."""
    accumulated_usage: dict[str, int] | None = None
    action: dict | None = None
    used_tools = False

    for iteration in range(MAX_TOOL_ITERATIONS):
        tool_choice = "auto" if iteration < MAX_TOOL_ITERATIONS - 1 else "none"

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tool_choice == "auto" else None,
            tool_choice=tool_choice if tool_choice == "auto" else None,
        )

        accumulated_usage = _accumulate_usage(
            accumulated_usage,
            usage_to_dict(getattr(response, "usage", None)),
        )

        choice = response.choices[0]
        assistant_message = choice.message

        if not assistant_message.tool_calls:
            return AgentLoopResult(
                reply=(assistant_message.content or "").strip(),
                usage=accumulated_usage,
                action=action,
                used_tools=used_tools,
            )

        messages.append({
            "role": "assistant",
            "content": assistant_message.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ],
        })

        used_tools = True
        for tc in assistant_message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            logger.info(
                "Agent tool call",
                extra={"tool": tc.function.name, "arguments": args, "iteration": iteration},
            )

            result: ToolResult = tool_executor.execute(tc.function.name, args)

            if result.action is not None:
                action = result.action

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result.content,
            })

    return AgentLoopResult(
        reply="I ran into a limit on the number of steps I can take. Please try again with a simpler request.",
        usage=accumulated_usage,
        used_tools=used_tools,
        action=action,
    )


@dataclass(slots=True)
class AgentStreamEvent:
    """An event yielded by the streaming agent loop."""
    event_type: str  # "delta", "tool_call", "completion", "error"
    data: dict


def run_agent_loop_stream(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict],
    tool_executor: ToolExecutor,
) -> Iterator[AgentStreamEvent]:
    """Run the agent loop with streaming. Yields AgentStreamEvents.

    During intermediate tool-call iterations, yields tool_call events.
    On the final iteration (text response), yields delta events for each chunk
    and a completion event at the end.
    """
    accumulated_usage: dict[str, int] | None = None
    action: dict | None = None

    for iteration in range(MAX_TOOL_ITERATIONS):
        is_last_chance = iteration == MAX_TOOL_ITERATIONS - 1
        tool_choice = "none" if is_last_chance else "auto"

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if not is_last_chance else None,
            tool_choice=tool_choice if not is_last_chance else None,
            stream=True,
            stream_options={"include_usage": True},
        )

        content_parts: list[str] = []
        tool_calls_by_index: dict[int, dict] = {}
        chunk_usage = None

        for chunk in stream:
            chunk_usage = usage_to_dict(getattr(chunk, "usage", None)) or chunk_usage

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                content_parts.append(delta.content)
                yield AgentStreamEvent(event_type="delta", data={"delta": delta.content})

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_by_index:
                        tool_calls_by_index[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = tool_calls_by_index[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

        accumulated_usage = _accumulate_usage(accumulated_usage, chunk_usage)

        if not tool_calls_by_index:
            yield AgentStreamEvent(
                event_type="completion",
                data={
                    "reply": "".join(content_parts).strip(),
                    "usage": accumulated_usage,
                    "action": action,
                },
            )
            return

        assistant_content = "".join(content_parts) or None
        messages.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in tool_calls_by_index.values()
            ],
        })

        for tc in tool_calls_by_index.values():
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            yield AgentStreamEvent(
                event_type="tool_call",
                data={"tool": tc["name"], "arguments": args},
            )

            result: ToolResult = tool_executor.execute(tc["name"], args)
            if result.action is not None:
                action = result.action

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result.content,
            })

    yield AgentStreamEvent(
        event_type="completion",
        data={
            "reply": "I ran into a limit on the number of steps I can take. Please try again with a simpler request.",
            "usage": accumulated_usage,
            "action": action,
        },
    )
