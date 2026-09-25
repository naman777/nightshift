"""How agents reach tools. Agents never touch infrastructure directly: every call goes through an MCPClient.

Two transports share one interface:
  * InProcessClient  - calls MCP server objects directly, always through the policy layer (used by tests, bench, workers)
  * StdioMCPClient   - speaks real MCP over stdio to a server subprocess (mcp_servers/<name>/__main__.py)
"""
from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import Tier

SEP = "__"  # namespaced tool name: "metrics__query_range" (valid for every LLM provider)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    tier: Tier = Tier.READ_ONLY

    def as_llm(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass
class CallContext:
    incident_id: str = ""
    agent: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    reason: str = ""
    approved_by: str = ""      # set by the approval workflow (Slack click) for reversible tools
    confirmation: str = ""     # typed confirmation string for destructive tools


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    blocked: bool = False
    dry_run: bool = False


class MCPClient(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any], ctx: CallContext) -> ToolResult: ...


class InProcessClient:
    """Routes namespaced tool calls to in-process servers via the shared policy engine."""

    def __init__(self, servers: list[Any], policy: Any):
        self.servers = {s.name: s for s in servers}
        self.policy = policy

    async def list_tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for s in self.servers.values():
            for t in s.tools.values():
                out.append(ToolSpec(f"{s.name}{SEP}{t.name}", t.description, t.input_schema, t.tier))
        return out

    async def call_tool(self, name: str, arguments: dict[str, Any], ctx: CallContext) -> ToolResult:
        server_name, _, tool_name = name.partition(SEP)
        server = self.servers.get(server_name)
        if server is None or tool_name not in server.tools:
            return ToolResult(f"unknown tool: {name}", is_error=True)
        return await self.policy.execute(server, server.tools[tool_name], arguments, ctx)


class StdioMCPClient:
    """Real MCP over stdio. One subprocess per server; use as an async context manager."""

    def __init__(self, server_names: list[str], env: dict[str, str] | None = None):
        self.server_names = server_names
        self.env = env
        self._stack = contextlib.AsyncExitStack()
        self._sessions: dict[str, Any] = {}

    async def __aenter__(self) -> "StdioMCPClient":
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        for name in self.server_names:
            params = StdioServerParameters(command=sys.executable, args=["-m", f"mcp_servers.{name}"], env=self.env)
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[name] = session
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()

    async def list_tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for name, s in self._sessions.items():
            for t in (await s.list_tools()).tools:
                out.append(ToolSpec(f"{name}{SEP}{t.name}", t.description or "", t.input_schema if hasattr(t, "input_schema") else t.inputSchema))
        return out

    async def call_tool(self, name: str, arguments: dict[str, Any], ctx: CallContext) -> ToolResult:
        server_name, _, tool_name = name.partition(SEP)
        s = self._sessions.get(server_name)
        if s is None:
            return ToolResult(f"unknown tool: {name}", is_error=True)
        res = await s.call_tool(tool_name, arguments)
        text = "".join(getattr(c, "text", "") for c in res.content)
        return ToolResult(text, is_error=bool(getattr(res, "is_error", getattr(res, "isError", False))))


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True)
