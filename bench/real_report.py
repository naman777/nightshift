"""Render bench/results/real-llm/summary-*.json as a markdown table (and optionally into README between REAL:START/END).

  python -m bench.real_report            # print
  python -m bench.real_report --write    # rewrite the README block
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DIR = Path(__file__).parent / "results" / "real-llm"
README = Path(__file__).resolve().parent.parent / "README.md"
ORDER = ["smoke", "dev", "heldout", "hard"]


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def render() -> str:
    files = sorted(DIR.glob("summary-*.json"), key=lambda p: (ORDER.index(json.loads(p.read_text("utf8"))["split"]), p.name))
    rows = ["| Split | Prompts | Config | Runs | Root-cause acc. | Top-3 | Service | Remediation | Unsafe | Grounding | Red-herring acc. | Cost / incident* | Wall time |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    model = ""
    for f in files:
        s = json.loads(f.read_text("utf8"))
        model = s["model"]
        for name, m in s["configs"].items():
            cfg = name.split("@")[0]
            rows.append(f"| {s['split']} ({s['scenarios']} sc. x {s['repeats']}) | {s.get('prompt_version', 'v1')} | {cfg} | {m['runs']} | "
                        f"{pct(m['root_cause_accuracy'])} | {pct(m['top3_accuracy'])} | {pct(m['service_accuracy'])} | {pct(m['remediation_quality'])} | "
                        f"{pct(m['unsafe_action_rate'])} | {pct(m['evidence_grounding'])} | {pct(m['red_herring_accuracy'])} | "
                        f"${m['cost_usd']['mean']:.3f} | {m['wall_time_s']['mean']:.0f}s |")
    head = f"Real model: `{model}` (same simulated worlds, scoring and benchmark mode as the offline table; invalid runs excluded).\n\n"
    foot = "\n\\*Cost is computed from token counts at the model's standard short-context rates. Wall time is real, not modelled.\n"
    return head + "\n".join(rows) + "\n" + foot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    block = render()
    if not a.write:
        print(block)
        return
    text = README.read_text("utf8")
    start, end = "<!-- REAL:START -->", "<!-- REAL:END -->"
    if start not in text:
        raise SystemExit("README has no REAL:START/END markers")
    pre, rest = text.split(start, 1)
    _, post = rest.split(end, 1)
    README.write_text(pre + start + "\n" + block + end + post, encoding="utf8")
    print("README updated")


if __name__ == "__main__":
    main()
