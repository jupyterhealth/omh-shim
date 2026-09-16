"""omh-shim: convert wearable health data to IEEE 1752 and Open mHealth schemas."""

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any

from omh_shim import _dispatch, _schema_loader, _validate
from omh_shim._helpers import build_header
from omh_shim._schema_loader import HEADER_SCHEMA_ID, known_ids
from omh_shim._schema_loader import load as load_schema
from omh_shim.errors import ConversionError, ValidationError

__all__ = [
    "convert",
    "ConversionError",
    "ValidationError",
    "SCHEMA_IDS",
    "known_ids",
    "load_schema",
]
__version__ = "2.0.0"

_NAMESPACE_PRECEDENCE: tuple[str, ...] = ("ieee", "omh")
"""Body-schema standards in preference order. No other namespace is permitted:
omh-shim emits standard schemas only, and converts nothing it cannot name."""

_SCHEMA_CANDIDATES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "heart_rate": ("omh:heart-rate:2.0",),
    "sleep_duration": ("ieee:total-sleep-time:1.0",),
    "sleep_episode": ("ieee:sleep-episode:1.0",),
    "physical_activity": ("ieee:physical-activity:1.0",),
    "oxygen_saturation": ("omh:oxygen-saturation:2.0",),
    "blood_glucose": ("omh:blood-glucose:4.0",),
})
"""data_type -> candidate schema ids. A candidate must name the same measure as
its data_type or the successor that measure's deprecated Open mHealth schema
declares, and may not itself be deprecated; IEEE 1752 wins over Open mHealth
when both are vendored."""


def _successor_name(superseded_by: str) -> str:
    """Measure name from a supersededBy value: a w3id URL or an ``ns:name:ver`` schema id."""
    tail = superseded_by.rsplit("/", 1)[-1].removesuffix(".json")
    return tail.split(":")[1] if ":" in tail else tail


def _vendored_omh_measures() -> frozenset[str]:
    """Measure names of the vendored ``omh:`` schemas."""
    return frozenset(
        schema_id.split(":")[1]
        for schema_id in _schema_loader.known_ids()
        if schema_id.startswith("omh:")
    )


def _declared_successor(expected_name: str) -> str | None:
    """Successor name the vendored deprecated ``omh:<expected_name>:*`` schema declares.

    Sorted and deprecation-preferring: if two versions of the same measure were ever
    vendored, one deprecated and one not, an unordered first-match would flip the
    answer with ``PYTHONHASHSEED``. Returns ``None`` when no vendored ``omh:`` schema
    of that measure is deprecated (including when none is vendored at all).
    """
    for schema_id in sorted(_schema_loader.known_ids()):
        namespace, name, _version = schema_id.split(":")
        if namespace != "omh" or name != expected_name:
            continue
        deprecation = _schema_loader.load(schema_id).get("deprecation")
        if deprecation is None:
            continue
        superseded_by = deprecation.get("supersededBy")
        if not superseded_by:
            raise RuntimeError(
                f"{schema_id}: deprecation block declares no 'supersededBy' — "
                f"omh-shim cannot follow a successor its publisher did not name"
            )
        # The successor's namespace is discarded on purpose: rule 1 (IEEE-first) picks it.
        return _successor_name(superseded_by)
    return None


def _resolve(data_type: str, candidates: tuple[str, ...]) -> str:
    """Return the preferred vendored schema id for ``data_type``.

    Ranks candidates by ``_NAMESPACE_PRECEDENCE`` rather than trusting the
    order they were declared in, so a mis-typed table cannot silently emit the
    wrong standard. Raises ``RuntimeError`` on a malformed candidate id, an
    unknown namespace, a vendored candidate its publisher has deprecated, a
    candidate whose measure name neither matches the data type nor is the
    successor that measure's Open mHealth schema declares, more than one
    candidate in the same namespace, or a type with no vendored candidate.
    """
    expected_name = data_type.replace("_", "-")
    ranked = []
    seen_namespaces: set[str] = set()
    for candidate in candidates:
        parts = candidate.split(":")
        if len(parts) != 3:
            raise RuntimeError(
                f"{data_type}: malformed candidate {candidate!r} "
                f"(expected 'namespace:name:version')"
            )
        namespace, name, _version = parts
        if namespace not in _NAMESPACE_PRECEDENCE:
            raise RuntimeError(
                f"{data_type}: unknown namespace in {candidate!r} "
                f"(expected one of {_NAMESPACE_PRECEDENCE})"
            )
        # Only a vendored candidate can be inspected; an unvendored one fails the closing check.
        if candidate in _schema_loader.known_ids():
            deprecation = _schema_loader.load(candidate).get("deprecation")
            if deprecation is not None:
                raise RuntimeError(
                    f"{data_type}: candidate {candidate!r} is deprecated by its publisher "
                    f"in favor of {deprecation.get('supersededBy')!r} — omh-shim never "
                    f"emits a deprecated schema"
                )
        if name != expected_name:
            successor = _declared_successor(expected_name)
            if successor is None:
                if expected_name not in _vendored_omh_measures():
                    raise RuntimeError(
                        f"{data_type}: candidate {candidate!r} has name {name!r}, expected "
                        f"{expected_name!r} — no Open mHealth schema for {expected_name!r} is "
                        f"vendored, so no successor can be read; omh-shim does not infer equivalents"
                    )
                raise RuntimeError(
                    f"{data_type}: candidate {candidate!r} has name {name!r}, expected "
                    f"{expected_name!r} — vendored omh:{expected_name} is not deprecated and "
                    f"declares no successor; omh-shim does not infer equivalents"
                )
            if name != successor:
                raise RuntimeError(
                    f"{data_type}: candidate {candidate!r} has name {name!r}, but the "
                    f"declared successor of {expected_name!r} is {successor!r}"
                )
        if namespace in seen_namespaces:
            raise RuntimeError(
                f"{data_type}: namespace {namespace!r} appears more than once in "
                f"{list(candidates)} — one candidate per namespace keeps preference unambiguous"
            )
        seen_namespaces.add(namespace)
        ranked.append((_NAMESPACE_PRECEDENCE.index(namespace), candidate))
    vendored = _schema_loader.known_ids()
    for _rank, candidate in sorted(ranked):
        if candidate in vendored:
            return candidate
    raise RuntimeError(f"{data_type}: no candidate is vendored: {list(candidates)}")


SCHEMA_IDS: Mapping[str, str] = MappingProxyType(
    {dt: _resolve(dt, c) for dt, c in _SCHEMA_CANDIDATES.items()}
)
"""Read-only mapping of data_type -> resolved schema id."""

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

    ``tz`` is required for daily data types (physical_activity,
    sleep_duration, oxygen_saturation) — pass ``datetime.UTC`` or a ``ZoneInfo``.

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
