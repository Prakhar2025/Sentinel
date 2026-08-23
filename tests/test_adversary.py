"""Tests for the adversarial evasion pack (structure, not full evaluation)."""

from __future__ import annotations

from datetime import timedelta

from sentinel.adversary import Strategy, evasion_rates, generate_evasion_events
from sentinel.data.generate import WINDOW_START


def test_pack_generates_all_strategies_deterministically() -> None:
    first = generate_evasion_events(seed=42, start=WINDOW_START)
    second = generate_evasion_events(seed=42, start=WINDOW_START)
    assert [e.event_id for e, _ in first] == [e.event_id for e, _ in second]
    strategies = {strategy for _, strategy in first}
    assert strategies == set(Strategy)


def test_slow_rate_spreads_over_weeks() -> None:
    events = [
        (e, s)
        for e, s in generate_evasion_events(seed=42, start=WINDOW_START)
        if s is Strategy.SLOW_RATE
    ]
    times = [e.ts for e, _ in events]
    spread = max(times) - min(times)
    assert spread >= timedelta(days=60)


def test_rotation_uses_fresh_identities() -> None:
    events = [
        e for e, s in generate_evasion_events(seed=42, start=WINDOW_START) if s is Strategy.ROTATION
    ]
    assert len({e.device_id for e in events}) == len(events)
    assert len({e.upi_vpa for e in events}) == len(events)


def test_partitioned_has_three_sub_ring_devices() -> None:
    events = [
        e
        for e, s in generate_evasion_events(seed=42, start=WINDOW_START)
        if s is Strategy.PARTITIONED
    ]
    # Two rings per strategy, three sub-rings each: one device per sub-ring.
    assert len({e.device_id for e in events}) == 6
    phones = {e.phone for e in events}
    assert len(phones) <= 6  # bridge phones link adjacent sub-rings only


def test_evasion_rates_table() -> None:
    scored = [
        (None, Strategy.SLOW_RATE, 10),
        (None, Strategy.SLOW_RATE, 80),
        (None, Strategy.ROTATION, 45),  # above review, below block
    ]
    table = evasion_rates(scored, review_at=42, block_at=49)
    assert table["slow_rate"]["missed_entirely"] == 1
    assert table["slow_rate"]["not_blocked"] == 1
    assert table["rotation"]["not_blocked"] == 1
    assert table["rotation"]["missed_entirely_rate"] == 0.0
