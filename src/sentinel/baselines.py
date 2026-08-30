"""Baseline classifiers (FR-13, docs/05): measured, not asserted.

Logistic regression (ring-grouped CV over C) and a small gradient-
boosted tree, trained on the SAME cached feature rows and ring-
stratified splits as the rule ensemble, evaluated on the same held-out
test rows. If a baseline wins, that result is shown; it strengthens the
v2 GNN case honestly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from .features import FeatureVector
from .metrics import precision_recall_f1


@dataclass(slots=True)
class Row:
    """One cached feature row with its label and grouping."""

    features: FeatureVector
    is_fraud: bool
    group: str
    event_id: str | None = None


class RowLike(Protocol):
    """Structural shape of a feature row (calibrate.ScoredRow qualifies)."""

    features: FeatureVector
    is_fraud: bool
    group: str


def _matrix(rows: Sequence[RowLike]) -> tuple[list[list[float]], list[int], list[str]]:
    return (
        [row.features.normalized() for row in rows],
        [int(row.is_fraud) for row in rows],
        [row.group for row in rows],
    )


def _at_threshold(scores: list[float], labels: list[int], threshold: float) -> dict[str, float]:
    tp = fp = fn = 0
    for score, label in zip(scores, labels, strict=True):
        predicted = score >= threshold
        if predicted and label:
            tp += 1
        elif predicted and not label:
            fp += 1
        elif not predicted and label:
            fn += 1
    return precision_recall_f1(tp, fp, fn)


def fit_logistic(train: Sequence[RowLike]) -> LogisticRegression:
    """LR with ring-grouped 3-fold CV over the regularization strength."""
    x, y, groups = _matrix(train)
    best_c, best_f1 = 1.0, -1.0
    n_groups = len(set(groups))
    if n_groups < 2:
        model = LogisticRegression(C=best_c, max_iter=1000)
        model.fit(x, y)
        return model
    splitter = GroupKFold(n_splits=min(3, n_groups))
    for c in (0.1, 1.0, 10.0):
        fold_f1: list[float] = []
        for train_idx, hold_idx in splitter.split(x, y, groups=groups):
            fold_train_x = [x[i] for i in train_idx]
            fold_train_y = [y[i] for i in train_idx]
            fold_x = [x[i] for i in hold_idx]
            fold_y = [y[i] for i in hold_idx]
            if len(set(fold_train_y)) < 2 or len(set(fold_y)) < 2:
                continue
            model = LogisticRegression(C=c, max_iter=1000)
            model.fit(fold_train_x, fold_train_y)
            scores = model.predict_proba(fold_x)[:, 1].tolist()
            tp = sum(1 for s, y in zip(scores, fold_y, strict=True) if s >= 0.5 and y)
            fp = sum(1 for s, y in zip(scores, fold_y, strict=True) if s >= 0.5 and not y)
            fn = sum(1 for s, y in zip(scores, fold_y, strict=True) if s < 0.5 and y)
            result = precision_recall_f1(tp, fp, fn)
            fold_f1.append(result["f1"])
        if fold_f1 and sum(fold_f1) / len(fold_f1) > best_f1:
            best_f1 = sum(fold_f1) / len(fold_f1)
            best_c = c
    model = LogisticRegression(C=best_c, max_iter=1000)
    model.fit(x, y)
    return model


def fit_gbm(train: Sequence[RowLike]) -> GradientBoostingClassifier:
    """Small-depth GBDT to limit overfit at this sample size."""
    x, y, _groups = _matrix(train)
    model = GradientBoostingClassifier(max_depth=3, n_estimators=100, random_state=42)
    model.fit(x, y)
    return model


def evaluate_baselines(
    train: Sequence[RowLike], test: Sequence[RowLike]
) -> dict[str, dict[str, float]]:
    """Side-by-side test metrics for both baselines at p >= 0.5."""
    x_test, y_test, _groups = _matrix(test)
    results: dict[str, dict[str, float]] = {}
    for name, model in (
        ("logistic_regression", fit_logistic(train)),
        ("gradient_boosting", fit_gbm(train)),
    ):
        scores = model.predict_proba(x_test)[:, 1].tolist()
        results[name] = _at_threshold(scores, y_test, 0.5)
    return results


__all__ = ["Row", "RowLike", "evaluate_baselines", "fit_gbm", "fit_logistic"]
