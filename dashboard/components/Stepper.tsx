import { Progress } from '@/lib/derive';

export default function Stepper({ p }: { p: Progress }) {
  return (
    <ol className="flex items-center">
      {p.stages.map((s, i) => {
        const done = i < p.current || (p.tone === 'done' && i === p.current);
        const active = i === p.current && p.tone !== 'done';
        const stopped = active && p.tone === 'stopped';
        return (
          <li key={s} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold transition
                ${done ? 'bg-emerald-500 text-emerald-950' : stopped ? 'bg-slate-400 text-slate-900' : active ? 'bg-indigo-500 text-white ring-4 ring-indigo-500/25' : 'bg-white/10 text-slate-500'}`}>
                {done ? '✓' : i + 1}
              </span>
              <span className={`hidden text-xs sm:block ${active ? 'font-medium text-white' : done ? 'text-slate-300' : 'text-slate-500'}`}>{s}</span>
            </div>
            {i < p.stages.length - 1 && <div className={`mx-2 h-px flex-1 ${done ? 'bg-emerald-500/60' : 'bg-white/10'}`} />}
          </li>
        );
      })}
    </ol>
  );
}
