"""Tests for the synthetic data generator (docs/04 requirements)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from sentinel.data.entities import PHONE_RE, VPA_RE
from sentinel.data.generate import (
    DEFAULT_CLEAN,
    DEFAULT_FRAUD,
    generate_dataset,
    main,
    validate,
    write_artifacts,
)
from sentinel.data.models import PaymentEvent, PaymentMethod, RingStrategy, Split
from sentinel.data.splits import assert_no_identity_leakage, assign_splits, identity_entities

SEED = 42


@pytest.fixture(scope="module")
def dataset() -> tuple[list[PaymentEvent], list, dict]:
    events, labels, summary = generate_dataset(seed=SEED)
    return events, labels, summary


def test_exact_composition(dataset) -> None:
    _events, labels, summary = dataset
    assert summary["total_events"] == DEFAULT_CLEAN + DEFAULT_FRAUD
    assert summary["fraud_events"] == DEFAULT_FRAUD
    assert summary["clean_events"] == DEFAULT_CLEAN
    assert len(labels) == 1000
    assert validate(summary) == []


def test_determinism() -> None:
    first = generate_dataset(seed=SEED)
    second = generate_dataset(seed=SEED)
    assert [e.model_dump() for e in first[0]] == [e.model_dump() for e in second[0]]
    assert [label.model_dump() for label in first[1]] == [label.model_dump() for label in second[1]]


def test_different_seed_changes_data() -> None:
    first = generate_dataset(seed=SEED)[0]
    second = generate_dataset(seed=43)[0]
    assert [e.event_id for e in first] != [e.event_id for e in second]


def test_split_proportions_and_fraud_presence(dataset) -> None:
    _, labels, _summary = dataset
    total = len(labels)
    for split, share in ((Split.TRAIN, 0.6), (Split.CALIBRATION, 0.2), (Split.TEST, 0.2)):
        count = sum(1 for label in labels if label.split is split)
        assert abs(count / total - share) < 0.10
        fraud_in_split = sum(1 for label in labels if label.split is split and label.is_fraud)
        assert fraud_in_split >= 8, f"{split} needs at least one whole ring"


def test_zero_identity_leakage_across_splits(dataset) -> None:
    events, labels, _ = dataset
    splits = [label.split for label in labels]
    assert_no_identity_leakage(events, splits)  # raises on any leak


def test_leakage_guard_detects_real_leak() -> None:
    factory_events = [
        PaymentEvent(
            event_id=f"e{i}",
            merchant_id="m1",
            customer_id="c1",
            amount_paise=100,
            upi_vpa="a@ybl",
            phone="+919000000000",
            device_id="d1",
            email="a@x.com",
            ts=__import__("datetime").datetime(2026, 1, 1) + timedelta(hours=i),
            payment_method=PaymentMethod.UPI,
        )
        for i in range(2)
    ]
    with pytest.raises(ValueError, match="identity leakage"):
        assert_no_identity_leakage(factory_events, [Split.TRAIN, Split.TEST])


def test_entity_formats(dataset) -> None:
    events, _, _ = dataset
    for event in events:
        if event.phone:
            assert PHONE_RE.match(event.phone), event.phone
        if event.upi_vpa:
            assert VPA_RE.match(event.upi_vpa), event.upi_vpa
        assert isinstance(event.amount_paise, int)
        assert event.amount_paise > 0
        assert event.currency == "INR"


def test_amount_distribution_realism(dataset) -> None:
    events, labels, _ = dataset
    clean_amounts = sorted(
        e.amount_paise for e, label in zip(events, labels, strict=True) if not label.is_fraud
    )
    median = clean_amounts[len(clean_amounts) // 2]
    assert 20_000 <= median <= 80_000  # median 200-800 INR
    assert clean_amounts[-1] <= 1_210_000  # tail capped near 12k INR


def test_merchant_concentration_realistic(dataset) -> None:
    events, _, summary = dataset
    assert 0.10 <= summary["top_merchant_share"] <= 0.40
    # Power-law head: the top-3 merchants together should hold a large
    # minority of traffic, but no merchant should dominate everything.
    counts: dict[str, int] = {}
    for event in events:
        counts[event.merchant_id] = counts.get(event.merchant_id, 0) + 1
    top3 = sorted(counts.values(), reverse=True)[:3]
    assert sum(top3) / len(events) > 0.40


def test_benign_overlap_exists(dataset) -> None:
    """Households share devices; without overlap FP metrics would be fake."""
    events, _, _ = dataset
    device_users: dict[str, set[str]] = {}
    for event in events:
        if event.device_id:
            device_users.setdefault(event.device_id, set()).add(event.customer_id)
    shared = [d for d, users in device_users.items() if len(users) >= 2]
    assert len(shared) > 10, "expected benign shared devices in the clean population"


def test_ring_structure(dataset) -> None:
    events, labels, _ = dataset
    fraud_ids = {label.event_id for label in labels if label.is_fraud}
    ring_events = [e for e in events if e.event_id in fraud_ids]
    by_ring: dict[str, list[PaymentEvent]] = {}
    for event, label in zip(events, labels, strict=True):
        if label.is_fraud:
            by_ring.setdefault(label.ring_id or "", []).append(event)
    assert len(by_ring) >= 8
    for ring_id, members in by_ring.items():
        merchants = {e.merchant_id for e in members}
        devices = {e.device_id for e in members}
        customers = {e.customer_id for e in members}
        assert len(merchants) >= 3, f"{ring_id} must hit >=3 merchants"
        # Identity fan-out: many customers per few devices is the ring signal.
        assert len(customers) / max(len(devices), 1) >= 2.5
    assert ring_events, "fraud events must exist"


def test_burn_and_rotate_exists(dataset) -> None:
    """At least one ring abandons a VPA after its first fraud outcome."""
    events, labels, _ = dataset
    by_ring: dict[str, list[tuple[PaymentEvent, object]]] = {}
    for event, label in zip(events, labels, strict=True):
        if label.is_fraud:
            by_ring.setdefault(label.ring_id or "", []).append((event, label))
    burned_elsewhere = False
    for members in by_ring.values():
        members_sorted = sorted(members, key=lambda pair: pair[0].ts)
        for index, (event, _) in enumerate(members_sorted):
            if event.prior_outcome is not None:
                later_uses = [
                    later.upi_vpa
                    for later, _ in members_sorted[index + 1 :]
                    if later.upi_vpa == event.upi_vpa
                ]
                if not later_uses and index + 1 < len(members_sorted):
                    burned_elsewhere = True
    assert burned_elsewhere, "expected burn-and-rotate behavior in at least one ring"


def test_sophisticated_ring_is_slow(dataset) -> None:
    events, labels, _ = dataset
    sophisticated_rings = {
        label.ring_id for label in labels if label.ring_strategy is RingStrategy.SOPHISTICATED
    }
    assert sophisticated_rings, "at least one sophisticated ring required"
    for _event, label in zip(events, labels, strict=True):
        if label.ring_id in sophisticated_rings:
            pass  # membership check only; spread asserted below
    for ring_id in sophisticated_rings:
        times = [e.ts for e, label in zip(events, labels, strict=True) if label.ring_id == ring_id]
        spread = max(times) - min(times)
        assert spread >= timedelta(days=14), "sophisticated ring must spread over weeks"


def test_standard_rings_are_bursty(dataset) -> None:
    events, labels, _ = dataset
    standard_rings = {
        label.ring_id: label for label in labels if label.ring_strategy is RingStrategy.STANDARD
    }
    for ring_id in list(standard_rings)[:3]:
        times = [e.ts for e, label in zip(events, labels, strict=True) if label.ring_id == ring_id]
        spread = max(times) - min(times)
        assert spread <= timedelta(days=7), "standard rings must burst inside a week"


def test_fraud_outcome_share(dataset) -> None:
    events, labels, summary = dataset
    assert 0.20 <= summary["fraud_outcome_share"] <= 0.45
    # Clean events carry a tiny benign dispute rate (labels stay clean).
    clean_outcomes = sum(
        1
        for e, label in zip(events, labels, strict=True)
        if not label.is_fraud and e.prior_outcome is not None
    )
    assert 0 < clean_outcomes <= 30


def test_serving_label_separation(tmp_path: Path) -> None:
    events, labels, summary = generate_dataset(seed=SEED)
    write_artifacts(tmp_path, events, labels, summary)
    event_lines = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    label_lines = {
        json.loads(line)["event_id"]: json.loads(line)
        for line in (tmp_path / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert len(event_lines) == 1000
    for record in event_lines:
        assert "is_fraud" not in record
        assert "ring_id" not in record
        assert "split" not in record
    assert set(label_lines) == {record["event_id"] for record in event_lines}


def test_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "gen"
    code = main(["--seed", "7", "--out", str(out)])
    captured = capsys.readouterr()
    assert code == 0
    assert "INVARIANT VIOLATION" not in captured.out
    assert (out / "events.jsonl").exists()
    assert (out / "labels.jsonl").exists()
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["seed"] == 7
    assert summary["fraud_events"] == DEFAULT_FRAUD


def test_validate_catches_bad_summary() -> None:
    problems = validate(
        {
            "fraud_events": 99,
            "total_events": 1000,
            "splits": {},
            "ring_strategies": {"sophisticated": 0},
        }
    )
    assert any("99" in p for p in problems)
    assert any("sophisticated" in p for p in problems)


def test_identity_entities_excludes_merchants() -> None:
    event = PaymentEvent(
        event_id="e",
        merchant_id="m",
        customer_id="c",
        amount_paise=1,
        upi_vpa="a@ybl",
        phone="+919000000001",
        device_id="d",
        email="a@x.com",
        ts=__import__("datetime").datetime(2026, 1, 1),
        payment_method=PaymentMethod.UPI,
    )
    keys = identity_entities(event)
    assert "merchant:m" not in keys
    assert len(keys) == 5


def test_assign_splits_gives_each_population_all_three_splits() -> None:
    events, labels, _ = generate_dataset(seed=SEED)
    fraud_ids = {label.event_id for label in labels if label.is_fraud}
    splits = assign_splits(events, fraud_ids)
    fraud_splits = {
        split for event, split in zip(events, splits, strict=True) if event.event_id in fraud_ids
    }
    assert fraud_splits == {Split.TRAIN, Split.CALIBRATION, Split.TEST}
