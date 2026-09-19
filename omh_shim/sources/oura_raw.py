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
    """Input: a heartrate item ``{"bpm", "source", "timestamp"}`` or a sleep item (``lowest_heart_rate``)."""
    if "bedtime_start" in sample:
        frame = _sleep_interval(sample)
        lowest = require(sample, "lowest_heart_rate", context="oura_raw heart_rate (sleep record)")
        return {
            "heart_rate": unit_value(lowest, "beats/min"),
            "effective_time_frame": frame,
            "temporal_relationship_to_sleep": "during sleep",
            "descriptive_statistic": "minimum",
        }
    return {
        "heart_rate": unit_value(sample["bpm"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


# Oura caps ``sleep`` at 3 h, so only ``long_sleep`` (>3 h) is main sleep; OW's is_nap rule agrees.
_MAIN_SLEEP_TYPES = frozenset({"long_sleep"})
_NOT_MAIN_SLEEP_TYPES = frozenset({"sleep", "late_nap"})
_REJECTED_SLEEP_TYPES = frozenset({"rest", "deleted"})


def _sleep_interval(sample: Mapping[str, Any]) -> dict[str, Any]:
    """effective_time_frame for an Oura sleep item (bedtime_start/bedtime_end)."""
    # Every sleep-derived body starts here, so a 'rest' (user-rejected false detection) or
    # 'deleted' record is rejected once for all data types, as OW also skips both.
    if (sleep_type := sample.get("type")) in _REJECTED_SLEEP_TYPES:
        raise ConversionError(f"oura_raw sleep record type {sleep_type!r} is not converted")
    return {"time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])}


def _is_main_sleep(sample: Mapping[str, Any]) -> bool | None:
    """Oura v2 ``PublicSleepType`` -> is_main_sleep; ``None`` when the type is absent or unmapped."""
    sleep_type = sample.get("type")
    if sleep_type in _MAIN_SLEEP_TYPES:
        return True
    if sleep_type in _NOT_MAIN_SLEEP_TYPES:
        return False
    # An unpublished type does not make the measurements wrong, only the main/nap label
    # unknown — the same policy as an unmapped workout ``intensity``.
    return None


def sleep_duration(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i] with ``total_sleep_duration`` in seconds."""
    frame = _sleep_interval(sample)
    total = require(sample, "total_sleep_duration", context="oura_raw sleep_duration")
    out: dict[str, Any] = {
        "total_sleep_time": unit_value(total, "sec", cast=int),
        "effective_time_frame": frame,
    }
    if (is_main := _is_main_sleep(sample)) is not None:
        out["is_main_sleep"] = is_main
    return out


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


_OURA_INTENSITY = {"easy": "light", "moderate": "moderate", "hard": "vigorous"}


def _daily_activity(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["day"], tz=tz)},
    }
    set_optional(out, "distance", sample, "equivalent_walking_distance", unit="m")
    set_optional(out, "kcal_burned", sample, "active_calories", unit="kcal")
    set_optional(out, "base_movement_quantity", sample, "steps", unit="steps", cast=int)
    # Oura's low/medium/high are its own activity classes, reported in seconds.
    set_optional(out, "duration_light_activity", sample, "low_activity_time", unit="sec", cast=int)
    set_optional(out, "duration_moderate_activity", sample, "medium_activity_time", unit="sec", cast=int)
    set_optional(out, "duration_vigorous_activity", sample, "high_activity_time", unit="sec", cast=int)
    return out


def _workout(sample: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "activity_name": sample["activity"],
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["start_datetime"], sample["end_datetime"])
        },
    }
    set_optional(out, "distance", sample, "distance", unit="m")
    set_optional(out, "kcal_burned", sample, "calories", unit="kcal")
    intensity = sample.get("intensity")
    if intensity is not None and (level := _OURA_INTENSITY.get(intensity)) is not None:
        out["reported_activity_intensity"] = level
    return out


def physical_activity(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """Input: Oura daily_activity item (has ``day``; needs ``tz``) or workout item (has ``activity`` + ``start_datetime``)."""
    # A workout item also carries ``day``, so the workout check runs first.
    if "activity" in sample and "start_datetime" in sample:
        return _workout(sample)
    if "day" in sample:
        return _daily_activity(sample, tz=tz)
    raise ConversionError(
        "oura_raw physical_activity expects a daily_activity item (with 'day') "
        "or a workout item (with 'activity' and 'start_datetime')"
    )


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
    frame = _sleep_interval(sample)
    breaths = require(sample, "average_breath", context="oura_raw respiratory_rate")
    return {
        "respiratory_rate": unit_value(breaths, "breaths/min"),
        "effective_time_frame": frame,
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


def time_in_bed(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i]; ``time_in_bed`` is seconds."""
    frame = _sleep_interval(sample)
    seconds = require(sample, "time_in_bed", context="oura_raw time_in_bed")
    out: dict[str, Any] = {
        "time_in_bed": unit_value(seconds, "sec", cast=int),
        "effective_time_frame": frame,
    }
    if (is_main := _is_main_sleep(sample)) is not None:
        out["is_main_sleep"] = is_main
    return out


def sleep_stage_summary(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Input: Oura sleep/data[i]; stage durations are seconds."""
    frame = _sleep_interval(sample)
    total = require(sample, "total_sleep_duration", context="oura_raw sleep_stage_summary")
    summary: dict[str, Any] = {"total_sleep_time": unit_value(total, "sec", cast=int)}
    set_optional(summary, "light_sleep_duration", sample, "light_sleep_duration", unit="sec", cast=int)
    set_optional(summary, "deep_sleep_duration", sample, "deep_sleep_duration", unit="sec", cast=int)
    set_optional(summary, "rem_sleep_duration", sample, "rem_sleep_duration", unit="sec", cast=int)
    set_optional(summary, "awake_duration", sample, "awake_time", unit="sec", cast=int)
    set_optional(summary, "latency_to_sleep_onset", sample, "latency", unit="sec", cast=int)
    set_optional(summary, "sleep_efficiency_percentage", sample, "efficiency", unit="%")
    out: dict[str, Any] = {
        "sleep_stage_summary": summary,
        "effective_time_frame": frame,
    }
    if (is_main := _is_main_sleep(sample)) is not None:
        out["is_main_sleep"] = is_main
    return out
