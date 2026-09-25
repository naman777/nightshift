'use client';
import { useState } from 'react';
import { Report, post } from '@/lib/api';

export default function ReportCard({ id, report, status }: { id: string; report: Report; status: string }) {
  const [typed, setTyped] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const a = report.proposed_action;
  const destructive = a?.tier === 'destructive';
  const waiting = status === 'awaiting_approval';
  const act = async (kind: 'approve' | 'reject') => {
    setBusy(true);
    try {
      await post(`/incidents/${id}/${kind}`, { user: 'dashboard', confirmation: typed, reason });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="border border-slate-800 rounded p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">Root cause</div>
          <div className="text-lg font-medium">{report.root_cause}</div>
          <div className="text-sm text-slate-400 mt-1">
            <code>{report.service}</code> · {report.category} · confidence {(report.confidence * 100).toFixed(0)}% · evidence {report.evidence.join(', ')}
          </div>
        </div>
        <div className="text-right text-xs text-slate-400">
          <div>${report.usage.cost_usd.toFixed(3)} · {report.usage.llm_calls} LLM calls</div>
          <div>{report.usage.tool_calls} tool calls · {report.rounds} round(s)</div>
          {report.degraded && <div className="text-amber-400">degraded (budget/fallback)</div>}
        </div>
      </div>
      {report.ruled_out.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">Ruled out</div>
          <ul className="text-sm space-y-1">
            {report.ruled_out.map((r, i) => (
              <li key={i} className="text-slate-300">
                <span className="line-through text-slate-500">{r.hypothesis}</span> <span className="text-xs text-slate-500">({r.evidence.join(', ')})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {a && (
        <div className="border-t border-slate-800 pt-3">
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">Proposed action ({a.tier})</div>
          <code className="text-sm">{a.type} {a.target} {Object.keys(a.params).length ? JSON.stringify(a.params) : ''}</code>
          {waiting && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {destructive && (
                <>
                  <input className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm" placeholder={`type: CONFIRM ${a.type}`} value={typed} onChange={(e) => setTyped(e.target.value)} />
                  <input className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm" placeholder="reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                </>
              )}
              <button disabled={busy} onClick={() => act('approve')} className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-sm disabled:opacity-50">Approve</button>
              <button disabled={busy} onClick={() => act('reject')} className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-sm disabled:opacity-50">Reject</button>
              <span className="text-xs text-slate-500">No response in 30 minutes = rejected.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
