'use client';
import { useEffect, useState } from 'react';

export function usePoll<T>(fn: () => Promise<T>, ms = 1500): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const d = await fn();
        if (alive) { setData(d); setError(null); }
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    tick();
    const id = setInterval(tick, ms);
    return () => { alive = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms]);
  return { data, error };
}
