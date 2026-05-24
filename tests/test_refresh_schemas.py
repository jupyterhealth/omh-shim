"""Unit tests for tools/refresh_schemas.py helpers."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import refresh_schemas  # noqa: E402

# --- _pinned.json helpers ---


def test_read_pinned_returns_recorded_ref(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({
        "omh": {"ref": "abc123", "fetched": "2026-04-09",
                "source": "https://github.com/openmhealth/schemas"}
    }))
    assert refresh_schemas.read_pinned(pinned, family="omh") == "abc123"


def test_read_pinned_raises_when_family_missing(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({"omh": {"ref": "abc", "fetched": "x", "source": "y"}}))
    with pytest.raises(KeyError, match="ieee"):
        refresh_schemas.read_pinned(pinned, family="ieee")


def test_write_pinned_updates_ref_and_date(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({
        "omh": {"ref": "old", "fetched": "2026-01-01",
                "source": "https://github.com/openmhealth/schemas"}
    }))
    refresh_schemas.write_pinned(pinned, family="omh", new_ref="new",
                                 today="2026-05-24")
    data = json.loads(pinned.read_text())
    assert data["omh"]["ref"] == "new"
    assert data["omh"]["fetched"] == "2026-05-24"
    assert data["omh"]["source"] == "https://github.com/openmhealth/schemas"


def test_write_pinned_preserves_other_families(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({
        "omh": {"ref": "old-omh", "fetched": "2026-01-01", "source": "x"},
        "ieee": {"ref": "1.0.0", "fetched": "2026-01-01", "source": "y"}
    }))
    refresh_schemas.write_pinned(pinned, family="omh", new_ref="new-omh",
                                 today="2026-05-24")
    data = json.loads(pinned.read_text())
    assert data["omh"]["ref"] == "new-omh"
    assert data["ieee"]["ref"] == "1.0.0"  # untouched


# --- _resolve_ref ---


def test_resolve_ref_prefers_cli_arg(tmp_path, monkeypatch):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({"omh": {"ref": "from-pinned", "fetched": "x", "source": "y"}}))
    monkeypatch.setattr(refresh_schemas, "PINNED_PATH", pinned)
    ref, was_explicit = refresh_schemas._resolve_ref("from-cli", family="omh")
    assert ref == "from-cli"
    assert was_explicit is True


def test_resolve_ref_falls_back_to_pinned(tmp_path, monkeypatch):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({"omh": {"ref": "from-pinned", "fetched": "x", "source": "y"}}))
    monkeypatch.setattr(refresh_schemas, "PINNED_PATH", pinned)
    ref, was_explicit = refresh_schemas._resolve_ref(None, family="omh")
    assert ref == "from-pinned"
    assert was_explicit is False


def test_resolve_ref_exits_when_pinned_missing(tmp_path, monkeypatch):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({}))  # no families
    monkeypatch.setattr(refresh_schemas, "PINNED_PATH", pinned)
    with pytest.raises(SystemExit, match="omh.*ref"):
        refresh_schemas._resolve_ref(None, family="omh")


# --- walk_refs ---


def test_walk_refs_collects_relative_refs():
    schema = {"$ref": "unit-value-1.x.json",
              "properties": {"x": {"$ref": "time-frame-1.x.json"},
                             "y": {"$ref": "#/definitions/foo"}}}  # ignored
    assert refresh_schemas.walk_refs(schema) == {
        "unit-value-1.x.json", "time-frame-1.x.json"}


def test_walk_refs_handles_nested():
    schema = {"allOf": [{"$ref": "a.json"}, {"items": {"$ref": "b.json"}}]}
    assert refresh_schemas.walk_refs(schema) == {"a.json", "b.json"}
