# Oura Raw → Open mHealth Mapping Reference

Source: Oura Ring v2 API (`/v2/usercollection/*`).
Converter module: `omh_shim/sources/oura_raw.py`.
Mapping logic ported with permission from [dicristea/oura-clinical-workbench](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn). See [AUTHORS.md](../../AUTHORS.md).

This document covers the **body** content of each converter. For the IEEE 1752.1 data-point header envelope every `convert()` call returns, see [ieee-1752-header.md](ieee-1752-header.md).

---

## heart_rate → `omh:heart-rate:2.0`

**Oura endpoint:** `/v2/usercollection/heartrate` (per-moment samples)

| Oura field | OMH field | Type | Notes |
|---|---|---|---|
| `bpm` | `heart_rate.value` | float | beats/min |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | Must include timezone offset |
| `source` | — | dropped | Oura's context label (sleep/awake/rest), not device model. OW preserves this under its own `source` metadata when ingesting. |

### Resting heart rate (sleep record)

A `/v2/usercollection/sleep` item (recognised by `bedtime_start`) converts through the same function:

| Oura field | OMH field | Type | Notes |
|---|---|---|---|
| `lowest_heart_rate` | `heart_rate.value` | float | beats/min; **required** (null raises) |
| `bedtime_start`, `bedtime_end` | `effective_time_frame.time_interval` | ISO-8601 | The sleep episode |
| (constant) | `temporal_relationship_to_sleep` | enum | `"during sleep"` |
| (constant) | `descriptive_statistic` | enum | `"minimum"`: Oura documents the field as the lowest HR during sleep |

---

## sleep_duration → `ieee:total-sleep-time:1.0`

**Oura endpoint:** `/v2/usercollection/sleep`

| Oura field | OMH field | Type | Notes |
|---|---|---|---|
| `total_sleep_duration` | `total_sleep_time.value` | int | Oura reports in seconds; no unit conversion needed |
| `bedtime_start` | `effective_time_frame.time_interval.start_date_time` | ISO-8601 | |
| `bedtime_end` | `effective_time_frame.time_interval.end_date_time` | ISO-8601 | |

### Endpoint-specific handling

- **A `deleted` record raises `ConversionError`.** The check lives in the shared sleep interval helper, so every sleep-derived data type rejects it; a deleted record must not become an observation.

### Not mapped (gaps)

| Oura field | Reason |
|---|---|
| `time_in_bed` | Own schema; see `time_in_bed` |

---

## sleep_episode → `ieee:sleep-episode:1.0`

**Oura endpoint:** `/v2/usercollection/sleep`

| Oura field | Body field | Type | Notes |
|---|---|---|---|
| `bedtime_start` | `effective_time_frame.time_interval.start_date_time` | ISO-8601 | Required |
| `bedtime_end` | `effective_time_frame.time_interval.end_date_time` | ISO-8601 | Required |
| `total_sleep_duration` | `total_sleep_time.value` | int | sec; optional |
| `light_sleep_duration` | `light_sleep_duration.value` | int | sec; optional |
| `deep_sleep_duration` | `deep_sleep_duration.value` | int | sec; optional |
| `rem_sleep_duration` | `rem_sleep_duration.value` | int | sec; optional |
| `awake_time` | `wake_after_sleep_onset.value` | int | sec; optional |
| `latency` | `latency_to_sleep_onset.value` | int | sec; optional |
| `efficiency` | `sleep_efficiency_percentage.value` | float | %; optional |
| `type` | `is_main_sleep` | bool | Oura `PublicSleepType`: `sleep`, `long_sleep` → `true`; `late_nap`, `rest` → `false`; `deleted` raises `ConversionError` for every sleep-derived data type (a deleted record must not become an observation); absent → field omitted |

### Endpoint-specific handling

- **Optional fields omitted when absent.** Only `effective_time_frame` is schema-required. All other fields are set only if the Oura sample contains them with a non-None value.
- **Main sleep follows Oura's `PublicSleepType`.** Oura v2 (OpenAPI 1.39) enumerates `deleted | sleep | long_sleep | late_nap | rest`. There is no `nap` value; `late_nap` and `rest` are the non-main types.
- **WASO is approximate.** `awake_time` is all awake time in bed and includes the `latency` Oura also reports separately.

### Not mapped (gaps)

| Oura field | Reason |
|---|---|
| `time_in_bed` | Own schema; see `time_in_bed` |
| `restless_periods` | Oura's restless periods are not IEEE's `number_of_awakenings` |
| `heart_rate` (nested object) | Contains time-series data. dicristea maps to IEEE `heart-rate:1.0` as a data-series record. Out of scope. |
| `average_heart_rate` | Summary statistic; dicristea maps to `omh:heart-rate:2.0` with `descriptive_statistic: "average"`. Out of scope. |
| `lowest_heart_rate` | Own data type; see `heart_rate` (resting heart rate) |
| `average_breath` | Own data type; see `respiratory_rate` |
| `average_hrv` | No IEEE or OMH schema defines HRV. |

---

## physical_activity → `ieee:physical-activity:1.0`

Two Oura shapes convert through one function; a workout item also carries `day`, so the workout check runs first.

**Oura shape A:** `/v2/usercollection/daily_activity` item (has `day`; requires `tz`)

| Oura field | Body field | Type | Notes |
|---|---|---|---|
| (hardcoded) | `activity_name` | string | Always `"daily activity summary"` |
| `day` | `effective_time_frame.time_interval` | day interval | Requires `tz` |
| `equivalent_walking_distance` | `distance.value` | float | m; optional |
| `active_calories` | `kcal_burned.value` | float | kcal; optional |
| `steps` | `base_movement_quantity.value` | int | unit `steps`; optional |
| `low_activity_time` | `duration_light_activity.value` | int | sec; optional; Oura's own class |
| `medium_activity_time` | `duration_moderate_activity.value` | int | sec; optional |
| `high_activity_time` | `duration_vigorous_activity.value` | int | sec; optional |

**Oura shape B:** `/v2/usercollection/workout` item (has `activity` and `start_datetime`; `tz` ignored)

| Oura field | Body field | Type | Notes |
|---|---|---|---|
| `activity` | `activity_name` | string | e.g. `running` |
| `start_datetime`, `end_datetime` | `effective_time_frame.time_interval` | ISO-8601 | Required |
| `distance` | `distance.value` | float | m; optional |
| `calories` | `kcal_burned.value` | float | kcal; optional |
| `intensity` | `reported_activity_intensity` | enum | `easy→light`, `moderate→moderate`, `hard→vigorous` |

### Not mapped

| Oura field | Reason |
|---|---|
| `label`, `source`, `day` (workout) | Free text / provenance / redundant with the interval |
| `total_calories`, `score`, `met`, `*_met_minutes`, `sedentary_time`, `resting_time`, `non_wear_time`, `inactivity_alerts`, `target_*`, `class_5_min`, `contributors` | No field on `ieee:physical-activity:1.0` (`met` is a sample object, not a scalar MET value) |

---

## oxygen_saturation → `omh:oxygen-saturation:2.0`

**Oura endpoint:** `/v2/usercollection/daily_spo2`

| Oura field | OMH field | Type | Notes |
|---|---|---|---|
| `spo2_percentage.average` | `oxygen_saturation.value` | float | percent (%) |
| `day` | `effective_time_frame.time_interval` | day interval | Requires `tz` |

### Endpoint-specific handling

- **Nested input.** Oura wraps the SpO2 value in `{"spo2_percentage": {"average": 96.5}}`. The converter raises `ConversionError` if `spo2_percentage` is missing, not a mapping, or lacks `average`.
- **Timezone required.** Same as `physical_activity` — the `day` field needs explicit timezone for day bounds.
- **Daily aggregate.** Oura reports SpO2 as the nightly average from per-minute measurements during sleep. The shim represents this as a full calendar day interval.

### Not mapped (gaps)

| Oura field | Reason |
|---|---|
| `breathing_disturbance_index` | No OMH equivalent; maps to IEEE `apnea-hypopnea-index` (not shimmed) |
| `spo2_percentage.min` / `.max` | Could map via descriptive-statistic; deferred |

---

## sleep_stage_summary → `ieee:sleep-stage-summary:1.0`

**Oura endpoint:** `/v2/usercollection/sleep` (the same item `sleep_episode` reads)

| Oura field | Body field | Type | Notes |
|---|---|---|---|
| `total_sleep_duration` | `sleep_stage_summary.total_sleep_time.value` | int | sec; **required** (null raises) |
| `light_sleep_duration` | `sleep_stage_summary.light_sleep_duration.value` | int | sec; optional |
| `deep_sleep_duration` | `sleep_stage_summary.deep_sleep_duration.value` | int | sec; optional |
| `rem_sleep_duration` | `sleep_stage_summary.rem_sleep_duration.value` | int | sec; optional |
| `awake_time` | `sleep_stage_summary.awake_duration.value` | int | sec; optional |
| `latency` | `sleep_stage_summary.latency_to_sleep_onset.value` | int | sec; optional |
| `efficiency` | `sleep_stage_summary.sleep_efficiency_percentage.value` | float | %; optional |
| `bedtime_start`, `bedtime_end` | `effective_time_frame.time_interval` | ISO-8601 | Required |
| `type` | `is_main_sleep` | bool | As in `sleep_episode` |

`sleep_stage_episodes` is not populated: Oura's `sleep_phase_5_min` is a hypnogram string and no consumer asks for intervals yet.

---

## time_in_bed → `ieee:time-in-bed:1.0`

**Oura endpoint:** `/v2/usercollection/sleep`

| Oura field | Body field | Type | Notes |
|---|---|---|---|
| `time_in_bed` | `time_in_bed.value` | int | sec; **required** (Oura marks it required too) |
| `bedtime_start`, `bedtime_end` | `effective_time_frame.time_interval` | ISO-8601 | Required |
| `type` | `is_main_sleep` | bool | As in `sleep_episode` |

---

## respiratory_rate → `omh:respiratory-rate:2.0`

**Oura endpoint:** `/v2/usercollection/sleep`

| Oura field | OMH field | Type | Notes |
|---|---|---|---|
| `average_breath` | `respiratory_rate.value` | float | breaths/min; **required** (null raises) |
| `bedtime_start`, `bedtime_end` | `effective_time_frame.time_interval` | ISO-8601 | The sleep episode |
| (constant) | `descriptive_statistic` | enum | `"average"`: Oura documents the field as the average over the sleep |

---

## body_weight → `omh:body-weight:3.0` and body_height → `omh:body-height:2.0`

**Oura endpoint:** `/v2/usercollection/personal_info` — a profile object, not a timestamped reading.

| Oura field | OMH field | Type | Notes |
|---|---|---|---|
| `weight` | `body_weight.value` | float | kg; **required** for `body_weight` |
| `height` | `body_height.value` | float | **m** (Oura's unit, emitted as-is; `ow_normalized` emits cm); **required** for `body_height` |
| `timestamp` | `effective_time_frame.date_time` | ISO-8601 | **Caller-supplied.** Oura sends no measurement time. The caller stamps one before calling `convert()` (JHE's raw mode uses the S3 object's `last_modified`, the moment Open Wearables fetched the profile; Open Wearables itself stamps sync time). Absent → `ConversionError`. |

### Not mapped

| Oura field | Reason |
|---|---|
| `id` | The user's id, not the reading's |
| `age`, `biological_sex`, `email` | Demographics / PII; not a measure |
