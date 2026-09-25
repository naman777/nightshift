"""Thin model adapter: Anthropic / OpenAI over httpx, plus a deterministic mock. Owns token + cost accounting."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Awaitable, Callable, Protocol

import httpx

from .models import LLMResponse, Message, ToolCall, Usage

# USD per 1M tokens (input, output). Unknown models fall back to DEFAULT_PRICE.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-5": (5.0, 25.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "mock-strong": (5.0, 25.0),
    "mock-cheap": (1.0, 5.0),
}
DEFAULT_PRICE = (3.0, 15.0)


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
    """`input_tokens` are the uncached input tokens; cache reads bill at 10% and cache writes at 125% of the input price."""
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    return round((input_tokens * pin + cache_read * pin * 0.1 + cache_write * pin * 1.25 + output_tokens * pout) / 1_000_000, 6)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


async def post_with_retry(client: httpx.AsyncClient, url: str, attempts: int = 4, **kw: Any) -> httpx.Response:
    """POST with exponential backoff on rate limits, overload and transient network errors (LLM APIs return 429/529 under load)."""
    delay = 1.0
    for i in range(attempts):
        try:
            r = await client.post(url, **kw)
            if r.status_code not in RETRY_STATUS or i == attempts - 1:
                r.raise_for_status()
                return r
        except (httpx.TransportError, httpx.TimeoutException):
            if i == attempts - 1:
                raise
        await asyncio.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")  # pragma: no cover


class ToolSchema(dict):
    """{'name','description','input_schema'} — JSON-schema for a tool."""


class LLM(Protocol):
    async def complete(self, system: str, messages: list[Message], tools: list[dict], model: str,
                       max_tokens: int = 2048) -> LLMResponse: ...


# -- Mock ---------------------------------------------------------------------------

Responder = Callable[[str, list[Message], list[dict], str], LLMResponse | Awaitable[LLMResponse]]


class MockLLM:
    """Deterministic provider driven by a responder function: (system, messages, tools, model) -> LLMResponse.

    Token counts are estimated from text length so budgets and cost accounting behave realistically.
    """

    def __init__(self, responder: Responder):
        self.responder = responder
        self.calls = 0

    async def complete(self, system, messages, tools, model, max_tokens=2048) -> LLMResponse:
        self.calls += 1
        out = self.responder(system, messages, tools, model)
        if hasattr(out, "__await__"):
            out = await out
        in_tok = estimate_tokens(system) + sum(estimate_tokens(m.content) + 20 * len(m.tool_calls) for m in messages)
        out_tok = estimate_tokens(out.text) + sum(estimate_tokens(json.dumps(t.arguments)) + 8 for t in out.tool_calls)
        out.usage = Usage(input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost_usd(model, in_tok, out_tok), llm_calls=1)
        out.model = model
        return out


# -- Anthropic ----------------------------------------------------------------------

class AnthropicLLM:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = client or httpx.AsyncClient(timeout=120)

    @staticmethod
    def _messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                blocks += [{"type": "tool_use", "id": t.id, "name": t.name, "input": t.arguments} for t in m.tool_calls]
                out.append({"role": "assistant", "content": blocks})
            else:  # tool result
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    async def complete(self, system, messages, tools, model, max_tokens=2048) -> LLMResponse:
        # cache_control on the system block caches tools + system across the many calls of one investigation
        body = {"model": model, "max_tokens": max_tokens, "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "messages": self._messages(messages),
                "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools]}
        r = await post_with_retry(self.client, self.URL, json=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        data = r.json()
        text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
        calls = [ToolCall(id=b["id"], name=b["name"], arguments=b["input"]) for b in data["content"] if b["type"] == "tool_use"]
        u = data.get("usage", {})
        i, o = u.get("input_tokens", 0), u.get("output_tokens", 0)
        cr, cw = u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0)
        return LLMResponse(text=text, tool_calls=calls, model=model,
                           usage=Usage(input_tokens=i + cr + cw, output_tokens=o, cost_usd=cost_usd(model, i, o, cr, cw), llm_calls=1,
                                       cache_read_tokens=cr, cache_write_tokens=cw))


def _parse_args(raw: str | None) -> dict[str, Any]:
    """Models occasionally emit malformed JSON arguments; surface that to the loop as a tool error instead of crashing the run."""
    try:
        val = json.loads(raw or "{}")
        return val if isinstance(val, dict) else {"__malformed__": raw}
    except ValueError:
        return {"__malformed__": raw}


# -- OpenAI -------------------------------------------------------------------------

class OpenAILLM:
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.client = client or httpx.AsyncClient(timeout=120)

    @staticmethod
    def _messages(system: str, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    msg["tool_calls"] = [{"id": t.id, "type": "function",
                                          "function": {"name": t.name, "arguments": json.dumps(t.arguments)}} for t in m.tool_calls]
                out.append(msg)
            else:
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        return out

    async def complete(self, system, messages, tools, model, max_tokens=2048) -> LLMResponse:
        body = {"model": model, "max_tokens": max_tokens, "messages": self._messages(system, messages),
                "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                            "parameters": t["input_schema"]}} for t in tools]}
        r = await post_with_retry(self.client, self.URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        data = r.json()
        msg = data["choices"][0]["message"]
        calls = [ToolCall(id=c["id"], name=c["function"]["name"], arguments=_parse_args(c["function"]["arguments"]))
                 for c in msg.get("tool_calls") or []]
        u = data.get("usage", {})
        i, o = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        return LLMResponse(text=msg.get("content") or "", tool_calls=calls, model=model,
                           usage=Usage(input_tokens=i, output_tokens=o, cost_usd=cost_usd(model, i, o), llm_calls=1))


def make_llm(provider: str | None = None, responder: Responder | None = None) -> LLM:
    provider = provider or os.environ.get("NIGHTSHIFT_LLM_PROVIDER", "mock")
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    if responder is None:
        raise ValueError("mock provider needs a responder (see agents.scripted)")
    return MockLLM(responder)
