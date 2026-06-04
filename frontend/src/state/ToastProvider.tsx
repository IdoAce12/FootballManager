/**
 * Lightweight, dependency-free toast notification system.
 *
 * `useToast()` exposes `push()` which renders an animated pop-up in the
 * top-right viewport that auto-dismisses. Used to surface transfer outcomes
 * ("deal completed", "insufficient budget", …) and any API errors.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type ToastVariant = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  variant: ToastVariant;
  title: string;
  message: string;
}

interface ToastContextValue {
  push: (variant: ToastVariant, title: string, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const VARIANT_STYLES: Record<ToastVariant, { accent: string; icon: string; ring: string }> = {
  success: { accent: 'text-emerald-300', icon: '✓', ring: 'border-emerald-500/50' },
  error: { accent: 'text-rose-300', icon: '✕', ring: 'border-rose-500/50' },
  info: { accent: 'text-cyan-300', icon: 'ℹ', ring: 'border-cyan-500/50' },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (variant: ToastVariant, title: string, message: string) => {
      const id = ++counter.current;
      setToasts((prev) => [...prev, { id, variant, title, message }]);
      window.setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-full max-w-sm flex-col gap-3">
        {toasts.map((toast) => {
          const styles = VARIANT_STYLES[toast.variant];
          return (
            <div
              key={toast.id}
              className={`panel pointer-events-auto animate-slide-in-right border ${styles.ring} px-4 py-3`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-slate-800 text-sm font-bold ${styles.accent}`}
                >
                  {styles.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-bold ${styles.accent}`}>{toast.title}</p>
                  <p className="mt-0.5 break-words text-sm text-slate-300">{toast.message}</p>
                </div>
                <button
                  onClick={() => dismiss(toast.id)}
                  className="flex-none text-slate-500 transition-colors hover:text-slate-200"
                  aria-label="Dismiss notification"
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a <ToastProvider>');
  }
  return ctx;
}
