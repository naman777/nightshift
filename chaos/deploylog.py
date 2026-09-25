"""Deploy history as an append-only JSONL (target/deploys.jsonl). The change agent's `recent_deploys` tool reads it."""
from __future__ import annotations

import json
import time
from pathlib import Path

from chaos.gitcfg import ROOT

DEFAULT = ROOT / "target" / "deploys.jsonl"


def record(service: str, sha: str, message: str, author: str = "dana", ts: float | None = None, path: Path = DEFAULT) -> dict:
    row = {"ts": int(ts or time.time()), "service": service, "sha": sha, "author": author, "message": message}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def read(path: Path = DEFAULT) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()] if path.exists() else []
