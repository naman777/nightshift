"""OpenTelemetry spans with a graceful no-op fallback (the SDK exporter is configured by the deployment)."""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

try:  # pragma: no cover - depends on env
    from opentelemetry import trace

    _tracer = trace.get_tracer("nightshift")
except Exception:  # pragma: no cover
    _tracer = None


@contextlib.contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            try:
                s.set_attribute(f"nightshift.{k}", v if isinstance(v, (str, int, float, bool)) else str(v))
            except Exception:
                pass
        yield s
