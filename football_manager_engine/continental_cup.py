"""
continental_cup.py
====================
European Champions Cup — continental tournament layered on domestic leagues.

Top four finishers from each tier-1 league qualify at season end. Fixtures are
scheduled on mid-week anchors that align with selected domestic matchdays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from data_pipeline import GameState
from domain_models import Club, League, Standing

CONTINENTAL_CUP_NAME = "European Champions Cup"
QUALIFIERS_PER_LEAGUE = 4
MIN_LEAGUE_CLUBS = 4
MAX_TOURNAMENT_TEAMS = 16

# Significantly higher than domestic league matchday rewards (tier-1 win ≈ €5M).
CONTINENTAL_WIN_REWARD = 18_000_000.0
CONTINENTAL_DRAW_REWARD = 7_000_000.0

# Continental rounds fire when the domestic league reaches these matchdays.
CONTINENTAL_LEAGUE_ANCHORS: Tuple[int, ...] = (3, 7, 11, 15, 19, 23, 27)

GROUP_ROUND_PAIRINGS: Tuple[Tuple[Tuple[int, int], Tuple[int, int]], ...] = (
    ((0, 1), (2, 3)),
    ((0, 2), (1, 3)),
    ((0, 3), (1, 2)),
)


@dataclass(slots=True)
class ContinentalFixture:
    """A single Champions Cup fixture."""

    matchday: int
    home_id: int
    away_id: int
    stage: str
    group_name: Optional[str] = None
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None

    @property
    def is_played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


@dataclass
class ContinentalCup:
    """In-memory continental competition for one season."""

    season_year: int
    qualified_ids: List[int]
    fixtures: List[ContinentalFixture] = field(default_factory=list)
    group_tables: Dict[str, Dict[int, Standing]] = field(default_factory=dict)
    current_matchday: int = 0
    phase: str = "group"
    champion_club_id: Optional[int] = None
    knockout_seeds: List[int] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.qualified_ids) and self.phase != "complete"

    @property
    def total_matchdays(self) -> int:
        if not self.fixtures:
            return 0
        return max(fixture.matchday for fixture in self.fixtures)

    def fixtures_for_matchday(self, matchday: int) -> List[ContinentalFixture]:
        return [
            fixture
            for fixture in self.fixtures
            if fixture.matchday == matchday and not fixture.is_played
        ]

    def record_result(self, fixture: ContinentalFixture, home_goals: int, away_goals: int) -> None:
        fixture.home_goals = home_goals
        fixture.away_goals = away_goals
        if fixture.stage == "group" and fixture.group_name:
            table = self.group_tables[fixture.group_name]
            table[fixture.home_id].register(home_goals, away_goals)
            table[fixture.away_id].register(away_goals, home_goals)

    def group_standings(self, group_name: str) -> List[Standing]:
        table = self.group_tables.get(group_name, {})
        return sorted(
            table.values(),
            key=lambda row: (-row.points, -row.goal_difference, -row.goals_for, row.club_name),
        )

    def all_group_standings(self) -> Dict[str, List[Standing]]:
        return {name: self.group_standings(name) for name in sorted(self.group_tables)}

    def advance_knockout(self, clubs: Dict[int, Club]) -> None:
        """Seed the knockout bracket from group winners and runners-up."""
        if self.phase != "group":
            return

        seeds: List[int] = []
        for group_name in sorted(self.group_tables):
            ordered = self.group_standings(group_name)
            if len(ordered) >= 2:
                seeds.append(ordered[0].club_id)
                seeds.append(ordered[1].club_id)
            elif ordered:
                seeds.append(ordered[0].club_id)
        if len(seeds) < 2:
            self.phase = "complete"
            if seeds:
                self.champion_club_id = seeds[0]
            return

        seeds.sort(key=lambda club_id: clubs[club_id].overall_rating(), reverse=True)
        bracket = seeds[:8] if len(seeds) >= 8 else seeds
        self.knockout_seeds = bracket
        self.phase = "knockout"
        self._schedule_knockout_round(bracket, matchday=4, stage="quarter_final")

    def _schedule_knockout_round(
        self,
        seeds: List[int],
        *,
        matchday: int,
        stage: str,
    ) -> None:
        """Append unplayed knockout fixtures for the supplied seeds."""
        existing = {
            (fixture.home_id, fixture.away_id, fixture.matchday)
            for fixture in self.fixtures
            if fixture.stage != "group"
        }
        for index in range(0, len(seeds) - 1, 2):
            home_id, away_id = seeds[index], seeds[index + 1]
            key = (home_id, away_id, matchday)
            if key in existing:
                continue
            self.fixtures.append(
                ContinentalFixture(
                    matchday=matchday,
                    home_id=home_id,
                    away_id=away_id,
                    stage=stage,
                )
            )

    def resolve_knockout_round(self, matchday: int, clubs: Dict[int, Club]) -> None:
        """Promote winners from a completed knockout matchday."""
        if self.phase != "knockout":
            return

        round_fixtures = [
            fixture
            for fixture in self.fixtures
            if fixture.matchday == matchday and fixture.stage != "group" and fixture.is_played
        ]
        if not round_fixtures:
            return

        winners: List[int] = []
        for fixture in round_fixtures:
            if fixture.home_goals is None or fixture.away_goals is None:
                continue
            if fixture.home_goals >= fixture.away_goals:
                winners.append(fixture.home_id)
            else:
                winners.append(fixture.away_id)

        if not winners:
            return

        if len(winners) == 1:
            self.champion_club_id = winners[0]
            self.phase = "complete"
            return

        next_md = matchday + 1
        if next_md > len(CONTINENTAL_LEAGUE_ANCHORS):
            self.champion_club_id = winners[0]
            self.phase = "complete"
            return

        stage = "semi_final" if len(winners) == 4 else "final"
        self.knockout_seeds = winners
        self._schedule_knockout_round(winners, matchday=next_md, stage=stage)


def continental_round_for_league_matchday(league_matchday: int) -> Optional[int]:
    """Map a domestic matchday to a continental round number, if scheduled."""
    if league_matchday in CONTINENTAL_LEAGUE_ANCHORS:
        return CONTINENTAL_LEAGUE_ANCHORS.index(league_matchday) + 1
    return None


def qualify_clubs_from_leagues(
    state: GameState,
    standings_snapshot: Optional[Dict[int, List[Standing]]] = None,
) -> List[int]:
    """Collect top-four qualifiers from every tier-1 league large enough to run."""
    qualified: List[int] = []
    leagues = sorted(
        (league for league in state.leagues.values() if league.level == 1),
        key=lambda league: (league.name, league.league_id),
    )
    for league in leagues:
        if len(league.clubs) < MIN_LEAGUE_CLUBS:
            continue
        if standings_snapshot and league.league_id in standings_snapshot:
            rows = standings_snapshot[league.league_id][:QUALIFIERS_PER_LEAGUE]
            qualified.extend(row.club_id for row in rows)
        else:
            clubs = sorted(
                league.clubs.values(),
                key=lambda club: club.overall_rating(),
                reverse=True,
            )
            qualified.extend(club.club_id for club in clubs[:QUALIFIERS_PER_LEAGUE])
    return list(dict.fromkeys(qualified))


def snapshot_league_standings(state: GameState) -> Dict[int, List[Standing]]:
    """Capture final tables before season rollover."""
    snapshot: Dict[int, List[Standing]] = {}
    for league in state.leagues.values():
        if league.level == 1 and len(league.clubs) >= MIN_LEAGUE_CLUBS:
            snapshot[league.league_id] = league.standings()
    return snapshot


def build_continental_cup(
    qualified_ids: List[int],
    clubs: Dict[int, Club],
    season_year: int,
) -> Optional[ContinentalCup]:
    """Construct group-stage fixtures for the new continental season."""
    if not qualified_ids:
        return None

    ranked = sorted(
        qualified_ids,
        key=lambda club_id: clubs[club_id].overall_rating() if club_id in clubs else 0.0,
        reverse=True,
    )[:MAX_TOURNAMENT_TEAMS]
    if len(ranked) < 4:
        return None

    group_count = len(ranked) // 4
    teams = ranked[: group_count * 4]
    cup = ContinentalCup(season_year=season_year, qualified_ids=teams)

    group_names = [chr(ord("A") + index) for index in range(group_count)]
    for group_name, chunk_start in zip(group_names, range(0, len(teams), 4)):
        group_teams = teams[chunk_start : chunk_start + 4]
        cup.group_tables[group_name] = {
            club_id: Standing(club_id, clubs[club_id].name)
            for club_id in group_teams
            if club_id in clubs
        }
        for matchday_index, pairings in enumerate(GROUP_ROUND_PAIRINGS, start=1):
            for home_offset, away_offset in pairings:
                home_id = group_teams[home_offset]
                away_id = group_teams[away_offset]
                cup.fixtures.append(
                    ContinentalFixture(
                        matchday=matchday_index,
                        home_id=home_id,
                        away_id=away_id,
                        stage="group",
                        group_name=group_name,
                    )
                )

    return cup


def continental_cash_reward(
    club_id: int,
    results: List[object],
) -> Tuple[float, str, str]:
    """Return (amount, outcome, label) for a continental fixture."""
    for result in results:
        home_id = getattr(result, "home_club_id", None)
        away_id = getattr(result, "away_club_id", None)
        if club_id not in (home_id, away_id):
            continue
        home_goals = getattr(result, "home_goals", 0)
        away_goals = getattr(result, "away_goals", 0)
        is_home = home_id == club_id
        if (is_home and home_goals > away_goals) or (not is_home and away_goals > home_goals):
            return CONTINENTAL_WIN_REWARD, "win", "€18.0M"
        if home_goals == away_goals:
            return CONTINENTAL_DRAW_REWARD, "draw", "€7.0M"
        return 0.0, "loss", "€0"
    return 0.0, "none", "€0"
