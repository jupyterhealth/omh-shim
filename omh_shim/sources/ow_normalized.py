"""Converters for Open Wearables normalized read-API shapes -> Open mHealth schemas."""

from collections.abc import Mapping
from datetime import timedelta, tzinfo
from typing import Any

from omh_shim._helpers import (
    date_time_frame,
    day_interval,
    interval_from_bounds,
    isoformat,
    parse_datetime,
    set_optional,
    unit_value,
)
from omh_shim.errors import ConversionError


def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=heart_rate."""
    return {
        "heart_rate": unit_value(sample["value"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def heart_rate_variability(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: OW TimeSeriesSample with type=heart_rate_variability."""
    return {
        "heart_rate_variability": unit_value(sample["value"], "ms"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def step_count(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Two shapes: ActivitySummary (``date`` + ``steps``) or TimeSeriesSample
    (``timestamp`` + ``type=steps`` + ``value``). The latter builds a 1-minute
    interval because OMH step-count requires time_interval, not date_time."""
    if "date" in sample:
        steps = sample["steps"]
        time_interval = day_interval(sample["date"], tz=tz)
    elif "timestamp" in sample and sample.get("type") == "steps":
        steps = sample["value"]
        end = parse_datetime(sample["timestamp"])
        start = end - timedelta(minutes=1)
        time_interval = {"start_date_time": isoformat(start), "end_date_time": isoformat(end)}
    else:
        raise ConversionError(
            "ow_normalized step_count input must have either {'date', 'steps'} "
            "or {'timestamp', 'type': 'steps', 'value'}"
        )
    return {
        "step_count": unit_value(steps, "steps", cast=int),
        "effective_time_frame": {"time_interval": time_interval},
    }


def sleep_duration(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: OW ActivitySummary with ``sleep_total_duration_minutes``."""
    return {
        "sleep_duration": unit_value(
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
        out, "sleep_maintenance_efficiency_percentage", sample,
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
