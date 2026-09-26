import './globals.css';
import type { ReactNode } from 'react';
import Nav from '@/components/Nav';

export const metadata = { title: 'Nightshift', description: 'An AI on-call engineer that investigates incidents and asks before it acts.' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Nav />
        <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
      </body>
    </html>
  );
}
