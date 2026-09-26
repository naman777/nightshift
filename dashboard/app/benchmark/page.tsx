'use client';
import { useState } from 'react';
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
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold tracking-tight">Benchmark</h1><p className="mt-1 text-sm text-slate-400">Accuracy of each configuration across the 50 simulated incidents. Held-out scenarios are never tuned against.</p></div>
      {summary?.policy && <p className="text-sm text-amber-300/80">{summary.policy}</p>}
      {available.length > 1 && (
        <div className="flex gap-2">
          {available.map(([k, label]) => (
            <button key={k} onClick={() => setPicked(k)}
              className={`px-3 py-1 rounded text-sm ${k === split ? 'bg-indigo-500' : 'bg-white/5 hover:bg-white/10'}`}>{label}</button>
          ))}
        </div>
      )}
      {cfgs.length === 0 && <p className="text-slate-400">No results yet. Run <code>make bench</code>.</p>}
      <div className="space-y-2">
        {cfgs.map(([name, c]) => (
          <div key={name} className="flex items-center gap-3 text-sm">
            <div className="w-72 text-slate-300">{LABEL[name] ?? name}</div>
            <div className="flex-1 bg-white/5 rounded h-5 overflow-hidden">
              <div className={name.startsWith('naive') ? 'bg-slate-500 h-5' : 'bg-indigo-400 h-5'} style={{ width: `${c.root_cause_accuracy * 100}%` }} />
            </div>
            <div className="w-12 text-right">{pct(c.root_cause_accuracy)}</div>
          </div>
        ))}
      </div>
      {cfgs.length > 0 && (
        <div className="card overflow-x-auto"><table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-500">
            <tr>{HEADERS.map((h) => <th key={h} className="p-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {cfgs.map(([name, c]) => (
              <tr key={name} className="border-t border-white/5">
                <td className="p-2">{LABEL[name] ?? name}</td>
                <td className="p-2">{pct(c.root_cause_accuracy)} ±{Math.round(c.accuracy_std * 100)}</td>
                <td className="p-2">{pct(c.top3_accuracy)}</td>
                <td className="p-2">{pct(c.remediation_quality)}</td>
                <td className="p-2">{pct(c.unsafe_action_rate)}</td>
                <td className="p-2">{pct(c.evidence_grounding)}</td>
                <td className="p-2">{pct(c.red_herring_accuracy)}</td>
                <td className="p-2">${c.cost_usd.mean.toFixed(3)}</td>
                <td className="p-2">{c.modeled_time_s.p50.toFixed(1)}s / {c.modeled_time_s.p95.toFixed(1)}s</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
