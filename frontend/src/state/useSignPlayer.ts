/**
 * Shared "sign player" action used by every scouting view.
 * Wraps the POST /api/transfers/sign call, surfaces the server's response
 * string via a toast, and invalidates global state on success so the header
 * budget + squad refresh instantly.
 */

import { useCallback, useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import { useGame } from '@/state/GameContext';
import { useToast } from '@/state/ToastProvider';

export function useSignPlayer() {
  const { push } = useToast();
  const { invalidate } = useGame();
  const [signingId, setSigningId] = useState<number | null>(null);

  const sign = useCallback(
    async (playerId: number, playerName: string) => {
      setSigningId(playerId);
      try {
        const result = await gameApi.signPlayer({ player_id: playerId });
        if (result.success) {
          push(
            'success',
            `Signed ${result.player_name}!`,
            `${result.from_club} → ${result.to_club} for ${result.fee_label}. ` +
              `Budget left: ${result.remaining_budget_label}.`,
          );
          await invalidate();
        } else {
          push('error', `Bid rejected: ${playerName}`, result.message);
        }
        return result;
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Transfer request failed.';
        push('error', 'Transfer failed', message);
        return null;
      } finally {
        setSigningId(null);
      }
    },
    [push, invalidate],
  );

  return { sign, signingId };
}
