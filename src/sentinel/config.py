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
    bedrock_timeout_seconds: float = 5.0

    # Verdict thresholds (locked at Phase 3 calibration; doc 05)
    review_threshold: int = 35
    block_threshold: int = 70

    # Service wiring
    model_config_path: str = "evaluation/model_config.json"
    spool_dir: str = "data/spool"


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton settings instance."""
    return Settings()
