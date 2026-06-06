/**
 * MatchSimTerminal — progressive live matchday ticker.
 * Preview on simulate; commit via POST /api/matchday/confirm when the user returns to desk.
 */

import { motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import { PromotionOverlay } from '@/components/PromotionOverlay';
import type { MatchEventModel, NextSeasonResponse, SimulateResponse, StandingRow } from '@/api/types';
import { formatMoney } from '@/lib/format';
import { useGame } from '@/state/GameContext';
import { useToast } from '@/state/ToastProvider';

const MATCH_REWARD_WIN = 3_000_000;
const MATCH_REWARD_DRAW = 1_000_000;

const TICK_INTERVAL_MS = 1500;

interface MatchSimTerminalProps {
  onReturnToDesk?: () => void;
}

interface LiveScore {
  home: number;
  away: number;
  homeName: string;
  awayName: string;
}

interface MatchRewards {
  pointsEarned: number;
  resultLabel: string;
  leaguePosition: number;
  totalPoints: number;
  goalDifference: number;
  matchRewardAmount: number;
  matchRewardLabel: string;
  matchRewardOutcome: string;
}

function isFullTimeEvent(ev: MatchEventModel): boolean {
  const t = ev.type.toLowerCase().replace(/\s+/g, '');
  return t === 'full-time' || t === 'fulltime';
}

function eventStyle(type: string): { row: string; tag: string; label: string } {
  switch (type) {
    case 'Goal':
      return { row: 'bg-emerald-500/10 border-emerald-500/40', tag: 'text-emerald-300', label: 'GOAL' };
    case 'Red card':
      return { row: 'bg-rose-500/10 border-rose-500/40', tag: 'text-rose-300', label: 'RED' };
    case 'Yellow card':
      return { row: 'border-slate-800', tag: 'text-yellow-300', label: 'YEL' };
    case 'Save':
      return { row: 'border-slate-800', tag: 'text-cyan-300', label: 'SAVE' };
    case 'Injury':
      return { row: 'border-slate-800', tag: 'text-orange-300', label: 'INJ' };
    case 'Full-time':
      return { row: 'bg-slate-800/60 border-slate-700', tag: 'text-slate-200', label: 'FT' };
    case 'Half-time':
      return { row: 'bg-slate-800/40 border-slate-700', tag: 'text-slate-300', label: 'HT' };
    case 'Kick-off':
      return { row: 'border-slate-800', tag: 'text-slate-400', label: 'KO' };
    default:
      return { row: 'border-slate-800', tag: 'text-slate-500', label: '•' };
  }
}

function StatBar({
  label,
  home,
  away,
  homeName,
  awayName,
}: {
  label: string;
  home: number;
  away: number;
  homeName: string;
  awayName: string;
}) {
  const total = home + away || 1;
  const homePct = (home / total) * 100;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] text-slate-400">
        <span className="font-mono font-bold text-slate-200">{home}</span>
        <span className="uppercase tracking-wider">{label}</span>
        <span className="font-mono font-bold text-slate-200">{away}</span>
      </div>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className="bg-cyan-500" style={{ width: `${homePct}%` }} title={homeName} />
        <div className="bg-emerald-500" style={{ width: `${100 - homePct}%` }} title={awayName} />
      </div>
    </div>
  );
}

function parseScoreFromGoalDescription(desc: string): { home: number; away: number } | null {
  const m = desc.match(/\((\d+)-(\d+)\)/);
  if (!m) return null;
  return { home: Number(m[1]), away: Number(m[2]) };
}

function computeRewards(
  result: SimulateResponse,
  userClubId: number,
  preMatchPoints: number,
): MatchRewards | null {
  if (!result.user_match_played || !result.home_stats || !result.away_stats) return null;

  const isHome = result.home_stats.club_id === userClubId;
  const hg = result.home_stats.goals;
  const ag = result.away_stats.goals;
  let pointsEarned = 0;
  let resultLabel = 'Draw';
  if (hg > ag) {
    pointsEarned = isHome ? 3 : 0;
    resultLabel = isHome ? 'Victory' : 'Defeat';
  } else if (ag > hg) {
    pointsEarned = isHome ? 0 : 3;
    resultLabel = isHome ? 'Defeat' : 'Victory';
  } else {
    pointsEarned = 1;
  }

  const row: StandingRow | undefined = result.standings.find((s) => s.club_id === userClubId);

  let matchRewardAmount = MATCH_REWARD_DRAW;
  let matchRewardOutcome = 'draw';
  if (hg > ag) {
    matchRewardAmount = isHome ? MATCH_REWARD_WIN : 0;
    matchRewardOutcome = isHome ? 'win' : 'loss';
  } else if (ag > hg) {
    matchRewardAmount = isHome ? 0 : MATCH_REWARD_WIN;
    matchRewardOutcome = isHome ? 'loss' : 'win';
  }

  const matchRewardLabel =
    matchRewardAmount > 0 ? `+${formatMoney(matchRewardAmount)}` : '€0';

  return {
    pointsEarned,
    resultLabel,
    leaguePosition: row?.position ?? 0,
    totalPoints: row?.points ?? preMatchPoints + pointsEarned,
    goalDifference: row?.goal_difference ?? 0,
    matchRewardAmount,
    matchRewardLabel,
    matchRewardOutcome,
  };
}

function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/50 bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-widest text-emerald-300">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
      </span>
      Live
    </span>
  );
}

export function MatchSimTerminal({ onReturnToDesk }: MatchSimTerminalProps) {
  const { commitMatchdayAndSync, status, invalidate } = useGame();
  const { push } = useToast();

  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [revealed, setRevealed] = useState<MatchEventModel[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [isFinished, setIsFinished] = useState(false);
  const [liveScore, setLiveScore] = useState<LiveScore | null>(null);
  const [preMatchPoints, setPreMatchPoints] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [awaitingConfirm, setAwaitingConfirm] = useState(false);
  const [advancingSeason, setAdvancingSeason] = useState(false);
  const [seasonRecap, setSeasonRecap] = useState<NextSeasonResponse | null>(null);
  const [promotionOverlay, setPromotionOverlay] = useState<NextSeasonResponse | null>(null);
  const [confirmedCashReward, setConfirmedCashReward] = useState<string | null>(null);
  const [goalFlash, setGoalFlash] = useState(false);

  const feedRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const eventsRef = useRef<MatchEventModel[]>([]);
  const streamIndexRef = useRef(0);

  const userClubId = status?.club_id ?? -1;
  const serverPending = Boolean(status?.pending_matchday);
  const mustConfirmBeforeNext = awaitingConfirm || serverPending;

  const rewards = useMemo(
    () => (result && isFinished ? computeRewards(result, userClubId, preMatchPoints) : null),
    [result, isFinished, userClubId, preMatchPoints],
  );

  const clearStreamTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const markStreamFinished = useCallback(() => {
    clearStreamTimer();
    setStreaming(false);
    setIsFinished(true);
  }, [clearStreamTimer]);

  const resetTerminalView = useCallback(() => {
    clearStreamTimer();
    setResult(null);
    setRevealed([]);
    setStreaming(false);
    setIsFinished(false);
    setLiveScore(null);
    setAwaitingConfirm(false);
    setConfirmedCashReward(null);
    eventsRef.current = [];
    streamIndexRef.current = 0;
  }, [clearStreamTimer]);

  const revealEvent = useCallback((ev: MatchEventModel) => {
    setRevealed((prev) => [...prev, ev]);

    if (ev.type === 'Goal') {
      setGoalFlash(true);
      window.setTimeout(() => setGoalFlash(false), 700);
      const parsed = parseScoreFromGoalDescription(ev.description);
      if (parsed) {
        setLiveScore((prev) => (prev ? { ...prev, home: parsed.home, away: parsed.away } : prev));
      }
    }

    if (isFullTimeEvent(ev)) {
      markStreamFinished();
    }
  }, [markStreamFinished]);

  const startEventStream = useCallback(
    (data: SimulateResponse) => {
      clearStreamTimer();
      setRevealed([]);
      setIsFinished(false);
      setStreaming(false);
      eventsRef.current = data.events;
      streamIndexRef.current = 0;

      const events = data.events;
      if (events.length === 0) {
        markStreamFinished();
        return;
      }

      if (data.home_stats && data.away_stats) {
        setLiveScore({
          home: 0,
          away: 0,
          homeName: data.home_stats.name,
          awayName: data.away_stats.name,
        });
      }

      setStreaming(true);

      const tick = () => {
        const idx = streamIndexRef.current;
        if (idx >= events.length) {
          markStreamFinished();
          return;
        }

        const ev = events[idx];
        streamIndexRef.current = idx + 1;
        revealEvent(ev);

        if (streamIndexRef.current >= events.length) {
          markStreamFinished();
        }
      };

      // First event immediately — avoids waiting one tick before any commentary.
      tick();
      if (streamIndexRef.current < events.length) {
        timerRef.current = window.setInterval(tick, TICK_INTERVAL_MS);
      }
    },
    [clearStreamTimer, markStreamFinished, revealEvent],
  );

  useEffect(() => () => clearStreamTimer(), [clearStreamTimer]);

  useEffect(() => {
    if (status?.pending_matchday) {
      setAwaitingConfirm(true);
    }
  }, [status?.pending_matchday]);

  /** Safety net: unlock UI when every log line is on screen (fixes off-by-one / timer races). */
  useEffect(() => {
    if (!result) return;
    const total = result.events.length;
    if (total === 0) {
      if (!isFinished) markStreamFinished();
      return;
    }
    if (revealed.length >= total && !isFinished) {
      markStreamFinished();
    }
  }, [result, revealed.length, isFinished, markStreamFinished]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' });
  }, [revealed]);

  const launch = async () => {
    if (mustConfirmBeforeNext) {
      push(
        'error',
        'Uncommitted matchday',
        'Confirm your last match results with RETURN TO MANAGER DESK before simulating again.',
      );
      return;
    }

    setRunning(true);
    resetTerminalView();
    setPreMatchPoints(status?.points ?? 0);

    try {
      const data = await gameApi.simulateMatchday();
      setResult(data);
      setAwaitingConfirm(true);
      startEventStream(data);

      if (data.season_complete && !data.user_match_played) {
        push('info', 'Season complete', 'All matchdays have been played.');
        markStreamFinished();
      }
    } catch (err) {
      push('error', 'Simulation failed', err instanceof ApiError ? err.message : 'Unknown error.');
    } finally {
      setRunning(false);
    }
  };

  const returnToDesk = async () => {
    const canCommit = result === null ? mustConfirmBeforeNext : isFinished;
    if (!canCommit || confirming) return;

    setConfirming(true);
    clearStreamTimer();

    try {
      const confirmed = await commitMatchdayAndSync();
      if (!confirmed.committed) {
        throw new ApiError('Server did not commit the matchday.', 500);
      }

      const leagueCash =
        confirmed.match_reward > 0
          ? ` League reward ${confirmed.match_reward_label}.`
          : '';
      const continentalCash =
        confirmed.continental_match_played && (confirmed.continental_match_reward ?? 0) > 0
          ? ` Champions Cup reward ${confirmed.continental_match_reward_label}.`
          : '';
      const totalRewardLabel =
        (confirmed.continental_match_reward ?? 0) > 0
          ? `${confirmed.match_reward_label} + ${confirmed.continental_match_reward_label}`
          : confirmed.match_reward_label;
      setConfirmedCashReward(totalRewardLabel);
      push(
        'success',
        'Matchday confirmed',
        `Matchweek ${confirmed.matchday} recorded.${leagueCash}${continentalCash}`,
      );

      resetTerminalView();
      await invalidate();
      onReturnToDesk?.();
    } catch (err) {
      push(
        'error',
        'Confirm failed',
        err instanceof ApiError ? err.message : 'Could not commit matchday.',
      );
    } finally {
      setConfirming(false);
    }
  };

  const proceedToNextSeason = async () => {
    if (!isFinished || advancingSeason) return;

    setAdvancingSeason(true);
    clearStreamTimer();

    try {
      if (mustConfirmBeforeNext) {
        const confirmed = await commitMatchdayAndSync();
        if (!confirmed.committed) {
          throw new ApiError('Server did not commit the final matchday.', 500);
        }
        if (confirmed.match_reward > 0) {
          setConfirmedCashReward(confirmed.match_reward_label);
        }
      }

      const recap = await gameApi.advanceNextSeason();
      setSeasonRecap(recap);
      push('success', `Season ${recap.new_season_year}`, recap.message);

      if (recap.promoted) {
        setPromotionOverlay(recap);
      } else {
        resetTerminalView();
        await invalidate();
        onReturnToDesk?.();
      }
    } catch (err) {
      push(
        'error',
        'Season transition failed',
        err instanceof ApiError ? err.message : 'Could not start the new season.',
      );
    } finally {
      setAdvancingSeason(false);
    }
  };

  const displayScore =
    isFinished && result?.scoreline
      ? result.scoreline
      : liveScore
        ? `${liveScore.homeName} ${liveScore.home} - ${liveScore.away} ${liveScore.awayName}`
        : null;

  const showPostMatchPanel = isFinished && result !== null;
  const showServerPendingBanner = mustConfirmBeforeNext && !result;
  const isLastMatchweek =
    result !== null && result.total_matchdays > 0 && result.matchday >= result.total_matchdays;
  /** After a live sim, wait for isFinished; for server-only pending, allow commit immediately. */
  const deskButtonDisabled = confirming || (result !== null && !isFinished);
  const seasonButtonDisabled = deskButtonDisabled || advancingSeason;

  const dismissPromotionOverlay = async () => {
    setPromotionOverlay(null);
    resetTerminalView();
    await invalidate();
    onReturnToDesk?.();
  };

  return (
    <div className="space-y-5">
      <PromotionOverlay
        open={promotionOverlay !== null}
        leagueName={promotionOverlay?.promotion_to_league ?? promotionOverlay?.new_league_name}
        onDismiss={() => void dismissPromotionOverlay()}
      />
      {mustConfirmBeforeNext && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-5 py-3 text-sm text-amber-100">
          <span className="font-bold">Results awaiting confirmation.</span> The league calendar
          will not advance until you commit this matchday.
          {showServerPendingBanner && (
            <button
              type="button"
              onClick={() => void returnToDesk()}
              disabled={deskButtonDisabled}
              className={`btn mt-3 w-full py-2 text-xs font-bold ${
                isFinished
                  ? 'border border-emerald-400/60 bg-emerald-500 text-slate-950 shadow-glow hover:bg-emerald-400'
                  : 'border border-cyan-500/40 bg-cyan-500/10 text-cyan-300'
              }`}
            >
              {confirming ? 'COMMITTING…' : 'COMMIT MATCHDAY & RETURN TO DESK'}
            </button>
          )}
        </div>
      )}

      <div className="panel-glow flex flex-col items-center gap-3 p-6 text-center">
        <button
          type="button"
          onClick={() => void launch()}
          disabled={running || streaming || mustConfirmBeforeNext}
          className={`btn btn-launch px-10 py-4 text-base ${
            running || streaming || mustConfirmBeforeNext ? '' : 'animate-pulse-ring'
          }`}
        >
          {running
            ? 'SIMULATING MATCHDAY…'
            : streaming
              ? 'MATCH IN PROGRESS…'
              : mustConfirmBeforeNext
                ? 'CONFIRM LAST MATCHDAY FIRST'
                : '⚽ LAUNCH SIMULATION MATCHDAY'}
        </button>
        <p className="text-xs text-slate-500">
          Every league fixture resolves concurrently — your match streams live below.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel-glow animate-fade-in-up">
          <div className="panel-header">
            <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">
              Results &amp; Standings
            </h2>
            {result && (
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-bold text-slate-300">
                MD {result.matchday}/{result.total_matchdays}
              </span>
            )}
          </div>

          {!result ? (
            <p className="px-5 py-12 text-center text-sm text-slate-600">
              Launch a matchday to see scores and the updated table.
            </p>
          ) : !showPostMatchPanel ? (
            <div className="flex flex-col items-center justify-center gap-4 px-5 py-16">
              {displayScore && (
                <div className="text-center">
                  <div className="mb-2 flex items-center justify-center gap-2">
                    <p className="text-[10px] uppercase tracking-widest text-slate-500">Live Score</p>
                    {(streaming || running) && <LiveBadge />}
                  </div>
                  <p className="text-2xl font-black text-white">{displayScore}</p>
                </div>
              )}
              <p className="max-w-xs text-center text-sm text-slate-500">
                Full results and league standings unlock at the final whistle…
              </p>
              <div className="h-1 w-32 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full w-1/2 animate-pulse bg-cyan-500/60" />
              </div>
            </div>
          ) : (
            <div className="space-y-4 p-4">
              {result.scoreline && (
                <div
                  className={`rounded-xl bg-gradient-to-r from-cyan-500/10 to-emerald-500/10 p-4 ring-1 ring-slate-700 ${
                    goalFlash ? 'animate-goal-shake animate-score-flash' : ''
                  }`}
                >
                  <div className="flex items-center justify-center gap-2">
                    <p className="text-[10px] uppercase tracking-widest text-slate-500">Final Score</p>
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-slate-400">
                      FT
                    </span>
                  </div>
                  <motion.p
                    key={result.scoreline}
                    className="mt-1 text-center text-xl font-black text-white"
                    animate={goalFlash ? { scale: [1, 1.08, 1] } : { scale: 1 }}
                    transition={{ duration: 0.35 }}
                  >
                    {result.scoreline}
                  </motion.p>
                  {result.home_stats && result.away_stats && (
                    <div className="mt-3 space-y-2">
                      <StatBar
                        label="Possession %"
                        home={Math.round(result.home_stats.possession_pct)}
                        away={Math.round(result.away_stats.possession_pct)}
                        homeName={result.home_stats.name}
                        awayName={result.away_stats.name}
                      />
                      <StatBar
                        label="Shots"
                        home={result.home_stats.shots}
                        away={result.away_stats.shots}
                        homeName={result.home_stats.name}
                        awayName={result.away_stats.name}
                      />
                      <StatBar
                        label="On Target"
                        home={result.home_stats.shots_on_target}
                        away={result.away_stats.shots_on_target}
                        homeName={result.home_stats.name}
                        awayName={result.away_stats.name}
                      />
                    </div>
                  )}
                </div>
              )}

              {rewards && (
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
                  <div className="match-reward-badge mb-4">
                    <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-300/90">
                      Match Reward
                    </p>
                    <p className="mt-1 font-mono text-xl font-black text-emerald-300 drop-shadow-[0_0_12px_rgba(52,211,153,0.8)]">
                      {confirmedCashReward ?? rewards.matchRewardLabel}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      {confirmedCashReward
                        ? 'Credited to transfer budget'
                        : 'Paid on confirm · Win €3.0M · Draw €1.0M'}
                    </p>
                  </div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400">
                    Matchday Payout
                  </p>
                  <p className="mt-1 text-lg font-black text-white">{rewards.resultLabel}</p>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                    <div className="rounded-lg bg-slate-900/50 py-2">
                      <p className="text-slate-500">Points</p>
                      <p className="font-mono text-lg font-bold text-cyan-300">+{rewards.pointsEarned}</p>
                    </div>
                    <div className="rounded-lg bg-slate-900/50 py-2">
                      <p className="text-slate-500">Total</p>
                      <p className="font-mono text-lg font-bold text-white">{rewards.totalPoints}</p>
                    </div>
                    <div className="rounded-lg bg-slate-900/50 py-2">
                      <p className="text-slate-500">Position</p>
                      <p className="font-mono text-lg font-bold text-emerald-300">
                        #{rewards.leaguePosition}
                      </p>
                    </div>
                  </div>
                  <p className="mt-2 text-center text-[11px] text-slate-400">
                    Goal difference {rewards.goalDifference >= 0 ? '+' : ''}
                    {rewards.goalDifference} · Board confidence updated
                  </p>
                </div>
              )}

              {result.other_results.length > 0 && (
                <div>
                  <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                    Other Results
                  </p>
                  <div className="grid gap-1">
                    {result.other_results.map((r, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-md bg-slate-800/40 px-3 py-1.5 text-xs"
                      >
                        <span className="truncate text-right text-slate-300" style={{ flex: 1 }}>
                          {r.home}
                        </span>
                        <span className="mx-3 flex-none font-mono font-bold text-slate-100">
                          {r.home_goals} - {r.away_goals}
                        </span>
                        <span className="truncate text-slate-300" style={{ flex: 1 }}>
                          {r.away}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                  League Table
                </p>
                <div className="max-h-[220px] overflow-auto rounded-lg ring-1 ring-slate-800">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-slate-900/95 text-[10px] uppercase tracking-wider text-slate-500">
                      <tr>
                        <th className="px-2 py-1.5">#</th>
                        <th className="px-2 py-1.5">Club</th>
                        <th className="px-2 py-1.5 text-center">P</th>
                        <th className="px-2 py-1.5 text-center">GD</th>
                        <th className="px-2 py-1.5 text-center">Pts</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.standings.map((row) => (
                        <tr
                          key={row.club_id}
                          className={`border-b border-slate-800/50 hover:bg-slate-800/40 ${
                            row.club_id === userClubId ? 'bg-cyan-500/10' : ''
                          }`}
                        >
                          <td className="px-2 py-1.5 font-mono text-slate-500">{row.position}</td>
                          <td className="px-2 py-1.5 font-medium text-slate-200">{row.club_name}</td>
                          <td className="px-2 py-1.5 text-center font-mono text-slate-400">
                            {row.played}
                          </td>
                          <td className="px-2 py-1.5 text-center font-mono text-slate-400">
                            {row.goal_difference > 0
                              ? `+${row.goal_difference}`
                              : row.goal_difference}
                          </td>
                          <td className="px-2 py-1.5 text-center font-mono font-bold text-cyan-300">
                            {row.points}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {seasonRecap && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">
                  <p className="font-bold text-amber-300">Season Recap</p>
                  <p className="mt-1">{seasonRecap.message}</p>
                  <p className="mt-2 text-xs text-slate-300">
                    Board bonus {seasonRecap.budget_bonus_label} · New budget{' '}
                    {seasonRecap.new_transfer_budget_label}
                  </p>
                </div>
              )}

              {isLastMatchweek ? (
                <button
                  type="button"
                  onClick={() => void proceedToNextSeason()}
                  disabled={seasonButtonDisabled}
                  className={`btn w-full py-3 text-sm font-extrabold uppercase tracking-wide transition-all ${
                    isFinished && !advancingSeason && !confirming
                      ? 'animate-pulse border border-amber-400/80 bg-gradient-to-r from-amber-400 via-yellow-400 to-amber-500 text-slate-950 shadow-glow hover:from-amber-300 hover:to-yellow-300'
                      : 'border border-amber-500/30 bg-amber-500/10 text-amber-200/60'
                  }`}
                >
                  {advancingSeason || confirming
                    ? 'BEGINNING NEW SEASON…'
                    : '✦ PROCEED TO THE NEXT SEASON'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void returnToDesk()}
                  disabled={deskButtonDisabled}
                  className={`btn w-full py-3 text-sm font-bold transition-all ${
                    isFinished && !confirming
                      ? 'border border-emerald-400/70 bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 shadow-glow hover:from-emerald-400 hover:to-cyan-400'
                      : 'border border-cyan-500/40 bg-cyan-500/10 text-cyan-300'
                  }`}
                >
                  {confirming ? 'COMMITTING RESULTS…' : 'RETURN TO MANAGER DESK'}
                </button>
              )}
            </div>
          )}
        </section>

        <section className="panel-glow flex flex-col animate-fade-in-up">
          <div className="panel-header">
            <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">
              Live Commentary
            </h2>
            <span className="flex items-center gap-2 text-xs text-slate-500">
              {streaming && <LiveBadge />}
              {isFinished && <span className="font-bold text-emerald-400">FULL-TIME</span>}
              {!streaming && !isFinished && !result && 'IDLE'}
            </span>
          </div>

          <div
            ref={feedRef}
            className="h-[460px] space-y-1.5 overflow-auto bg-slate-950/40 p-4 font-mono text-sm"
          >
            {revealed.length === 0 && !result ? (
              <p className="py-16 text-center text-slate-600">
                The match feed will appear here once you kick off.
              </p>
            ) : revealed.length === 0 && running ? (
              <p className="py-16 text-center text-slate-500 animate-pulse">
                Connecting to the match engine…
              </p>
            ) : revealed.length === 0 && result && !result.user_match_played ? (
              <p className="py-16 text-center text-slate-500">
                No user match this round (season may be complete).
              </p>
            ) : (
              revealed.map((ev, idx) => {
                const style = eventStyle(ev.type);
                return (
                  <div
                    key={`${ev.minute}-${ev.type}-${idx}`}
                    className={`flex animate-fade-in-up items-start gap-3 rounded-md border px-3 py-1.5 ${style.row}`}
                  >
                    <span className="w-9 flex-none text-right font-bold text-slate-500">
                      {ev.minute}&apos;
                    </span>
                    <span className={`w-10 flex-none text-[10px] font-extrabold ${style.tag}`}>
                      {style.label}
                    </span>
                    <span className="text-slate-200">{ev.description}</span>
                  </div>
                );
              })
            )}
            {streaming && revealed.length > 0 && (
              <p className="py-2 text-center text-[11px] text-slate-600 animate-pulse">…</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
