/**
 * Trophy Room — manager bio and chronological career achievements.
 */

import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import type { CareerProfileResponse, CareerSeasonRecord } from '@/api/types';
import { useGame } from '@/state/GameContext';

function TrophyCup({ glow }: { glow: boolean }) {
  return (
    <svg
      viewBox="0 0 64 72"
      className={`h-14 w-14 ${glow ? 'trophy-glow' : 'opacity-40 grayscale'}`}
      aria-hidden
    >
      <defs>
        <linearGradient id="cupGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fbbf24" />
          <stop offset="100%" stopColor="#f59e0b" />
        </linearGradient>
      </defs>
      <path
        fill={glow ? 'url(#cupGrad)' : '#475569'}
        d="M16 8h32v6c0 12-6 20-16 22-10-2-16-10-16-22V8zm8 52h16v6H24v-6zm-4 6h24v4H20v-4z"
      />
      <ellipse cx="32" cy="58" rx="14" ry="3" fill={glow ? '#fcd34d' : '#334155'} opacity="0.6" />
    </svg>
  );
}

function earnsTrophy(record: CareerSeasonRecord): boolean {
  return (
    record.status === 'Champions' ||
    record.status === 'Promoted' ||
    (record.status === 'Top Three' && record.final_position <= 3)
  );
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'Champions':
      return 'border-amber-400/50 bg-amber-500/15 text-amber-200';
    case 'Promoted':
      return 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200';
    case 'Top Three':
      return 'border-emerald-400/50 bg-emerald-500/15 text-emerald-200';
    default:
      return 'border-slate-600 bg-slate-800/60 text-slate-400';
  }
}

export function TrophyRoom() {
  const { version } = useGame();
  const [profile, setProfile] = useState<CareerProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await gameApi.getCareerProfile();
        if (!cancelled) {
          setProfile(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load career profile.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [version]);

  if (loading) {
    return (
      <p className="py-16 text-center text-sm text-slate-500">Opening the trophy cabinet…</p>
    );
  }

  if (error) {
    return (
      <div className="panel border-rose-500/40 px-6 py-8 text-center text-rose-200">{error}</div>
    );
  }

  if (!profile) return null;

  return (
    <div className="space-y-6">
      <motion.section
        className="panel-glow px-6 py-6"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-cyan-400/90">
          Manager profile
        </p>
        <h2 className="mt-2 text-2xl font-black text-white">{profile.manager_name}</h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-300">{profile.bio}</p>
        <p className="mt-4 text-xs text-slate-500">
          {profile.trophy_count} illuminated trophy{profile.trophy_count === 1 ? '' : 'ies'} in
          the cabinet
        </p>
      </motion.section>

      <section className="panel-glow">
        <div className="panel-header">
          <h3 className="text-sm font-bold uppercase tracking-widest text-slate-300">
            Trophy Room
          </h3>
        </div>

        {profile.history.length === 0 ? (
          <p className="px-6 py-12 text-center text-sm text-slate-500">
            Complete your first season to begin filling the trophy room.
          </p>
        ) : (
          <ul className="divide-y divide-slate-800/80">
            {profile.history.map((record, idx) => {
              const lit = earnsTrophy(record);
              return (
                <motion.li
                  key={`${record.season_year}-${record.club_name}-${idx}`}
                  className="flex flex-wrap items-center gap-4 px-6 py-5"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.05 }}
                >
                  <TrophyCup glow={lit} />
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-xs text-slate-500">{record.season_year}</p>
                    <p className="font-bold text-white">
                      {record.club_name}{' '}
                      <span className="font-normal text-slate-500">· {record.league_name}</span>
                    </p>
                    <p className="mt-1 text-sm text-slate-400">
                      Finished{' '}
                      <span className="font-semibold text-slate-200">
                        {record.final_position}
                        {ordinalSuffix(record.final_position)}
                      </span>
                    </p>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${statusBadgeClass(record.status)}`}
                  >
                    {record.status}
                  </span>
                </motion.li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function ordinalSuffix(n: number): string {
  const v = n % 100;
  if (v >= 11 && v <= 13) return 'th';
  return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] ?? 'th';
}
