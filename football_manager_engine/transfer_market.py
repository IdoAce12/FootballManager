"""
transfer_market.py
==================
A global, financially-aware transfer market where AI clubs behave like real
sporting directors: they appraise their squad, identify weaknesses, scout the
player pool for value, table bids, and negotiate contracts subject to budget.

Core subsystems
---------------
* :class:`PlayerValuation` - a transparent valuation model combining overall,
  potential, age curve, contract length and market value into a single fair
  price, with a "negotiation band" around it.
* :class:`TransferOffer` / :class:`TransferOutcome` - immutable records of a
  bid and its resolution.
* :class:`TransferMarket` - the orchestrator that:
    - runs an AI scouting + bidding window across every club,
    - evaluates incoming human-manager offers and accepts/rejects them,
    - executes accepted transfers (money + registration + contract),
    - logs a complete, auditable transfer history.

All monetary values are in EUR. The market deliberately never lets a club
spend beyond its transfer budget or breach basic wage sanity, so the global
economy stays balanced across a season.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from domain_models import Club, Player, Sector

if TYPE_CHECKING:  # avoid a runtime import cycle; only needed for typing
    from data_pipeline import GameState

__all__ = [
    "PlayerValuation",
    "OfferStatus",
    "TransferOffer",
    "TransferOutcome",
    "TransferMarket",
]


# ---------------------------------------------------------------------------
# Valuation model
# ---------------------------------------------------------------------------
class PlayerValuation:
    """Stateless fair-value estimator for a :class:`Player`.

    The model intentionally favours youth + potential (the way real markets
    do) while discounting ageing players, then anchors to the dataset's own
    ``value_eur`` so prices stay realistic for superstars.
    """

    @staticmethod
    def age_multiplier(age: int) -> float:
        if age <= 19:
            return 1.45
        if age <= 22:
            return 1.30
        if age <= 25:
            return 1.10
        if age <= 28:
            return 1.00
        if age <= 30:
            return 0.82
        if age <= 32:
            return 0.60
        if age <= 34:
            return 0.38
        return 0.22

    @staticmethod
    def potential_multiplier(player: Player) -> float:
        gap = max(0, player.potential - player.overall)
        return 1.0 + min(0.60, gap * 0.05)

    @staticmethod
    def contract_multiplier(player: Player, season_year: int) -> float:
        years_left = max(0, player.contract_until - season_year)
        if years_left <= 0:
            return 0.35           # near free agent -> cheap
        if years_left == 1:
            return 0.65
        if years_left == 2:
            return 0.90
        return 1.0

    @classmethod
    def fair_value(cls, player: Player, season_year: int = 2025) -> float:
        """Blend a ratings-derived model with the dataset's market value."""
        # Exponential model: each overall point above 60 is worth more.
        base = 25_000.0 * (1.11 ** max(0, player.overall - 50))
        model_value = (
            base
            * cls.age_multiplier(player.age)
            * cls.potential_multiplier(player)
            * cls.contract_multiplier(player, season_year)
        )
        anchor = float(player.value_eur)
        if anchor > 0:
            # Trust the dataset anchor but let the model move it +/-.
            value = 0.6 * anchor + 0.4 * model_value
        else:
            value = model_value
        return round(max(50_000.0, value), 2)

    @classmethod
    def negotiation_band(
        cls, player: Player, season_year: int = 2025
    ) -> Tuple[float, float, float]:
        """Return (min_acceptable, fair, asking) prices for negotiation."""
        fair = cls.fair_value(player, season_year)
        return round(fair * 0.85, 2), fair, round(fair * 1.20, 2)


# ---------------------------------------------------------------------------
# Offers & outcomes
# ---------------------------------------------------------------------------
class OfferStatus(Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    COMPLETED = "Completed"
    WITHDRAWN = "Withdrawn"


@dataclass(slots=True)
class TransferOffer:
    """A bid from a buying club for a player owned by a selling club."""

    buyer_id: int
    seller_id: Optional[int]
    player_id: int
    fee: float
    offered_wage_weekly: float
    contract_years: int = 4
    status: OfferStatus = OfferStatus.PENDING

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<Offer player={self.player_id} fee={self.fee:,.0f} "
                f"status={self.status.value}>")


@dataclass(slots=True)
class TransferOutcome:
    """Auditable record appended to the market history."""

    player_name: str
    from_club: str
    to_club: str
    fee: float
    wage_weekly: float
    accepted: bool
    reason: str

    def render(self) -> str:
        verb = "JOINS" if self.accepted else "REJECTED by"
        return (f"{self.player_name}: {self.from_club} -> {self.to_club} "
                f"| EUR {self.fee:,.0f} | {verb} ({self.reason})")


# ---------------------------------------------------------------------------
# The market
# ---------------------------------------------------------------------------
class TransferMarket:
    """Global market orchestrator over a :class:`GameState`."""

    def __init__(self, state: "GameState", season_year: int = 2025,
                 seed: Optional[int] = None) -> None:
        self.state = state
        self.season_year = season_year
        self._rng = random.Random(seed)
        self.history: List[TransferOutcome] = []
        # Pre-built, sorted index of players by primary sector. Built once so
        # the AI scouting loop never has to scan all 18k players per call.
        self._sector_index: Dict[Sector, List[Player]] = self._build_sector_index()

    def _build_sector_index(self) -> Dict[Sector, List[Player]]:
        index: Dict[Sector, List[Player]] = {s: [] for s in Sector}
        for player in self.state.players.values():
            index[player.primary_sector].append(player)
        for sector in index:
            index[sector].sort(key=lambda p: p.overall, reverse=True)
        return index

    # ------------------------------------------------------------------ #
    # Valuation passthroughs
    # ------------------------------------------------------------------ #
    def value_of(self, player: Player) -> float:
        return PlayerValuation.fair_value(player, self.season_year)

    def band_for(self, player: Player) -> Tuple[float, float, float]:
        return PlayerValuation.negotiation_band(player, self.season_year)

    # ------------------------------------------------------------------ #
    # Human-manager facing: submit & evaluate an offer
    # ------------------------------------------------------------------ #
    def submit_offer(self, offer: TransferOffer) -> TransferOutcome:
        """Evaluate an offer (from any club) for a player and resolve it."""
        player = self.state.players.get(offer.player_id)
        if player is None:
            return self._record(TransferOutcome(
                "?", "?", "?", offer.fee, offer.offered_wage_weekly, False,
                "player not found"))

        buyer = self.state.clubs.get(offer.buyer_id)
        if buyer is None:
            return self._record(TransferOutcome(
                player.short_name, "?", "?", offer.fee, offer.offered_wage_weekly,
                False, "buyer not found"))

        seller = self.state.clubs.get(player.club_id) if player.club_id else None
        seller_name = seller.name if seller else "Free Agent"

        # 1. Buyer affordability checks.
        if offer.fee > buyer.transfer_budget + 1.0:
            offer.status = OfferStatus.REJECTED
            return self._record(TransferOutcome(
                player.short_name, seller_name, buyer.name, offer.fee,
                offer.offered_wage_weekly, False, "buyer cannot afford the fee"))

        projected_bill = buyer.weekly_wage_bill + offer.offered_wage_weekly
        if projected_bill > buyer.wage_budget_weekly * 1.05:
            offer.status = OfferStatus.REJECTED
            return self._record(TransferOutcome(
                player.short_name, seller_name, buyer.name, offer.fee,
                offer.offered_wage_weekly, False, "wage demand exceeds buyer budget"))

        # 2. Selling club's willingness (valuation + squad need).
        if seller is not None:
            min_price, fair, _ = self.band_for(player)
            accept, reason = self._seller_decision(seller, player, offer.fee,
                                                   min_price, fair)
            if not accept:
                offer.status = OfferStatus.REJECTED
                return self._record(TransferOutcome(
                    player.short_name, seller_name, buyer.name, offer.fee,
                    offer.offered_wage_weekly, False, reason))

        # 3. Player's willingness (wages + move sense).
        if offer.offered_wage_weekly < player.wage_eur * 0.9:
            offer.status = OfferStatus.REJECTED
            return self._record(TransferOutcome(
                player.short_name, seller_name, buyer.name, offer.fee,
                offer.offered_wage_weekly, False, "player rejects the wage terms"))

        # 4. Execute.
        self._execute_transfer(buyer, seller, player, offer)
        offer.status = OfferStatus.COMPLETED
        return self._record(TransferOutcome(
            player.short_name, seller_name, buyer.name, offer.fee,
            offer.offered_wage_weekly, True, "deal completed"))

    def _seller_decision(
        self, seller: Club, player: Player, fee: float,
        min_price: float, fair: float,
    ) -> Tuple[bool, str]:
        """Whether the selling club agrees to let the player go for ``fee``."""
        # Star players that anchor a weak sector are harder to prise away.
        is_key = player.overall >= seller.overall_rating() + 2
        threshold = min_price * (1.15 if is_key else 1.0)
        if player.primary_sector is seller.weakest_sector():
            threshold *= 1.10  # reluctant to sell from their weakest area

        if fee >= threshold:
            return True, "fee meets valuation"
        if fee >= fair * 1.4:
            return True, "fee too good to refuse"
        return False, f"fee below valuation (wants ~EUR {threshold:,.0f})"

    def _execute_transfer(
        self, buyer: Club, seller: Optional[Club], player: Player,
        offer: TransferOffer,
    ) -> None:
        if seller is not None:
            seller.remove_player(player)
            seller.transfer_budget += offer.fee  # selling club banks the fee
        else:
            try:
                self.state.free_agents.remove(player)
            except ValueError:
                pass

        buyer.transfer_budget -= offer.fee
        player.wage_eur = int(offer.offered_wage_weekly)
        player.contract_until = self.season_year + offer.contract_years
        player.value_eur = int(max(player.value_eur, offer.fee))
        player.morale = min(100.0, player.morale + 6.0)  # excited by the move
        buyer.add_player(player)

    # ------------------------------------------------------------------ #
    # AI transfer window: every club scouts & bids autonomously
    # ------------------------------------------------------------------ #
    def run_ai_window(self, max_deals_per_club: int = 2,
                      activity: float = 0.6) -> List[TransferOutcome]:
        """Simulate one AI transfer window across all clubs.

        Each club, in randomised order, may target its weakest sector and bid
        for affordable upgrades from the global pool.
        """
        outcomes: List[TransferOutcome] = []
        clubs = list(self.state.clubs.values())
        self._rng.shuffle(clubs)
        # Players may only move once per window to avoid unrealistic churn.
        locked: set[int] = set()

        for buyer in clubs:
            if self._rng.random() > activity:
                continue
            deals = 0
            for _ in range(max_deals_per_club):
                target = self._scout_target(buyer, locked)
                if target is None:
                    break
                offer = self._build_ai_offer(buyer, target)
                if offer is None:
                    break
                outcome = self.submit_offer(offer)
                outcomes.append(outcome)
                if outcome.accepted:
                    deals += 1
                    locked.add(target.player_id)
                if deals >= max_deals_per_club:
                    break
        self.history.extend(outcomes)
        return outcomes

    def _scout_target(self, buyer: Club,
                      locked: Optional[set[int]] = None) -> Optional[Player]:
        """Find the best affordable upgrade for the buyer's weakest sector."""
        locked = locked or set()
        weak_sector = buyer.weakest_sector()
        current_level = buyer.sector_rating(weak_sector)
        budget = buyer.transfer_budget
        wage_room = buyer.wage_budget_weekly - buyer.weekly_wage_bill

        best: Optional[Player] = None
        best_score = 0.0
        # Sample the pool for performance: scan top clubs' fringe players +
        # a random sample so the AI does not iterate all 18k every call.
        candidates = self._candidate_pool(weak_sector)
        for player in candidates:
            if player.club_id == buyer.club_id or player.player_id in locked:
                continue
            if player.primary_sector is not weak_sector:
                continue
            fee = self.value_of(player)
            if fee > budget or player.wage_eur > wage_room * 1.05:
                continue
            upgrade = player.role_rating(weak_sector) - current_level
            if upgrade <= 1.0:
                continue
            # Prefer young, high-upgrade, affordable targets.
            score = upgrade * (1.0 + (30 - min(player.age, 30)) * 0.03)
            if score > best_score:
                best_score = score
                best = player
        return best

    def _candidate_pool(self, sector: Sector) -> List[Player]:
        """Build a bounded candidate list for scouting (performance guard)."""
        pool = self._sector_index.get(sector, [])
        # Take a strong-but-bounded slice + random sample of the mid tier.
        top = pool[:120]
        if len(pool) > 160:
            mid = pool[120:600]
            mid_sample = self._rng.sample(mid, k=min(40, len(mid)))
        else:
            mid_sample = []
        return top + mid_sample

    def _build_ai_offer(self, buyer: Club, target: Player) -> Optional[TransferOffer]:
        min_price, fair, asking = self.band_for(target)
        # AI bids near fair value, slightly randomised.
        fee = round(fair * self._rng.uniform(0.95, 1.18), 2)
        if fee > buyer.transfer_budget:
            fee = buyer.transfer_budget
        if fee < min_price * 0.9:
            return None
        offered_wage = round(max(target.wage_eur * 1.05,
                                 target.wage_eur + 1.0) * self._rng.uniform(1.0, 1.15), 2)
        return TransferOffer(
            buyer_id=buyer.club_id,
            seller_id=target.club_id,
            player_id=target.player_id,
            fee=fee,
            offered_wage_weekly=offered_wage,
            contract_years=self._rng.randint(3, 5),
        )

    # ------------------------------------------------------------------ #
    # Scouting report (human-manager helper)
    # ------------------------------------------------------------------ #
    def scout_report(self, club: Club, limit: int = 10) -> List[Tuple[Player, float, float]]:
        """Return affordable upgrade targets for a (human) club's weak sector.

        Each tuple is (player, fair_value, rating_upgrade).
        """
        weak_sector = club.weakest_sector()
        current = club.sector_rating(weak_sector)
        budget = club.transfer_budget
        results: List[Tuple[Player, float, float]] = []
        for player in self._candidate_pool(weak_sector):
            if player.club_id == club.club_id:
                continue
            if player.primary_sector is not weak_sector:
                continue
            fee = self.value_of(player)
            if fee > budget:
                continue
            upgrade = round(player.role_rating(weak_sector) - current, 2)
            if upgrade <= 0:
                continue
            results.append((player, fee, upgrade))
        results.sort(key=lambda t: t[2], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------ #
    # Bookkeeping
    # ------------------------------------------------------------------ #
    def _record(self, outcome: TransferOutcome) -> TransferOutcome:
        return outcome

    def completed_deals(self) -> List[TransferOutcome]:
        return [o for o in self.history if o.accepted]


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
    market = TransferMarket(gs, season_year=2025, seed=7)
    print("\nRunning an AI transfer window...")
    deals = market.run_ai_window(max_deals_per_club=1, activity=0.4)
    done = [d for d in deals if d.accepted]
    print(f"AI completed {len(done)} deals out of {len(deals)} bids. Samples:")
    for outcome in done[:12]:
        print("  " + outcome.render())
