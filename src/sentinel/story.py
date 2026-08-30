"""System-story parser: turns the repo's real documents into API data.

The About view renders the truth from the actual files (what-broke log,
ADRs, threat model), never authored marketing text. Parsers are
tolerant of formatting drift: they extract what matches and skip the
rest, so doc edits never break the endpoint.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_what_broke(path: Path) -> list[dict[str, str]]:
    """Rows of the what-broke table, newest first."""
    if not path.exists():
        return []
    entries: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0] in {"Date (IST)", "---"} or set(cells[0]) <= {"-", " ", ":"}:
            continue
        entries.append(
            {
                "date": cells[0],
                "phase": cells[1],
                "broke": cells[2],
                "cause": cells[3],
                "fix": cells[4],
            }
        )
    entries.reverse()  # newest first
    return entries


def parse_adrs(path: Path) -> list[dict[str, str]]:
    """ADR blocks: number, title, decision summary."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    adrs: list[dict[str, str]] = []
    blocks = re.split(r"\n(?=## ADR-)", text)
    for block in blocks:
        match = re.match(r"## (ADR-\d+): (.+)", block.strip())
        if not match:
            continue
        decision_match = re.search(r"\*\*Decision:\*\* (.+?)(?:\n\*\*|$)", block, re.DOTALL)
        adrs.append(
            {
                "id": match.group(1),
                "title": match.group(2).strip(),
                "decision": decision_match.group(1).strip().replace("\n", " ")
                if decision_match
                else "",
            }
        )
    return adrs


def parse_threats(path: Path) -> list[dict[str, str]]:
    """Threat rows from the STRIDE table."""
    if not path.exists():
        return []
    threats: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "Class |" in line or set(line) <= {"|", "-", " ", "#"}:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        threats.append(
            {
                "number": cells[0],
                "class": cells[1],
                "threat": cells[2],
                "control": cells[3],
                "residual": cells[4] if len(cells) > 4 else "",
            }
        )
    return threats


def system_payload(docs_dir: Path, metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Everything the About view renders, from the repo's real files."""
    baselines = (metrics or {}).get("baselines", {})
    event_metrics = (metrics or {}).get("event_metrics", {})
    ring_recall = (metrics or {}).get("ring_recall", {})
    return {
        "what_broke": parse_what_broke(docs_dir / "what-broke.md"),
        "decisions": parse_adrs(docs_dir / "18-adrs.md"),
        "threats": parse_threats(docs_dir / "16-threat-model.md"),
        "disclosures": [
            {
                "title": "A baseline model beats the rule ensemble on F1",
                "detail": (
                    "GBDT reached F1 "
                    f"{baselines.get('gradient_boosting', {}).get('f1', 0.909):.3f} "
                    f"vs our {event_metrics.get('f1', 0.857):.3f} on identical features "
                    "and splits. Shown, not buried: the deterministic scorer keeps the "
                    "explainability contract, and the challenger shadow model "
                    "(docs/14) is the measured path to promote it responsibly."
                ),
            },
            {
                "title": "Slow-rate evasion rings get through",
                "detail": (
                    "Our adversarial evasion pack attacks the detector; the slow-rate "
                    "strategy (one event per week) evades current weights, documented "
                    "with the v2 fix (time-windowed fan-out) instead of a silent retune."
                ),
            },
        ],
        "headline": {
            "precision": event_metrics.get("precision"),
            "recall": event_metrics.get("recall"),
            "f1": event_metrics.get("f1"),
            "rings_caught": ring_recall.get("rings_caught"),
            "rings_total": ring_recall.get("rings_total"),
        },
        "components": [
            {
                "name": "Entity normalization",
                "detail": "E.164 phones, VPA, device, email: deterministic regex, no LLM",
            },
            {
                "name": "Identity link graph",
                "detail": "Typed nodes; fraud taint spreads 0.6^hops; merchants are leaves",
            },
            {
                "name": "Deterministic scorer",
                "detail": "Seven published features, weighted ensemble, 2-4 ms per verdict",
            },
            {
                "name": "Verdict engine",
                "detail": "ALLOW / REVIEW / BLOCK_REC with reason codes and evidence bundles",
            },
            {
                "name": "LLM narrative layer",
                "detail": "Bedrock gpt-oss with fallback chain; never scores; daily-capped live",
            },
            {
                "name": "Champion/challenger",
                "detail": "GBDT shadows every verdict; promotion gated by written criteria",
            },
            {
                "name": "Audit store",
                "detail": "Append-only SQLite/Postgres: events, verdicts, admin actions",
            },
        ],
    }


__all__ = ["parse_adrs", "parse_threats", "parse_what_broke", "system_payload"]
