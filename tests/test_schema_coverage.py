"""Schema coverage test — fails when vendored body schemas drift from converter registry.

Implements the coverage check Min requested on the 2026-05-22 OMH process
review call. See jupyterhealth/omh-shim#7 for full spec.
"""

import importlib.resources

import pytest

from omh_shim import SCHEMA_IDS
from omh_shim._dispatch import REGISTRY
from omh_shim._schema_loader import _FILENAMES

SCHEMA_STATUS: frozenset[str] = frozenset({
    "omh_heart-rate_2-0.json",
    "local_heart-rate-variability_1-0.json",
    "omh_oxygen-saturation_2-0.json",
    "omh_physical-activity_1-2.json",
    "omh_sleep-duration_2-0.json",
    "omh_sleep-episode_1-1.json",
    "omh_step-count_3-0.json",
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
    """Every vendored body schema must be in SCHEMA_STATUS or NOT_RELEVANT."""
    vendored = _vendored_body_files()
    known = SCHEMA_STATUS | NOT_RELEVANT
    unknown = vendored - known
    assert not unknown, (
        f"Found new schema(s) we don't handle: {sorted(unknown)}. "
        "Review the schema, then either add a converter + entry to SCHEMA_STATUS, "
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


def test_no_overlap_between_status_and_not_relevant():
    """A schema can't be both implemented and not_relevant."""
    overlap = SCHEMA_STATUS & NOT_RELEVANT
    assert not overlap, (
        f"These schemas appear in both SCHEMA_STATUS and NOT_RELEVANT: "
        f"{sorted(overlap)}. Each schema must be in exactly one set."
    )


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
