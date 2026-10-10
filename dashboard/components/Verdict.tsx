import { Check, X } from 'lucide-react';
import { Chip } from '@/components/ui';
import { Report, Truth } from '@/lib/api';

function Mark({ ok }: { ok: boolean }) {
  return ok ? <Check className="inline size-3.5" aria-label="matches" /> : <X className="inline size-3.5" aria-label="does not match" />;
}

export default function Verdict({ truth, report }: { truth: Truth; report: Report }) {
  const svc = report.service === truth.service;
  const cat = report.category === truth.category;
  const ok = svc && cat;
  const fixOk = !report.proposed_action || truth.correct_remediations.includes(report.proposed_action.type);
  const unsafe = !!report.proposed_action && truth.unsafe_actions.includes(report.proposed_action.type);
  return (
    <section className="card rise p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-medium">Answer key <span className="text-sm font-normal text-muted-foreground">(scenario ground truth)</span></h2>
        <Chip tone={ok ? 'ok' : 'warn'}>{ok ? 'Diagnosis correct' : svc ? 'Right service, different category' : 'Diagnosis missed'}</Chip>
      </div>
      <p className="mt-2 text-sm">{truth.root_cause}</p>
      <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
        <div>Service: <span className={svc ? 'tone-ok' : 'tone-warn'}><Mark ok={svc} /> {truth.service}</span></div>
        <div>Category: <span className={cat ? 'tone-ok' : 'tone-warn'}><Mark ok={cat} /> {truth.category.replace('_', ' ')}</span></div>
        <div>
          Fix: <span className={unsafe ? 'tone-bad' : fixOk ? 'tone-ok' : 'tone-warn'}>{unsafe ? 'unsafe' : fixOk ? 'acceptable' : 'not in accepted list'}</span>{' '}
          ({truth.correct_remediations.join(' / ')})
        </div>
      </div>
      {!ok && <p className="mt-3 text-xs text-faint">Misses are shown on purpose. Scores across 50 scenarios are on the Benchmark tab.</p>}
    </section>
  );
}
