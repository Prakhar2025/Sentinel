"""Ring-stratified split assignment with an identity-leakage guard.

The honesty protocol (docs/05) requires that no identity entity (customer,
VPA, phone, device, email) appear in two different splits: otherwise the
graph scorer effectively memorizes a ring during calibration and test
metrics leak. Merchants are intentionally allowed to span splits: sharing
merchants across rings and the clean population is the cross-merchant
phenomenon the detector exists to find.

Algorithm:
1. Build connected components over events using identity-entity edges
   (union-find). A ring naturally forms one component; a household sharing
   a device forms another; standalone clean events are singletons.
2. Assign whole components to splits greedily, largest first, always to
   the split furthest below its target share (60/20/20 by event count).
   Deterministic: components ordered by (size desc, first event index).
"""

from __future__ import annotations

from .models import PaymentEvent, Split

TARGET_SHARES: list[tuple[Split, float]] = [
    (Split.TRAIN, 0.6),
    (Split.CALIBRATION, 0.2),
    (Split.TEST, 0.2),
]


class UnionFind:
    """Minimal union-find over integer indices."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, i: int) -> int:
        root = i
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[i] != root:  # path compression
            self._parent[i], i = root, self._parent[i]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def identity_entities(event: PaymentEvent) -> list[str]:
    """Identity entity keys used for linkage; merchants excluded by design."""
    keys = [f"customer:{event.customer_id}"]
    if event.upi_vpa:
        keys.append(f"vpa:{event.upi_vpa}")
    if event.phone:
        keys.append(f"phone:{event.phone}")
    if event.device_id:
        keys.append(f"device:{event.device_id}")
    if event.email:
        keys.append(f"email:{event.email}")
    return keys


def assign_splits(events: list[PaymentEvent], fraud_event_ids: set[str]) -> list[Split]:
    """Assign a split to every event with zero identity leakage.

    Fraud and clean populations are allocated independently, each toward a
    60/20/20 share. Without this, greedy allocation on the overall total
    lets the train split absorb every ring (observed in the first run:
    100/100 fraud in train), which would make calibration and test
    fraud-free and the evaluation meaningless.
    """
    n = len(events)
    uf = UnionFind(n)
    by_entity: dict[str, int] = {}
    for index, event in enumerate(events):
        for key in identity_entities(event):
            first = by_entity.get(key)
            if first is None:
                by_entity[key] = index
            else:
                uf.union(first, index)

    components: dict[int, list[int]] = {}
    for index in range(n):
        components.setdefault(uf.find(index), []).append(index)
    all_components = sorted(
        components.values(),
        key=lambda members: (-len(members), members[0]),
    )

    assignment: list[Split | None] = [None] * n
    # Components are pure by construction (ring entities never collide with
    # clean entities), so the first member's fraud flag classifies it.
    fraud_components = [
        members for members in all_components if events[members[0]].event_id in fraud_event_ids
    ]
    clean_components = [
        members for members in all_components if events[members[0]].event_id not in fraud_event_ids
    ]

    n_fraud = sum(len(members) for members in fraud_components)
    n_clean = n - n_fraud
    _fill(fraud_components, n_fraud, assignment)
    _fill(clean_components, n_clean, assignment)
    return [split for split in assignment if split is not None]


def _fill(
    components: list[list[int]], population_size: int, assignment: list[Split | None]
) -> None:
    """Greedy largest-first allocation of components toward 60/20/20."""
    counts = {split: 0 for split, _ in TARGET_SHARES}
    for members in components:
        deficits = {
            split: share * population_size - counts[split] for split, share in TARGET_SHARES
        }
        chosen = max(TARGET_SHARES, key=lambda pair: deficits[pair[0]])[0]
        for member in members:
            assignment[member] = chosen
        counts[chosen] += len(members)


def assert_no_identity_leakage(events: list[PaymentEvent], splits: list[Split]) -> None:
    """Raise ValueError if any identity entity spans two splits."""
    seen: dict[str, Split] = {}
    for event, split in zip(events, splits, strict=True):
        for key in identity_entities(event):
            previous = seen.get(key)
            if previous is not None and previous is not split:
                msg = f"identity leakage: {key} appears in {previous} and {split}"
                raise ValueError(msg)
            seen[key] = split
