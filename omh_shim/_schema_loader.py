"""Load vendored OMH JSON schemas by schema id.

Uses an explicit lookup table instead of string substitution to avoid
filename collisions (``omh:a.b:1.0`` and ``omh:a-b:1.0`` would collide
under ``:``->``_``, ``.``->``-`` encoding).
"""

import importlib.resources
import json
from functools import cache
from typing import Any

_FILENAMES: dict[str, str] = {
    "omh:heart-rate:2.0": "data/omh_heart-rate_2-0.json",
    "local:heart-rate-variability:1.0": "data/local_heart-rate-variability_1-0.json",
    "omh:step-count:3.0": "data/omh_step-count_3-0.json",
    "omh:sleep-duration:2.0": "data/omh_sleep-duration_2-0.json",
    "omh:sleep-episode:1.1": "data/omh_sleep-episode_1-1.json",
    "omh:physical-activity:1.2": "data/omh_physical-activity_1-2.json",
    "omh:oxygen-saturation:2.0": "data/omh_oxygen-saturation_2-0.json",
    "omh:blood-glucose:4.0": "data/omh_blood-glucose_4-0.json",
    # Clinical body schemas served to downstream consumers; no converters.
    "omh:blood-pressure:4.0": "data/omh_blood-pressure_4-0.json",
    "omh:body-temperature:4.0": "data/omh_body-temperature_4-0.json",
    "omh:body-weight:3.0": "data/omh_body-weight_3-0.json",
    "omh:forced-expiratory-volume-1-second:1.0": "data/omh_forced-expiratory-volume-1-second_1-0.json",
    "omh:forced-vital-capacity:1.0": "data/omh_forced-vital-capacity_1-0.json",
    "omh:respiratory-rate:2.0": "data/omh_respiratory-rate_2-0.json",
    "omh:rr-interval:1.0": "data/omh_rr-interval_1-0.json",
    # IEEE 1752 body schema (ieee: namespace) served to downstream consumers; no converter.
    "ieee:sleep-stage-summary:1.0": "data/ieee_sleep-stage-summary_1-0.json",
    "ieee:header:1.0": "metadata/header-1.0.json",
}

HEADER_SCHEMA_ID = "ieee:header:1.0"


def known_ids() -> frozenset[str]:
    """Schema ids this loader has filename entries for."""
    return frozenset(_FILENAMES)


@cache
def load(schema_id: str) -> dict[str, Any]:
    """Load a vendored JSON schema by id. Raises KeyError if unknown."""
    filename = _FILENAMES[schema_id]
    resource = importlib.resources.files("omh_shim.schemas").joinpath(filename)
    with resource.open("r", encoding="utf-8") as f:
        loaded: dict[str, Any] = json.load(f)
    return loaded
