import { Chip } from '@/components/ui';
import { Report } from '@/lib/api';
import { AGENT, AgentState, Plan } from '@/lib/derive';

const STATE: Record<string, string> = { idle: 'text-faint', working: 'font-medium text-foreground', done: 'tone-ok font-medium' };
const STATE_LABEL: Record<string, string> = { idle: 'waiting', working: 'working', done: 'done' };

export default function PlanCard({ plan, agents, report, followUps }: { plan: Plan; agents: AgentState[]; report: Report | null; followUps: number }) {
  const state = (a: string) => agents.find((x) => x.id === a)?.state ?? 'idle';
  const leading = (h: Plan['hypotheses'][number]) => !!report && h.category === report.category && (!h.service || h.service === report.service);
  return (
    <section className="card rise p-5">
      <h2 className="text-xl font-medium">The plan</h2>
      <div className="mt-4 grid gap-6 md:grid-cols-2">
        <div>
          <div className="label mb-2">Hypotheses to test</div>
          <ul className="space-y-2">
            {plan.hypotheses.map((h) => (
              <li key={h.id} className="rounded-lg border px-3 py-2 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <span>{h.text}</span>
                  {leading(h) && <Chip tone="ok" className="shrink-0">leading</Chip>}
                </div>
                {(h.service || h.category !== 'unknown') && (
                  <div className="mt-1 text-[11px] text-faint">{[h.service, h.category.replace('_', ' ')].filter(Boolean).join(' · ')}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="label mb-2">Who checks what</div>
          <ul className="space-y-2">
            {plan.assignments.map((a, i) => (
              <li key={i} className="rounded-lg border px-3 py-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{AGENT[a.agent]?.label ?? a.agent}</span>
                  <span className={`text-[11px] ${STATE[state(a.agent)]}`}>{STATE_LABEL[state(a.agent)]}</span>
                </div>
                <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{a.question.replace(/^(Investigate alert \S+ on \S+|Alert on \S+)\.\s*/, '')}</div>
              </li>
            ))}
          </ul>
          {followUps > 0 && <p className="mt-2 text-xs tone-warn">The commander asked for {followUps} follow-up round{followUps > 1 ? 's' : ''}.</p>}
        </div>
      </div>
    </section>
  );
}
