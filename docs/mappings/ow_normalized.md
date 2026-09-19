# Open Wearables Normalized → Open mHealth Mapping Reference

Source: Open Wearables (OW) read API, 0.9.0 — `GET /api/v1/users/{id}/timeseries`, `.../events/sleep`, `.../events/workouts`, `.../summaries/activity`, `.../summaries/sleep`.
Converter module: `omh_shim/sources/ow_normalized.py`.

OW normalizes data from multiple device vendors (Oura, Fitbit, etc.) into a common schema before serving it through the read API. The field names below reflect OW's normalized shapes, not any vendor's raw format.

This document covers the **body** content of each converter. For the IEEE 1752.1 data-point header envelope every `convert()` call returns, see [ieee-1752-header.md](ieee-1752-header.md).

---

## heart_rate → `omh:heart-rate:2.0`

**OW shape:** `TimeSeriesSample` with `type=heart_rate`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `heart_rate.value` | float | beats/min |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |

### Resting heart rate

A `TimeSeriesSample` with `type=resting_heart_rate` (OW's per-night scalar; Oura's `lowest_heart_rate`) converts through the same function and additionally emits `temporal_relationship_to_sleep: "during sleep"`. No `descriptive_statistic` is set: OW's series is provider-generic, so omh-shim does not claim it is a minimum. The `oura_raw` counterpart does.

### Not mapped

| OW field | Reason |
|---|---|
| `unit` | Always `"bpm"` in OW; OMH schema requires `"beats/min"` — hardcoded |
| `type` | Discriminator for dispatch, not health data |
| `zone_offset` | Informational; the timestamp already carries the offset |
| `source` | Device metadata (provider, source, device, device_type); feeds the header's `external_datasheets` |

---

## sleep_duration → `ieee:total-sleep-time:1.0`

**OW shape:** `SleepSummary` (`GET /users/{id}/summaries/sleep`)

| OW field | Body field | Type | Notes |
|---|---|---|---|
| `duration_minutes` | `total_sleep_time.value` | int | Required. Seconds (×60), scale applied before the int cast. OW defines it as total sleep **excluding naps**. |
| `date` | `effective_time_frame.time_interval` | day interval | Requires `tz` |
| (constant) | `is_main_sleep` | bool | Always `true`, because `duration_minutes` excludes naps |

### Endpoint-specific handling

- **Daily, not per-episode.** The frame is the calendar day in `tz`, not the session bounds: `start_time`/`end_time` are optional in `SleepSummary` (null on a day with no main sleep) and describe only the longest session. `oura_raw.sleep_duration` uses episode bounds because its input is an episode; the two sources differ on purpose.
- **A null `duration_minutes` raises `ConversionError`.** IEEE requires `total_sleep_time`.

### Not mapped

| OW field | Reason |
|---|---|
| `total_duration_minutes` | Includes naps; IEEE total-sleep-time is per-episode with an `is_main_sleep` flag, and a nap-inclusive total has no honest value for that flag |
| `time_in_bed_minutes` | Own schema; see `time_in_bed` |
| `efficiency_percent`, `stages`, `avg_*` | No field on `ieee:total-sleep-time:1.0`. The per-session equivalents are converted from `SleepSession` (`/events/sleep`) by `sleep_episode` / `sleep_stage_summary`; the daily aggregates and `avg_*` are not converted. |
| `interruptions_count` | `sleep_events` wants intervals, not a count |
| `start_time`, `end_time`, `zone_offset`, `sessions`, `nap_*` | See "Daily, not per-episode" |

---

## sleep_episode → `ieee:sleep-episode:1.0`

**OW shape:** `SleepSession` (`GET /users/{id}/events/sleep`)

| OW field | Body field | Type | Notes |
|---|---|---|---|
| `start_time` | `effective_time_frame.time_interval.start_date_time` | ISO-8601 | Required; OW serialises with an offset |
| `end_time` | `effective_time_frame.time_interval.end_date_time` | ISO-8601 | Required |
| `sleep_duration_seconds` | `total_sleep_time.value` | int | sec; optional |
| `stages.light_minutes` | `light_sleep_duration.value` | int | sec (×60); optional; `stages` may be `null` |
| `stages.deep_minutes` | `deep_sleep_duration.value` | int | sec (×60); optional |
| `stages.rem_minutes` | `rem_sleep_duration.value` | int | sec (×60); optional |
| `stages.awake_minutes` | `wake_after_sleep_onset.value` | int | sec (×60); optional; **approximation**, see below |
| `efficiency_percent` | `sleep_efficiency_percentage.value` | float | %; optional |
| `is_nap` | `is_main_sleep` | bool | Inverted; OW always serialises `is_nap` (default `false`), so the flag is always emitted |

### Endpoint-specific handling

- **WASO is approximate.** Oura's awake time is all awake time in bed, including sleep-onset latency, and OW drops Oura's `latency`. True wake-after-sleep-onset is not derivable from the OW response.
- **Minutes → seconds.** The ×60 scaling is applied before the int cast (32.5 min → 1950 sec).
- **Same `SleepSession` feeds three data types.** `sleep_stage_summary` and `time_in_bed` read the same object; one fetch, one observation per IEEE measure.

### Not mapped

| OW field | Reason |
|---|---|
| `id` | Stable per-session UUID; an identifier for the caller's dedup, not health data |
| `duration_seconds` | Derivable from the interval |
| `time_in_bed_seconds` | Own schema; see `time_in_bed` |
| `zone_offset` | The timestamps already carry the offset |
| `source` | Device metadata (provider, source, device, device_type); feeds the header's `external_datasheets` |
| `sleep_stage_intervals` | Only returned with `include=stages`; no consumer asks yet |

---

## physical_activity → `ieee:physical-activity:1.0`

Two OW shapes convert through one function, told apart by their keys.

**OW shape A:** `ActivitySummary` (`GET /users/{id}/summaries/activity`; has `date`; requires `tz`)

| OW field | Body field | Type | Notes |
|---|---|---|---|
| (hardcoded) | `activity_name` | string | Always `"daily activity summary"` |
| `date` | `effective_time_frame.time_interval` | day interval | Requires `tz` |
| `distance_meters` | `distance.value` | float | m; optional |
| `active_calories_kcal` | `kcal_burned.value` | float | kcal; optional |
| `steps` | `base_movement_quantity.value` | int | unit `steps`; optional |
| `active_minutes` | `duration.value` | int | min; optional |
| `intensity_minutes.light` | `duration_light_activity.value` | int | min; optional |
| `intensity_minutes.moderate` | `duration_moderate_activity.value` | int | min; optional |
| `intensity_minutes.vigorous` | `duration_vigorous_activity.value` | int | min; optional |

**OW shape B:** `Workout` (`GET /users/{id}/events/workouts`; has `start_time` and `end_time`, no `date`; `tz` ignored)

| OW field | Body field | Type | Notes |
|---|---|---|---|
| `type` | `activity_name` | string | OW's normalized activity, e.g. `running` |
| `start_time`, `end_time` | `effective_time_frame.time_interval` | ISO-8601 | Required |
| `duration_seconds` | `duration.value` | int | sec; optional |
| `distance_meters` | `distance.value` | float | m; optional |
| `calories_kcal` | `kcal_burned.value` | float | kcal; optional |
| `steps_count` | `base_movement_quantity.value` | int | steps; optional |
| `intensity` | `reported_activity_intensity` | enum | `low→light`, `moderate→moderate`, `high→vigorous`; `unknown`/null omitted |

### Endpoint-specific handling

- **Steps live here.** `ieee:physical-activity:1.0` models step count as `base_movement_quantity`, which is why OMH deprecated `step-count:3.0` in its favor.
- **A sample matching neither shape raises `ConversionError`.**

### Not mapped

| OW field | Reason |
|---|---|
| `name` (Workout) | Free text; IEEE's only label is `activity_name`, and the normalized `type` is the interoperable value |
| `sedentary_minutes`, `total_calories_kcal`, `heart_rate`, `floors_climbed`, `elevation_meters` | No field on `ieee:physical-activity:1.0` |
| `avg/max_heart_rate_bpm`, `hr_zones`, `power_zones`, `segments`, `avg_pace_sec_per_km` (Workout) | No field on `ieee:physical-activity:1.0` |
| `met_value` (schema field) | MET arrives as the separate `physical_effort` timeseries, not on either shape |
| `source` | Device metadata (provider, source, device, device_type); feeds the header's `external_datasheets` |

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
| `source` | Device metadata (provider, source, device, device_type); feeds the header's `external_datasheets` |

---

## sleep_stage_summary → `ieee:sleep-stage-summary:1.0`

**OW shape:** `SleepSession` (`GET /users/{id}/events/sleep`), the same object `sleep_episode` reads

| OW field | Body field | Type | Notes |
|---|---|---|---|
| `sleep_duration_seconds` | `sleep_stage_summary.total_sleep_time.value` | int | sec; **required** (null raises) |
| `stages.light_minutes` | `sleep_stage_summary.light_sleep_duration.value` | int | sec (×60); optional |
| `stages.deep_minutes` | `sleep_stage_summary.deep_sleep_duration.value` | int | sec (×60); optional |
| `stages.rem_minutes` | `sleep_stage_summary.rem_sleep_duration.value` | int | sec (×60); optional |
| `stages.awake_minutes` | `sleep_stage_summary.awake_duration.value` | int | sec (×60); optional |
| `efficiency_percent` | `sleep_stage_summary.sleep_efficiency_percentage.value` | float | %; optional |
| `start_time`, `end_time` | `effective_time_frame.time_interval` | ISO-8601 | Required |
| `is_nap` | `is_main_sleep` | bool | Inverted |

`stages` may be `null`; the body then carries no stage durations, only `total_sleep_time` (all the schema requires) and, when present, `sleep_efficiency_percentage` (read from the session, not from `stages`). `sleep_stage_episodes` (from `sleep_stage_intervals`, `include=stages`) is not populated.

---

## time_in_bed → `ieee:time-in-bed:1.0`

**OW shape:** `SleepSession` (`GET /users/{id}/events/sleep`)

| OW field | Body field | Type | Notes |
|---|---|---|---|
| `time_in_bed_seconds` | `time_in_bed.value` | int | sec; **required** (null raises) |
| `start_time`, `end_time` | `effective_time_frame.time_interval` | ISO-8601 | Required |
| `is_nap` | `is_main_sleep` | bool | Inverted |

---

## respiratory_rate → `omh:respiratory-rate:2.0`

**OW shape:** `TimeSeriesSample` with `type=respiratory_rate` (Oura: per-night `average_breath`)

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `respiratory_rate.value` | float | breaths/min (OW's `brpm` is not read) |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |

---

## body_weight → `omh:body-weight:3.0`

**OW shape:** `TimeSeriesSample` with `type=weight` (OW writes one sample per changed value, stamped at sync time)

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `body_weight.value` | float | kg |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |

---

## body_height → `omh:body-height:2.0`

**OW shape:** `TimeSeriesSample` with `type=height`

| OW field | OMH field | Type | Notes |
|---|---|---|---|
| `value` | `body_height.value` | float | **cm** (OW converts Oura's metres at ingest; `oura_raw` emits `m`) |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |
