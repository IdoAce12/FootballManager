"""
api.py
======
FastAPI web layer for the FC26 Football Manager engine.

This module is the thin, stateless-per-request HTTP boundary that exposes the
in-memory game engine (``AppController`` + subsystems) to a React frontend
(Vite ``localhost:5173`` or CRA ``localhost:3000``).

Design
------
* The heavy, mutable game world is loaded **once** at application startup
  (FastAPI ``lifespan``) and held in a single process-wide :class:`GameContext`.
  Loading the full 18,000+ player CSV per-request would be catastrophic, so the
  controller is a long-lived singleton injected into endpoints via a dependency.
* Every endpoint returns a strictly-typed Pydantic response model so the
  frontend gets a stable, self-documenting JSON contract (visible at ``/docs``).
* All domain → DTO conversion lives in small ``_serialize_*`` helpers, keeping
  route handlers declarative and testable.

Run
---
    uvicorn api:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app_controller import AppController, bootstrap, format_money
from continental_cup import CONTINENTAL_CUP_NAME, CONTINENTAL_LEAGUE_ANCHORS
from domain_models import Club, League, Player
from match_simulation_engine import MatchEvent, MatchResult

# Ensure accented player names never crash a Windows console on startup logs.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass


# ===========================================================================
# Configuration
# ===========================================================================
def _default_csv_path() -> str:
    """Resolve the dataset path (env override -> repo root or engine dir on Render)."""
    env_path = os.environ.get("FM_CSV")
    if env_path:
        return env_path
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(os.path.dirname(here), "FC26_20250921.csv"),
        os.path.join(here, "FC26_20250921.csv"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(os.path.dirname(here), "FC26_20250921.csv")


# ===========================================================================
# Process-wide game context (the long-lived singleton)
# ===========================================================================
@dataclass(slots=True)
class GameContext:
    """Holds the single, in-memory game world for the whole API process.

    The world (all 18k players) is loaded at startup, but a *career* is only
    active once the user completes onboarding (manager name + league + club)
    via ``POST /api/game/setup``. Until then :pyattr:`initialized` is False and
    the dashboard endpoints stay locked behind a 409.
    """

    controller: AppController
    csv_path: str
    seed: int
    manager_name: Optional[str] = None

    @property
    def initialized(self) -> bool:
        return (
            self.manager_name is not None
            and self.controller.managed_club is not None
            and self.controller.managed_league is not None
        )

    @property
    def club(self) -> Club:
        if self.controller.managed_club is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No career initialized. Complete onboarding first.",
            )
        return self.controller.managed_club

    @property
    def league(self) -> League:
        if self.controller.managed_league is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No career initialized. Complete onboarding first.",
            )
        return self.controller.managed_league


# Single module-level reference, populated by the lifespan handler.
_CONTEXT: Optional[GameContext] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the dataset once on startup; defer team selection to onboarding."""
    global _CONTEXT
    csv_path = _default_csv_path()
    if not os.path.isfile(csv_path):
        raise RuntimeError(f"FC26 dataset not found at: {csv_path}")

    seed = int(os.environ.get("FM_SEED", "2026"))
    print(f"[api] Bootstrapping game world from {csv_path} ...")
    controller = bootstrap(csv_path, seed=seed)
    # No club is auto-selected — the player chooses theirs in onboarding.
    _CONTEXT = GameContext(controller=controller, csv_path=csv_path, seed=seed)
    print(f"[api] World loaded ({len(controller.state.clubs)} clubs). Awaiting onboarding.")
    try:
        yield
    finally:
        _CONTEXT = None
        print("[api] Shutdown complete.")


def get_context() -> GameContext:
    """FastAPI dependency: provide the ready game context or fail fast."""
    if _CONTEXT is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Game engine is still initializing. Try again shortly.",
        )
    return _CONTEXT


# ===========================================================================
# FastAPI application + middleware
# ===========================================================================
app = FastAPI(
    title="FC26 Football Manager API",
    version="1.0.0",
    description="HTTP layer over the FC26 enterprise football management engine.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Pydantic response / request schemas (the JSON contract)
# ===========================================================================
class StatusResponse(BaseModel):
    season_year: int
    current_week: int = Field(..., description="Matchdays already played")
    total_matchdays: int
    season_complete: bool
    pending_matchday: bool = Field(
        ...,
        description="True when a simulated matchday awaits POST /api/matchday/confirm",
    )
    club_id: int
    club_name: str
    league_name: str
    league_position: int
    transfer_budget: float
    transfer_budget_label: str
    weekly_wage_bill: float
    points: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    squad_overall: float


class PlayerSummary(BaseModel):
    player_id: int
    name: str
    long_name: str
    age: int
    nationality: str
    position: str
    positions: List[str]
    overall: int
    potential: int
    market_value: int
    market_value_label: str
    wage_eur: int
    stamina: int = Field(..., description="Baseline stamina attribute (0-100)")
    fitness: float = Field(..., description="Live match-readiness (0-100)")
    form: float
    morale: float
    sharpness: float
    pace: int
    shooting: int
    passing: int
    dribbling: int
    defending: int
    physic: int
    goals: int
    assists: int
    goals_scored: int
    assists_given: int
    clean_sheets: int
    appearances: int
    average_rating: float
    is_injured: bool
    injured_for_matchdays: int
    contract_until: int


class LineupSlotModel(BaseModel):
    slot_index: int
    position: str
    player_id: Optional[int]
    player_name: Optional[str]
    overall: Optional[int]
    potential: Optional[int] = None


class SquadResponse(BaseModel):
    club_id: int
    club_name: str
    formation: str
    squad_overall: float
    attack_rating: float
    midfield_rating: float
    defence_rating: float
    goalkeeper_rating: float
    player_count: int
    lineup: List[LineupSlotModel]
    players: List[PlayerSummary]


class LineupUpdateRequest(BaseModel):
    formation: Optional[str] = None
    starting_xi: List[int] = Field(
        ..., min_length=11, max_length=11, description="11 player IDs in formation slot order"
    )


class ScoutTarget(BaseModel):
    player_id: int
    name: str
    age: int
    nationality: str
    position: str
    overall: int
    potential: int
    growth_potential: int = Field(..., description="potential - overall")
    market_value: int
    market_value_label: str
    wage_eur: int
    club_name: Optional[str]


class WonderkidResponse(BaseModel):
    count: int
    wonderkids: List[ScoutTarget]


class SearchResponse(BaseModel):
    filters_applied: dict
    count: int
    results: List[ScoutTarget]


class IncomingTransferBidModel(BaseModel):
    player_id: int
    player_name: str
    player_overall: int
    bidding_club: str
    fee: float
    fee_label: str
    market_value: int
    market_value_label: str


class ConfirmMatchdayResponse(BaseModel):
    committed: bool
    matchday: int
    total_matchdays: int
    season_complete: bool
    standings: List[StandingRow]
    match_reward: float = 0
    match_reward_label: str = "€0"
    match_reward_outcome: str = "none"
    continental_match_played: bool = False
    continental_match_reward: float = 0
    continental_match_reward_label: str = "€0"
    continental_match_reward_outcome: str = "none"
    transfer_budget: float = 0
    transfer_budget_label: str = "€0"
    incoming_bid: Optional[IncomingTransferBidModel] = None


class ContinentalFixtureModel(BaseModel):
    matchday: int
    league_matchday: Optional[int] = None
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    stage: str
    group_name: Optional[str] = None
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    is_played: bool


class ContinentalGroupStandingRow(BaseModel):
    position: int
    club_id: int
    club_name: str
    played: int
    won: int
    drawn: int
    lost: int
    goal_difference: int
    points: int


class ContinentalGroupModel(BaseModel):
    group_name: str
    standings: List[ContinentalGroupStandingRow]


class ContinentalBracketMatchModel(BaseModel):
    matchday: int
    stage: str
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    winner_id: Optional[int] = None
    winner_name: Optional[str] = None


class ContinentalCupResponse(BaseModel):
    name: str
    season_year: int
    active: bool
    phase: str
    qualified: bool
    current_matchday: int
    total_matchdays: int
    champion_club_id: Optional[int] = None
    champion_club_name: Optional[str] = None
    groups: List[ContinentalGroupModel]
    fixtures: List[ContinentalFixtureModel]
    bracket: List[ContinentalBracketMatchModel]
    schedule_anchors: List[int]


class SellRequest(BaseModel):
    player_id: int = Field(..., description="Squad player to sell")


class SellResponse(BaseModel):
    success: bool
    message: str
    player_name: str
    buyer_club: str
    fee: float
    fee_label: str
    multiplier_pct: float
    market_value: int
    market_value_label: str
    remaining_budget: float
    remaining_budget_label: str
    squad_size: int


class NextSeasonResponse(BaseModel):
    success: bool
    message: str
    previous_season_year: int
    new_season_year: int
    league_position: int
    budget_bonus: float
    budget_bonus_label: str
    new_transfer_budget: float
    new_transfer_budget_label: str
    total_matchdays: int
    promoted: bool = False
    promotion_from_league: Optional[str] = None
    promotion_to_league: Optional[str] = None
    new_league_id: Optional[int] = None
    new_league_name: Optional[str] = None
    new_league_level: Optional[int] = None
    matchday_win_reward: float = 0
    matchday_draw_reward: float = 0
    season_status: str = "Stayed"


class AcceptBidRequest(BaseModel):
    player_id: int
    fee: float = Field(..., gt=0, description="Agreed transfer fee from the bid")


class AcceptBidResponse(BaseModel):
    success: bool
    message: str
    player_name: str
    fee: float
    fee_label: str
    remaining_budget: float
    remaining_budget_label: str
    squad_size: int


class CareerSeasonRecordModel(BaseModel):
    season_year: int
    club_name: str
    league_name: str
    final_position: int
    status: str


class CareerProfileResponse(BaseModel):
    manager_name: str
    bio: str
    history: List[CareerSeasonRecordModel]
    trophy_count: int


class SignRequest(BaseModel):
    player_id: int = Field(..., description="ID of the player to sign")
    fee: Optional[float] = Field(
        default=None, description="Optional override bid; defaults to fair value"
    )
    weekly_wage: Optional[float] = Field(
        default=None, description="Optional wage offer; defaults to ~110% of current"
    )
    contract_years: int = Field(default=4, ge=1, le=6)


class SignResponse(BaseModel):
    success: bool
    message: str
    player_name: str
    from_club: str
    to_club: str
    fee: float
    fee_label: str
    weekly_wage: float
    remaining_budget: float
    remaining_budget_label: str


class MatchEventModel(BaseModel):
    minute: int
    type: str
    team: str
    description: str
    player: Optional[str]


class TeamStatsModel(BaseModel):
    club_id: int
    name: str
    goals: int
    shots: int
    shots_on_target: int
    possession_pct: float
    expected_goals: float
    yellow_cards: int
    red_cards: int


class OtherResultModel(BaseModel):
    home: str
    away: str
    home_goals: int
    away_goals: int
    scoreline: str


class StandingRow(BaseModel):
    position: int
    club_id: int
    club_name: str
    played: int
    won: int
    drawn: int
    lost: int
    goal_difference: int
    points: int


class SimulateResponse(BaseModel):
    committed: bool = False
    pending_confirmation: bool = True
    matchday: int
    total_matchdays: int
    season_complete: bool
    user_match_played: bool
    scoreline: Optional[str]
    home_stats: Optional[TeamStatsModel]
    away_stats: Optional[TeamStatsModel]
    events: List[MatchEventModel]
    other_results: List[OtherResultModel]
    standings: List[StandingRow]


# --- Onboarding / session schemas ------------------------------------------
class LeagueOption(BaseModel):
    league_id: int
    league_name: str
    level: int
    club_count: int


class ClubOption(BaseModel):
    club_team_id: int
    club_name: str
    overall: float
    transfer_budget_label: str


class SetupRequest(BaseModel):
    manager_name: str = Field(..., min_length=1, max_length=40)
    league_id: int
    club_team_id: int


class SessionResponse(BaseModel):
    initialized: bool
    manager_name: Optional[str]
    league_id: Optional[int]
    league_name: Optional[str]
    club_id: Optional[int]
    club_name: Optional[str]
    squad_overall: Optional[float]
    transfer_budget_label: Optional[str]


# ===========================================================================
# Serialization helpers (domain -> DTO)
# ===========================================================================
def _serialize_player(player: Player, ctx: GameContext) -> PlayerSummary:
    value = int(ctx.controller.market.value_of(player))
    return PlayerSummary(
        player_id=player.player_id,
        name=player.short_name,
        long_name=player.long_name,
        age=player.age,
        nationality=player.nationality,
        position=player.primary_position.code,
        positions=[p.code for p in player.positions],
        overall=player.overall,
        potential=player.potential,
        market_value=value,
        market_value_label=format_money(value),
        wage_eur=player.wage_eur,
        stamina=player.base_stamina,
        fitness=round(player.fitness, 1),
        form=round(player.form, 1),
        morale=round(player.morale, 1),
        sharpness=round(player.sharpness, 1),
        pace=player.pace,
        shooting=player.shooting,
        passing=player.passing,
        dribbling=player.dribbling,
        defending=player.defending,
        physic=player.physic,
        goals=player.goals,
        assists=player.assists,
        goals_scored=player.goals_scored,
        assists_given=player.assists_given,
        clean_sheets=player.clean_sheets,
        appearances=player.appearances,
        average_rating=player.average_rating,
        is_injured=player.is_injured,
        injured_for_matchdays=player.injured_until_match,
        contract_until=player.contract_until,
    )


def _serialize_scout_target(player: Player, ctx: GameContext) -> ScoutTarget:
    value = int(ctx.controller.market.value_of(player))
    owner = ctx.controller.state.clubs.get(player.club_id) if player.club_id else None
    return ScoutTarget(
        player_id=player.player_id,
        name=player.short_name,
        age=player.age,
        nationality=player.nationality,
        position=player.primary_position.code,
        overall=player.overall,
        potential=player.potential,
        growth_potential=max(0, player.potential - player.overall),
        market_value=value,
        market_value_label=format_money(value),
        wage_eur=player.wage_eur,
        club_name=owner.name if owner else None,
    )


def _serialize_event(event: MatchEvent) -> MatchEventModel:
    return MatchEventModel(
        minute=event.minute,
        type=event.event_type.value,
        team=event.team_name,
        description=event.description,
        player=event.player_name,
    )


def _serialize_team_stats(stats, total_ticks: int) -> TeamStatsModel:
    return TeamStatsModel(
        club_id=stats.club_id,
        name=stats.name,
        goals=stats.goals,
        shots=stats.shots,
        shots_on_target=stats.shots_on_target,
        possession_pct=stats.possession_pct(total_ticks),
        expected_goals=round(stats.expected_goals, 2),
        yellow_cards=stats.yellow_cards,
        red_cards=stats.red_cards,
    )


def _serialize_standings(league: League) -> List[StandingRow]:
    rows: List[StandingRow] = []
    for rank, standing in enumerate(league.standings(), start=1):
        rows.append(
            StandingRow(
                position=rank,
                club_id=standing.club_id,
                club_name=standing.club_name,
                played=standing.played,
                won=standing.won,
                drawn=standing.drawn,
                lost=standing.lost,
                goal_difference=standing.goal_difference,
                points=standing.points,
            )
        )
    return rows


# ===========================================================================
# Routes
# ===========================================================================
def _build_session(ctx: GameContext) -> SessionResponse:
    """Snapshot of the current career/onboarding state for the frontend."""
    controller = ctx.controller
    club = controller.managed_club
    league = controller.managed_league
    return SessionResponse(
        initialized=ctx.initialized,
        manager_name=ctx.manager_name,
        league_id=league.league_id if league else None,
        league_name=league.name if league else None,
        club_id=club.club_id if club else None,
        club_name=club.name if club else None,
        squad_overall=club.overall_rating() if club else None,
        transfer_budget_label=format_money(club.transfer_budget) if club else None,
    )


@app.get("/", tags=["meta"])
def root() -> dict:
    """Lightweight liveness probe + API map."""
    return {
        "service": "FC26 Football Manager API",
        "version": app.version,
        "docs": "/docs",
        "endpoints": [
            "/api/game/session",
            "/api/leagues",
            "/api/leagues/{league_id}/clubs",
            "/api/game/setup",
            "/api/game/reset",
            "/api/status",
            "/api/squad",
            "/api/scouting/wonderkids",
            "/api/scouting/search",
            "/api/transfers/sign",
            "/api/transfers/sell",
            "/api/game/next-season",
            "/api/matchday/simulate",
            "/api/continental",
        ],
    }


# --- Onboarding endpoints --------------------------------------------------
@app.get("/api/game/session", response_model=SessionResponse, tags=["onboarding"])
def get_session(ctx: GameContext = Depends(get_context)) -> SessionResponse:
    """Report whether a career is initialized (drives onboarding vs dashboard)."""
    return _build_session(ctx)


@app.get("/api/leagues", response_model=List[LeagueOption], tags=["onboarding"])
def list_leagues(ctx: GameContext = Depends(get_context)) -> List[LeagueOption]:
    """All selectable leagues (>=2 clubs), sorted alphabetically by name."""
    options = [
        LeagueOption(
            league_id=lg.league_id,
            league_name=lg.name,
            level=lg.level,
            club_count=len(lg.clubs),
        )
        for lg in ctx.controller.state.leagues.values()
        if len(lg.clubs) >= 2
    ]
    options.sort(key=lambda o: (o.league_name.lower(), o.league_id))
    return options


@app.get(
    "/api/leagues/{league_id}/clubs",
    response_model=List[ClubOption],
    tags=["onboarding"],
)
def list_league_clubs(
    league_id: int, ctx: GameContext = Depends(get_context)
) -> List[ClubOption]:
    """All clubs belonging to ``league_id`` (alphabetical)."""
    league = ctx.controller.state.leagues.get(league_id)
    if league is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League {league_id} not found.",
        )
    options = [
        ClubOption(
            club_team_id=club.club_id,
            club_name=club.name,
            overall=club.overall_rating(),
            transfer_budget_label=format_money(club.transfer_budget),
        )
        for club in league.clubs.values()
    ]
    options.sort(key=lambda o: o.club_name.lower())
    return options


def _rebootstrap_world(ctx: GameContext) -> AppController:
    """Load a pristine game world from the CSV (safe to call mid-session).

    Discards the current career's match history, standings progress, transfer
    activity and squad condition — every club is reset to its dataset defaults.
    """
    return bootstrap(ctx.csv_path, seed=ctx.seed)


@app.post("/api/game/reset", response_model=SessionResponse, tags=["onboarding"])
def reset_career(ctx: GameContext = Depends(get_context)) -> SessionResponse:
    """Wipe the active career and return to the onboarding state.

    Safe to call at any time (mid-season, after transfers, etc.). Re-loads the
    full world from the CSV but does **not** bind a manager, league or club.
    """
    global _CONTEXT
    fresh = _rebootstrap_world(ctx)
    _CONTEXT = GameContext(
        controller=fresh,
        csv_path=ctx.csv_path,
        seed=ctx.seed,
        manager_name=None,
    )
    print("[api] Career reset — world re-bootstrapped, awaiting new onboarding.")
    return _build_session(_CONTEXT)


@app.post("/api/game/setup", response_model=SessionResponse, tags=["onboarding"])
def setup_game(
    payload: SetupRequest, ctx: GameContext = Depends(get_context)
) -> SessionResponse:
    """Reset the world and start a fresh career with the chosen league + club.

    Safe to call mid-session (re-sign / new career): always re-bootstraps the
    entire game state from the CSV so the new manager gets a clean slate.
    """
    global _CONTEXT

    # Validate the selection against the *currently loaded* world first so we
    # fail fast (cheaply) before paying for a full re-bootstrap.
    src_league = ctx.controller.state.leagues.get(payload.league_id)
    if src_league is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"League {payload.league_id} not found.",
        )
    src_club = src_league.clubs.get(payload.club_team_id)
    if src_club is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Club {payload.club_team_id} does not belong to "
                f"league {payload.league_id}."
            ),
        )

    fresh = _rebootstrap_world(ctx)
    league = fresh.state.leagues[payload.league_id]
    club = league.clubs[payload.club_team_id]
    fresh.select_league(league)   # ensures fixtures exist
    fresh.select_club(club)
    fresh.manager_name = payload.manager_name.strip()
    fresh.initialize_continental_cup()

    _CONTEXT = GameContext(
        controller=fresh,
        csv_path=ctx.csv_path,
        seed=ctx.seed,
        manager_name=payload.manager_name.strip(),
    )
    print(
        f"[api] Career initialized: {payload.manager_name} @ {club.name} "
        f"({league.name})."
    )
    return _build_session(_CONTEXT)


@app.get("/api/status", response_model=StatusResponse, tags=["game"])
def get_status(ctx: GameContext = Depends(get_context)) -> StatusResponse:
    """Headline dashboard metrics for the managed club."""
    controller = ctx.controller
    club = ctx.club
    league = ctx.league
    standing = league.table[club.club_id]
    position = next(
        (i for i, s in enumerate(league.standings(), start=1) if s.club_id == club.club_id),
        0,
    )
    return StatusResponse(
        season_year=controller.season_year,
        current_week=league.current_matchday,
        total_matchdays=league.total_matchdays,
        season_complete=league.current_matchday >= league.total_matchdays,
        pending_matchday=controller.pending_matchday is not None,
        club_id=club.club_id,
        club_name=club.name,
        league_name=league.name,
        league_position=position,
        transfer_budget=round(club.transfer_budget, 2),
        transfer_budget_label=format_money(club.transfer_budget),
        weekly_wage_bill=round(club.weekly_wage_bill, 2),
        points=standing.points,
        won=standing.won,
        drawn=standing.drawn,
        lost=standing.lost,
        goals_for=standing.goals_for,
        goals_against=standing.goals_against,
        goal_difference=standing.goal_difference,
        squad_overall=club.overall_rating(),
    )


def _serialize_lineup(club: Club) -> List[LineupSlotModel]:
    xi = club.resolve_xi()
    by_slot = {idx: slot for idx, slot in enumerate(xi)}
    slots: List[LineupSlotModel] = []
    for idx, pos in enumerate(club.formation.slots):
        slot = by_slot.get(idx)
        if slot is not None:
            slots.append(
                LineupSlotModel(
                    slot_index=idx,
                    position=pos.code,
                    player_id=slot.player.player_id,
                    player_name=slot.player.short_name,
                    overall=slot.player.overall,
                    potential=slot.player.potential,
                )
            )
        else:
            pid = club.starting_xi.get(idx)
            player = club._player_by_id(pid) if pid else None
            slots.append(
                LineupSlotModel(
                    slot_index=idx,
                    position=pos.code,
                    player_id=pid,
                    player_name=player.short_name if player else None,
                    overall=player.overall if player else None,
                    potential=player.potential if player else None,
                )
            )
    return slots


def _league_matchday_for_continental(continental_matchday: int) -> Optional[int]:
    if 1 <= continental_matchday <= len(CONTINENTAL_LEAGUE_ANCHORS):
        return CONTINENTAL_LEAGUE_ANCHORS[continental_matchday - 1]
    return None


def _serialize_continental_cup(ctx: GameContext) -> ContinentalCupResponse:
    controller = ctx.controller
    club = ctx.club
    cup = controller.continental_cup
    if cup is None:
        return ContinentalCupResponse(
            name=CONTINENTAL_CUP_NAME,
            season_year=controller.season_year,
            active=False,
            phase="inactive",
            qualified=False,
            current_matchday=0,
            total_matchdays=0,
            groups=[],
            fixtures=[],
            bracket=[],
            schedule_anchors=list(CONTINENTAL_LEAGUE_ANCHORS),
        )

    clubs = controller.state.clubs
    groups: List[ContinentalGroupModel] = []
    for group_name, rows in cup.all_group_standings().items():
        groups.append(
            ContinentalGroupModel(
                group_name=group_name,
                standings=[
                    ContinentalGroupStandingRow(
                        position=index,
                        club_id=row.club_id,
                        club_name=row.club_name,
                        played=row.played,
                        won=row.won,
                        drawn=row.drawn,
                        lost=row.lost,
                        goal_difference=row.goal_difference,
                        points=row.points,
                    )
                    for index, row in enumerate(rows, start=1)
                ],
            )
        )

    fixtures: List[ContinentalFixtureModel] = []
    bracket: List[ContinentalBracketMatchModel] = []
    for fixture in sorted(cup.fixtures, key=lambda item: (item.matchday, item.stage, item.group_name or "")):
        home = clubs.get(fixture.home_id)
        away = clubs.get(fixture.away_id)
        payload = ContinentalFixtureModel(
            matchday=fixture.matchday,
            league_matchday=_league_matchday_for_continental(fixture.matchday),
            home_id=fixture.home_id,
            home_name=home.name if home else "Unknown",
            away_id=fixture.away_id,
            away_name=away.name if away else "Unknown",
            stage=fixture.stage,
            group_name=fixture.group_name,
            home_goals=fixture.home_goals,
            away_goals=fixture.away_goals,
            is_played=fixture.is_played,
        )
        fixtures.append(payload)
        if fixture.stage != "group":
            winner_id = None
            winner_name = None
            if fixture.is_played and fixture.home_goals is not None and fixture.away_goals is not None:
                winner_id = (
                    fixture.home_id
                    if fixture.home_goals >= fixture.away_goals
                    else fixture.away_id
                )
                winner = clubs.get(winner_id)
                winner_name = winner.name if winner else None
            bracket.append(
                ContinentalBracketMatchModel(
                    matchday=fixture.matchday,
                    stage=fixture.stage,
                    home_id=fixture.home_id,
                    home_name=home.name if home else "Unknown",
                    away_id=fixture.away_id,
                    away_name=away.name if away else "Unknown",
                    home_goals=fixture.home_goals,
                    away_goals=fixture.away_goals,
                    winner_id=winner_id,
                    winner_name=winner_name,
                )
            )

    champion = clubs.get(cup.champion_club_id) if cup.champion_club_id else None
    return ContinentalCupResponse(
        name=CONTINENTAL_CUP_NAME,
        season_year=cup.season_year,
        active=cup.active,
        phase=cup.phase,
        qualified=club.club_id in cup.qualified_ids,
        current_matchday=cup.current_matchday,
        total_matchdays=cup.total_matchdays,
        champion_club_id=cup.champion_club_id,
        champion_club_name=champion.name if champion else None,
        groups=groups,
        fixtures=fixtures,
        bracket=bracket,
        schedule_anchors=list(CONTINENTAL_LEAGUE_ANCHORS),
    )


@app.get("/api/continental", response_model=ContinentalCupResponse, tags=["game"])
def get_continental_cup(ctx: GameContext = Depends(get_context)) -> ContinentalCupResponse:
    """European Champions Cup standings, bracket and scheduled matchdays."""
    return _serialize_continental_cup(ctx)


@app.get("/api/squad", response_model=SquadResponse, tags=["game"])
def get_squad(ctx: GameContext = Depends(get_context)) -> SquadResponse:
    """Full active roster of the user's club with per-player attributes."""
    club = ctx.club
    xi = club.resolve_xi()
    players = sorted(club.players, key=lambda p: p.overall, reverse=True)
    return SquadResponse(
        club_id=club.club_id,
        club_name=club.name,
        formation=club.formation.name,
        squad_overall=club.overall_rating(),
        attack_rating=club.attack_rating(xi),
        midfield_rating=club.midfield_rating(xi),
        defence_rating=club.defence_rating(xi),
        goalkeeper_rating=club.goalkeeper_rating(xi),
        player_count=len(players),
        lineup=_serialize_lineup(club),
        players=[_serialize_player(p, ctx) for p in players],
    )


@app.put("/api/squad/lineup", response_model=SquadResponse, tags=["game"])
def update_lineup(
    payload: LineupUpdateRequest, ctx: GameContext = Depends(get_context)
) -> SquadResponse:
    """Set formation and/or the 11-player starting XI used for match ratings."""
    club = ctx.club
    try:
        ctx.controller.set_lineup(
            club, payload.starting_xi, formation_name=payload.formation
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return get_squad(ctx)


@app.get(
    "/api/scouting/wonderkids", response_model=WonderkidResponse, tags=["scouting"]
)
def get_wonderkids(
    limit: int = Query(default=25, ge=1, le=100),
    max_age: int = Query(default=21, ge=15, le=25),
    min_potential: int = Query(default=80, ge=50, le=99),
    ctx: GameContext = Depends(get_context),
) -> WonderkidResponse:
    """Top young, high-ceiling transfer targets parsed live from the dataset."""
    candidates = [
        p
        for p in ctx.controller.state.players.values()
        if p.age <= max_age and p.potential >= min_potential
    ]
    # Rank by ceiling, then by remaining growth headroom.
    candidates.sort(
        key=lambda p: (p.potential, p.potential - p.overall, -p.age), reverse=True
    )
    top = candidates[:limit]
    return WonderkidResponse(
        count=len(top),
        wonderkids=[_serialize_scout_target(p, ctx) for p in top],
    )


@app.get("/api/scouting/search", response_model=SearchResponse, tags=["scouting"])
def search_players(
    name: Optional[str] = Query(default=None, description="Substring match on player name"),
    position: Optional[str] = Query(default=None, description="Exact position code, e.g. ST"),
    min_age: Optional[int] = Query(default=None, ge=15, le=45),
    max_age: Optional[int] = Query(default=None, ge=15, le=45),
    min_ovr: Optional[int] = Query(default=None, ge=40, le=99),
    max_ovr: Optional[int] = Query(default=None, ge=40, le=99),
    min_pot: Optional[int] = Query(default=None, ge=40, le=99),
    max_pot: Optional[int] = Query(default=None, ge=40, le=99),
    limit: int = Query(default=50, ge=1, le=150),
    ctx: GameContext = Depends(get_context),
) -> SearchResponse:
    """High-performance filter across the full 18,405-player dataset (stdlib)."""
    if not any([name, position, min_age, max_age, min_ovr, max_ovr, min_pot, max_pot]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one search filter.",
        )
    if min_age is not None and max_age is not None and min_age > max_age:
        raise HTTPException(status_code=400, detail="min_age cannot exceed max_age.")
    if min_ovr is not None and max_ovr is not None and min_ovr > max_ovr:
        raise HTTPException(status_code=400, detail="min_ovr cannot exceed max_ovr.")
    if min_pot is not None and max_pot is not None and min_pot > max_pot:
        raise HTTPException(status_code=400, detail="min_pot cannot exceed max_pot.")

    needle = (name or "").strip().lower()
    pos_filter = (position or "").strip().upper()
    pool = ctx.controller.state.players.values()

    results: List[Player] = []
    for player in pool:
        if needle:
            if needle not in player.short_name.lower() and needle not in player.long_name.lower():
                continue
        if pos_filter:
            codes = {p.code for p in player.positions}
            if pos_filter not in codes:
                continue
        if min_age is not None and player.age < min_age:
            continue
        if max_age is not None and player.age > max_age:
            continue
        if min_ovr is not None and player.overall < min_ovr:
            continue
        if max_ovr is not None and player.overall > max_ovr:
            continue
        if min_pot is not None and player.potential < min_pot:
            continue
        if max_pot is not None and player.potential > max_pot:
            continue
        results.append(player)

    results.sort(key=lambda p: (p.overall, p.potential), reverse=True)
    top = results[:limit]
    filters_applied = {
        k: v
        for k, v in {
            "name": name,
            "position": pos_filter or None,
            "min_age": min_age,
            "max_age": max_age,
            "min_ovr": min_ovr,
            "max_ovr": max_ovr,
            "min_pot": min_pot,
            "max_pot": max_pot,
        }.items()
        if v is not None and v != ""
    }
    return SearchResponse(
        filters_applied=filters_applied,
        count=len(top),
        results=[_serialize_scout_target(p, ctx) for p in top],
    )


@app.post("/api/transfers/sign", response_model=SignResponse, tags=["transfers"])
def sign_player(
    payload: SignRequest, ctx: GameContext = Depends(get_context)
) -> SignResponse:
    """Run the transfer validation matrix and attempt to sign a player."""
    controller = ctx.controller
    club = ctx.club
    target = controller.state.players.get(payload.player_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player {payload.player_id} not found.",
        )
    if target.club_id == club.club_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{target.short_name} already plays for {club.name}.",
        )
    _, fair, _ = controller.market.band_for(target)
    fee = float(payload.fee) if payload.fee is not None else fair
    wage = (
        float(payload.weekly_wage)
        if payload.weekly_wage is not None
        else max(target.wage_eur * 1.10, fair * 0.0005)
    )

    outcome = controller.make_bid(
        target, fee=fee, weekly_wage=wage, years=payload.contract_years
    )
    return SignResponse(
        success=outcome.accepted,
        message=outcome.reason,
        player_name=outcome.player_name,
        from_club=outcome.from_club,
        to_club=outcome.to_club,
        fee=round(outcome.fee, 2),
        fee_label=format_money(outcome.fee),
        weekly_wage=round(outcome.wage_weekly, 2),
        remaining_budget=round(club.transfer_budget, 2),
        remaining_budget_label=format_money(club.transfer_budget),
    )


@app.post("/api/transfers/sell", response_model=SellResponse, tags=["transfers"])
def sell_player(
    payload: SellRequest, ctx: GameContext = Depends(get_context)
) -> SellResponse:
    """Sell a squad player to an anonymous buyer at market rate."""
    controller = ctx.controller
    club = ctx.club
    try:
        deal = controller.sell_player(club, payload.player_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SellResponse(
        success=True,
        message=(
            f"{deal['player_name']} sold to {deal['buyer_club']} for "
            f"{deal['fee_label']}."
        ),
        player_name=str(deal["player_name"]),
        buyer_club=str(deal["buyer_club"]),
        fee=float(deal["fee"]),
        fee_label=str(deal["fee_label"]),
        multiplier_pct=float(deal["multiplier_pct"]),
        market_value=int(deal["market_value"]),
        market_value_label=str(deal["market_value_label"]),
        remaining_budget=float(deal["remaining_budget"]),
        remaining_budget_label=str(deal["remaining_budget_label"]),
        squad_size=int(deal["squad_size"]),
    )


@app.post("/api/game/next-season", response_model=NextSeasonResponse, tags=["game"])
def advance_next_season(ctx: GameContext = Depends(get_context)) -> NextSeasonResponse:
    """Roll into a new season after the final matchweek is committed."""
    controller = ctx.controller
    league = ctx.league
    club = ctx.club
    try:
        summary = controller.advance_to_next_season(league, club)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    promo_msg = ""
    if summary.get("promoted"):
        promo_msg = (
            f" PROMOTION SECURED — welcome to {summary.get('promotion_to_league')}!"
        )

    return NextSeasonResponse(
        success=True,
        message=(
            f"Welcome to the {summary['new_season_year']} campaign! "
            f"Finished {summary['previous_season_year']} in "
            f"{_ordinal(summary['league_position'])} place.{promo_msg}"
        ),
        previous_season_year=summary["previous_season_year"],
        new_season_year=summary["new_season_year"],
        league_position=summary["league_position"],
        budget_bonus=summary["budget_bonus"],
        budget_bonus_label=summary["budget_bonus_label"],
        new_transfer_budget=summary["new_transfer_budget"],
        new_transfer_budget_label=summary["new_transfer_budget_label"],
        total_matchdays=summary["total_matchdays"],
        promoted=bool(summary.get("promoted")),
        promotion_from_league=summary.get("promotion_from_league"),
        promotion_to_league=summary.get("promotion_to_league"),
        new_league_id=summary.get("new_league_id"),
        new_league_name=summary.get("new_league_name"),
        new_league_level=summary.get("new_league_level"),
        matchday_win_reward=float(summary.get("matchday_win_reward", 0)),
        matchday_draw_reward=float(summary.get("matchday_draw_reward", 0)),
        season_status=str(summary.get("season_status", "Stayed")),
    )


@app.get("/api/career/profile", response_model=CareerProfileResponse, tags=["game"])
def get_career_profile(ctx: GameContext = Depends(get_context)) -> CareerProfileResponse:
    """Manager biography and chronological trophy-room history."""
    profile = ctx.controller.career_profile()
    return CareerProfileResponse(
        manager_name=str(profile["manager_name"]),
        bio=str(profile["bio"]),
        history=[CareerSeasonRecordModel(**row) for row in profile["history"]],
        trophy_count=int(profile["trophy_count"]),
    )


@app.post("/api/transfers/accept-bid", response_model=AcceptBidResponse, tags=["transfers"])
def accept_incoming_bid(
    payload: AcceptBidRequest, ctx: GameContext = Depends(get_context)
) -> AcceptBidResponse:
    """Accept a mega-club incoming bid — player leaves, fee credited."""
    controller = ctx.controller
    club = ctx.club
    try:
        deal = controller.accept_incoming_bid(club, payload.player_id, payload.fee)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AcceptBidResponse(
        success=True,
        message=f"{deal['player_name']} sold. {deal['fee_label']} credited.",
        player_name=str(deal["player_name"]),
        fee=float(deal["fee"]),
        fee_label=str(deal["fee_label"]),
        remaining_budget=float(deal["remaining_budget"]),
        remaining_budget_label=str(deal["remaining_budget_label"]),
        squad_size=int(deal["squad_size"]),
    )


def _ordinal(n: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}
    v = n % 100
    return f"{n}{suffix.get(v if v < 20 else v % 10, 'th')}"


def _build_simulate_response(
    league: League,
    club: Club,
    results: List[MatchResult],
    *,
    committed: bool,
    preview_matchday: int,
) -> SimulateResponse:
    user_match = next(
        (r for r in results if club.club_id in (r.home_club_id, r.away_club_id)),
        None,
    )
    events: List[MatchEventModel] = []
    home_stats = away_stats = None
    scoreline: Optional[str] = None
    if user_match is not None:
        scoreline = user_match.scoreline
        total_ticks = (
            user_match.home_stats.possession_ticks
            + user_match.away_stats.possession_ticks
        )
        home_stats = _serialize_team_stats(user_match.home_stats, total_ticks)
        away_stats = _serialize_team_stats(user_match.away_stats, total_ticks)
        events = [_serialize_event(e) for e in user_match.events]

    other_results = [
        OtherResultModel(
            home=r.home_name,
            away=r.away_name,
            home_goals=r.home_goals,
            away_goals=r.away_goals,
            scoreline=r.scoreline,
        )
        for r in results
        if r is not user_match
    ]

    effective_md = preview_matchday if not committed else league.current_matchday
    return SimulateResponse(
        committed=committed,
        pending_confirmation=not committed,
        matchday=effective_md,
        total_matchdays=league.total_matchdays,
        season_complete=effective_md >= league.total_matchdays,
        user_match_played=user_match is not None,
        scoreline=scoreline,
        home_stats=home_stats,
        away_stats=away_stats,
        events=events,
        other_results=other_results,
        standings=_serialize_standings(league),
    )


@app.post("/api/matchday/simulate", response_model=SimulateResponse, tags=["game"])
def simulate_matchday(ctx: GameContext = Depends(get_context)) -> SimulateResponse:
    """Preview the next matchday without committing standings (anti-spoiler)."""
    controller = ctx.controller
    club = ctx.club
    league = ctx.league

    if league.current_matchday >= league.total_matchdays:
        return SimulateResponse(
            committed=False,
            pending_confirmation=False,
            matchday=league.current_matchday,
            total_matchdays=league.total_matchdays,
            season_complete=True,
            user_match_played=False,
            scoreline=None,
            home_stats=None,
            away_stats=None,
            events=[],
            other_results=[],
            standings=_serialize_standings(league),
        )

    pending = controller.simulate_matchday_preview(league, commentary_club_id=club.club_id)
    results = [r for _, r in pending.pairs]
    return _build_simulate_response(
        league,
        club,
        results,
        committed=False,
        preview_matchday=pending.matchday,
    )


@app.post("/api/matchday/confirm", response_model=ConfirmMatchdayResponse, tags=["game"])
def confirm_matchday(ctx: GameContext = Depends(get_context)) -> ConfirmMatchdayResponse:
    """Commit a previewed matchday after the live ticker finishes."""
    controller = ctx.controller
    league = ctx.league
    if controller.pending_matchday is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending matchday to confirm. Simulate a matchday first.",
        )
    try:
        _, reward = controller.confirm_matchday(league, ctx.club)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    bid_raw = reward.get("incoming_bid")
    incoming_bid = None
    if isinstance(bid_raw, dict):
        incoming_bid = IncomingTransferBidModel(**bid_raw)

    return ConfirmMatchdayResponse(
        committed=True,
        matchday=league.current_matchday,
        total_matchdays=league.total_matchdays,
        season_complete=league.current_matchday >= league.total_matchdays,
        standings=_serialize_standings(league),
        match_reward=float(reward["match_reward"]),
        match_reward_label=str(reward["match_reward_label"]),
        match_reward_outcome=str(reward["match_reward_outcome"]),
        continental_match_played=bool(reward.get("continental_match_played")),
        continental_match_reward=float(reward.get("continental_match_reward", 0)),
        continental_match_reward_label=str(
            reward.get("continental_match_reward_label", format_money(0))
        ),
        continental_match_reward_outcome=str(
            reward.get("continental_match_reward_outcome", "none")
        ),
        transfer_budget=float(reward["transfer_budget"]),
        transfer_budget_label=str(reward["transfer_budget_label"]),
        incoming_bid=incoming_bid,
    )


if __name__ == "__main__":  # pragma: no cover - convenience launcher
    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.environ.get("FM_PORT", "8000")),
        reload=False,
    )
