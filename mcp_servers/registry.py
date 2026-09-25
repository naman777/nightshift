from __future__ import annotations

from typing import Any

from .base import Server
from .changes.server import build as build_changes
from .code.server import build as build_code
from .logs.server import build as build_logs
from .metrics.server import build as build_metrics
from .runtime.server import build as build_runtime

READ_SERVERS = ("metrics", "logs", "changes", "code")


def build_servers(backends: dict[str, Any], include_runtime: bool = True) -> list[Server]:
    servers = [build_metrics(backends["metrics"]), build_logs(backends["logs"]),
               build_changes(backends["changes"]), build_code(backends["code"])]
    if include_runtime and "runtime" in backends:
        servers.append(build_runtime(backends["runtime"]))
    return servers
