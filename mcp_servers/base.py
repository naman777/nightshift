"""Minimal MCP server abstraction: declare tools once, serve them in-process or over real MCP stdio."""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agents.core.models import Tier


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    tier: Tier = Tier.READ_ONLY


def schema(props: dict[str, tuple[str, str]], required: list[str] | None = None) -> dict[str, Any]:
    """schema({'query': ('string', 'PromQL')}, ['query'])"""
    return {
        "type": "object",
        "properties": {k: {"type": t, "description": d} for k, (t, d) in props.items()},
        "required": required or [],
    }


@dataclass
class Server:
    name: str
    backend: Any
    tools: dict[str, Tool] = field(default_factory=dict)

    def tool(self, name: str, description: str, input_schema: dict[str, Any], tier: Tier = Tier.READ_ONLY):
        def deco(fn: Callable[..., Awaitable[Any]]):
            self.tools[name] = Tool(name, description, input_schema, fn, tier)
            return fn
        return deco

    async def call(self, tool: Tool, arguments: dict[str, Any]) -> Any:
        return await tool.handler(self.backend, **arguments)

    def serve_stdio(self) -> None:  # pragma: no cover - exercised by tests/test_mcp_stdio.py via subprocess
        """Expose this server over real MCP (stdio). Write tools stay dry-run unless policy says otherwise."""
        import asyncio
        import json

        from mcp.server.mcpserver import MCPServer

        srv = MCPServer(self.name)
        for t in self.tools.values():
            def make(tool: Tool):
                async def fn(**kwargs: Any) -> str:
                    out = await self.call(tool, kwargs)
                    return out if isinstance(out, str) else json.dumps(out, default=str)
                return fn
            fn = make(t)
            srv.add_tool(fn, name=t.name, description=t.description)
        asyncio.run(srv.run_stdio_async())


def positional_ok(fn: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any]:
    """Drop arguments a handler does not accept (models sometimes add extras)."""
    params = inspect.signature(fn).parameters
    if any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return args
    return {k: v for k, v in args.items() if k in params}
