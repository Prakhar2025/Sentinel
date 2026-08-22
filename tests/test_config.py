"""Tests for typed application settings."""

from __future__ import annotations

import importlib

import pytest

from sentinel.config import Settings, get_settings


def test_defaults_match_design_documents() -> None:
    """Model routing and threshold defaults must match docs 03 and 05.

    IDs are the live Bedrock IDs measured on 2026-08-22 (docs/08 appendix).
    """
    settings = Settings()
    assert settings.extraction_model == "amazon.nova-lite-v1:0"
    assert settings.explanation_model == "openai.gpt-oss-120b-1:0"
    assert settings.fallback1_explanation_model == "openai.gpt-oss-20b-1:0"
    assert settings.fallback2_explanation_model == "zai.glm-5"
    assert settings.aws_region == "us-east-1"
    assert (settings.review_threshold, settings.block_threshold) == (35, 70)


def test_settings_singleton_is_cached() -> None:
    """get_settings must return the same instance across calls."""
    assert get_settings() is get_settings()


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables must override defaults without touching .env."""
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.delenv("SENTINEL_API_KEY", raising=False)
    settings = Settings()
    assert settings.aws_region == "ap-south-1"


def test_import_surface() -> None:
    """Package exposes a version string for the audit trail."""
    import sentinel

    assert isinstance(sentinel.__version__, str)
    assert importlib.import_module("sentinel.config") is not None
