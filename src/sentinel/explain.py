"""Explanation service (docs/03 LLM layer, docs/05 "where the LLM sits").

The LLM NEVER scores; it turns an existing verdict's evidence into a
structured, validated narrative. Contract:

- Chain: explanation model -> fallback1 -> fallback2 (docs/03 routing).
- Per model: one call; a single stricter retry (with a doubled token
  budget) only when the response parses as malformed JSON. Timeouts and
  throttles move to the next model immediately; no retry storms.
- Output must validate against the ExplanationOut schema (pydantic =
  the published JSON schema). Failure everywhere -> SKIPPED and the
  verdict stands unchanged (degradation ladder, doc 10).
- Every call is cost-logged through the injected sink.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .llm import CostRecord, LLMResponse, estimate_cost, strip_code_fences

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a fraud-analysis explainer for a payment risk system. You "
    "receive one verdict's evidence and must respond with ONLY a JSON "
    "object, no markdown, with exactly these keys: "
    '"summary" (string, at most 60 words, plain language for a merchant '
    'risk analyst), "risk_factors" (array of 1-5 short strings), '
    '"recommended_action" (one sentence). Never invent evidence that is '
    "not in the input."
)

RETRY_SYSTEM_PROMPT = (
    "Your previous response was not valid JSON and it MUST be. Respond "
    "with ONLY a raw JSON object. No markdown fences, no commentary, no "
    "code blocks. Keys: summary, risk_factors, recommended_action."
)


class ExplanationOut(BaseModel):
    """The published output schema for explanations."""

    summary: str
    risk_factors: list[str]
    recommended_action: str


@dataclass(slots=True)
class ExplanationResult:
    """Outcome of one explanation attempt."""

    status: str  # DONE | FAILED | SKIPPED
    model_used: str | None
    narrative: str | None  # validated JSON text
    calls_made: int
    latency_ms: int


class ExplanationService:
    """Bounded fallback-chain explanation generator."""

    def __init__(
        self,
        converse: Callable[[str, str, str, int], LLMResponse],
        chain: list[str],
        max_tokens: int = 1024,
        on_cost: Callable[[CostRecord], None] | None = None,
    ) -> None:
        self._converse = converse
        self._chain = chain
        self._max_tokens = max_tokens
        self._on_cost = on_cost

    def explain(self, verdict_payload: dict[str, Any]) -> ExplanationResult:
        """Generate one narrative; never raises, never retries unbounded."""
        user = _user_prompt(verdict_payload)
        calls = 0
        total_latency = 0
        for position, model_id in enumerate(self._chain):
            for attempt, system in enumerate(
                (SYSTEM_PROMPT, RETRY_SYSTEM_PROMPT) if position == 0 else (SYSTEM_PROMPT,)
            ):
                budget = self._max_tokens * (2**attempt)
                try:
                    response = self._converse(model_id, system, user, budget)
                except Exception as exc:  # transport/throttle: next model, no retry
                    logger.warning("model %s unavailable: %s", model_id, exc)
                    calls += 1
                    break
                calls += 1
                total_latency += response.latency_ms
                self._record_cost(response, "explanation")
                parsed = self._parse(response)
                if parsed is not None:
                    return ExplanationResult(
                        status="DONE",
                        model_used=model_id,
                        narrative=parsed.model_dump_json(),
                        calls_made=calls,
                        latency_ms=total_latency,
                    )
        return ExplanationResult(
            status="SKIPPED",
            model_used=None,
            narrative=None,
            calls_made=calls,
            latency_ms=total_latency,
        )

    def _parse(self, response: LLMResponse) -> ExplanationOut | None:
        """Validate one response, honoring the empty-reasoning case."""
        if not response.text.strip():
            # gpt-oss burned the whole budget reasoning (Phase 0 finding);
            # a bigger-budget retry is the correct response.
            return None
        cleaned = strip_code_fences(response.text)
        try:
            return ExplanationOut.model_validate_json(cleaned)
        except ValidationError:
            try:
                # Some models emit trailing text after the JSON object.
                start, end = cleaned.find("{"), cleaned.rfind("}")
                if start != -1 and end > start:
                    return ExplanationOut.model_validate_json(cleaned[start : end + 1])
            except ValidationError:
                return None
            return None

    def _record_cost(self, response: LLMResponse, purpose: str) -> None:
        if self._on_cost is None:
            return
        self._on_cost(
            CostRecord(
                model_id=response.model_id,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                purpose=purpose,
                cost_estimate_usd=estimate_cost(
                    response.model_id, response.input_tokens, response.output_tokens
                ),
            )
        )


def _user_prompt(verdict_payload: dict[str, Any]) -> str:
    """Render the evidence bundle for the model (bounded, no PII beyond ids)."""
    evidence = {
        "score": verdict_payload.get("score"),
        "verdict": verdict_payload.get("verdict"),
        "reason_codes": verdict_payload.get("reason_codes", []),
        "features": verdict_payload.get("features", {}),
        "evidence": verdict_payload.get("evidence", {}),
        "amount_paise": verdict_payload.get("amount_paise"),
    }
    return "Explain this fraud verdict for a risk analyst.\n" + json.dumps(evidence, default=str)


class CostLog:
    """Appends cost records as JSONL and keeps a running total."""

    def __init__(self, path: Any) -> None:
        from pathlib import Path

        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.total_estimate_usd = 0.0
        self.calls = 0

    def __call__(self, record: CostRecord) -> None:
        self.calls += 1
        self.total_estimate_usd += record.cost_estimate_usd
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_json()) + "\n")

    def summary(self) -> str:
        return f"{self.calls} calls, estimated ${self.total_estimate_usd:.4f} (estimate only; billing is authoritative)"


__all__ = [
    "CostLog",
    "ExplanationOut",
    "ExplanationResult",
    "ExplanationService",
]
