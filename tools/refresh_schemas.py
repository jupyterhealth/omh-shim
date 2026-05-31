#!/usr/bin/env python3
"""Refresh vendored schemas from OMH and IEEE 1752.1 at pinned refs.

By default the script verifies the vendored body + utility (OMH) and
envelope/utility (IEEE 1752.1) schemas against the refs recorded in
``omh_shim/schemas/_pinned.json``. Pass ``--omh-ref`` and/or ``--ieee-ref``
to fetch a different ref for either source; when changes are confirmed, the
pinned ref for any family passed explicitly is updated automatically. The
local HRV placeholder is intentionally excluded.

Run from the repo root::

    python tools/refresh_schemas.py                     # verify against pinned refs
    python tools/refresh_schemas.py --omh-ref v1.0.0    # bump OMH ref to a tag
    python tools/refresh_schemas.py --ieee-ref 1.0.3    # bump IEEE ref
    python tools/refresh_schemas.py --omh-ref ... --ieee-ref ...

Standard library only — no extra deps.
"""

import argparse
import datetime
import difflib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "omh_shim" / "schemas"
PINNED_PATH = SCHEMAS_DIR / "_pinned.json"
RAW_BASE = "https://raw.githubusercontent.com/openmhealth/schemas"
IEEE_RAW_BASE = "https://opensource.ieee.org/omh/1752/-/raw"

# Top-level schemas to refresh. The local HRV placeholder is excluded.
TARGETS: list[tuple[str, str]] = [
    # (vendored filename, upstream path within schema/omh/)
    ("data/omh_heart-rate_2-0.json", "heart-rate-2.0.json"),
    ("data/omh_step-count_3-0.json", "step-count-3.0.json"),
    ("data/omh_sleep-duration_2-0.json", "sleep-duration-2.0.json"),
    ("data/omh_sleep-episode_1-1.json", "sleep-episode-1.1.json"),
    ("data/omh_physical-activity_1-2.json", "physical-activity-1.2.json"),
    ("data/omh_oxygen-saturation_2-0.json", "oxygen-saturation-2.0.json"),
    # Clinical body schemas (served for downstream consumers; no converters).
    ("data/omh_blood-glucose_4-0.json", "blood-glucose-4.0.json"),
    ("data/omh_blood-pressure_4-0.json", "blood-pressure-4.0.json"),
    ("data/omh_body-temperature_4-0.json", "body-temperature-4.0.json"),
    ("data/omh_respiratory-rate_2-0.json", "respiratory-rate-2.0.json"),
    ("data/omh_rr-interval_1-0.json", "rr-interval-1.0.json"),
]

# OMH utility/sub-body schemas transitively required by the clinical bodies.
# These live under schema/omh/ upstream and are vendored into utility/. The
# upstream ``*.x.json`` files are symlink pointers to a concrete version, so
# fetching follows the pointer and stores the concrete content under the ``.x``
# name the bodies $ref (see _check_targets).
OMH_UTILITY_TARGETS: list[tuple[str, str]] = [
    ("utility/body-location-1.x.json", "body-location-1.x.json"),
    ("utility/systolic-blood-pressure-1.x.json", "systolic-blood-pressure-1.x.json"),
    ("utility/diastolic-blood-pressure-1.x.json", "diastolic-blood-pressure-1.x.json"),
    ("utility/specimen-source-2.x.json", "specimen-source-2.x.json"),
    ("utility/temporal-relationship-to-meal-1.x.json", "temporal-relationship-to-meal-1.x.json"),
]

# IEEE 1752.1 envelope schemas (metadata/). Pulled from opensource.ieee.org.
IEEE_METADATA_TARGETS: list[tuple[str, str]] = [
    # (vendored path under SCHEMAS_DIR, upstream path under schemas/)
    ("metadata/data-point-1.0.json", "metadata/data-point-1.0.json"),
    ("metadata/data-series-1.0.json", "metadata/data-series-1.0.json"),
    ("metadata/header-1.0.json", "metadata/header-1.0.json"),
    ("metadata/schema-id-1.0.json", "metadata/schema-id-1.0.json"),
]

# IEEE 1752.1 utility refs transitively required by the metadata envelope.
IEEE_UTILITY_TARGETS: list[tuple[str, str]] = [
    ("utility/date-time-1.0.json", "utility/date-time-1.0.json"),
    ("utility/frequency-unit-value-1.0.json", "utility/frequency-unit-value-1.0.json"),
    ("utility/duration-unit-value-1.0.json", "utility/duration-unit-value-1.0.json"),
    ("utility/duration-unit-value-range-1.0.json", "utility/duration-unit-value-range-1.0.json"),
    ("utility/unit-value-1.0.json", "utility/unit-value-1.0.json"),
    ("utility/unit-value-range-1.0.json", "utility/unit-value-range-1.0.json"),
    # Additional IEEE utility refs required by the clinical bodies.
    ("utility/time-frame-1.0.json", "utility/time-frame-1.0.json"),
    ("utility/time-interval-1.0.json", "utility/time-interval-1.0.json"),
    ("utility/temperature-unit-value-1.0.json", "utility/temperature-unit-value-1.0.json"),
    ("utility/body-posture-1.0.json", "utility/body-posture-1.0.json"),
]


def read_pinned(pinned_path: Path, *, family: str) -> str:
    """Read the pinned ref for a schema family ('omh' or 'ieee') from JSON."""
    data = json.loads(pinned_path.read_text())
    return str(data[family]["ref"])


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
        ) from None


def walk_refs(node: object) -> set[str]:
    """Collect relative-filename $refs from a JSON schema.

    Skips intra-document refs (starting with '#') and absolute URLs
    (starting with 'http'). Returns only bare filenames like 'unit-value-1.x.json'.
    """
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith(("#", "http")):
            refs.add(ref)
        for value in node.values():
            refs.update(walk_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.update(walk_refs(item))
    return refs


def _check_targets(
    targets: list[tuple[str, str]],
    url_fn: Callable[[str, str], str],
    ref: str,
    *,
    follow_pointers: bool = False,
) -> dict[str, tuple[str, str]]:
    """Fetch each target at ref, diff against local, return {vendored: (content, diff)} for changed files.

    With ``follow_pointers``, an upstream ``*.x.json`` that is a symlink (served
    as the bare target filename rather than JSON) is followed once, and the
    concrete schema is stored under the vendored ``.x`` name. This matches how
    OMH publishes "latest 1.x" pointers under schema/omh/.
    """
    diffs: dict[str, tuple[str, str]] = {}
    for vendored, upstream in targets:
        new_content = fetch(url_fn(ref, upstream))
        if follow_pointers and not new_content.lstrip().startswith("{"):
            pointer = new_content.strip()
            if "\n" in pointer or not pointer.endswith(".json"):
                sys.exit(f"{vendored}: expected a '.x' pointer filename, got {pointer[:80]!r}")
            new_content = fetch(url_fn(ref, pointer))
            if not new_content.lstrip().startswith("{"):
                sys.exit(f"{vendored}: pointer -> {pointer} did not resolve to a JSON schema")
        local_path = SCHEMAS_DIR / vendored
        old_content = local_path.read_text() if local_path.exists() else ""
        if old_content == new_content:
            print(f"  unchanged: {vendored}")
            continue
        diff_text = "\n".join(
            difflib.unified_diff(
                old_content.splitlines(), new_content.splitlines(),
                fromfile=f"current/{vendored}", tofile=f"upstream/{vendored}",
                lineterm="",
            )
        )
        diffs[vendored] = (new_content, diff_text)
        print(f"  CHANGED:   {vendored}")
        print(diff_text)
        print()
    return diffs


def fetch(url: str) -> str:
    # Some hosts (e.g. opensource.ieee.org GitLab) reject the default Python
    # User-Agent with HTTP 418, so set an explicit one.
    req = urllib.request.Request(url, headers={"User-Agent": "omh-shim-refresh/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            return str(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} fetching {url}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh vendored OMH schemas at a pinned ref.")
    parser.add_argument(
        "--omh-ref",
        help="Tag or SHA from openmhealth/schemas. Defaults to the ref in _pinned.json.",
    )
    parser.add_argument(
        "--ieee-ref",
        help="Tag or SHA from opensource.ieee.org/omh/1752. "
        "Defaults to the ref in _pinned.json.",
    )
    args = parser.parse_args(argv)

    ref, ref_was_explicit = _resolve_ref(args.omh_ref, family="omh")
    print(f"openmhealth/schemas ref: {ref}")
    print()

    def omh_url(ref: str, upstream: str) -> str:
        return f"{RAW_BASE}/{ref}/schema/omh/{upstream}"

    diffs = _check_targets(TARGETS, omh_url, ref)
    diffs.update(_check_targets(OMH_UTILITY_TARGETS, omh_url, ref, follow_pointers=True))

    ieee_ref, ieee_was_explicit = _resolve_ref(args.ieee_ref, family="ieee")
    print()
    print(f"opensource.ieee.org/omh/1752 ref: {ieee_ref}")
    print()

    ieee_diffs = _check_targets(
        IEEE_METADATA_TARGETS + IEEE_UTILITY_TARGETS,
        lambda ref, upstream: f"{IEEE_RAW_BASE}/{ref}/schemas/{upstream}",
        ieee_ref,
    )

    all_diffs = {**diffs, **ieee_diffs}

    if not all_diffs:
        print("All vendored schemas are up to date. No changes needed.")
        return 0

    answer = input(f"Update {len(all_diffs)} file(s)? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted. No files changed.")
        return 1

    for vendored, (new_content, _diff) in all_diffs.items():
        (SCHEMAS_DIR / vendored).write_text(new_content)
        print(f"  wrote {vendored}")

    if ref_was_explicit:
        today = datetime.date.today().isoformat()
        write_pinned(PINNED_PATH, family="omh", new_ref=ref, today=today)
        print(f"  updated {PINNED_PATH.relative_to(REPO_ROOT)} omh ref -> {ref} ({today})")

    if ieee_was_explicit:
        today = datetime.date.today().isoformat()
        write_pinned(PINNED_PATH, family="ieee", new_ref=ieee_ref, today=today)
        print(
            f"  updated {PINNED_PATH.relative_to(REPO_ROOT)} ieee ref -> {ieee_ref} ({today})"
        )

    # Verify transitive $ref closure
    all_refs: set[str] = set()
    for p in SCHEMAS_DIR.rglob("*.json"):
        if p.name == "_pinned.json":
            continue
        all_refs.update(walk_refs(json.loads(p.read_text())))
    existing = {p.name for p in SCHEMAS_DIR.rglob("*.json")}
    missing = sorted(r for r in all_refs if r not in existing)
    if missing:
        print(f"\n  WARNING: {len(missing)} transitive $ref(s) not vendored: {missing}")
        print("  Run the ref-closure check from the plan and vendor the missing files.")

    print()
    print("Re-run pytest to confirm everything still validates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
