"""Code backend: read-only sandboxed view of a source tree; tests run only from an allow-list."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Protocol

ALLOWED_TEST_CMDS = {"go test ./...": ["go", "test", "./..."], "pytest": ["python", "-m", "pytest", "-q"]}


class CodeBackend(Protocol):
    async def read_file(self, path: str, start: int, end: int) -> dict[str, Any]: ...
    async def grep(self, pattern: str, path: str | None, limit: int) -> list[dict[str, Any]]: ...
    async def run_tests(self, target: str) -> dict[str, Any]: ...


class SandboxError(ValueError):
    pass


class FsCodeBackend:
    def __init__(self, root: str | Path, test_cmd: str = "go test ./..."):
        self.root = Path(root).resolve()
        self.test_cmd = test_cmd

    def _safe(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root not in (p, *p.parents):
            raise SandboxError(f"path escapes sandbox: {rel}")
        return p

    async def read_file(self, path, start, end):
        p = self._safe(path)
        if not p.is_file():
            return {"error": f"no such file: {path}"}
        lines = p.read_text(errors="replace").splitlines()
        s, e = max(1, start), min(len(lines), end)
        return {"path": path, "start": s, "end": e, "total_lines": len(lines),
                "content": "\n".join(f"{i}: {lines[i - 1]}" for i in range(s, e + 1))}

    async def grep(self, pattern, path, limit):
        rx = re.compile(pattern)
        base = self._safe(path or ".")
        out: list[dict[str, Any]] = []
        for f in sorted(base.rglob("*")) if base.is_dir() else [base]:
            if not f.is_file() or f.suffix in (".png", ".db", ".bin") or ".git" in f.parts:
                continue
            for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                if rx.search(line):
                    out.append({"path": str(f.relative_to(self.root)), "line": i, "text": line.strip()[:200]})
                    if len(out) >= limit:
                        return out
        return out

    async def run_tests(self, target):
        cmd = ALLOWED_TEST_CMDS.get(target) or ALLOWED_TEST_CMDS.get(self.test_cmd)
        if not cmd:
            return {"error": f"test command not allow-listed: {target}"}
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=self.root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 120)
        except asyncio.TimeoutError:
            proc.kill()
            return {"passed": False, "output": "timeout"}
        return {"passed": proc.returncode == 0, "output": out.decode(errors="replace")[-3000:]}
