"""Deterministic weighted rule scorer (docs/05).

The LLM never scores. The ensemble is a published, versioned weight
vector over the seven normalized features; every score decomposes into
per-feature contributions, which is the explainability contract.
Weights sum to 100 by construction and are validated on every call.
"""

from __future__ import annotations

from dataclasses import dataclass

from .features import FeatureVector

MODEL_VERSION = "rules-v1.0"

FEATURE_NAMES = (
    "device_identity_ratio",
    "cross_merchant_fanout",
    "taint_propagation",
    "velocity_72h",
    "burn_rotate",
    "amount_pattern",
    "new_identity_burst",
)

DEFAULT_WEIGHTS: dict[str, int] = {
    "device_identity_ratio": 14,
    "cross_merchant_fanout": 20,
    "taint_propagation": 24,
    "velocity_72h": 14,
    "burn_rotate": 10,
    "amount_pattern": 4,
    "new_identity_burst": 14,
}


class WeightValidationError(ValueError):
    """Raised when a weight vector is malformed (sum != 100 or unknown key)."""


def validate_weights(weights: dict[str, int]) -> None:
    """Ensure the weight vector is complete, non-negative, and sums to 100."""
    if set(weights) != set(FEATURE_NAMES):
        raise WeightValidationError(f"weight keys must be exactly {FEATURE_NAMES}")
    if any(value < 0 for value in weights.values()):
        raise WeightValidationError("weights must be non-negative")
    if sum(weights.values()) != 100:
        raise WeightValidationError(f"weights must sum to 100, got {sum(weights.values())}")


@dataclass(slots=True, frozen=True)
class ScoreResult:
    """Score plus its full decomposition."""

    score: int  # 0-100
    contributions: dict[str, float]


def score_features(features: FeatureVector, weights: dict[str, int] | None = None) -> ScoreResult:
    """Score one feature vector; deterministic and pure."""
    active = weights if weights is not None else DEFAULT_WEIGHTS
    validate_weights(active)
    values = features.normalized()
    contributions = {
        name: round(weight * value, 4)
        for name, weight, value in zip(FEATURE_NAMES, active.values(), values, strict=True)
    }
    total = sum(contributions.values())
    return ScoreResult(score=round(min(100.0, max(0.0, total))), contributions=contributions)


def reason_codes(features: FeatureVector) -> list[str]:
    """Machine-readable reasons for the verdict (docs/06 reference table)."""
    codes: list[str] = []
    if features.cross_merchant_fanout >= 3:
        codes.append("RNG_DEVICE_FANOUT")
    if features.device_identity_ratio >= 5 or features.new_identity_fraction >= 0.5:
        codes.append("RNG_IDENTITY_FARM")
    if features.taint >= 0.3:
        codes.append("RNG_TAINT_LINK")
    if features.velocity_merchants_72h >= 3:
        codes.append("RNG_VELOCITY")
    if features.burn_rotate == 1:
        codes.append("RNG_BURN_ROTATE")
    if features.amount_band_hit >= 1.0:
        codes.append("RNG_AMOUNT_PATTERN")
    return codes
