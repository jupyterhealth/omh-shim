"""Core behavior tests for omh-shim.

Tests are written as specification — they assert correct behavior, and the
code must pass them. Not the other way around.
"""

from datetime import UTC
from zoneinfo import ZoneInfo

import pytest

from omh_shim import SCHEMA_IDS, ConversionError, ValidationError, convert
from omh_shim._helpers import day_interval, parse_datetime
from omh_shim._schema_loader import HEADER_SCHEMA_ID

# --- public API ---


def test_convert_unknown_pair_raises_conversion_error():
    with pytest.raises(ConversionError):
        convert(source="ow_normalized", data_type="not_a_real_type", sample={})


# --- parse_datetime ---


def test_parse_datetime_rejects_naive():
    with pytest.raises(ConversionError, match="timezone"):
        parse_datetime("2026-04-09T08:30:00")


def test_parse_datetime_accepts_utc_Z():
    dt = parse_datetime("2026-04-09T08:30:00Z")
    assert dt.utcoffset().total_seconds() == 0


def test_parse_datetime_accepts_offset():
    dt = parse_datetime("2026-04-09T08:30:00-07:00")
    assert dt.utcoffset().total_seconds() == -7 * 3600


def test_parse_datetime_rejects_garbage():
    with pytest.raises(ConversionError):
        parse_datetime("not a datetime")


# --- day_interval ---


def test_day_interval_requires_tz():
    with pytest.raises(ConversionError, match="timezone"):
        day_interval("2026-04-09", tz=None)


def test_day_interval_utc():
    assert day_interval("2026-04-09", tz=UTC) == {
        "start_date_time": "2026-04-09T00:00:00Z",
        "end_date_time": "2026-04-10T00:00:00Z",
    }


def test_day_interval_non_utc():
    assert day_interval("2026-04-09", tz=ZoneInfo("America/Los_Angeles")) == {
        "start_date_time": "2026-04-09T00:00:00-07:00",
        "end_date_time": "2026-04-10T00:00:00-07:00",
    }


def test_day_interval_spring_forward():
    """March 8 2026 LA: PST -> PDT. Offset changes from -08 to -07."""
    assert day_interval("2026-03-08", tz=ZoneInfo("America/Los_Angeles")) == {
        "start_date_time": "2026-03-08T00:00:00-08:00",
        "end_date_time": "2026-03-09T00:00:00-07:00",
    }


def test_day_interval_fall_back():
    """Nov 1 2026 LA: PDT -> PST. Offset changes from -07 to -08."""
    assert day_interval("2026-11-01", tz=ZoneInfo("America/Los_Angeles")) == {
        "start_date_time": "2026-11-01T00:00:00-07:00",
        "end_date_time": "2026-11-02T00:00:00-08:00",
    }


# --- convert() error wrapping ---


def test_convert_wraps_missing_field():
    with pytest.raises(ConversionError):
        convert(source="oura_raw", data_type="heart_rate", sample={})


def test_convert_wraps_type_error():
    with pytest.raises(ConversionError):
        convert(
            source="oura_raw",
            data_type="heart_rate",
            sample={"bpm": None, "timestamp": "2026-04-09T08:00:00Z"},
        )


# --- tz required for daily types ---


DAILY_CASES = [
    ("oura_raw", "step_count", {"day": "2026-04-09", "steps": 100}),
    ("oura_raw", "physical_activity", {"day": "2026-04-09"}),
    ("oura_raw", "oxygen_saturation", {"day": "2026-04-09", "spo2_percentage": {"average": 96.5}}),
    ("ow_normalized", "step_count", {"date": "2026-04-09", "steps": 100}),
    ("ow_normalized", "physical_activity", {"date": "2026-04-09"}),
    ("ow_normalized", "sleep_duration", {"date": "2026-04-09", "sleep_total_duration_minutes": 480}),
]


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_require_tz(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_accept_utc(source, data_type, sample):
    result = convert(source=source, data_type=data_type, sample=sample, tz=UTC)
    body = result["body"]
    interval = body["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T00:00:00Z"


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_respect_non_utc_tz(source, data_type, sample):
    result = convert(source=source, data_type=data_type, sample=sample,
                     tz=ZoneInfo("America/Los_Angeles"))
    body = result["body"]
    interval = body["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T00:00:00-07:00"


# --- naive datetime rejection across all timestamp converters ---


NAIVE_CASES = [
    ("oura_raw", "heart_rate", {"bpm": 72, "timestamp": "2026-04-09T08:30:00"}),
    ("oura_raw", "heart_rate_variability", {"rmssd": 45.0, "timestamp": "2026-04-09T08:30:00"}),
    ("oura_raw", "sleep_duration", {"total_sleep_duration": 27000,
     "bedtime_start": "2026-04-09T22:00:00", "bedtime_end": "2026-04-10T06:00:00"}),
    ("oura_raw", "sleep_episode", {"bedtime_start": "2026-04-09T22:00:00",
     "bedtime_end": "2026-04-10T06:00:00"}),
    ("ow_normalized", "heart_rate", {"timestamp": "2026-04-09T08:30:00",
     "type": "heart_rate", "value": 72}),
    ("ow_normalized", "heart_rate_variability", {"timestamp": "2026-04-09T08:30:00",
     "type": "heart_rate_variability", "value": 45.0}),
    ("ow_normalized", "sleep_episode", {"bedtime_start": "2026-04-09T22:00:00",
     "bedtime_end": "2026-04-10T06:00:00"}),
    ("ow_normalized", "step_count", {"timestamp": "2026-04-09T08:30:00",
     "type": "steps", "value": 10}),
]


@pytest.mark.parametrize("source,data_type,sample", NAIVE_CASES)
def test_rejects_naive_datetime(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


# --- converters raise ConversionError directly (not raw KeyError) ---


def test_oura_hrv_rejects_normalized_score_directly():
    from omh_shim.sources import oura_raw
    with pytest.raises(ConversionError, match="rmssd"):
        oura_raw.heart_rate_variability(
            {"day": "2026-04-09", "contributors": {"hrv_balance": 70}}, tz=None)


def test_ow_step_count_rejects_unknown_shape_directly():
    from omh_shim.sources import ow_normalized
    with pytest.raises(ConversionError):
        ow_normalized.step_count({"foo": "bar"}, tz=UTC)


# --- schema validation ---


def test_validation_passes_valid():
    from omh_shim._validate import validate_output
    validate_output(
        {"heart_rate": {"value": 72, "unit": "beats/min"},
         "effective_time_frame": {"date_time": "2026-04-09T08:00:00Z"}},
        "omh:heart-rate:2.0",
    )


def test_validation_rejects_empty():
    from omh_shim._validate import validate_output
    with pytest.raises(ValidationError):
        validate_output({}, "omh:heart-rate:2.0")


def test_all_schemas_load():
    from omh_shim._schema_loader import load
    for schema_id in SCHEMA_IDS.values():
        assert isinstance(load(schema_id), dict)


def test_hrv_schema_is_local_namespace():
    assert SCHEMA_IDS["heart_rate_variability"].startswith("local:")


# --- numeric precision ---


def test_oura_heart_rate_preserves_fractional_bpm():
    result = convert(source="oura_raw", data_type="heart_rate",
                     sample={"bpm": 72.456, "timestamp": "2026-04-09T08:00:00Z"})
    assert result["body"]["heart_rate"]["value"] == 72.456


def test_ow_sleep_duration_fractional_minutes():
    """32.5 minutes -> 1950 seconds (not 1920 from int-then-scale)."""
    result = convert(source="ow_normalized", data_type="sleep_duration",
                     sample={"date": "2026-04-09", "sleep_total_duration_minutes": 32.5},
                     tz=UTC)
    assert result["body"]["sleep_duration"]["value"] == 1950


# --- validate kwarg ---


# --- header envelope (IEEE 1752.1 / OMH data-point) ---


def test_convert_always_returns_envelope():
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    assert "header" in result
    assert "body" in result
    assert result["body"]["heart_rate"]["value"] == 72.0


def test_header_has_correct_schema_id_components():
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    sid = result["header"]["schema_id"]
    assert sid == {"namespace": "omh", "name": "heart-rate", "version": "2.0"}


def test_header_has_uuid():
    import uuid as uuid_mod
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    uuid_mod.UUID(result["header"]["uuid"])  # raises ValueError if invalid


def test_header_has_sensed_modality():
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    assert result["header"]["modality"] == "sensed"


def test_header_has_source_creation_date_time():
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    assert "source_creation_date_time" in result["header"]


def test_header_has_no_acquisition_provenance():
    """acquisition_provenance is from the older OMH data-point schema, not
    IEEE 1752.1. The header must NOT include it."""
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    assert "acquisition_provenance" not in result["header"]


def test_header_external_datasheets_from_source_metadata():
    """external_datasheets auto-populated from sample's source metadata."""
    result = convert(
        source="oura_raw", data_type="heart_rate",
        sample={"bpm": 72, "timestamp": "2026-04-09T08:00:00Z",
                "source": {"device": "Oura Ring Gen3"}},
    )
    assert result["header"]["external_datasheets"] == [
        {"datasheet_type": "manufacturer", "datasheet_reference": "Oura Ring Gen3"},
    ]


def test_header_omits_external_datasheets_when_no_source():
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72})
    assert "external_datasheets" not in result["header"]


def test_header_external_datasheets_oura_raw_implicit_device():
    """oura_raw samples lack nested source metadata; the device is implicit."""
    result = convert(
        source="oura_raw", data_type="heart_rate",
        sample={"bpm": 72, "timestamp": "2026-04-09T08:00:00Z"},
    )
    assert result["header"]["external_datasheets"] == [
        {"datasheet_type": "manufacturer", "datasheet_reference": "Oura Ring"},
    ]


def test_header_local_schema_namespace():
    """HRV uses the local: namespace — header.schema_id must reflect that."""
    result = convert(
        source="oura_raw", data_type="heart_rate_variability",
        sample={"rmssd": 42.5, "timestamp": "2026-04-09T08:00:00Z"},
    )
    sid = result["header"]["schema_id"]
    assert sid == {"namespace": "local", "name": "heart-rate-variability", "version": "1.0"}


def test_validate_raises_on_remote_ref():
    """Unknown $ref URIs must fail loudly via NoNetwork, not fetch over the network."""
    from jsonschema import Draft7Validator

    from omh_shim._validate import _registry

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$ref": "https://example.invalid/never-resolvable.json"
    }
    validator = Draft7Validator(schema, registry=_registry())
    # iter_errors raises when a $ref can't be resolved; the NoNetwork retriever
    # ensures the underlying cause is an explicit RuntimeError marking the URI
    # as blocked, rather than a silent fetch attempt or a generic Unresolvable.
    with pytest.raises(Exception) as exc_info:
        list(validator.iter_errors({}))
    chain_msgs = []
    err = exc_info.value
    while err is not None:
        chain_msgs.append(str(err))
        err = err.__cause__
    combined = " | ".join(chain_msgs)
    assert "Remote" in combined or "blocked" in combined, (
        f"Expected NoNetwork marker in error chain, got: {combined}"
    )


def test_registry_resolves_w3id_refs():
    """A schema referencing a w3id IEEE URL must resolve from the local registry."""
    from jsonschema import Draft7Validator

    from omh_shim._validate import _registry

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$ref": "https://w3id.org/ieee/ieee-1752-schema/header-1.0.json"
    }
    validator = Draft7Validator(schema, registry=_registry())
    # If the $ref doesn't resolve, this raises. Validating an empty object
    # against the IEEE header should produce errors (required fields missing),
    # not a fetch attempt.
    errors = list(validator.iter_errors({}))
    assert errors  # missing required fields
    assert all("Remote" not in str(e) for e in errors), \
        "Should not have hit NoNetwork — w3id ref should resolve locally"


# --- header validation against IEEE 1752.1 ---


def test_header_validates_against_ieee_schema():
    """Every (source, data_type) fixture produces an IEEE-valid header."""
    import json
    from datetime import UTC
    from pathlib import Path

    FIXTURES = Path(__file__).parent / "fixtures"
    for source in ("oura_raw", "ow_normalized"):
        for fixture in (FIXTURES / source).glob("*_input.json"):
            data_type = fixture.stem.replace("_input", "")
            sample = json.loads(fixture.read_text())
            result = convert(source=source, data_type=data_type,
                             sample=sample, tz=UTC)
            assert "header" in result, f"{source}/{data_type}: missing header"


def test_header_validation_rejects_empty():
    """An empty header must fail validation (missing required fields)."""
    from omh_shim._validate import validate_output
    with pytest.raises(ValidationError):
        validate_output({}, HEADER_SCHEMA_ID)


def test_validate_false_skips(monkeypatch):
    """validate=False must skip both body AND header validation."""
    from omh_shim import _validate
    call_log = []
    original = _validate.validate_output

    def spy(*args, **kwargs):
        call_log.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(_validate, "validate_output", spy)
    convert(source="ow_normalized", data_type="heart_rate",
            sample={"timestamp": "2026-04-09T08:00:00Z",
                    "type": "heart_rate", "value": 72},
            validate=False)
    assert len(call_log) == 0, "validate_output should not be called when validate=False"
