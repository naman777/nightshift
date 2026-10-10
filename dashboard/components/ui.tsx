// ChaiUI pieces (https://ui.chaicode.com), ported to this app's Tailwind 3 setup. Tokens and base classes are in app/globals.css.
import { ReactNode } from 'react';

export function Highlight({ children }: { children: ReactNode }) {
  return <span className="highlight">{children}</span>;
}

type Tone = 'ok' | 'warn' | 'bad' | 'special';

export function Chip({ tone, children, className = '' }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={`chip ${tone ? `tone-${tone}` : ''} ${className}`}>{children}</span>;
}

const LEVEL: Record<string, Tone> = { standard: 'ok', tricky: 'warn', hard: 'bad' };

/** Difficulty as a small coloured word with a dot. */
export function Level({ level }: { level: string }) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 text-[11px] font-semibold capitalize tracking-wide tone-${LEVEL[level] ?? 'ok'}`}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />{level}
    </span>
  );
}

/** A pinging dot for something in progress. The ping stops for reduced motion; the dot stays. */
export function LiveDot({ className = '' }: { className?: string }) {
  return (
    <span className={`relative flex size-2 shrink-0 items-center justify-center ${className}`} aria-hidden="true">
      <span className="absolute size-full rounded-full bg-current opacity-60 motion-safe:animate-ping" />
      <span className="relative size-1.5 rounded-full bg-current" />
    </span>
  );
}

/** A filter switch. Its active segment is the one place a warm brown fill is allowed. */
export function Segmented<T extends string>({ options, value, onChange, label }: { options: readonly { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex max-w-full overflow-x-auto rounded-md border border-gray-200 bg-white [scrollbar-width:none] dark:border-gray-800 dark:bg-black/50">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}
          className={`inline-flex h-9 shrink-0 cursor-pointer items-center justify-center whitespace-nowrap px-3.5 text-[13px] outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${
            value === o.value ? 'bg-orange-100 text-orange-900 dark:bg-orange-900/40 dark:text-orange-100'
              : 'text-gray-600 hover:bg-orange-50 hover:text-orange-900 dark:text-gray-400 dark:hover:bg-orange-900/20 dark:hover:text-orange-100'}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A stacked single choice, each option with a line of explanation. */
export function OptionList<T extends string>({ options, value, onChange, label }: { options: { id: T; label: string; sub?: string; disabled?: boolean }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="space-y-1.5">
      {options.map((o) => (
        <button key={o.id} type="button" role="radio" aria-checked={value === o.id} disabled={o.disabled} onClick={() => onChange(o.id)}
          className={`w-full rounded-lg border px-3 py-2 text-left outline-none transition-colors duration-200 hover:border-card-edge focus-visible:ring-[3px] focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${value === o.id ? 'is-picked' : ''}`}>
          <div className="flex items-center justify-between gap-2 text-sm font-medium">
            {o.label}
            <span className={`size-2 shrink-0 rounded-full ${value === o.id ? 'bg-highlight' : 'border border-input'}`} aria-hidden="true" />
          </div>
          {o.sub && <div className="mt-0.5 text-xs text-muted-foreground">{o.sub}</div>}
        </button>
      ))}
    </div>
  );
}

/** The hero pill: a glint runs round its border. Use one, above the headline. */
export function AnimatedBadge({ children }: { children: ReactNode }) {
  return (
    <span className="relative inline-flex w-fit items-center justify-center overflow-hidden rounded-full p-px">
      <span aria-hidden="true" className="absolute left-1/2 top-1/2 h-5 w-[300px] rounded-full bg-gradient-to-r from-transparent via-transparent to-orange-500 motion-safe:animate-chai-spin"
        style={{ transform: 'translate(-50%, -50%)' }} />
      <span className="relative z-10 rounded-full bg-neutral-50 px-4 py-2 text-sm font-medium text-neutral-800 dark:bg-stone-900 dark:text-neutral-100">{children}</span>
    </span>
  );
}

/** Title and lead for a listing page. The lead carries the highlight phrase. */
export function PageHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-medium sm:text-center sm:text-3xl">{title}</h1>
      {children && <p className="mx-auto max-w-3xl text-base text-neutral-700 sm:text-center sm:text-lg dark:text-neutral-400">{children}</p>}
    </div>
  );
}

export function SectionHead({ title, children, aside }: { title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 className="text-2xl font-medium sm:text-[30px] sm:leading-9">{title}</h2>
        {children && <p className="mt-1 text-gray-600 dark:text-gray-300">{children}</p>}
      </div>
      {aside}
    </div>
  );
}
