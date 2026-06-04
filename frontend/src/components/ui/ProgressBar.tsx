import { barColor } from '@/lib/format';

interface ProgressBarProps {
  value: number; // 0-100
  showLabel?: boolean;
  className?: string;
}

/** A thin, colour-coded 0-100 progress bar (green full -> red depleted). */
export function ProgressBar({ value, showLabel = true, className = '' }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor(clamped)}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel && (
        <span className="w-9 flex-none text-right font-mono text-xs text-slate-400">
          {Math.round(clamped)}
        </span>
      )}
    </div>
  );
}
