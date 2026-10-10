import Link from 'next/link';
import StatusBadge from '@/components/StatusBadge';
import { Incident } from '@/lib/api';
import { fmtTime, prettyId } from '@/lib/derive';

export default function IncidentRow({ incident: i }: { incident: Incident }) {
  return (
    <Link href={`/incidents/${i.id}`} className="card flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 text-sm sm:opacity-90 sm:hover:opacity-100">
      <span className="min-w-0 break-words font-medium">{prettyId(i.id)}</span>
      <span className="flex items-center gap-4 text-xs text-faint">{fmtTime(i.created_at)} <StatusBadge status={i.status} /></span>
    </Link>
  );
}
