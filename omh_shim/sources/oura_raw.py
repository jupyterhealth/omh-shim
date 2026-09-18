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
    require,
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


_MAIN_SLEEP_TYPES = frozenset({"sleep", "long_sleep"})
_NOT_MAIN_SLEEP_TYPES = frozenset({"late_nap", "rest"})


def _sleep_interval(sample: Mapping[str, Any]) -> dict[str, Any]:
    """effective_time_frame for an Oura sleep item (bedtime_start/bedtime_end)."""
    # Every sleep-derived body starts here, so a deleted record is rejected once for all data types.
    if sample.get("type") == "deleted":
        raise ConversionError("oura_raw sleep record type 'deleted' is not converted")
    return {"time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])}


def _is_main_sleep(sample: Mapping[str, Any]) -> bool | None:
    """Oura v2 ``PublicSleepType`` -> is_main_sleep; ``None`` when the record has no type."""
    sleep_type = sample.get("type")
    if sleep_type is None:
        return None
    if sleep_type in _MAIN_SLEEP_TYPES:
        return True
    if sleep_type in _NOT_MAIN_SLEEP_TYPES:
        return False
    # 'deleted' is caught in _sleep_interval; anything here is a value Oura has not published.
    raise ConversionError(f"oura_raw sleep record type {sleep_type!r} is not converted")


def sleep_duration(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i] with ``total_sleep_duration`` in seconds."""
    return {
        "total_sleep_time": unit_value(sample["total_sleep_duration"], "sec", cast=int),
        "effective_time_frame": _sleep_interval(sample),
    }


def sleep_episode(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i]."""
    out: dict[str, Any] = {"effective_time_frame": _sleep_interval(sample)}
    set_optional(out, "total_sleep_time", sample, "total_sleep_duration", unit="sec", cast=int)
    set_optional(out, "light_sleep_duration", sample, "light_sleep_duration", unit="sec", cast=int)
    set_optional(out, "deep_sleep_duration", sample, "deep_sleep_duration", unit="sec", cast=int)
    set_optional(out, "rem_sleep_duration", sample, "rem_sleep_duration", unit="sec", cast=int)
    # Approximation: Oura's awake_time includes the latency it also reports separately.
    set_optional(out, "wake_after_sleep_onset", sample, "awake_time", unit="sec", cast=int)
    set_optional(out, "latency_to_sleep_onset", sample, "latency", unit="sec", cast=int)
    set_optional(out, "sleep_efficiency_percentage", sample, "efficiency", unit="%")
    if (is_main := _is_main_sleep(sample)) is not None:
        out["is_main_sleep"] = is_main
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
    set_optional(out, "base_movement_quantity", sample, "steps", unit="steps", cast=int)
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


def _profile_timestamp(sample: Mapping[str, Any], data_type: str) -> Any:
    """Oura personal_info carries no measurement time; the caller stamps one (OW stamps sync time)."""
    timestamp = sample.get("timestamp")
    if timestamp is None:
        raise ConversionError(
            f"oura_raw {data_type} requires a caller-supplied 'timestamp'; "
            "Oura personal_info carries none"
        )
    return timestamp


def respiratory_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i]; ``average_breath`` is the average over the sleep."""
    breaths = require(sample, "average_breath", context="oura_raw respiratory_rate")
    return {
        "respiratory_rate": unit_value(breaths, "breaths/min"),
        "effective_time_frame": _sleep_interval(sample),
        "descriptive_statistic": "average",
    }


def body_weight(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura personal_info (``weight`` in kg) plus a caller-supplied ``timestamp``."""
    return {
        "body_weight": unit_value(require(sample, "weight", context="oura_raw body_weight"), "kg"),
        "effective_time_frame": date_time_frame(_profile_timestamp(sample, "body_weight")),
    }


def body_height(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura personal_info (``height`` in metres) plus a caller-supplied ``timestamp``."""
    return {
        "body_height": unit_value(require(sample, "height", context="oura_raw body_height"), "m"),
        "effective_time_frame": date_time_frame(_profile_timestamp(sample, "body_height")),
    }
