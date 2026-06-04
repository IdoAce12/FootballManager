/** Presentation helpers shared across components. */

/** Tailwind text color for an OVR/potential rating (0-99 scale). */
export function ratingTextColor(rating: number): string {
  if (rating >= 85) return 'text-emerald-400';
  if (rating >= 78) return 'text-cyan-400';
  if (rating >= 70) return 'text-sky-300';
  if (rating >= 60) return 'text-slate-300';
  return 'text-slate-400';
}

/** Tailwind background classes for an OVR badge. */
export function ratingBadgeClasses(rating: number): string {
  if (rating >= 85) return 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40';
  if (rating >= 78) return 'bg-cyan-500/15 text-cyan-300 ring-cyan-500/40';
  if (rating >= 70) return 'bg-sky-500/15 text-sky-300 ring-sky-500/40';
  if (rating >= 60) return 'bg-slate-600/20 text-slate-200 ring-slate-500/40';
  return 'bg-slate-700/30 text-slate-400 ring-slate-600/40';
}

/** Colour ramp for a 0-100 bar (fitness/form): red -> amber -> green. */
export function barColor(value: number): string {
  if (value >= 75) return 'bg-emerald-500';
  if (value >= 50) return 'bg-yellow-400';
  if (value >= 30) return 'bg-orange-400';
  return 'bg-rose-500';
}

/** Accent colour for a pitch sector / position group. */
export function positionGroupColor(position: string): string {
  const p = position.toUpperCase();
  if (p === 'GK') return 'bg-amber-500/15 text-amber-300 ring-amber-500/30';
  if (['CB', 'RB', 'LB', 'RWB', 'LWB'].includes(p))
    return 'bg-sky-500/15 text-sky-300 ring-sky-500/30';
  if (['CDM', 'CM', 'CAM', 'RM', 'LM'].includes(p))
    return 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30';
  return 'bg-rose-500/15 text-rose-300 ring-rose-500/30';
}

import type { PlayerSummary } from '@/api/types';

/** Season stats line for squad UI (e.g. "5 G / 3 A"). */
export function formatPlayerStats(player: PlayerSummary): string {
  const goals = player.goals_scored ?? player.goals;
  const assists = player.assists_given ?? player.assists;
  const parts = [`${goals} G`, `${assists} A`];
  if (player.clean_sheets > 0) {
    parts.push(`${player.clean_sheets} CS`);
  }
  return parts.join(' / ');
}

/** Compact currency for ad-hoc values (the API usually returns a label too). */
export function formatMoney(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  const v = Math.abs(amount);
  if (v >= 1_000_000_000) return `${sign}€${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `${sign}€${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${sign}€${(v / 1_000).toFixed(0)}K`;
  return `${sign}€${v.toFixed(0)}`;
}
