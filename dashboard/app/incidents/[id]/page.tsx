'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import Investigators from '@/components/Investigators';
import NowNext from '@/components/NowNext';
import PlanCard from '@/components/PlanCard';
import ReportCard from '@/components/ReportCard';
import Stepper from '@/components/Stepper';
import StatusBadge from '@/components/StatusBadge';
import Tabs from '@/components/Tabs';
import Verdict from '@/components/Verdict';
import { IncidentDetail, getJSON } from '@/lib/api';
import { prettyId, progress } from '@/lib/derive';
import { usePoll } from '@/lib/usePoll';

export default function IncidentPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = usePoll(() => getJSON<IncidentDetail>(`/incidents/${id}`), 1000);
  if (error && !data) return <p className="text-red-300">Could not load this incident ({error}). <Link href="/" className="underline">Back</Link></p>;
  if (!data) return <p className="text-slate-400">Loading...</p>;
  const inc = data.incident;
  const p = progress(data);
  const labels = inc.alert?.labels ?? {};
  const setup = [labels.mode === 'single' ? 'Single agent' : 'Team of specialists', labels.llm_provider === 'openai' ? `Real LLM (${labels.llm_model})` : 'Offline reference policy'];
  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-xs text-slate-500 hover:text-white">← Run another</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {inc.alert?.name ?? 'Incident'} <span className="text-slate-500">on {inc.alert?.service}</span>
          </h1>
          <StatusBadge status={inc.status} />
        </div>
        <p className="mt-1 text-xs text-slate-500">{prettyId(id)} · {setup.join(' · ')}</p>
      </div>

      <div className="card px-5 py-4"><Stepper p={p} /></div>
      <NowNext p={p} />

      {p.plan && <PlanCard plan={p.plan} agents={p.agents} report={inc.report} followUps={p.followUps} />}
      <Investigators agents={p.agents} />
      {inc.report && <ReportCard id={id} report={inc.report} status={inc.status} />}
      {inc.report && inc.ground_truth && <Verdict truth={inc.ground_truth} report={inc.report} />}
      <Tabs evidence={data.evidence} audit={data.audit} steps={data.steps} />
    </div>
  );
}
