"""Application settings.

All configuration comes from environment variables (12-factor), optionally
loaded from a local .env file. AWS credentials are NEVER stored here: the
boto3 default credential chain is the only source of AWS authentication.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings with safe defaults for local development."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # API authentication (demo scope; doc 06/07 two-key model)
    sentinel_api_key: str = "dev-sentinel-key"
    sentinel_admin_api_key: str = "dev-admin-key"

    # AWS / Bedrock routing (doc 03). IDs verified against the live control
    # plane in us-east-1 on 2026-08-22; see the docs/08 appendix for latency
    # and constrained-JSON measurements. Llama 3.3 70B is listed but not
    # invocable via its base model ID in this region, so it stays out of the
    # chain and GLM-5 is the last fallback.
    aws_region: str = "us-east-1"
    extraction_model: str = "amazon.nova-lite-v1:0"
    explanation_model: str = "openai.gpt-oss-120b-1:0"
    fallback1_explanation_model: str = "openai.gpt-oss-20b-1:0"
    fallback2_explanation_model: str = "zai.glm-5"
    # LLM behavior. Timeout default raised from 5s to 30s after the Phase 0
    # measurement: gpt-oss-120b took 7.2s on a trivial prompt (reasoning
    # overhead), so 5s would timeout every real explanation. Explanations
    # are async by design, so the larger bound costs nothing user-facing.
    bedrock_timeout_seconds: float = 30.0
    explanation_max_tokens: int = 1024

    # Verdict thresholds (locked at Phase 3 calibration; doc 05)
    review_threshold: int = 35
    block_threshold: int = 70

    # Service wiring
    model_config_path: str = "evaluation/model_config.json"
    challenger_model_path: str = "evaluation/challenger.pkl"
    spool_dir: str = "data/spool"
    console_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton settings instance."""
    return Settings()
