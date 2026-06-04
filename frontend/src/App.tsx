/**
 * App — top-level shell.
 * Composes the persistent DashboardHeader with a tabbed workspace switching
 * between the SquadManager, ScoutingHub and MatchSimTerminal views.
 */

import { useState } from 'react';
import { DashboardHeader } from '@/components/DashboardHeader';
import { GameOnboarding } from '@/components/GameOnboarding';
import { IncomingBidModal } from '@/components/IncomingBidModal';
import { MatchSimTerminal } from '@/components/MatchSimTerminal';
import { ScoutingHub } from '@/components/ScoutingHub';
import { TacticalPitch } from '@/components/TacticalPitch';
import { TrophyRoom } from '@/components/TrophyRoom';
import { useGame } from '@/state/GameContext';

type TabId = 'squad' | 'scouting' | 'match' | 'trophy';

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'squad', label: 'Squad', icon: '👥' },
  { id: 'scouting', label: 'Scouting Hub', icon: '🔍' },
  { id: 'match', label: 'Match Day', icon: '⚽' },
  { id: 'trophy', label: 'Trophy Room', icon: '🏆' },
];

export default function App() {
  const [tab, setTab] = useState<TabId>('squad');
  const { error, status, loading, initialized, checkingSession, pendingIncomingBid, dismissIncomingBid } =
    useGame();

  // 1) Probing the backend session — brief splash.
  if (checkingSession) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <div className="flex h-16 w-16 animate-pulse items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-emerald-500 text-2xl font-black text-slate-950">
          FC
        </div>
        <p className="text-sm text-slate-500">Connecting to the engine…</p>
      </div>
    );
  }

  // 2) No career yet — render the onboarding setup screen.
  if (!initialized) {
    return <GameOnboarding />;
  }

  // 3) Career active — render the full tactical dashboard.
  return (
    <div className="min-h-screen">
      <DashboardHeader />

      <main className="mx-auto max-w-[1500px] px-5 py-6">
        {/* Connection error banner */}
        {error && !status && (
          <div className="mb-5 rounded-xl border border-rose-500/40 bg-rose-500/10 px-5 py-3 text-sm text-rose-200">
            <span className="font-bold">Backend unreachable.</span> {error}{' '}
            Make sure the FastAPI server is running:{' '}
            <code className="rounded bg-slate-900 px-1.5 py-0.5 text-cyan-300">
              uvicorn api:app --reload --port 8000
            </code>
          </div>
        )}

        {/* Tab navigation */}
        <nav className="mb-6 flex gap-2 rounded-xl border border-slate-800/80 bg-slate-900/50 p-1.5 neon-border-cyan">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-bold transition-all ${
                tab === t.id
                  ? 'bg-gradient-to-r from-cyan-500 to-emerald-500 text-slate-950 shadow-glow'
                  : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
              }`}
            >
              <span aria-hidden>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        {/* Active views — keep mounted so matchday confirm state survives tab switches */}
        <div className={tab === 'squad' ? '' : 'hidden'}>
          <TacticalPitch />
        </div>
        <div className={tab === 'scouting' ? '' : 'hidden'}>
          <ScoutingHub />
        </div>
        <div className={tab === 'match' ? '' : 'hidden'}>
          <MatchSimTerminal onReturnToDesk={() => setTab('squad')} />
        </div>
        <div className={tab === 'trophy' ? '' : 'hidden'}>
          <TrophyRoom />
        </div>

        {pendingIncomingBid && (
          <IncomingBidModal bid={pendingIncomingBid} onClose={dismissIncomingBid} />
        )}

        {loading && !status && !error && (
          <p className="mt-10 text-center text-sm text-slate-500">Connecting to the engine…</p>
        )}
      </main>

      <footer className="border-t border-slate-800/80 py-4 text-center text-xs text-slate-600">
        FC26 Football Manager · Enterprise Engine · React + FastAPI
      </footer>
    </div>
  );
}
