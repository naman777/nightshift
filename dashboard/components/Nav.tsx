'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/', label: 'Run an incident' },
  { href: '/incidents', label: 'History' },
  { href: '/benchmark', label: 'Benchmark' },
];

export default function Nav() {
  const path = usePathname();
  const active = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));
  return (
    <header className="sticky top-0 z-10 border-b border-white/10 bg-[#0a0d13]/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-8 px-5 py-3">
        <Link href="/" className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-indigo-500 text-xs">N</span>
          Nightshift
        </Link>
        <nav className="flex gap-1 text-sm">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href}
              className={`rounded-md px-3 py-1.5 transition ${active(l.href) ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-white'}`}>{l.label}</Link>
          ))}
        </nav>
        <span className="ml-auto hidden text-xs text-slate-500 sm:block">AI on-call engineer</span>
      </div>
    </header>
  );
}
