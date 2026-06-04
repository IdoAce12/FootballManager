/**
 * GameOnboarding — career setup screen.
 *
 * Shown whenever no career is initialized. Collects manager name, league and
 * club (the league/club dropdowns are populated dynamically from the backend)
 * and POSTs to /api/game/setup via the GameContext. On success the context
 * flips `initialized` and the app transitions to the dashboard.
 */

import { useEffect, useState, type ReactNode } from 'react';
import { API_BASE_URL, ApiError, gameApi } from '@/api/client';
import type { ClubOption, LeagueOption } from '@/api/types';
import { ratingTextColor } from '@/lib/format';
import { useGame } from '@/state/GameContext';

export function GameOnboarding() {
  const { setupGame } = useGame();

  const [managerName, setManagerName] = useState('');
  const [leagues, setLeagues] = useState<LeagueOption[]>([]);
  const [leagueId, setLeagueId] = useState<number | ''>('');
  const [clubs, setClubs] = useState<ClubOption[]>([]);
  const [clubId, setClubId] = useState<number | ''>('');

  const [loadingLeagues, setLoadingLeagues] = useState(true);
  const [loadingClubs, setLoadingClubs] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load leagues on mount.
  useEffect(() => {
    let active = true;
    setLoadingLeagues(true);
    gameApi
      .getLeagues()
      .then((data) => {
        if (active) {
          setLeagues(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof ApiError
              ? err.message
              : API_BASE_URL
                ? `Could not load leagues. Is the backend running at ${API_BASE_URL}?`
                : 'Could not load leagues. Set VITE_API_URL to your deployed API URL.',
          );
        }
      })
      .finally(() => {
        if (active) setLoadingLeagues(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // Load clubs whenever the selected league changes.
  useEffect(() => {
    if (leagueId === '') {
      setClubs([]);
      setClubId('');
      return;
    }
    let active = true;
    setLoadingClubs(true);
    setClubId('');
    gameApi
      .getLeagueClubs(Number(leagueId))
      .then((data) => {
        if (active) setClubs(data);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof ApiError ? err.message : 'Could not load clubs.');
          setClubs([]);
        }
      })
      .finally(() => {
        if (active) setLoadingClubs(false);
      });
    return () => {
      active = false;
    };
  }, [leagueId]);

  const selectedClub = clubs.find((c) => c.club_team_id === clubId) ?? null;
  const canSubmit =
    managerName.trim().length > 0 && leagueId !== '' && clubId !== '' && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const ok = await setupGame({
      manager_name: managerName.trim(),
      league_id: Number(leagueId),
      club_team_id: Number(clubId),
    });
    if (!ok) {
      setError('Setup was rejected by the server. Please try again.');
      setSubmitting(false);
    }
    // On success the GameContext flips `initialized` and App unmounts this view.
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      {/* Ambient pitch glow */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 -top-40 h-96 w-96 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-emerald-500/20 blur-3xl" />
      </div>

      <div className="relative w-full max-w-lg animate-fade-in-up">
        <div className="rounded-3xl border border-slate-700/60 bg-slate-900/60 p-8 shadow-2xl backdrop-blur-xl">
          {/* Brand */}
          <div className="mb-7 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-emerald-500 text-2xl font-black text-slate-950 shadow-glow">
              FC
            </div>
            <h1 className="text-2xl font-black tracking-tight text-white">
              Start Your Career
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Choose your club and take control of the dugout.
            </p>
          </div>

          {error && (
            <div className="mb-5 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-200">
              {error}
            </div>
          )}

          <div className="space-y-5">
            {/* Manager name */}
            <Field label="Manager Name">
              <input
                value={managerName}
                onChange={(e) => setManagerName(e.target.value)}
                maxLength={40}
                placeholder="e.g. Alex Ferguson"
                className="onboarding-input"
              />
            </Field>

            {/* League select */}
            <Field label="Select League">
              <select
                value={leagueId}
                onChange={(e) =>
                  setLeagueId(e.target.value === '' ? '' : Number(e.target.value))
                }
                disabled={loadingLeagues}
                className="onboarding-input"
              >
                <option value="">
                  {loadingLeagues ? 'Loading leagues…' : 'Choose a league…'}
                </option>
                {leagues.map((lg) => (
                  <option key={lg.league_id} value={lg.league_id}>
                    {lg.league_name} · {lg.club_count} clubs
                  </option>
                ))}
              </select>
            </Field>

            {/* Club select */}
            <Field label="Select Club">
              <select
                value={clubId}
                onChange={(e) =>
                  setClubId(e.target.value === '' ? '' : Number(e.target.value))
                }
                disabled={leagueId === '' || loadingClubs}
                className="onboarding-input"
              >
                <option value="">
                  {leagueId === ''
                    ? 'Select a league first…'
                    : loadingClubs
                      ? 'Loading clubs…'
                      : 'Choose your club…'}
                </option>
                {clubs.map((c) => (
                  <option key={c.club_team_id} value={c.club_team_id}>
                    {c.club_name} (OVR {c.overall.toFixed(0)})
                  </option>
                ))}
              </select>
            </Field>

            {/* Selected club preview */}
            {selectedClub && (
              <div className="flex items-center justify-between rounded-xl border border-slate-700/60 bg-slate-800/40 px-4 py-3 animate-fade-in-up">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">
                    Your Club
                  </p>
                  <p className="text-lg font-extrabold text-white">
                    {selectedClub.club_name}
                  </p>
                </div>
                <div className="flex items-center gap-4 text-right">
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-500">
                      Squad OVR
                    </p>
                    <p className={`font-mono text-xl font-black ${ratingTextColor(selectedClub.overall)}`}>
                      {selectedClub.overall.toFixed(1)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-500">
                      Budget
                    </p>
                    <p className="font-mono text-base font-bold text-emerald-400">
                      {selectedClub.transfer_budget_label}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className={`btn btn-launch w-full py-3.5 text-base ${
                canSubmit ? 'animate-pulse-ring' : ''
              }`}
            >
              {submitting ? 'INITIALIZING…' : '⚡ INITIALIZE CAREER'}
            </button>
          </div>
        </div>

        <p className="mt-4 text-center text-xs text-slate-600">
          FC26 Football Manager · 18,000+ real players · Enterprise Engine
        </p>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-widest text-slate-400">
        {label}
      </span>
      {children}
    </label>
  );
}
