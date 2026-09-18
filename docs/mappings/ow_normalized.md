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

### Not mapped

| OW field | Reason |
|---|---|
| `unit` | Always `"bpm"` in OW; OMH schema requires `"beats/min"` — hardcoded |
| `type` | Discriminator for dispatch, not health data |
| `zone_offset` | Informational; the timestamp already carries the offset |
| `source` | Device metadata (source_name, device_model); not part of OMH heart-rate schema |

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
| `efficiency_percent`, `stages`, `avg_*` | No field on `ieee:total-sleep-time:1.0`; carried by `sleep_episode` / `sleep_stage_summary` |
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
| `source` | Device metadata; feeds the header's `external_datasheets` |
| `sleep_stage_intervals` | Only returned with `include=stages`; no consumer asks yet |

---

## physical_activity → `ieee:physical-activity:1.0`

**OW shape:** `ActivitySummary`

| OW field | Body field | Type | Notes |
|---|---|---|---|
| (hardcoded) | `activity_name` | string | Always `"daily activity summary"` |
| `date` | `effective_time_frame.time_interval` | day interval | Requires `tz` |
| `distance_meters` | `distance.value` | float | meters; optional |
| `active_calories_kcal` | `kcal_burned.value` | float | kcal; optional |
| `steps` | `base_movement_quantity.value` | int | unit: steps; optional |

### Endpoint-specific handling

- **Timezone required.** Same as all daily types.
- **Steps live here.** `ieee:physical-activity:1.0` models step count as `base_movement_quantity` (unit `steps`), which is why OMH deprecated `step-count:3.0` in its favor. The OW per-minute step timeseries shape has no IEEE home and is no longer converted.
- **Active minutes not modeled.** OW provides `active_minutes` but `ieee:physical-activity:1.0` has no directly equivalent field.

### Not mapped

| OW field | Reason |
|---|---|
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
