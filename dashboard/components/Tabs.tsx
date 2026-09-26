'use client';
import { useState } from 'react';
import { Audit, Evidence, Step } from '@/lib/api';
import { AGENT, cleanClaim, fmtTime, pct, toolVerb } from '@/lib/derive';

const DEC: Record<string, string> = { allowed: 'text-emerald-300', blocked: 'text-red-300' };

function logLine(s: Step): string {
  if (s.kind === 'tool') return `${toolVerb(s.name)} · ${s.duration_ms} ms`;
  if (s.kind === 'llm') return `model call (${s.name})${s.duration_ms ? ` · ${s.duration_ms} ms` : ''}`;
  if (s.kind === 'plan') return 'published the plan';
  if (s.kind === 'decision') return `decision: ${s.name}`;
  return `finished: ${s.name}`;
}

export default function Tabs({ evidence, audit, steps }: { evidence: Evidence[]; audit: Audit[]; steps: Step[] }) {
  const [tab, setTab] = useState<'evidence' | 'audit' | 'log'>('evidence');
  const blocked = audit.filter((a) => a.decision === 'blocked').length;
  const t0 = steps[0]?.ts ?? 0;
  const items = [
    ['evidence', `Evidence (${evidence.length})`],
    ['audit', `Safety audit (${audit.length})`],
    ['log', `Activity log (${steps.length})`],
  ] as const;
  return (
    <section>
      <div className="mb-3 flex gap-1 border-b border-white/10">
        {items.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${tab === k ? 'border-indigo-400 text-white' : 'border-transparent text-slate-400 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'evidence' && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500">Every claim in the diagnosis must cite one of these, and each one records the exact tool call that produced it.</p>
          {evidence.length === 0 && <p className="text-sm text-slate-500">No evidence gathered yet.</p>}
          {evidence.map((e) => (
            <div key={e.id} className="card p-3 text-sm">
              <div className="flex items-center gap-2 text-[11px]">
                <span className="font-mono text-slate-500">{e.id}</span>
                <span className="chip bg-white/10 text-slate-300">{AGENT[e.agent]?.label ?? e.agent}</span>
                <span className="ml-auto text-slate-500">confidence {pct(e.confidence)}</span>
              </div>
              <p className="mt-1.5">{cleanClaim(e.claim)}</p>
              <p className="mt-1 break-all font-mono text-[11px] text-slate-600">{e.evidence_query}</p>
            </div>
          ))}
        </div>
      )}

      {tab === 'audit' && (
        <div>
          <p className="mb-3 text-xs text-slate-500">
            Agents never call tools directly. Every call passes a policy layer that checks its trust tier and writes an append-only record.
            <span className="ml-2 text-slate-300">{audit.length - blocked} allowed · {blocked} blocked</span>
          </p>
          <div className="card overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500">
                <tr>{['Time', 'Agent', 'Tool', 'Tier', 'Decision', 'Reason'].map((h) => <th key={h} className="p-2.5 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.seq} className="border-t border-white/5">
                    <td className="p-2.5 text-slate-500">{fmtTime(a.ts)}</td>
                    <td className="p-2.5">{AGENT[a.agent]?.label ?? a.agent}</td>
                    <td className="p-2.5 font-mono">{a.tool}</td>
                    <td className="p-2.5 text-slate-400">{a.tier}</td>
                    <td className={`p-2.5 ${DEC[a.decision] ?? 'text-amber-300'}`}>{a.decision}</td>
                    <td className="p-2.5 text-slate-500">{a.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'log' && (
        <ol className="card divide-y divide-white/5 text-xs">
          {steps.map((s) => (
            <li key={s.seq} className="flex gap-3 px-3 py-2">
              <span className="w-12 shrink-0 font-mono text-slate-600">+{(s.ts - t0).toFixed(1)}s</span>
              <span className="w-24 shrink-0 text-slate-300">{AGENT[s.agent]?.label ?? s.agent}</span>
              <span className="min-w-0 text-slate-400">{logLine(s)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
