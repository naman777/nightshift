const STYLE: Record<string, [string, string]> = {
  investigating: ['bg-sky-500/15 text-sky-300', 'Investigating'], diagnosed: ['bg-indigo-500/15 text-indigo-300', 'Diagnosed'],
  awaiting_approval: ['bg-amber-500/15 text-amber-300', 'Needs your approval'], resolved: ['bg-emerald-500/15 text-emerald-300', 'Resolved'],
  rejected: ['bg-slate-500/20 text-slate-300', 'Rejected'], blocked: ['bg-red-500/15 text-red-300', 'Blocked'], escalated: ['bg-purple-500/15 text-purple-300', 'Escalated'],
};

export default function StatusBadge({ status }: { status: string }) {
  const [cls, label] = STYLE[status] ?? ['bg-slate-700 text-slate-200', status.replace('_', ' ')];
  return <span className={`chip ${cls}`}>{label}</span>;
}
