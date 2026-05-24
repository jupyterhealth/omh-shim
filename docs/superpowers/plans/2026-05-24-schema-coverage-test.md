# Schema coverage test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a test that fails when a vendored body schema appears that the shim doesn't handle, or when an implemented converter lacks a corresponding schema entry. Tracks [jupyterhealth/omh-shim#7](https://github.com/jupyterhealth/omh-shim/issues/7).

**Architecture:** Single test file `tests/test_schema_coverage.py` with a `SCHEMA_STATUS` frozenset (implemented schemas) and a `NOT_RELEVANT` frozenset (intentionally excluded, initially empty). Four test functions verify bidirectional consistency between the vendored `data/` directory and the `_dispatch.REGISTRY`.

**Tech Stack:** Python 3.11+, pytest, `importlib.resources`, `omh_shim._dispatch.REGISTRY`, `omh_shim.SCHEMA_IDS`.

---

## Files

- Create: `tests/test_schema_coverage.py`

## Task 1: Schema coverage test (single task)

**Files:**
- Create: `tests/test_schema_coverage.py`

- [ ] **Step 1: Create the test file:**

```python
"""Schema coverage test — fails when vendored body schemas drift from converter registry.

Implements the coverage check Min requested on the 2026-05-22 OMH process
review call. See jupyterhealth/omh-shim#7 for full spec.
"""

import importlib.resources

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
```

- [ ] **Step 2: Run tests, expect all 4 new tests PASS (they should pass against the current codebase):**

```
.venv/bin/pytest tests/test_schema_coverage.py -v
```

Expected: 4 PASS. The current vendored set matches the current REGISTRY, so no drift.

- [ ] **Step 3: Run full suite:**

```
.venv/bin/pytest -q
```

Expected: 87 passed (83 + 4 new).

- [ ] **Step 4: Verify failure mode — unknown schema:**

```bash
echo '{}' > omh_shim/schemas/data/zzz_unknown_1-0.json
.venv/bin/pytest tests/test_schema_coverage.py::test_no_unknown_vendored_body_schemas -v
# Expect: FAIL with "Found new schema(s) we don't handle: ['zzz_unknown_1-0.json']"
rm omh_shim/schemas/data/zzz_unknown_1-0.json
```

- [ ] **Step 5: Verify failure mode — NOT_RELEVANT escape hatch:**

Temporarily add `"zzz_unknown_1-0.json"` to `NOT_RELEVANT` in the test file, re-create the dummy file, run the test — should PASS. Then revert both.

- [ ] **Step 6: Run ruff check:**

```
.venv/bin/ruff check .
```

Expected: clean.

- [ ] **Step 7: Commit:**

```
git add tests/test_schema_coverage.py
git commit -m "test(schemas): add coverage test for vendored body schemas (#7)

Fails when a new vendored schema appears without a converter or manifest
entry, when a SCHEMA_STATUS entry lacks a converter, or when a converter
exists without a SCHEMA_STATUS entry. NOT_RELEVANT set provides an
escape hatch for intentionally-excluded schemas."
```

---

## Self-Review

**Spec coverage:**
- test_no_unknown_vendored_body_schemas → acceptance criteria 1, 2
- test_schema_status_entries_have_converters → acceptance criteria 3 (SCHEMA_STATUS ↔ REGISTRY consistency, direction 1)
- test_converters_have_schema_status_entries → acceptance criteria 3 (direction 2)
- test_no_overlap_between_status_and_not_relevant → acceptance criteria 4
- NOT_RELEVANT initially empty, escape hatch verified → acceptance criteria 2 (second bullet)
