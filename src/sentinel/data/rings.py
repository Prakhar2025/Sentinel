"""Fraud ring injector (attack model from docs/01 and docs/04).

Each ring reuses a small pool of devices / UPI VPAs / phones / IPs across
several merchants, with fresh customer accounts per event. Two archetypes:

- STANDARD: burst behavior. Events cluster in a 2-5 day window, hitting
  3-6 merchants; identity fan-out is high and easy to relate.
- SOPHISTICATED: low-and-slow. Events spread over ~3 weeks with low per-day
  velocity, mimicking the clean population's diurnal pattern; only taint
  and patient fan-out can catch it. At least one such ring is injected so
  recall limits are visible and honestly reportable.

Burn-and-rotate: once an event carries a fraud outcome (chargeback /
refund abuse, ~30% of ring events), the VPA used for it is abandoned and
later events rotate to the next VPA in the pool; a graph neighbor takes
over, which is the classic pattern feature F5 detects.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from .entities import NAME_PARTS, EntityFactory
from .models import PaymentEvent, PaymentMethod, PriorOutcome, RingStrategy

OUTCOME_SHARE = 0.30  # fraction of ring events carrying a fraud outcome
SOPHISTICATED_SHARE = 0.15  # fraction of rings that are low-and-slow


@dataclass(slots=True)
class RingSpec:
    """Sampled parameters for one ring."""

    ring_id: str
    strategy: RingStrategy
    n_events: int
    n_devices: int
    n_vpas: int
    n_phones: int
    n_merchants: int
    window: timedelta
    n_ips: int


@dataclass(slots=True)
class RingResult:
    """Generated events plus ring metadata for evaluation."""

    spec: RingSpec
    events: list[PaymentEvent]


def sample_specs(str_rng: random.Random, n_rings: int, total_events: int) -> list[RingSpec]:
    """Split total_events across n_rings with sizes 8-14 and archetypes."""
    sizes = _split(total_events, n_rings, low=8, high=14, rng=str_rng)
    n_sophisticated = max(1, round(n_rings * SOPHISTICATED_SHARE))
    specs: list[RingSpec] = []
    for i, size in enumerate(sizes):
        strategy = RingStrategy.SOPHISTICATED if i < n_sophisticated else RingStrategy.STANDARD
        if strategy is RingStrategy.SOPHISTICATED:
            window = timedelta(days=str_rng.randint(18, 25))
            n_devices = str_rng.randint(2, 3)
            n_merchants = str_rng.randint(3, 5)
        else:
            window = timedelta(days=str_rng.randint(2, 5))
            n_devices = str_rng.randint(1, 3)
            n_merchants = str_rng.randint(3, 6)
        specs.append(
            RingSpec(
                ring_id=f"ring_{i:03d}",
                strategy=strategy,
                n_events=size,
                n_devices=n_devices,
                n_vpas=str_rng.randint(4, 10),
                n_phones=str_rng.randint(2, 4),
                n_merchants=n_merchants,
                window=window,
                n_ips=str_rng.randint(2, 5),
            )
        )
    return specs


def _split(total: int, parts: int, low: int, high: int, rng: random.Random) -> list[int]:
    """Randomly split total into `parts` chunks within [low, high]."""
    for _ in range(200):  # bounded, never loops (budget discipline)
        sizes = [rng.randint(low, high) for _ in range(parts)]
        if sum(sizes) == total:
            return sizes
    # Deterministic fallback: adjust the last chunks to meet the total.
    sizes = [total // parts] * parts
    remainder = total - sum(sizes)
    for i in range(remainder):
        sizes[i] += 1
    return sizes


def generate_ring(
    spec: RingSpec,
    factory: EntityFactory,
    str_rng: random.Random,
    merchants: list[str],
    window_start: datetime,
) -> RingResult:
    """Generate one ring's events with reuse, rotation, and outcomes."""
    devices = [factory.device() for _ in range(spec.n_devices)]
    vpas = [factory.vpa() for _ in range(spec.n_vpas)]
    phones = [factory.phone() for _ in range(spec.n_phones)]
    ips = [factory.ip() for _ in range(spec.n_ips)]
    ring_merchants = str_rng.sample(merchants, k=spec.n_merchants)

    # One shared email base with dotted/numbered alias variants: a classic
    # ring fingerprint the evidence view can surface.
    base_name = f"{str_rng.choice(NAME_PARTS)}.{str_rng.choice(NAME_PARTS)}"
    email_variants = [
        base_name.replace(".", "") + f"{str_rng.randint(10, 99)}",
        base_name,
        base_name.split(".")[0] + f".{str_rng.randint(100, 999)}",
    ]

    # Spread over the window: bursts for standard, near-uniform for
    # sophisticated (low daily velocity that mimics organic traffic).
    offsets: list[float] = []
    for i in range(spec.n_events):
        if spec.strategy is RingStrategy.SOPHISTICATED:
            frac = (i + str_rng.random() * 0.5) / spec.n_events
        else:
            frac = _burst_fraction(str_rng)
        offsets.append(min(frac, 0.98) * spec.window.total_seconds())
    offsets.sort()

    # Outcome positions: ~30% of events, first one around 40% through the
    # sequence so burn-and-rotate has tail events to rotate into.
    n_outcomes = max(1, round(spec.n_events * OUTCOME_SHARE))
    outcome_positions = set(_pick_outcome_positions(str_rng, spec.n_events, n_outcomes))

    events: list[PaymentEvent] = []
    burned_vpas: set[str] = set()
    vpa_cursor = 0
    for i, offset in enumerate(offsets):
        vpa = vpas[vpa_cursor]
        if i in outcome_positions:
            burned_vpas.add(vpa)
        ts = window_start + timedelta(seconds=offset)
        outcome: PriorOutcome | None = None
        if i in outcome_positions:
            outcome = str_rng.choice([PriorOutcome.CHARGEBACK, PriorOutcome.REFUND_ABUSE])
        events.append(
            PaymentEvent(
                event_id="",
                merchant_id=ring_merchants[i % spec.n_merchants],
                customer_id=factory.customer(),
                amount_paise=str_rng.randint(500, 2_000) * 100,
                upi_vpa=vpa,
                phone=str_rng.choice(phones),
                device_id=str_rng.choice(devices),
                email=str_rng.choice(email_variants) + "@gmail.com",
                ip=str_rng.choice(ips),
                ts=ts,
                payment_method=PaymentMethod.UPI,
                prior_outcome=outcome,
            )
        )
        if vpa in burned_vpas and vpa_cursor < len(vpas) - 1:
            vpa_cursor += 1
    return RingResult(spec=spec, events=events)


def _burst_fraction(str_rng: random.Random) -> float:
    """Clustered offsets: most events land in a tight sub-window."""
    if str_rng.random() < 0.6:
        return str_rng.uniform(0.0, 0.2)
    return str_rng.uniform(0.2, 0.95)


def _pick_outcome_positions(str_rng: random.Random, n_events: int, n_outcomes: int) -> list[int]:
    """Choose outcome positions with the first near the 40% mark."""
    anchor = int(n_events * 0.4)
    positions = {min(anchor, n_events - 1)}
    while len(positions) < n_outcomes:
        positions.add(str_rng.randrange(n_events))
    return sorted(positions)
