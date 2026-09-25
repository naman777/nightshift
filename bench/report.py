"""Renders results: markdown table (for README / docs), SVG chart, and README injection.  python -m bench.report"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
LABELS = {"naive-recent-change": "Naive: blame last change", "naive-top-errors": "Naive: blame noisiest service", "single": "Single agent (all tools)",
          "multi": "Multi-agent", "multi-routed": "Multi-agent + model routing", "multi-nocite": "Multi-agent, no citation rule (ablation)"}


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def render_markdown(summary: dict) -> str:
    cfgs = summary["configs"]
    lines = [f"Split: `{summary['split']}` · {summary['scenarios']} scenarios x {summary['repeats']} repeat(s) · prompts `{summary['prompt_version']}` · "
             f"{summary.get('policy', '')}", "",
             "| Configuration | Root-cause acc. | Top-3 | Judge | Remediation | Unsafe-action rate | Grounding | Red-herring acc. | Cost / incident | Time to dx (modelled p50 / p95) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, c in cfgs.items():
        lines.append(f"| {LABELS.get(name, name)} | {pct(c['root_cause_accuracy'])} ± {c['accuracy_std'] * 100:.0f} | {pct(c['top3_accuracy'])} | {pct(c['judge_accuracy'])} | "
                     f"{pct(c['remediation_quality'])} | {pct(c['unsafe_action_rate'])} | {pct(c['evidence_grounding'])} | {pct(c['red_herring_accuracy'])} | "
                     f"${c['cost_usd']['mean']:.3f} | {c['modeled_time_s']['p50']:.1f}s / {c['modeled_time_s']['p95']:.1f}s |")
    inv = sum(c["invalid"] for c in cfgs.values())
    lines += ["", f"Invalid scenarios (expected alert never fired): {inv}."]
    return "\n".join(lines)


def render_svg(summary: dict) -> str:
    cfgs = summary["configs"]
    w, h, pad, bar = 640, 60 + 34 * len(cfgs), 210, 22
    rows = []
    for i, (name, c) in enumerate(cfgs.items()):
        y = 40 + i * 34
        v = c["root_cause_accuracy"]
        fill = "#3b82f6" if not name.startswith("naive") else "#9ca3af"
        rows.append(f'<text x="8" y="{y + 15}" font-size="12" fill="#374151">{LABELS.get(name, name)}</text>'
                    f'<rect x="{pad}" y="{y}" width="{max(2, (w - pad - 60) * v):.0f}" height="{bar}" rx="3" fill="{fill}"/>'
                    f'<text x="{pad + max(2, (w - pad - 60) * v) + 6:.0f}" y="{y + 15}" font-size="12" fill="#111827">{v * 100:.0f}%</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="sans-serif">'
            f'<rect width="100%" height="100%" fill="#ffffff"/><text x="8" y="22" font-size="14" font-weight="bold" fill="#111827">Root-cause accuracy '
            f'({summary["split"]} split, {summary["scenarios"]} scenarios)</text>{"".join(rows)}</svg>')


def inject_readme(table: str) -> bool:
    if not README.exists():
        return False
    text = README.read_text(encoding="utf8")
    new = re.sub(r"<!-- BENCH:START -->.*?<!-- BENCH:END -->", f"<!-- BENCH:START -->\n{table}\n<!-- BENCH:END -->", text, flags=re.S)
    if new == text:
        return False
    README.write_text(new, encoding="utf8")
    return True


def main() -> None:
    summary = json.loads((ROOT / "bench" / "results" / "summary.json").read_text(encoding="utf8"))
    table = render_markdown(summary)
    (ROOT / "bench" / "results" / "results.md").write_text(table + "\n", encoding="utf8")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "results.svg").write_text(render_svg(summary), encoding="utf8")
    print(table)
    print("README updated" if inject_readme(table) else "README markers not found; wrote bench/results/results.md")


if __name__ == "__main__":
    main()
