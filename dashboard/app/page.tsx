'use client';
import { ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import IncidentRow from '@/components/IncidentRow';
import { AnimatedBadge, Highlight, Level, OptionList, SectionHead, Segmented } from '@/components/ui';
import { DemoConfig, Incident, Scenario, getJSON, launch } from '@/lib/api';
import { usePoll } from '@/lib/usePoll';

const FEATURED: { id: string; title: string; why: string }[] = [
  { id: 'bad-deploy-n-plus-one-00', title: 'Bad deploy', why: 'A release made every order query slow. The classic.' },
  { id: 'bad-config-push-lb-timeout-00', title: 'Config change + red herring', why: 'A harmless deploy is a decoy; the real cause is a config value.' },
  { id: 'dependency-outage-injection-02', title: 'Prompt injection', why: 'The logs contain an attack. Watch the agent refuse to obey it.' },
  { id: 'hard-01-decoy-config-slow-dep', title: 'Hard: convincing decoy', why: 'A plausible wrong answer is planted. Hard even for a strong model.' },
];
const FILTERS = ['all', 'standard', 'tricky', 'hard'] as const;

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
  const usedUp = real?.limit?.remaining === 0;
  const realSub = !real?.available ? 'Off on this host (needs OPENAI_API_KEY)'
    : usedUp ? "Today's real-model runs are used up (resets 00:00 UTC)"
    : real.limit ? `Real reasoning, takes up to a minute. ${real.limit.remaining} run${real.limit.remaining === 1 ? '' : 's'} left for you today`
    : 'Real reasoning, a few cents per run';

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
    <div className="space-y-12 sm:space-y-16">
      <section className="flex flex-col gap-y-2.5 sm:gap-y-4 md:w-3/4">
        <AnimatedBadge>50 simulated production incidents</AnimatedBadge>
        <h1 className="text-[42px] font-semibold leading-[1.05] tracking-tight md:text-6xl lg:text-7xl">Watch AI agents solve an incident</h1>
        <p className="mt-4 max-w-3xl text-base text-neutral-700 sm:mt-6 md:text-xl dark:text-neutral-400">
          Nightshift investigates production incidents like an on-call engineer: it plans, gathers evidence from metrics, logs, deploys and code,
          names a root cause with citations, and proposes a fix. <Highlight>Nothing runs without your approval</Highlight>.
        </p>
        <div className="mt-6 flex items-center gap-4">
          <Link href="/benchmark" className="btn-outline">See the benchmark</Link>
        </div>
      </section>

      {loadError && <p className="card p-4 text-sm tone-bad">Cannot reach the gateway ({loadError}). Start it with <code>python -m gateway.demo</code>.</p>}

      <div className="grid gap-10 lg:grid-cols-[1fr_320px]">
        <div className="space-y-12">
          <section>
            <SectionHead title="Suggested demos">Four incidents that show <Highlight>what the agents can and cannot do</Highlight>.</SectionHead>
            <div className="grid gap-4 sm:grid-cols-2">
              {FEATURED.filter((f) => byId.has(f.id)).map((f) => (
                <button key={f.id} type="button" aria-pressed={picked === f.id} onClick={() => setPicked(f.id)}
                  className={`card p-4 text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring ${picked === f.id ? 'is-picked' : 'sm:opacity-90 sm:hover:opacity-100'}`}>
                  <div className="font-montserrat text-base font-semibold leading-snug">{f.title}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{f.why}</div>
                </button>
              ))}
            </div>
          </section>

          <section>
            <SectionHead title="All scenarios"
              aside={<Segmented label="Difficulty" value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ value: f, label: f[0].toUpperCase() + f.slice(1) }))} />}>
              Showing <span className="font-semibold text-foreground">{shown.length}</span> of {scenarios.length}
            </SectionHead>
            <div className="grid max-h-[28rem] gap-3 overflow-auto pr-1 sm:grid-cols-2">
              {shown.map((s) => (
                <button key={s.id} type="button" aria-pressed={picked === s.id} onClick={() => setPicked(s.id)}
                  className={`card p-3 text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring ${picked === s.id ? 'is-picked' : 'sm:opacity-90 sm:hover:opacity-100'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-montserrat text-sm font-semibold leading-snug">{s.title}</span>
                    <Level level={s.difficulty} />
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{s.tags.length ? s.tags.join(' · ') : s.blurb}</div>
                  <div className="mt-1.5 break-all font-mono text-[10px] text-faint">{s.id}</div>
                </button>
              ))}
            </div>
          </section>
        </div>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="card space-y-5 p-5">
            <div>
              <div className="label">Selected incident</div>
              <div className="mt-1 font-montserrat text-base font-semibold leading-snug">{sel?.title ?? '...'}</div>
              <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{sel?.blurb}</div>
              {sel && sel.tags.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{sel.tags.map((t) => <span key={t} className="chip !whitespace-normal">{t}</span>)}</div>}
              <div className="mt-2 text-xs text-faint">Alert: <code>{sel?.alert}</code></div>
            </div>

            <div>
              <div className="label mb-2">Agent setup</div>
              <OptionList label="Agent setup" value={mode} onChange={setMode} options={[
                { id: 'multi', label: 'Team of specialists', sub: 'Commander + metrics, logs, changes, code' },
                { id: 'single', label: 'Single agent', sub: 'One agent, cheaper and faster' }]} />
            </div>

            <div>
              <div className="label mb-2">Model</div>
              <OptionList label="Model" value={provider} onChange={setProvider} options={[
                { id: 'mock', label: 'Offline reference policy', sub: 'Free and instant. Not a language model.' },
                { id: 'openai', label: real?.label ?? 'Real LLM', sub: realSub, disabled: !real?.available || usedUp }]} />
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                <span className="text-foreground">The benchmark numbers come from the real model, not this policy:</span> 96% held-out root-cause accuracy
                was measured with <code>gpt-6-luna</code> (15 scenarios x 3 runs). The offline policy is hand-written for these simulated worlds and is here
                so the demo runs free; its runs show the workflow, not model accuracy.
              </p>
              {provider === 'mock' && (
                <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" checked={pace} onChange={(e) => setPace(e.target.checked)} className="accent-neutral-900 dark:accent-neutral-200" />
                  Slow it down so I can watch
                </label>
              )}
            </div>

            <button className="btn-solid w-full" disabled={busy || !sel} onClick={run}>{busy ? 'Starting...' : 'Run investigation'}<ArrowUpRight className="-ml-1 size-4" aria-hidden="true" /></button>
            {error && <p className="text-xs tone-bad">{error}</p>}
          </div>
        </aside>
      </div>

      {recent && recent.length > 0 && (
        <section>
          <SectionHead title="Recent runs" aside={<Link href="/incidents" className="text-sm text-muted-foreground transition-colors duration-200 hover:text-brand">See all</Link>} />
          <div className="grid gap-2">
            {recent.slice(0, 4).map((i) => <IncidentRow key={i.id} incident={i} />)}
          </div>
        </section>
      )}
    </div>
  );
}
