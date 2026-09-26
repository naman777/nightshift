'use client';
import Link from 'next/link';
import StatusBadge from '@/components/StatusBadge';
import { Incident, getJSON } from '@/lib/api';
import { fmtTime, prettyId } from '@/lib/derive';
import { usePoll } from '@/lib/usePoll';

export default function History() {
  const { data, error } = usePoll(() => getJSON<Incident[]>('/incidents'), 2000);
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">History</h1>
      {error && <p className="text-sm text-red-300">Gateway unreachable: {error}</p>}
      {data && data.length === 0 && <p className="text-slate-400">No runs yet. <Link href="/" className="text-indigo-300 hover:underline">Launch one</Link>.</p>}
      <div className="grid gap-2">
        {data?.map((i) => (
          <Link key={i.id} href={`/incidents/${i.id}`} className="card flex items-center justify-between px-4 py-3 text-sm transition hover:bg-white/[0.06]">
            <span className="font-medium">{prettyId(i.id)}</span>
            <span className="flex items-center gap-4 text-xs text-slate-500">{fmtTime(i.created_at)} <StatusBadge status={i.status} /></span>
          </Link>
        ))}
      </div>
    </div>
  );
}
