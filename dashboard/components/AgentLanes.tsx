import { Step } from '@/lib/api';

const LANES = ['commander', 'metrics', 'logs', 'changes', 'code', 'remediation', 'single'];
const ICON: Record<string, string> = { llm: 'think', tool: 'tool', finding: 'done' };

function line(r: Step): string {
  if (r.kind === 'llm') return r.detail.slice(0, 70) || r.name;
  if (r.kind === 'finding') return `${r.name}: ${r.detail.slice(0, 90)}`;
  return `${r.name}  ${r.duration_ms}ms`;
}

export default function AgentLanes({ steps }: { steps: Step[] }) {
  const by = new Map<string, Step[]>();
  steps.forEach((s) => by.set(s.agent, [...(by.get(s.agent) ?? []), s]));
  const lanes = LANES.filter((l) => by.has(l));
  if (lanes.length === 0) return <p className="text-slate-500 text-sm">Waiting for the first agent step...</p>;
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(lanes.length, 4)}, minmax(0, 1fr))` }}>
      {lanes.map((l) => {
        const rows = by.get(l)!;
        const done = rows.some((r) => r.kind === 'finding');
        return (
          <div key={l} className="border border-slate-800 rounded p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium capitalize">{l}</span>
              <span className={`text-xs ${done ? 'text-emerald-400' : 'text-blue-300 animate-pulse'}`}>{done ? 'finished' : 'working'}</span>
            </div>
            <ol className="space-y-1 text-xs font-mono max-h-64 overflow-auto">
              {rows.map((r) => (
                <li key={r.seq} className="text-slate-300">
                  <span className="text-slate-500">{ICON[r.kind] ?? r.kind}</span> {line(r)}
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </div>
  );
}
