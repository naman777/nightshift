'use client';
import { useState } from 'react';
import { Highlight, PageHead, Segmented } from '@/components/ui';
import { BenchConfig, BenchSummary, getJSON } from '@/lib/api';
import { usePoll } from '@/lib/usePoll';

const LABEL: Record<string, string> = {
  'naive-recent-change': 'Naive: blame last change', 'naive-top-errors': 'Naive: blame noisiest service', single: 'Single agent',
  multi: 'Multi-agent', 'multi-routed': 'Multi-agent + model routing', 'multi-nocite': 'Multi-agent, no citation rule (ablation)',
  'multi-memory': 'Multi-agent + incident memory',
};
const SPLITS: [string, string][] = [
  ['heldout', 'Held-out (15)'], ['dev', 'Development (25)'], ['hard', 'Hard stress set (10)'],
];
const pct = (x: number | null | undefined) => (x == null ? 'n/a' : `${Math.round(x * 100)}%`);
const HEADERS = ['Configuration', 'Accuracy', 'Top-3', 'Remediation', 'Unsafe', 'Grounding', 'Red-herring', 'Cost', 'Time p50/p95 (modelled)'];

type Payload = BenchSummary & { splits?: Record<string, BenchSummary> };

export default function Benchmark() {
  const { data } = usePoll(() => getJSON<Payload>('/bench/results'), 10000);
  const available = SPLITS.filter(([k]) => data?.splits?.[k]);
  const [picked, setPicked] = useState<string | null>(null);
  const split = picked && data?.splits?.[picked] ? picked : available[0]?.[0] ?? null;
  const summary: BenchSummary | undefined = split ? data?.splits?.[split] : data ?? undefined;
  const cfgs = Object.entries(summary?.configs ?? {}) as [string, BenchConfig][];
  return (
    <div className="space-y-8">
      <PageHead title="Benchmark">
        Accuracy of each configuration across the 50 simulated incidents. <Highlight>Held-out scenarios</Highlight> are never tuned against.
      </PageHead>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        {summary?.policy ? <p className="text-sm tone-warn">Produced by: {summary.policy}</p> : <span />}
        {available.length > 1 && split && <Segmented label="Scenario split" value={split} onChange={setPicked} options={available.map(([k, label]) => ({ value: k, label }))} />}
      </div>
      {data && cfgs.length === 0 && <p className="text-muted-foreground sm:text-center">No results yet. Run <code>make bench</code>.</p>}
      {cfgs.length > 0 && (
        <section className="card space-y-3 p-5">
          <h2 className="font-montserrat text-base font-semibold">Root-cause accuracy</h2>
          {cfgs.map(([name, c]) => (
            <div key={name} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-sm sm:grid-cols-[18rem_1fr_3rem]">
              <div className="text-muted-foreground">{LABEL[name] ?? name}</div>
              <div className="col-span-2 row-start-2 h-2 overflow-hidden rounded-full bg-black/[0.08] sm:col-span-1 sm:row-start-auto dark:bg-white/10">
                <div className={`h-full rounded-full ${name.startsWith('naive') ? 'bg-neutral-400 dark:bg-neutral-600' : 'bg-primary'}`} style={{ width: `${c.root_cause_accuracy * 100}%` }} />
              </div>
              <div className="text-right font-montserrat font-semibold tabular-nums">{pct(c.root_cause_accuracy)}</div>
            </div>
          ))}
        </section>
      )}
      {cfgs.length > 0 && (
        <div className="card overflow-x-auto"><table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>{HEADERS.map((h) => <th key={h} className="whitespace-nowrap p-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody className="tabular-nums">
            {cfgs.map(([name, c]) => (
              <tr key={name} className="border-t">
                <td className="whitespace-nowrap p-3 font-medium">{LABEL[name] ?? name}</td>
                <td className="whitespace-nowrap p-3">{pct(c.root_cause_accuracy)} ±{Math.round(c.accuracy_std * 100)}</td>
                <td className="p-3">{pct(c.top3_accuracy)}</td>
                <td className="p-3">{pct(c.remediation_quality)}</td>
                <td className="p-3">{pct(c.unsafe_action_rate)}</td>
                <td className="p-3">{pct(c.evidence_grounding)}</td>
                <td className="p-3">{pct(c.red_herring_accuracy)}</td>
                <td className="p-3">${c.cost_usd.mean.toFixed(3)}</td>
                <td className="whitespace-nowrap p-3">{c.modeled_time_s.p50.toFixed(1)}s / {c.modeled_time_s.p95.toFixed(1)}s</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
