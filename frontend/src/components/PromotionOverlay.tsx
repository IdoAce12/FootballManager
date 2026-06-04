/**
 * Full-screen promotion celebration after tier-up on season rollover.
 */

import { AnimatePresence, motion } from 'framer-motion';

interface PromotionOverlayProps {
  open: boolean;
  leagueName?: string | null;
  onDismiss: () => void;
}

const CONFETTI = Array.from({ length: 48 }, (_, i) => ({
  id: i,
  left: `${(i * 17) % 100}%`,
  delay: (i % 7) * 0.08,
  color: ['#fbbf24', '#34d399', '#22d3ee', '#f472b6', '#a78bfa'][i % 5],
}));

export function PromotionOverlay({ open, leagueName, onDismiss }: PromotionOverlayProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/90 backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="promotion-title"
        >
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            {CONFETTI.map((c) => (
              <span
                key={c.id}
                className="confetti-piece absolute top-0 h-3 w-2 rounded-sm"
                style={{
                  left: c.left,
                  backgroundColor: c.color,
                  animationDelay: `${c.delay}s`,
                }}
              />
            ))}
          </div>

          <motion.div
            className="relative z-10 mx-4 max-w-lg rounded-2xl border-2 border-amber-400/70 bg-gradient-to-br from-amber-950/90 via-slate-900 to-slate-950 px-8 py-10 text-center shadow-[0_0_60px_-10px_rgba(251,191,36,0.7)]"
            initial={{ scale: 0.85, y: 24, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 260, damping: 22 }}
          >
            <p className="text-xs font-bold uppercase tracking-[0.35em] text-amber-300/90">
              Season complete
            </p>
            <h2
              id="promotion-title"
              className="mt-4 text-2xl font-black leading-tight text-amber-100 sm:text-3xl"
            >
              PROMOTION SECURED
            </h2>
            <p className="mt-2 text-lg font-bold text-amber-400">
              WELCOME TO THE FIRST DIVISION!
            </p>
            {leagueName && (
              <p className="mt-4 text-sm text-slate-400">
                Your club now competes in{' '}
                <span className="font-semibold text-cyan-300">{leagueName}</span>
              </p>
            )}
            <button
              type="button"
              onClick={onDismiss}
              className="btn btn-launch mt-8 w-full border border-amber-400/50 bg-gradient-to-r from-amber-500 to-yellow-400 text-slate-950 hover:from-amber-400"
            >
              Continue campaign
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
