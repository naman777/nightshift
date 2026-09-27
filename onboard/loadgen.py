"""Light concurrent HTTP load for the sandbox balancer, so faults have user-visible effects (and the logs have traffic).

    python3 loadgen.py http://127.0.0.1:8090/ [workers=6] [timeout_s=3]
"""
from __future__ import annotations

import sys
import threading
import time
import urllib.request

url = sys.argv[1]
workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 3


def worker() -> None:
    while True:
        try:
            urllib.request.urlopen(url, timeout=timeout).read()
        except Exception:
            pass
        time.sleep(0.15)


for _ in range(workers):
    threading.Thread(target=worker, daemon=True).start()
while True:
    time.sleep(3600)
