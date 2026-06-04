"""
domain_models.py
================
Core domain layer for the Football Manager Game Engine.

This module defines the deep object-oriented model that the entire engine is
built upon:

    * :class:`Player`  - an individual footballer with static ratings, dynamic
      match-state (fitness, morale, form, sharpness) and an age-curve driven
      development / XP system.
    * :class:`Club`    - a squad with a configurable :class:`Formation`,
      tactical sliders, finances (transfer budget + wage bill) and derived
      sector ratings (attack / midfield / defence / goalkeeping).
    * :class:`League`  - a competition that owns a set of clubs, generates a
      double round-robin fixture list and maintains a live standings table.

The module is intentionally dependency-free (pure standard library) so that it
can be embedded anywhere and scales comfortably to the full 18,000+ player
FC26 dataset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "Sector",
    "Position",
    "Mentality",
    "WorkRate",
    "TacticalSetup",
    "Formation",
    "FORMATIONS",
    "DevelopmentReport",
    "Player",
    "SquadSlot",
    "Club",
    "Standing",
    "Fixture",
    "League",
]


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class Sector(Enum):
    """A coarse pitch sector used by the simulation engine for match-ups."""

    GOALKEEPER = "GK"
    DEFENCE = "DEF"
    MIDFIELD = "MID"
    ATTACK = "ATT"


class Position(Enum):
    """Concrete on-pitch positions mapped to a coarse :class:`Sector`."""

    GK = ("GK", Sector.GOALKEEPER)
    RB = ("RB", Sector.DEFENCE)
    RWB = ("RWB", Sector.DEFENCE)
    CB = ("CB", Sector.DEFENCE)
    LB = ("LB", Sector.DEFENCE)
    LWB = ("LWB", Sector.DEFENCE)
    CDM = ("CDM", Sector.MIDFIELD)
    CM = ("CM", Sector.MIDFIELD)
    CAM = ("CAM", Sector.MIDFIELD)
    RM = ("RM", Sector.MIDFIELD)
    LM = ("LM", Sector.MIDFIELD)
    RW = ("RW", Sector.ATTACK)
    LW = ("LW", Sector.ATTACK)
    CF = ("CF", Sector.ATTACK)
    ST = ("ST", Sector.ATTACK)

    def __init__(self, code: str, sector: Sector) -> None:
        self.code = code
        self.sector = sector

    @classmethod
    def from_code(cls, code: str) -> Optional["Position"]:
        code = code.strip().upper()
        for member in cls:
            if member.code == code:
                return member
        # Common FC/FIFA aliases that are not 1:1 with our canonical set.
        aliases = {
            "RWB": cls.RWB, "LWB": cls.LWB,
            "RDM": cls.CDM, "LDM": cls.CDM, "RCM": cls.CM, "LCM": cls.CM,
            "RCB": cls.CB, "LCB": cls.CB,
            "RAM": cls.CAM, "LAM": cls.CAM,
            "RES": None, "SUB": None,
        }
        return aliases.get(code)


# Position compatibility matrix: how well a player of native position P can be
# deployed in slot S (1.0 == perfect, lower == out of position penalty).
_POSITION_FIT: Dict[Position, Dict[Position, float]] = {}


def _build_position_fit() -> None:
    """Pre-compute the position compatibility matrix once at import time."""

    # Players who share a sector are reasonably interchangeable; identical
    # positions are perfect; cross-sector deployment is heavily penalised.
    same_sector = 0.90
    neighbour_sector = 0.72
    far_sector = 0.45
    sector_order = [
        Sector.GOALKEEPER,
        Sector.DEFENCE,
        Sector.MIDFIELD,
        Sector.ATTACK,
    ]
    for native in Position:
        _POSITION_FIT[native] = {}
        for slot in Position:
            if native is slot:
                fit = 1.0
            elif native.sector is slot.sector:
                fit = same_sector
            else:
                distance = abs(
                    sector_order.index(native.sector)
                    - sector_order.index(slot.sector)
                )
                fit = neighbour_sector if distance == 1 else far_sector
            # A goalkeeper is essentially useless outfield and vice versa.
            if (native.sector is Sector.GOALKEEPER) ^ (
                slot.sector is Sector.GOALKEEPER
            ):
                fit = 0.20
            _POSITION_FIT[native][slot] = fit


_build_position_fit()


class Mentality(Enum):
    """Team mentality slider, biasing the attack/defence balance."""

    VERY_DEFENSIVE = ("Very Defensive", -2)
    DEFENSIVE = ("Defensive", -1)
    BALANCED = ("Balanced", 0)
    ATTACKING = ("Attacking", 1)
    VERY_ATTACKING = ("Very Attacking", 2)

    def __init__(self, label: str, bias: int) -> None:
        self.label = label
        self.bias = bias


class WorkRate(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @classmethod
    def parse(cls, value: str) -> "WorkRate":
        value = (value or "").strip().lower()
        if value.startswith("high"):
            return cls.HIGH
        if value.startswith("low"):
            return cls.LOW
        return cls.MEDIUM


# ---------------------------------------------------------------------------
# Tactical configuration
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TacticalSetup:
    """Continuous tactical sliders attached to a :class:`Club`.

    All sliders are expressed on a normalised 0-100 scale (50 == neutral) so
    the simulation engine can blend them linearly.
    """

    tempo: int = 50          # ball circulation speed -> chance volume vs fatigue
    pressing: int = 50       # defensive intensity -> turnovers vs stamina cost
    mentality: Mentality = Mentality.BALANCED
    width: int = 50          # narrow (0) .. wide (100)
    defensive_line: int = 50  # deep (0) .. high line (100)

    def clamp(self) -> None:
        self.tempo = int(_clamp(self.tempo, 0, 100))
        self.pressing = int(_clamp(self.pressing, 0, 100))
        self.width = int(_clamp(self.width, 0, 100))
        self.defensive_line = int(_clamp(self.defensive_line, 0, 100))

    @property
    def attack_modifier(self) -> float:
        """Multiplicative attacking output modifier from sliders."""
        base = 1.0 + self.mentality.bias * 0.06
        base += (self.tempo - 50) / 500.0
        return round(base, 4)

    @property
    def defence_modifier(self) -> float:
        """Multiplicative defensive solidity modifier from sliders."""
        base = 1.0 - self.mentality.bias * 0.045
        base += (self.pressing - 50) / 600.0
        return round(base, 4)

    @property
    def stamina_drain_modifier(self) -> float:
        """High tempo + high pressing burns more fitness per minute."""
        return round(1.0 + (self.tempo - 50) / 250.0 + (self.pressing - 50) / 220.0, 4)


@dataclass(frozen=True, slots=True)
class Formation:
    """An immutable formation template, e.g. 4-3-3."""

    name: str
    slots: Tuple[Position, ...]

    def __post_init__(self) -> None:
        if len(self.slots) != 11:
            raise ValueError(f"Formation {self.name} must define 11 slots")

    def sector_counts(self) -> Dict[Sector, int]:
        counts: Dict[Sector, int] = {s: 0 for s in Sector}
        for pos in self.slots:
            counts[pos.sector] += 1
        return counts


def _f(name: str, codes: Sequence[str]) -> Formation:
    return Formation(name, tuple(Position.from_code(c) for c in codes))  # type: ignore[arg-type]


FORMATIONS: Dict[str, Formation] = {
    "4-3-3": _f("4-3-3", ["GK", "RB", "CB", "CB", "LB", "CM", "CM", "CAM", "RW", "ST", "LW"]),
    "4-4-2": _f("4-4-2", ["GK", "RB", "CB", "CB", "LB", "RM", "CM", "CM", "LM", "ST", "ST"]),
    "4-2-3-1": _f("4-2-3-1", ["GK", "RB", "CB", "CB", "LB", "CDM", "CDM", "CAM", "RM", "LM", "ST"]),
    "3-5-2": _f("3-5-2", ["GK", "CB", "CB", "CB", "RM", "CM", "CDM", "CM", "LM", "ST", "ST"]),
    "4-1-2-1-2": _f("4-1-2-1-2", ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CM", "CAM", "ST", "ST"]),
    "5-3-2": _f("5-3-2", ["GK", "RWB", "CB", "CB", "CB", "LWB", "CM", "CM", "CM", "ST", "ST"]),
    "4-3-3 (False 9)": _f("4-3-3 (False 9)", ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CM", "RW", "CF", "LW"]),
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_int(raw: str, default: int = 0) -> int:
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    # FC position-rating cells look like "86+3"; take the base number.
    for sep in ("+", "-"):
        if sep in raw[1:]:
            raw = raw.split(sep)[0]
            break
    try:
        return int(float(raw))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DevelopmentReport:
    """Outcome of a development tick for auditing/UX."""

    player_id: int
    name: str
    old_overall: int
    new_overall: int
    xp_gained: float
    note: str

    @property
    def delta(self) -> int:
        return self.new_overall - self.old_overall


@dataclass(slots=True)
class Player:
    """A single footballer.

    Static attributes are seeded from the FC26 dataset; dynamic attributes are
    mutated throughout a season by the simulation, development and transfer
    subsystems.
    """

    # --- Identity -----------------------------------------------------------
    player_id: int
    short_name: str
    long_name: str
    age: int
    nationality: str

    # --- Core ratings -------------------------------------------------------
    overall: int
    potential: int
    positions: List[Position]
    value_eur: int
    wage_eur: int

    # --- Physical / technical pillars --------------------------------------
    pace: int = 50
    shooting: int = 50
    passing: int = 50
    dribbling: int = 50
    defending: int = 50
    physic: int = 50
    base_stamina: int = 60

    # --- Goalkeeping pillars (only meaningful for keepers) -----------------
    gk_diving: int = 10
    gk_handling: int = 10
    gk_kicking: int = 10
    gk_positioning: int = 10
    gk_reflexes: int = 10

    # --- Personality / meta -------------------------------------------------
    preferred_foot: str = "Right"
    weak_foot: int = 3
    skill_moves: int = 3
    international_reputation: int = 1
    attacking_work_rate: WorkRate = WorkRate.MEDIUM
    defensive_work_rate: WorkRate = WorkRate.MEDIUM
    height_cm: int = 180
    weight_kg: int = 75
    contract_until: int = 2026
    squad_number: int = 0

    # --- Ownership ----------------------------------------------------------
    club_id: Optional[int] = None

    # --- Dynamic season state ----------------------------------------------
    fitness: float = 100.0       # 0-100 freshness between matches
    stamina_current: float = 100.0  # 0-100 in-match energy
    morale: float = 75.0         # 0-100 happiness
    form: float = 50.0           # 0-100 rolling performance trend
    sharpness: float = 70.0      # 0-100 match sharpness
    xp: float = 0.0
    injured_until_match: int = 0  # global matchday index when fit again
    yellow_cards: int = 0
    red_cards: int = 0

    # --- Season aggregate stats --------------------------------------------
    appearances: int = 0
    goals: int = 0
    assists: int = 0
    clean_sheets: int = 0
    rating_history: List[float] = field(default_factory=list)

    @property
    def goals_scored(self) -> int:
        """Alias used by API / UI longevity stats."""
        return self.goals

    @goals_scored.setter
    def goals_scored(self, value: int) -> None:
        self.goals = max(0, int(value))

    @property
    def assists_given(self) -> int:
        return self.assists

    @assists_given.setter
    def assists_given(self, value: int) -> None:
        self.assists = max(0, int(value))

    # ------------------------------------------------------------------ #
    # Derived / read-only properties
    # ------------------------------------------------------------------ #
    @property
    def primary_position(self) -> Position:
        return self.positions[0] if self.positions else Position.CM

    @property
    def primary_sector(self) -> Sector:
        return self.primary_position.sector

    @property
    def is_goalkeeper(self) -> bool:
        return self.primary_sector is Sector.GOALKEEPER

    @property
    def average_rating(self) -> float:
        if not self.rating_history:
            return 0.0
        return round(sum(self.rating_history) / len(self.rating_history), 2)

    @property
    def is_injured(self) -> bool:
        return self.injured_until_match > 0

    @property
    def is_wonderkid(self) -> bool:
        return self.age <= 21 and (self.potential - self.overall) >= 6

    # ------------------------------------------------------------------ #
    # Role ratings (used by Club sector calculations & the match engine)
    # ------------------------------------------------------------------ #
    def role_rating(self, sector: Sector) -> float:
        """Compute how strong this player is when operating in ``sector``.

        Blends the headline overall with the attribute pillars that matter
        most for that sector, then applies a position-fit penalty when the
        player is asked to operate away from their natural sector.
        """

        if sector is Sector.GOALKEEPER:
            if self.is_goalkeeper:
                base = (
                    self.gk_diving
                    + self.gk_handling
                    + self.gk_positioning
                    + self.gk_reflexes
                ) / 4.0
                base = max(base, self.overall)
            else:
                base = 25.0
        elif sector is Sector.DEFENCE:
            base = 0.55 * self.overall + 0.30 * self.defending + 0.15 * self.physic
        elif sector is Sector.MIDFIELD:
            base = (
                0.45 * self.overall
                + 0.30 * self.passing
                + 0.15 * self.dribbling
                + 0.10 * self.physic
            )
        else:  # ATTACK
            base = (
                0.45 * self.overall
                + 0.30 * self.shooting
                + 0.15 * self.pace
                + 0.10 * self.dribbling
            )

        fit = max(_POSITION_FIT[self.primary_position][p] for p in self._slots_in(sector))
        return round(base * fit, 2)

    @staticmethod
    def _slots_in(sector: Sector) -> List[Position]:
        return [p for p in Position if p.sector is sector]

    def fit_for_slot(self, slot: Position) -> float:
        """Position compatibility (0..1) of this player for a formation slot."""
        return max(_POSITION_FIT[p][slot] for p in self.positions) if self.positions else 0.45

    def slot_effective_rating(self, slot: Position) -> float:
        """Effective rating when fielded in ``slot`` incl. live condition."""
        sector_rating = self.role_rating(slot.sector)
        fit = self.fit_for_slot(slot)
        condition = self.condition_multiplier()
        return round(sector_rating * (0.6 + 0.4 * fit) * condition, 2)

    def condition_multiplier(self) -> float:
        """Combined live multiplier from fitness, morale, form & sharpness."""
        fitness_factor = 0.80 + 0.20 * (self.fitness / 100.0)
        morale_factor = 0.95 + 0.10 * (self.morale / 100.0)
        form_factor = 0.95 + 0.10 * (self.form / 100.0)
        sharp_factor = 0.97 + 0.06 * (self.sharpness / 100.0)
        return round(fitness_factor * morale_factor * form_factor * sharp_factor, 4)

    def effective_overall(self) -> float:
        """Overall adjusted for live condition (used for quick comparisons)."""
        return round(self.overall * self.condition_multiplier(), 2)

    # ------------------------------------------------------------------ #
    # Live match state mutations
    # ------------------------------------------------------------------ #
    def drain_stamina(self, intensity: float) -> None:
        """Per-minute in-match stamina depletion.

        Players with higher base stamina/physic deplete slower; intensity is a
        team-tactics derived multiplier (see :pyattr:`TacticalSetup`).
        """
        endurance = 0.5 + (self.base_stamina / 200.0)  # 0.5 .. 1.0
        drain = intensity * (1.10 - endurance) * 1.6
        self.stamina_current = _clamp(self.stamina_current - drain, 0.0, 100.0)

    def in_match_performance(self, slot: Position) -> float:
        """Effective slot rating that also decays with in-match stamina."""
        stamina_factor = 0.85 + 0.15 * (self.stamina_current / 100.0)
        return self.slot_effective_rating(slot) * stamina_factor

    def reset_match_state(self) -> None:
        self.stamina_current = self.fitness  # start match as fresh as recovery allows

    def recover(self, days: float = 3.0) -> None:
        """Between-match recovery of fitness & sharpness."""
        recovery_rate = 6.0 + (self.base_stamina / 25.0)
        self.fitness = _clamp(self.fitness + recovery_rate * (days / 3.0), 0.0, 100.0)
        self.sharpness = _clamp(self.sharpness + 4.0, 0.0, 100.0)
        if self.injured_until_match > 0:
            self.injured_until_match -= 1

    def apply_match_load(self, minutes: int, tactical_drain: float) -> None:
        """Apply post-match fitness cost based on minutes played."""
        load = (minutes / 90.0) * (14.0 + tactical_drain * 3.0)
        endurance_relief = self.base_stamina / 30.0
        self.fitness = _clamp(self.fitness - max(2.0, load - endurance_relief), 0.0, 100.0)
        self.sharpness = _clamp(self.sharpness + minutes / 18.0, 0.0, 100.0)

    def register_match_rating(self, rating: float) -> None:
        rating = round(_clamp(rating, 1.0, 10.0), 2)
        self.rating_history.append(rating)
        # Form is an exponential moving average of recent ratings (scaled 0-100).
        target = rating * 10.0
        self.form = round(_clamp(0.65 * self.form + 0.35 * target, 0.0, 100.0), 2)
        # Morale nudged by whether the player out/under-performed expectation.
        if rating >= 7.5:
            self.morale = _clamp(self.morale + 4.0, 0.0, 100.0)
        elif rating < 5.5:
            self.morale = _clamp(self.morale - 5.0, 0.0, 100.0)

    # ------------------------------------------------------------------ #
    # Development / XP system (age-curve driven)
    # ------------------------------------------------------------------ #
    def age_growth_coefficient(self) -> float:
        """Return a signed growth coefficient based on the classic age curve.

        Positive -> player can still improve (fast for wonderkids), negative ->
        the player declines (accelerating for veterans).
        """
        if self.age <= 18:
            return 1.35
        if self.age <= 21:
            return 1.10
        if self.age <= 23:
            return 0.75
        if self.age <= 26:
            return 0.35
        if self.age <= 29:
            return 0.10
        if self.age <= 31:
            return -0.20
        if self.age <= 33:
            return -0.55
        return -0.95

    def gain_xp(self, minutes: int, rating: float, team_quality: float) -> None:
        """Accumulate development XP from a single appearance."""
        # Playing against/with stronger sides accelerates growth.
        exposure = team_quality / 80.0
        perf = max(0.0, rating - 5.0) / 5.0
        self.xp += (minutes / 90.0) * (1.0 + perf) * exposure

    def develop(self, matches_factor: float = 1.0) -> DevelopmentReport:
        """Convert accumulated XP into an overall change once per period.

        The headroom to ``potential`` gates growth; veterans ignore XP and
        decline purely on the age curve.
        """
        old = self.overall
        coeff = self.age_growth_coefficient()
        note = ""

        if coeff > 0:
            headroom = max(0, self.potential - self.overall)
            # Growth proportional to XP, age coefficient and remaining headroom.
            growth = self.xp * coeff * 0.08 * matches_factor
            growth *= 1.0 + min(1.0, headroom / 12.0)
            applied = int(_clamp(round(growth), 0, headroom))
            if applied > 0:
                self.overall += applied
                note = "wonderkid surge" if self.is_wonderkid else "progression"
            else:
                note = "marginal gains"
        else:
            # Decline: faster with age, partially mitigated by sharpness/fitness.
            decline_pressure = abs(coeff) * matches_factor
            condition_relief = (self.fitness + self.sharpness) / 400.0
            decline = decline_pressure * (1.3 - condition_relief)
            applied = int(_clamp(round(decline), 0, 4))
            if applied > 0:
                self.overall = max(40, self.overall - applied)
                note = "veteran decline"
            else:
                note = "holding level"

        # Re-base potential for players who exceeded expectations.
        self.potential = max(self.potential, self.overall)
        xp_spent = self.xp
        self.xp = 0.0
        return DevelopmentReport(
            player_id=self.player_id,
            name=self.short_name,
            old_overall=old,
            new_overall=self.overall,
            xp_gained=round(xp_spent, 2),
            note=note,
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        pos = "/".join(p.code for p in self.positions) or "?"
        return f"<Player {self.short_name} {self.overall}OVR ({pos})>"


# ---------------------------------------------------------------------------
# Club
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SquadSlot:
    """Pairing of a formation position with the chosen player."""

    position: Position
    player: Player
    effective_rating: float


@dataclass(slots=True)
class Club:
    """A football club: squad + tactics + finances."""

    club_id: int
    name: str
    league_id: int
    players: List[Player] = field(default_factory=list)
    formation: Formation = field(default_factory=lambda: FORMATIONS["4-3-3"])
    tactics: TacticalSetup = field(default_factory=TacticalSetup)

    transfer_budget: float = 0.0
    wage_budget_weekly: float = 0.0

    # User-selected starting XI: formation slot index (0-10) -> player_id
    starting_xi: Dict[int, int] = field(default_factory=dict)

    # transient cache of the most recently resolved XI
    _xi_cache: Optional[List[SquadSlot]] = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    # Squad management
    # ------------------------------------------------------------------ #
    def add_player(self, player: Player) -> None:
        player.club_id = self.club_id
        self.players.append(player)
        self._xi_cache = None

    def remove_player(self, player: Player) -> None:
        self.players = [p for p in self.players if p.player_id != player.player_id]
        if player.club_id == self.club_id:
            player.club_id = None
        self._xi_cache = None
        self.starting_xi = {
            idx: pid for idx, pid in self.starting_xi.items() if pid != player.player_id
        }

    def set_starting_xi(self, assignments: Dict[int, int]) -> None:
        """Assign players to formation slot indices (0-10). Validates count & squad."""
        if len(assignments) != 11:
            raise ValueError("Starting XI must contain exactly 11 slot assignments.")
        squad_ids = {p.player_id for p in self.players}
        for idx, pid in assignments.items():
            if idx < 0 or idx > 10:
                raise ValueError(f"Invalid slot index {idx}.")
            if pid not in squad_ids:
                raise ValueError(f"Player {pid} is not in this squad.")
        if len(set(assignments.values())) != 11:
            raise ValueError("Each starting XI slot must have a unique player.")
        self.starting_xi = dict(assignments)
        self._xi_cache = None

    def _player_by_id(self, player_id: int) -> Optional[Player]:
        for player in self.players:
            if player.player_id == player_id:
                return player
        return None

    @property
    def squad_size(self) -> int:
        return len(self.players)

    @property
    def weekly_wage_bill(self) -> float:
        return float(sum(p.wage_eur for p in self.players))

    @property
    def squad_market_value(self) -> float:
        return float(sum(p.value_eur for p in self.players))

    def available_players(self, current_match_index: int = 0) -> List[Player]:
        return [
            p
            for p in self.players
            if p.injured_until_match <= 0 and p.red_cards == 0
        ]

    # ------------------------------------------------------------------ #
    def ensure_valid_lineup(self) -> None:
        """Drop released players from XI and auto-fill if fewer than 11 remain."""
        squad_ids = {p.player_id for p in self.players}
        self.starting_xi = {
            idx: pid for idx, pid in self.starting_xi.items() if pid in squad_ids
        }
        if len(self.starting_xi) < 11 and self.squad_size >= 11:
            for idx, slot in enumerate(self.select_best_xi()):
                self.starting_xi[idx] = slot.player.player_id
        self._xi_cache = None

    # Starting XI resolution (manual lineup or auto best XI)
    # ------------------------------------------------------------------ #
    def resolve_xi(
        self,
        formation: Optional[Formation] = None,
        respect_condition: bool = True,
    ) -> List[SquadSlot]:
        """Return the active XI used for ratings and match simulation."""
        formation = formation or self.formation
        if len(self.starting_xi) == 11:
            xi: List[SquadSlot] = []
            for slot_idx, pos in enumerate(formation.slots):
                pid = self.starting_xi.get(slot_idx)
                if pid is None:
                    break
                player = self._player_by_id(pid)
                if player is None:
                    break
                score = (
                    player.slot_effective_rating(pos)
                    if respect_condition
                    else player.role_rating(pos.sector) * player.fit_for_slot(pos)
                )
                xi.append(SquadSlot(pos, player, round(score, 2)))
            if len(xi) == 11:
                self._xi_cache = xi
                return xi
        return self.select_best_xi(formation, respect_condition)

    # ------------------------------------------------------------------ #
    # Best XI selection (greedy, position-fit & condition aware)
    # ------------------------------------------------------------------ #
    def select_best_xi(
        self,
        formation: Optional[Formation] = None,
        respect_condition: bool = True,
    ) -> List[SquadSlot]:
        """Pick the strongest legal XI for ``formation``.

        Greedy assignment: positions are filled in order of scarcity, each time
        choosing the highest effective-rating player still available. This is
        fast (O(slots * squad)) which matters when simulating an entire league.
        """

        formation = formation or self.formation
        pool = self.available_players()
        if not pool:
            pool = list(self.players)  # emergency: field anyone

        used: set[int] = set()
        xi: List[SquadSlot] = []

        # Fill scarcer sectors (fewer eligible players) first for better fits.
        slots_sorted = sorted(
            enumerate(formation.slots),
            key=lambda item: sum(1 for p in pool if p.fit_for_slot(item[1]) >= 0.85),
        )

        for _, slot in slots_sorted:
            best_player: Optional[Player] = None
            best_score = -1.0
            for player in pool:
                if player.player_id in used:
                    continue
                score = (
                    player.slot_effective_rating(slot)
                    if respect_condition
                    else player.role_rating(slot.sector) * player.fit_for_slot(slot)
                )
                if score > best_score:
                    best_score = score
                    best_player = player
            if best_player is not None:
                used.add(best_player.player_id)
                xi.append(SquadSlot(slot, best_player, round(best_score, 2)))

        # Restore formation order for presentation.
        order = {pos: i for i, pos in enumerate(formation.slots)}
        xi.sort(key=lambda s: order.get(s.position, 99))
        self._xi_cache = xi
        return xi

    # ------------------------------------------------------------------ #
    # Sector ratings (the heart of the match-up engine)
    # ------------------------------------------------------------------ #
    def sector_rating(self, sector: Sector, xi: Optional[List[SquadSlot]] = None) -> float:
        xi = xi or self.resolve_xi()
        members = [s for s in xi if s.position.sector is sector]
        if not members:
            return 35.0
        return round(sum(s.effective_rating for s in members) / len(members), 2)

    def attack_rating(self, xi: Optional[List[SquadSlot]] = None) -> float:
        xi = xi or self.resolve_xi()
        att = self.sector_rating(Sector.ATTACK, xi)
        mid = self.sector_rating(Sector.MIDFIELD, xi)
        raw = 0.7 * att + 0.3 * mid
        return round(raw * self.tactics.attack_modifier, 2)

    def midfield_rating(self, xi: Optional[List[SquadSlot]] = None) -> float:
        xi = xi or self.resolve_xi()
        return self.sector_rating(Sector.MIDFIELD, xi)

    def defence_rating(self, xi: Optional[List[SquadSlot]] = None) -> float:
        xi = xi or self.resolve_xi()
        deff = self.sector_rating(Sector.DEFENCE, xi)
        mid = self.sector_rating(Sector.MIDFIELD, xi)
        raw = 0.75 * deff + 0.25 * mid
        return round(raw * self.tactics.defence_modifier, 2)

    def goalkeeper_rating(self, xi: Optional[List[SquadSlot]] = None) -> float:
        xi = xi or self.resolve_xi()
        return self.sector_rating(Sector.GOALKEEPER, xi)

    def overall_rating(self) -> float:
        """Single-number club strength from the active XI sectors."""
        xi = self.resolve_xi()
        return round(
            0.30 * self.attack_rating(xi)
            + 0.30 * self.midfield_rating(xi)
            + 0.25 * self.defence_rating(xi)
            + 0.15 * self.goalkeeper_rating(xi),
            2,
        )

    def squad_depth_score(self) -> float:
        """How well the bench backs up the XI (used by transfer AI)."""
        if self.squad_size <= 11:
            return 0.0
        ranked = sorted(self.players, key=lambda p: p.overall, reverse=True)
        bench = ranked[11:18]
        if not bench:
            return 0.0
        return round(sum(p.overall for p in bench) / len(bench), 2)

    def weakest_sector(self) -> Sector:
        ratings = {
            Sector.GOALKEEPER: self.goalkeeper_rating(),
            Sector.DEFENCE: self.defence_rating(),
            Sector.MIDFIELD: self.midfield_rating(),
            Sector.ATTACK: self.attack_rating(),
        }
        return min(ratings, key=ratings.get)  # type: ignore[arg-type]

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Club {self.name} ({self.squad_size} players, {self.overall_rating()} OVR)>"


# ---------------------------------------------------------------------------
# League
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Standing:
    """A single row of a league table."""

    club_id: int
    club_name: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def register(self, scored: int, conceded: int) -> None:
        self.played += 1
        self.goals_for += scored
        self.goals_against += conceded
        if scored > conceded:
            self.won += 1
        elif scored == conceded:
            self.drawn += 1
        else:
            self.lost += 1


@dataclass(slots=True)
class Fixture:
    """A scheduled match between two clubs on a given matchday."""

    matchday: int
    home_id: int
    away_id: int
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None

    @property
    def is_played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


@dataclass(slots=True)
class League:
    """A competition owning clubs, fixtures and a live standings table."""

    league_id: int
    name: str
    level: int = 1
    clubs: Dict[int, Club] = field(default_factory=dict)
    fixtures: List[Fixture] = field(default_factory=list)
    table: Dict[int, Standing] = field(default_factory=dict)
    current_matchday: int = 0

    def add_club(self, club: Club) -> None:
        self.clubs[club.club_id] = club
        self.table[club.club_id] = Standing(club.club_id, club.name)

    @property
    def total_matchdays(self) -> int:
        n = len(self.clubs)
        return (n - 1) * 2 if n > 1 else 0

    # ------------------------------------------------------------------ #
    # Fixture generation (double round-robin via circle method)
    # ------------------------------------------------------------------ #
    def generate_fixtures(self) -> None:
        """Build a balanced double round-robin schedule."""
        self.fixtures.clear()
        ids = list(self.clubs.keys())
        if len(ids) < 2:
            return

        bye: Optional[int] = None
        if len(ids) % 2 == 1:
            bye = -1
            ids.append(bye)

        n = len(ids)
        rounds = n - 1
        half = n // 2
        rotation = ids[:]

        single_round_fixtures: List[List[Tuple[int, int]]] = []
        for _ in range(rounds):
            day_pairs: List[Tuple[int, int]] = []
            for i in range(half):
                home = rotation[i]
                away = rotation[n - 1 - i]
                if home != bye and away != bye:
                    day_pairs.append((home, away))
            single_round_fixtures.append(day_pairs)
            # rotate keeping first fixed
            rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]

        matchday = 0
        # First half of season
        for day_pairs in single_round_fixtures:
            matchday += 1
            for home, away in day_pairs:
                self.fixtures.append(Fixture(matchday, home, away))
        # Second half (reversed venues)
        for day_pairs in single_round_fixtures:
            matchday += 1
            for home, away in day_pairs:
                self.fixtures.append(Fixture(matchday, away, home))

    def fixtures_for_matchday(self, matchday: int) -> List[Fixture]:
        return [f for f in self.fixtures if f.matchday == matchday]

    def record_result(self, fixture: Fixture, home_goals: int, away_goals: int) -> None:
        fixture.home_goals = home_goals
        fixture.away_goals = away_goals
        self.table[fixture.home_id].register(home_goals, away_goals)
        self.table[fixture.away_id].register(away_goals, home_goals)

    def standings(self) -> List[Standing]:
        """Return the table sorted by Pts, GD, GF, name (classic tie-breaks)."""
        return sorted(
            self.table.values(),
            key=lambda s: (-s.points, -s.goal_difference, -s.goals_for, s.club_name),
        )

    def is_complete(self) -> bool:
        return bool(self.fixtures) and all(f.is_played for f in self.fixtures)

    def reset_season(self) -> None:
        for standing in self.table.values():
            standing.played = standing.won = standing.drawn = standing.lost = 0
            standing.goals_for = standing.goals_against = 0
        self.current_matchday = 0
        self.generate_fixtures()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<League {self.name} ({len(self.clubs)} clubs)>"
