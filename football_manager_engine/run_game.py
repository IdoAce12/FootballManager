"""
run_game.py
===========
Single entry point for the FC26 Football Manager engine.

Usage
-----
    python run_game.py                 # uses ../FC26_20250921.csv by default
    python run_game.py path/to.csv     # explicit dataset path
    python run_game.py --demo          # non-interactive end-to-end demo run

The interactive mode launches the full :class:`GameDashboard`. The ``--demo``
mode bootstraps the world, auto-selects a marquee league/club, simulates an
entire season concurrently and prints the headline outputs - handy for CI
smoke-tests and for verifying the whole operational flow without input.
"""

from __future__ import annotations

import os
import sys

from app_controller import AppController, GameDashboard, bootstrap, format_money


def _enable_utf8_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _default_csv() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "FC26_20250921.csv")


def run_demo(csv_path: str) -> None:
    """Non-interactive, end-to-end demonstration of the full game loop."""
    print("\n### FC26 MANAGER - AUTOMATED DEMO RUN ###\n")
    controller: AppController = bootstrap(csv_path, seed=2026)

    # Pick a strong, well-sized league and its best club automatically.
    leagues = controller.state.playable_leagues(min_clubs=10)
    league = max(leagues, key=lambda lg: len(lg.clubs))
    controller.select_league(league)
    club = max(league.clubs.values(), key=lambda c: c.overall_rating())
    controller.select_club(club)
    print(f"Managing {club.name} in {league.name} "
          f"({len(league.clubs)} clubs, {league.total_matchdays} matchdays).")
    print(f"Squad OVR {club.overall_rating():.1f} | Budget {format_money(club.transfer_budget)}")

    print("\n-- Running an AI transfer window across the world --")
    outcomes = controller.market.run_ai_window(max_deals_per_club=1, activity=0.25)
    done = [o for o in outcomes if o.accepted]
    print(f"AI completed {len(done)} transfers. Examples:")
    for o in done[:5]:
        print("  " + o.render())

    print("\n-- Simulating the ENTIRE season (matchdays run concurrently) --")

    def progress(md: int, results) -> None:
        if md % 6 == 0 or md == league.total_matchdays:
            leader = league.standings()[0]
            print(f"  matchday {md:>2}/{league.total_matchdays}: "
                  f"leaders {leader.club_name} ({leader.points} pts)")

    controller.simulate_remaining_season(league, on_matchday=progress)

    print("\n-- FINAL TABLE --")
    print(f"{'#':>2} {'Club':<26}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GD':>5}{'Pts':>5}")
    for rank, s in enumerate(league.standings(), start=1):
        print(f"{rank:>2} {s.club_name:<26}{s.played:>3}{s.won:>3}{s.drawn:>3}"
              f"{s.lost:>3}{s.goal_difference:>+5}{s.points:>5}")

    players = [p for c in league.clubs.values() for p in c.players]
    scorers = sorted(players, key=lambda p: (p.goals, p.assists), reverse=True)[:5]
    print("\n-- GOLDEN BOOT --")
    for p in scorers:
        owner = controller.state.clubs.get(p.club_id)
        print(f"  {p.short_name:<22} {p.goals} goals, {p.assists} assists "
              f"({owner.name if owner else '-'})")

    print("\n-- END OF SEASON DEVELOPMENT (top risers in league) --")
    reports = controller.run_end_of_season_development(scope_league_only=True)
    for r in [r for r in reports if r.delta > 0][:6]:
        print(f"  {r.name:<22} {r.old_overall} -> {r.new_overall} (+{r.delta}) [{r.note}]")

    print("\n### DEMO COMPLETE ###")


def main(argv: list[str]) -> int:
    _enable_utf8_console()
    args = [a for a in argv[1:] if a]
    demo = "--demo" in args
    paths = [a for a in args if not a.startswith("--")]
    csv_path = paths[0] if paths else _default_csv()

    if not os.path.isfile(csv_path):
        print(f"[fatal] dataset not found: {csv_path}")
        return 1

    if demo:
        run_demo(csv_path)
        return 0

    controller = bootstrap(csv_path, seed=None)
    GameDashboard(controller).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
