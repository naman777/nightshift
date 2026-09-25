const COLORS: Record<string, string> = {
  investigating: 'bg-blue-500/20 text-blue-300', diagnosed: 'bg-indigo-500/20 text-indigo-300',
  awaiting_approval: 'bg-amber-500/20 text-amber-300', resolved: 'bg-emerald-500/20 text-emerald-300',
  rejected: 'bg-slate-500/20 text-slate-300', blocked: 'bg-red-500/20 text-red-300', escalated: 'bg-purple-500/20 text-purple-300',
};

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${COLORS[status] ?? 'bg-slate-700 text-slate-200'}`}>{status.replace('_', ' ')}</span>;
}
