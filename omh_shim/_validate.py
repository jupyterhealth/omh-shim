"""Validate converter outputs against vendored OMH schemas.

OMH schemas use ``$ref`` to reference other schemas by relative filename
(e.g. ``"unit-value-1.x.json"``). All transitively-referenced schemas are
vendored alongside the top-level OMH schemas in ``omh_shim/schemas/`` so
ref resolution can be served from local files without network access.
"""

import importlib.resources
import json
from functools import lru_cache
from typing import Any

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


@lru_cache(maxsize=1)
def _registry() -> Registry:
    """Build a referencing.Registry that serves every vendored schema by filename."""
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
            resources.append((name, Resource.from_contents(doc, default_specification=DRAFT7)))
    return Registry().with_resources(resources)


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
