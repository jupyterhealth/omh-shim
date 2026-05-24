"""Unit tests for tools/refresh_schemas.py helpers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import refresh_schemas  # noqa: E402


def test_parse_readme_ref_extracts_sha():
    text = (
        "These schemas are vendored from openmhealth/schemas\n"
        "at commit `36078a89e5e5efeba8dfc590a81cc42fd140c815` (main, fetched 2026-04-09).\n"
    )
    assert refresh_schemas.parse_readme_ref(text) == "36078a89e5e5efeba8dfc590a81cc42fd140c815"


def test_parse_readme_ref_extracts_tag():
    text = "at commit `v1.0.0` (fetched 2026-05-01).\n"
    assert refresh_schemas.parse_readme_ref(text) == "v1.0.0"


def test_parse_readme_ref_raises_when_missing():
    with pytest.raises(ValueError, match="No ref found"):
        refresh_schemas.parse_readme_ref("README with no ref line.\n")
