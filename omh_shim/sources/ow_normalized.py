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


def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=heart_rate."""
    return {
        "heart_rate": unit_value(sample["value"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


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


def physical_activity(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: OW ActivitySummary with optional distance/calories."""
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["date"], tz=tz)},
    }
    set_optional(out, "distance", sample, "distance_meters", unit="m")
    set_optional(out, "kcal_burned", sample, "active_calories_kcal", unit="kcal")
    set_optional(out, "base_movement_quantity", sample, "steps", unit="steps", cast=int)
    return out


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
