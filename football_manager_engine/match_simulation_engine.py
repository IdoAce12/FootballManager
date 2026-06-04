"""
match_simulation_engine.py
==========================
An advanced, probabilistic, minute-by-minute football match simulator.

Design
------
The engine models a match as 90 (+ stoppage) discrete minute-ticks. Each tick
follows a causal chain rooted in *sector match-ups*:

    1. POSSESSION   - Home Midfield vs Away Midfield (blended with tempo &
                      pressing sliders) yields a possession probability for the
                      minute. The team that "wins" the minute is the aggressor.
    2. PROGRESSION  - The aggressor attempts to build an attack. The chance of
                      manufacturing a clear opportunity scales with their
                      *Attack Rating* relative to the opponent's *Defence
                      Rating* and team mentality.
    3. CONVERSION   - A generated chance becomes a shot, then is resolved
                      against the opponent's *Goalkeeper OVR* + defensive
                      pressure to decide goal / save / miss / block.

Alongside the scoreline the engine tracks, per minute:
    * live, evolving player match ratings (1.0 - 10.0),
    * fitness / stamina drain ticks (tactics-weighted),
    * disciplinary events (yellow / red cards),
    * injuries,
    * a fully detailed, human-readable event commentary log,
    * rich aggregate team statistics (possession, shots, shots on target, xG).

The simulator is fully deterministic given a seed, enabling reproducible
testing while still feeling organic.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from domain_models import (
    Club,
    Player,
    Position,
    Sector,
    SquadSlot,
)

__all__ = [
    "EventType",
    "MatchEvent",
    "TeamMatchStats",
    "MatchResult",
    "MatchEngine",
]


# ---------------------------------------------------------------------------
# Events & statistics
# ---------------------------------------------------------------------------
class EventType(Enum):
    KICK_OFF = "Kick-off"
    GOAL = "Goal"
    SHOT_ON_TARGET = "Shot on target"
    SHOT_OFF_TARGET = "Shot off target"
    SHOT_BLOCKED = "Blocked shot"
    SAVE = "Save"
    CHANCE = "Chance created"
    YELLOW_CARD = "Yellow card"
    RED_CARD = "Red card"
    INJURY = "Injury"
    SUBSTITUTION = "Substitution"
    HALF_TIME = "Half-time"
    FULL_TIME = "Full-time"
    POSSESSION_PHASE = "Possession"


@dataclass(slots=True)
class MatchEvent:
    """A single timestamped commentary entry."""

    minute: int
    event_type: EventType
    team_name: str
    description: str
    player_name: Optional[str] = None

    def render(self) -> str:
        tag = f"{self.minute:>3}'"
        icon = _EVENT_ICONS.get(self.event_type, "  ")
        return f"{tag} {icon} {self.description}"


_EVENT_ICONS: Dict[EventType, str] = {
    EventType.GOAL: "[GOAL]",
    EventType.SHOT_ON_TARGET: "[SOT]",
    EventType.SHOT_OFF_TARGET: "[OFF]",
    EventType.SHOT_BLOCKED: "[BLK]",
    EventType.SAVE: "[SAVE]",
    EventType.YELLOW_CARD: "[YC]",
    EventType.RED_CARD: "[RC]",
    EventType.INJURY: "[INJ]",
    EventType.SUBSTITUTION: "[SUB]",
    EventType.KICK_OFF: "[--]",
    EventType.HALF_TIME: "[HT]",
    EventType.FULL_TIME: "[FT]",
    EventType.CHANCE: "[!]",
    EventType.POSSESSION_PHASE: "[..]",
}


@dataclass(slots=True)
class TeamMatchStats:
    """Aggregate per-team statistics accumulated during the match."""

    club_id: int
    name: str
    goals: int = 0
    shots: int = 0
    shots_on_target: int = 0
    shots_blocked: int = 0
    possession_ticks: int = 0
    chances: int = 0
    expected_goals: float = 0.0
    yellow_cards: int = 0
    red_cards: int = 0
    injuries: int = 0

    def possession_pct(self, total_ticks: int) -> float:
        if total_ticks <= 0:
            return 50.0
        return round(100.0 * self.possession_ticks / total_ticks, 1)


@dataclass(slots=True)
class MatchResult:
    """The full outcome bundle returned by :meth:`MatchEngine.simulate`."""

    home_club_id: int
    away_club_id: int
    home_name: str
    away_name: str
    home_goals: int
    away_goals: int
    home_stats: TeamMatchStats
    away_stats: TeamMatchStats
    events: List[MatchEvent] = field(default_factory=list)
    player_ratings: Dict[int, float] = field(default_factory=dict)
    home_xi: List[SquadSlot] = field(default_factory=list)
    away_xi: List[SquadSlot] = field(default_factory=list)

    @property
    def scoreline(self) -> str:
        return f"{self.home_name} {self.home_goals} - {self.away_goals} {self.away_name}"

    @property
    def winner_id(self) -> Optional[int]:
        if self.home_goals > self.away_goals:
            return self.home_club_id
        if self.away_goals > self.home_goals:
            return self.away_club_id
        return None

    def key_events(self) -> List[MatchEvent]:
        keep = {
            EventType.GOAL,
            EventType.RED_CARD,
            EventType.YELLOW_CARD,
            EventType.INJURY,
            EventType.SUBSTITUTION,
        }
        return [e for e in self.events if e.event_type in keep]


# ---------------------------------------------------------------------------
# Internal per-side live match context
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class _SideContext:
    """Mutable per-team state held only for the duration of one simulation."""

    club: Club
    xi: List[SquadSlot]
    stats: TeamMatchStats
    is_home: bool
    live_ratings: Dict[int, float] = field(default_factory=dict)
    sent_off: List[int] = field(default_factory=list)

    def active_slots(self) -> List[SquadSlot]:
        return [s for s in self.xi if s.player.player_id not in self.sent_off]

    def players_in_sector(self, sector: Sector) -> List[SquadSlot]:
        return [s for s in self.active_slots() if s.position.sector is sector]

    def goalkeeper(self) -> Optional[Player]:
        gks = self.players_in_sector(Sector.GOALKEEPER)
        return gks[0].player if gks else None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class MatchEngine:
    """Stateless, reusable match simulator.

    A single instance can simulate any number of matches (it carries no match
    state between calls), which makes it safe to share across the concurrent
    matchday executor in the controller.
    """

    HOME_ADVANTAGE = 1.06          # multiplicative boost to home attack output
    BASE_MINUTE_CHANCE = 0.132     # baseline chance-creation prob per minute
    # One team-level roll per minute (~0.4% chance of any injury in a full match).
    INJURY_TEAM_MINUTE_PROB = 0.000022  # ~0.4% of matches see an injury
    FOUL_BASE_PROB = 0.022         # per minute, scaled by pressing
    # On-target shot → goal baseline (target 35–40% before keeper/finish modifiers).
    GOAL_ON_TARGET_BASE = 0.40
    # Dominance pools — wider band so elite sides (e.g. +10 OVR) reach ~75–80% share.
    MIN_PROB_SHARE = 0.10
    MAX_PROB_SHARE = 0.90
    DOMINANCE_GAP_SCALE = 8.0      # smaller = stronger pull for rating gaps
    DOMINANCE_MAX_BOOST = 0.42     # max additive share swing from a large gap

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)
        self._persist_state: bool = True

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @staticmethod
    def probability_share(
        rating_a: float,
        rating_b: float,
        min_share: float = MIN_PROB_SHARE,
        max_share: float = MAX_PROB_SHARE,
    ) -> float:
        """Relative win-share for team A with exponential gap scaling (0..1).

        A +10 OVR favourite (e.g. AZ vs a mid-table side) lands near 75–80%
        of attacking/possession pools instead of a flat ~53% linear split.
        """
        total = rating_a + rating_b
        if total <= 0:
            return 0.5

        linear = rating_a / total
        gap = rating_a - rating_b
        if abs(gap) < 0.01:
            return max(min_share, min(max_share, linear))

        # Exponential pull: each OVR point of gap matters more as |gap| grows.
        gap_strength = 1.0 - math.exp(-abs(gap) / MatchEngine.DOMINANCE_GAP_SCALE)
        direction = 1.0 if gap > 0 else -1.0
        gap_bonus = direction * gap_strength * (
            MatchEngine.DOMINANCE_MAX_BOOST * min(abs(gap) / 12.0, 1.0)
        )
        adjusted = linear + gap_bonus
        return max(min_share, min(max_share, adjusted))

    def simulate(
        self,
        home: Club,
        away: Club,
        current_match_index: int = 0,
        collect_commentary: bool = True,
        persist_state: bool = True,
    ) -> MatchResult:
        """Simulate a full 90'+ match between ``home`` and ``away``.

        When ``persist_state`` is False (preview/dry-run), player fitness, form and
        card state are not mutated — used for anti-spoiler matchday previews.
        """

        self._persist_state = persist_state
        home_xi = home.resolve_xi()
        away_xi = away.resolve_xi()

        if persist_state:
            for slot in home_xi + away_xi:
                slot.player.reset_match_state()

        home_ctx = _SideContext(
            club=home,
            xi=home_xi,
            stats=TeamMatchStats(home.club_id, home.name),
            is_home=True,
        )
        away_ctx = _SideContext(
            club=away,
            xi=away_xi,
            stats=TeamMatchStats(away.club_id, away.name),
            is_home=False,
        )

        # Every player starts a match on a neutral 6.0 base rating.
        for ctx in (home_ctx, away_ctx):
            for slot in ctx.xi:
                ctx.live_ratings[slot.player.player_id] = 6.0

        events: List[MatchEvent] = []
        if collect_commentary:
            events.append(
                MatchEvent(0, EventType.KICK_OFF, home.name,
                           f"Kick-off! {home.name} host {away.name}.")
            )

        total_minutes = 90 + self._rng.randint(2, 6)  # added time
        for minute in range(1, total_minutes + 1):
            self._simulate_minute(minute, home_ctx, away_ctx, events, collect_commentary,
                                  current_match_index)
            if minute == 45 and collect_commentary:
                events.append(
                    MatchEvent(
                        45, EventType.HALF_TIME, home.name,
                        f"Half-time: {home.name} {home_ctx.stats.goals} - "
                        f"{away_ctx.stats.goals} {away.name}.",
                    )
                )

        if collect_commentary:
            events.append(
                MatchEvent(
                    total_minutes, EventType.FULL_TIME, home.name,
                    f"Full-time: {home.name} {home_ctx.stats.goals} - "
                    f"{away_ctx.stats.goals} {away.name}.",
                )
            )

        self._finalise_ratings(home_ctx)
        self._finalise_ratings(away_ctx)
        if persist_state:
            self._commit_player_state(home_ctx, away_ctx, total_minutes, current_match_index)

        result = MatchResult(
            home_club_id=home.club_id,
            away_club_id=away.club_id,
            home_name=home.name,
            away_name=away.name,
            home_goals=home_ctx.stats.goals,
            away_goals=away_ctx.stats.goals,
            home_stats=home_ctx.stats,
            away_stats=away_ctx.stats,
            events=events,
            player_ratings={
                **home_ctx.live_ratings,
                **away_ctx.live_ratings,
            },
            home_xi=home_xi,
            away_xi=away_xi,
        )
        return result

    # ------------------------------------------------------------------ #
    # Minute resolution
    # ------------------------------------------------------------------ #
    def _simulate_minute(
        self,
        minute: int,
        home: _SideContext,
        away: _SideContext,
        events: List[MatchEvent],
        commentary: bool,
        match_index: int,
    ) -> None:
        # --- 1. Stamina drain for everyone on the pitch -----------------
        self._apply_stamina_tick(home)
        self._apply_stamina_tick(away)

        # --- 2. Possession battle (midfield match-up) -------------------
        home_mid = home.club.midfield_rating(home.xi) * self._numeric_advantage(home)
        away_mid = away.club.midfield_rating(away.xi) * self._numeric_advantage(away)
        home_mid *= 1.0 + (home.club.tactics.tempo - 50) / 400.0
        away_mid *= 1.0 + (away.club.tactics.tempo - 50) / 400.0
        home_share = self.probability_share(home_mid, away_mid)

        if self._rng.random() < home_share:
            aggressor, defender = home, away
            aggressor.stats.possession_ticks += 1
        else:
            aggressor, defender = away, home
            aggressor.stats.possession_ticks += 1

        # --- 3. Discipline & injuries (independent of attack) ----------
        self._maybe_foul_and_card(minute, aggressor, defender, events, commentary)
        self._maybe_injury(minute, home, events, commentary, match_index)
        self._maybe_injury(minute, away, events, commentary, match_index)

        # --- 4. Attack generation (attack vs defence match-up) ---------
        self._attempt_attack(minute, aggressor, defender, events, commentary)

    def _numeric_advantage(self, ctx: _SideContext) -> float:
        """Penalise a side that has had players sent off."""
        missing = len(ctx.sent_off)
        if missing == 0:
            return 1.0
        return max(0.55, 1.0 - missing * 0.12)

    def _apply_stamina_tick(self, ctx: _SideContext) -> None:
        drain = ctx.club.tactics.stamina_drain_modifier
        for slot in ctx.active_slots():
            slot.player.drain_stamina(drain)

    # ------------------------------------------------------------------ #
    # Attack resolution
    # ------------------------------------------------------------------ #
    def _attempt_attack(
        self,
        minute: int,
        attacker: _SideContext,
        defender: _SideContext,
        events: List[MatchEvent],
        commentary: bool,
    ) -> None:
        atk_rating = attacker.club.attack_rating(attacker.xi)
        def_rating = defender.club.defence_rating(defender.xi) * self._numeric_advantage(defender)

        if attacker.is_home:
            atk_rating *= self.HOME_ADVANTAGE

        atk_share = self.probability_share(atk_rating, def_rating)
        chance_prob = self.BASE_MINUTE_CHANCE * (0.52 + 0.72 * atk_share)
        chance_prob *= attacker.club.tactics.attack_modifier
        chance_prob = min(0.36, chance_prob)

        if self._rng.random() >= chance_prob:
            return  # no opportunity this minute

        attacker.stats.chances += 1
        shooter_slot = self._pick_shooter(attacker)
        if shooter_slot is None:
            return
        shooter = shooter_slot.player
        creator_slot = self._pick_creator(attacker, exclude=shooter.player_id)

        if commentary:
            events.append(
                MatchEvent(
                    minute, EventType.CHANCE, attacker.club.name,
                    f"{attacker.club.name} carve out a chance through {shooter.short_name}.",
                    shooter.short_name,
                )
            )

        finish_quality = shooter.in_match_performance(shooter_slot.position)
        shot_share = self.probability_share(finish_quality, def_rating * 0.92)
        xg = self._estimate_xg(finish_quality, def_rating) * (0.75 + 0.35 * shot_share)
        attacker.stats.shots += 1
        attacker.stats.expected_goals = round(attacker.stats.expected_goals + xg, 3)

        roll = self._rng.random()
        keeper = defender.goalkeeper()
        keeper_rating = keeper.role_rating(Sector.GOALKEEPER) if keeper else 45.0
        keeper_rating *= keeper.condition_multiplier() if keeper else 1.0

        on_target_prob = 0.44 + 0.30 * shot_share
        if roll > on_target_prob:
            # Off target or blocked.
            if self._rng.random() < 0.30:
                attacker.stats.shots_blocked += 1
                self._bump_rating(defender, self._pick_defender(defender), +0.10)
                if commentary:
                    events.append(MatchEvent(
                        minute, EventType.SHOT_BLOCKED, attacker.club.name,
                        f"{shooter.short_name}'s effort is blocked by a {defender.club.name} defender!",
                        shooter.short_name))
            else:
                if commentary:
                    events.append(MatchEvent(
                        minute, EventType.SHOT_OFF_TARGET, attacker.club.name,
                        f"{shooter.short_name} drags the shot wide.",
                        shooter.short_name))
                self._bump_rating(attacker, shooter_slot, -0.10)
            return

        attacker.stats.shots_on_target += 1

        finish_vs_gk = self.probability_share(finish_quality, keeper_rating)
        # Dynamic 35–40% baseline on target, scaled by finisher vs keeper.
        goal_prob = self.GOAL_ON_TARGET_BASE * (0.78 + 0.50 * finish_vs_gk)
        goal_prob += xg * 0.14
        goal_prob = min(0.82, max(0.30, goal_prob))
        if self._rng.random() < goal_prob:
            self._register_goal(
                minute, attacker, defender, shooter_slot, creator_slot, events, commentary
            )
        else:
            if keeper:
                self._bump_rating_player(defender, keeper, +0.45)
            if commentary:
                kname = keeper.short_name if keeper else "the keeper"
                events.append(MatchEvent(
                    minute, EventType.SAVE, defender.club.name,
                    f"SAVE! {kname} denies {shooter.short_name} with a strong stop.",
                    kname))
            self._bump_rating(attacker, shooter_slot, +0.05)

    def _apply_goal_stats(self, shooter: Player, assister: Optional[Player]) -> None:
        """Increment live season counters on the Player objects."""
        shooter.goals_scored += 1
        if assister is not None:
            assister.assists_given += 1

    def _register_goal(
        self,
        minute: int,
        attacker: _SideContext,
        defender: _SideContext,
        shooter_slot: SquadSlot,
        creator_slot: Optional[SquadSlot],
        events: List[MatchEvent],
        commentary: bool,
    ) -> None:
        # Weighted re-roll at conversion time for realistic scorer/assister spread.
        scorer_slot = self._pick_shooter(attacker) or shooter_slot
        assister_slot = self._pick_assister(attacker, scorer_slot.player.player_id)
        if assister_slot is None and creator_slot is not None:
            assister_slot = creator_slot

        attacker.stats.goals += 1
        shooter = scorer_slot.player
        if self._persist_state:
            self._apply_goal_stats(
                shooter,
                assister_slot.player if assister_slot is not None else None,
            )
        self._bump_rating(attacker, scorer_slot, +1.30)
        assist_txt = ""
        if assister_slot is not None:
            self._bump_rating(attacker, assister_slot, +0.70)
            assist_txt = f", assisted by {assister_slot.player.short_name}"
        # Concession dents the keeper & nearest defender slightly.
        keeper = defender.goalkeeper()
        if keeper:
            self._bump_rating_player(defender, keeper, -0.35)
        self._bump_rating(defender, self._pick_defender(defender), -0.25)

        if commentary:
            events.append(MatchEvent(
                minute, EventType.GOAL, attacker.club.name,
                f"GOAL!! {shooter.short_name} scores for {attacker.club.name}{assist_txt}! "
                f"({attacker.stats.goals}-{defender.stats.goals})",
                shooter.short_name))

    # ------------------------------------------------------------------ #
    # Discipline & injuries
    # ------------------------------------------------------------------ #
    def _maybe_foul_and_card(
        self,
        minute: int,
        aggressor: _SideContext,
        defender: _SideContext,
        events: List[MatchEvent],
        commentary: bool,
    ) -> None:
        foul_prob = self.FOUL_BASE_PROB * (0.7 + defender.club.tactics.pressing / 100.0)
        if self._rng.random() >= foul_prob:
            return
        offender_slot = self._pick_defender(defender)
        if offender_slot is None:
            return
        offender = offender_slot.player

        # Most fouls are nothing; a fraction are cards; a sliver are reds.
        severity = self._rng.random()
        if severity < 0.78:
            return  # ordinary foul, no card
        if severity < 0.985:
            if self._persist_state:
                offender.yellow_cards += 1
            defender.stats.yellow_cards += 1
            self._bump_rating_player(defender, offender, -0.15)
            if offender.yellow_cards % 2 == 0:
                # Second yellow -> red.
                self._send_off(minute, defender, offender_slot, events, commentary,
                               reason="second bookable offence")
            elif commentary:
                events.append(MatchEvent(
                    minute, EventType.YELLOW_CARD, defender.club.name,
                    f"Yellow card for {offender.short_name} ({defender.club.name}).",
                    offender.short_name))
        else:
            self._send_off(minute, defender, offender_slot, events, commentary,
                           reason="serious foul play")

    def _send_off(
        self,
        minute: int,
        ctx: _SideContext,
        slot: SquadSlot,
        events: List[MatchEvent],
        commentary: bool,
        reason: str,
    ) -> None:
        player = slot.player
        if self._persist_state:
            player.red_cards += 1
        ctx.stats.red_cards += 1
        ctx.sent_off.append(player.player_id)
        self._bump_rating_player(ctx, player, -1.0)
        if commentary:
            events.append(MatchEvent(
                minute, EventType.RED_CARD, ctx.club.name,
                f"RED CARD! {player.short_name} is sent off for {reason}. "
                f"{ctx.club.name} down to {11 - len(ctx.sent_off)} men.",
                player.short_name))

    def _maybe_injury(
        self,
        minute: int,
        ctx: _SideContext,
        events: List[MatchEvent],
        commentary: bool,
        match_index: int,
    ) -> None:
        active = ctx.active_slots()
        if not active:
            return

        # Single team-level roll per minute (~0.3–0.5% injury rate per match).
        avg_stamina = sum(s.player.stamina_current for s in active) / len(active)
        fatigue_factor = 1.0 + (100.0 - avg_stamina) / 200.0
        if self._rng.random() >= self.INJURY_TEAM_MINUTE_PROB * fatigue_factor:
            return

        slot = self._rng.choice(active)
        player = slot.player
        weeks = self._rng.randint(1, 4)
        if self._persist_state:
            player.injured_until_match = match_index + weeks
        ctx.stats.injuries += 1
        self._bump_rating_player(ctx, player, -0.20)
        if commentary:
            events.append(MatchEvent(
                minute, EventType.INJURY, ctx.club.name,
                f"{player.short_name} ({ctx.club.name}) goes down injured "
                f"and will miss ~{weeks} match(es).",
                player.short_name))

    # ------------------------------------------------------------------ #
    # Player selection helpers
    # ------------------------------------------------------------------ #
    def _pick_shooter(self, ctx: _SideContext) -> Optional[SquadSlot]:
        candidates = ctx.players_in_sector(Sector.ATTACK) or ctx.players_in_sector(Sector.MIDFIELD)
        if not candidates:
            candidates = ctx.active_slots()
        if not candidates:
            return None
        weights = [max(1.0, s.player.shooting + s.player.in_match_performance(s.position) / 2)
                   for s in candidates]
        return self._weighted_choice(candidates, weights)

    def _pick_creator(self, ctx: _SideContext, exclude: int) -> Optional[SquadSlot]:
        """Chance-build phase — prefer midfield creators."""
        return self._pick_assister(ctx, exclude, solo_goal_rate=0.30)

    def _pick_assister(
        self, ctx: _SideContext, exclude: int, solo_goal_rate: float = 0.28
    ) -> Optional[SquadSlot]:
        """Weighted assister: midfield primary, attack secondary, defence rare."""
        if self._rng.random() < solo_goal_rate:
            return None

        mids = [
            s for s in ctx.players_in_sector(Sector.MIDFIELD)
            if s.player.player_id != exclude
        ]
        attackers = [
            s for s in ctx.players_in_sector(Sector.ATTACK)
            if s.player.player_id != exclude
        ]
        defenders = [
            s for s in ctx.players_in_sector(Sector.DEFENCE)
            if s.player.player_id != exclude
        ]

        pool: List[SquadSlot] = []
        weights: List[float] = []
        for slot in mids:
            pool.append(slot)
            weights.append(max(1.0, slot.player.passing * 1.4 + slot.player.overall * 0.2))
        for slot in attackers:
            pool.append(slot)
            weights.append(max(1.0, slot.player.passing + slot.player.dribbling * 0.35))
        if self._rng.random() < 0.12 and defenders:
            slot = self._weighted_choice(
                defenders,
                [max(1.0, s.player.passing + s.player.defending * 0.25) for s in defenders],
            )
            return slot

        if not pool:
            return None
        return self._weighted_choice(pool, weights)

    def _pick_defender(self, ctx: _SideContext) -> Optional[SquadSlot]:
        candidates = ctx.players_in_sector(Sector.DEFENCE) or ctx.players_in_sector(Sector.MIDFIELD)
        if not candidates:
            candidates = [s for s in ctx.active_slots()
                          if s.position.sector is not Sector.GOALKEEPER]
        if not candidates:
            return None
        return self._rng.choice(candidates)

    def _weighted_choice(
        self, slots: List[SquadSlot], weights: List[float]
    ) -> SquadSlot:
        total = sum(weights)
        r = self._rng.random() * total
        upto = 0.0
        for slot, weight in zip(slots, weights):
            upto += weight
            if upto >= r:
                return slot
        return slots[-1]

    # ------------------------------------------------------------------ #
    # Ratings & xG
    # ------------------------------------------------------------------ #
    @staticmethod
    def _estimate_xg(finish_quality: float, def_rating: float) -> float:
        """Single-shot expected-goals estimate in [0.04, 0.62]."""
        base = finish_quality / (finish_quality + def_rating) if (finish_quality + def_rating) else 0.2
        return round(max(0.04, min(0.62, base * 0.82)), 3)

    @staticmethod
    def _bump_rating(ctx: _SideContext, slot: Optional[SquadSlot], delta: float) -> None:
        if slot is None:
            return
        MatchEngine._bump_rating_player(ctx, slot.player, delta)

    @staticmethod
    def _bump_rating_player(ctx: _SideContext, player: Player, delta: float) -> None:
        pid = player.player_id
        current = ctx.live_ratings.get(pid, 6.0)
        ctx.live_ratings[pid] = max(1.0, min(10.0, current + delta))

    def _finalise_ratings(self, ctx: _SideContext) -> None:
        """Nudge every live rating by overall team contribution & condition."""
        team_goals = ctx.stats.goals
        for slot in ctx.xi:
            pid = slot.player.player_id
            rating = ctx.live_ratings.get(pid, 6.0)
            # Small passive adjustment: clean sheet bonus for defenders/keeper.
            if slot.position.sector in (Sector.DEFENCE, Sector.GOALKEEPER):
                pass  # adjusted at commit time once we know conceded goals
            # Reward involvement on a high-scoring side marginally.
            rating += min(0.3, team_goals * 0.03)
            ctx.live_ratings[pid] = round(max(1.0, min(10.0, rating)), 2)

    def _commit_player_state(
        self,
        home: _SideContext,
        away: _SideContext,
        minutes: int,
        match_index: int,
    ) -> None:
        """Persist match consequences back onto the Player objects."""
        for ctx, opp in ((home, away), (away, home)):
            conceded = opp.stats.goals
            tactical_drain = ctx.club.tactics.stamina_drain_modifier
            for slot in ctx.xi:
                player = slot.player
                played = minutes if player.player_id not in ctx.sent_off else self._rng.randint(20, minutes)
                rating = ctx.live_ratings.get(player.player_id, 6.0)
                # Clean-sheet reward for the defensive unit.
                if conceded == 0 and slot.position.sector in (Sector.DEFENCE, Sector.GOALKEEPER):
                    rating = min(10.0, rating + 0.5)
                    player.clean_sheets += 1
                ctx.live_ratings[player.player_id] = round(rating, 2)

                player.appearances += 1
                player.register_match_rating(rating)
                player.apply_match_load(played, tactical_drain)
                player.gain_xp(played, rating, ctx.club.overall_rating())

    def commit_match_result(
        self,
        home: Club,
        away: Club,
        result: MatchResult,
        match_index: int,
        minutes: int = 92,
    ) -> None:
        """Apply post-match squad effects after the user confirms a preview."""
        bundles = (
            (result.home_xi, result.away_goals, home),
            (result.away_xi, result.home_goals, away),
        )
        for xi, conceded, club in bundles:
            tactical_drain = club.tactics.stamina_drain_modifier
            team_quality = club.overall_rating()
            for slot in xi:
                player = slot.player
                rating = result.player_ratings.get(player.player_id, 6.0)
                if conceded == 0 and slot.position.sector in (Sector.DEFENCE, Sector.GOALKEEPER):
                    rating = min(10.0, rating + 0.5)
                    player.clean_sheets += 1
                player.appearances += 1
                player.register_match_rating(rating)
                player.apply_match_load(minutes, tactical_drain)
                player.gain_xp(minutes, rating, team_quality)

        for ev in result.events:
            if ev.event_type is not EventType.GOAL or not ev.player_name:
                continue
            for xi in (result.home_xi, result.away_xi):
                for slot in xi:
                    if slot.player.short_name == ev.player_name:
                        slot.player.goals_scored += 1
                        break
            if "assisted by" in ev.description:
                marker = "assisted by "
                name = ev.description.split(marker, 1)[1].split("!", 1)[0].strip().rstrip(".")
                for xi in (result.home_xi, result.away_xi):
                    for slot in xi:
                        if slot.player.short_name == name:
                            slot.player.assists_given += 1
                            break


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import os
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    from data_pipeline import load_game_state

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "FC26_20250921.csv",
    )
    gs = load_game_state(path)
    league = gs.playable_leagues()[0]
    clubs = list(league.clubs.values())
    engine = MatchEngine(seed=42)
    result = engine.simulate(clubs[0], clubs[1])
    print("\n" + "=" * 60)
    print(result.scoreline)
    print("=" * 60)
    for ev in result.key_events():
        print(ev.render())
