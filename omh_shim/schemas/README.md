# Vendored Schemas

Schemas are vendored from two upstream sources:

- **OMH:** `https://github.com/openmhealth/schemas` — body schemas (heart-rate, step-count, etc.)
- **IEEE 1752.1:** `https://opensource.ieee.org/omh/1752` — envelope schemas (header, data-point, schema-id) and shared utility refs

Pinned versions are recorded in [`_pinned.json`](_pinned.json). Don't edit that file by hand — use `tools/refresh_schemas.py` (see below).

## Layout

```
omh_shim/schemas/
  metadata/     # IEEE 1752.1 envelope (data-point, data-series, header, schema-id)
  data/         # OMH body schemas (heart-rate, step-count, sleep-*, physical-activity, oxygen-saturation, hr-variability)
  utility/      # Shared $ref deps (time-frame, unit-value, descriptive-statistic, ...)
```

## Body schemas (the 7 that `convert()` validates against)

| Filename | Source | Notes |
|---|---|---|
| `data/omh_heart-rate_2-0.json` | OMH `schema/omh/heart-rate-2.0.json` | |
| `data/omh_step-count_3-0.json` | OMH `schema/omh/step-count-3.0.json` | |
| `data/omh_sleep-duration_2-0.json` | OMH `schema/omh/sleep-duration-2.0.json` | |
| `data/omh_sleep-episode_1-1.json` | OMH `schema/omh/sleep-episode-1.1.json` | |
| `data/omh_physical-activity_1-2.json` | OMH `schema/omh/physical-activity-1.2.json` | |
| `data/omh_oxygen-saturation_2-0.json` | OMH `schema/omh/oxygen-saturation-2.0.json` | |
| `data/local_heart-rate-variability_1-0.json` | local placeholder | Open mHealth has no canonical HRV schema. Locally-authored. |

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

## Body validation source decision

For the 7 implemented data types, body validation uses the OMH schemas. Some of these (`physical-activity`, `step-count`, `sleep-episode`) also have IEEE 1752.1 versions; migration is deferred pending [JHE#443](https://github.com/jupyterhealth/jupyterhealth-exchange/issues/443) (JHE schemas drift from canonical sources).

Header validation uses the IEEE 1752.1 envelope (`metadata/header-1.0.json`) — added in [omh-shim#10](https://github.com/jupyterhealth/omh-shim/issues/10).
