'use client';
import Link from 'next/link';
import IncidentRow from '@/components/IncidentRow';
import { Highlight, PageHead } from '@/components/ui';
import { Incident, getJSON } from '@/lib/api';
import { usePoll } from '@/lib/usePoll';

export default function History() {
  const { data, error } = usePoll(() => getJSON<Incident[]>('/incidents'), 2000);
  return (
    <div className="space-y-8">
      <PageHead title="History">Every investigation run on this demo, with <Highlight>its diagnosis and audit trail</Highlight>.</PageHead>
      {error && <p className="text-sm tone-bad">Gateway unreachable: {error}</p>}
      {data && data.length === 0 && <p className="text-muted-foreground sm:text-center">No runs yet. <Link href="/" className="text-foreground underline underline-offset-4 transition-colors hover:text-brand">Launch one</Link>.</p>}
      {data && data.length > 0 && <p className="text-sm text-gray-500 dark:text-gray-400">Showing <span className="font-semibold text-foreground">{data.length}</span> runs</p>}
      <div className="grid gap-2">
        {data?.map((i) => <IncidentRow key={i.id} incident={i} />)}
      </div>
    </div>
  );
}
