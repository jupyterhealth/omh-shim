"""(source, data_type) -> converter function lookup."""

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any, Protocol

from omh_shim.errors import ConversionError
from omh_shim.sources import oura_raw, ow_normalized


class _Converter(Protocol):
    def __call__(
        self, sample: Mapping[str, Any], *, tz: tzinfo | None
    ) -> dict[str, Any]: ...


REGISTRY: Mapping[tuple[str, str], _Converter] = MappingProxyType({
    ("oura_raw", "heart_rate"):              oura_raw.heart_rate,
    ("oura_raw", "heart_rate_variability"):  oura_raw.heart_rate_variability,
    ("oura_raw", "step_count"):              oura_raw.step_count,
    ("oura_raw", "sleep_duration"):          oura_raw.sleep_duration,
    ("oura_raw", "sleep_episode"):           oura_raw.sleep_episode,
    ("oura_raw", "physical_activity"):       oura_raw.physical_activity,
    ("oura_raw", "oxygen_saturation"):       oura_raw.oxygen_saturation,
    ("ow_normalized", "heart_rate"):             ow_normalized.heart_rate,
    ("ow_normalized", "heart_rate_variability"): ow_normalized.heart_rate_variability,
    ("ow_normalized", "step_count"):             ow_normalized.step_count,
    ("ow_normalized", "sleep_duration"):         ow_normalized.sleep_duration,
    ("ow_normalized", "sleep_episode"):          ow_normalized.sleep_episode,
    ("ow_normalized", "physical_activity"):      ow_normalized.physical_activity,
    ("ow_normalized", "oxygen_saturation"):      ow_normalized.oxygen_saturation,
})


def lookup(source: str, data_type: str) -> _Converter:
    """Return the registered converter, or raise ``ConversionError``."""
    try:
        return REGISTRY[(source, data_type)]
    except KeyError as e:
        raise ConversionError(
            f"No converter for source={source!r} data_type={data_type!r}"
        ) from e
