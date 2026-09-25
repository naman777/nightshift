from __future__ import annotations

import json

import httpx

from agents.cli import main as cli_main
from agents.core.llm import AnthropicLLM, OpenAILLM
from agents.core.models import Message, ToolCall

TOOLS = [{"name": "metrics__top_anomalies", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
HISTORY = [
    Message(role="user", content="investigate"),
    Message(role="assistant", content="checking", tool_calls=[ToolCall(id="tu_1", name="metrics__top_anomalies", arguments={"window_minutes": 30})]),
    Message(role="tool", tool_call_id="tu_1", tool_name="metrics__top_anomalies", content="<tool_result>...</tool_result>"),
]


async def test_anthropic_request_and_response_translation():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["headers"] = json.loads(request.content), request.headers
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"},
                                                     {"type": "tool_use", "id": "tu_2", "name": "submit_finding", "input": {"summary": "s"}}],
                                         "usage": {"input_tokens": 1000, "output_tokens": 200}})

    llm = AnthropicLLM("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = await llm.complete("sys", HISTORY, TOOLS, "claude-haiku-4-5")
    b = seen["body"]
    assert seen["headers"]["x-api-key"] == "k" and b["system"] == "sys" and b["tools"][0]["input_schema"]["type"] == "object"
    assert b["messages"][1]["content"][1] == {"type": "tool_use", "id": "tu_1", "name": "metrics__top_anomalies", "input": {"window_minutes": 30}}
    assert b["messages"][2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "<tool_result>...</tool_result>"}]}
    assert r.text == "ok" and r.tool_calls[0].name == "submit_finding" and r.tool_calls[0].arguments == {"summary": "s"}
    assert r.usage.input_tokens == 1000 and r.usage.cost_usd == round((1000 * 1 + 200 * 5) / 1e6, 6)


async def test_openai_request_and_response_translation():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "submit_finding", "arguments": "{\"summary\": \"s\"}"}}]}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 100}})

    llm = OpenAILLM("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = await llm.complete("sys", HISTORY, TOOLS, "gpt-4o-mini")
    msgs = seen["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": "sys"} and msgs[2]["tool_calls"][0]["function"]["name"] == "metrics__top_anomalies"
    assert msgs[3] == {"role": "tool", "tool_call_id": "tu_1", "content": "<tool_result>...</tool_result>"}
    assert r.tool_calls[0].arguments == {"summary": "s"} and r.usage.cost_usd == round((500 * 0.15 + 100 * 0.6) / 1e6, 6)


def test_cli_investigates_a_scenario(capsys):
    assert cli_main(["investigate", "memory-leak-orders-cache-00"]) == 0
    out = capsys.readouterr().out
    assert "CORRECT" in out and "resource_leak" in out and "not executed" in out
    assert cli_main(["investigate", "no-such-scenario"]) == 2
    assert cli_main(["scenarios"]) == 0
