"""LIVE Bedrock tests. These cost real money and never run in CI.

Run manually when needed:
    .venv/Scripts/python -m pytest -m bedrock --no-cov -q

Budget: at most 6 bounded calls (3 chain models x 1 smoke + 1-2 full
explanations). Nowhere near the $20 soft budget.
"""

from __future__ import annotations

import pytest

from sentinel.config import get_settings
from sentinel.explain import CostLog, ExplanationOut, ExplanationService
from sentinel.llm import BedrockClient

pytestmark = pytest.mark.bedrock


@pytest.fixture(scope="module")
def client() -> BedrockClient:
    settings = get_settings()
    return BedrockClient(
        region=settings.aws_region,
        timeout_seconds=settings.bedrock_timeout_seconds,
    )


@pytest.mark.parametrize(
    "model_attr",
    ["explanation_model", "fallback1_explanation_model", "fallback2_explanation_model"],
)
def test_chain_model_returns_text(client: BedrockClient, model_attr: str) -> None:
    settings = get_settings()
    model_id = getattr(settings, model_attr)
    response = client.converse(
        model_id=model_id,
        system="Reply with the single word: ready",
        user="ready?",
        max_tokens=512,
    )
    assert response.text.strip()
    assert response.input_tokens > 0


def test_full_explanation_chain(tmp_path, client: BedrockClient) -> None:
    settings = get_settings()
    cost_log = CostLog(tmp_path / "live_cost.jsonl")
    service = ExplanationService(
        converse=client.converse,
        chain=[settings.explanation_model],
        max_tokens=settings.explanation_max_tokens,
        on_cost=cost_log,
    )
    payload = {
        "event_id": "live-1",
        "score": 78,
        "verdict": "BLOCK_REC",
        "reason_codes": ["RNG_DEVICE_FANOUT", "RNG_TAINT_LINK"],
        "features": {"device_identity_ratio": 6.0, "cross_merchant_fanout": 4},
        "evidence": {
            "linked_merchants": ["mcht_1", "mcht_2", "mcht_3", "mcht_4"],
            "shared_devices": [{"device_id": "dev_x", "linked_identities": 6}],
            "taint_path": ["cust_a", "dev_x", "cust_b"],
        },
        "amount_paise": 120_000,
    }
    result = service.explain(payload)
    assert result.status == "DONE"
    assert result.model_used == settings.explanation_model
    parsed = ExplanationOut.model_validate_json(result.narrative or "")
    assert parsed.summary
    assert parsed.risk_factors
    print(cost_log.summary())
