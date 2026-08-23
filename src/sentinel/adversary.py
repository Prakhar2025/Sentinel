"""Adversarial evasion pack (FR-12, docs/05).

Attacker simulators that attack OUR OWN detector and report what gets
through. Defense research only: the generators reuse the synthetic
entity factory and create no capability beyond what the dataset
generator already has. Evasion rings are evaluation-exclusive; they are
never used for calibration or weight fitting.

Strategies (docs/05 table):
- slow_rate: weeks between merchants, targeting the velocity feature.
  Lifetime fan-out still accumulates, so this tests whether F2 alone
  holds up.
- rotation: a fresh device and VPA for every event, sharing only a
  rotating pair of phones, targeting identity fan-out and ratio.
- benign_mimicry: amounts drawn from the clean population's log-normal
  distribution, targeting the amount-band feature.
- partitioned: sub-rings sized below cluster-density thresholds, linked
  only by a shared phone between adjacent sub-rings plus taint from a
  seeded outcome, targeting cluster geometry.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np

from .data.entities import EntityFactory
from .data.models import PaymentEvent, PaymentMethod, PriorOutcome

IST_OFFSET = timedelta(hours=5, minutes=30)
MERCHANT_POOL = [f"mcht_{i:05d}" for i in range(900, 940)]  # disjoint ids


class Strategy(StrEnum):
    SLOW_RATE = "slow_rate"
    ROTATION = "rotation"
    BENIGN_MIMICRY = "benign_mimicry"
    PARTITIONED = "partitioned"


def generate_evasion_events(
    seed: int, start: datetime, events_per_ring: int = 10, rings_per_strategy: int = 2
) -> list[tuple[PaymentEvent, Strategy]]:
    """Build all evasion rings; deterministic for a given seed."""
    rng = random.Random(seed * 7_654_321 + 13)
    np_rng = np.random.default_rng(seed * 7_654_321 + 13)
    factory = EntityFactory(random.Random(seed * 7_654_321 + 17))
    out: list[tuple[PaymentEvent, Strategy]] = []

    for strategy in Strategy:
        for ring in range(rings_per_strategy):
            out.extend(_ring(strategy, ring, rng, np_rng, factory, start, events_per_ring))
    return out


def _ring(
    strategy: Strategy,
    index: int,
    rng: random.Random,
    np_rng: np.random.Generator,
    factory: EntityFactory,
    start: datetime,
    n_events: int,
) -> list[tuple[PaymentEvent, Strategy]]:
    merchants = rng.sample(MERCHANT_POOL, k=min(6, max(3, n_events // 2)))
    events: list[tuple[PaymentEvent, Strategy]] = []

    if strategy is Strategy.SLOW_RATE:
        device = factory.device()
        vpas = [factory.vpa() for _ in range(3)]
        for i in range(n_events):
            events.append(
                (
                    _event(
                        factory,
                        rng,
                        merchant=merchants[i % len(merchants)],
                        device=device,
                        vpa=vpas[i % len(vpas)],
                        ts=start + timedelta(days=7 * i, hours=rng.randint(0, 12)),
                        amount=rng.randint(500, 2_000) * 100,
                        outcome=None,
                    ),
                    strategy,
                )
            )

    elif strategy is Strategy.ROTATION:
        phones = [factory.phone(), factory.phone()]
        for i in range(n_events):
            events.append(
                (
                    _event(
                        factory,
                        rng,
                        merchant=merchants[i % len(merchants)],
                        device=factory.device(),  # fresh device every event
                        vpa=factory.vpa(),  # fresh VPA every event
                        ts=start + timedelta(days=i, hours=rng.randint(0, 20)),
                        amount=rng.randint(500, 2_000) * 100,
                        outcome=PriorOutcome.CHARGEBACK if i == 2 else None,
                        phone=phones[i % 2],
                    ),
                    strategy,
                )
            )

    elif strategy is Strategy.BENIGN_MIMICRY:
        device = factory.device()
        vpa = factory.vpa()
        for i in range(n_events):
            rupees = float(np_rng.lognormal(mean=6.11, sigma=0.95))
            events.append(
                (
                    _event(
                        factory,
                        rng,
                        merchant=merchants[i % len(merchants)],
                        device=device,
                        vpa=vpa,
                        ts=start + timedelta(days=i // 3, hours=rng.randint(6, 22)),
                        amount=int(min(max(rupees, 20.0), 12_000.0)) * 100,
                        outcome=None,
                    ),
                    strategy,
                )
            )

    else:  # PARTITIONED: three small sub-rings bridged by shared phones + taint
        bridge_phones = [factory.phone(), factory.phone()]
        for sub in range(3):
            device = factory.device()
            vpa = factory.vpa()
            for i in range(max(3, n_events // 3)):
                phone = bridge_phones[min(sub, len(bridge_phones) - 1)]
                events.append(
                    (
                        _event(
                            factory,
                            rng,
                            merchant=merchants[(sub + i) % len(merchants)],
                            device=device,
                            vpa=vpa,
                            phone=phone,
                            ts=start + timedelta(days=sub * 4 + i, hours=rng.randint(0, 20)),
                            amount=rng.randint(500, 2_000) * 100,
                            outcome=(PriorOutcome.CONFIRMED_FRAUD if sub == 0 and i == 0 else None),
                        ),
                        strategy,
                    )
                )
    return events


def _event(
    factory: EntityFactory,
    rng: random.Random,
    *,
    merchant: str,
    device: str,
    vpa: str,
    ts: datetime,
    amount: int,
    outcome: PriorOutcome | None,
    phone: str | None = None,
) -> PaymentEvent:
    return PaymentEvent(
        event_id="",
        merchant_id=merchant,
        customer_id=factory.customer(),
        amount_paise=amount,
        upi_vpa=vpa,
        phone=phone or factory.phone(),
        device_id=device,
        email=None,
        ip=factory.ip(),
        ts=ts,
        payment_method=PaymentMethod.UPI,
        prior_outcome=outcome,
    )


def evasion_rates(
    scored: list[tuple[PaymentEvent, Strategy, int]], review_at: int, block_at: int
) -> dict[str, dict[str, float | int]]:
    """Per-strategy evasion table: how much slipped below each bar."""
    by_strategy: dict[str, list[int]] = {}
    for _event, strategy, score in scored:
        by_strategy.setdefault(strategy.value, []).append(score)
    table: dict[str, dict[str, float | int]] = {}
    for strategy_name, scores in sorted(by_strategy.items()):
        below_review = sum(1 for s in scores if s < review_at)
        below_block = sum(1 for s in scores if s < block_at)
        table[strategy_name] = {
            "events": len(scores),
            "missed_entirely": below_review,
            "missed_entirely_rate": round(below_review / len(scores), 4),
            "not_blocked": below_block,
            "not_blocked_rate": round(below_block / len(scores), 4),
        }
    return table


__all__ = ["Strategy", "evasion_rates", "generate_evasion_events"]
