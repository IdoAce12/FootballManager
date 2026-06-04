/**
 * SellPlayerModal — official transfer offer UI with accept flow.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { useEffect } from 'react';
import type { PlayerSummary } from '@/api/types';
import { formatMoney } from '@/lib/format';

export interface SellOfferPreview {
  player: PlayerSummary;
  marketValue: number;
  estimatedMin: number;
  estimatedMax: number;
}

interface SellPlayerModalProps {
  open: boolean;
  offer: SellOfferPreview | null;
  loading?: boolean;
  acceptedFee?: string | null;
  showMoneyRain?: boolean;
  onAccept: () => void;
  onCancel: () => void;
}

export function SellPlayerModal({
  open,
  offer,
  loading = false,
  acceptedFee,
  showMoneyRain = false,
  onAccept,
  onCancel,
}: SellPlayerModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, loading, onCancel]);

  return (
    <AnimatePresence>
      {open && offer && (
        <motion.div
          className="fixed inset-0 z-[110] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
        >
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/85 backdrop-blur-md"
            onClick={loading ? undefined : onCancel}
            aria-label="Close"
          />
          <motion.div
            className="neon-border-amber relative w-full max-w-md overflow-hidden rounded-2xl bg-slate-900/95 p-6 shadow-2xl"
            initial={{ scale: 0.92, y: 24, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 26 }}
          >
            {showMoneyRain && (
              <div className="pointer-events-none absolute inset-0 overflow-hidden">
                {Array.from({ length: 12 }).map((_, i) => (
                  <motion.span
                    key={i}
                    className="absolute text-lg font-bold text-amber-300"
                    style={{ left: `${8 + i * 7}%`, top: '-10%' }}
                    initial={{ y: 0, opacity: 1 }}
                    animate={{ y: 320, opacity: 0 }}
                    transition={{ duration: 1.2, delay: i * 0.05, ease: 'easeIn' }}
                  >
                    €
                  </motion.span>
                ))}
              </div>
            )}

            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-400">
              Official Transfer Offer
            </p>
            <h2 className="mt-1 text-xl font-black text-white">{offer.player.name}</h2>
            <p className="text-sm text-slate-400">
              {offer.player.position} · OVR {offer.player.overall} · Age {offer.player.age}
            </p>

            <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
              <p className="text-[10px] uppercase tracking-widest text-amber-300/80">
                Anonymous buying club bid
              </p>
              <p className="mt-2 font-mono text-2xl font-black text-amber-200">
                {formatMoney(offer.marketValue)} – {formatMoney(offer.estimatedMax)}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Offer range 85%–105% of current market value ({offer.player.market_value_label})
              </p>
              {acceptedFee && (
                <motion.p
                  className="mt-3 text-center font-mono text-lg font-bold text-emerald-300"
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                >
                  DEAL CLOSED: {acceptedFee}
                </motion.p>
              )}
            </div>

            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={onCancel}
                disabled={loading}
                className="btn border border-slate-600 bg-slate-800 text-slate-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onAccept}
                disabled={loading || Boolean(acceptedFee)}
                className="btn border border-amber-400/70 bg-gradient-to-r from-amber-500 to-yellow-400 text-slate-950 shadow-glow hover:from-amber-400"
              >
                {loading ? 'Processing…' : 'ACCEPT OFFER'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
