# Pin refresh_schemas.py to a versioned ref — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tools/refresh_schemas.py` reproducible: it should pull from a pinned ref recorded in `omh_shim/schemas/README.md` by default (overridable via `--omh-ref`), include `oxygen-saturation` in its target set, and auto-update the README ref on successful refresh. Tracks GitHub issue [jupyterhealth/omh-shim#8](https://github.com/jupyterhealth/omh-shim/issues/8).

**Architecture:** Refactor `main()` into pure helpers (`parse_readme_ref`, `update_readme_ref`) that can be unit-tested without network or filesystem mocking, plus an argparse-based CLI entry point. Keep `urllib`-based network I/O as the only impure layer. Tests cover the helpers directly; end-to-end behavior verified manually against the live upstream repo (network call, but only once per ref, run by hand).

**Tech Stack:** Python 3.11+, standard library only (`urllib`, `argparse`, `pathlib`, `re`, `datetime`). Pytest for tests. No new dependencies.

---

## Files

- Modify: `tools/refresh_schemas.py` — refactor into helpers, add argparse, add target, wire README write
- Modify: `omh_shim/schemas/README.md` — record the new ref format (`at commit \`<ref>\` (fetched YYYY-MM-DD)`) plus a line documenting the refresh-script CLI
- Create: `tests/test_refresh_schemas.py` — unit tests for the two pure helpers

## Baseline

`tools/refresh_schemas.py` today (lines referenced are pre-edit):
- L25-26: GitHub API + raw base URLs
- L28-35: `TARGETS` list, 5 entries (missing `oxygen-saturation`)
- L38-43: `fetch(url)` helper
- L46-48: `get_main_sha()` always fetches `refs/heads/main` — this is what we're replacing
- L51-97: `main()` body — fetches main SHA, loops TARGETS, prints diffs, prompts, writes files, prints SHA for manual README update

`omh_shim/schemas/README.md` line 4 records the ref:
```
at commit `36078a89e5e5efeba8dfc590a81cc42fd140c815` (main, fetched 2026-04-09).
```

We'll keep that exact format. The script will parse it to read the current ref, and rewrite it on successful refresh to a different ref. The format is stable across SHA refs and tag refs (e.g. `v1.0.0`); the script doesn't try to resolve tags to SHAs — whatever the user passes is what gets stored.

## Decision Log

- **No tag→SHA resolution.** Whatever ref the user passes is stored verbatim. Trades a small reproducibility margin (someone could re-point a tag) for keeping the script standard-library-only.
- **README is only auto-written when `--omh-ref` was passed explicitly.** Default-mode runs (re-fetching at the README's own ref) never touch the README. This avoids the failure mode where the vendored files have drifted from the README ref and a re-fetch silently "fixes" the README to match.
- **No mocking the network in tests.** Pure helpers are unit-tested; the CLI's end-to-end behavior is verified manually. Mocking `urllib.request.urlopen` adds complexity without buying confidence that the GitHub raw URL pattern is right — which is the only thing that could break in production.

---

## Task 1: Test scaffold + parse_readme_ref helper

**Files:**
- Create: `tests/test_refresh_schemas.py`
- Modify: `tools/refresh_schemas.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_refresh_schemas.py`:

```python
"""Unit tests for tools/refresh_schemas.py helpers.

The script lives in tools/ (not the package), so we import it via path
manipulation. Network-touching code is not exercised here — see manual
verification at the end of the plan.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import refresh_schemas  # noqa: E402


# --- parse_readme_ref ---


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_refresh_schemas.py -v`
Expected: 3 FAIL with `AttributeError: module 'refresh_schemas' has no attribute 'parse_readme_ref'`

- [ ] **Step 3: Implement parse_readme_ref**

Add to `tools/refresh_schemas.py`, after the `RAW_BASE` constant (around line 25):

```python
import re


_REF_LINE_RE = re.compile(r"at commit `([^`]+)`")


def parse_readme_ref(text: str) -> str:
    """Extract the pinned ref from omh_shim/schemas/README.md text.

    Looks for the `at commit \`<ref>\`` pattern. Returns the ref string
    (which may be a SHA or a tag). Raises ValueError if not found.
    """
    match = _REF_LINE_RE.search(text)
    if not match:
        raise ValueError(
            "No ref found in README. Expected a line containing "
            "`at commit \\`<ref>\\``."
        )
    return match.group(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_refresh_schemas.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_refresh_schemas.py tools/refresh_schemas.py
git commit -m "refactor(refresh): extract parse_readme_ref helper

Pure function that reads the pinned ref out of schemas/README.md.
First step toward a versioned refresh script (#8)."
```

---

## Task 2: update_readme_ref helper

**Files:**
- Modify: `tests/test_refresh_schemas.py`
- Modify: `tools/refresh_schemas.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_refresh_schemas.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_refresh_schemas.py -v`
Expected: 3 new FAILs with `AttributeError: module 'refresh_schemas' has no attribute 'update_readme_ref'`. The previous 3 tests still PASS.

- [ ] **Step 3: Implement update_readme_ref**

Add to `tools/refresh_schemas.py`, immediately after `parse_readme_ref`:

```python
_REF_LINE_REPLACE_RE = re.compile(r"at commit `[^`]+` \([^)]*\)\.")


def update_readme_ref(text: str, *, new_ref: str, today: str) -> str:
    """Rewrite the `at commit \`<ref>\` (...)` line in README text.

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_refresh_schemas.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_refresh_schemas.py tools/refresh_schemas.py
git commit -m "refactor(refresh): extract update_readme_ref helper

Pure function that rewrites the pinned ref line in schemas/README.md.
Date is injected by the caller so the helper stays deterministic."
```

---

## Task 3: Add argparse + --omh-ref + fail-loud when no ref available

**Files:**
- Modify: `tools/refresh_schemas.py`

- [ ] **Step 1: Add argparse to the script**

Replace the existing `main()` function (lines ~51-97) with this version. The diff-and-prompt flow is preserved; the changes are:
1. Replace `get_main_sha()` with arg-or-README resolution
2. Resolve `ref` once, use it everywhere instead of `sha`
3. README is only rewritten when `--omh-ref` was passed AND files changed AND user confirmed

```python
import argparse
import datetime


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "omh_shim" / "schemas"
README_PATH = SCHEMAS_DIR / "README.md"


def _resolve_ref(arg_ref: str | None, readme_text: str) -> tuple[str, bool]:
    """Return (ref_to_use, was_passed_explicitly).

    Precedence: CLI arg > README. If neither is available, raise.
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
```

Also delete the old `get_main_sha()` function and the `GITHUB_API` constant — both unused now.

- [ ] **Step 2: Sanity check — script still imports**

Run: `python -c "import sys; sys.path.insert(0, 'tools'); import refresh_schemas; print(refresh_schemas.main.__doc__ or 'ok')"`
Expected: prints `ok` (or a docstring) with no traceback.

- [ ] **Step 3: Add test for the no-ref error path**

Append to `tests/test_refresh_schemas.py`:

```python
# --- _resolve_ref ---


def test_resolve_ref_prefers_cli_arg():
    text = "at commit `from-readme` (fetched 2026-01-01).\n"
    ref, was_explicit = refresh_schemas._resolve_ref("from-cli", text)
    assert ref == "from-cli"
    assert was_explicit is True


def test_resolve_ref_falls_back_to_readme():
    text = "at commit `from-readme` (fetched 2026-01-01).\n"
    ref, was_explicit = refresh_schemas._resolve_ref(None, text)
    assert ref == "from-readme"
    assert was_explicit is False


def test_resolve_ref_exits_when_neither_available():
    with pytest.raises(SystemExit, match="Pass --omh-ref"):
        refresh_schemas._resolve_ref(None, "README with no ref.\n")
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_refresh_schemas.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Manual sanity check — --help works**

Run: `python tools/refresh_schemas.py --help`
Expected: argparse help output mentioning `--omh-ref`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_refresh_schemas.py tools/refresh_schemas.py
git commit -m "feat(refresh): pin to versioned ref via --omh-ref

Default to the ref recorded in schemas/README.md; fail loudly if
neither is available. On confirmed update with an explicit --omh-ref,
rewrite the README ref automatically (no longer a manual step)."
```

---

## Task 4: Add oxygen-saturation to TARGETS

**Files:**
- Modify: `tools/refresh_schemas.py`

- [ ] **Step 1: Inspect current TARGETS**

Read `tools/refresh_schemas.py` around the `TARGETS` constant. Confirm `oxygen-saturation` is absent.

- [ ] **Step 2: Add the missing entry**

Add to the `TARGETS` list (the order doesn't matter functionally; group with the other top-level OMH schemas):

```python
TARGETS: list[tuple[str, str]] = [
    # (vendored filename, upstream path within schema/omh/)
    ("omh_heart-rate_2-0.json", "heart-rate-2.0.json"),
    ("omh_step-count_3-0.json", "step-count-3.0.json"),
    ("omh_sleep-duration_2-0.json", "sleep-duration-2.0.json"),
    ("omh_sleep-episode_1-1.json", "sleep-episode-1.1.json"),
    ("omh_physical-activity_1-2.json", "physical-activity-1.2.json"),
    ("omh_oxygen-saturation_2-0.json", "oxygen-saturation-2.0.json"),
]
```

- [ ] **Step 3: Sanity check**

Run: `python -c "import sys; sys.path.insert(0, 'tools'); import refresh_schemas; assert ('omh_oxygen-saturation_2-0.json', 'oxygen-saturation-2.0.json') in refresh_schemas.TARGETS; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add tools/refresh_schemas.py
git commit -m "fix(refresh): include oxygen-saturation in TARGETS

The schema was wired through SCHEMA_IDS and _schema_loader but missing
from the refresh script's target list, so refreshes silently skipped it."
```

---

## Task 5: Document new behavior in schemas/README.md

**Files:**
- Modify: `omh_shim/schemas/README.md`

- [ ] **Step 1: Update the "Refresh procedure" section**

In `omh_shim/schemas/README.md`, replace the "Refresh procedure" section with:

```markdown
## Refresh procedure

The refresh script is pinned to a specific ref recorded above. Run with no
args to verify the vendored files still match that ref:

```bash
python tools/refresh_schemas.py
```

To pull a different ref (a tag or commit SHA), pass `--omh-ref`. On
confirmed update, the script rewrites the ref recorded in this README
automatically:

```bash
python tools/refresh_schemas.py --omh-ref v1.0.0
python tools/refresh_schemas.py --omh-ref 7969045b1c2d...
```

The script never writes to this README when run without `--omh-ref` —
default-mode runs only verify the vendored files match the recorded ref.
```

- [ ] **Step 2: Verify the ref line is still parseable**

Run: `python -c "import sys; sys.path.insert(0, 'tools'); import refresh_schemas; from pathlib import Path; print(refresh_schemas.parse_readme_ref(Path('omh_shim/schemas/README.md').read_text()))"`
Expected: prints the current SHA (`36078a89e5e5efeba8dfc590a81cc42fd140c815`).

- [ ] **Step 3: Commit**

```bash
git add omh_shim/schemas/README.md
git commit -m "docs(schemas): document --omh-ref refresh workflow"
```

---

## Task 6: Manual end-to-end verification

This is verification, not a commit-able task. Each check corresponds to one acceptance criterion on [issue #8](https://github.com/jupyterhealth/omh-shim/issues/8).

- [ ] **Check 1: Default run reports unchanged at the recorded SHA**

Run: `python tools/refresh_schemas.py`
Expected output ends with: `All vendored schemas are up to date. No changes needed.`
Confirms: acceptance criterion 1.

- [ ] **Check 2: oxygen-saturation appears in the targets output**

Look at the output of Check 1. Confirm a line `  unchanged: omh_oxygen-saturation_2-0.json` appears.
Confirms: acceptance criterion 3.

- [ ] **Check 3: Newer ref produces diffs and auto-writes README on confirm**

Find a newer SHA. As of 2026-05-24, `main` of `openmhealth/schemas` should be ahead of `36078a89...`. Get current main SHA:

```bash
curl -s https://api.github.com/repos/openmhealth/schemas/git/refs/heads/main | python3 -c "import sys,json; print(json.load(sys.stdin)['object']['sha'])"
```

If that SHA differs from `36078a89...`, run:

```bash
python tools/refresh_schemas.py --omh-ref <new-sha>
```

Expected: diffs printed (one per changed file), prompt `Update N file(s)? [y/N]`. Answer `y`. Expect schema files rewritten AND a final line `updated omh_shim/schemas/README.md ref -> <new-sha> (2026-05-24)`. Verify `git diff omh_shim/schemas/README.md` shows the SHA line changed.

If main hasn't moved, instead test the auto-write logic by manually pointing to a tag (whichever the repo has — e.g. an old-version tag if one exists). Even passing the same SHA explicitly should hit the "unchanged" branch and NOT write the README.

After verifying, run `git checkout -- omh_shim/schemas/ tools/` to revert any test-only schema updates (only the planned commits should land).

Confirms: acceptance criteria 2 and the README-write behavior.

- [ ] **Check 4: No ref + no README ref fails loudly**

Temporarily remove the ref line from `omh_shim/schemas/README.md` (use a scratch copy or revert immediately after):

```bash
cp omh_shim/schemas/README.md /tmp/README.bak
# delete the "at commit ..." line manually in your editor
python tools/refresh_schemas.py
# expect: exit code != 0 with message "No ref found ... Pass --omh-ref ..."
cp /tmp/README.bak omh_shim/schemas/README.md
```

Confirms: acceptance criterion 4.

- [ ] **Check 5: Existing test suite still green**

Run: `pytest -q`
Expected: all pre-existing tests pass; the 9 new ones in `test_refresh_schemas.py` pass.

---

## Self-Review

**Spec coverage** (against [issue #8](https://github.com/jupyterhealth/omh-shim/issues/8)):

- Add `--omh-ref` arg defaulting to README SHA → Task 3
- Fail loudly if README has no SHA (no fallback to `main`) → Task 3, Step 3 (test) + Check 4
- Add oxygen-saturation to TARGETS → Task 4
- Auto-rewrite README SHA on confirmed update → Task 3 (logic) + Check 3 (verification)
- Preserve diff-and-prompt UX → Task 3, kept intact in the rewritten `main()`
- All 4 acceptance criteria → Checks 1, 2, 3, 4

**Placeholder scan:** No TBDs, no "implement later," every code step shows the actual code. The "find a newer SHA" branch in Check 3 has a fallback for the case where main hasn't moved.

**Type consistency:** `parse_readme_ref` returns `str`, raises `ValueError`. `update_readme_ref` takes `text: str`, keyword-only `new_ref: str`, `today: str`, returns `str`, raises `ValueError`. `_resolve_ref` returns `tuple[str, bool]`. CLI uses `argparse.Namespace.omh_ref: str | None`. All consistent across tasks.
