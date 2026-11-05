"""OpenTelemetry spans in the GenAI conventions that AgentCore Evaluations reads.

The agent is hand-written, so it records its own spans: one invoke_agent span per question,
one chat span per model call and one execute_tool span per tool call. The scope name must start
with "opentelemetry.instrumentation." for Evaluations' generic framework support. Without the
ADOT distro (local runs, tests) these calls are no-ops.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace

tracer = trace.get_tracer("opentelemetry.instrumentation.askwri")


def _messages(role: str, text: str) -> str:
    return json.dumps([{"role": role, "parts": [{"type": "text", "content": text}]}])


@contextmanager
def agent_span(question: str, session_id: str) -> Iterator[trace.Span]:
    """Span for one whole question; record the answer with finish_agent_span."""
    with tracer.start_as_current_span("invoke_agent askwri") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.agent.name", "askwri")
        span.set_attribute("gen_ai.conversation.id", session_id)
        # Evaluations finds a session's spans by session.id, not the GenAI conversation id.
        span.set_attribute("session.id", session_id)
        span.set_attribute("gen_ai.task.input", question)
        span.set_attribute("agentcore.invocation.user_prompt", question)
        yield span


def finish_agent_span(span: trace.Span, response: str) -> None:
    """Record the text the user was shown (answer or decline)."""
    span.set_attribute("gen_ai.task.output", response)
    span.set_attribute("agentcore.invocation.agent_response", response)


@contextmanager
def chat_span(model: str, system: str, prompt: str) -> Iterator[trace.Span]:
    """Span for one model call; record the reply with finish_chat_span."""
    with tracer.start_as_current_span(f"chat {model}") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.system_instructions", system)
        span.set_attribute("gen_ai.input.messages", _messages("user", prompt))
        yield span


def finish_chat_span(span: trace.Span, reply: str, input_tokens: int, output_tokens: int) -> None:
    span.set_attribute("gen_ai.output.messages", _messages("assistant", reply))
    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)


@contextmanager
def tool_span(name: str, arguments: dict) -> Iterator[trace.Span]:
    """Span for one gateway tool call; record the result with finish_tool_span."""
    with tracer.start_as_current_span(f"execute_tool {name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", name)
        span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments, ensure_ascii=False))
        yield span


def finish_tool_span(span: trace.Span, result: dict) -> None:
    span.set_attribute("gen_ai.tool.call.result", json.dumps(result, ensure_ascii=False)[:20000])
