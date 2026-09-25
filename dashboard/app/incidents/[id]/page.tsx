'use client';
import { useParams } from 'next/navigation';
import AgentLanes from '@/components/AgentLanes';
import ReportCard from '@/components/ReportCard';
import StatusBadge from '@/components/StatusBadge';
import { getJSON, IncidentDetail } from '@/lib/api';
import { usePoll } from '@/lib/usePoll';

export default function IncidentPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = usePoll(() => getJSON<IncidentDetail>(`/incidents/${id}`), 1000);
  if (error && !data) return <p className="text-red-400">{error}</p>;
  if (!data) return <p className="text-slate-400">Loading...</p>;
  const inc = data.incident;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold font-mono">{id}</h1>
        <StatusBadge status={inc.status} />
        <span className="text-sm text-slate-400">{inc.alert?.name} on {inc.alert?.service}</span>
      </div>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-2">Agents (live)</h2>
        <AgentLanes steps={data.steps} />
      </section>
      {inc.report && (
        <section>
          <ReportCard id={id} report={inc.report} status={inc.status} />
        </section>
      )}
      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-2">Evidence board</h2>
        <table className="w-full text-sm border border-slate-800">
          <thead className="text-left text-slate-500 text-xs">
            <tr><th className="p-2">id</th><th className="p-2">agent</th><th className="p-2">claim</th><th className="p-2">query</th><th className="p-2">conf</th></tr>
          </thead>
          <tbody>
            {data.evidence.map((e) => (
              <tr key={e.id} className="border-t border-slate-800 align-top">
                <td className="p-2 font-mono text-xs">{e.id}</td>
                <td className="p-2">{e.agent}</td>
                <td className="p-2">{e.claim.replace(/\[[^\]]*\]/g, '').trim()}</td>
                <td className="p-2 font-mono text-xs text-slate-400 break-all">{e.evidence_query}</td>
                <td className="p-2">{(e.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-slate-500 mb-2">Audit log (every tool call, allowed or blocked)</h2>
        <table className="w-full text-xs border border-slate-800">
          <thead className="text-left text-slate-500">
            <tr><th className="p-2">time</th><th className="p-2">agent</th><th className="p-2">tool</th><th className="p-2">tier</th><th className="p-2">decision</th><th className="p-2">reason</th></tr>
          </thead>
          <tbody>
            {data.audit.map((a) => (
              <tr key={a.seq} className="border-t border-slate-800">
                <td className="p-2">{new Date(a.ts * 1000).toLocaleTimeString()}</td>
                <td className="p-2">{a.agent}</td>
                <td className="p-2 font-mono">{a.tool}</td>
                <td className="p-2">{a.tier}</td>
                <td className={`p-2 ${a.decision === 'blocked' ? 'text-red-400' : a.decision === 'allowed' ? 'text-emerald-400' : 'text-amber-300'}`}>{a.decision}</td>
                <td className="p-2 text-slate-400">{a.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
