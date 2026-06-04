interface OvrGaugeProps {
  value: number; // typically 40-99
  label?: string;
  size?: number;
}

/**
 * Radial "squad OVR matrix" gauge rendered with an SVG conic stroke.
 * The arc fills proportionally and is colour-graded by quality tier.
 */
export function OvrGauge({ value, label = 'SQUAD OVR', size = 72 }: OvrGaugeProps) {
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  const dash = circumference * pct;

  const stroke =
    value >= 85 ? '#34d399' : value >= 78 ? '#22d3ee' : value >= 70 ? '#38bdf8' : '#94a3b8';

  return (
    <div className="flex items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#1e293b"
            strokeWidth={6}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={stroke}
            strokeWidth={6}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference}`}
            style={{ transition: 'stroke-dasharray 0.8s ease-out' }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-lg font-extrabold text-white">
            {Math.round(value)}
          </span>
        </div>
      </div>
      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
        {label}
      </span>
    </div>
  );
}
