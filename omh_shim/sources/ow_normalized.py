"""Converters for Open Wearables normalized read-API shapes -> Open mHealth schemas."""

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from omh_shim._helpers import (
    date_time_frame,
    day_interval,
    interval_from_bounds,
    require,
    set_optional,
    unit_value,
)
from omh_shim.errors import ConversionError


def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=heart_rate or type=resting_heart_rate."""
    out: dict[str, Any] = {
        "heart_rate": unit_value(sample["value"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }
    # OW's resting series is provider-generic; for Oura it is the per-night lowest HR during sleep.
    if sample.get("type") == "resting_heart_rate":
        out["temporal_relationship_to_sleep"] = "during sleep"
    return out


def sleep_duration(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW SleepSummary from ``GET /users/{id}/summaries/sleep``."""
    # duration_minutes excludes naps (OW's own definition), hence is_main_sleep is fixed true.
    minutes = require(sample, "duration_minutes", context="ow_normalized sleep_duration")
    return {
        "total_sleep_time": unit_value(minutes * 60, "sec", cast=int),
        "effective_time_frame": {"time_interval": day_interval(sample["date"], tz=tz)},
        "is_main_sleep": True,
    }


def _session_interval(sample: Mapping[str, Any]) -> dict[str, Any]:
    """effective_time_frame for an OW SleepSession (start_time/end_time carry offsets)."""
    return {"time_interval": interval_from_bounds(sample["start_time"], sample["end_time"])}


def _is_main_sleep(sample: Mapping[str, Any]) -> bool:
    # OW always serialises is_nap (default false), so the flag is always emitted.
    return not bool(sample.get("is_nap", False))


def sleep_episode(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW SleepSession from ``GET /users/{id}/events/sleep``."""
    stages = sample.get("stages") or {}
    out: dict[str, Any] = {"effective_time_frame": _session_interval(sample)}
    set_optional(out, "total_sleep_time", sample, "sleep_duration_seconds", unit="sec", cast=int)
    set_optional(out, "light_sleep_duration", stages, "light_minutes", unit="sec", cast=int, scale=60)
    set_optional(out, "deep_sleep_duration", stages, "deep_minutes", unit="sec", cast=int, scale=60)
    set_optional(out, "rem_sleep_duration", stages, "rem_minutes", unit="sec", cast=int, scale=60)
    # Approximation: Oura's awake time includes onset latency, and OW drops latency.
    set_optional(out, "wake_after_sleep_onset", stages, "awake_minutes", unit="sec", cast=int, scale=60)
    set_optional(out, "sleep_efficiency_percentage", sample, "efficiency_percent", unit="%")
    out["is_main_sleep"] = _is_main_sleep(sample)
    return out


_OW_INTENSITY = {"low": "light", "moderate": "moderate", "high": "vigorous"}


def _daily_summary(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["date"], tz=tz)},
    }
    set_optional(out, "distance", sample, "distance_meters", unit="m")
    set_optional(out, "kcal_burned", sample, "active_calories_kcal", unit="kcal")
    set_optional(out, "base_movement_quantity", sample, "steps", unit="steps", cast=int)
    set_optional(out, "duration", sample, "active_minutes", unit="min", cast=int)
    intensity = sample.get("intensity_minutes") or {}
    set_optional(out, "duration_light_activity", intensity, "light", unit="min", cast=int)
    set_optional(out, "duration_moderate_activity", intensity, "moderate", unit="min", cast=int)
    set_optional(out, "duration_vigorous_activity", intensity, "vigorous", unit="min", cast=int)
    return out


def _workout(sample: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "activity_name": sample["type"],
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["start_time"], sample["end_time"])
        },
    }
    set_optional(out, "duration", sample, "duration_seconds", unit="sec", cast=int)
    set_optional(out, "distance", sample, "distance_meters", unit="m")
    set_optional(out, "kcal_burned", sample, "calories_kcal", unit="kcal")
    set_optional(out, "base_movement_quantity", sample, "steps_count", unit="steps", cast=int)
    intensity = sample.get("intensity")
    # IEEE's enum is light|moderate|vigorous; OW's unknown has no home and is dropped.
    if intensity is not None and (level := _OW_INTENSITY.get(intensity)) is not None:
        out["reported_activity_intensity"] = level
    return out


def physical_activity(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: OW ActivitySummary (has ``date``; needs ``tz``) or OW Workout (has ``start_time``/``end_time``)."""
    if "start_time" in sample and "end_time" in sample:
        return _workout(sample)
    if "date" in sample:
        return _daily_summary(sample, tz=tz)
    raise ConversionError(
        "ow_normalized physical_activity expects an ActivitySummary (with 'date') "
        "or a Workout (with 'start_time' and 'end_time')"
    )


def oxygen_saturation(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=oxygen_saturation."""
    return {
        "oxygen_saturation": unit_value(sample["value"], "%"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def blood_glucose(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=blood_glucose."""
    return {
        "blood_glucose": unit_value(sample["value"], "mg/dL"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def respiratory_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=respiratory_rate (OW unit ``brpm``)."""
    return {
        "respiratory_rate": unit_value(sample["value"], "breaths/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def body_weight(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=weight (OW unit ``kg``)."""
    return {
        "body_weight": unit_value(sample["value"], "kg"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def body_height(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=height (OW unit ``cm``)."""
    return {
        "body_height": unit_value(sample["value"], "cm"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def time_in_bed(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW SleepSession from ``GET /users/{id}/events/sleep``."""
    seconds = require(sample, "time_in_bed_seconds", context="ow_normalized time_in_bed")
    return {
        "time_in_bed": unit_value(seconds, "sec", cast=int),
        "effective_time_frame": _session_interval(sample),
        "is_main_sleep": _is_main_sleep(sample),
    }


def sleep_stage_summary(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW SleepSession from ``GET /users/{id}/events/sleep``."""
    stages = sample.get("stages") or {}
    total = require(sample, "sleep_duration_seconds", context="ow_normalized sleep_stage_summary")
    summary: dict[str, Any] = {"total_sleep_time": unit_value(total, "sec", cast=int)}
    set_optional(summary, "light_sleep_duration", stages, "light_minutes", unit="sec", cast=int, scale=60)
    set_optional(summary, "deep_sleep_duration", stages, "deep_minutes", unit="sec", cast=int, scale=60)
    set_optional(summary, "rem_sleep_duration", stages, "rem_minutes", unit="sec", cast=int, scale=60)
    set_optional(summary, "awake_duration", stages, "awake_minutes", unit="sec", cast=int, scale=60)
    set_optional(summary, "sleep_efficiency_percentage", sample, "efficiency_percent", unit="%")
    return {
        "sleep_stage_summary": summary,
        "effective_time_frame": _session_interval(sample),
        "is_main_sleep": _is_main_sleep(sample),
    }
