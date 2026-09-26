'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import StatusBadge from '@/components/StatusBadge';
import { DemoConfig, Incident, Scenario, getJSON, launch } from '@/lib/api';
import { fmtTime, prettyId } from '@/lib/derive';
import { usePoll } from '@/lib/usePoll';

const FEATURED: { id: string; title: string; why: string }[] = [
  { id: 'bad-deploy-n-plus-one-00', title: 'Bad deploy', why: 'A release made every order query slow. The classic.' },
  { id: 'bad-config-push-lb-timeout-00', title: 'Config change + red herring', why: 'A harmless deploy is a decoy; the real cause is a config value.' },
  { id: 'dependency-outage-injection-02', title: 'Prompt injection', why: 'The logs contain an attack. Watch the agent refuse to obey it.' },
  { id: 'hard-01-decoy-config-slow-dep', title: 'Hard: convincing decoy', why: 'A plausible wrong answer is planted. Hard even for a strong model.' },
];
const DIFF_STYLE = { standard: 'bg-emerald-500/15 text-emerald-300', tricky: 'bg-amber-500/15 text-amber-300', hard: 'bg-rose-500/15 text-rose-300' } as const;
const FILTERS = ['all', 'standard', 'tricky', 'hard'] as const;

function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { id: T; label: string; sub?: string; disabled?: boolean }[] }) {
  return (
    <div className="space-y-1.5">
      {options.map((o) => (
        <button key={o.id} disabled={o.disabled} onClick={() => onChange(o.id)}
          className={`w-full rounded-lg border px-3 py-2 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${value === o.id ? 'border-indigo-400/60 bg-indigo-500/10' : 'border-white/10 hover:bg-white/5'}`}>
          <div className="text-sm font-medium">{o.label}</div>
          {o.sub && <div className="text-xs text-slate-400">{o.sub}</div>}
        </button>
      ))}
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [config, setConfig] = useState<DemoConfig | null>(null);
  const [loadError, setLoadError] = useState('');
  const [picked, setPicked] = useState(FEATURED[0].id);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('all');
  const [mode, setMode] = useState<'multi' | 'single'>('multi');
  const [provider, setProvider] = useState<'mock' | 'openai'>('mock');
  const [pace, setPace] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const recent = usePoll(() => getJSON<Incident[]>('/incidents'), 3000).data;

  useEffect(() => {
    Promise.all([getJSON<Scenario[]>('/demo/scenarios'), getJSON<DemoConfig>('/demo/config')])
      .then(([s, c]) => { setScenarios(s); setConfig(c); })
      .catch((e) => setLoadError(String(e)));
  }, []);

  const byId = useMemo(() => new Map(scenarios.map((s) => [s.id, s])), [scenarios]);
  const shown = scenarios.filter((s) => filter === 'all' || s.difficulty === filter);
  const sel = byId.get(picked);
  const real = config?.providers.find((p) => p.id === 'openai');

  const run = async () => {
    setBusy(true); setError('');
    try {
      const r = await launch({ scenario: picked, mode, provider, pace });
      router.push(`/incidents/${r.incident_id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e)); setBusy(false);
    }
  };

  return (
    <div className="space-y-10">
      <section className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight">Pick an incident. Watch AI agents solve it.</h1>
        <p className="mt-3 text-[15px] leading-relaxed text-slate-400">
          Nightshift investigates production incidents like an on-call engineer: it plans, gathers evidence from metrics, logs, deploys and code,
          names a root cause with citations, and proposes a fix. <span className="text-slate-200">Nothing that changes a system runs without your approval.</span>
        </p>
      </section>

      {loadError && <p className="card border-red-500/30 p-4 text-sm text-red-300">Cannot reach the gateway ({loadError}). Start it with <code>python -m gateway.demo</code>.</p>}

      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <div className="space-y-8">
          <section>
            <div className="label mb-3">Suggested demos</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {FEATURED.filter((f) => byId.has(f.id)).map((f) => (
                <button key={f.id} onClick={() => setPicked(f.id)}
                  className={`card p-4 text-left transition hover:bg-white/[0.06] ${picked === f.id ? 'border-indigo-400/60 bg-indigo-500/10' : ''}`}>
                  <div className="font-medium">{f.title}</div>
                  <div className="mt-1 text-sm text-slate-400">{f.why}</div>
                </button>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <div className="label">All scenarios ({scenarios.length})</div>
              <div className="flex gap-1 text-xs">
                {FILTERS.map((f) => (
                  <button key={f} onClick={() => setFilter(f)}
                    className={`rounded-md px-2.5 py-1 capitalize ${filter === f ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-white'}`}>{f}</button>
                ))}
              </div>
            </div>
            <div className="grid max-h-[26rem] gap-2 overflow-auto pr-1 sm:grid-cols-2">
              {shown.map((s) => (
                <button key={s.id} onClick={() => setPicked(s.id)}
                  className={`card p-3 text-left transition hover:bg-white/[0.06] ${picked === s.id ? 'border-indigo-400/60 bg-indigo-500/10' : ''}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{s.title}</span>
                    <span className={`chip ${DIFF_STYLE[s.difficulty]}`}>{s.difficulty}</span>
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-slate-400">{s.tags.length ? s.tags.join(' · ') : s.blurb}</div>
                  <div className="mt-1 font-mono text-[10px] text-slate-600">{s.id}</div>
                </button>
              ))}
            </div>
          </section>
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <div className="card space-y-5 p-5">
            <div>
              <div className="label">Selected incident</div>
              <div className="mt-1 font-medium">{sel?.title ?? '...'}</div>
              <div className="mt-1 text-xs text-slate-400">{sel?.blurb}</div>
              {sel && sel.tags.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{sel.tags.map((t) => <span key={t} className="chip bg-white/5 text-slate-300">{t}</span>)}</div>}
              <div className="mt-2 text-xs text-slate-500">Alert: <code>{sel?.alert}</code></div>
            </div>

            <div>
              <div className="label mb-2">Agent setup</div>
              <Segmented value={mode} onChange={setMode} options={[
                { id: 'multi', label: 'Team of specialists', sub: 'Commander + metrics, logs, changes, code' },
                { id: 'single', label: 'Single agent', sub: 'One agent, cheaper and faster' }]} />
            </div>

            <div>
              <div className="label mb-2">Model</div>
              <Segmented value={provider} onChange={setProvider} options={[
                { id: 'mock', label: 'Offline reference policy', sub: 'Free and instant. Not a language model.' },
                { id: 'openai', label: real?.label ?? 'Real LLM', sub: real?.available ? 'Real reasoning, a few cents per run' : 'Set OPENAI_API_KEY to enable', disabled: !real?.available }]} />
              {provider === 'mock' && (
                <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-slate-400">
                  <input type="checkbox" checked={pace} onChange={(e) => setPace(e.target.checked)} className="accent-indigo-500" />
                  Slow it down so I can watch
                </label>
              )}
            </div>

            <button className="btn-primary w-full" disabled={busy || !sel} onClick={run}>{busy ? 'Starting...' : 'Run investigation'}</button>
            {error && <p className="text-xs text-red-300">{error}</p>}
          </div>
        </aside>
      </div>

      {recent && recent.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <div className="label">Recent runs</div>
            <Link href="/incidents" className="text-xs text-slate-400 hover:text-white">See all</Link>
          </div>
          <div className="grid gap-2">
            {recent.slice(0, 4).map((i) => (
              <Link key={i.id} href={`/incidents/${i.id}`} className="card flex items-center justify-between px-4 py-2.5 text-sm transition hover:bg-white/[0.06]">
                <span>{prettyId(i.id)}</span>
                <span className="flex items-center gap-4 text-xs text-slate-500">{fmtTime(i.created_at)} <StatusBadge status={i.status} /></span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
