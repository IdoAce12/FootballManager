# FC26 Football Manager — Enterprise Game Engine

A production-grade, modular **football manager simulation engine** built from
scratch around the real-world **FC26 dataset (18,000+ players)**. It bootstraps
the entire global football world in memory, then lets you manage a club through
concurrent league seasons, a probabilistic match engine, an active AI transfer
economy and an age-curve player development system.

Built on the **Python standard library only** — no third-party dependencies.

---

## Architecture

The codebase is split into clean, single-responsibility modules with a strict
one-directional dependency flow:

```
                    domain_models.py        (pure model layer — no deps)
                          ▲
        ┌─────────────────┼──────────────────┐
        │                 │                  │
data_pipeline.py   match_simulation_   transfer_market.py
(CSV → GameState)      engine.py        (AI economy)
        │                 │                  │
        └────────► app_controller.py ◄───────┘
                  (season loop + dashboard)
                          ▲
                     run_game.py            (entry point)
```

| Module | Responsibility |
| --- | --- |
| `domain_models.py` | `Player`, `Club`, `League`, formations, tactical sliders, age-curve development/XP, fitness/morale/form, live condition modelling, fixtures & standings. |
| `data_pipeline.py` | High-performance single-pass CSV parser. Builds the full `GameState` (players → clubs → leagues), derives club finances, generates fixtures. |
| `match_simulation_engine.py` | Minute-by-minute probabilistic simulator driven by sector match-ups (midfield → possession → attack vs defence + GK → goal). Live ratings, stamina ticks, cards, injuries, full commentary & stats. |
| `transfer_market.py` | Transparent valuation model + AI clubs that scout weaknesses, bid, negotiate and complete transfers within budget. |
| `app_controller.py` | Headless season state-machine (concurrent matchdays, recovery, development, season rollover) + interactive `GameDashboard`. |
| `run_game.py` | CLI entry point: interactive mode or `--demo` end-to-end run. |

---

## Quick start

```bash
# from inside the football_manager_engine/ directory

# 1) Interactive manager mode (pick a league + club, then manage)
python run_game.py

# 2) Non-interactive end-to-end demo (great for a smoke test)
python run_game.py --demo

# 3) Point at a dataset explicitly
python run_game.py "C:/path/to/FC26_20250921.csv"
```

By default the engine looks for `FC26_20250921.csv` in the parent directory.

Each module is also independently runnable for focused testing:

```bash
python data_pipeline.py            # parse + print world summary
python match_simulation_engine.py  # simulate one match with commentary
python transfer_market.py          # run one AI transfer window
```

---

## Key design decisions

### Sector match-up match engine
Every minute resolves a causal chain rather than a single dice roll:

1. **Possession** — Home Midfield vs Away Midfield (blended with *tempo* &
   *pressing* sliders and red-card numerical disadvantage) decides who attacks.
2. **Chance creation** — the aggressor's *Attack Rating* vs the opponent's
   *Defence Rating*, scaled by *mentality*, decides whether a chance is carved.
3. **Conversion** — a per-shot **xG** is computed from the shooter's live
   performance vs the defence, then resolved against the **Goalkeeper OVR** to
   pick goal / save / off-target / blocked.

Outputs include live **player match ratings (1.0–10.0)**, **stamina drain**,
**yellow/red cards**, **injuries** and a full human-readable commentary log.

### Age-curve development
`Player.develop()` converts in-match **XP** into overall changes gated by the
classic age curve: wonderkids (≤21 with a potential gap) surge, peak players
hold, and veterans (30+) decline at an accelerating rate.

### Concurrent matchdays
`AppController.play_matchday()` dispatches **every fixture in a round to a
thread pool** (each with its own seeded engine), so the whole matchday resolves
together and the standings update as one atomic round. Matches in a round never
share a club, so the per-`Player`/`Club` mutations are disjoint and safe.

### Performance
The full ~18,400-player dataset parses in **well under a second**, and an entire
30-club / 58-matchday season (870 matches) simulates concurrently in a few tens
of seconds — all in pure Python.

---

## Tuning knobs

Most match feel is controlled by constants at the top of `MatchEngine`
(`BASE_MINUTE_CHANCE`, `HOME_ADVANTAGE`, `INJURY_BASE_PROB`, `FOUL_BASE_PROB`)
and by `TacticalSetup` slider→modifier formulas in `domain_models.py`. The
valuation/aggression of the AI economy lives in `PlayerValuation` and
`TransferMarket.run_ai_window(...)`.

All randomness is seedable for fully reproducible runs.
