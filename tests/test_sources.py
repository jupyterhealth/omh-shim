"""Parameterized tests for all source converters.

One fixture pair per (source, data_type) under ``tests/fixtures/<source>/``.
``convert()`` validates each output against its target schema by default,
so a green test is also a passing schema validation.

Daily types are called with ``tz=UTC`` to match the UTC-anchored expected
fixtures; the non-UTC behavior is covered in ``test_core.py``.
"""

import json
from datetime import UTC
from pathlib import Path

import pytest

from omh_shim import ConversionError, convert

FIXTURES = Path(__file__).parent / "fixtures"

DATA_TYPES = [
    "heart_rate",
    "oxygen_saturation",
    "sleep_duration",
    "sleep_episode",
    "physical_activity",
    "respiratory_rate",
    "body_weight",
]
SOURCES = ["oura_raw", "ow_normalized"]


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("data_type", DATA_TYPES)
def test_converter_matches_expected(source, data_type):
    fixture_dir = FIXTURES / source
    sample = json.loads((fixture_dir / f"{data_type}_input.json").read_text())
    expected = json.loads((fixture_dir / f"{data_type}_expected.json").read_text())
    result = convert(source=source, data_type=data_type, sample=sample, tz=UTC)
    assert "header" in result, "convert() must always return {header, body}"
    assert "body" in result
    assert result["body"] == expected


# --- source-specific edge cases ---


_OURA_SLEEP_BOUNDS = {
    "bedtime_start": "2026-04-09T13:00:00+00:00",
    "bedtime_end": "2026-04-09T13:45:00+00:00",
}


@pytest.mark.parametrize("sleep_type,expected", [
    ("sleep", True), ("long_sleep", True), ("late_nap", False), ("rest", False),
])
def test_oura_sleep_episode_is_main_sleep_follows_public_sleep_type(sleep_type, expected):
    """Oura v2 PublicSleepType is deleted|sleep|long_sleep|late_nap|rest; there is no 'nap'."""
    sample = {**_OURA_SLEEP_BOUNDS, "total_sleep_duration": 2400, "type": sleep_type}
    result = convert(source="oura_raw", data_type="sleep_episode", sample=sample)
    assert result["body"]["is_main_sleep"] is expected


@pytest.mark.parametrize("sleep_type", ["deleted", "nap"])
def test_oura_sleep_episode_rejects_deleted_and_unknown_types(sleep_type):
    with pytest.raises(ConversionError, match="type"):
        convert(source="oura_raw", data_type="sleep_episode",
                sample={**_OURA_SLEEP_BOUNDS, "type": sleep_type})


def test_oura_sleep_episode_omits_is_main_sleep_when_type_absent():
    body = convert(source="oura_raw", data_type="sleep_episode", sample=_OURA_SLEEP_BOUNDS)["body"]
    assert "is_main_sleep" not in body


def test_oura_sleep_duration_rejects_deleted_record():
    """A deleted Oura sleep must not become an Observation under any sleep-derived data type."""
    with pytest.raises(ConversionError, match="deleted"):
        convert(source="oura_raw", data_type="sleep_duration",
                sample={**_OURA_SLEEP_BOUNDS, "total_sleep_duration": 2400, "type": "deleted"})


def test_oura_physical_activity_omits_optional_fields_when_absent():
    result = convert(
        source="oura_raw",
        data_type="physical_activity",
        sample={"day": "2026-04-09"},
        tz=UTC,
    )
    body = result["body"]
    assert "distance" not in body
    assert "kcal_burned" not in body
    assert "base_movement_quantity" not in body


def test_oura_oxygen_saturation_rejects_missing_spo2_percentage():
    with pytest.raises(ConversionError, match="spo2_percentage"):
        convert(source="oura_raw", data_type="oxygen_saturation",
                sample={"day": "2026-04-09"}, tz=UTC)


def test_oura_oxygen_saturation_rejects_flat_value():
    """spo2_percentage must be a nested object with 'average', not a bare number."""
    with pytest.raises(ConversionError, match="spo2_percentage"):
        convert(source="oura_raw", data_type="oxygen_saturation",
                sample={"day": "2026-04-09", "spo2_percentage": 96.5}, tz=UTC)


def test_ow_physical_activity_omits_optional_fields_when_absent():
    result = convert(
        source="ow_normalized",
        data_type="physical_activity",
        sample={"date": "2026-04-09"},
        tz=UTC,
    )
    body = result["body"]
    assert "distance" not in body
    assert "kcal_burned" not in body
    assert "base_movement_quantity" not in body
    assert body["activity_name"] == "daily activity summary"


def test_ow_sleep_episode_null_stages_omits_stage_fields():
    """OW serialises ``stages: null`` when a provider reports no staging."""
    sample = {
        "start_time": "2026-04-09T22:30:00Z",
        "end_time": "2026-04-10T06:45:00Z",
        "stages": None,
        "is_nap": False,
    }
    body = convert(source="ow_normalized", data_type="sleep_episode", sample=sample)["body"]
    for key in ("light_sleep_duration", "deep_sleep_duration", "rem_sleep_duration",
                "wake_after_sleep_onset"):
        assert key not in body
    assert body["is_main_sleep"] is True


def test_ow_sleep_episode_nap_is_not_main_sleep():
    sample = {
        "start_time": "2026-04-09T13:00:00Z",
        "end_time": "2026-04-09T13:45:00Z",
        "sleep_duration_seconds": 2400,
        "is_nap": True,
    }
    result = convert(source="ow_normalized", data_type="sleep_episode", sample=sample)
    assert result["body"]["is_main_sleep"] is False


def test_ow_sleep_duration_requires_duration_minutes():
    """ieee:total-sleep-time requires total_sleep_time; a null day cannot be converted."""
    with pytest.raises(ConversionError, match="duration_minutes"):
        convert(source="ow_normalized", data_type="sleep_duration",
                sample={"date": "2026-04-09", "duration_minutes": None}, tz=UTC)


def test_ow_blood_glucose_matches_expected():
    """blood_glucose is ow_normalized-only, so it cannot join the SOURCES cross product."""
    fixture_dir = FIXTURES / "ow_normalized"
    sample = json.loads((fixture_dir / "blood_glucose_input.json").read_text())
    expected = json.loads((fixture_dir / "blood_glucose_expected.json").read_text())
    result = convert(source="ow_normalized", data_type="blood_glucose", sample=sample)
    assert result["body"] == expected


def test_oura_respiratory_rate_requires_average_breath():
    with pytest.raises(ConversionError, match="average_breath"):
        convert(source="oura_raw", data_type="respiratory_rate",
                sample={**_OURA_SLEEP_BOUNDS, "average_breath": None})


def test_oura_body_weight_requires_caller_timestamp():
    """Oura personal_info is a profile with no measurement time; the caller stamps one."""
    with pytest.raises(ConversionError, match="timestamp"):
        convert(source="oura_raw", data_type="body_weight", sample={"id": "user-1", "weight": 72.5})
