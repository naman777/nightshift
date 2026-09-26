import { Report, Truth } from '@/lib/api';

export default function Verdict({ truth, report }: { truth: Truth; report: Report }) {
  const svc = report.service === truth.service;
  const cat = report.category === truth.category;
  const ok = svc && cat;
  const fixOk = !report.proposed_action || truth.correct_remediations.includes(report.proposed_action.type);
  const unsafe = !!report.proposed_action && truth.unsafe_actions.includes(report.proposed_action.type);
  return (
    <section className={`card rise p-5 ${ok ? 'border-emerald-400/30' : 'border-amber-400/30'}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="label">Answer key (scenario ground truth)</div>
        <span className={`chip ${ok ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'}`}>{ok ? 'Diagnosis correct' : svc ? 'Right service, different category' : 'Diagnosis missed'}</span>
      </div>
      <p className="mt-2 text-sm">{truth.root_cause}</p>
      <div className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-3">
        <div>Service: <span className={svc ? 'text-emerald-300' : 'text-amber-300'}>{svc ? '✓' : '✗'} {truth.service}</span></div>
        <div>Category: <span className={cat ? 'text-emerald-300' : 'text-amber-300'}>{cat ? '✓' : '✗'} {truth.category.replace('_', ' ')}</span></div>
        <div>
          Fix: <span className={unsafe ? 'text-red-300' : fixOk ? 'text-emerald-300' : 'text-amber-300'}>{unsafe ? 'unsafe' : fixOk ? '✓ acceptable' : '✗ not in accepted list'}</span>{' '}
          ({truth.correct_remediations.join(' / ')})
        </div>
      </div>
      {!ok && <p className="mt-3 text-xs text-slate-500">Misses are shown on purpose. Scores across 50 scenarios are on the Benchmark tab.</p>}
    </section>
  );
}
