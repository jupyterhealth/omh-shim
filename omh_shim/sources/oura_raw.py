"""Converters for raw Oura v2 API response items -> Open mHealth schemas.

Mapping logic ported with permission from dicristea/oura-clinical-workbench.
See AUTHORS.md.
"""

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
from omh_shim.errors import ConversionError


def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: ``{"bpm": 72, "source": "sleep", "timestamp": "...+00:00"}``"""
    return {
        "heart_rate": unit_value(sample["bpm"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def heart_rate_variability(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Accepts ``rmssd`` or ``contributors.hrv_balance_ms`` (real ms values).
    Rejects the normalized 0-100 ``hrv_balance`` score."""
    if "rmssd" in sample:
        value_ms = sample["rmssd"]
    elif isinstance(sample.get("contributors"), dict) and "hrv_balance_ms" in sample["contributors"]:
        value_ms = sample["contributors"]["hrv_balance_ms"]
    else:
        raise ConversionError(
            "oura_raw heart_rate_variability requires either 'rmssd' or "
            "'contributors.hrv_balance_ms' — the normalized 0-100 hrv_balance "
            "score is not a valid HRV measurement in milliseconds"
        )

    timestamp = sample.get("timestamp") or sample.get("day")
    if timestamp is None:
        raise ConversionError(
            "oura_raw heart_rate_variability requires 'timestamp' or 'day'"
        )

    return {
        "heart_rate_variability": unit_value(value_ms, "ms"),
        "effective_time_frame": date_time_frame(timestamp),
    }


def step_count(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: ``{"day": "2026-04-09", "steps": 8432, ...}``"""
    return {
        "step_count": unit_value(sample["steps"], "steps", cast=int),
        "effective_time_frame": {"time_interval": day_interval(sample["day"], tz=tz)},
    }


def sleep_duration(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i] with ``total_sleep_duration`` in seconds."""
    return {
        "sleep_duration": unit_value(sample["total_sleep_duration"], "sec", cast=int),
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])
        },
    }


def sleep_episode(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i]. Oura's ``long_sleep``/``short_sleep`` are
    both main sleep; only ``nap`` is not."""
    out: dict[str, Any] = {
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])
        }
    }
    set_optional(out, "total_sleep_time", sample, "total_sleep_duration", unit="sec", cast=int)
    set_optional(out, "wake_after_sleep_onset", sample, "awake_time", unit="sec", cast=int)
    set_optional(out, "latency_to_sleep_onset", sample, "latency", unit="sec", cast=int)
    set_optional(out, "sleep_maintenance_efficiency_percentage", sample, "efficiency", unit="%")
    if (sleep_type := sample.get("type")) is not None:
        out["is_main_sleep"] = sleep_type != "nap"
    return out


def physical_activity(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: ``{"day": "2026-04-09", "active_calories": 342, ...}``"""
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["day"], tz=tz)},
    }
    set_optional(out, "distance", sample, "equivalent_walking_distance", unit="m")
    set_optional(out, "kcal_burned", sample, "active_calories", unit="kcal")
    return out


def oxygen_saturation(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: Oura ``daily_spo2/data[i]`` with a nested ``spo2_percentage.average``.

    Example::

        {"day": "2021-01-01", "spo2_percentage": {"average": 93.0}, ...}

    Oura reports SpO2 as a daily aggregate (the nightly average from the
    per-minute measurements the ring takes while the user sleeps), so the
    effective time frame is the full calendar day in ``tz``.
    """
    spo2_pct = sample.get("spo2_percentage")
    if not isinstance(spo2_pct, Mapping) or "average" not in spo2_pct:
        raise ConversionError(
            "oura_raw oxygen_saturation requires 'spo2_percentage.average' "
            "(a nested object with an 'average' field)"
        )
    return {
        "oxygen_saturation": unit_value(spo2_pct["average"], "%"),
        "effective_time_frame": {"time_interval": day_interval(sample["day"], tz=tz)},
    }
