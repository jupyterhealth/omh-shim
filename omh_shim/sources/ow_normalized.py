"""Converters for Open Wearables normalized read-API shapes -> Open mHealth schemas."""

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from omh_shim._helpers import (
    date_time_frame,
    day_interval,
    interval_from_bounds,
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
    """Input: OW ActivitySummary with ``sleep_total_duration_minutes``."""
    return {
        "total_sleep_time": unit_value(
            sample["sleep_total_duration_minutes"] * 60, "sec", cast=int
        ),
        "effective_time_frame": {"time_interval": day_interval(sample["date"], tz=tz)},
    }


def sleep_episode(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW sleep detail with bedtime_start/end and optional fields."""
    out: dict[str, Any] = {
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])
        }
    }
    set_optional(
        out, "total_sleep_time", sample, "sleep_total_duration_minutes",
        unit="sec", cast=int, scale=60,
    )
    set_optional(
        out, "wake_after_sleep_onset", sample, "sleep_awake_minutes",
        unit="sec", cast=int, scale=60,
    )
    set_optional(
        out, "sleep_efficiency_percentage", sample,
        "sleep_efficiency_score", unit="%",
    )
    if (is_nap := sample.get("is_nap")) is not None:
        out["is_main_sleep"] = not is_nap
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
