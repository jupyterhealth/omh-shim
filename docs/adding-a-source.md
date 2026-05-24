# Adding a New Source

This guide walks through adding a new device source to omh-shim. By the end
you'll have converters that transform vendor-specific data into validated
Open mHealth schemas, with full test coverage.

## Prerequisites

- The data type you're converting must have a vendored OMH schema under
  `omh_shim/schemas/data/`. If it doesn't, vendor one first using
  `tools/refresh_schemas.py` (see `omh_shim/schemas/README.md`).
- Familiarity with the vendor's API response shape (field names, types, nesting).

## Step 1: Create the source module

Create `omh_shim/sources/<source_name>.py`. Each converter is a function
whose name matches a `data_type` in `SCHEMA_IDS` (`omh_shim/__init__.py`).

Every converter function must follow this signature:

```python
from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    ...
```

- **`sample`** — one record from the vendor's API (a dict).
- **`tz`** — timezone for daily data types (`step_count`, `physical_activity`,
  `sleep_duration`, `oxygen_saturation`). Timestamp-based types can ignore it.
- **Returns** — the OMH body dict (not the envelope). The envelope (header +
  body) is built automatically by `convert()`.

### Shared helpers

`omh_shim/_helpers.py` provides common OMH formatting functions. Use them
instead of building dicts by hand:

| Helper | Use for | Example |
|---|---|---|
| `unit_value(value, unit)` | `{"value": 72, "unit": "beats/min"}` | `unit_value(72, "beats/min")` |
| `date_time_frame(timestamp_str)` | `{"date_time": "2026-04-09T08:00:00Z"}` | Timestamp-based types |
| `day_interval(day_str, tz=tz)` | `{"time_interval": {"start_date_time": ..., "end_date_time": ...}}` | Daily types |
| `interval_from_bounds(start, end)` | Time interval from two timestamps | Sleep episodes |
| `set_optional(out, omh_key, sample, vendor_key, unit=...)` | Conditionally set a field | Optional measurements |

### Error handling

Raise `ConversionError` (from `omh_shim.errors`) for invalid input — missing
required fields, wrong types, etc. Don't let raw `KeyError` or `TypeError`
propagate; `convert()` wraps them but an explicit `ConversionError` with a
clear message is better.

### Example converter

```python
"""Converters for Garmin API response items -> Open mHealth schemas."""

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from omh_shim._helpers import date_time_frame, unit_value
from omh_shim.errors import ConversionError


def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Garmin heart rate sample.

    Example::

        {"timestamp": "2026-04-09T08:30:00Z", "heartRate": 72}
    """
    if "heartRate" not in sample:
        raise ConversionError("garmin heart_rate requires 'heartRate' field")
    return {
        "heart_rate": unit_value(sample["heartRate"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }
```

## Step 2: Register converters

In `omh_shim/_dispatch.py`, import your module and add entries to `REGISTRY`:

```python
from omh_shim.sources import garmin

REGISTRY: Mapping[tuple[str, str], _Converter] = MappingProxyType({
    # ... existing entries ...
    ("garmin", "heart_rate"): garmin.heart_rate,
})
```

Each entry is `(source_name, data_type) -> converter_function`. Only register
converters for data types the vendor actually provides.

## Step 3: Add test fixtures

Create `tests/fixtures/<source_name>/` with paired files for each data type:

```
tests/fixtures/garmin/
  heart_rate_input.json      # one vendor API sample
  heart_rate_expected.json   # the expected OMH body output
```

The parameterized test in `tests/test_sources.py` will automatically pick
these up once you add your source to `SOURCES` (next step).

To generate the expected output from your converter:

```python
import json
from datetime import UTC
from omh_shim import convert

result = convert(source="garmin", data_type="heart_rate",
                 sample={"timestamp": "2026-04-09T08:30:00Z", "heartRate": 72})
print(json.dumps(result["body"], indent=2))
```

## Step 4: Wire into the test suite

In `tests/test_sources.py`, add your source to `SOURCES`:

```python
SOURCES = ["oura_raw", "ow_normalized", "garmin"]
```

If your source has daily data types, add them to `DAILY_CASES` in
`tests/test_core.py` so the "tz required" contract is enforced.

Add edge-case tests for your error paths (malformed input, missing fields)
as standalone test functions in `test_sources.py`.

## Step 5: Update the coverage manifest

In `tests/test_schema_coverage.py`, no changes needed — the coverage test
checks `SCHEMA_IDS` against `_dispatch.REGISTRY` and the vendored schemas.
As long as your registered data types already have schemas in `SCHEMA_STATUS`,
it passes. If you're adding a data type that isn't in `SCHEMA_STATUS` yet,
add it there.

## Step 6: Update documentation

- **`README.md`** — add your source to the "Supported sources and data types"
  table.
- **`docs/mappings/<source_name>.md`** — create a mapping reference showing
  vendor field → OMH field for each converter. Follow the format in
  `docs/mappings/oura_raw.md`.
- **`CHANGELOG.md`** — add an entry under `[Unreleased]`.

## Checklist

Before opening a PR:

- [ ] Source module under `omh_shim/sources/` with converter functions
- [ ] Entries in `_dispatch.REGISTRY`
- [ ] Fixture files (input + expected) for each converter
- [ ] Source added to `SOURCES` in `test_sources.py`
- [ ] Daily types added to `DAILY_CASES` in `test_core.py`
- [ ] Edge-case tests for error paths
- [ ] `pytest -q` passes (schema validation runs automatically)
- [ ] `ruff check .` clean
- [ ] `mypy` clean
- [ ] README table updated
- [ ] Mapping reference doc created
- [ ] CHANGELOG entry added
