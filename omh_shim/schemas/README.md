# Vendored OMH Schemas

These schemas are vendored from [openmhealth/schemas](https://github.com/openmhealth/schemas)
at commit `36078a89e5e5efeba8dfc590a81cc42fd140c815` (main, fetched 2026-04-09).

## Top-level schemas (the 7 that omh-shim's `convert()` validates against)

| Filename | Source path | Notes |
|---|---|---|
| `omh_heart-rate_2-0.json` | `schema/omh/heart-rate-2.0.json` | Standard OMH heart-rate v2.0 |
| `omh_step-count_3-0.json` | `schema/omh/step-count-3.0.json` | Standard OMH step-count v3.0 |
| `omh_sleep-duration_2-0.json` | `schema/omh/sleep-duration-2.0.json` | Standard OMH sleep-duration v2.0 |
| `omh_sleep-episode_1-1.json` | `schema/omh/sleep-episode-1.1.json` | Standard OMH sleep-episode v1.1 |
| `omh_physical-activity_1-2.json` | `schema/omh/physical-activity-1.2.json` | Standard OMH physical-activity v1.2 (latest available; spec called for 2.0 but upstream max is 1.2 as of 2026-04) |
| `omh_oxygen-saturation_2-0.json` | `schema/omh/oxygen-saturation-2.0.json` | Standard OMH oxygen-saturation v2.0 |
| `omh_heart-rate-variability_1-0.json` | **local placeholder** | Open mHealth has not published a canonical HRV schema. This is a small non-standard schema mirroring OMH unit-value/time-frame patterns. Re-vendor with the canonical schema if/when one is published upstream. |

## Transitive `$ref` dependencies

The OMH top-level schemas reference other schemas via `$ref` (e.g. `unit-value-1.x.json`).
All transitively-referenced schemas are vendored alongside so the validator can resolve refs
from local files without network access. Vendored aliases (`*-1.x.json`) have been resolved
to point at concrete-version content rather than being one-line filename pointers.

These files are loaded into a `referencing.Registry` at validator startup so jsonschema
Draft7Validator can resolve `$ref` strings to local files.

## Refresh procedure

The refresh script is pinned to a specific ref recorded above. Run with no
args to verify the vendored files still match that ref:

```bash
python tools/refresh_schemas.py
```

To pull a different ref (a tag or commit SHA), pass `--omh-ref`. On
confirmed update, the script rewrites the ref recorded in this README
automatically:

```bash
python tools/refresh_schemas.py --omh-ref v1.0.0
python tools/refresh_schemas.py --omh-ref 7969045b1c2d...
```

The script never writes to this README when run without `--omh-ref` —
default-mode runs only verify the vendored files match the recorded ref.
