from __future__ import annotations

import pytest

from agents.core.db import Database
from agents.core.evidence import EvidenceBoard
from agents.core.models import LLMResponse, Message, ToolCall


@pytest.fixture(autouse=True)
def _dev_auth(monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_ALLOW_INSECURE", "1")  # tests exercise the gate explicitly where they need it


@pytest.fixture
def db():
    d = Database.memory()
    yield d
    d.close()


@pytest.fixture
def board(db):
    b = EvidenceBoard(db)
    b.open_incident("inc-1", "fp-1")
    return b


def script(*responses: LLMResponse):
    """Responder that replays a fixed list of responses (last one repeats)."""
    it = iter(responses)
    last: list[LLMResponse] = []

    def responder(system: str, messages: list[Message], tools: list[dict], model: str) -> LLMResponse:
        try:
            last[:] = [next(it)]
        except StopIteration:
            pass
        r = last[0]
        return r.model_copy(deep=True)

    return responder


def call(name: str, cid: str = "t1", **args) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=cid, name=name, arguments=args)])
