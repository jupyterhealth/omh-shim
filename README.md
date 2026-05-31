# omh-shim

Convert wearable health data from vendor schemas to [Open mHealth](https://www.openmhealth.org/) schemas.

## Status

v1.0 — initial public release. Public API is stable; converter coverage will continue to expand.

## Install

```bash
pip install git+https://github.com/jupyterhealth/omh-shim.git@v1.0.1
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
        "source": {"source_name": "Oura Ring", "device_model": "Oura Gen 3"},
    },
)
```

Daily data types (``step_count``, ``physical_activity``, ``sleep_duration``,
``oxygen_saturation``)
aggregate over a calendar day, so they REQUIRE an explicit timezone so the day
boundaries reflect the user's local day rather than silently assuming UTC:

```python
from datetime import UTC
from zoneinfo import ZoneInfo

# UTC-anchored upstream data
convert(
    source="oura_raw",
    data_type="step_count",
    sample={"day": "2026-04-09", "steps": 8432},
    tz=UTC,
)

# User's local timezone
convert(
    source="oura_raw",
    data_type="step_count",
    sample={"day": "2026-04-09", "steps": 8432},
    tz=ZoneInfo("America/Los_Angeles"),
)
```

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
| `oura_raw` | `heart_rate`, `heart_rate_variability`, `oxygen_saturation`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |
| `ow_normalized` | `heart_rate`, `heart_rate_variability`, `oxygen_saturation`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |

Note: `heart_rate_variability` targets the local placeholder schema
`local:heart-rate-variability:1.0` (Open mHealth has not published a canonical
HRV schema as of 2026-04). The `local:` namespace is deliberate — downstream
consumers should not assume OMH-standard interoperability for HRV records.

## Served schemas without a converter

omh-shim also vendors clinical OMH body schemas — blood pressure, blood
glucose, body temperature, respiratory rate, and RR interval — that have no
`convert()` converter. They exist so consumers can **serve and validate** OMH
bodies offline from a single pinned source:

```python
from omh_shim import known_ids, load_schema

"omh:blood-pressure:4.0" in known_ids()    # True
schema = load_schema("omh:blood-glucose:4.0")  # vendored JSON schema, all $refs resolvable offline
```

These are tracked as `SERVED_NO_CONVERTER` in `tests/test_schema_coverage.py`
(the authoritative list) and refreshed alongside the converter schemas by
`tools/refresh_schemas.py`.

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
