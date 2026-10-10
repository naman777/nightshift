'use client';
import { ArrowUpRight } from 'lucide-react';
import { useState } from 'react';
import { Chip } from '@/components/ui';
import { Report, post } from '@/lib/api';
import { pct } from '@/lib/derive';

const TIER: Record<string, ['ok' | 'warn' | 'bad', string]> = {
  read_only: ['ok', 'Read-only: runs without asking.'],
  reversible: ['warn', 'Reversible: needs one human approval.'],
  destructive: ['bad', 'Destructive: needs typed confirmation and a reason.'],
};

export default function ReportCard({ id, report, status }: { id: string; report: Report; status: string }) {
  const [typed, setTyped] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const a = report.proposed_action;
  const waiting = status === 'awaiting_approval';
  const destructive = a?.tier === 'destructive';
  const act = async (kind: 'approve' | 'reject') => {
    setBusy(true);
    setErr('');
    try {
      await post(`/incidents/${id}/${kind}`, { user: 'dashboard', confirmation: typed, reason });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const tier = a ? TIER[a.tier] : null;
  return (
    <section className="card rise space-y-5 p-5">
      <div>
        <div className="label">Root cause</div>
        <h2 className="mt-1 text-xl font-medium leading-snug sm:text-2xl">{report.root_cause}</h2>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
          <Chip>{report.service}</Chip>
          <Chip>{report.category.replace('_', ' ')}</Chip>
          <span className="flex items-center gap-2 text-muted-foreground">
            confidence
            <span className="h-1.5 w-24 overflow-hidden rounded-full bg-black/[0.08] dark:bg-white/10" role="progressbar" aria-label="confidence" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(report.confidence * 100)}>
              <span className="block h-full rounded-full bg-primary transition-[width] duration-500 ease-out" style={{ width: pct(report.confidence) }} />
            </span>
            <span className="font-semibold text-foreground">{pct(report.confidence)}</span>
          </span>
          <span className="text-faint">cited evidence: {report.evidence.join(', ') || 'none'}</span>
        </div>
        {report.degraded && <p className="mt-2 text-xs tone-warn">Degraded result (budget or fallback). Treat with caution.</p>}
      </div>

      {report.ruled_out.length > 0 && (
        <div>
          <div className="label mb-1.5">Ruled out</div>
          <ul className="space-y-1 text-sm">
            {report.ruled_out.map((r, i) => (
              <li key={i}>
                <span className="text-muted-foreground line-through">{r.hypothesis}</span> <span className="text-[11px] text-faint">{r.evidence.join(', ')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-faint">
        <span>${report.usage.cost_usd.toFixed(3)} est. cost</span>
        <span>{report.usage.llm_calls} model calls</span>
        <span>{report.usage.tool_calls} tool calls</span>
        <span>{report.rounds} round{report.rounds === 1 ? '' : 's'}</span>
      </div>

      {a && (
        <div className="rounded-lg border p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label">Proposed fix</span>
            <Chip tone={tier?.[0]}>{a.tier.replace('_', ' ')}</Chip>
          </div>
          <code className="mt-2 block break-words text-sm">{a.type} {a.target} {Object.keys(a.params).length ? JSON.stringify(a.params) : ''}</code>
          <p className="mt-1 text-xs text-muted-foreground">{tier?.[1]} The tier comes from the tool, never from the model.</p>
          {waiting && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              {destructive && (
                <>
                  <input className="field" aria-label={`Type CONFIRM ${a.type} to approve`} placeholder={`type: CONFIRM ${a.type}`} value={typed} onChange={(e) => setTyped(e.target.value)} />
                  <input className="field" aria-label="Reason" placeholder="reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                </>
              )}
              <button disabled={busy} onClick={() => act('approve')} className="btn-solid">Approve and run<ArrowUpRight className="-ml-1 size-4" aria-hidden="true" /></button>
              <button disabled={busy} onClick={() => act('reject')} className="btn-outline">Reject</button>
              <span className="text-xs text-faint">No answer in 30 min = rejected.</span>
            </div>
          )}
          {err && <p className="mt-2 text-xs tone-bad">{err}</p>}
        </div>
      )}
    </section>
  );
}
