'use client';
import { useState } from 'react';
import { Report, post } from '@/lib/api';
import { pct } from '@/lib/derive';

const TIER: Record<string, [string, string]> = {
  read_only: ['bg-emerald-500/15 text-emerald-300', 'Read-only: runs without asking.'],
  reversible: ['bg-amber-500/15 text-amber-300', 'Reversible: needs one human approval.'],
  destructive: ['bg-rose-500/15 text-rose-300', 'Destructive: needs typed confirmation and a reason.'],
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
  const tier = a ? TIER[a.tier] ?? ['bg-slate-700 text-slate-200', ''] : null;
  return (
    <section className="card rise space-y-5 p-5">
      <div>
        <div className="label">Root cause</div>
        <h2 className="mt-1 text-xl font-semibold leading-snug">{report.root_cause}</h2>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="chip bg-white/10 text-slate-200">{report.service}</span>
          <span className="chip bg-white/10 text-slate-200">{report.category.replace('_', ' ')}</span>
          <span className="flex items-center gap-2 text-slate-400">
            confidence
            <span className="h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
              <span className="block h-full bg-indigo-400" style={{ width: pct(report.confidence) }} />
            </span>
            {pct(report.confidence)}
          </span>
          <span className="text-slate-500">cited evidence: {report.evidence.join(', ') || 'none'}</span>
        </div>
        {report.degraded && <p className="mt-2 text-xs text-amber-300">Degraded result (budget or fallback). Treat with caution.</p>}
      </div>

      {report.ruled_out.length > 0 && (
        <div>
          <div className="label mb-1.5">Ruled out</div>
          <ul className="space-y-1 text-sm text-slate-300">
            {report.ruled_out.map((r, i) => (
              <li key={i}>
                <span className="text-slate-500 line-through">{r.hypothesis}</span> <span className="text-[11px] text-slate-600">{r.evidence.join(', ')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
        <span>${report.usage.cost_usd.toFixed(3)} est. cost</span>
        <span>{report.usage.llm_calls} model calls</span>
        <span>{report.usage.tool_calls} tool calls</span>
        <span>{report.rounds} round{report.rounds === 1 ? '' : 's'}</span>
      </div>

      {a && tier && (
        <div className="rounded-lg border border-white/10 bg-black/20 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label">Proposed fix</span>
            <span className={`chip ${tier[0]}`}>{a.tier.replace('_', ' ')}</span>
          </div>
          <code className="mt-2 block text-sm">{a.type} {a.target} {Object.keys(a.params).length ? JSON.stringify(a.params) : ''}</code>
          <p className="mt-1 text-xs text-slate-500">{tier[1]} The tier comes from the tool, never from the model.</p>
          {waiting && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {destructive && (
                <>
                  <input className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm" placeholder={`type: CONFIRM ${a.type}`} value={typed} onChange={(e) => setTyped(e.target.value)} />
                  <input className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm" placeholder="reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                </>
              )}
              <button disabled={busy} onClick={() => act('approve')} className="btn bg-emerald-500 text-emerald-950 hover:bg-emerald-400">Approve and run</button>
              <button disabled={busy} onClick={() => act('reject')} className="btn-ghost">Reject</button>
              <span className="text-xs text-slate-500">No answer in 30 min = rejected.</span>
            </div>
          )}
          {err && <p className="mt-2 text-xs text-red-300">{err}</p>}
        </div>
      )}
    </section>
  );
}
