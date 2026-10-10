import { LiveDot } from '@/components/ui';

// Status is text and a thin outline, never a filled pill. Purple is kept for the one special case: handed to a human.
const STYLE: Record<string, [string, string]> = {
  investigating: ['!text-foreground', 'Investigating'], diagnosed: ['!text-foreground', 'Diagnosed'],
  awaiting_approval: ['tone-warn', 'Needs your approval'], resolved: ['tone-ok', 'Resolved'],
  rejected: ['', 'Rejected'], blocked: ['tone-bad', 'Blocked'], escalated: ['tone-special', 'Escalated'],
};

export default function StatusBadge({ status }: { status: string }) {
  const [cls, label] = STYLE[status] ?? ['', status.replace('_', ' ')];
  return <span className={`chip ${cls}`}>{status === 'investigating' && <LiveDot />}{label}</span>;
}
