"""Shared helpers for source converters."""

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from omh_shim.errors import ConversionError


def parse_datetime(value: Any) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware datetime.

    Rejects naive datetimes — silent UTC coercion is a clinical-data footgun.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            raise ConversionError(f"invalid ISO-8601 datetime: {value!r}") from e
    else:
        raise ConversionError(
            f"expected ISO-8601 datetime string, got {type(value).__name__}"
        )
    if dt.tzinfo is None:
        raise ConversionError(
            f"datetime {value!r} has no timezone; omh-shim requires explicit "
            "timezone offsets to avoid silently misaligning clinical data"
        )
    return dt


def isoformat(dt: datetime) -> str:
    """ISO-8601 with ``Z`` suffix when the offset is UTC."""
    return dt.isoformat().replace("+00:00", "Z")


def day_interval(date_str: str, *, tz: tzinfo | None) -> dict[str, Any]:
    """OMH time_interval covering one calendar day in ``tz``. Raises if
    ``tz`` is None — a "day" in Tokyo is not a "day" in UTC."""
    if tz is None:
        raise ConversionError(
            "this data type requires an explicit timezone — pass tz=... to "
            "convert() so day boundaries reflect the user's local calendar day"
        )
    start = datetime.fromisoformat(date_str).replace(tzinfo=tz)
    end = start + timedelta(days=1)
    return {"start_date_time": isoformat(start), "end_date_time": isoformat(end)}


def interval_from_bounds(start: str, end: str) -> dict[str, Any]:
    """OMH time_interval from explicit start/end ISO-8601 strings."""
    return {
        "start_date_time": isoformat(parse_datetime(start)),
        "end_date_time": isoformat(parse_datetime(end)),
    }


def date_time_frame(timestamp: Any) -> dict[str, Any]:
    """OMH effective_time_frame with a single date_time."""
    return {"date_time": isoformat(parse_datetime(timestamp))}


def unit_value(
    value: Any,
    unit: str,
    cast: Callable[[Any], Any] = float,
) -> dict[str, Any]:
    """OMH unit_value: ``{"value": cast(value), "unit": unit}``."""
    return {"value": cast(value), "unit": unit}


def build_header(
    schema_id: str,
    *,
    external_datasheets: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build an IEEE 1752.1 data-point header per ``header-1.0.json``.

    Properties conform to the IEEE 1752.1 header schema:
    ``uuid``, ``schema_id``, ``source_creation_date_time`` (required);
    ``modality``, ``external_datasheets`` (optional).

    ``acquisition_provenance`` is NOT included — it belongs to the older
    OMH data-point schema, not the IEEE 1752.1 standard.
    """
    namespace, name, version = schema_id.split(":", 2)
    header: dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "schema_id": {
            "namespace": namespace,
            "name": name,
            "version": version,
        },
        "source_creation_date_time": isoformat(datetime.now(UTC)),
        "modality": "sensed",
    }
    if external_datasheets:
        header["external_datasheets"] = external_datasheets
    return header


def set_optional(
    out: dict[str, Any],
    out_key: str,
    sample: Mapping[str, Any],
    field: str,
    *,
    unit: str,
    cast: Callable[[Any], Any] = float,
    scale: float = 1,
) -> None:
    """Set ``out[out_key]`` to a unit_value if ``sample[field]`` is present
    and not None. Scale is applied before cast (so 32.5 min * 60 -> 1950 sec)."""
    v = sample.get(field)
    if v is None:
        return
    out[out_key] = {"value": cast(v * scale), "unit": unit}


def require(sample: Mapping[str, Any], field: str, *, context: str) -> Any:
    """``sample[field]``, or ``ConversionError`` when the key is absent or ``None``."""
    value = sample.get(field)
    if value is None:
        raise ConversionError(f"{context} requires {field!r}")
    return value
