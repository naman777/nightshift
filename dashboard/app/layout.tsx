import './globals.css';
import Link from 'next/link';
import type { ReactNode } from 'react';

export const metadata = { title: 'Nightshift', description: 'AI on-call engineer' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-slate-800 px-6 py-3 flex items-center gap-6">
          <Link href="/" className="font-semibold tracking-tight text-lg">Nightshift</Link>
          <nav className="flex gap-4 text-sm text-slate-400">
            <Link href="/" className="hover:text-white">Incidents</Link>
            <Link href="/benchmark" className="hover:text-white">Benchmark</Link>
          </nav>
        </header>
        <main className="p-6 max-w-7xl mx-auto">{children}</main>
      </body>
    </html>
  );
}
