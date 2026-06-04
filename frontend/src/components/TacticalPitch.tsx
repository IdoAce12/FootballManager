/**
 * TacticalPitch — glassmorphic formation view with interactive lineup selection.
 * Replaces the legacy squad table; only the 11 selected starters drive sector ratings.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, gameApi } from '@/api/client';
import type { PlayerSummary, SquadResponse } from '@/api/types';
import { FORMATION_NAMES, layoutForFormation } from '@/lib/formationLayouts';
import { SellPlayerModal, type SellOfferPreview } from '@/components/ui/SellPlayerModal';
import { formatPlayerStats, ratingBadgeClasses, ratingTextColor } from '@/lib/format';
import { useGame } from '@/state/GameContext';
import { useToast } from '@/state/ToastProvider';

export function TacticalPitch() {
  const { version, invalidate } = useGame();
  const { push } = useToast();

  const [squad, setSquad] = useState<SquadResponse | null>(null);
  const [formation, setFormation] = useState<string>('4-3-3');
  const [assignments, setAssignments] = useState<(number | null)[]>(Array(11).fill(null));
  const [activeSlot, setActiveSlot] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sellingId, setSellingId] = useState<number | null>(null);
  const [sellModalOpen, setSellModalOpen] = useState(false);
  const [sellOffer, setSellOffer] = useState<SellOfferPreview | null>(null);
  const [acceptedFee, setAcceptedFee] = useState<string | null>(null);
  const [moneyRain, setMoneyRain] = useState(false);

  const loadSquad = useCallback(async () => {
    setLoading(true);
    try {
      const data = await gameApi.getSquad();
      setSquad(data);
      setFormation(data.formation);
      const ids = data.lineup
        .sort((a, b) => a.slot_index - b.slot_index)
        .map((s) => s.player_id);
      setAssignments(ids.length === 11 ? ids : Array(11).fill(null));
    } catch (err) {
      push('error', 'Squad load failed', err instanceof ApiError ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void loadSquad();
  }, [loadSquad, version]);

  const layout = useMemo(() => layoutForFormation(formation), [formation]);

  const playerMap = useMemo(() => {
    const m = new Map<number, PlayerSummary>();
    squad?.players.forEach((p) => m.set(p.player_id, p));
    return m;
  }, [squad]);

  const saveLineup = async (nextFormation: string, nextAssignments: (number | null)[]) => {
    if (nextAssignments.some((id) => id === null)) {
      push('error', 'Incomplete XI', 'Assign all 11 positions before saving.');
      return;
    }
    setSaving(true);
    try {
      const data = await gameApi.updateLineup({
        formation: nextFormation,
        starting_xi: nextAssignments as number[],
      });
      setSquad(data);
      setFormation(data.formation);
      push('success', 'Lineup saved', 'Starting XI and sector ratings updated.');
      await invalidate();
      setActiveSlot(null);
    } catch (err) {
      push('error', 'Save failed', err instanceof ApiError ? err.message : 'Could not save lineup.');
    } finally {
      setSaving(false);
    }
  };

  const onSelectPlayer = (playerId: number) => {
    if (activeSlot === null) return;
    const next = [...assignments];
    for (let i = 0; i < next.length; i += 1) {
      if (next[i] === playerId) next[i] = null;
    }
    next[activeSlot] = playerId;
    setAssignments(next);
    void saveLineup(formation, next);
  };

  const openSellModal = (player: PlayerSummary) => {
    const mv = player.market_value;
    setSellOffer({
      player,
      marketValue: mv,
      estimatedMin: Math.round(mv * 0.85),
      estimatedMax: Math.round(mv * 1.05),
    });
    setAcceptedFee(null);
    setMoneyRain(false);
    setSellModalOpen(true);
  };

  const closeSellModal = () => {
    if (sellingId !== null) return;
    setSellModalOpen(false);
    setSellOffer(null);
    setAcceptedFee(null);
    setMoneyRain(false);
  };

  const acceptSellOffer = async () => {
    if (!sellOffer) return;
    setSellingId(sellOffer.player.player_id);
    try {
      const res = await gameApi.sellPlayer({ player_id: sellOffer.player.player_id });
      setAcceptedFee(res.fee_label);
      setMoneyRain(true);
      push('success', 'Transfer complete', res.message);
      window.setTimeout(async () => {
        await loadSquad();
        await invalidate();
        setActiveSlot(null);
        closeSellModal();
      }, 1200);
    } catch (err) {
      push('error', 'Sale failed', err instanceof ApiError ? err.message : 'Unknown error.');
    } finally {
      setSellingId(null);
    }
  };

  const onFormationChange = (name: string) => {
    setFormation(name);
    if (!squad) return;
    const auto = squad.players
      .slice()
      .sort((a, b) => b.overall - a.overall)
      .slice(0, 11)
      .map((p) => p.player_id);
    if (auto.length === 11) {
      setAssignments(auto);
      void saveLineup(name, auto);
    }
  };

  if (loading && !squad) {
    return <p className="py-16 text-center text-sm text-slate-500">Loading tactical board…</p>;
  }

  return (
    <section className="panel-glow animate-fade-in-up overflow-hidden">
      <div className="panel-header flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">
            Tactical Board
          </h2>
          <p className="text-xs text-slate-500">
            Tap a position to assign a starter — ratings use this XI only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Formation
            <select
              value={formation}
              onChange={(e) => onFormationChange(e.target.value)}
              disabled={saving}
              className="mt-1 block rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            >
              {FORMATION_NAMES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          {squad && (
            <div className="grid grid-cols-4 gap-2 text-center text-xs">
              <RatingChip label="ATT" value={squad.attack_rating} />
              <RatingChip label="MID" value={squad.midfield_rating} />
              <RatingChip label="DEF" value={squad.defence_rating} />
              <RatingChip label="GK" value={squad.goalkeeper_rating} />
            </div>
          )}
        </div>
      </div>

      <div className="relative grid gap-0 lg:grid-cols-[1fr_320px]">
        {/* Pitch */}
        <div className="relative min-h-[520px] p-4">
          <div className="relative mx-auto aspect-[3/4] max-w-xl overflow-hidden rounded-2xl border border-emerald-500/20 bg-gradient-to-b from-emerald-900/40 via-emerald-800/30 to-emerald-950/50 shadow-inner backdrop-blur-sm">
            <div className="pointer-events-none absolute inset-4 rounded-xl border border-white/10" />
            <div className="pointer-events-none absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/15" />
            <div className="pointer-events-none absolute left-1/2 top-4 bottom-4 w-px bg-white/10" />

            {layout.map((node) => {
              const slotIdx = node.slotIndex;
              const pid = assignments[slotIdx] ?? null;
              const player = pid ? playerMap.get(pid) : undefined;
              const posLabel = squad?.lineup.find((l) => l.slot_index === slotIdx)?.position ?? '?';
              const isActive = activeSlot === slotIdx;

              return (
                <button
                  key={slotIdx}
                  type="button"
                  onClick={() => setActiveSlot(slotIdx)}
                  style={{ left: `${node.x}%`, top: `${node.y}%` }}
                  className={`pitch-node-glow absolute z-10 w-[4.5rem] -translate-x-1/2 -translate-y-1/2 rounded-xl border px-1 py-1.5 text-center transition-all ${
                    isActive
                      ? 'border-cyan-400 bg-cyan-500/20 shadow-glow scale-105 animate-pulse'
                      : 'border-slate-600/80 bg-slate-950/70 hover:border-cyan-500/50 hover:bg-slate-900/80'
                  }`}
                >
                  <p className="text-[9px] font-bold uppercase tracking-wider text-emerald-300/90">
                    {posLabel}
                  </p>
                  <p className="truncate text-[11px] font-bold text-white">
                    {player?.name ?? '—'}
                  </p>
                  {player && (
                    <p
                      className={`font-mono text-sm font-extrabold ${ratingTextColor(player.overall)}`}
                    >
                      {player.overall}
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Slide-over roster picker */}
        <aside
          className={`border-t border-slate-800/80 bg-slate-950/60 lg:border-l lg:border-t-0 ${
            activeSlot !== null ? 'block' : 'hidden lg:block'
          }`}
        >
          <div className="sticky top-0 border-b border-slate-800/80 bg-slate-900/90 px-4 py-3 backdrop-blur">
            <p className="text-xs font-bold uppercase tracking-widest text-cyan-400">
              {activeSlot !== null
                ? `Assign ${squad?.lineup.find((l) => l.slot_index === activeSlot)?.position ?? 'Slot'}`
                : 'Select a position'}
            </p>
            <p className="text-[11px] text-slate-500">Choose from your squad roster</p>
          </div>
          <div className="max-h-[480px] overflow-auto p-2">
            {activeSlot === null ? (
              <p className="px-3 py-8 text-center text-sm text-slate-600">
                Click a node on the pitch to open the lineup selector.
              </p>
            ) : (
              squad?.players
                .slice()
                .sort((a, b) => b.overall - a.overall)
                .map((p) => {
                  const assignedElsewhere = assignments.includes(p.player_id) &&
                    assignments[activeSlot] !== p.player_id;
                  return (
                    <button
                      key={p.player_id}
                      type="button"
                      disabled={assignedElsewhere || saving}
                      onClick={() => onSelectPlayer(p.player_id)}
                      className="mb-1 flex w-full items-center justify-between rounded-lg border border-slate-800/60 bg-slate-900/50 px-3 py-2 text-left transition-colors hover:border-cyan-500/40 hover:bg-slate-800/60 disabled:opacity-40"
                    >
                      <div>
                        <p className="text-sm font-semibold text-slate-100">{p.name}</p>
                        <p className="text-[10px] text-slate-500">
                          {p.position} · {p.age}y · FIT {Math.round(p.fitness)}
                        </p>
                        <p className="mt-0.5 font-mono text-[10px] font-bold text-cyan-400/90">
                          {formatPlayerStats(p)}
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span
                          className={`rounded-md px-2 py-1 font-mono text-sm font-bold ring-1 ${ratingBadgeClasses(
                            p.overall,
                          )}`}
                        >
                          {p.overall}
                        </span>
                        <button
                          type="button"
                          disabled={sellingId === p.player_id || saving}
                          onClick={(e) => {
                            e.stopPropagation();
                            openSellModal(p);
                          }}
                          className="rounded border border-amber-500/60 bg-amber-500/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-200 shadow-[0_0_12px_-2px_rgba(251,191,36,0.7)] hover:bg-amber-500/25"
                        >
                          Sell
                        </button>
                      </div>
                    </button>
                  );
                })
            )}
          </div>
        </aside>
      </div>

      {squad && (
        <div className="border-t border-slate-800/80 p-4">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Full Squad · {squad.player_count} players
          </p>
          <div className="max-h-[280px] overflow-auto rounded-lg ring-1 ring-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-900/95 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3 py-2">Player</th>
                  <th className="px-3 py-2">Pos</th>
                  <th className="px-3 py-2 text-center">OVR</th>
                  <th className="px-3 py-2 text-center">Stats</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {squad.players
                  .slice()
                  .sort((a, b) => b.overall - a.overall)
                  .map((p) => (
                    <tr key={p.player_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="px-3 py-2 font-medium text-slate-200">{p.name}</td>
                      <td className="px-3 py-2 text-slate-400">{p.position}</td>
                      <td className={`px-3 py-2 text-center font-mono font-bold ${ratingTextColor(p.overall)}`}>
                        {p.overall}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-cyan-300/90">
                        {formatPlayerStats(p)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          disabled={sellingId === p.player_id}
                          onClick={() => openSellModal(p)}
                          className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-200 hover:bg-amber-500/20"
                        >
                          Sell Player
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <SellPlayerModal
        open={sellModalOpen}
        offer={sellOffer}
        loading={sellingId !== null}
        acceptedFee={acceptedFee}
        showMoneyRain={moneyRain}
        onAccept={() => void acceptSellOffer()}
        onCancel={closeSellModal}
      />
    </section>
  );
}

function RatingChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-800/60 px-2 py-1">
      <p className="text-[9px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`font-mono font-bold ${ratingTextColor(value)}`}>{value.toFixed(1)}</p>
    </div>
  );
}
