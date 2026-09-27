"""Start the whole Nightshift demo with one command:  python start.py

Starts the gateway (simulated backends, no docker) and the dashboard, waits until both answer, opens the browser, and stops
both when you press Ctrl+C. Logs go to .run/gateway.log and .run/dashboard.log.

  python start.py                 # start everything and open http://localhost:3001
  python start.py --no-browser    # do not open the browser
  python start.py --fresh         # start with an empty incident history
  python start.py --port 8000 --dashboard-port 3001
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH = ROOT / "dashboard"
LOGS = ROOT / ".run"
IS_WIN = os.name == "nt"


def say(msg: str) -> None:
    print(f"[nightshift] {msg}", flush=True)


def die(msg: str) -> "None":
    print(f"[nightshift] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_http(url: str, timeout: float, proc: subprocess.Popen, name: str) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            die(f"{name} exited early (code {proc.returncode}). See the log in {LOGS}.")
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    die(f"{name} did not become ready within {int(timeout)}s. See the log in {LOGS}.")


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WIN:  # npm spawns children: kill the whole tree
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.kill()


def main() -> None:
    ap = argparse.ArgumentParser(description="Start the Nightshift gateway + dashboard.")
    ap.add_argument("--port", type=int, default=8000, help="gateway port")
    ap.add_argument("--dashboard-port", type=int, default=3001)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="delete the demo incident history first")
    a = ap.parse_args()
    if IS_WIN:  # closing the console window / Ctrl+Break should also clean up the children
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    if sys.version_info < (3, 11):
        die(f"Python 3.11+ is required (found {sys.version.split()[0]}).")
    try:
        import fastapi, uvicorn, sse_starlette  # noqa: F401
    except ImportError:
        die('Python dependencies are missing. Run:  pip install -e ".[dev]"')
    npm = shutil.which("npm")
    if not npm:
        die("Node.js / npm was not found. Install Node 18+ from https://nodejs.org and re-run.")
    for port, name in ((a.port, "gateway"), (a.dashboard_port, "dashboard")):
        if port_busy(port):
            die(f"port {port} is already in use (is Nightshift already running?). Stop it, or pick another port with --port / --dashboard-port.")

    if not (DASH / "node_modules").exists():
        say("first run: installing dashboard dependencies (about a minute)...")
        if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=DASH).returncode != 0:
            die("npm install failed.")
    if a.fresh:
        (ROOT / "nightshift-demo.db").unlink(missing_ok=True)

    LOGS.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "GATEWAY_INTERNAL_URL": f"http://localhost:{a.port}"}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0
    gateway = dashboard = None
    logs = []
    try:
        say("starting the gateway (simulated backends, offline policy)...")
        gl = open(LOGS / "gateway.log", "w", encoding="utf8")
        logs.append(gl)
        gateway = subprocess.Popen([sys.executable, "-m", "gateway.demo", "--port", str(a.port)], cwd=ROOT, env=env, stdout=gl, stderr=subprocess.STDOUT,
                                   creationflags=flags, start_new_session=not IS_WIN)
        wait_http(f"http://127.0.0.1:{a.port}/healthz", 60, gateway, "gateway")

        say("starting the dashboard...")
        dl = open(LOGS / "dashboard.log", "w", encoding="utf8")
        logs.append(dl)
        dashboard = subprocess.Popen([npm, "run", "dev", "--", "-p", str(a.dashboard_port)], cwd=DASH, env=env, stdout=dl, stderr=subprocess.STDOUT,
                                     creationflags=flags, start_new_session=not IS_WIN)
        wait_http(f"http://localhost:{a.dashboard_port}", 120, dashboard, "dashboard")

        real = "on" if _has_openai_key() else "off (add OPENAI_API_KEY to .env to enable it)"
        url = f"http://localhost:{a.dashboard_port}"
        print(f"\n  Nightshift is running\n  Dashboard  {url}\n  Gateway    http://localhost:{a.port}\n  Real-LLM option: {real}\n"
              f"  Logs       {LOGS}\n\n  Press Ctrl+C to stop everything.\n", flush=True)
        if not a.no_browser:
            webbrowser.open(url)
        while True:
            for name, p in (("gateway", gateway), ("dashboard", dashboard)):
                if p.poll() is not None:
                    die(f"{name} stopped unexpectedly (code {p.returncode}). See {LOGS}.")
            time.sleep(1)
    except KeyboardInterrupt:
        say("stopping...")
    finally:
        stop(dashboard)
        stop(gateway)
        for f in logs:
            f.close()


def _has_openai_key() -> bool:
    if os.environ.get("OPENAI_API_KEY"):
        return True
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf8").splitlines():
            if line.startswith("OPENAI_API_KEY=") and line.split("=", 1)[1].split("#")[0].strip():
                return True
    return False


if __name__ == "__main__":
    main()
