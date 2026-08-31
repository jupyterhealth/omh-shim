# Open Wearables Normalized → Open mHealth Mapping Reference

Source: Open Wearables (OW) read API — `GET /api/v1/external/users/{id}/timeseries` and `GET /api/v1/external/users/{id}/summaries`.
Converter module: `omh_shim/sources/ow_normalized.py`.

OW normalizes data from multiple device vendors (Oura, Fitbit, etc.) into a common schema before serving it through the read API. The field names below reflect OW's normalized shapes, not any vendor's raw format.

This document covers the **body** content of each converter. For the IEEE 1752.1 data-point header envelope (`header=True`), see [ieee-1752-header.md](ieee-1752-header.md).

---

## heart_rate → `omh:heart-rate:2.0`

**OW shape:** `TimeSeriesSample` with `type=heart_rate`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `heart_rate.value` | float | beats/min |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |

### Not mapped

| OW field | Reason |
|---|---|
| `unit` | Always `"bpm"` in OW; OMH schema requires `"beats/min"` — hardcoded |
| `type` | Discriminator for dispatch, not health data |
| `zone_offset` | Informational; the timestamp already carries the offset |
| `source` | Device metadata (source_name, device_model); not part of OMH heart-rate schema |

---

## heart_rate_variability → `local:heart-rate-variability:1.0`

**OW shape:** `TimeSeriesSample` with `type=heart_rate_variability`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `heart_rate_variability.value` | float | ms |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | |

### Endpoint-specific handling

- **Local placeholder schema.** Same as Oura raw — `local:` namespace, not OMH-standard.

---

## step_count → `omh:step-count:3.0`

**OW shape:** Two supported input shapes.

### Shape 1: `ActivitySummary` (preferred)

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `steps` | `step_count.value` | int | unit: steps |
| `date` | `effective_time_frame.time_interval` | day interval | Requires `tz` |

### Shape 2: `TimeSeriesSample` with `type=steps`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `step_count.value` | int | unit: steps |
| `timestamp` | `effective_time_frame.time_interval` | 1-minute interval | end = timestamp, start = timestamp − 1 min |

### Endpoint-specific handling

- **OMH step-count:3.0 requires `time_interval`**, not `date_time`. This is why the TimeSeriesSample shape builds a 1-minute interval rather than using the timestamp directly — the OMH schema would reject `date_time` for this data type.
- **Timezone required for ActivitySummary shape.** The `date` field is a bare `YYYY-MM-DD`; day bounds need an explicit timezone. The TimeSeriesSample shape does not need `tz` because the timestamp already has an offset.
- **Unknown shapes rejected.** Samples that match neither shape raise `ConversionError`.

---

## sleep_duration → `omh:sleep-duration:2.0`

**OW shape:** `ActivitySummary` (sleep fields)

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `sleep_total_duration_minutes` | `sleep_duration.value` | int | Converted to seconds (×60). Scale applied before int cast to preserve fractional-minute precision. |
| `date` | `effective_time_frame.time_interval` | day interval | Requires `tz` |

### Not mapped

| OW field | Reason |
|---|---|
| `sleep_time_in_bed_minutes` | OMH sleep-duration covers total sleep time, not time in bed |

---

## sleep_episode → `omh:sleep-episode:1.1`

**OW shape:** Sleep detail object

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `bedtime_start` | `effective_time_frame.time_interval.start_date_time` | ISO-8601 | Required |
| `bedtime_end` | `effective_time_frame.time_interval.end_date_time` | ISO-8601 | Required |
| `sleep_total_duration_minutes` | `total_sleep_time.value` | int | sec (×60); optional |
| `sleep_awake_minutes` | `wake_after_sleep_onset.value` | int | sec (×60); optional |
| `sleep_efficiency_score` | `sleep_maintenance_efficiency_percentage.value` | float | %; optional |
| `is_nap` | `is_main_sleep` | bool | Inverted: `is_nap=true` → `is_main_sleep=false` |

### Endpoint-specific handling

- **Minutes → seconds.** OW reports sleep durations in minutes; OMH requires seconds. The ×60 scaling is applied before the int cast so fractional minutes preserve precision (e.g., 32.5 min → 1950 sec, not 1920).
- **Optional fields omitted when absent.** Only `effective_time_frame` is schema-required.

### Not mapped (gaps)

| OW field | Reason |
|---|---|
| `sleep_deep_minutes` | OMH sleep-episode:1.1 has no per-stage breakdown |
| `sleep_rem_minutes` | Same |
| `sleep_light_minutes` | Same |
| `sleep_time_in_bed_minutes` | Separate concept from the episode's time interval |
| `record_id` | OW internal identifier; not health data |

---

## physical_activity → `omh:physical-activity:1.2`

**OW shape:** `ActivitySummary`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| (hardcoded) | `activity_name` | string | Always `"daily activity summary"` |
| `date` | `effective_time_frame.time_interval` | day interval | Requires `tz` |
| `distance_meters` | `distance.value` | float | meters; optional |
| `active_calories_kcal` | `kcal_burned.value` | float | kcal; optional |

### Endpoint-specific handling

- **Timezone required.** Same as all daily types.
- **Step count not included.** OMH physical-activity:1.2 has no step-count field; use the `step_count` converter.
- **Active minutes not modeled.** OW provides `active_minutes` but OMH physical-activity:1.2 has no field for it.

### Not mapped

| OW field | Reason |
|---|---|
| `steps` | Mapped via `step_count` converter |
| `active_minutes` | No OMH equivalent |
| `source` | Device metadata, not health data |

---

## blood_glucose → `omh:blood-glucose:4.0`

**OW shape:** `TimeSeriesSample` with `type=blood_glucose`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `blood_glucose.value` | float | mg/dL |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |

### Endpoint-specific handling

- **No `oura_raw` counterpart.** Glucose reaches Open Wearables through the mobile SDK (Apple HealthKit / Android Health Connect). Oura does not currently expose glucose through its API.

### Not mapped

| OW field | Reason |
|---|---|
| `unit` | Always `"mg_dl"` in OW; OMH schema requires `"mg/dL"`, so it is hardcoded |
| `type` | Discriminator for dispatch, not health data |
| `zone_offset` | Informational; the timestamp already carries the offset |
| `source` | Device metadata (source_name, device_model); not part of OMH blood-glucose schema |
