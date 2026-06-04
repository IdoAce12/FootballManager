/**
 * Smooth counting animation for currency values in the header.
 */

import { useEffect, useRef, useState } from 'react';
import { formatMoney } from '@/lib/format';

interface AnimatedMoneyProps {
  value: number;
  className?: string;
  durationMs?: number;
}

export function AnimatedMoney({ value, className = '', durationMs = 650 }: AnimatedMoneyProps) {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    const to = value;
    if (Math.abs(to - from) < 1) {
      setDisplay(to);
      fromRef.current = to;
      return;
    }

    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - t) ** 3;
      const next = from + (to - from) * eased;
      setDisplay(next);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
        setDisplay(to);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, durationMs]);

  return <span className={className}>{formatMoney(display)}</span>;
}
