'use client';
import Link from 'next/link';
import StatusBadge from '@/components/StatusBadge';
import { getJSON, Incident } from '@/lib/api';
import { usePoll } from '@/lib/usePoll';

export default function Home() {
  const { data, error } = usePoll(() => getJSON<Incident[]>('/incidents'), 2000);
  return (
    <div>
      <h1 className="text-2xl font-semibold mb-4">Incidents</h1>
      {error && <p className="text-red-400 text-sm mb-3">Gateway unreachable: {error}</p>}
      {data && data.length === 0 && <p className="text-slate-400">No incidents yet. Fire an alert (make chaos) or POST one to /webhook/alertmanager.</p>}
      <div className="grid gap-2">
        {data?.map((i) => (
          <Link key={i.id} href={`/incidents/${i.id}`} className="flex items-center justify-between border border-slate-800 rounded px-4 py-3 hover:bg-slate-900">
            <span className="font-mono text-sm">{i.id}</span>
            <span className="flex items-center gap-4 text-xs text-slate-400">
              {new Date(i.created_at * 1000).toLocaleTimeString()} <StatusBadge status={i.status} />
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
