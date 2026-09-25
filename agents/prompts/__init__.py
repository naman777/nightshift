"""Versioned prompts. Every benchmark run records the prompt version so diffs are attributable."""
from __future__ import annotations

from pathlib import Path

LATEST = "v1"
_ROOT = Path(__file__).parent


def load(role: str, version: str = LATEST) -> str:
    return (_ROOT / version / f"{role}.md").read_text(encoding="utf8")


def versions() -> list[str]:
    return sorted(p.name for p in _ROOT.iterdir() if p.is_dir() and p.name.startswith("v"))
