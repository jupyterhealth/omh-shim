#!/usr/bin/env python3
"""Refresh vendored OMH schemas from openmhealth/schemas at a pinned ref.

By default the script verifies the 6 vendored top-level schemas against the
ref recorded in ``omh_shim/schemas/_pinned.json``. Pass ``--omh-ref <tag-or-sha>``
to fetch a different ref; when changes are confirmed, the pinned ref is
updated automatically. The local HRV placeholder is intentionally excluded.

Run from the repo root::

    python tools/refresh_schemas.py                     # verify against pinned ref
    python tools/refresh_schemas.py --omh-ref v1.0.0    # bump to a tag
    python tools/refresh_schemas.py --omh-ref 7969045   # bump to a SHA

Standard library only — no extra deps.
"""

import argparse
import datetime
import difflib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "omh_shim" / "schemas"
PINNED_PATH = SCHEMAS_DIR / "_pinned.json"
RAW_BASE = "https://raw.githubusercontent.com/openmhealth/schemas"

# Top-level schemas to refresh. The local HRV placeholder is excluded.
TARGETS: list[tuple[str, str]] = [
    # (vendored filename, upstream path within schema/omh/)
    ("omh_heart-rate_2-0.json", "heart-rate-2.0.json"),
    ("omh_step-count_3-0.json", "step-count-3.0.json"),
    ("omh_sleep-duration_2-0.json", "sleep-duration-2.0.json"),
    ("omh_sleep-episode_1-1.json", "sleep-episode-1.1.json"),
    ("omh_physical-activity_1-2.json", "physical-activity-1.2.json"),
    ("omh_oxygen-saturation_2-0.json", "oxygen-saturation-2.0.json"),
]


def read_pinned(pinned_path: Path, *, family: str) -> str:
    """Read the pinned ref for a schema family ('omh' or 'ieee') from JSON."""
    data = json.loads(pinned_path.read_text())
    return data[family]["ref"]


def write_pinned(pinned_path: Path, *, family: str, new_ref: str, today: str) -> None:
    """Update the recorded ref + fetched date for a schema family.

    Preserves other families' entries.
    """
    data = json.loads(pinned_path.read_text())
    data[family]["ref"] = new_ref
    data[family]["fetched"] = today
    pinned_path.write_text(json.dumps(data, indent=2) + "\n")


def _resolve_ref(arg_ref: str | None, family: str) -> tuple[str, bool]:
    """Return (ref_to_use, was_passed_explicitly).

    Precedence: CLI arg > _pinned.json. Raises SystemExit if neither exists.
    """
    if arg_ref:
        return arg_ref, True
    try:
        return read_pinned(PINNED_PATH, family=family), False
    except (FileNotFoundError, KeyError):
        try:
            display_path = PINNED_PATH.relative_to(REPO_ROOT)
        except ValueError:
            display_path = PINNED_PATH
        raise SystemExit(
            f"No '{family}' ref recorded in {display_path}. "
            f"Pass --{family}-ref <tag-or-sha> or record one."
        )


def fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} fetching {url}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh vendored OMH schemas at a pinned ref.")
    parser.add_argument(
        "--omh-ref",
        help="Tag or SHA from openmhealth/schemas. Defaults to the ref in _pinned.json.",
    )
    args = parser.parse_args(argv)

    ref, ref_was_explicit = _resolve_ref(args.omh_ref, family="omh")
    print(f"openmhealth/schemas ref: {ref}")
    print()

    diffs: dict[str, tuple[str, str]] = {}
    for vendored, upstream in TARGETS:
        url = f"{RAW_BASE}/{ref}/schema/omh/{upstream}"
        new_content = fetch(url)
        local_path = SCHEMAS_DIR / vendored
        old_content = local_path.read_text() if local_path.exists() else ""

        if old_content == new_content:
            print(f"  unchanged: {vendored}")
            continue

        diff = "\n".join(
            difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                fromfile=f"current/{vendored}",
                tofile=f"upstream/{vendored}",
                lineterm="",
            )
        )
        diffs[vendored] = (new_content, diff)
        print(f"  CHANGED:   {vendored}")
        print(diff)
        print()

    if not diffs:
        print("All vendored schemas are up to date. No changes needed.")
        return 0

    answer = input(f"Update {len(diffs)} file(s)? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted. No files changed.")
        return 1

    for vendored, (new_content, _diff) in diffs.items():
        (SCHEMAS_DIR / vendored).write_text(new_content)
        print(f"  wrote {vendored}")

    if ref_was_explicit:
        today = datetime.date.today().isoformat()
        write_pinned(PINNED_PATH, family="omh", new_ref=ref, today=today)
        print(f"  updated {PINNED_PATH.relative_to(REPO_ROOT)} omh ref -> {ref} ({today})")

    print()
    print("Re-run pytest to confirm everything still validates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
