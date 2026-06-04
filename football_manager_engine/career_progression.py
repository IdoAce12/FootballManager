"""
career_progression.py
=====================
League promotion mapping, career records, and incoming mega-club bids.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from data_pipeline import GameState
from domain_models import Club, League, Player, Standing

# Second division league_id -> first division league_id (dataset FC26)
PROMOTION_LEAGUE_MAP: Dict[int, int] = {
    14: 13,   # Championship -> Premier League
    17: 16,   # Ligue 2 -> Ligue 1
    54: 53,   # La Liga 2 -> La Liga
    32: 31,   # Serie B -> Serie A
    20: 19,   # 2. Bundesliga -> Bundesliga
}

# Matchday cash rewards by league tier (win, draw)
MATCHDAY_REWARDS_BY_LEVEL: Dict[int, Tuple[float, float]] = {
    1: (5_000_000.0, 2_000_000.0),
    2: (3_000_000.0, 1_000_000.0),
    3: (1_500_000.0, 500_000.0),
}

MEGA_CLUBS: Tuple[str, ...] = (
    "Real Madrid",
    "Paris Saint-Germain",
    "Manchester City",
    "FC Barcelona",
    "Bayern Munich",
    "Liverpool",
    "Juventus",
    "Chelsea",
)


@dataclass(slots=True)
class CareerSeasonRecord:
    season_year: int
    club_name: str
    league_name: str
    final_position: int
    status: str


@dataclass(slots=True)
class IncomingTransferBid:
    player_id: int
    player_name: str
    player_overall: int
    bidding_club: str
    fee: float
    fee_label: str
    market_value: int
    market_value_label: str


def resolve_promotion_league(league: League, state: GameState) -> Optional[League]:
    """Map a tier-2 league to its tier-1 counterpart when defined."""
    target_id = PROMOTION_LEAGUE_MAP.get(league.league_id)
    if target_id is not None:
        target = state.leagues.get(target_id)
        if target is not None and len(target.clubs) >= 2:
            return target

    name_l2 = league.name.lower()
    for lg in state.leagues.values():
        if lg.level != 1 or len(lg.clubs) < 4:
            continue
        n1 = lg.name.lower()
        if "2" in name_l2 and name_l2.replace("2", "").strip() in n1:
            return lg
        if "championship" in name_l2 and "premier" in n1:
            return lg
        if "bundesliga" in name_l2 and "2." in name_l2 and "bundesliga" in n1 and "2" not in n1[:3]:
            return lg
    return None


def move_club_to_league(club: Club, old_league: League, new_league: League) -> None:
    """Re-bind a club to a higher (or different) competition."""
    if club.club_id in old_league.clubs:
        del old_league.clubs[club.club_id]
    old_league.table.pop(club.club_id, None)

    club.league_id = new_league.league_id
    new_league.clubs[club.club_id] = club
    if club.club_id not in new_league.table:
        new_league.table[club.club_id] = Standing(club.club_id, club.name)


def season_status_label(position: int, league_level: int, promoted: bool) -> str:
    if promoted:
        return "Promoted"
    if position == 1:
        return "Champions"
    if position <= 3 and league_level == 1:
        return "Top Three"
    return "Stayed"


def build_manager_bio(manager_name: str, history: List[CareerSeasonRecord]) -> str:
    if not history:
        return (
            f"{manager_name} is a rising gaffer ready to etch their name into football history. "
            "Every season is a blank page waiting for silverware."
        )
    seasons = len(history)
    championships = sum(1 for r in history if r.status == "Champions")
    promotions = sum(1 for r in history if r.status == "Promoted")
    latest = history[-1]
    parts = [
        f"{manager_name} has managed {seasons} professional season{'s' if seasons != 1 else ''}.",
    ]
    if championships:
        parts.append(f"Lifting the title {championships} time{'s' if championships != 1 else ''}.")
    if promotions:
        parts.append(
            f"Famous for ruthless promotion pushes ({promotions} ascent{'s' if promotions != 1 else ''})."
        )
    parts.append(
        f"Most recently: {latest.final_position}{_ordinal_suffix(latest.final_position)} with "
        f"{latest.club_name} ({latest.status})."
    )
    return " ".join(parts)


def _ordinal_suffix(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def maybe_generate_incoming_bid(
    club: Club,
    rng: random.Random,
    value_fn,
    format_money_fn,
    chance: float = 0.15,
) -> Optional[IncomingTransferBid]:
    if rng.random() > chance:
        return None
    if len(club.players) < 11:
        return None

    ranked = sorted(club.players, key=lambda p: p.overall, reverse=True)
    pool = [p for p in ranked[:10] if p.overall >= 72]
    if not pool:
        pool = ranked[:5]
    player: Player = rng.choice(pool)

    market_value = int(value_fn(player))
    multiplier = rng.uniform(0.90, 1.20)
    fee = round(market_value * multiplier, 2)
    return IncomingTransferBid(
        player_id=player.player_id,
        player_name=player.short_name,
        player_overall=player.overall,
        bidding_club=rng.choice(MEGA_CLUBS),
        fee=fee,
        fee_label=format_money_fn(fee),
        market_value=market_value,
        market_value_label=format_money_fn(market_value),
    )
