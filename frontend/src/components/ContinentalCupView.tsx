/**
 * ContinentalCupView — European Champions Cup standings, bracket and fixtures.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import type { ContinentalCupResponse } from '@/api/types';
import { useGame } from '@/state/GameContext';
import { useToast } from '@/state/ToastProvider';

type SubTab = 'standings' | 'fixtures' | 'bracket';

const STAGE_LABELS: Record<string, string> = {
  group: 'Group Stage',
  quarter_final: 'Quarter-Final',
  semi_final: 'Semi-Final',
  final: 'Final',
};

export function ContinentalCupView() {
  const { version, status } = useGame();
  const { push } = useToast();
  const [data, setData] = useState<ContinentalCupResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [subTab, setSubTab] = useState<SubTab>('standings');

  const loadCup = useCallback(async () => {
    setLoading(true);
    try {
      const response = await gameApi.getContinentalCup();
      setData(response);
    } catch (err) {
      push('error', 'Champions Cup', err instanceof ApiError ? err.message : 'Load failed');
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void loadCup();
  }, [loadCup, version]);

  const matchdays = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.fixtures.map((fixture) => fixture.matchday))).sort(
      (a, b) => a - b,
    );
  }, [data]);

  if (loading && !data) {
    return <p className="py-16 text-center text-sm text-slate-500">Loading Champions Cup…</p>;
  }

  if (!data || !data.active) {
    return (
      <section className="panel-glow animate-fade-in-up p-8 text-center">
        <p className="text-lg font-bold text-slate-200">{data?.name ?? 'European Champions Cup'}</p>
        <p className="mt-2 text-sm text-slate-500">
          No active continental tournament this season.
        </p>
      </section>
    );
  }

  return (
    <section className="panel-glow animate-fade-in-up overflow-hidden">
      <div className="panel-header flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">
            {data.name}
          </h2>
          <p className="text-xs text-slate-500">
            Season {data.season_year}
            {status?.club_name ? ` · ${status.club_name}` : ''}
            {data.qualified ? ' · Qualified' : ' · Not qualified'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge label="Phase" value={STAGE_LABELS[data.phase] ?? data.phase} />
          <Badge
            label="Matchday"
            value={`${data.current_matchday} / ${data.total_matchdays}`}
          />
          {data.champion_club_name && (
            <Badge label="Champion" value={data.champion_club_name} accent />
          )}
        </div>
      </div>

      <nav className="flex gap-2 border-b border-slate-800/80 px-4 py-3">
        {(
          [
            { id: 'standings' as const, label: 'Group Standings' },
            { id: 'fixtures' as const, label: 'Matchdays' },
            { id: 'bracket' as const, label: 'Knockout Bracket' },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSubTab(tab.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wide transition-colors ${
              subTab === tab.id
                ? 'bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/40'
                : 'text-slate-500 hover:bg-slate-800/60 hover:text-slate-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="p-4">
        {subTab === 'standings' && (
          <div className="grid gap-4 md:grid-cols-2">
            {data.groups.map((group) => (
              <div
                key={group.group_name}
                className="overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40"
              >
                <p className="border-b border-slate-800/80 bg-slate-900/80 px-4 py-2 text-xs font-bold uppercase tracking-widest text-emerald-300">
                  Group {group.group_name}
                </p>
                <table className="w-full text-left text-xs">
                  <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-3 py-2">#</th>
                      <th className="px-3 py-2">Club</th>
                      <th className="px-3 py-2 text-center">P</th>
                      <th className="px-3 py-2 text-center">GD</th>
                      <th className="px-3 py-2 text-center">Pts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.standings.map((row) => (
                      <tr
                        key={row.club_id}
                        className={`border-t border-slate-800/50 ${
                          row.club_id === status?.club_id ? 'bg-cyan-500/10' : ''
                        }`}
                      >
                        <td className="px-3 py-2 font-mono text-slate-400">{row.position}</td>
                        <td className="px-3 py-2 font-medium text-slate-200">{row.club_name}</td>
                        <td className="px-3 py-2 text-center text-slate-400">{row.played}</td>
                        <td className="px-3 py-2 text-center text-slate-400">{row.goal_difference}</td>
                        <td className="px-3 py-2 text-center font-bold text-emerald-300">
                          {row.points}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}

        {subTab === 'fixtures' && (
          <div className="space-y-4">
            <p className="text-[11px] text-slate-500">
              Mid-week rounds align with domestic matchdays:{' '}
              {data.schedule_anchors.join(', ')}
            </p>
            {matchdays.map((matchday) => {
              const roundFixtures = data.fixtures.filter(
                (fixture) => fixture.matchday === matchday,
              );
              return (
                <div
                  key={matchday}
                  className="overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/40"
                >
                  <p className="border-b border-slate-800/80 bg-slate-900/80 px-4 py-2 text-xs font-bold uppercase tracking-widest text-cyan-300">
                    Continental MD {matchday}
                    {roundFixtures[0]?.league_matchday
                      ? ` · League MD ${roundFixtures[0].league_matchday}`
                      : ''}
                  </p>
                  <div className="divide-y divide-slate-800/50">
                    {roundFixtures.map((fixture) => (
                      <div
                        key={`${fixture.home_id}-${fixture.away_id}-${fixture.stage}`}
                        className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                          {fixture.group_name
                            ? `Group ${fixture.group_name}`
                            : STAGE_LABELS[fixture.stage] ?? fixture.stage}
                        </span>
                        <span className="font-medium text-slate-200">
                          {fixture.home_name}
                          <span className="mx-2 font-mono text-cyan-300">
                            {fixture.is_played
                              ? `${fixture.home_goals} - ${fixture.away_goals}`
                              : 'vs'}
                          </span>
                          {fixture.away_name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {subTab === 'bracket' && (
          <div className="space-y-3">
            {data.bracket.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">
                Knockout bracket unlocks after the group stage.
              </p>
            ) : (
              data.bracket.map((match) => (
                <div
                  key={`${match.stage}-${match.home_id}-${match.away_id}-${match.matchday}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3"
                >
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-amber-300">
                      {STAGE_LABELS[match.stage] ?? match.stage} · MD {match.matchday}
                    </p>
                    <p className="mt-1 text-sm text-slate-200">
                      {match.home_name}{' '}
                      <span className="font-mono text-cyan-300">
                        {match.home_goals !== null && match.away_goals !== null
                          ? `${match.home_goals} - ${match.away_goals}`
                          : 'vs'}
                      </span>{' '}
                      {match.away_name}
                    </p>
                  </div>
                  {match.winner_name && (
                    <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-bold text-emerald-300 ring-1 ring-emerald-500/30">
                      {match.winner_name}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function Badge({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg px-3 py-1.5 ${
        accent ? 'bg-amber-500/15 ring-1 ring-amber-500/30' : 'bg-slate-800/60'
      }`}
    >
      <p className="text-[9px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`font-semibold ${accent ? 'text-amber-200' : 'text-slate-200'}`}>{value}</p>
    </div>
  );
}
