/**
 * SquadManager — active roster table.
 * Consumes `/api/squad` and renders every player with position, age, OVR,
 * potential, a colour-coded fitness bar, form, market value and more.
 * Refetches whenever the global `version` changes (e.g. after a signing).
 */

import { useEffect, useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import type { PlayerSummary, SquadResponse } from '@/api/types';
import { ProgressBar } from '@/components/ui/ProgressBar';
import {
  positionGroupColor,
  ratingBadgeClasses,
  ratingTextColor,
} from '@/lib/format';
import { useGame } from '@/state/GameContext';

function SectorChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-800/60 px-3 py-1.5 text-center">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`font-mono text-base font-extrabold ${ratingTextColor(value)}`}>
        {value.toFixed(1)}
      </p>
    </div>
  );
}

function PlayerRow({ player }: { player: PlayerSummary }) {
  return (
    <tr className="table-row">
      <td className="px-3 py-2.5">
        <span
          className={`inline-flex w-12 justify-center rounded-md px-2 py-1 text-xs font-bold ring-1 ${positionGroupColor(
            player.position,
          )}`}
        >
          {player.position}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-100">{player.name}</span>
          {player.is_injured && (
            <span
              title={`Injured (~${player.injured_for_matchdays} matchdays)`}
              className="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-bold text-rose-300"
            >
              INJ
            </span>
          )}
        </div>
        <p className="text-[11px] text-slate-500">{player.nationality}</p>
      </td>
      <td className="px-3 py-2.5 text-center font-mono text-sm text-slate-300">{player.age}</td>
      <td className="px-3 py-2.5 text-center">
        <span
          className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-sm font-extrabold ring-1 ${ratingBadgeClasses(
            player.overall,
          )}`}
        >
          {player.overall}
        </span>
      </td>
      <td className="px-3 py-2.5 text-center">
        <span className={`font-mono text-sm font-bold ${ratingTextColor(player.potential)}`}>
          {player.potential}
        </span>
      </td>
      <td className="w-44 px-3 py-2.5">
        <ProgressBar value={player.fitness} />
      </td>
      <td className="px-3 py-2.5 text-center">
        <span className="font-mono text-sm text-slate-300">{Math.round(player.form)}</span>
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-sm font-semibold text-emerald-400">
        {player.market_value_label}
      </td>
    </tr>
  );
}

export function SquadManager() {
  const { version } = useGame();
  const [squad, setSquad] = useState<SquadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    gameApi
      .getSquad()
      .then((data) => {
        if (active) {
          setSquad(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof ApiError ? err.message : 'Failed to load squad.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [version]);

  return (
    <section className="panel animate-fade-in-up">
      <div className="panel-header">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">
            Squad Manager
          </h2>
          <p className="text-xs text-slate-500">
            {squad ? `${squad.player_count} registered players · ${squad.formation}` : 'Loading…'}
          </p>
        </div>
        {squad && (
          <div className="grid grid-cols-4 gap-2">
            <SectorChip label="ATT" value={squad.attack_rating} />
            <SectorChip label="MID" value={squad.midfield_rating} />
            <SectorChip label="DEF" value={squad.defence_rating} />
            <SectorChip label="GK" value={squad.goalkeeper_rating} />
          </div>
        )}
      </div>

      <div className="max-h-[560px] overflow-auto">
        {error ? (
          <p className="px-5 py-8 text-center text-sm text-rose-400">{error}</p>
        ) : loading && !squad ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">Loading roster…</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 bg-slate-900/95 backdrop-blur">
              <tr className="text-[10px] uppercase tracking-widest text-slate-500">
                <th className="px-3 py-2.5 font-semibold">Pos</th>
                <th className="px-3 py-2.5 font-semibold">Player</th>
                <th className="px-3 py-2.5 text-center font-semibold">Age</th>
                <th className="px-3 py-2.5 text-center font-semibold">OVR</th>
                <th className="px-3 py-2.5 text-center font-semibold">POT</th>
                <th className="px-3 py-2.5 font-semibold">Fitness</th>
                <th className="px-3 py-2.5 text-center font-semibold">Form</th>
                <th className="px-3 py-2.5 text-right font-semibold">Value</th>
              </tr>
            </thead>
            <tbody>
              {squad?.players.map((player) => (
                <PlayerRow key={player.player_id} player={player} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
