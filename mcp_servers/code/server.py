from __future__ import annotations

from typing import Any

from ..base import Server, schema
from .backend import CodeBackend


def build(backend: CodeBackend) -> Server:
    srv = Server("code", backend)

    @srv.tool("read_file", "Read a source file (line-numbered). Use start/end to page through large files.",
              schema({"path": ("string", "path relative to repo root"), "start": ("number", "first line, default 1"),
                      "end": ("number", "last line, default 200")}, ["path"]))
    async def read_file(b: CodeBackend, path: str, start: int = 1, end: int = 200) -> Any:
        return await b.read_file(path, int(start), int(end))

    @srv.tool("grep", "Regex search across the source tree.",
              schema({"pattern": ("string", "regex"), "path": ("string", "optional subdirectory"), "limit": ("number", "default 20")}, ["pattern"]))
    async def grep(b: CodeBackend, pattern: str, path: str | None = None, limit: int = 20) -> Any:
        return {"matches": await b.grep(pattern, path, int(limit))}

    @srv.tool("run_tests", "Run the project's test suite in a sandbox and return pass/fail plus output tail.",
              schema({"target": ("string", "allow-listed test command, e.g. 'go test ./...'")}, ["target"]))
    async def run_tests(b: CodeBackend, target: str = "go test ./...") -> Any:
        return await b.run_tests(target)

    return srv
