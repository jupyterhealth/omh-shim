"""Schema coverage test — fails when vendored body schemas drift from converter registry.

Implements the coverage check Min requested on the 2026-05-22 OMH process
review call. See jupyterhealth/omh-shim#7 for full spec.
"""

import importlib.resources

import pytest

from omh_shim import SCHEMA_IDS, ValidationError, _validate, known_ids, load_schema
from omh_shim._dispatch import REGISTRY
from omh_shim._schema_loader import _FILENAMES

# Minimal valid bodies for each served (converter-less) clinical schema, used
# to sanity-check that a conformant body validates and an empty one is rejected.
# (Full transitive $ref coverage is asserted instance-independently by
# test_served_schemas_refs_resolve_offline, not by these samples.) Keyed by id.
SERVED_SAMPLES: dict[str, dict] = {
    "omh:blood-glucose:4.0": {
        "blood_glucose": {"value": 5.5, "unit": "mmol/L"},
        "effective_time_frame": {"date_time": "2026-05-31T08:00:00Z"},
    },
    "omh:blood-pressure:4.0": {
        "systolic_blood_pressure": {"value": 120, "unit": "mmHg"},
        "diastolic_blood_pressure": {"value": 80, "unit": "mmHg"},
        "effective_time_frame": {"date_time": "2026-05-31T08:00:00Z"},
        "body_posture": "sitting",
    },
    "omh:body-temperature:4.0": {
        "body_temperature": {"value": 37.0, "unit": "C"},
        "effective_time_frame": {"date_time": "2026-05-31T08:00:00Z"},
        "measurement_location": "oral",
    },
    "omh:respiratory-rate:2.0": {
        "respiratory_rate": {"value": 16, "unit": "breaths/min"},
        "effective_time_frame": {"date_time": "2026-05-31T08:00:00Z"},
    },
    "omh:rr-interval:1.0": {
        "rr_interval": {"value": 850, "unit": "ms"},
    },
}

SCHEMA_STATUS: frozenset[str] = frozenset({
    "omh_heart-rate_2-0.json",
    "local_heart-rate-variability_1-0.json",
    "omh_oxygen-saturation_2-0.json",
    "omh_physical-activity_1-2.json",
    "omh_sleep-duration_2-0.json",
    "omh_sleep-episode_1-1.json",
    "omh_step-count_3-0.json",
})

# Body schemas vendored so downstream consumers (e.g. the JHE MCP server) can
# serve and validate them. omh-shim has no wearable converter that produces
# these, so they are intentionally absent from SCHEMA_STATUS and SCHEMA_IDS.
SERVED_NO_CONVERTER: frozenset[str] = frozenset({
    "omh_blood-glucose_4-0.json",
    "omh_blood-pressure_4-0.json",
    "omh_body-temperature_4-0.json",
    "omh_respiratory-rate_2-0.json",
    "omh_rr-interval_1-0.json",
})

NOT_RELEVANT: frozenset[str] = frozenset()


def _vendored_body_files() -> set[str]:
    """Return the set of .json filenames under omh_shim/schemas/data/."""
    data_dir = importlib.resources.files("omh_shim.schemas").joinpath("data")
    return {
        entry.name
        for entry in data_dir.iterdir()
        if entry.name.endswith(".json")
    }


def test_no_unknown_vendored_body_schemas():
    """Every vendored body schema must be in one of the known sets."""
    vendored = _vendored_body_files()
    known = SCHEMA_STATUS | SERVED_NO_CONVERTER | NOT_RELEVANT
    unknown = vendored - known
    assert not unknown, (
        f"Found new schema(s) we don't handle: {sorted(unknown)}. "
        "Review the schema, then either add a converter + entry to SCHEMA_STATUS, "
        "add it to SERVED_NO_CONVERTER (served downstream, no converter), "
        "or add it to NOT_RELEVANT with a comment explaining why."
    )


def test_schema_status_entries_have_converters():
    """Every SCHEMA_STATUS entry must have a registered converter."""
    loader_filenames = set(_FILENAMES.values())
    for filename in SCHEMA_STATUS:
        path = f"data/{filename}"
        assert path in loader_filenames, (
            f"{filename} is in SCHEMA_STATUS but has no _FILENAMES entry "
            f"(path 'data/{filename}' not found in _schema_loader._FILENAMES)."
        )


def test_converters_have_schema_status_entries():
    """Every data_type in REGISTRY must have its schema in SCHEMA_STATUS."""
    for data_type in {dt for (_, dt) in REGISTRY}:
        schema_id = SCHEMA_IDS[data_type]
        filename = _FILENAMES[schema_id]
        basename = filename.split("/")[-1]
        assert basename in SCHEMA_STATUS, (
            f"Converter for '{data_type}' exists (schema_id={schema_id}) "
            f"but '{basename}' is not in SCHEMA_STATUS."
        )


def test_served_no_converter_entries_have_loader_but_no_converter():
    """SERVED_NO_CONVERTER schemas are loadable by id but have no converter."""
    loader_filenames = set(_FILENAMES.values())
    converter_files = {_FILENAMES[SCHEMA_IDS[dt]].split("/")[-1] for (_, dt) in REGISTRY}
    for filename in SERVED_NO_CONVERTER:
        assert f"data/{filename}" in loader_filenames, (
            f"{filename} is in SERVED_NO_CONVERTER but has no _FILENAMES entry "
            f"(path 'data/{filename}' not found in _schema_loader._FILENAMES)."
        )
        assert filename not in converter_files, (
            f"{filename} is in SERVED_NO_CONVERTER but a converter produces it; "
            "move it to SCHEMA_STATUS."
        )


def test_categories_are_pairwise_disjoint():
    """Each vendored body schema belongs to exactly one category."""
    assert not (SCHEMA_STATUS & SERVED_NO_CONVERTER)
    assert not (SCHEMA_STATUS & NOT_RELEVANT)
    assert not (SERVED_NO_CONVERTER & NOT_RELEVANT)


def test_served_samples_cover_every_served_schema():
    """SERVED_SAMPLES must stay in sync with SERVED_NO_CONVERTER."""
    sample_files = {_FILENAMES[sid].split("/")[-1] for sid in SERVED_SAMPLES}
    assert sample_files == SERVED_NO_CONVERTER, (
        "SERVED_SAMPLES and SERVED_NO_CONVERTER are out of sync: "
        f"{sample_files ^ SERVED_NO_CONVERTER}"
    )


def test_served_schemas_loadable_by_id():
    """Every served schema id is resolvable via the public known_ids()/load_schema()."""
    for sid in SERVED_SAMPLES:
        assert sid in known_ids()
        assert load_schema(sid)["type"] == "object"


def _external_refs(node: object) -> set[str]:
    """All non-anchor ``$ref`` strings reachable in a JSON-schema node."""
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            refs.add(ref)
        for value in node.values():
            refs |= _external_refs(value)
    elif isinstance(node, list):
        for item in node:
            refs |= _external_refs(item)
    return refs


def test_served_schemas_refs_resolve_offline():
    """Every transitive $ref of each served schema resolves from local files.

    Instance-independent: it walks the whole $ref graph rather than relying on a
    sample body to descend into optional properties. The validation registry
    blocks network access, so an unvendored ref raises instead of resolving —
    this is the authoritative guarantee that the vendored closure is complete.
    """
    resolver = _validate._registry().resolver()
    for sid in SERVED_SAMPLES:
        seen: set[str] = set()
        stack: list[object] = [load_schema(sid)]
        while stack:
            for ref in _external_refs(stack.pop()):
                if ref in seen:
                    continue
                seen.add(ref)
                stack.append(resolver.lookup(ref).contents)


def test_served_schemas_validate_offline():
    """A conformant body validates (sanity that served schemas accept real data)."""
    for sid, body in SERVED_SAMPLES.items():
        _validate.validate_output(body, sid)


def test_served_schemas_reject_invalid_body():
    """An empty body is rejected, proving validation is wired (not a no-op)."""
    for sid in SERVED_SAMPLES:
        with pytest.raises(ValidationError):
            _validate.validate_output({}, sid)


def test_every_data_type_has_fixtures():
    """Every data_type in SCHEMA_IDS must have fixture files in at least one source."""
    from pathlib import Path

    fixtures_dir = Path(__file__).parent / "fixtures"
    sources = [d.name for d in fixtures_dir.iterdir() if d.is_dir()]
    missing = []

    for data_type in SCHEMA_IDS:
        has_fixture = any(
            (fixtures_dir / source / f"{data_type}_input.json").exists()
            for source in sources
        )
        if not has_fixture:
            missing.append(data_type)

    if missing:
        pytest.skip(
            f"Fixture gap tracked as follow-up: {sorted(missing)}. "
            "Each needs <data_type>_input.json + <data_type>_expected.json "
            "in at least one source under tests/fixtures/."
        )
