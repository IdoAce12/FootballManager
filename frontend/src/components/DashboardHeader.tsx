/**
 * DashboardHeader — persistent top bar.
 * Renders live `/api/status` metrics and a destructive "resign" control that
 * wipes the career and returns the player to onboarding.
 */

import { motion } from 'framer-motion';
import { useState } from 'react';
import { AnimatedMoney } from '@/components/ui/AnimatedMoney';
import { ConfirmModal } from '@/components/ui/ConfirmModal';
import { OvrGauge } from '@/components/ui/OvrGauge';
import { useGame } from '@/state/GameContext';

interface MetricProps {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}

function Metric({ label, value, sub, accent = 'text-slate-100' }: MetricProps) {
  return (
    <div className="stat-pill min-w-[120px]">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{label}</p>
      <p className={`mt-1 font-mono text-lg font-extrabold leading-none ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-[11px] text-slate-500">{sub}</p>}
    </div>
  );
}

export function DashboardHeader() {
  const { status, loading, managerName, resignCareer } = useGame();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [resigning, setResigning] = useState(false);

  const handleResign = async () => {
    setResigning(true);
    const ok = await resignCareer();
    setResigning(false);
    if (ok) setConfirmOpen(false);
  };

  return (
    <>
      <motion.header
        className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-lg neon-border-cyan"
        initial={{ y: -12, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.35 }}
      >
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-4 px-5 py-3">
          <div className="flex flex-1 items-center gap-4">
            <div className="flex h-12 w-12 flex-none items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-emerald-500 text-lg font-black text-slate-950 shadow-glow">
              FC
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-black tracking-tight text-white">
                {status?.club_name ?? (loading ? 'Loading…' : 'FC26 Manager')}
              </h1>
              <p className="truncate text-xs text-slate-400">
                <span className="text-cyan-400">{managerName ?? 'The Gaffer'}</span>
                {status && (
                  <>
                    {' · '}
                    {status.league_name}
                    {' · '}
                    <span className="text-slate-300">
                      {status.league_position
                        ? `${ordinal(status.league_position)} place`
                        : 'Unranked'}
                    </span>
                  </>
                )}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Metric
              label="Matchweek"
              value={status ? `${status.current_week}` : '—'}
              sub={status ? `of ${status.total_matchdays}` : undefined}
            />
            <div className="stat-pill min-w-[140px] neon-border-cyan">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                Transfer Budget
              </p>
              <p className="mt-1 font-mono text-lg font-extrabold leading-none text-emerald-400">
                {status ? (
                  <AnimatedMoney value={status.transfer_budget} />
                ) : (
                  '—'
                )}
              </p>
              {status && (
                <p className="mt-1 text-[11px] text-slate-500">
                  Wages {shortMoney(status.weekly_wage_bill)}/wk
                </p>
              )}
            </div>
            <Metric
              label="Points"
              value={status ? `${status.points}` : '—'}
              accent="text-cyan-400"
              sub={status ? `${status.won}W ${status.drawn}D ${status.lost}L` : undefined}
            />
            <div className="stat-pill flex items-center">
              <OvrGauge value={status?.squad_overall ?? 0} />
            </div>
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              className="rounded-lg border border-rose-500/40 bg-rose-950/40 px-3 py-2 text-[11px] font-bold uppercase tracking-wide text-rose-300 transition-colors hover:border-rose-400 hover:bg-rose-900/50 hover:text-rose-200"
            >
              Resign &amp; New Career
            </button>
          </div>
        </div>
      </motion.header>

      <ConfirmModal
        open={confirmOpen}
        title="Delete this career?"
        message={
          <>
            Are you sure you want to delete this career state? All match results,
            league progress, and squad condition for your current save will be
            permanently wiped. You will return to club selection.
          </>
        }
        confirmLabel="Yes, delete career"
        cancelLabel="Keep playing"
        loading={resigning}
        onConfirm={handleResign}
        onCancel={() => !resigning && setConfirmOpen(false)}
      />
    </>
  );
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] ?? s[v] ?? s[0]);
}

function shortMoney(amount: number): string {
  if (amount >= 1_000_000) return `€${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `€${(amount / 1_000).toFixed(0)}K`;
  return `€${amount}`;
}
