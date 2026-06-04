"""
data_pipeline.py
================
High-performance ingestion layer that turns the raw FC26 CSV export into a
fully wired, in-memory :class:`GameState`.

Responsibilities
----------------
1. Stream-parse the (18,000+ row) CSV with the stdlib :mod:`csv` reader -
   no third-party dependency, single pass, O(n).
2. Construct :class:`~domain_models.Player` objects with safe, defensive
   type-coercion (the dataset has empty cells, GK blanks, ``"86+3"`` style
   position cells, etc.).
3. Group players into their real-world :class:`~domain_models.Club` and
   :class:`~domain_models.League` based on the dataset's own identifiers.
4. Derive realistic per-club finances (transfer budget + wage budget) from the
   squad's market value and the league level.
5. Expose a clean :class:`GameState` aggregate plus convenience query helpers.

The pipeline keeps the most recent ``fifa_update`` record per ``player_id`` so
duplicate snapshots in the export collapse to a single canonical player.
"""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from domain_models import (
    Club,
    FORMATIONS,
    League,
    Player,
    Position,
    TacticalSetup,
    WorkRate,
)

__all__ = ["GameState", "DataPipeline", "load_game_state"]


# ---------------------------------------------------------------------------
# Coercion helpers (module-level for speed: no per-row closure allocation)
# ---------------------------------------------------------------------------
def _to_int(value: Optional[str], default: int = 0) -> int:
    if not value:
        return default
    value = value.strip()
    if not value:
        return default
    for sep in ("+", "-"):
        idx = value.find(sep, 1)
        if idx != -1:
            value = value[:idx]
            break
    try:
        return int(float(value))
    except ValueError:
        return default


def _to_float(value: Optional[str], default: float = 0.0) -> float:
    if not value:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _parse_positions(raw: str) -> List[Position]:
    positions: List[Position] = []
    for token in (raw or "").split(","):
        pos = Position.from_code(token.strip())
        if pos is not None and pos not in positions:
            positions.append(pos)
    return positions or [Position.CM]


def _parse_work_rate(raw: str) -> tuple[WorkRate, WorkRate]:
    # Format is "Attacking/Defensive" e.g. "High/Medium".
    parts = (raw or "").split("/")
    att = WorkRate.parse(parts[0]) if parts else WorkRate.MEDIUM
    deff = WorkRate.parse(parts[1]) if len(parts) > 1 else WorkRate.MEDIUM
    return att, deff


# ---------------------------------------------------------------------------
# Aggregate game state
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class GameState:
    """The fully bootstrapped world: every player, club and league in memory."""

    players: Dict[int, Player] = field(default_factory=dict)
    clubs: Dict[int, Club] = field(default_factory=dict)
    leagues: Dict[int, League] = field(default_factory=dict)
    free_agents: List[Player] = field(default_factory=list)
    load_seconds: float = 0.0

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    def playable_leagues(self, min_clubs: int = 4) -> List[League]:
        """Leagues large enough to run a proper round-robin season."""
        return sorted(
            (lg for lg in self.leagues.values() if len(lg.clubs) >= min_clubs),
            key=lambda lg: (lg.level, lg.name),
        )

    def find_club(self, query: str) -> Optional[Club]:
        query = query.strip().lower()
        for club in self.clubs.values():
            if club.name.lower() == query:
                return club
        for club in self.clubs.values():
            if query in club.name.lower():
                return club
        return None

    def search_players(self, query: str, limit: int = 25) -> List[Player]:
        query = query.strip().lower()
        hits = [
            p
            for p in self.players.values()
            if query in p.short_name.lower() or query in p.long_name.lower()
        ]
        hits.sort(key=lambda p: p.overall, reverse=True)
        return hits[:limit]

    def top_players(self, limit: int = 20) -> List[Player]:
        return sorted(self.players.values(), key=lambda p: p.overall, reverse=True)[:limit]

    def summary(self) -> str:
        return (
            f"GameState: {len(self.players):,} players | "
            f"{len(self.clubs):,} clubs | "
            f"{len(self.leagues):,} leagues | "
            f"{len(self.free_agents):,} free agents | "
            f"loaded in {self.load_seconds:.2f}s"
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class DataPipeline:
    """Parses the FC26 CSV and bootstraps a :class:`GameState`."""

    #: Default starting formation assigned to every club at bootstrap.
    DEFAULT_FORMATION = "4-3-3"

    def __init__(self, csv_path: str) -> None:
        if not os.path.isfile(csv_path):
            raise FileNotFoundError(f"FC26 dataset not found: {csv_path}")
        self.csv_path = csv_path

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def build(self) -> GameState:
        start = time.perf_counter()
        state = GameState()

        # Keep only the latest fifa_update per player to dedupe snapshots.
        latest_update: Dict[int, int] = {}

        with open(self.csv_path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                player = self._row_to_player(row)
                if player is None:
                    continue

                update_version = _to_int(row.get("fifa_update"), 0)
                seen = latest_update.get(player.player_id)
                if seen is not None and update_version <= seen:
                    continue
                latest_update[player.player_id] = update_version

                state.players[player.player_id] = player
                self._attach_to_club(state, player, row)

        self._finalise_clubs(state)
        state.load_seconds = time.perf_counter() - start
        return state

    # ------------------------------------------------------------------ #
    # Row -> Player
    # ------------------------------------------------------------------ #
    def _row_to_player(self, row: Dict[str, str]) -> Optional[Player]:
        pid = _to_int(row.get("player_id"), -1)
        if pid < 0:
            return None

        att_wr, def_wr = _parse_work_rate(row.get("work_rate", ""))

        return Player(
            player_id=pid,
            short_name=(row.get("short_name") or "Unknown").strip(),
            long_name=(row.get("long_name") or row.get("short_name") or "Unknown").strip(),
            age=_to_int(row.get("age"), 24),
            nationality=(row.get("nationality_name") or "Unknown").strip(),
            overall=_to_int(row.get("overall"), 50),
            potential=_to_int(row.get("potential"), 50),
            positions=_parse_positions(row.get("player_positions", "")),
            value_eur=_to_int(row.get("value_eur"), 0),
            wage_eur=_to_int(row.get("wage_eur"), 0),
            pace=_to_int(row.get("pace"), 50),
            shooting=_to_int(row.get("shooting"), 50),
            passing=_to_int(row.get("passing"), 50),
            dribbling=_to_int(row.get("dribbling"), 50),
            defending=_to_int(row.get("defending"), 50),
            physic=_to_int(row.get("physic"), 50),
            base_stamina=_to_int(row.get("power_stamina"), 60),
            gk_diving=_to_int(row.get("goalkeeping_diving"), 10),
            gk_handling=_to_int(row.get("goalkeeping_handling"), 10),
            gk_kicking=_to_int(row.get("goalkeeping_kicking"), 10),
            gk_positioning=_to_int(row.get("goalkeeping_positioning"), 10),
            gk_reflexes=_to_int(row.get("goalkeeping_reflexes"), 10),
            preferred_foot=(row.get("preferred_foot") or "Right").strip(),
            weak_foot=_to_int(row.get("weak_foot"), 3),
            skill_moves=_to_int(row.get("skill_moves"), 3),
            international_reputation=_to_int(row.get("international_reputation"), 1),
            attacking_work_rate=att_wr,
            defensive_work_rate=def_wr,
            height_cm=_to_int(row.get("height_cm"), 180),
            weight_kg=_to_int(row.get("weight_kg"), 75),
            contract_until=_to_int(row.get("club_contract_valid_until_year"), 2026),
            squad_number=_to_int(row.get("club_jersey_number"), 0),
        )

    # ------------------------------------------------------------------ #
    # Player -> Club / League graph
    # ------------------------------------------------------------------ #
    def _attach_to_club(self, state: GameState, player: Player, row: Dict[str, str]) -> None:
        club_id = _to_int(row.get("club_team_id"), -1)
        club_name = (row.get("club_name") or "").strip()

        if club_id < 0 or not club_name:
            state.free_agents.append(player)
            return

        league_id = _to_int(row.get("league_id"), -1)
        league_name = (row.get("league_name") or "Unknown League").strip()
        league_level = _to_int(row.get("league_level"), 1)

        league = state.leagues.get(league_id)
        if league is None and league_id >= 0:
            league = League(league_id=league_id, name=league_name, level=league_level)
            state.leagues[league_id] = league

        club = state.clubs.get(club_id)
        if club is None:
            club = Club(
                club_id=club_id,
                name=club_name,
                league_id=league_id,
                formation=FORMATIONS[self.DEFAULT_FORMATION],
                tactics=TacticalSetup(),
            )
            state.clubs[club_id] = club
            if league is not None:
                league.add_club(club)

        club.add_player(player)

    # ------------------------------------------------------------------ #
    # Finances + fixtures
    # ------------------------------------------------------------------ #
    def _finalise_clubs(self, state: GameState) -> None:
        """Derive club finances and generate every league's fixtures."""
        for club in state.clubs.values():
            league = state.leagues.get(club.league_id)
            level = league.level if league else 3

            squad_value = club.squad_market_value
            # Higher divisions get larger discretionary transfer budgets.
            level_factor = {1: 0.18, 2: 0.10, 3: 0.06}.get(level, 0.04)
            club.transfer_budget = round(max(500_000.0, squad_value * level_factor), 2)

            # Weekly wage budget = current bill + headroom scaled by division.
            current_bill = club.weekly_wage_bill
            headroom = {1: 0.25, 2: 0.15, 3: 0.10}.get(level, 0.08)
            club.wage_budget_weekly = round(current_bill * (1.0 + headroom), 2)

        for league in state.leagues.values():
            if len(league.clubs) >= 2:
                league.generate_fixtures()


def load_game_state(csv_path: str, verbose: bool = True) -> GameState:
    """Convenience one-liner used by the controller / scripts."""
    pipeline = DataPipeline(csv_path)
    state = pipeline.build()
    if verbose:
        print(state.summary())
    return state


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "FC26_20250921.csv",
    )
    gs = load_game_state(path)
    print("\nTop 5 players in the world:")
    for p in gs.top_players(5):
        print(f"  {p.short_name:<22} {p.overall} OVR  ({p.nationality})")
    print("\nLargest playable leagues:")
    for lg in gs.playable_leagues()[:5]:
        print(f"  {lg.name:<28} {len(lg.clubs)} clubs (level {lg.level})")
