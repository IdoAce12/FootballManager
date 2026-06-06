/**
 * Global game state.
 *
 * Two layers of state:
 *   1. Session/onboarding — whether a career has been initialized on the
 *      backend (manager + league + club). Probed once on load via
 *      `GET /api/game/session`. Until initialized, the app shows onboarding.
 *   2. Live status — the authoritative `/api/status` snapshot, plus a
 *      monotonic `version` counter. Mutating actions call `invalidate()` which
 *      bumps the version and refetches status; data-bound views key their
 *      fetches off `version` so the whole dashboard stays in sync.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, gameApi } from '@/api/client';
import type {
  ConfirmMatchdayResponse,
  IncomingTransferBid,
  SessionResponse,
  SetupRequest,
  StatusResponse,
} from '@/api/types';
import { useToast } from '@/state/ToastProvider';

interface GameContextValue {
  // Session / onboarding
  initialized: boolean;
  managerName: string | null;
  checkingSession: boolean;
  // Live status
  status: StatusResponse | null;
  loading: boolean;
  error: string | null;
  version: number;
  /** Mega-club bid surfaced after matchday confirm (~15% chance). */
  pendingIncomingBid: IncomingTransferBid | null;
  // Actions
  refreshStatus: () => Promise<void>;
  invalidate: () => Promise<void>;
  /** Commit a previewed matchday and fully sync dashboard state (status + squad consumers). */
  commitMatchdayAndSync: () => Promise<ConfirmMatchdayResponse>;
  dismissIncomingBid: () => void;
  setupGame: (payload: SetupRequest) => Promise<boolean>;
  /** Wipe career server-side and return to onboarding. */
  resignCareer: () => Promise<boolean>;
}

const GameContext = createContext<GameContextValue | null>(null);

export function GameProvider({ children }: { children: ReactNode }) {
  const { push } = useToast();
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [pendingIncomingBid, setPendingIncomingBid] = useState<IncomingTransferBid | null>(
    null,
  );
  const probed = useRef(false);

  const refreshStatus = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLoading(true);
    }
    try {
      const data = await gameApi.getStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load status.';
      setError(message);
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }, []);

  const invalidate = useCallback(async () => {
    setVersion((v) => v + 1);
    await refreshStatus();
  }, [refreshStatus]);

  const dismissIncomingBid = useCallback(() => setPendingIncomingBid(null), []);

  const commitMatchdayAndSync = useCallback(async (): Promise<ConfirmMatchdayResponse> => {
    const payload = await gameApi.confirmMatchday();
    if (payload.development?.length) {
      console.info('[matchday] Player development updates:', payload.development);
    }
    if (payload.incoming_bid) {
      setPendingIncomingBid(payload.incoming_bid);
    }
    setVersion((v) => v + 1);
    await refreshStatus();
    return payload;
  }, [refreshStatus]);

  const setupGame = useCallback(
    async (payload: SetupRequest): Promise<boolean> => {
      try {
        const next = await gameApi.setupGame(payload);
        setSession(next);
        if (next.initialized) {
          setVersion((v) => v + 1);
          await refreshStatus();
          push(
            'success',
            'Career initialized',
            `${next.manager_name} now manages ${next.club_name} (${next.league_name}).`,
          );
        }
        return next.initialized;
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Setup failed.';
        push('error', 'Setup failed', message);
        return false;
      }
    },
    [push, refreshStatus],
  );

  const resignCareer = useCallback(async (): Promise<boolean> => {
    try {
      const next = await gameApi.resetCareer();
      setSession(next);
      setStatus(null);
      setVersion(0);
      setPendingIncomingBid(null);
      setError(null);
      push('info', 'Career ended', 'Your save has been wiped. Choose a new club to continue.');
      return !next.initialized;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not reset career.';
      push('error', 'Reset failed', message);
      return false;
    }
  }, [push]);

  // Probe the session exactly once on first mount.
  useEffect(() => {
    if (probed.current) return;
    probed.current = true;
    (async () => {
      try {
        const data = await gameApi.getSession();
        setSession(data);
        if (data.initialized) {
          await refreshStatus();
        }
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : 'Cannot reach the backend.';
        setError(message);
        push('error', 'Connection error', message);
      } finally {
        setCheckingSession(false);
      }
    })();
  }, [refreshStatus, push]);

  // Keep the Render free-tier backend awake while a career is active.
  useEffect(() => {
    if (!session?.initialized) return undefined;
    const HEARTBEAT_MS = 4.5 * 60 * 1000;
    const id = window.setInterval(() => {
      void refreshStatus({ silent: true });
    }, HEARTBEAT_MS);
    return () => window.clearInterval(id);
  }, [session?.initialized, refreshStatus]);

  const value = useMemo<GameContextValue>(
    () => ({
      initialized: session?.initialized ?? false,
      managerName: session?.manager_name ?? null,
      checkingSession,
      status,
      loading,
      error,
      version,
      pendingIncomingBid,
      refreshStatus,
      invalidate,
      commitMatchdayAndSync,
      dismissIncomingBid,
      setupGame,
      resignCareer,
    }),
    [
      session,
      checkingSession,
      status,
      loading,
      error,
      version,
      pendingIncomingBid,
      refreshStatus,
      invalidate,
      commitMatchdayAndSync,
      dismissIncomingBid,
      setupGame,
      resignCareer,
    ],
  );

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}

export function useGame(): GameContextValue {
  const ctx = useContext(GameContext);
  if (!ctx) {
    throw new Error('useGame must be used within a <GameProvider>');
  }
  return ctx;
}
