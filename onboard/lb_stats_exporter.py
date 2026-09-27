"""Tiny Prometheus exporter for the C++ balancer's own JSON stats page (`GET /stats` on listen_port+1). Stdlib only.

    LB_STATS_TARGETS="lb=http://127.0.0.1:8081/stats,lb-sandbox=http://127.0.0.1:8091/stats" python3 lb_stats_exporter.py [port]

Exposes lb_stats_up{service}, lb_backend_connections{service,backend}, lb_backend_healthy{service,backend}. This is the adapter pattern for any
app with a JSON stats endpoint; it fails soft (lb_stats_up 0) when the endpoint is wedged, which is itself a signal.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGETS = dict(t.split("=", 1) for t in os.environ.get("LB_STATS_TARGETS", "").split(",") if "=" in t)


def scrape_one(item: tuple[str, str]) -> list[str]:
    service, url = item
    lines = []
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            stats = json.loads(r.read())
        lines.append(f'lb_stats_up{{service="{service}"}} 1')
        for b in stats.get("backends", []):
            lbl = f'service="{service}",backend="{b["port"]}"'
            lines.append(f"lb_backend_connections{{{lbl}}} {b['connections']}")
            lines.append(f"lb_backend_healthy{{{lbl}}} {1 if b['healthy'] else 0}")
    except Exception:
        lines.append(f'lb_stats_up{{service="{service}"}} 0')
    return lines


def render() -> str:
    with ThreadPoolExecutor(max_workers=max(1, len(TARGETS))) as ex:  # scrape targets in parallel: one wedged endpoint must not delay the others
        parts = list(ex.map(scrape_one, TARGETS.items()))
    return "\n".join(line for p in parts for line in p) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 9120), Handler).serve_forever()
