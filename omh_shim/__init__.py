"""omh-shim: convert wearable health data to Open mHealth schemas."""

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any

from omh_shim import _dispatch, _schema_loader, _validate
from omh_shim._helpers import build_header
from omh_shim._schema_loader import HEADER_SCHEMA_ID
from omh_shim.errors import ConversionError, ValidationError

__all__ = ["convert", "ConversionError", "ValidationError", "SCHEMA_IDS"]
__version__ = "1.0.2"

SCHEMA_IDS: Mapping[str, str] = MappingProxyType({
    "heart_rate": "omh:heart-rate:2.0",
    "heart_rate_variability": "local:heart-rate-variability:1.0",
    "step_count": "omh:step-count:3.0",
    "sleep_duration": "omh:sleep-duration:2.0",
    "sleep_episode": "omh:sleep-episode:1.1",
    "physical_activity": "omh:physical-activity:1.2",
    "oxygen_saturation": "omh:oxygen-saturation:2.0",
})
"""Read-only mapping of data_type -> schema id. ``heart_rate_variability``
uses a ``local:`` namespace placeholder (OMH has no canonical HRV schema)."""

# Fail fast if someone adds a converter without a schema id (or vice versa),
# or a schema id without a loader filename entry. Uses raise (not assert)
# so it survives python -O.
_registered = {dt for (_, dt) in _dispatch.REGISTRY}
if _registered != SCHEMA_IDS.keys():
    raise RuntimeError(f"REGISTRY/SCHEMA_IDS drift: {_registered ^ SCHEMA_IDS.keys()}")
# SCHEMA_IDS values must be a subset of loader entries (not equality),
# because the loader also serves non-body schemas like ieee:header:1.0
# that don't correspond to a convert() data_type.
if not set(SCHEMA_IDS.values()) <= _schema_loader.known_ids():
    raise RuntimeError(
        f"SCHEMA_IDS/loader drift: {set(SCHEMA_IDS.values()) - _schema_loader.known_ids()}"
    )
del _registered


_SOURCE_DEVICE_MAP: Mapping[str, str] = MappingProxyType({
    "oura_raw": "Oura Ring",
})


def _extract_datasheets(
    sample: Mapping[str, Any], *, source: str | None = None,
) -> list[dict[str, str]] | None:
    """Extract external_datasheets from the sample's source metadata.

    OW normalized samples include ``source.provider`` and ``source.device``
    as a nested dict; that more-specific metadata wins when present. Raw
    samples (e.g. ``oura_raw``) don't carry a source field — for those, the
    device is implicit from the ``source`` parameter and resolved via
    ``_SOURCE_DEVICE_MAP``.
    """
    source_meta = sample.get("source") if isinstance(sample, Mapping) else None
    if isinstance(source_meta, Mapping):
        device = source_meta.get("device") or source_meta.get("device_model")
        provider = source_meta.get("provider") or source_meta.get("source_name")
        ref = device or provider
        if ref:
            return [{"datasheet_type": "manufacturer", "datasheet_reference": str(ref)}]
    if source and source in _SOURCE_DEVICE_MAP:
        return [{
            "datasheet_type": "manufacturer",
            "datasheet_reference": _SOURCE_DEVICE_MAP[source],
        }]
    return None


def convert(
    source: str,
    data_type: str,
    sample: Mapping[str, Any],
    *,
    tz: tzinfo | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Convert one source sample to one Open mHealth data-point.

    Always returns the full IEEE 1752.1 data-point envelope::

        {"header": {...}, "body": {...}}

    The header includes ``uuid``, ``schema_id``, ``source_creation_date_time``,
    ``modality``, and ``external_datasheets`` (auto-populated from the sample's
    source metadata when available).

    ``tz`` is required for daily data types (step_count, physical_activity,
    sleep_duration) — pass ``datetime.UTC`` or a ``ZoneInfo``.

    Raises ``ConversionError`` on invalid input, ``ValidationError`` on
    schema mismatch (when ``validate=True``).
    """
    converter = _dispatch.lookup(source, data_type)
    try:
        body = converter(sample, tz=tz)
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(
            f"{source}/{data_type}: {type(e).__name__}: {e}"
        ) from e
    schema_id = SCHEMA_IDS[data_type]
    if validate:
        _validate.validate_output(body, schema_id)
    header = build_header(
        schema_id,
        external_datasheets=_extract_datasheets(sample, source=source),
    )
    if validate:
        _validate.validate_output(header, HEADER_SCHEMA_ID)
    return {"header": header, "body": body}
