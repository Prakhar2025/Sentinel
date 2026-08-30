"""Tests for the system-story parsers (real docs in /docs)."""

from __future__ import annotations

from pathlib import Path

from sentinel.story import parse_adrs, parse_threats, parse_what_broke, system_payload

DOCS = Path(__file__).resolve().parents[1] / "docs"


def test_what_broke_parses_real_doc() -> None:
    entries = parse_what_broke(DOCS / "what-broke.md")
    assert len(entries) >= 10
    first = entries[0]
    assert set(first) == {"date", "phase", "broke", "cause", "fix"}
    assert first["broke"]


def test_adrs_parse_real_doc() -> None:
    adrs = parse_adrs(DOCS / "18-adrs.md")
    assert len(adrs) == 6
    assert adrs[0]["id"] == "ADR-001"
    assert adrs[-1]["id"] == "ADR-006"
    assert all(adr["decision"] for adr in adrs)


def test_threats_parse_real_doc() -> None:
    threats = parse_threats(DOCS / "16-threat-model.md")
    assert len(threats) == 10
    assert threats[0]["class"] == "Spoofing"
    assert all(t["control"] for t in threats)


def test_system_payload_shape() -> None:
    payload = system_payload(DOCS, None)
    assert payload["what_broke"]
    assert payload["decisions"]
    assert payload["threats"]
    assert len(payload["components"]) == 7
    assert len(payload["disclosures"]) == 2
    assert payload["headline"]["precision"] is None


def test_parsers_skip_garbage(tmp_path: Path) -> None:
    (tmp_path / "what-broke.md").write_text("not a table\n| a | b |\n", encoding="utf-8")
    assert parse_what_broke(tmp_path / "what-broke.md") == []
    assert parse_adrs(tmp_path / "absent.md") == []
    assert parse_threats(tmp_path / "absent.md") == []
