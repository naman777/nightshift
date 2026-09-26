import { Step } from '@/lib/api';
import { AGENT, AgentState, fmtTime, toolVerb } from '@/lib/derive';

const DOT: Record<string, string> = { idle: 'bg-slate-600', working: 'bg-sky-400 animate-pulse', done: 'bg-emerald-400' };

function stepLine(s: Step): string {
  if (s.kind === 'tool') return `${toolVerb(s.name)}  (${s.duration_ms} ms)`;
  if (s.kind === 'llm') return s.detail ? `thinks: ${s.detail.slice(0, 90)}` : 'thinks';
  return `${s.name}: ${s.detail.slice(0, 110)}`;
}

export default function Investigators({ agents }: { agents: AgentState[] }) {
  if (agents.length === 0) return null;
  return (
    <section>
      <div className="label mb-3">Agents</div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => (
          <details key={a.id} className="card group p-4 open:bg-white/[0.05]">
            <summary className="cursor-pointer list-none">
              <div className="flex items-center justify-between">
                <span className="font-medium">{AGENT[a.id]?.label ?? a.id}</span>
                <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><span className={`h-2 w-2 rounded-full ${DOT[a.state]}`} />{a.state === 'idle' ? 'waiting' : a.state}</span>
              </div>
              <p className="mt-1 text-xs text-slate-400">{a.state === 'done' && a.summary ? a.summary : a.activity}</p>
              <p className="mt-2 text-[11px] text-slate-600">{a.tools} tool call{a.tools === 1 ? '' : 's'} · {a.llm} model call{a.llm === 1 ? '' : 's'} · click for detail</p>
            </summary>
            <ol className="mt-3 max-h-56 space-y-1 overflow-auto border-t border-white/10 pt-3 font-mono text-[11px] text-slate-400">
              {a.steps.map((s) => <li key={s.seq}><span className="text-slate-600">{fmtTime(s.ts)}</span> {stepLine(s)}</li>)}
            </ol>
          </details>
        ))}
      </div>
    </section>
  );
}
