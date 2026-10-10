'use client';
import { Moon } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { THEME_KEY } from '@/lib/theme';

const LINKS = [
  { href: '/', label: 'Run' },
  { href: '/incidents', label: 'History' },
  { href: '/benchmark', label: 'Benchmark' },
];

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2 font-brand text-xl font-medium tracking-tight">
      <Moon className="size-5 text-brand" aria-hidden="true" />
      <span className={compact ? 'max-sm:hidden' : ''}>Nightshift</span>
    </span>
  );
}

// One label for both themes: the server cannot know the stored choice, and a label that depends on it mismatches on hydration.
function ThemeSwitcher() {
  const toggle = () => {
    const next = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
    document.documentElement.classList.toggle('dark', next === 'dark');
    try { localStorage.setItem(THEME_KEY, next); } catch { /* private windows can refuse storage; the theme still applies */ }
  };
  return (
    <button type="button" onClick={toggle} aria-label="Toggle theme" title="Toggle theme"
      className="inline-flex size-9 cursor-pointer items-center justify-center rounded-md text-foreground outline-none transition-colors duration-200 hover:text-brand focus-visible:ring-[3px] focus-visible:ring-ring">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="size-[22px]">
        <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
        <path d="M12 3l0 18" />
        <path d="M12 9l4.65 -4.65" />
        <path d="M12 14.3l7.37 -7.37" />
        <path d="M12 19.6l8.85 -8.85" />
      </svg>
    </button>
  );
}

export default function Nav() {
  const path = usePathname();
  const active = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 0);
    on();
    addEventListener('scroll', on, { passive: true });
    return () => removeEventListener('scroll', on);
  }, []);
  return (
    <header className={`sticky top-0 z-50 transition-[backdrop-filter,background] duration-300 ${scrolled ? 'bg-[color-mix(in_oklab,var(--background)_60%,transparent)] backdrop-blur-md' : 'bg-transparent'}`}>
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4 sm:px-12">
        <Link href="/" aria-label="Nightshift home" ><Logo compact /></Link>
        <div className="flex items-center gap-1 sm:gap-2">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={active(l.href) ? 'page' : undefined}
              className={`rounded-md px-2.5 py-1.5 text-sm transition-colors duration-200 hover:text-brand ${active(l.href) ? 'font-medium text-foreground' : 'text-muted-foreground'}`}>{l.label}</Link>
          ))}
          <ThemeSwitcher />
        </div>
      </nav>
    </header>
  );
}
