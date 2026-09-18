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
| `lowest_heart_rate` | Same, with `descriptive_statistic: "minimum"`. Out of scope. |
| `average_breath` | dicristea maps to `omh:respiratory-rate:2.0`. Out of scope. |
| `average_hrv` | No IEEE or OMH schema defines HRV. |

---

## physical_activity → `ieee:physical-activity:1.0`

**Oura endpoint:** `/v2/usercollection/daily_activity`

| Oura field | Body field | Type | Notes |
|---|---|---|---|
| (hardcoded) | `activity_name` | string | Always `"daily activity summary"` |
| `day` | `effective_time_frame.time_interval` | day interval | Requires `tz` |
| `equivalent_walking_distance` | `distance.value` | float | meters; optional |
| `active_calories` | `kcal_burned.value` | float | kcal; optional |
| `steps` | `base_movement_quantity.value` | int | unit: steps; optional |

### Endpoint-specific handling

- **Timezone required.** The `day` field is a bare `YYYY-MM-DD` date, so the converter needs an explicit timezone for the day bounds. A "day" in Tokyo is not a "day" in UTC.
- **Optional fields omitted when absent.** `distance`, `kcal_burned` and `base_movement_quantity` are only set if the source field is present and non-None.
- **Steps live here.** `ieee:physical-activity:1.0` models step count as `base_movement_quantity` (unit `steps`), which is why OMH deprecated `step-count:3.0` in its favor.

### Not mapped (gaps)

| Oura field | Reason |
|---|---|
| `low_activity_time` | dicristea maps to IEEE `physical-activity:1.0` duration fields. No OMH equivalent. |
| `medium_activity_time` | Same |
| `high_activity_time` | Same |
| `*_met_minutes` | No standard equivalent |
| `non_wear_time` | Device metadata, not a health measurement |
| `score` | Oura-proprietary |
| `total_calories` | Includes BMR; `active_calories` is the clinically relevant subset |

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
