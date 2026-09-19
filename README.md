# omh-shim

Convert wearable health data from vendor schemas to [IEEE 1752](https://opensource.ieee.org/omh/1752) and [Open mHealth](https://www.openmhealth.org/) schemas.

## Status

v2.1 — both sources now convert every Oura-sourced measure Open Wearables 0.9.0
serves that has a live IEEE 1752 or Open mHealth schema (11 data types in all; blood
glucose is OW-only, the other 10 are Oura-sourced). Measures OW can serve from other
providers (blood pressure, body temperature, spirometry) stay served-only, see below.
The 2.0 line moved three data types to IEEE and removed two; see
[CHANGELOG.md](CHANGELOG.md) before upgrading from 1.x.

## Install

```bash
pip install git+https://github.com/jupyterhealth/omh-shim.git@v2.1.0
```

## Usage

Timestamp-based data types (one reading at a known instant):

```python
from omh_shim import convert

omh_record = convert(
    source="ow_normalized",
    data_type="heart_rate",
    sample={
        "timestamp": "2026-04-09T08:30:00+00:00",
        "type": "heart_rate",
        "value": 72,
        "unit": "bpm",
        "source": {"provider": "oura", "source": "oura", "device": None, "device_type": "ring"},
    },
)
```

The daily *shapes* — an OW `ActivitySummary` or `SleepSummary`, an Oura
`daily_activity` or `daily_spo2` item — aggregate over a calendar day, so they
REQUIRE an explicit timezone so the day boundaries reflect the user's local day
rather than silently assuming UTC. The episode and workout shapes that reach the
same data types carry their own interval and ignore `tz`:

```python
from datetime import UTC
from zoneinfo import ZoneInfo

# UTC-anchored upstream data
convert(
    source="oura_raw",
    data_type="physical_activity",
    sample={"day": "2026-04-09", "steps": 8432},
    tz=UTC,
)

# User's local timezone
convert(
    source="oura_raw",
    data_type="physical_activity",
    sample={"day": "2026-04-09", "steps": 8432},
    tz=ZoneInfo("America/Los_Angeles"),
)
```

On `oura_raw`, `body_weight` and `body_height` need a caller-supplied `timestamp`
because Oura's `personal_info` carries none (see
"[Supported sources and data types](#supported-sources-and-data-types)").

Every conversion returns the full IEEE 1752.1 data-point envelope —
`{"header": ..., "body": ...}` — with UUID, schema_id components, creation
timestamp, modality, and `external_datasheets` auto-populated from the sample's
source metadata (a nested `source` dict, or the device implied by `source` for
raw feeds like `oura_raw`):

```python
convert(
    source="oura_raw",
    data_type="heart_rate",
    sample={"bpm": 72, "source": "rest", "timestamp": "2026-04-09T03:15:00+00:00"},
)
# Returns:
# {
#   "header": {
#     "uuid": "...",
#     "schema_id": {"namespace": "omh", "name": "heart-rate", "version": "2.0"},
#     "source_creation_date_time": "...",
#     "modality": "sensed",
#     "external_datasheets": [{"datasheet_type": "manufacturer", "datasheet_reference": "Oura Ring"}]
#   },
#   "body": {
#     "heart_rate": {"value": 72.0, "unit": "beats/min"},
#     "effective_time_frame": {"date_time": "2026-04-09T03:15:00Z"}
#   }
# }
```

`convert` raises `ConversionError` for unknown `(source, data_type)` pairs,
invalid sample shapes, naive (timezone-less) datetimes, or a missing ``tz``
for daily data types. It raises `ValidationError` if the converter output
fails schema validation.

## Supported sources and data types

| `source` | `data_type` values |
|---|---|
| `oura_raw` | `heart_rate`, `oxygen_saturation`, `respiratory_rate`, `sleep_duration`, `sleep_episode`, `sleep_stage_summary`, `time_in_bed`, `physical_activity`, `body_weight`, `body_height` |
| `ow_normalized` | `heart_rate`, `oxygen_saturation`, `respiratory_rate`, `sleep_duration`, `sleep_episode`, `sleep_stage_summary`, `time_in_bed`, `physical_activity`, `body_weight`, `body_height`, `blood_glucose` |

Body schemas resolve IEEE 1752 first, Open mHealth second, and omh-shim never
emits a schema its publisher has deprecated — where a deprecated Open mHealth
schema declares a successor, that successor is what resolves (`sleep_duration`
emits `ieee:total-sleep-time:1.0`). omh-shim emits only schemas published by one
of those two standards; where neither defines a measure (heart-rate variability,
for example) it does not convert it. Steps are carried by `physical_activity` as
`base_movement_quantity`; there is no separate step-count data type.

Two converters accept a second input shape: `heart_rate` takes a resting-heart-rate
sample (OW `type=resting_heart_rate`, or an Oura sleep item) and tags it
`temporal_relationship_to_sleep: "during sleep"`; `physical_activity` takes a workout
(OW `Workout`, or an Oura workout item) as well as a daily summary. On `oura_raw`,
`body_weight` and `body_height` need a caller-supplied `timestamp` on the sample,
because Oura's `personal_info` carries no measurement time.

## Served schemas without a converter

omh-shim also vendors body schemas that have no `convert()` converter:

- Clinical Open mHealth bodies — `omh:blood-pressure:4.0`,
  `omh:body-temperature:4.0`, `omh:forced-expiratory-volume-1-second:1.0`,
  `omh:forced-vital-capacity:1.0`, `omh:rr-interval:1.0`.
- `omh:physical-activity:1.2`, `omh:sleep-episode:1.1`, `omh:step-count:3.0` and
  `omh:sleep-duration:2.0` — the Open mHealth bodies omh-shim emitted before
  2.0.0 moved them to IEEE. Open mHealth has deprecated all four, so none may be
  a resolution candidate; they stay vendored because they are the evidence the
  successor invariant reads at import, and so consumers can keep validating
  records written under the old ids.

They exist so consumers can **serve and validate** these bodies offline from a
single pinned source:

```python
from omh_shim import known_ids, load_schema

"omh:blood-pressure:4.0" in known_ids()    # True
schema = load_schema("omh:blood-pressure:4.0")  # vendored JSON schema, all $refs resolvable offline
```

These are tracked as `SERVED_NO_CONVERTER` in `tests/test_schema_coverage.py`
(the authoritative list) and refreshed alongside the converter schemas by
`tools/refresh_schemas.py`. `tools/check_schema_adoption.py` watches the same two
publishers for changes that would invalidate a resolved id — an Open mHealth
deprecation, or an IEEE measure omh-shim could now adopt. Both tools need an
editable install (`pip install -e .`) and run from the repo root.

## Adding a new source

See [`docs/adding-a-source.md`](docs/adding-a-source.md) for a step-by-step
guide to adding a new device source (converter functions, test fixtures,
documentation).

## Mapping references

- [`docs/mappings/oura_raw.md`](docs/mappings/oura_raw.md) — Oura Ring v2 API → OMH (body fields)
- [`docs/mappings/ow_normalized.md`](docs/mappings/ow_normalized.md) — Open Wearables normalized API → OMH (body fields)
- [`docs/mappings/ieee-1752-header.md`](docs/mappings/ieee-1752-header.md) — IEEE 1752.1 data-point header envelope

## Credits

`omh_shim/sources/oura_raw.py` ports converter mapping logic with permission
from [dicristea/oura-clinical-workbench](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn).
See [AUTHORS.md](AUTHORS.md).

## License

MIT. See [LICENSE](LICENSE).
