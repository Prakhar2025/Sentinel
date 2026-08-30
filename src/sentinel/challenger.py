"""Champion/challenger shadow model (v2).

The rule ensemble is the serving champion. A gradient-boosted
challenger, trained on the same cached train-split features, runs in
shadow: its opinion is recorded next to every verdict and never used
for the decision. This is how fintech risk teams evaluate model
replacements without touching production decisions.

Promotion criteria (documented, deliberate, in docs/14):
1. Challenger F1 strictly exceeds the champion on the held-out set
   across multiple seeds, not one.
2. No precision regression beyond -0.02 at the operating threshold.
3. Explainability parity: per-feature attributions (SHAP or
   equivalent) surfaced in the evidence panel before any cutover.
4. A soak period in shadow with agreement >= 95% on BLOCK_REC band
   disagreements reviewed by an analyst.

Until all four hold, the deterministic scorer stays. Nothing in this
module can alter a verdict.
"""

from __future__ import annotations

import pickle
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .baselines import RowLike, fit_gbm
from .features import FeatureVector

CHALLENGER_VERSION = "gbdt-challenger-1.0"


@dataclass(slots=True)
class ChallengerModel:
    """A fitted shadow model; predicts, never decides."""

    model: Any
    version: str = CHALLENGER_VERSION
    trained_on: str = "train-split"
    threshold: float = 0.5

    def predict(self, features: FeatureVector) -> dict[str, float | int | bool]:
        """Shadow opinion for one event: probability, 0-100 score, flag."""
        probability = float(self.model.predict_proba([features.normalized()])[0][1])
        return {
            "score": round(probability * 100),
            "probability": round(probability, 4),
            "flag": probability >= self.threshold,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(
                {
                    "model": self.model,
                    "version": self.version,
                    "trained_on": self.trained_on,
                    "threshold": self.threshold,
                },
                handle,
            )

    @classmethod
    def load(cls, path: Path) -> ChallengerModel | None:
        """Load a shadow model; None (shadow off) when absent or stale."""
        if not path.exists():
            return None
        try:
            with path.open("rb") as handle:
                payload = pickle.load(handle)
        except (OSError, pickle.UnpicklingError):
            return None
        if payload.get("version") != CHALLENGER_VERSION:
            return None
        return cls(
            model=payload["model"],
            version=payload["version"],
            trained_on=payload["trained_on"],
            threshold=payload["threshold"],
        )


def train_challenger(seed: int = 42, save_path: Path | None = None) -> ChallengerModel:
    """Fit the challenger on cached train-split features (online replay)."""
    from .calibrate import extract_rows
    from .data.models import Split

    train_rows, _ = extract_rows(Split.TRAIN, seed)
    return train_challenger_from_rows(train_rows, f"train-split seed {seed}", save_path)


def train_challenger_from_rows(
    train_rows: Sequence[RowLike], trained_on: str, save_path: Path | None = None
) -> ChallengerModel:
    """Fit from prepared rows; separated for testability."""
    challenger = ChallengerModel(model=fit_gbm(train_rows), trained_on=trained_on)
    if save_path is not None:
        challenger.save(save_path)
    return challenger


__all__ = [
    "CHALLENGER_VERSION",
    "ChallengerModel",
    "train_challenger",
    "train_challenger_from_rows",
]
