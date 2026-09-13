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
    ("oura_raw", "physical_activity", {"day": "2026-04-09"}),
    ("oura_raw", "oxygen_saturation", {"day": "2026-04-09", "spo2_percentage": {"average": 96.5}}),
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
    ("oura_raw", "sleep_duration", {"total_sleep_duration": 27000,
     "bedtime_start": "2026-04-09T22:00:00", "bedtime_end": "2026-04-10T06:00:00"}),
    ("oura_raw", "sleep_episode", {"bedtime_start": "2026-04-09T22:00:00",
     "bedtime_end": "2026-04-10T06:00:00"}),
    ("ow_normalized", "heart_rate", {"timestamp": "2026-04-09T08:30:00",
     "type": "heart_rate", "value": 72}),
    ("ow_normalized", "sleep_episode", {"bedtime_start": "2026-04-09T22:00:00",
     "bedtime_end": "2026-04-10T06:00:00"}),
]


@pytest.mark.parametrize("source,data_type,sample", NAIVE_CASES)
def test_rejects_naive_datetime(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


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


def test_hrv_data_type_removed():
    """Neither IEEE nor OMH defines HRV, so omh-shim does not convert it."""
    assert "heart_rate_variability" not in SCHEMA_IDS
    with pytest.raises(ConversionError, match="No converter"):
        convert(
            source="oura_raw", data_type="heart_rate_variability",
            sample={"rmssd": 42.5, "timestamp": "2026-04-09T08:00:00Z"},
        )


def test_no_local_namespace_schemas():
    """No hand-written schema may be served under any namespace."""
    from omh_shim import known_ids
    assert not [sid for sid in known_ids() if sid.startswith("local:")]


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
    assert result["body"]["total_sleep_time"]["value"] == 1950


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


# --- IEEE-first resolution ---


def test_resolver_prefers_ieee_when_vendored():
    """Any data type with a vendored IEEE candidate must resolve to it."""
    from omh_shim import _SCHEMA_CANDIDATES, known_ids
    vendored = known_ids()
    for data_type, candidates in _SCHEMA_CANDIDATES.items():
        if any(c.startswith("ieee:") and c in vendored for c in candidates):
            assert SCHEMA_IDS[data_type].startswith("ieee:"), data_type


def test_flipped_types_resolve_to_ieee():
    assert SCHEMA_IDS["physical_activity"] == "ieee:physical-activity:1.0"
    assert SCHEMA_IDS["sleep_episode"] == "ieee:sleep-episode:1.0"
    assert SCHEMA_IDS["sleep_duration"] == "ieee:total-sleep-time:1.0"


def test_types_without_ieee_stay_on_omh():
    """No IEEE body exists for these measures, so OMH is the correct fallback."""
    for data_type in ("heart_rate", "oxygen_saturation", "blood_glucose"):
        assert SCHEMA_IDS[data_type].startswith("omh:"), data_type


def test_no_custom_namespaces_in_candidates():
    from omh_shim import _NAMESPACE_PRECEDENCE, _SCHEMA_CANDIDATES
    for candidates in _SCHEMA_CANDIDATES.values():
        for candidate in candidates:
            assert candidate.split(":")[0] in _NAMESPACE_PRECEDENCE, candidate


def test_candidate_names_match_data_type_or_declared_successor():
    """No inference: an off-name candidate must be the successor OMH itself declared."""
    from omh_shim import _SCHEMA_CANDIDATES, _successor_name, known_ids, load_schema
    for data_type, candidates in _SCHEMA_CANDIDATES.items():
        expected = data_type.replace("_", "-")
        for candidate in candidates:
            name = candidate.split(":")[1]
            if name == expected:
                continue
            deprecated = [
                sid for sid in known_ids()
                if sid.startswith("omh:") and sid.split(":")[1] == expected
            ]
            assert deprecated, candidate
            superseded_by = load_schema(deprecated[0])["deprecation"]["supersededBy"]
            assert name == _successor_name(superseded_by), candidate


def test_resolver_ignores_declaration_order(monkeypatch):
    """Precedence comes from the namespace, not from how the table is typed.

    Every real OMH schema with an IEEE counterpart is now deprecated, so the
    non-deprecated pair this property needs has to be faked.
    """
    from omh_shim import _resolve, _schema_loader
    fake = "ieee:heart-rate:1.0"
    real_load = _schema_loader.load
    real_known = _schema_loader.known_ids()
    monkeypatch.setattr(_schema_loader, "known_ids", lambda: real_known | {fake})
    monkeypatch.setattr(
        _schema_loader, "load", lambda sid: {} if sid == fake else real_load(sid)
    )
    assert _resolve("heart_rate", ("omh:heart-rate:2.0", fake)) == fake


def test_resolver_rejects_unknown_namespace():
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="namespace"):
        _resolve("heart_rate", ("local:heart-rate:1.0",))


def test_resolver_rejects_unresolvable_type():
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="no candidate is vendored"):
        _resolve("heart_rate", ("ieee:heart-rate:1.0",))


def test_resolver_rejects_malformed_candidate():
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="malformed"):
        _resolve("sleep_episode", ("ieee:sleep-episode",))


def test_resolver_rejects_duplicate_namespace():
    """Two candidates in one namespace would tie, and the tie breaks lexicographically —
    silently preferring the lower version."""
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="more than once"):
        _resolve("sleep_episode", ("ieee:sleep-episode:2.0", "ieee:sleep-episode:1.0"))


def test_resolver_rejects_deprecated_candidate():
    """OMH deprecated sleep-episode 1.1 in favor of IEEE; it may not be a candidate."""
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="deprecated"):
        _resolve("sleep_episode", ("omh:sleep-episode:1.1",))


def test_resolver_accepts_declared_successor():
    from omh_shim import _resolve
    assert _resolve("sleep_duration", ("ieee:total-sleep-time:1.0",)) == "ieee:total-sleep-time:1.0"


def test_resolver_rejects_undeclared_successor_for_a_vendored_undeprecated_measure():
    """omh:heart-rate:2.0 is vendored and healthy, so it declares no successor at all."""
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="not deprecated and declares no successor"):
        _resolve("heart_rate", ("ieee:total-sleep-time:1.0",))


def test_resolver_distinguishes_an_unvendored_measure_from_an_undeprecated_one():
    """No omh:sleep-stage-summary is vendored — a different diagnosis from the test above."""
    from omh_shim import _resolve
    with pytest.raises(RuntimeError, match="no Open mHealth schema for 'sleep-stage-summary'"):
        _resolve("sleep_stage_summary", ("ieee:total-sleep-time:1.0",))


def test_resolver_rejects_a_candidate_that_is_not_the_declared_successor():
    """sleep-duration's declared successor is total-sleep-time, not sleep-episode."""
    from omh_shim import _resolve
    with pytest.raises(RuntimeError) as excinfo:
        _resolve("sleep_duration", ("ieee:sleep-episode:1.0",))
    message = str(excinfo.value)
    assert "total-sleep-time" in message
    assert "sleep-episode" in message


def test_declared_successor_prefers_the_deprecated_schema_and_is_order_independent(monkeypatch):
    """Two vendored versions of one measure must not let PYTHONHASHSEED pick the answer."""
    from omh_shim import _declared_successor, _schema_loader
    real_known = _schema_loader.known_ids()
    fresh, deprecated = "omh:sleep-duration:1.0", "omh:sleep-duration:2.0"
    monkeypatch.setattr(_schema_loader, "known_ids", lambda: real_known | {fresh})
    monkeypatch.setattr(
        _schema_loader, "load",
        lambda sid: {} if sid == fresh else {
            "deprecation": {"supersededBy": "omh:total-sleep-time:1.x"}
        } if sid == deprecated else {},
    )
    # fresh sorts first; a first-match-wins lookup would answer None here.
    assert _declared_successor("sleep-duration") == "total-sleep-time"


def test_declared_successor_raises_when_supersededby_is_missing(monkeypatch):
    from omh_shim import _declared_successor, _schema_loader
    monkeypatch.setattr(
        _schema_loader, "load",
        lambda sid: {"deprecation": {"reason": "retired"}} if sid == "omh:sleep-duration:2.0" else {},
    )
    with pytest.raises(RuntimeError, match="omh:sleep-duration:2.0.*supersededBy"):
        _declared_successor("sleep-duration")


@pytest.mark.parametrize("superseded_by,expected", [
    ("https://w3id.org/ieee/ieee-1752-schema/physical-activity.json", "physical-activity"),
    ("omh:total-sleep-time:1.x", "total-sleep-time"),
])
def test_successor_name_parses_both_formats(superseded_by, expected):
    from omh_shim import _successor_name
    assert _successor_name(superseded_by) == expected


def test_no_resolved_schema_is_deprecated():
    """The whole point: nothing we emit carries a publisher deprecation."""
    from omh_shim import load_schema
    for schema_id in SCHEMA_IDS.values():
        assert "deprecation" not in load_schema(schema_id), schema_id


def test_step_count_data_type_removed():
    assert "step_count" not in SCHEMA_IDS
    with pytest.raises(ConversionError, match="No converter"):
        convert(source="oura_raw", data_type="step_count", sample={"day": "2026-04-09", "steps": 1}, tz=UTC)


@pytest.mark.parametrize("source,sample", [
    ("oura_raw", {"day": "2026-04-09", "steps": 8432}),
    ("ow_normalized", {"date": "2026-04-09", "steps": 8432}),
])
def test_physical_activity_folds_steps(source, sample):
    body = convert(source=source, data_type="physical_activity", sample=sample, tz=UTC)["body"]
    assert body["base_movement_quantity"] == {"value": 8432, "unit": "steps"}
    assert "step_count" not in body


def test_sleep_duration_emits_ieee_field_name():
    body = convert(
        source="oura_raw", data_type="sleep_duration",
        sample={"bedtime_start": "2026-04-09T22:30:00Z", "bedtime_end": "2026-04-10T06:45:00Z",
                "total_sleep_duration": 27600},
    )["body"]
    assert body["total_sleep_time"] == {"value": 27600, "unit": "sec"}
    assert "sleep_duration" not in body


# --- IEEE sleep-episode field naming ---


@pytest.mark.parametrize("source,sample", [
    ("oura_raw", {"bedtime_start": "2026-04-09T22:30:00Z",
                  "bedtime_end": "2026-04-10T06:45:00Z", "efficiency": 92.5}),
    ("ow_normalized", {"bedtime_start": "2026-04-09T22:30:00Z",
                       "bedtime_end": "2026-04-10T06:45:00Z",
                       "sleep_efficiency_score": 92.5}),
])
def test_sleep_episode_uses_ieee_efficiency_field(source, sample):
    """IEEE has no additionalProperties:false, so validation alone can't catch
    the old field name — consumers would silently drop it."""
    body = convert(source=source, data_type="sleep_episode", sample=sample)["body"]
    assert body["sleep_efficiency_percentage"] == {"value": 92.5, "unit": "%"}
    assert "sleep_maintenance_efficiency_percentage" not in body


def test_sleep_episode_header_uses_ieee_namespace():
    result = convert(
        source="oura_raw", data_type="sleep_episode",
        sample={"bedtime_start": "2026-04-09T22:30:00Z",
                "bedtime_end": "2026-04-10T06:45:00Z"},
    )
    assert result["header"]["schema_id"] == {
        "namespace": "ieee", "name": "sleep-episode", "version": "1.0",
    }
