import './globals.css';
import { Manrope, Montserrat, Onest } from 'next/font/google';
import Link from 'next/link';
import type { ReactNode } from 'react';
import Nav, { Logo } from '@/components/Nav';
import { THEME_KEY } from '@/lib/theme';

const manrope = Manrope({ subsets: ['latin'], variable: '--font-manrope' });
const montserrat = Montserrat({ subsets: ['latin'], variable: '--font-montserrat' });
const onest = Onest({ subsets: ['latin'], variable: '--font-onest' });

export const metadata = { title: 'Nightshift', description: 'An AI on-call engineer that investigates incidents and asks before it acts.' };

// Sets the theme class before first paint, so a stored light choice does not flash dark.
const themeScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});document.documentElement.classList.toggle('dark',t!=='light')}catch(e){}})()`;

const FOOTER_LINKS = [
  { href: '/', label: 'Run an incident' },
  { href: '/incidents', label: 'History' },
  { href: '/benchmark', label: 'Benchmark' },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`dark ${manrope.variable} ${montserrat.variable} ${onest.variable}`} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body>
        <div className="relative isolate flex min-h-screen flex-col overflow-x-clip">
          {/* The chaicode.com page background. Light mode inverts it; the half-turn of hue keeps the browns warm. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/chaiui/background.svg" alt="" aria-hidden="true" decoding="async"
            className="pointer-events-none absolute left-1/2 top-0 -z-10 w-[2842px] max-w-none -translate-x-1/2 select-none hue-rotate-180 invert [mask-image:linear-gradient(to_bottom,#000_55%,transparent)] dark:hue-rotate-0 dark:invert-0" />
          <Nav />
          <main className="mx-auto w-full max-w-6xl flex-1 p-6 sm:p-12">{children}</main>
          <footer className="relative px-6 font-montserrat before:absolute before:left-1/2 before:top-0 before:h-px before:w-full before:max-w-[1440px] before:-translate-x-1/2 before:bg-amber-600 before:opacity-10 before:[mask-image:linear-gradient(90deg,transparent_0%,black_40%,black_60%,transparent_100%)] sm:px-12 dark:before:bg-orange-300">
            <div className="mx-auto flex max-w-6xl flex-col gap-6 py-8 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <Logo />
                <p className="mt-2 text-sm tracking-tight text-gray-500 dark:text-gray-400">An AI on-call engineer that asks before it acts.</p>
              </div>
              <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
                {FOOTER_LINKS.map((l) => (
                  <Link key={l.href} href={l.href} className="text-[15px] tracking-tight text-gray-500 transition-colors duration-200 hover:text-brand dark:text-gray-400">{l.label}</Link>
                ))}
              </nav>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
