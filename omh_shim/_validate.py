"""Validate converter outputs against vendored OMH schemas.

OMH schemas use ``$ref`` to reference other schemas by relative filename
(e.g. ``"unit-value-1.x.json"``). All transitively-referenced schemas are
vendored alongside the top-level OMH schemas in ``omh_shim/schemas/`` so
ref resolution can be served from local files without network access.
"""

import importlib.resources
import json
from functools import lru_cache
from typing import Any, NoReturn

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from omh_shim._schema_loader import load as load_schema
from omh_shim.errors import ValidationError


# maxsize is bounded to a small constant: there are currently 6 top-level
# schema ids (see omh_shim.SCHEMA_IDS). 16 leaves room for future types
# without making the cache unbounded.
@lru_cache(maxsize=16)
def _validator(schema_id: str) -> Draft7Validator:
    """Cached Draft7Validator per schema id. Built once, reused across calls."""
    return Draft7Validator(load_schema(schema_id), registry=_registry())


class _NoNetwork:
    """Retriever that raises instead of fetching unknown $ref URIs.

    Mirrors JHE's pattern in jupyterhealth-exchange/core/utils.py:24-26.
    """

    def __call__(self, uri: str) -> NoReturn:
        raise RuntimeError(f"Remote $ref blocked (not preloaded): {uri}")


@lru_cache(maxsize=1)
def _registry() -> Registry:
    """Build a referencing.Registry that serves every vendored schema.

    Each schema is registered under multiple URIs so $refs resolve regardless
    of how they're written:
    - bare filename (e.g. "header-1.0.json")
    - canonical IEEE w3id URL (metadata/ + utility/ schemas)
    - canonical OMH w3id URL (utility/ schemas, since OMH bodies $ref utility
      schemas using various URI forms)

    Mirrors JHE's referencing.Registry setup in core/utils.py.
    """
    ieee_base = "https://w3id.org/ieee/ieee-1752-schema/"
    omh_base = "https://w3id.org/openmhealth/schemas/omh/"

    schemas_pkg = importlib.resources.files("omh_shim.schemas")
    resources = []
    for subdir in ("metadata", "data", "utility"):
        sub = schemas_pkg.joinpath(subdir)
        if not sub.is_dir():
            continue
        for entry in sub.iterdir():
            name = entry.name
            if not name.endswith(".json"):
                continue
            with entry.open("r", encoding="utf-8") as f:
                doc = json.load(f)
            res = Resource.from_contents(doc, default_specification=DRAFT7)
            resources.append((name, res))
            # Also register under the w3id permalinks so refs like
            # "https://w3id.org/ieee/ieee-1752-schema/<name>" resolve.
            if subdir in ("metadata", "utility"):
                resources.append((ieee_base + name, res))
            if subdir == "utility":
                resources.append((omh_base + name, res))
    return Registry(retrieve=_NoNetwork()).with_resources(resources)  # type: ignore[call-arg]


def validate_output(output: dict[str, Any], schema_id: str) -> None:
    """Validate ``output`` against the OMH schema identified by ``schema_id``.

    Raises ``ValidationError`` with a human-readable message listing all
    violations. Returns ``None`` on success.
    """
    errors = sorted(
        _validator(schema_id).iter_errors(output),
        key=lambda e: list(e.absolute_path),
    )
    if not errors:
        return
    pieces = []
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        pieces.append(f"{path}: {e.message}")
    raise ValidationError(
        f"Output does not conform to {schema_id}: " + "; ".join(pieces)
    )
