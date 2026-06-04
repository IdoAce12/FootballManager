/**
 * Cinematic incoming transfer bid interruption on the dashboard desk.
 */

import { motion } from 'framer-motion';
import { useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import type { IncomingTransferBid } from '@/api/types';
import { useGame } from '@/state/GameContext';
import { useToast } from '@/state/ToastProvider';

interface IncomingBidModalProps {
  bid: IncomingTransferBid;
  onClose: () => void;
}

export function IncomingBidModal({ bid, onClose }: IncomingBidModalProps) {
  const { dismissIncomingBid, invalidate } = useGame();
  const { push } = useToast();
  const [busy, setBusy] = useState(false);

  const handleAccept = async () => {
    setBusy(true);
    try {
      const res = await gameApi.acceptIncomingBid({
        player_id: bid.player_id,
        fee: bid.fee,
      });
      push('success', 'Transfer complete', res.message);
      dismissIncomingBid();
      onClose();
      await invalidate();
    } catch (err) {
      push(
        'error',
        'Bid failed',
        err instanceof ApiError ? err.message : 'Could not complete the sale.',
      );
    } finally {
      setBusy(false);
    }
  };

  const handleReject = () => {
    dismissIncomingBid();
    onClose();
    push('info', 'Bid rejected', `${bid.player_name} stays at your club.`);
  };

  return (
    <motion.div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="bid-title"
    >
      <motion.div
        className="panel-glow w-full max-w-md border-rose-500/40 neon-border-amber"
        initial={{ scale: 0.92, y: 16 }}
        animate={{ scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 24 }}
      >
        <div className="border-b border-slate-800/80 bg-rose-950/30 px-6 py-4 text-center">
          <p className="text-2xl font-black tracking-tight text-rose-200">
            🚨 OFFICIAL BID RECEIVED
          </p>
        </div>

        <div className="space-y-4 px-6 py-6 text-center">
          <p className="text-sm text-slate-400">
            <span className="font-bold text-white">{bid.bidding_club}</span> have tabled an
            aggressive offer for your star asset.
          </p>

          <div className="rounded-xl border border-slate-700/80 bg-slate-900/80 px-4 py-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Player</p>
            <p className="mt-1 text-xl font-black text-white">
              {bid.player_name}{' '}
              <span className="text-cyan-400">OVR {bid.player_overall}</span>
            </p>
            <p className="mt-3 text-xs text-slate-500">
              Market value {bid.market_value_label}
            </p>
            <p className="mt-2 font-mono text-2xl font-extrabold text-emerald-400">
              {bid.fee_label}
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleAccept()}
              className="btn flex-1 border border-emerald-400/50 bg-emerald-600/90 text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              ACCEPT BILLIONS
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleReject}
              className="btn flex-1 border border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            >
              REJECT &amp; KEEP PLAYER
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
