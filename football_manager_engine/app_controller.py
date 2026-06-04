"""
app_controller.py
=================
The master controller that ties the four subsystems together into a playable
manager experience:

    data_pipeline  ->  GameState   (the world)
    domain_models  ->  Player/Club/League
    match_engine   ->  per-match simulation
    transfer_market->  AI economy

It exposes:
    * :class:`AppController` - the headless game-state machine. It drives the
      seasonal loop, simulates **entire matchdays concurrently** (every real
      fixture in a league resolved in parallel so the table updates as one
      atomic round), handles recovery, development and season rollover.
    * :class:`GameDashboard` - a clean, structured, text-based interactive
      console so the full operational flow can be exercised by a human.

The controller is deliberately UI-agnostic: every capability is a plain method
returning data, so the same engine can later be wrapped by a web/API layer.
"""

from __future__ import annotations

import os
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from data_pipeline import GameState, load_game_state
from domain_models import (
    Club,
    DevelopmentReport,
    Fixture,
    FORMATIONS,
    League,
    Mentality,
    Player,
    Sector,
)
from career_progression import (
    CareerSeasonRecord,
    MATCHDAY_REWARDS_BY_LEVEL,
    build_manager_bio,
    maybe_generate_incoming_bid,
    move_club_to_league,
    resolve_promotion_league,
    season_status_label,
)
from match_simulation_engine import MatchEngine, MatchResult
from transfer_market import TransferMarket, TransferOffer

__all__ = ["AppController", "GameDashboard", "format_money", "PendingMatchday"]


@dataclass(slots=True)
class PendingMatchday:
    """Uncommitted matchday results awaiting user confirmation (anti-spoiler)."""

    league_id: int
    matchday: int
    pairs: List[Tuple[Fixture, MatchResult]]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def format_money(amount: float) -> str:
    """Compact, human-friendly EUR formatting (e.g. EUR 58.6M)."""
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000:
        return f"{sign}EUR {amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"{sign}EUR {amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{sign}EUR {amount / 1_000:.0f}K"
    return f"{sign}EUR {amount:,.0f}"


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class AppController:
    """Headless game engine orchestrating a full managerial season."""

    state: GameState
    season_year: int = 2025
    seed: Optional[int] = None

    managed_league: Optional[League] = None
    managed_club: Optional[Club] = None
    global_match_index: int = 0
    market: TransferMarket = field(init=False)
    _rng: random.Random = field(init=False)
    max_workers: int = 8
    pending_matchday: Optional[PendingMatchday] = None
    manager_name: Optional[str] = None
    career_history: List[CareerSeasonRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self.market = TransferMarket(self.state, self.season_year, seed=self.seed)

    # ------------------------------------------------------------------ #
    # Setup / selection
    # ------------------------------------------------------------------ #
    def select_league(self, league: League) -> None:
        self.managed_league = league
        if not league.fixtures:
            league.generate_fixtures()

    def select_club(self, club: Club) -> None:
        self.managed_club = club

    # ------------------------------------------------------------------ #
    # Concurrent matchday simulation
    # ------------------------------------------------------------------ #
    def simulate_matchday_preview(
        self, league: Optional[League] = None, commentary_club_id: Optional[int] = None
    ) -> PendingMatchday:
        """Simulate the next matchday without committing standings or squad state."""
        league = league or self.managed_league
        if league is None:
            raise RuntimeError("No league selected")

        next_md = league.current_matchday + 1
        fixtures = league.fixtures_for_matchday(next_md)
        if not fixtures:
            return PendingMatchday(league_id=league.league_id, matchday=next_md, pairs=[])

        def worker(fixture: Fixture) -> Tuple[Fixture, MatchResult]:
            engine = MatchEngine(seed=self._rng.randint(1, 2_000_000_000))
            home = self.state.clubs[fixture.home_id]
            away = self.state.clubs[fixture.away_id]
            want_commentary = commentary_club_id in (fixture.home_id, fixture.away_id)
            result = engine.simulate(
                home,
                away,
                current_match_index=self.global_match_index,
                collect_commentary=want_commentary,
                persist_state=False,
            )
            return fixture, result

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            pairs = list(executor.map(worker, fixtures))

        pending = PendingMatchday(league_id=league.league_id, matchday=next_md, pairs=pairs)
        self.pending_matchday = pending
        return pending

    def _matchday_reward_rates(self, league: Optional[League] = None) -> Tuple[float, float]:
        league = league or self.managed_league
        level = league.level if league is not None else 2
        return MATCHDAY_REWARDS_BY_LEVEL.get(level, MATCHDAY_REWARDS_BY_LEVEL[2])

    def matchday_cash_reward(
        self, club: Club, results: List[MatchResult]
    ) -> Tuple[float, str, str]:
        """Return (amount, outcome, label) for the managed club's fixture."""
        win_amt, draw_amt = self._matchday_reward_rates()
        user_match = next(
            (
                r
                for r in results
                if club.club_id in (r.home_club_id, r.away_club_id)
            ),
            None,
        )
        if user_match is None:
            return 0.0, "none", format_money(0)

        is_home = user_match.home_club_id == club.club_id
        hg, ag = user_match.home_goals, user_match.away_goals
        if (is_home and hg > ag) or (not is_home and ag > hg):
            amount = win_amt
            outcome = "win"
        elif hg == ag:
            amount = draw_amt
            outcome = "draw"
        else:
            amount = 0.0
            outcome = "loss"
        return amount, outcome, format_money(amount)

    def confirm_matchday(
        self, league: Optional[League] = None, club: Optional[Club] = None
    ) -> Tuple[List[MatchResult], Dict[str, object]]:
        """Commit a previewed matchday: table, calendar, fitness and cash rewards."""
        league = league or self.managed_league
        club = club or self.managed_club
        if league is None:
            raise RuntimeError("No league selected")
        if self.pending_matchday is None or self.pending_matchday.league_id != league.league_id:
            raise RuntimeError("No pending matchday to confirm.")

        pending = self.pending_matchday
        results: List[MatchResult] = []
        commit_engine = MatchEngine(seed=self._rng.randint(1, 2_000_000_000))

        for fixture, result in pending.pairs:
            league.record_result(fixture, result.home_goals, result.away_goals)
            home = self.state.clubs[fixture.home_id]
            away = self.state.clubs[fixture.away_id]
            commit_engine.commit_match_result(
                home, away, result, self.global_match_index
            )
            results.append(result)

        league.current_matchday = pending.matchday
        self.global_match_index += 1
        self.pending_matchday = None
        self._recover_league(league)

        reward_amount, reward_outcome, reward_label = 0.0, "none", format_money(0)
        if club is not None:
            reward_amount, reward_outcome, reward_label = self.matchday_cash_reward(
                club, results
            )
            club.transfer_budget = round(club.transfer_budget + reward_amount, 2)

        incoming_bid_dict: Optional[Dict[str, object]] = None
        if club is not None:
            bid = maybe_generate_incoming_bid(
                club, self._rng, self.market.value_of, format_money, chance=0.15
            )
            if bid is not None:
                incoming_bid_dict = {
                    "player_id": bid.player_id,
                    "player_name": bid.player_name,
                    "player_overall": bid.player_overall,
                    "bidding_club": bid.bidding_club,
                    "fee": bid.fee,
                    "fee_label": bid.fee_label,
                    "market_value": bid.market_value,
                    "market_value_label": bid.market_value_label,
                }

        reward_info: Dict[str, object] = {
            "match_reward": reward_amount,
            "match_reward_label": reward_label,
            "match_reward_outcome": reward_outcome,
            "transfer_budget": round(club.transfer_budget, 2) if club else 0.0,
            "transfer_budget_label": format_money(club.transfer_budget) if club else "€0",
            "incoming_bid": incoming_bid_dict,
        }
        return results, reward_info

    def play_matchday(
        self, league: Optional[League] = None, commentary_club_id: Optional[int] = None
    ) -> List[MatchResult]:
        """Simulate and immediately commit a matchday (CLI / auto-sim path)."""
        pending = self.simulate_matchday_preview(league, commentary_club_id)
        if not pending.pairs:
            return []
        results, _ = self.confirm_matchday(league)
        return results

    def simulate_remaining_season(
        self, league: Optional[League] = None, on_matchday=None
    ) -> None:
        """Play every remaining matchday of the league to completion."""
        league = league or self.managed_league
        if league is None:
            raise RuntimeError("No league selected")
        while league.current_matchday < league.total_matchdays:
            results = self.play_matchday(league, commentary_club_id=None)
            if on_matchday is not None:
                on_matchday(league.current_matchday, results)

    def _recover_league(self, league: League) -> None:
        for club in league.clubs.values():
            for player in club.players:
                player.recover(days=self._rng.uniform(3.0, 7.0))

    # ------------------------------------------------------------------ #
    # Development & season rollover
    # ------------------------------------------------------------------ #
    def run_end_of_season_development(
        self, scope_league_only: bool = True
    ) -> List[DevelopmentReport]:
        """Apply the age-curve development model to players."""
        if scope_league_only and self.managed_league is not None:
            players: List[Player] = [
                p for c in self.managed_league.clubs.values() for p in c.players
            ]
        else:
            players = list(self.state.players.values())

        reports = [p.develop() for p in players]
        reports.sort(key=lambda r: r.delta, reverse=True)
        return reports

    def placement_budget_bonus(self, league: League, club: Club) -> Tuple[int, float]:
        """Financial reward from final league position (1 = champions)."""
        standings = league.standings()
        position = next(
            (i for i, row in enumerate(standings, start=1) if row.club_id == club.club_id),
            len(standings),
        )
        n = max(len(standings), 1)
        tier = (n - position + 1) / n
        bonus = 500_000.0 + tier * tier * 28_000_000.0
        if position == 1:
            bonus += 8_000_000.0
        elif position <= 3:
            bonus += 3_500_000.0
        elif position <= 6:
            bonus += 1_200_000.0
        return position, round(bonus, 2)

    def is_season_complete(self, league: Optional[League] = None) -> bool:
        league = league or self.managed_league
        if league is None:
            return False
        return league.current_matchday >= league.total_matchdays

    def advance_to_next_season(
        self, league: Optional[League] = None, club: Optional[Club] = None
    ) -> dict:
        """End the campaign: age world, reset table/fixtures, inject board bonus."""
        league = league or self.managed_league
        club = club or self.managed_club
        if league is None or club is None:
            raise RuntimeError("No managed career active.")
        if self.pending_matchday is not None:
            raise RuntimeError(
                "Confirm the final matchday before advancing to the next season."
            )
        if not self.is_season_complete(league):
            raise RuntimeError(
                f"Season not finished (matchweek {league.current_matchday}/"
                f"{league.total_matchdays})."
            )

        position, bonus = self.placement_budget_bonus(league, club)
        old_year = self.season_year
        old_league_name = league.name
        old_league_level = league.level
        promoted = False
        promotion_from: Optional[str] = None
        promotion_to: Optional[str] = None

        if league.level == 2 and position <= 3:
            target = resolve_promotion_league(league, self.state)
            if target is not None:
                move_club_to_league(club, league, target)
                promotion_from = old_league_name
                promotion_to = target.name
                league = target
                self.managed_league = target
                promoted = True

        status = season_status_label(position, old_league_level, promoted)
        self.career_history.append(
            CareerSeasonRecord(
                season_year=old_year,
                club_name=club.name,
                league_name=old_league_name,
                final_position=position,
                status=status,
            )
        )

        club.transfer_budget = round(club.transfer_budget + bonus, 2)
        club.ensure_valid_lineup()

        self.start_new_season()
        league = self.managed_league or league
        if league is not None:
            league.generate_fixtures()

        win_rate, draw_rate = self._matchday_reward_rates(league)

        return {
            "previous_season_year": old_year,
            "new_season_year": self.season_year,
            "league_position": position,
            "budget_bonus": bonus,
            "budget_bonus_label": format_money(bonus),
            "new_transfer_budget": round(club.transfer_budget, 2),
            "new_transfer_budget_label": format_money(club.transfer_budget),
            "total_matchdays": league.total_matchdays if league else 0,
            "promoted": promoted,
            "promotion_from_league": promotion_from,
            "promotion_to_league": promotion_to,
            "new_league_id": league.league_id if league else None,
            "new_league_name": league.name if league else None,
            "new_league_level": league.level if league else None,
            "matchday_win_reward": win_rate,
            "matchday_draw_reward": draw_rate,
            "season_status": status,
        }

    def accept_incoming_bid(self, club: Club, player_id: int, fee: float) -> Dict[str, object]:
        """Accept a mega-club bid — credits budget and releases the player."""
        player = club._player_by_id(player_id)
        if player is None:
            player = self.state.players.get(player_id)
        if player is None or player.club_id != club.club_id:
            raise ValueError("Player is not on your roster.")

        club.remove_player(player)
        player.club_id = None
        if player not in self.state.free_agents:
            self.state.free_agents.append(player)
        club.transfer_budget = round(club.transfer_budget + fee, 2)
        club.ensure_valid_lineup()
        return {
            "player_name": player.short_name,
            "fee": fee,
            "fee_label": format_money(fee),
            "remaining_budget": round(club.transfer_budget, 2),
            "remaining_budget_label": format_money(club.transfer_budget),
            "squad_size": club.squad_size,
        }

    def career_profile(self) -> Dict[str, object]:
        """Manager bio and trophy-room chronology."""
        name = self.manager_name or "The Gaffer"
        history = list(self.career_history)
        return {
            "manager_name": name,
            "bio": build_manager_bio(name, history),
            "history": [
                {
                    "season_year": r.season_year,
                    "club_name": r.club_name,
                    "league_name": r.league_name,
                    "final_position": r.final_position,
                    "status": r.status,
                }
                for r in history
            ],
            "trophy_count": sum(
                1
                for r in history
                if r.status in ("Champions", "Promoted", "Top Three")
                and r.final_position <= 3
            ),
        }

    def start_new_season(self) -> None:
        """Roll the world forward: age players, reset tables & fixtures."""
        self.run_end_of_season_development(scope_league_only=False)
        for player in self.state.players.values():
            player.age += 1
            player.fitness = 100.0
            player.morale = 75.0
            player.form = 50.0
            player.yellow_cards = 0
            player.red_cards = 0
            player.injured_until_match = 0
            player.appearances = 0
            player.goals = 0
            player.assists = 0
            player.clean_sheets = 0
            player.rating_history.clear()
        for league in self.state.leagues.values():
            if len(league.clubs) >= 2:
                league.reset_season()
        self.season_year += 1
        self.global_match_index = 0
        self.pending_matchday = None
        self.market.season_year = self.season_year

    def sell_player(self, club: Club, player_id: int) -> Dict[str, object]:
        """Sell a squad player — anonymous club pays 85–105% of market value."""
        player = club._player_by_id(player_id)
        if player is None:
            player = self.state.players.get(player_id)
        if player is None or player.club_id != club.club_id:
            raise ValueError("Player is not registered to your club.")

        base_value = float(self.market.value_of(player))
        multiplier = self._rng.uniform(0.85, 1.05)
        fee = round(base_value * multiplier, 2)
        buyer_names = (
            "Undisclosed European Club",
            "Premier League Interest",
            "Serie A Scouting Group",
            "La Liga Representative",
            "Bundesliga Sporting Director",
        )
        buyer = self._rng.choice(buyer_names)

        club.remove_player(player)
        player.club_id = None
        player.morale = max(45.0, player.morale - 4.0)
        if player not in self.state.free_agents:
            self.state.free_agents.append(player)
        club.transfer_budget = round(club.transfer_budget + fee, 2)
        club.ensure_valid_lineup()

        return {
            "player_name": player.short_name,
            "buyer_club": buyer,
            "fee": fee,
            "fee_label": format_money(fee),
            "multiplier_pct": round(multiplier * 100, 1),
            "market_value": int(base_value),
            "market_value_label": format_money(base_value),
            "remaining_budget": round(club.transfer_budget, 2),
            "remaining_budget_label": format_money(club.transfer_budget),
            "squad_size": club.squad_size,
        }

    # ------------------------------------------------------------------ #
    # Tactics
    # ------------------------------------------------------------------ #
    def set_lineup(
        self,
        club: Club,
        starting_xi: List[int],
        formation_name: Optional[str] = None,
    ) -> None:
        if formation_name is not None:
            self.set_formation(club, formation_name)
        assignments = {idx: pid for idx, pid in enumerate(starting_xi)}
        club.set_starting_xi(assignments)

    def set_formation(self, club: Club, formation_name: str) -> bool:
        formation = FORMATIONS.get(formation_name)
        if formation is None:
            return False
        club.formation = formation
        club._xi_cache = None
        return True

    def set_tactics(
        self, club: Club, tempo: Optional[int] = None, pressing: Optional[int] = None,
        mentality: Optional[Mentality] = None,
    ) -> None:
        if tempo is not None:
            club.tactics.tempo = tempo
        if pressing is not None:
            club.tactics.pressing = pressing
        if mentality is not None:
            club.tactics.mentality = mentality
        club.tactics.clamp()

    # ------------------------------------------------------------------ #
    # Transfers (human facing)
    # ------------------------------------------------------------------ #
    def make_bid(
        self, target: Player, fee: float, weekly_wage: float, years: int = 4
    ):
        if self.managed_club is None:
            raise RuntimeError("No managed club selected")
        offer = TransferOffer(
            buyer_id=self.managed_club.club_id,
            seller_id=target.club_id,
            player_id=target.player_id,
            fee=fee,
            offered_wage_weekly=weekly_wage,
            contract_years=years,
        )
        return self.market.submit_offer(offer)


# ---------------------------------------------------------------------------
# Interactive dashboard
# ---------------------------------------------------------------------------
class GameDashboard:
    """A structured, menu-driven console over an :class:`AppController`."""

    DIVIDER = "=" * 68

    def __init__(self, controller: AppController) -> None:
        self.c = controller

    # ------------------------------------------------------------------ #
    # Entry
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self._banner()
        if self.c.managed_league is None or self.c.managed_club is None:
            self._setup_flow()
        self._main_loop()

    def _banner(self) -> None:
        print("\n" + self.DIVIDER)
        print("        FC26 FOOTBALL MANAGER  -  ENTERPRISE ENGINE")
        print(self.DIVIDER)
        print(self.c.state.summary())

    # ------------------------------------------------------------------ #
    # Setup wizard
    # ------------------------------------------------------------------ #
    def _setup_flow(self) -> None:
        leagues = self.c.state.playable_leagues()
        print("\nSelect a league to manage in:")
        for i, lg in enumerate(leagues[:30], start=1):
            print(f"  {i:>2}. {lg.name:<30} ({len(lg.clubs)} clubs, lvl {lg.level})")
        league = self._choose_from(leagues[:30], "League number: ", leagues[0])
        self.c.select_league(league)

        clubs = sorted(league.clubs.values(),
                       key=lambda c: c.overall_rating(), reverse=True)
        print(f"\nClubs in {league.name} (by strength):")
        for i, club in enumerate(clubs, start=1):
            print(f"  {i:>2}. {club.name:<32} OVR {club.overall_rating():.1f}  "
                  f"| {format_money(club.transfer_budget)} budget")
        club = self._choose_from(clubs, "Club number to manage: ", clubs[0])
        self.c.select_club(club)
        print(f"\n>>> You are now the manager of {club.name}!")

    def _choose_from(self, items: list, prompt: str, default):
        try:
            raw = input(prompt).strip()
            if not raw:
                return default
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except (ValueError, EOFError):
            pass
        print("  (invalid choice, using default)")
        return default

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    def _main_loop(self) -> None:
        actions = {
            "1": ("View league table", self._show_table),
            "2": ("View my squad & best XI", self._show_squad),
            "3": ("Play next matchday (live)", self._play_next),
            "4": ("Simulate rest of season", self._sim_season),
            "5": ("Change formation", self._change_formation),
            "6": ("Adjust tactics (tempo/press/mentality)", self._adjust_tactics),
            "7": ("Scout report (transfer targets)", self._scout),
            "8": ("Make a transfer bid", self._make_bid),
            "9": ("Run AI transfer window", self._ai_window),
            "10": ("Top scorers / season stats", self._season_stats),
            "11": ("End-of-season development report", self._dev_report),
            "12": ("Advance to a new season", self._new_season),
            "0": ("Exit", None),
        }
        while True:
            print("\n" + self.DIVIDER)
            club = self.c.managed_club
            league = self.c.managed_league
            md = league.current_matchday if league else 0
            total = league.total_matchdays if league else 0
            print(f" {club.name if club else '-'}  |  {league.name if league else '-'}  "
                  f"|  Matchday {md}/{total}  |  Season {self.c.season_year}")
            print(f" Budget: {format_money(club.transfer_budget) if club else '-'}   "
                  f"Wages/wk: {format_money(club.weekly_wage_bill) if club else '-'}")
            print(self.DIVIDER)
            for key in sorted(actions, key=lambda k: (len(k), k)):
                print(f"  [{key}] {actions[key][0]}")

            choice = self._prompt("\nChoose an option: ")
            if choice == "0":
                print("\nThanks for playing. The legend continues another day.")
                return
            action = actions.get(choice)
            if action is None or action[1] is None:
                print("  Unknown option.")
                continue
            try:
                action[1]()
            except Exception as exc:  # keep the console alive on any error
                print(f"  [error] {exc}")

    def _prompt(self, text: str) -> str:
        try:
            return input(text).strip()
        except EOFError:
            return "0"

    # ------------------------------------------------------------------ #
    # Views / actions
    # ------------------------------------------------------------------ #
    def _show_table(self) -> None:
        league = self.c.managed_league
        if league is None:
            return
        print(f"\n{league.name} - Standings")
        print(f"{'#':>2} {'Club':<28}{'P':>3}{'W':>3}{'D':>3}{'L':>3}"
              f"{'GF':>4}{'GA':>4}{'GD':>4}{'Pts':>5}")
        print("-" * 68)
        for rank, s in enumerate(league.standings(), start=1):
            marker = " *" if self.c.managed_club and s.club_id == self.c.managed_club.club_id else "  "
            print(f"{rank:>2}{marker}{s.club_name:<26}{s.played:>3}{s.won:>3}"
                  f"{s.drawn:>3}{s.lost:>3}{s.goals_for:>4}{s.goals_against:>4}"
                  f"{s.goal_difference:>+4}{s.points:>5}")

    def _show_squad(self) -> None:
        club = self.c.managed_club
        if club is None:
            return
        xi = club.select_best_xi()
        print(f"\n{club.name} - Best XI ({club.formation.name})  "
              f"Team OVR {club.overall_rating():.1f}")
        print(f"  ATT {club.attack_rating():.1f} | MID {club.midfield_rating():.1f} "
              f"| DEF {club.defence_rating():.1f} | GK {club.goalkeeper_rating():.1f}")
        print("-" * 68)
        print(f"  {'Pos':<5}{'Name':<24}{'OVR':>4}{'Age':>4}{'Fit':>5}{'Mor':>5}{'Form':>6}")
        for slot in xi:
            p = slot.player
            print(f"  {slot.position.code:<5}{p.short_name:<24}{p.overall:>4}{p.age:>4}"
                  f"{p.fitness:>5.0f}{p.morale:>5.0f}{p.form:>6.0f}")
        injured = [p for p in club.players if p.is_injured]
        if injured:
            print(f"\n  Injured: " + ", ".join(
                f"{p.short_name} (~{p.injured_until_match} md)" for p in injured[:8]))

    def _play_next(self) -> None:
        league = self.c.managed_league
        club = self.c.managed_club
        if league is None or club is None:
            return
        if league.current_matchday >= league.total_matchdays:
            print("  Season already complete. Advance to a new season.")
            return
        results = self.c.play_matchday(league, commentary_club_id=club.club_id)
        my_result = next(
            (r for r in results if club.club_id in (r.home_club_id, r.away_club_id)),
            None,
        )
        if my_result is not None:
            self._render_match(my_result)
        print("\nOther results this matchday:")
        for r in results:
            if r is my_result:
                continue
            print(f"  {r.scoreline}")

    def _render_match(self, result: MatchResult) -> None:
        print("\n" + self.DIVIDER)
        print(f"  LIVE: {result.scoreline}")
        print(self.DIVIDER)
        hs, as_ = result.home_stats, result.away_stats
        total = hs.possession_ticks + as_.possession_ticks
        print(f"  Possession {hs.possession_pct(total):.0f}% - {as_.possession_pct(total):.0f}%"
              f" | Shots {hs.shots}-{as_.shots} (on target {hs.shots_on_target}-{as_.shots_on_target})"
              f" | xG {hs.expected_goals:.2f}-{as_.expected_goals:.2f}")
        print("-" * 68)
        for ev in result.events:
            from match_simulation_engine import EventType
            if ev.event_type in (EventType.GOAL, EventType.RED_CARD,
                                  EventType.YELLOW_CARD, EventType.INJURY,
                                  EventType.SAVE, EventType.HALF_TIME,
                                  EventType.FULL_TIME, EventType.KICK_OFF):
                print("  " + ev.render())
        # Top live ratings for the managed club.
        club = self.c.managed_club
        xi = result.home_xi if result.home_club_id == club.club_id else result.away_xi
        rated = sorted(xi, key=lambda s: result.player_ratings.get(s.player.player_id, 0),
                       reverse=True)[:3]
        print("\n  Top performers:")
        for slot in rated:
            r = result.player_ratings.get(slot.player.player_id, 6.0)
            print(f"    {slot.player.short_name:<22} {r:.1f}/10")

    def _sim_season(self) -> None:
        league = self.c.managed_league
        if league is None:
            return
        def progress(md: int, results: List[MatchResult]) -> None:
            if md % 5 == 0 or md == league.total_matchdays:
                leader = league.standings()[0]
                print(f"  ...matchday {md:>2}/{league.total_matchdays} done "
                      f"| leaders: {leader.club_name} ({leader.points} pts)")
        print("\nSimulating remaining season concurrently...")
        self.c.simulate_remaining_season(league, on_matchday=progress)
        print("\nSeason complete!")
        self._show_table()

    def _change_formation(self) -> None:
        club = self.c.managed_club
        if club is None:
            return
        names = list(FORMATIONS.keys())
        print("\nAvailable formations:")
        for i, name in enumerate(names, start=1):
            print(f"  {i}. {name}")
        choice = self._prompt("Formation number: ")
        try:
            name = names[int(choice) - 1]
            self.c.set_formation(club, name)
            print(f"  Formation set to {name}.")
        except (ValueError, IndexError):
            print("  Invalid selection.")

    def _adjust_tactics(self) -> None:
        club = self.c.managed_club
        if club is None:
            return
        t = club.tactics
        print(f"\nCurrent: tempo={t.tempo} pressing={t.pressing} "
              f"mentality={t.mentality.label}")
        tempo = self._prompt("New tempo (0-100, blank=keep): ")
        pressing = self._prompt("New pressing (0-100, blank=keep): ")
        print("Mentality: 1) Very Def 2) Def 3) Balanced 4) Att 5) Very Att")
        ment = self._prompt("Mentality (blank=keep): ")
        ment_map = {
            "1": Mentality.VERY_DEFENSIVE, "2": Mentality.DEFENSIVE,
            "3": Mentality.BALANCED, "4": Mentality.ATTACKING,
            "5": Mentality.VERY_ATTACKING,
        }
        self.c.set_tactics(
            club,
            tempo=int(tempo) if tempo.isdigit() else None,
            pressing=int(pressing) if pressing.isdigit() else None,
            mentality=ment_map.get(ment),
        )
        print(f"  Updated: tempo={t.tempo} pressing={t.pressing} "
              f"mentality={t.mentality.label}")

    def _scout(self) -> None:
        club = self.c.managed_club
        if club is None:
            return
        weak = club.weakest_sector()
        print(f"\nWeakest sector: {weak.value}. Scouting affordable upgrades "
              f"(budget {format_money(club.transfer_budget)})...")
        targets = self.c.market.scout_report(club, limit=12)
        if not targets:
            print("  No affordable upgrades found in scouting range.")
            return
        print(f"  {'Name':<24}{'OVR':>4}{'Age':>4}{'Pos':>6}{'Value':>14}{'+/-':>6}")
        for player, value, upgrade in targets:
            print(f"  {player.short_name:<24}{player.overall:>4}{player.age:>4}"
                  f"{player.primary_position.code:>6}{format_money(value):>14}{upgrade:>+6.1f}")

    def _make_bid(self) -> None:
        club = self.c.managed_club
        if club is None:
            return
        name = self._prompt("Search player by name: ")
        matches = self.c.state.search_players(name, limit=10)
        if not matches:
            print("  No players found.")
            return
        for i, p in enumerate(matches, start=1):
            owner = self.c.state.clubs.get(p.club_id)
            print(f"  {i:>2}. {p.short_name:<22} {p.overall} OVR  "
                  f"{p.primary_position.code:<4} {owner.name if owner else 'Free Agent':<22} "
                  f"value {format_money(self.c.market.value_of(p))}")
        sel = self._prompt("Pick player number: ")
        try:
            target = matches[int(sel) - 1]
        except (ValueError, IndexError):
            print("  Invalid selection.")
            return
        lo, fair, asking = self.c.market.band_for(target)
        print(f"  Valuation band: {format_money(lo)} (min) / {format_money(fair)} "
              f"(fair) / {format_money(asking)} (asking)")
        fee = self._prompt(f"Your fee bid (blank={fair:.0f}): ")
        wage = self._prompt(f"Weekly wage offer (blank={target.wage_eur * 1.1:.0f}): ")
        outcome = self.c.make_bid(
            target,
            fee=float(fee) if fee else fair,
            weekly_wage=float(wage) if wage else target.wage_eur * 1.1,
        )
        print("\n  " + outcome.render())

    def _ai_window(self) -> None:
        print("\nRunning a global AI transfer window (this may take a moment)...")
        outcomes = self.c.market.run_ai_window(max_deals_per_club=1, activity=0.35)
        done = [o for o in outcomes if o.accepted]
        print(f"  AI clubs completed {len(done)} deals from {len(outcomes)} bids.")
        for outcome in done[:15]:
            print("  " + outcome.render())

    def _season_stats(self) -> None:
        league = self.c.managed_league
        if league is None:
            return
        players = [p for c in league.clubs.values() for p in c.players]
        scorers = sorted(players, key=lambda p: (p.goals, p.assists), reverse=True)[:10]
        print(f"\n{league.name} - Top scorers")
        print(f"  {'Name':<24}{'Club':<24}{'Gls':>4}{'Ast':>4}{'Avg':>6}")
        for p in scorers:
            club = self.c.state.clubs.get(p.club_id)
            print(f"  {p.short_name:<24}{(club.name if club else '-'):<24}"
                  f"{p.goals:>4}{p.assists:>4}{p.average_rating:>6.2f}")

    def _dev_report(self) -> None:
        print("\nApplying age-curve development to your league's players...")
        reports = self.c.run_end_of_season_development(scope_league_only=True)
        risers = [r for r in reports if r.delta > 0][:10]
        fallers = [r for r in reports if r.delta < 0][-10:]
        print("\n  Biggest risers:")
        for r in risers:
            print(f"    {r.name:<22} {r.old_overall} -> {r.new_overall} "
                  f"(+{r.delta}) [{r.note}]")
        print("\n  Notable declines:")
        for r in fallers:
            print(f"    {r.name:<22} {r.old_overall} -> {r.new_overall} "
                  f"({r.delta}) [{r.note}]")

    def _new_season(self) -> None:
        confirm = self._prompt("Advance to a new season? Ages +1, tables reset. (y/N): ")
        if confirm.lower() != "y":
            print("  Cancelled.")
            return
        self.c.start_new_season()
        print(f"  Welcome to the {self.c.season_year} season! Fixtures regenerated.")


# ---------------------------------------------------------------------------
# Convenience bootstrap used by run_game.py
# ---------------------------------------------------------------------------
def bootstrap(csv_path: str, seed: Optional[int] = None) -> AppController:
    state = load_game_state(csv_path, verbose=True)
    return AppController(state=state, season_year=2025, seed=seed)


if __name__ == "__main__":  # pragma: no cover
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    default_csv = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "FC26_20250921.csv",
    )
    controller = bootstrap(sys.argv[1] if len(sys.argv) > 1 else default_csv)
    GameDashboard(controller).run()
