#!/usr/bin/env python3
"""Refresh vendored OMH schemas from openmhealth/schemas main.

Pulls the 6 top-level schemas (5 standard OMH + the local HRV placeholder is
left untouched), diffs each against the existing vendored copy, and prompts
before overwriting. Records the new commit SHA for omh_shim/schemas/README.md.

Run from the repo root::

    python tools/refresh_schemas.py

Standard library only — no extra deps.
"""

import difflib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "omh_shim" / "schemas"
GITHUB_API = "https://api.github.com/repos/openmhealth/schemas"
RAW_BASE = "https://raw.githubusercontent.com/openmhealth/schemas"

# Top-level schemas to refresh. The local HRV placeholder is excluded.
TARGETS: list[tuple[str, str]] = [
    # (vendored filename, upstream path within schema/omh/)
    ("omh_heart-rate_2-0.json", "heart-rate-2.0.json"),
    ("omh_step-count_3-0.json", "step-count-3.0.json"),
    ("omh_sleep-duration_2-0.json", "sleep-duration-2.0.json"),
    ("omh_sleep-episode_1-1.json", "sleep-episode-1.1.json"),
    ("omh_physical-activity_1-2.json", "physical-activity-1.2.json"),
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


def fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} fetching {url}")


def get_main_sha() -> str:
    body = fetch(f"{GITHUB_API}/git/refs/heads/main")
    return json.loads(body)["object"]["sha"]


def main() -> int:
    sha = get_main_sha()
    print(f"openmhealth/schemas main is at {sha}")
    print()

    diffs: dict[str, str] = {}
    for vendored, upstream in TARGETS:
        url = f"{RAW_BASE}/{sha}/schema/omh/{upstream}"
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

    print()
    print(f"Update omh_shim/schemas/README.md with the new SHA: {sha}")
    print("Then re-run pytest to confirm everything still validates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
