# Vendored Schemas

Schemas are vendored from two upstream sources:

- **OMH:** `https://github.com/openmhealth/schemas` — body schemas (heart-rate, blood-glucose, etc.)
- **IEEE 1752.1:** `https://opensource.ieee.org/omh/1752` — envelope schemas (header, data-point, schema-id) and shared utility refs

Pinned versions are recorded in [`_pinned.json`](_pinned.json). Don't edit that file by hand — use `tools/refresh_schemas.py` (see below).

## Layout

```
omh_shim/schemas/
  metadata/     # IEEE 1752.1 envelope (data-point, data-series, header, schema-id)
  data/         # IEEE and OMH body schemas
  utility/      # Shared $ref deps (time-frame, unit-value, descriptive-statistic, ...)
  utility/ieee/ # IEEE's own variant of a utility schema OMH also publishes under the same
                # filename, served at the w3id URI an IEEE body's $id re-bases onto
                # (currently descriptive-statistic-1.0.json, whose IEEE enum is wider)
```

Some `data/` body schemas (e.g. the clinical `blood-pressure`, `respiratory-rate`)
are vendored to be *served and validated* by downstream consumers but have no
`convert()` converter in omh-shim. These are tracked in
`tests/test_schema_coverage.py` as `SERVED_NO_CONVERTER`.

## Refresh procedure

Default mode verifies the vendored files match the recorded refs in `_pinned.json`:

```bash
python tools/refresh_schemas.py
```

To bump either pin, pass the corresponding flag:

```bash
python tools/refresh_schemas.py --omh-ref <tag-or-sha>
python tools/refresh_schemas.py --ieee-ref 1.0.3
python tools/refresh_schemas.py --omh-ref <tag-or-sha> --ieee-ref 1.0.3
```

The script shows diffs, prompts for confirmation, writes the schema files, and updates `_pinned.json` (only for families where you passed a flag — default-mode runs never write).

Body validation uses OMH schemas; header validation uses IEEE 1752.1 (`metadata/header-1.0.json`). See `tests/test_schema_coverage.py` for the authoritative list of implemented schemas.
