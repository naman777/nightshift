import { LiveDot } from '@/components/ui';
import { Step } from '@/lib/api';
import { AGENT, AgentState, fmtTime, toolVerb } from '@/lib/derive';

function stepLine(s: Step): string {
  if (s.kind === 'tool') return `${toolVerb(s.name)}  (${s.duration_ms} ms)`;
  if (s.kind === 'llm') return s.detail ? `thinks: ${s.detail.slice(0, 90)}` : 'thinks';
  return `${s.name}: ${s.detail.slice(0, 110)}`;
}

function State({ state }: { state: AgentState['state'] }) {
  if (state === 'working') return <span className="flex items-center gap-1.5 text-[11px] font-medium text-foreground"><LiveDot />working</span>;
  if (state === 'done') return <span className="tone-ok text-[11px] font-medium">done</span>;
  return <span className="text-[11px] text-faint">waiting</span>;
}

export default function Investigators({ agents }: { agents: AgentState[] }) {
  if (agents.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 text-xl font-medium">Agents</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => (
          <details key={a.id} className="card group p-4">
            <summary className="cursor-pointer list-none outline-none focus-visible:ring-[3px] focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
              <div className="flex items-center justify-between gap-2">
                <span className="font-montserrat text-base font-semibold leading-snug">{AGENT[a.id]?.label ?? a.id}</span>
                <State state={a.state} />
              </div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{a.state === 'done' && a.summary ? a.summary : a.activity}</p>
              <p className="mt-2 text-[11px] text-faint">{a.tools} tool call{a.tools === 1 ? '' : 's'} · {a.llm} model call{a.llm === 1 ? '' : 's'} · <span className="group-open:hidden">show steps</span><span className="hidden group-open:inline">hide steps</span></p>
            </summary>
            <ol className="mt-3 max-h-56 space-y-1 overflow-auto border-t pt-3 font-mono text-[11px] text-muted-foreground">
              {a.steps.map((s) => <li key={s.seq}><span className="text-faint">{fmtTime(s.ts)}</span> {stepLine(s)}</li>)}
            </ol>
          </details>
        ))}
      </div>
    </section>
  );
}
