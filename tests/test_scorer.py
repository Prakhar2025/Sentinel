"""Tests for the deterministic scorer (docs/05 scoring contract)."""

from __future__ import annotations

import pytest

from sentinel.features import feature_vector_from_raw
from sentinel.scorer import (
    DEFAULT_WEIGHTS,
    FEATURE_NAMES,
    WeightValidationError,
    reason_codes,
    score_features,
    validate_weights,
)


def vector(**overrides: float | int) -> object:
    raw = {
        "device_identity_ratio": 6.0,
        "cross_merchant_fanout": 6,
        "taint": 1.0,
        "velocity_merchants_72h": 5,
        "burn_rotate": 1,
        "amount_band_hit": 1.0,
        "new_identity_fraction": 1.0,
    }
    raw.update(overrides)
    return feature_vector_from_raw(raw)


def test_default_weights_sum_to_100() -> None:
    assert sum(DEFAULT_WEIGHTS.values()) == 100
    assert set(DEFAULT_WEIGHTS) == set(FEATURE_NAMES)


def test_all_max_features_scores_100() -> None:
    result = score_features(vector())
    assert result.score == 100


def test_all_zero_features_scores_0() -> None:
    result = score_features(
        vector(
            device_identity_ratio=0.0,
            cross_merchant_fanout=0,
            taint=0.0,
            velocity_merchants_72h=0,
            burn_rotate=0,
            amount_band_hit=0.0,
            new_identity_fraction=0.0,
        )
    )
    assert result.score == 0


def test_score_is_deterministic_and_decomposes() -> None:
    first = score_features(vector())
    second = score_features(vector())
    assert first.score == second.score
    assert first.contributions == second.contributions
    assert pytest.approx(sum(first.contributions.values()), abs=0.5) == first.score


def test_validation_rejects_bad_weights() -> None:
    with pytest.raises(WeightValidationError):
        validate_weights({name: 10 for name in FEATURE_NAMES})  # sums to 70
    bad_keys = dict(DEFAULT_WEIGHTS)
    bad_keys.pop("taint_propagation")
    with pytest.raises(WeightValidationError):
        validate_weights(bad_keys)
    negative = dict(DEFAULT_WEIGHTS)
    negative["taint_propagation"] = -1
    negative["velocity_72h"] = 25
    with pytest.raises(WeightValidationError):
        validate_weights(negative)


def test_reason_codes_fire_on_ring_features() -> None:
    codes = reason_codes(vector())
    assert set(codes) == {
        "RNG_DEVICE_FANOUT",
        "RNG_IDENTITY_FARM",
        "RNG_TAINT_LINK",
        "RNG_VELOCITY",
        "RNG_BURN_ROTATE",
        "RNG_AMOUNT_PATTERN",
    }


def test_reason_codes_empty_for_clean_profile() -> None:
    codes = reason_codes(
        vector(
            device_identity_ratio=1.0,
            cross_merchant_fanout=1,
            taint=0.0,
            velocity_merchants_72h=1,
            burn_rotate=0,
            amount_band_hit=0.0,
            new_identity_fraction=0.0,
        )
    )
    assert codes == []
