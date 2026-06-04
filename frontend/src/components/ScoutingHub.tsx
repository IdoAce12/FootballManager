/**
 * ScoutingHub — advanced global database search with multi-filter panel.
 */

import { useState, type ReactNode } from 'react';
import { ApiError, gameApi } from '@/api/client';
import type { ScoutSearchParams, ScoutTarget } from '@/api/types';
import { positionGroupColor, ratingTextColor } from '@/lib/format';
import { useSignPlayer } from '@/state/useSignPlayer';

interface FilterState {
  name: string;
  position: string;
  minAge: string;
  maxAge: string;
  minOvr: string;
  maxOvr: string;
  minPot: string;
  maxPot: string;
}

const EMPTY_FILTERS: FilterState = {
  name: '',
  position: '',
  minAge: '',
  maxAge: '',
  minOvr: '',
  maxOvr: '',
  minPot: '',
  maxPot: '',
};

function TargetCard({
  target,
  onSign,
  signingId,
}: {
  target: ScoutTarget;
  onSign: (id: number, name: string) => void;
  signingId: number | null;
}) {
  const isSigning = signingId === target.player_id;
  return (
    <div className="panel flex flex-col gap-3 p-4 transition-transform hover:-translate-y-0.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-bold text-slate-100">{target.name}</p>
          <p className="truncate text-[11px] text-slate-500">
            {target.club_name ?? 'Free Agent'} · {target.nationality} · {target.age}y
          </p>
        </div>
        <span
          className={`flex-none rounded-md px-2 py-1 text-[11px] font-bold ring-1 ${positionGroupColor(
            target.position,
          )}`}
        >
          {target.position}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-lg bg-slate-800/50 py-1.5">
          <p className="text-slate-500">OVR</p>
          <p className={`font-mono text-base font-extrabold ${ratingTextColor(target.overall)}`}>
            {target.overall}
          </p>
        </div>
        <div className="rounded-lg bg-slate-800/50 py-1.5">
          <p className="text-slate-500">POT</p>
          <p className={`font-mono text-base font-extrabold ${ratingTextColor(target.potential)}`}>
            {target.potential}
          </p>
        </div>
        <div className="rounded-lg bg-slate-800/50 py-1.5">
          <p className="text-slate-500">+Growth</p>
          <p className="font-mono text-base font-extrabold text-cyan-300">
            +{target.growth_potential}
          </p>
        </div>
      </div>
      <p className="font-mono text-sm font-bold text-emerald-400">{target.market_value_label}</p>
      <button
        type="button"
        onClick={() => onSign(target.player_id, target.name)}
        disabled={isSigning}
        className="btn btn-sign w-full"
      >
        {isSigning ? 'PROCESSING…' : 'SIGN PLAYER'}
      </button>
    </div>
  );
}

export function ScoutingHub() {
  const { sign, signingId } = useSignPlayer();
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [results, setResults] = useState<ScoutTarget[]>([]);
  const [applied, setApplied] = useState<Record<string, string | number>>({});
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildParams = (): ScoutSearchParams | null => {
    const params: ScoutSearchParams = { limit: 60 };
    if (filters.name.trim()) params.name = filters.name.trim();
    if (filters.position.trim()) params.position = filters.position.trim().toUpperCase();
    const minAge = filters.minAge ? Number(filters.minAge) : undefined;
    const maxAge = filters.maxAge ? Number(filters.maxAge) : undefined;
    const minOvr = filters.minOvr ? Number(filters.minOvr) : undefined;
    const maxOvr = filters.maxOvr ? Number(filters.maxOvr) : undefined;
    const minPot = filters.minPot ? Number(filters.minPot) : undefined;
    const maxPot = filters.maxPot ? Number(filters.maxPot) : undefined;
    if (minAge !== undefined) params.min_age = minAge;
    if (maxAge !== undefined) params.max_age = maxAge;
    if (minOvr !== undefined) params.min_ovr = minOvr;
    if (maxOvr !== undefined) params.max_ovr = maxOvr;
    if (minPot !== undefined) params.min_pot = minPot;
    if (maxPot !== undefined) params.max_pot = maxPot;
    if (Object.keys(params).length <= 1) return null;
    return params;
  };

  const runSearch = async () => {
    const params = buildParams();
    if (!params) {
      setError('Set at least one filter before searching.');
      return;
    }
    setSearching(true);
    setError(null);
    setSearched(true);
    try {
      const data = await gameApi.searchPlayers(params);
      setResults(data.results);
      setApplied(data.filters_applied);
    } catch (err) {
      setResults([]);
      setError(err instanceof ApiError ? err.message : 'Search failed.');
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-5">
      <section className="panel p-5">
        <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">
          Global Scouting Database
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          Query all 18,405 FC26 players with precision filters.
        </p>

        <div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <FilterField label="Player Name">
            <input
              value={filters.name}
              onChange={(e) => setFilters({ ...filters, name: e.target.value })}
              placeholder="e.g. Mbappé"
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Position">
            <input
              value={filters.position}
              onChange={(e) => setFilters({ ...filters, position: e.target.value })}
              placeholder="ST, CAM, CB…"
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Min Age">
            <input
              type="number"
              min={15}
              max={45}
              value={filters.minAge}
              onChange={(e) => setFilters({ ...filters, minAge: e.target.value })}
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Max Age">
            <input
              type="number"
              min={15}
              max={45}
              value={filters.maxAge}
              onChange={(e) => setFilters({ ...filters, maxAge: e.target.value })}
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Min OVR">
            <input
              type="number"
              min={40}
              max={99}
              value={filters.minOvr}
              onChange={(e) => setFilters({ ...filters, minOvr: e.target.value })}
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Max OVR">
            <input
              type="number"
              min={40}
              max={99}
              value={filters.maxOvr}
              onChange={(e) => setFilters({ ...filters, maxOvr: e.target.value })}
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Min Potential">
            <input
              type="number"
              min={40}
              max={99}
              value={filters.minPot}
              onChange={(e) => setFilters({ ...filters, minPot: e.target.value })}
              className="filter-input"
            />
          </FilterField>
          <FilterField label="Max Potential">
            <input
              type="number"
              min={40}
              max={99}
              value={filters.maxPot}
              onChange={(e) => setFilters({ ...filters, maxPot: e.target.value })}
              className="filter-input"
            />
          </FilterField>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={runSearch} disabled={searching} className="btn btn-sign px-6">
            {searching ? 'Searching…' : 'Run Scouting Report'}
          </button>
          <button
            type="button"
            onClick={() => {
              setFilters(EMPTY_FILTERS);
              setResults([]);
              setSearched(false);
              setError(null);
            }}
            className="btn border border-slate-600 bg-slate-800 text-slate-200"
          >
            Clear Filters
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      </section>

      <section className="panel p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
            Results {searched ? `(${results.length})` : ''}
          </p>
          {searched && Object.keys(applied).length > 0 && (
            <p className="text-[10px] text-slate-600">
              {Object.entries(applied)
                .map(([k, v]) => `${k}=${v}`)
                .join(' · ')}
            </p>
          )}
        </div>
        {!searched ? (
          <p className="py-12 text-center text-sm text-slate-600">
            Configure filters and run a scouting report to explore the database.
          </p>
        ) : results.length === 0 ? (
          <p className="py-12 text-center text-sm text-slate-500">No players matched your filters.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {results.map((t) => (
              <TargetCard key={t.player_id} target={t} onSign={sign} signingId={signingId} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}
