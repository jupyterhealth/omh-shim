# Header validation against IEEE 1752.1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Validate the output header against the vendored IEEE `metadata/header-1.0.json` schema. Currently `convert()` validates only the body; the header is hand-built by `build_header()` and never checked against a schema. JHE validates the header ([core/models.py:1320-1321](https://github.com/jupyterhealth/jupyterhealth-exchange/blob/main/core/models.py#L1320-L1321)) — the shim should match. Tracks [jupyterhealth/omh-shim#10](https://github.com/jupyterhealth/omh-shim/issues/10).

**Architecture:** Add one new schema-id constant for the IEEE header, wire it through `_schema_loader._FILENAMES`, and call `validate_output()` for the header inside `convert()` alongside the existing body validation. TDD.

**Tech Stack:** Python 3.11+, `jsonschema`, `referencing`, pytest.

---

## Files

- Modify: `omh_shim/_schema_loader.py` — add `_FILENAMES` entry for the IEEE header
- Modify: `omh_shim/__init__.py` — add header validation call in `convert()`
- Modify: `tests/test_core.py` — add header validation tests

## Task 1: Add IEEE header schema to _FILENAMES + validate in convert()

- [ ] **Step 1: Write failing tests in `tests/test_core.py` (append):**

```python
# --- header validation against IEEE 1752.1 ---


def test_header_validates_against_ieee_schema():
    """Every (source, data_type) fixture produces an IEEE-valid header."""
    import json
    from pathlib import Path
    from datetime import UTC

    FIXTURES = Path(__file__).parent / "fixtures"
    for source in ("oura_raw", "ow_normalized"):
        for fixture in (FIXTURES / source).glob("*_input.json"):
            data_type = fixture.stem.replace("_input", "")
            sample = json.loads(fixture.read_text())
            tz = UTC if data_type in ("step_count", "physical_activity",
                                       "sleep_duration") else None
            result = convert(source=source, data_type=data_type,
                             sample=sample, tz=tz)
            assert "header" in result, f"{source}/{data_type}: missing header"


def test_header_validation_rejects_empty():
    """An empty header must fail validation (missing required fields)."""
    from omh_shim._validate import validate_output
    with pytest.raises(ValidationError, match="header"):
        validate_output({}, "ieee:header:1.0")


def test_validate_false_skips_header_validation(monkeypatch):
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
```

- [ ] **Step 2: Run tests to see which fail:**

```
.venv/bin/pytest tests/test_core.py::test_header_validates_against_ieee_schema tests/test_core.py::test_header_validation_rejects_empty tests/test_core.py::test_validate_false_skips_header_validation -v
```

Expected: `test_header_validation_rejects_empty` FAILS (KeyError: `ieee:header:1.0` not in `_FILENAMES`). The other two may pass already since they exercise different paths — but `test_header_validation_rejects_empty` is the one that proves the schema-id isn't wired.

- [ ] **Step 3: Add `_FILENAMES` entry in `omh_shim/_schema_loader.py`:**

```python
_FILENAMES: dict[str, str] = {
    "omh:heart-rate:2.0": "data/omh_heart-rate_2-0.json",
    # ... existing entries ...
    "ieee:header:1.0": "metadata/header-1.0.json",
}
```

- [ ] **Step 4: Add header validation in `omh_shim/__init__.py`:**

Inside `convert()`, after the body validation call and before the return statement, add:

```python
    if validate:
        _validate.validate_output(body, schema_id)
        _validate.validate_output(
            build_header(schema_id, external_datasheets=_extract_datasheets(sample, source=source)),
            "ieee:header:1.0",
        )
```

Wait — the issue is that `build_header` is called BELOW. Looking at the current flow:

```python
    if validate:
        _validate.validate_output(body, schema_id)
    return {
        "header": build_header(...),
        "body": body,
    }
```

The header is built INSIDE the return dict literal. To validate it, we need to build it before the return. Refactor:

```python
    if validate:
        _validate.validate_output(body, schema_id)
    header = build_header(
        schema_id,
        external_datasheets=_extract_datasheets(sample, source=source),
    )
    if validate:
        _validate.validate_output(header, "ieee:header:1.0")
    return {"header": header, "body": body}
```

This extracts `build_header(...)` into a variable `header` so it can be both validated and returned.

- [ ] **Step 5: Run tests, expect all 3 new tests PASS. Run full suite:**

```
.venv/bin/pytest -q
```

Expected: 90 passed (87 + 3 new).

- [ ] **Step 6: Check drift detection is satisfied.** The `__init__.py` drift check at module load should still pass — `_FILENAMES` now has one more entry (`ieee:header:1.0`) but `SCHEMA_IDS` doesn't include it (it's not a data-type). Check if the drift guard blocks this:

```python
if set(SCHEMA_IDS.values()) != _schema_loader.known_ids():
    raise RuntimeError(...)
```

If this fires, `known_ids()` now returns a set that includes `ieee:header:1.0`, which isn't in `SCHEMA_IDS`. Two fixes:
- Option A: exclude the `ieee:` prefix from `known_ids()` by convention
- Option B: change the drift check to `SCHEMA_IDS.values() <= known_ids()` (subset, not equality)
- Option C: add a separate `_HEADER_IDS` constant

Option B is cleanest — SCHEMA_IDS values should be a subset of known_ids (SCHEMA_IDS is body schemas; known_ids is everything the loader can load). Update the guard at `__init__.py:33-34`.

- [ ] **Step 7: Run mypy, ruff:**

```
.venv/bin/mypy
.venv/bin/ruff check .
```

Both must pass.

- [ ] **Step 8: Commit:**

```
git add omh_shim/_schema_loader.py omh_shim/__init__.py tests/test_core.py docs/superpowers/plans/2026-05-24-header-validation.md
git commit -m "feat(validate): validate header against IEEE 1752.1 header-1.0 (#10)

convert() now validates the output header alongside the body when
validate=True. The IEEE header-1.0 schema is already vendored (from #9);
this adds it to _FILENAMES and wires the validation call."
```
