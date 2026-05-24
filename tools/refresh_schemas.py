#!/usr/bin/env python3
"""Refresh vendored OMH schemas from openmhealth/schemas at a pinned ref.

By default the script verifies the 6 vendored top-level schemas against the
ref recorded in ``omh_shim/schemas/README.md``. Pass ``--omh-ref <tag-or-sha>``
to fetch a different ref; when changes are confirmed, the README ref is
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
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "omh_shim" / "schemas"
README_PATH = SCHEMAS_DIR / "README.md"
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


_REF_LINE_RE = re.compile(r"at commit `([^`]+)`")


def parse_readme_ref(text: str) -> str:
    r"""Extract the pinned ref from omh_shim/schemas/README.md text.

    Looks for the `at commit \`<ref>\`` pattern. Returns the ref string
    (SHA or tag). Raises ValueError if not found.
    """
    match = _REF_LINE_RE.search(text)
    if not match:
        raise ValueError(
            "No ref found in README. Expected a line containing "
            "`at commit \\`<ref>\\``."
        )
    return match.group(1)


_REF_LINE_REPLACE_RE = re.compile(r"at commit `[^`]+` \([^)]*\)\.")


def update_readme_ref(text: str, *, new_ref: str, today: str) -> str:
    r"""Rewrite the `at commit \`<ref>\` (...)` line in README text.

    ``today`` is passed in (not read from datetime.date.today()) so callers
    can control the recorded date — useful for tests and for users running
    the script across midnight UTC.

    Raises ValueError if no matching line exists.
    """
    new_line = f"at commit `{new_ref}` (fetched {today})."
    out, n = _REF_LINE_REPLACE_RE.subn(new_line, text, count=1)
    if n == 0:
        raise ValueError("No ref line to replace in README.")
    return out


def _resolve_ref(arg_ref: str | None, readme_text: str) -> tuple[str, bool]:
    """Return (ref_to_use, was_passed_explicitly).

    Precedence: CLI arg > README. If neither is available, raise SystemExit.
    """
    if arg_ref:
        return arg_ref, True
    try:
        return parse_readme_ref(readme_text), False
    except ValueError as e:
        raise SystemExit(
            f"{e} Pass --omh-ref <tag-or-sha> or record one in "
            f"{README_PATH.relative_to(REPO_ROOT)}."
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
        help="Tag or SHA from openmhealth/schemas. Defaults to the ref recorded "
        "in omh_shim/schemas/README.md.",
    )
    args = parser.parse_args(argv)

    readme_text = README_PATH.read_text()
    ref, ref_was_explicit = _resolve_ref(args.omh_ref, readme_text)
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
        README_PATH.write_text(update_readme_ref(readme_text, new_ref=ref, today=today))
        print(f"  updated {README_PATH.relative_to(REPO_ROOT)} ref -> {ref} ({today})")

    print()
    print("Re-run pytest to confirm everything still validates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
