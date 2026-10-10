import { Check } from 'lucide-react';
import { Progress } from '@/lib/derive';

export default function Stepper({ p }: { p: Progress }) {
  return (
    <ol className="flex items-center">
      {p.stages.map((s, i) => {
        const done = i < p.current || (p.tone === 'done' && i === p.current);
        const active = i === p.current && p.tone !== 'done';
        const stopped = active && p.tone === 'stopped';
        return (
          <li key={s} aria-current={active ? 'step' : undefined} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <span className={`grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold transition-colors duration-300
                ${done ? 'tone-ok border-current' : stopped ? 'border-input text-muted-foreground' : active ? 'border-transparent bg-primary text-primary-foreground' : 'border-border text-faint'}`}>
                {done ? <Check className="size-3.5" aria-label="done" /> : i + 1}
              </span>
              <span className={`hidden text-xs sm:block ${active ? 'font-medium text-foreground' : done ? 'text-muted-foreground' : 'text-faint'}`}>{s}</span>
            </div>
            {i < p.stages.length - 1 && <div className={`mx-2 h-px flex-1 ${done ? 'tone-ok bg-current opacity-40' : 'bg-border'}`} />}
          </li>
        );
      })}
    </ol>
  );
}
