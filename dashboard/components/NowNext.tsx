import { LiveDot } from '@/components/ui';
import { Progress } from '@/lib/derive';

export default function NowNext({ p }: { p: Progress }) {
  const live = p.tone === 'active';
  return (
    <div className="card grid divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0">
      <div className="p-4">
        <div className="label flex items-center gap-2">{live && <LiveDot className="text-foreground" />}Happening now</div>
        <p className="mt-1.5 text-[15px] leading-snug">{p.now}</p>
      </div>
      <div className="p-4">
        <div className="label">Next</div>
        <p className="mt-1.5 text-[15px] leading-snug text-muted-foreground">{p.next}</p>
      </div>
    </div>
  );
}
