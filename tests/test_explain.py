"""Stub-based tests for the LLM layer (no network, no spend)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel.explain import CostLog, ExplanationOut, ExplanationService, _user_prompt
from sentinel.llm import LLMResponse, estimate_cost, strip_code_fences

CHAIN = ["model-a", "model-b", "model-c"]

VALID = json.dumps(
    {
        "summary": "Device shared by six identities across four merchants.",
        "risk_factors": ["device fan-out", "taint path"],
        "recommended_action": "Hold fulfilment and verify the customer.",
    }
)


def reply(model_id: str, text: str, latency_ms: int = 500) -> LLMResponse:
    return LLMResponse(
        text=text,
        stop_reason="end_turn",
        latency_ms=latency_ms,
        input_tokens=400,
        output_tokens=150,
        model_id=model_id,
    )


class FakeConverse:
    """Scripted converse callable for deterministic tests."""

    def __init__(self, script: list[LLMResponse | Exception]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, int]] = []

    def __call__(self, model_id: str, system: str, user: str, max_tokens: int):
        self.calls.append((model_id, max_tokens))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def payload() -> dict:
    return {
        "event_id": "e1",
        "score": 78,
        "verdict": "BLOCK_REC",
        "reason_codes": ["RNG_DEVICE_FANOUT"],
        "features": {"device_identity_ratio": 6.0},
        "evidence": {"linked_merchants": ["m1", "m2"]},
        "amount_paise": 120_000,
    }


class TestFenceStripping:
    def test_strips_json_fences(self) -> None:
        assert strip_code_fences(f"```json\n{VALID}\n```") == VALID

    def test_plain_json_untouched(self) -> None:
        assert strip_code_fences(VALID) == VALID

    def test_empty(self) -> None:
        assert strip_code_fences("") == ""


class TestExplanationService:
    def test_happy_path_first_model(self) -> None:
        fake = FakeConverse([reply("model-a", VALID)])
        service = ExplanationService(converse=fake, chain=CHAIN)
        result = service.explain(payload())
        assert result.status == "DONE"
        assert result.model_used == "model-a"
        assert result.calls_made == 1
        parsed = ExplanationOut.model_validate_json(result.narrative or "")
        assert parsed.summary.startswith("Device shared")

    def test_fenced_json_is_accepted(self) -> None:
        fake = FakeConverse([reply("model-a", f"```json\n{VALID}\n```")])
        service = ExplanationService(converse=fake, chain=CHAIN)
        assert service.explain(payload()).status == "DONE"

    def test_malformed_then_retry_with_doubled_budget(self) -> None:
        fake = FakeConverse([reply("model-a", "I think this is..."), reply("model-a", VALID)])
        service = ExplanationService(converse=fake, chain=CHAIN, max_tokens=512)
        result = service.explain(payload())
        assert result.status == "DONE"
        assert fake.calls[0][1] == 512
        assert fake.calls[1][1] == 1024  # doubled on the stricter retry

    def test_timeout_falls_through_chain_without_retry(self) -> None:
        fake = FakeConverse([TimeoutError("t1"), TimeoutError("t2"), reply("model-c", VALID)])
        service = ExplanationService(converse=fake, chain=CHAIN)
        result = service.explain(payload())
        assert result.status == "DONE"
        assert result.model_used == "model-c"
        assert result.calls_made == 3

    def test_all_failures_end_as_skipped(self) -> None:
        fake = FakeConverse(
            [
                reply("model-a", "garbage"),
                reply("model-a", "still garbage"),
                TimeoutError("t2"),
                TimeoutError("t3"),
            ]
        )
        service = ExplanationService(converse=fake, chain=CHAIN)
        result = service.explain(payload())
        assert result.status == "SKIPPED"
        assert result.narrative is None
        assert result.calls_made == 4  # bounded: 2 + 1 + 1

    def test_empty_reasoning_response_treated_as_malformed(self) -> None:
        fake = FakeConverse([reply("model-a", ""), reply("model-a", VALID)])
        service = ExplanationService(converse=fake, chain=CHAIN)
        assert service.explain(payload()).status == "DONE"
        assert fake.calls[1][1] > fake.calls[0][1]

    def test_trailing_text_after_json_is_rescued(self) -> None:
        fake = FakeConverse([reply("model-a", VALID + "\nHope this helps!")])
        service = ExplanationService(converse=fake, chain=CHAIN)
        assert service.explain(payload()).status == "DONE"


class TestCostLogging:
    def test_cost_records_flow_to_sink(self, tmp_path: Path) -> None:
        log = CostLog(tmp_path / "costs.jsonl")
        fake = FakeConverse([reply("model-a", VALID)])
        ExplanationService(converse=fake, chain=CHAIN, on_cost=log).explain(payload())
        assert log.calls == 1
        assert log.total_estimate_usd > 0
        lines = (tmp_path / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[0])["purpose"] == "explanation"

    def test_estimate_cost_math(self) -> None:
        cost = estimate_cost("openai.gpt-oss-120b-1:0", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.75)


def test_user_prompt_contains_evidence_not_pii_payload() -> None:
    prompt = _user_prompt(payload())
    assert "RNG_DEVICE_FANOUT" in prompt
    assert "amount_paise" in prompt
