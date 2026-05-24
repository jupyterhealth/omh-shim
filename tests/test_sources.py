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
    "heart_rate_variability",
    "oxygen_saturation",
    "step_count",
    "sleep_duration",
    "sleep_episode",
    "physical_activity",
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


def test_oura_hrv_rejects_normalized_score():
    """Oura's daily_readiness contributors.hrv_balance is a 0-100 score, not ms."""
    sample = {"day": "2026-04-09", "score": 85, "contributors": {"hrv_balance": 70}}
    with pytest.raises(ConversionError, match="rmssd"):
        convert(source="oura_raw", data_type="heart_rate_variability", sample=sample)


def test_oura_sleep_episode_nap_is_not_main_sleep():
    sample = {
        "id": "nap-1",
        "bedtime_start": "2026-04-09T13:00:00+00:00",
        "bedtime_end": "2026-04-09T13:45:00+00:00",
        "total_sleep_duration": 2400,
        "type": "nap",
    }
    result = convert(source="oura_raw", data_type="sleep_episode", sample=sample)
    assert result["body"]["is_main_sleep"] is False


def test_oura_physical_activity_omits_optional_fields_when_absent():
    result = convert(
        source="oura_raw",
        data_type="physical_activity",
        sample={"day": "2026-04-09"},
        tz=UTC,
    )
    assert "distance" not in result
    assert "kcal_burned" not in result


def test_ow_step_count_accepts_timeseries_shape():
    """TimeSeriesSample with type=steps — 1-minute interval ending at timestamp."""
    sample = {
        "timestamp": "2026-04-09T08:30:00+00:00",
        "type": "steps",
        "value": 12,
        "unit": "steps",
    }
    result = convert(source="ow_normalized", data_type="step_count", sample=sample)
    body = result["body"]
    assert body["step_count"] == {"value": 12, "unit": "steps"}
    interval = body["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T08:29:00Z"
    assert interval["end_date_time"] == "2026-04-09T08:30:00Z"


def test_ow_step_count_rejects_unknown_shape():
    with pytest.raises(ConversionError):
        convert(
            source="ow_normalized",
            data_type="step_count",
            sample={"foo": "bar"},
            tz=UTC,
        )


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
        sample={"date": "2026-04-09", "steps": 100},
        tz=UTC,
    )
    body = result["body"]
    assert "distance" not in body
    assert "kcal_burned" not in body
    assert body["activity_name"] == "daily activity summary"
