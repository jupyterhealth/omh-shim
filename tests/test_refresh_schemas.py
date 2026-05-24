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


# --- update_readme_ref ---


def test_update_readme_ref_rewrites_sha_and_date():
    text = (
        "Header line\n"
        "at commit `oldsha` (main, fetched 2026-04-09).\n"
        "Trailing content.\n"
    )
    out = refresh_schemas.update_readme_ref(text, new_ref="newsha", today="2026-05-24")
    assert "at commit `newsha` (fetched 2026-05-24)." in out
    assert "oldsha" not in out
    assert "Header line\n" in out
    assert "Trailing content.\n" in out


def test_update_readme_ref_preserves_other_content():
    text = (
        "# Title\n\n"
        "Some prose with `backticks` and other content.\n"
        "at commit `abc123` (fetched 2026-01-01).\n"
        "More prose.\n"
    )
    out = refresh_schemas.update_readme_ref(text, new_ref="def456", today="2026-05-24")
    assert "Some prose with `backticks` and other content.\n" in out
    assert "More prose.\n" in out
    assert "abc123" not in out


def test_update_readme_ref_raises_when_no_line_to_replace():
    with pytest.raises(ValueError, match="No ref line"):
        refresh_schemas.update_readme_ref(
            "README with no ref line.\n", new_ref="x", today="2026-05-24"
        )
