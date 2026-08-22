"""Domain models for payment events and evaluation labels.

PaymentEvent mirrors the API input contract (docs/06): it is the
serving-shaped record and deliberately carries no label. Ground truth lives
only in EventLabel, which never crosses the serving boundary (docs/04).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PaymentMethod(StrEnum):
    """Payment instrument used for the event."""

    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"


class PriorOutcome(StrEnum):
    """Known prior outcome attached to the event (merchant-side knowledge).

    Clean events may carry benign dispute outcomes at a low rate; this is
    deliberate benign overlap so taint-style features cannot trivially
    equal fraud (docs/04, generator requirements).
    """

    CHARGEBACK = "chargeback"
    REFUND_ABUSE = "refund_abuse"
    CONFIRMED_FRAUD = "confirmed_fraud"


class Split(StrEnum):
    """Evaluation split assignment (ring-stratified, docs/05)."""

    TRAIN = "train"
    CALIBRATION = "calibration"
    TEST = "test"


class RingStrategy(StrEnum):
    """Injection archetype of a fraud ring."""

    STANDARD = "standard"
    SOPHISTICATED = "sophisticated"


class PaymentEvent(BaseModel):
    """A single payment event in serving shape (no label fields)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    merchant_id: str
    customer_id: str
    amount_paise: int = Field(ge=0)
    currency: str = "INR"
    upi_vpa: str | None = None
    phone: str | None = None
    device_id: str | None = None
    email: str | None = None
    ip: str | None = None
    ts: datetime
    payment_method: PaymentMethod
    prior_outcome: PriorOutcome | None = None


class EventLabel(BaseModel):
    """Ground truth for one event; evaluation-side only."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    is_fraud: bool
    ring_id: str | None = None
    ring_strategy: RingStrategy | None = None
    split: Split
