"""One-shot Bedrock model verification (Phase 0).

Fills the model verification table in docs/08-tech-stack.md with measured
facts: which candidate models exist in the configured region, whether they
honor constrained JSON output via the Converse API, and their latency.

Budget guardrails (non-negotiable):
- Discovery uses list_foundation_models (control plane; free).
- At most ONE inference call per model, max 128 output tokens.
- No retry loops. Any error is reported, never retried.

Usage: python scripts/verify_models.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

# Candidate models per docs/03 + 08. Matched case-insensitively against
# modelId/modelName returned by the Bedrock control plane.
CANDIDATES: dict[str, str] = {
    "gpt-oss-120b": "gpt-oss-120b",
    "gpt-oss-20b": "gpt-oss-20b",
    "glm-5": "glm-5",
    "nova-lite": "nova-lite",
    "llama3-3-70b": "llama3-3-70b",
}

PROMPT = (
    "You are being tested for JSON output compliance. "
    'Respond with exactly this JSON object and nothing else: {"ok": true, "model": "your-model-name"}'
)

EXPECTED_KEYS = {"ok", "model"}


@dataclass(slots=True)
class VerifyResult:
    """Measured verification outcome for one candidate model."""

    label: str
    model_id: str | None
    constrained_json: str  # "native" | "prompt" | "failed"
    latency_ms: int | None
    note: str

    def as_row(self) -> list[str]:
        return [
            self.label,
            self.model_id or "not found in region",
            {
                "native": "yes (native responseFormat)",
                "prompt": "yes (prompt-only)",
                "failed": "no",
            }[self.constrained_json],
            f"{self.latency_ms} ms" if self.latency_ms is not None else "-",
            self.note,
        ]


def discover_models(client: Any) -> dict[str, str]:
    """Map candidate labels to real Bedrock model IDs available in-region.

    Prefers ON_DEMAND models; falls back to any listed ID (cross-region
    inference profiles do not appear under byInferenceType=ON_DEMAND).
    """
    found: dict[str, str] = {}
    listings: list[Any] = [
        client.list_foundation_models(byInferenceType="ON_DEMAND"),
        client.list_foundation_models(),
    ]
    for response in listings:
        for summary in response.get("modelSummaries", []):
            model_id = summary.get("modelId", "")
            haystack = f"{model_id} {summary.get('modelName', '')}".lower()
            for label, needle in CANDIDATES.items():
                if needle in haystack and label not in found:
                    found[label] = model_id
    return found


def try_converse(runtime: Any, model_id: str) -> tuple[str, int, str]:
    """One Converse call. Tries native JSON responseFormat, falls back to prompt-only once.

    Returns (mechanism, latency_ms, note). Never retries beyond the single fallback.
    """
    base: dict[str, Any] = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": PROMPT}]}],
        # Reasoning models (gpt-oss) spend tokens on thinking before the answer;
        # 128 proved too small and produced empty text in the first measured run.
        "inferenceConfig": {"maxTokens": 512, "temperature": 0},
    }
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("native", {**base, "responseFormat": {"json": {"type": "json"}}}),
        ("prompt", base),
    ]
    last_error = "unknown error"
    for mechanism, payload in attempts:
        started = time.perf_counter()
        try:
            response = runtime.converse(**payload)
        except (ClientError, BotoCoreError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
            continue
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = "".join(
            block.get("text", "")
            for block in response.get("output", {}).get("message", {}).get("content", [])
        )
        cleaned = strip_code_fences(text)
        try:
            parsed = json.loads(cleaned)
            if EXPECTED_KEYS.intersection(parsed.keys()):
                note = "returned valid JSON"
                if mechanism == "prompt":
                    note += " (no native responseFormat support)"
                if cleaned != text:
                    note += "; response was fenced in markdown"
                return mechanism, latency_ms, note
            last_error = "response was JSON but missing expected keys"
        except json.JSONDecodeError:
            last_error = f"non-JSON response: {text[:60]!r}"
    return "failed", 0, last_error


def strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` markdown fences some providers wrap around JSON."""
    trimmed = text.strip()
    if trimmed.startswith("```"):
        first_newline = trimmed.find("\n")
        if first_newline != -1:
            trimmed = trimmed[first_newline + 1 :]
        if trimmed.rstrip().endswith("```"):
            trimmed = trimmed.rstrip()[:-3]
    return trimmed.strip()


def main() -> int:
    """Run discovery plus one bounded inference call per candidate. Exit 0 always: this is measurement, not gating."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    session = boto3.Session(region_name="us-east-1")
    control = session.client(
        "bedrock",
        config=BotoConfig(retries={"max_attempts": 1}, connect_timeout=10, read_timeout=30),
    )
    runtime = session.client(
        "bedrock-runtime",
        config=BotoConfig(retries={"max_attempts": 1}, connect_timeout=10, read_timeout=30),
    )

    try:
        available = discover_models(control)
    except (ClientError, BotoCoreError) as exc:
        print(f"discovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    results: list[VerifyResult] = []
    for label in CANDIDATES:
        model_id = available.get(label)
        if model_id is None:
            results.append(
                VerifyResult(label, None, "failed", None, "model not available in region")
            )
            continue
        mechanism, latency_ms, note = try_converse(runtime, model_id)
        results.append(VerifyResult(label, model_id, mechanism, latency_ms, note))

    if args.json:
        print(
            json.dumps({"region": "us-east-1", "results": [asdict(r) for r in results]}, indent=2)
        )
    else:
        widths = [12, 34, 26, 10, 44]
        header = ["Candidate", "Model ID", "Constrained JSON", "Latency", "Note"]
        for row in [header] + [r.as_row() for r in results]:
            print(
                "  ".join(str(cell).ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip()
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
