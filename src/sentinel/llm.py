"""Bedrock client wrapper (docs/03, docs/08 measured appendix).

Security and budget rules baked in:
- Credentials come ONLY from the boto3 default chain; this module never
  sees or stores key material.
- Retries are disabled at the botocore level (max_attempts=1); retry
  policy belongs to the ExplanationService and is explicitly bounded.
- Every call's token usage is recorded for the cost log.

Phase 0 measurements this module encodes:
- No candidate model supports native responseFormat JSON; responses may
  be wrapped in markdown fences (strip_code_fences is mandatory).
- gpt-oss models are reasoning models: they need a generous maxTokens
  budget or they return empty text with stopReason "max_tokens".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import boto3
from botocore.config import Config as BotoConfig

# Rough per-million-token price estimates (USD) for the cost log. Real
# spend is what AWS billing reports; these are for visibility only and
# are labeled as estimates everywhere they appear.
PRICE_PER_MTOKEN_ESTIMATE: dict[str, tuple[float, float]] = {
    "openai.gpt-oss-120b-1:0": (0.15, 0.60),
    "openai.gpt-oss-20b-1:0": (0.05, 0.20),
    "zai.glm-5": (0.20, 0.60),
    "amazon.nova-lite-v1:0": (0.06, 0.24),
}
DEFAULT_PRICE = (0.20, 0.60)


@dataclass(slots=True, frozen=True)
class LLMResponse:
    """One Converse call result."""

    text: str
    stop_reason: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    model_id: str


@dataclass(slots=True, frozen=True)
class CostRecord:
    """One billed call, written to the cost log."""

    model_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    purpose: str
    cost_estimate_usd: float

    def as_json(self) -> dict[str, float | int | str]:
        return {
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "purpose": self.purpose,
            "cost_estimate_usd": round(self.cost_estimate_usd, 6),
        }


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost of one call (visibility only, not billing)."""
    price_in, price_out = PRICE_PER_MTOKEN_ESTIMATE.get(model_id, DEFAULT_PRICE)
    return (input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out


def strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` fences some Bedrock models wrap around JSON."""
    trimmed = text.strip()
    if trimmed.startswith("```"):
        first_newline = trimmed.find("\n")
        if first_newline != -1:
            trimmed = trimmed[first_newline + 1 :]
        stripped = trimmed.rstrip()
        if stripped.endswith("```"):
            trimmed = stripped[:-3]
    return trimmed.strip()


class ConverseFn(Protocol):
    """Callable shape of BedrockClient.converse (injectable for tests)."""

    def __call__(self, model_id: str, system: str, user: str, max_tokens: int) -> LLMResponse: ...


class BedrockClient:
    """Thin Converse wrapper over the default AWS credential chain."""

    def __init__(self, region: str, timeout_seconds: float) -> None:
        self._client = boto3.Session(region_name=region).client(
            "bedrock-runtime",
            config=BotoConfig(
                retries={"max_attempts": 1},
                connect_timeout=10,
                read_timeout=timeout_seconds,
            ),
        )

    def converse(self, model_id: str, system: str, user: str, max_tokens: int) -> LLMResponse:
        """One Converse call. Raises on transport/timeout errors (no retries)."""
        import time

        started = time.perf_counter()
        response: dict[str, Any] = self._client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = "".join(
            block.get("text", "")
            for block in response.get("output", {}).get("message", {}).get("content", [])
        )
        usage = response.get("usage", {})
        return LLMResponse(
            text=text,
            stop_reason=str(response.get("stopReason", "unknown")),
            latency_ms=latency_ms,
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            model_id=model_id,
        )


def build_client_factory(region: str, timeout_seconds: float) -> Callable[[], BedrockClient]:
    """Factory so tests can inject fakes at the same seam."""

    def _factory() -> BedrockClient:
        return BedrockClient(region=region, timeout_seconds=timeout_seconds)

    return _factory
