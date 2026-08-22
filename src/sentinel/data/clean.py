"""Clean population generator.

Realism requirements from docs/04:
- Zipf-distributed merchants (a few large, many small)
- Log-normal amounts (median about 450 INR, tail to about 12k INR)
- Diurnal and weekday seasonality
- ~15% of events occur on a device shared within a household (benign overlap
  that makes false positives possible and the FP-cost metric meaningful)
- A small number of customers share a phone (phone upgrade)
- A tiny rate of benign chargeback/refund outcomes on clean events

Every clean event carries label is_fraud=False; the identity entities here
must never collide with ring entities (EntityFactory guarantees global
uniqueness).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from .entities import EntityFactory
from .models import PaymentEvent, PaymentMethod, PriorOutcome

IST_OFFSET = timedelta(hours=5, minutes=30)

# Hour-of-day weights: quiet nights, morning bump, evening peak.
HOUR_WEIGHTS = [
    0.2,
    0.1,
    0.1,
    0.1,
    0.1,
    0.2,
    0.4,
    0.8,
    1.4,
    2.0,
    2.6,
    3.0,
    3.2,
    3.0,
    2.6,
    2.4,
    2.6,
    3.0,
    3.6,
    4.4,
    4.6,
    4.0,
    2.6,
    1.0,
]
# Day-of-week factors (Mon..Sun): weekend shopping boost.
WEEKDAY_FACTORS = [1.0, 0.95, 0.95, 1.05, 1.15, 1.45, 1.35]

# Method mix for the clean population.
METHOD_TABLE: list[tuple[PaymentMethod, float]] = [
    (PaymentMethod.UPI, 0.85),
    (PaymentMethod.CARD, 0.10),
    (PaymentMethod.NETBANKING, 0.05),
]

# Benign dispute outcomes on clean events (labels stay is_fraud=False).
CLEAN_OUTCOME_TABLE: list[tuple[PriorOutcome | None, float]] = [
    (None, 0.987),
    (PriorOutcome.CHARGEBACK, 0.010),
    (PriorOutcome.REFUND_ABUSE, 0.003),
]

HOUSEHOLD_SHARE = 0.15  # events on a shared family device
PHONE_REUSE_SHARE = 0.05  # customers reachable on a previous owner's phone
MERCHANT_EXPONENT = 1.2  # power-law merchant weights; top merchant ~25% share


@dataclass(slots=True)
class CleanPerson:
    """A synthetic clean customer and their stable identity artifacts."""

    customer_id: str
    phone: str
    vpa: str
    email: str
    device: str
    ip: str


@dataclass(slots=True)
class CleanGenerator:
    """Builds the clean event stream for one dataset."""

    factory: EntityFactory
    str_rng: random.Random
    np_rng: np.random.Generator
    merchants: list[str]
    start: datetime
    days: int
    people: dict[str, CleanPerson] = field(default_factory=dict)
    household_devices: list[str] = field(default_factory=list)
    spare_phones: list[str] = field(default_factory=list)

    def _person(self) -> CleanPerson:
        person = CleanPerson(
            customer_id=self.factory.customer(),
            phone=self.factory.phone(),
            vpa=self.factory.vpa(),
            email=self.factory.email(),
            device=self.factory.device(),
            ip=self.factory.ip(),
        )
        self.spare_phones.append(person.phone)
        self.people[person.customer_id] = person
        return person

    def _pick_merchant(self) -> str:
        """Sample a merchant from a finite power-law weight profile.

        A raw numpy zipf draw clipped to the pool size piles the entire
        heavy tail onto the last merchant (measured: 57% share at a=1.1).
        Explicitly normalized rank weights give a realistic head (~25%
        top merchant) with no clip artifact.
        """
        ranks = np.arange(1, len(self.merchants) + 1, dtype=np.float64)
        weights = ranks**-MERCHANT_EXPONENT
        probs = weights / weights.sum()
        index = int(self.np_rng.choice(len(self.merchants), p=probs))
        return self.merchants[index]

    def _amount_paise(self) -> int:
        rupees = float(self.np_rng.lognormal(mean=6.11, sigma=0.95))
        rupees = min(max(rupees, 20.0), 12_000.0)
        return round(rupees) * 100

    def _timestamp(self) -> datetime:
        base = self.start
        day_probs = [
            WEEKDAY_FACTORS[(base + timedelta(days=d)).weekday()] for d in range(self.days)
        ]
        day = self.str_rng.choices(range(self.days), weights=day_probs, k=1)[0]
        hour = self.str_rng.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
        minute = self.str_rng.randint(0, 59)
        second = self.str_rng.randint(0, 59)
        return base + timedelta(days=day, hours=hour, minutes=minute, seconds=second)

    def _pick_person(self) -> CleanPerson:
        if self.people and self.str_rng.random() < 0.35:
            return self.str_rng.choice(list(self.people.values()))
        return self._person()

    def generate(self, n_events: int) -> list[PaymentEvent]:
        """Generate n_events clean events with repeat customers and overlap."""
        events: list[PaymentEvent] = []
        while len(events) < n_events:
            person = self._pick_person()
            device = person.device
            if self.str_rng.random() < HOUSEHOLD_SHARE:
                if self.household_devices and self.str_rng.random() < 0.7:
                    device = self.str_rng.choice(self.household_devices)
                else:
                    device = self.factory.device()
                    self.household_devices.append(device)
            phone = person.phone
            if self.spare_phones and self.str_rng.random() < PHONE_REUSE_SHARE:
                phone = self.str_rng.choice(self.spare_phones)
            outcome = self.str_rng.choices(
                [o for o, _ in CLEAN_OUTCOME_TABLE],
                weights=[w for _, w in CLEAN_OUTCOME_TABLE],
                k=1,
            )[0]
            method = self.str_rng.choices(
                [m for m, _ in METHOD_TABLE],
                weights=[w for _, w in METHOD_TABLE],
                k=1,
            )[0]
            events.append(
                PaymentEvent(
                    event_id="",  # assigned after chronological sort
                    merchant_id=self._pick_merchant(),
                    customer_id=person.customer_id,
                    amount_paise=self._amount_paise(),
                    upi_vpa=person.vpa if method is PaymentMethod.UPI else None,
                    phone=phone,
                    device_id=device,
                    email=person.email,
                    ip=person.ip,
                    ts=self._timestamp(),
                    payment_method=method,
                    prior_outcome=outcome,
                )
            )
        return events[:n_events]
