import { Progress } from '@/lib/derive';

export default function NowNext({ p }: { p: Progress }) {
  const live = p.tone === 'active';
  return (
    <div className="grid gap-px overflow-hidden rounded-xl border border-white/10 bg-white/10 sm:grid-cols-2">
      <div className="bg-[#0d1119] p-4">
        <div className="label flex items-center gap-2">
          {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />}Happening now
        </div>
        <p className="mt-1.5 text-[15px] leading-snug">{p.now}</p>
      </div>
      <div className="bg-[#0d1119] p-4">
        <div className="label">Next</div>
        <p className="mt-1.5 text-[15px] leading-snug text-slate-300">{p.next}</p>
      </div>
    </div>
  );
}
