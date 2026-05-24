# JHE-aligned schema layout + IEEE 1752.1 source + structured pinning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `omh_shim/schemas/` to mirror JHE's `metadata/`, `data/`, `utility/` layout; add IEEE 1752.1 as a second vendoring source (for envelope schemas); replace the README-as-state-source with a structured `_pinned.json`; block remote `$ref` fetches; register schemas under multiple URI bases so refs resolve regardless of how they're written. Tracks GitHub issue [jupyterhealth/omh-shim#9](https://github.com/jupyterhealth/omh-shim/issues/9).

**Architecture:**
- `omh_shim/schemas/` is reorganized into three subdirectories aligned with JHE's structure.
- A new `omh_shim/schemas/_pinned.json` records the OMH SHA + IEEE tag (replacing the markdown-embedded ref that #8 established).
- `tools/refresh_schemas.py` grows a `--ieee-ref` flag and a second TARGETS list (IEEE metadata + transitive utility deps).
- `omh_shim/_validate.py` adopts a `NoNetwork` retriever (mirroring JHE's `core/utils.py`) so unresolved `$ref`s raise instead of fetching.
- The `referencing.Registry` registers each schema under both its bare filename AND its canonical w3id URL (also mirroring JHE).

**Tech Stack:** Python 3.11+, stdlib (`json`, `re`, `argparse`, `urllib`, `pathlib`, `datetime`), `jsonschema`, `referencing`. No new dependencies.

---

## Files

- Create: `omh_shim/schemas/_pinned.json` — structured ref state (replaces README parsing)
- Create: `omh_shim/schemas/metadata/` — IEEE 1752.1 envelope (4 files initially)
- Create: `omh_shim/schemas/data/` — body schemas (7 omh_* + 1 local_*)
- Create: `omh_shim/schemas/utility/` — transitive `$ref` deps (existing OMH utility + new IEEE utility)
- Modify: `omh_shim/_schema_loader.py` — update `_FILENAMES` paths to `data/`
- Modify: `omh_shim/_validate.py` — walk subdir tree, register under bare + w3id URLs, install `NoNetwork` retriever
- Modify: `tools/refresh_schemas.py` — replace README helpers with `read_pinned`/`write_pinned`, add `--ieee-ref`, add IEEE targets
- Modify: `tests/test_refresh_schemas.py` — replace README-parsing tests with `_pinned.json` tests
- Modify: `omh_shim/schemas/README.md` — pure human documentation; reference `_pinned.json` for state
- Delete: bare files at `omh_shim/schemas/*.json` (they're moved into subdirs)

## Baseline (post-#8)

```
omh_shim/schemas/
  README.md                                  # contains 'at commit <sha>' line
  __init__.py
  *.json                                     # 23 schemas flat
```

`_schema_loader._FILENAMES` maps schema-ids to bare filenames. `_validate._registry()` globs `*.json` and registers each by bare filename only.

`tools/refresh_schemas.py` has `parse_readme_ref` / `update_readme_ref` helpers and a single `TARGETS` list pulling from `openmhealth/schemas`.

## Decision Log

- **`_pinned.json` lives in `omh_shim/schemas/`** (alongside the schemas) rather than at repo root. Reason: it's schema-specific state, and keeping it co-located with the schemas means it ships with the package. The leading underscore signals "internal — read/write only via the refresh script."
- **Mirror JHE's *layout* but pull schema *content* from canonical sources.** Tracked as a "Clarification" addendum on the #9 issue body. JHE's vendored content drifts from canonical OMH/IEEE — tracked separately at [JHE#443](https://github.com/jupyterhealth/jupyterhealth-exchange/issues/443).
- **Body schemas stay on OMH** for the 7 currently-implemented data types, even though some (physical-activity, step-count, sleep-episode) have IEEE 1.0 equivalents. Migrating body validation to IEEE is a separate decision pending JHE's response on #443.
- **IEEE 1.0.2 is the pinned tag** for the initial IEEE vendoring. Most recent tag, published 2026-05-04.
- **`NoNetwork` retriever raises `RuntimeError`** (matching JHE's pattern), not a custom exception. Keeps the boundary recognizable.
- **`local_heart-rate-variability_1-0.json` keeps the `local_` prefix** in `data/` (rather than renaming to `omh_`). Reason: the file is locally-authored, not from upstream — the prefix is a provenance signal. The `:local:` schema-id namespace makes this consistent.

---

## Task 1: Introduce `_pinned.json` and `read_pinned`/`write_pinned` helpers

**Files:**
- Create: `omh_shim/schemas/_pinned.json`
- Modify: `tools/refresh_schemas.py`
- Modify: `tests/test_refresh_schemas.py`

- [ ] **Step 1: Create `omh_shim/schemas/_pinned.json`:**

```json
{
  "omh": {
    "ref": "36078a89e5e5efeba8dfc590a81cc42fd140c815",
    "fetched": "2026-04-09",
    "source": "https://github.com/openmhealth/schemas"
  }
}
```

(IEEE entry will be added in Task 6 when we vendor IEEE schemas.)

- [ ] **Step 2: Replace the README-parsing tests with `_pinned.json` tests.** In `tests/test_refresh_schemas.py`, delete the `parse_readme_ref`, `update_readme_ref`, and `_resolve_ref` tests (they're being replaced). Add:

```python
# --- _pinned.json helpers ---


def test_read_pinned_returns_recorded_ref(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({
        "omh": {"ref": "abc123", "fetched": "2026-04-09",
                "source": "https://github.com/openmhealth/schemas"}
    }))
    assert refresh_schemas.read_pinned(pinned, family="omh") == "abc123"


def test_read_pinned_raises_when_family_missing(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({"omh": {"ref": "abc", "fetched": "x", "source": "y"}}))
    with pytest.raises(KeyError, match="ieee"):
        refresh_schemas.read_pinned(pinned, family="ieee")


def test_write_pinned_updates_ref_and_date(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({
        "omh": {"ref": "old", "fetched": "2026-01-01",
                "source": "https://github.com/openmhealth/schemas"}
    }))
    refresh_schemas.write_pinned(pinned, family="omh", new_ref="new",
                                 today="2026-05-24")
    data = json.loads(pinned.read_text())
    assert data["omh"]["ref"] == "new"
    assert data["omh"]["fetched"] == "2026-05-24"
    assert data["omh"]["source"] == "https://github.com/openmhealth/schemas"


def test_write_pinned_preserves_other_families(tmp_path):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({
        "omh": {"ref": "old-omh", "fetched": "2026-01-01", "source": "x"},
        "ieee": {"ref": "1.0.0", "fetched": "2026-01-01", "source": "y"}
    }))
    refresh_schemas.write_pinned(pinned, family="omh", new_ref="new-omh",
                                 today="2026-05-24")
    data = json.loads(pinned.read_text())
    assert data["omh"]["ref"] == "new-omh"
    assert data["ieee"]["ref"] == "1.0.0"  # untouched
```

Don't delete the imports at the top of the test file.

- [ ] **Step 3: Run tests, verify the 4 new tests FAIL** (`AttributeError: module 'refresh_schemas' has no attribute 'read_pinned'`):

```
.venv/bin/pytest tests/test_refresh_schemas.py -v
```

- [ ] **Step 4: Replace `parse_readme_ref` and `update_readme_ref` in `tools/refresh_schemas.py` with `read_pinned` and `write_pinned`.** Delete the regex constants `_REF_LINE_RE` and `_REF_LINE_REPLACE_RE`. Delete `import re`. Add the new helpers:

```python
PINNED_PATH = SCHEMAS_DIR / "_pinned.json"


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
```

Add `import json` near top (it's already imported in some places — check before adding). Add `from pathlib import Path` if not present.

- [ ] **Step 5: Run tests, verify the 4 new tests PASS:**

```
.venv/bin/pytest tests/test_refresh_schemas.py -v
```

(The previous `parse_readme_ref`/`update_readme_ref` tests are gone, so total test count in this file drops then climbs back.)

- [ ] **Step 6: Commit:**

```
git add omh_shim/schemas/_pinned.json tools/refresh_schemas.py tests/test_refresh_schemas.py
git commit -m "refactor(refresh): move pinned ref from README to _pinned.json

README is human documentation; pinned state belongs in a structured
file the script can read/write without regex surgery."
```

---

## Task 2: Wire `_resolve_ref` and `main()` to use `_pinned.json`

**Files:**
- Modify: `tools/refresh_schemas.py`
- Modify: `tests/test_refresh_schemas.py`

- [ ] **Step 1: Replace `_resolve_ref` to use `read_pinned`.** The new signature:

```python
def _resolve_ref(arg_ref: str | None, family: str) -> tuple[str, bool]:
    """Return (ref_to_use, was_passed_explicitly).

    Precedence: CLI arg > _pinned.json. Raises SystemExit if neither exists.
    """
    if arg_ref:
        return arg_ref, True
    try:
        return read_pinned(PINNED_PATH, family=family), False
    except (FileNotFoundError, KeyError) as e:
        raise SystemExit(
            f"No '{family}' ref recorded in {PINNED_PATH.relative_to(REPO_ROOT)}. "
            f"Pass --{family}-ref <tag-or-sha> or record one."
        )
```

- [ ] **Step 2: Update `main()` to use the new resolver and write back to `_pinned.json` instead of the README:**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh vendored OMH schemas at a pinned ref.")
    parser.add_argument("--omh-ref", help="Tag or SHA from openmhealth/schemas. "
                        "Defaults to the ref in _pinned.json.")
    args = parser.parse_args(argv)

    ref, ref_was_explicit = _resolve_ref(args.omh_ref, family="omh")
    print(f"openmhealth/schemas ref: {ref}")
    print()

    # [rest of body unchanged through diff loop and write loop]

    if ref_was_explicit:
        today = datetime.date.today().isoformat()
        write_pinned(PINNED_PATH, family="omh", new_ref=ref, today=today)
        print(f"  updated {PINNED_PATH.relative_to(REPO_ROOT)} omh ref -> {ref} ({today})")

    print()
    print("Re-run pytest to confirm everything still validates.")
    return 0
```

Remove `README_PATH` constant if it's no longer referenced. Remove the `readme_text` variable.

- [ ] **Step 3: Update `_resolve_ref` tests in `tests/test_refresh_schemas.py`.** The new tests use `tmp_path` and a real `_pinned.json` file:

```python
def test_resolve_ref_prefers_cli_arg(tmp_path, monkeypatch):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({"omh": {"ref": "from-pinned", "fetched": "x", "source": "y"}}))
    monkeypatch.setattr(refresh_schemas, "PINNED_PATH", pinned)
    ref, was_explicit = refresh_schemas._resolve_ref("from-cli", family="omh")
    assert ref == "from-cli"
    assert was_explicit is True


def test_resolve_ref_falls_back_to_pinned(tmp_path, monkeypatch):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({"omh": {"ref": "from-pinned", "fetched": "x", "source": "y"}}))
    monkeypatch.setattr(refresh_schemas, "PINNED_PATH", pinned)
    ref, was_explicit = refresh_schemas._resolve_ref(None, family="omh")
    assert ref == "from-pinned"
    assert was_explicit is False


def test_resolve_ref_exits_when_pinned_missing(tmp_path, monkeypatch):
    pinned = tmp_path / "_pinned.json"
    pinned.write_text(json.dumps({}))  # no families
    monkeypatch.setattr(refresh_schemas, "PINNED_PATH", pinned)
    with pytest.raises(SystemExit, match="omh.*ref"):
        refresh_schemas._resolve_ref(None, family="omh")
```

- [ ] **Step 4: Run tests, verify all green:**

```
.venv/bin/pytest tests/test_refresh_schemas.py -v
```

- [ ] **Step 5: Run end-to-end against the live repo to confirm default mode still works:**

```
.venv/bin/python tools/refresh_schemas.py
```

Expected output: `openmhealth/schemas ref: 36078a89...` followed by 6 unchanged lines.

- [ ] **Step 6: Commit:**

```
git add tools/refresh_schemas.py tests/test_refresh_schemas.py
git commit -m "feat(refresh): wire CLI to _pinned.json (drop README parsing)

_resolve_ref now reads from _pinned.json by family ('omh'/'ieee'),
preparing for the IEEE source in the next task."
```

---

## Task 3: Restructure `omh_shim/schemas/` into subdirs

**Files:** files moved, `_schema_loader.py` paths updated, `_validate.py` registry walker updated.

- [ ] **Step 1: Create the three subdirectories and move files:**

```bash
cd omh_shim/schemas
mkdir -p metadata data utility

# Body schemas → data/
git mv omh_heart-rate_2-0.json data/
git mv omh_oxygen-saturation_2-0.json data/
git mv omh_physical-activity_1-2.json data/
git mv omh_sleep-duration_2-0.json data/
git mv omh_sleep-episode_1-1.json data/
git mv omh_step-count_3-0.json data/
git mv local_heart-rate-variability_1-0.json data/

# Everything else → utility/ (transitive $refs from bodies)
git mv activity-name-1.x.json utility/
git mv date-time-1.x.json utility/
git mv descriptive-statistic-1.0.json utility/
git mv descriptive-statistic-1.x.json utility/
git mv descriptive-statistic-denominator-1.x.json utility/
git mv duration-unit-value-1.x.json utility/
git mv kcal-unit-value-1.x.json utility/
git mv length-unit-value-1.x.json utility/
git mv part-of-day-1.x.json utility/
git mv temporal-relationship-to-physical-activity-1.x.json utility/
git mv temporal-relationship-to-sleep-1.x.json utility/
git mv time-frame-1.x.json utility/
git mv time-interval-1.x.json utility/
git mv unit-value-1.x.json utility/

cd -
```

`metadata/` is intentionally empty until Task 6 vendors IEEE schemas there.

- [ ] **Step 2: Update `omh_shim/_schema_loader.py::_FILENAMES`** to point at the new paths:

```python
_FILENAMES: dict[str, str] = {
    "omh:heart-rate:2.0": "data/omh_heart-rate_2-0.json",
    "local:heart-rate-variability:1.0": "data/local_heart-rate-variability_1-0.json",
    "omh:step-count:3.0": "data/omh_step-count_3-0.json",
    "omh:sleep-duration:2.0": "data/omh_sleep-duration_2-0.json",
    "omh:sleep-episode:1.1": "data/omh_sleep-episode_1-1.json",
    "omh:physical-activity:1.2": "data/omh_physical-activity_1-2.json",
    "omh:oxygen-saturation:2.0": "data/omh_oxygen-saturation_2-0.json",
}
```

The `joinpath` in `load()` uses `importlib.resources.files("omh_shim.schemas")` — a relative path like `data/foo.json` works.

- [ ] **Step 3: Update `omh_shim/_validate.py::_registry()`** to walk the subdirectory tree:

```python
@lru_cache(maxsize=1)
def _registry() -> Registry:
    """Build a referencing.Registry that serves every vendored schema by filename."""
    schemas_pkg = importlib.resources.files("omh_shim.schemas")
    resources = []
    for subdir in ("metadata", "data", "utility"):
        for entry in schemas_pkg.joinpath(subdir).iterdir():
            name = entry.name
            if not name.endswith(".json"):
                continue
            with entry.open("r", encoding="utf-8") as f:
                doc = json.load(f)
            resources.append((name, Resource.from_contents(doc, default_specification=DRAFT7)))
    return Registry().with_resources(resources)
```

(Multi-URI registration comes in Task 7. For now, keep bare-filename registration so existing $refs resolve.)

- [ ] **Step 4: Run the full test suite. Expect 81 passed.**

```
.venv/bin/pytest -q
```

If a test fails, the most likely cause is a missed `_FILENAMES` entry. Compare the failure against the list in Step 2.

- [ ] **Step 5: Update `tools/refresh_schemas.py` paths so it writes/reads from `data/` instead of bare.** In `TARGETS`, the vendored filenames now need a `data/` prefix:

```python
TARGETS: list[tuple[str, str]] = [
    ("data/omh_heart-rate_2-0.json", "heart-rate-2.0.json"),
    ("data/omh_step-count_3-0.json", "step-count-3.0.json"),
    ("data/omh_sleep-duration_2-0.json", "sleep-duration-2.0.json"),
    ("data/omh_sleep-episode_1-1.json", "sleep-episode-1.1.json"),
    ("data/omh_physical-activity_1-2.json", "physical-activity-1.2.json"),
    ("data/omh_oxygen-saturation_2-0.json", "oxygen-saturation-2.0.json"),
]
```

- [ ] **Step 6: Verify the refresh script still works in default mode:**

```
.venv/bin/python tools/refresh_schemas.py
```

Expect "unchanged" for all 6.

- [ ] **Step 7: Commit:**

```
git add -A omh_shim/schemas omh_shim/_schema_loader.py omh_shim/_validate.py tools/refresh_schemas.py
git commit -m "refactor(schemas): reorganize into metadata/, data/, utility/ subdirs

Mirrors JHE's layout in jupyterhealth-exchange/data/omh/json-schemas/.
metadata/ is empty until IEEE schemas land in the next task."
```

---

## Task 4: Walk transitive `$ref`s in the refresh script

**Files:**
- Modify: `tools/refresh_schemas.py`
- Modify: `tests/test_refresh_schemas.py`

The refresh script currently only fetches the top-level body schemas in `TARGETS`. Their `$ref` deps (unit-value, time-frame, etc.) are already vendored, so default-mode runs work — but on a future `--omh-ref` bump that adds a new transitive ref, the script would miss it. This task adds explicit utility-ref tracking.

- [ ] **Step 1: Add tests for a `walk_refs` helper:**

```python
# --- walk_refs ---


def test_walk_refs_collects_relative_refs():
    schema = {"$ref": "unit-value-1.x.json",
              "properties": {"x": {"$ref": "time-frame-1.x.json"},
                             "y": {"$ref": "#/definitions/foo"}}}  # ignored
    assert refresh_schemas.walk_refs(schema) == {
        "unit-value-1.x.json", "time-frame-1.x.json"}


def test_walk_refs_handles_nested():
    schema = {"allOf": [{"$ref": "a.json"}, {"items": {"$ref": "b.json"}}]}
    assert refresh_schemas.walk_refs(schema) == {"a.json", "b.json"}
```

- [ ] **Step 2: Run tests, expect 2 FAIL with AttributeError.**

- [ ] **Step 3: Implement `walk_refs` in `tools/refresh_schemas.py`:**

```python
def walk_refs(node: object) -> set[str]:
    """Collect relative-filename $refs from a JSON schema.

    Skips intra-document refs (starting with '#/') and absolute URLs
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
```

- [ ] **Step 4: Run tests, expect 2 PASS. Run full suite: still 81 + 2 new = 83.**

- [ ] **Step 5: Commit:**

```
git add tools/refresh_schemas.py tests/test_refresh_schemas.py
git commit -m "feat(refresh): add walk_refs helper for transitive \$ref tracking

Future-proofs the refresh script for schemas that introduce new utility
refs in a version bump."
```

---

## Task 5: Add `NoNetwork` retriever to `_validate.py`

**Files:**
- Modify: `omh_shim/_validate.py`
- Modify: `tests/test_core.py`

Mirror JHE's pattern: unresolved `$ref`s should raise a clear error, not try to fetch over the network.

- [ ] **Step 1: Add a test in `tests/test_core.py` (append at the end):**

```python
def test_validate_raises_on_remote_ref():
    """Unknown $ref URIs must fail loudly, not fetch over the network."""
    import json
    import tempfile
    from omh_shim._validate import validate_output

    # Construct a synthetic body that doesn't match any real schema id
    # — but the schema we're using has a remote $ref we never preloaded.
    # We achieve this indirectly by validating against a hand-crafted schema
    # via the validator's internals.
    from omh_shim._validate import _registry
    from jsonschema import Draft7Validator

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$ref": "https://example.invalid/never-resolvable.json"
    }
    validator = Draft7Validator(schema, registry=_registry())
    errors = list(validator.iter_errors({}))
    assert errors, "Expected validation to surface unresolved $ref"
    assert any("never-resolvable" in str(e) or "Remote" in str(e) or "blocked" in str(e)
               for e in errors)
```

- [ ] **Step 2: Run the test. It may PASS already if jsonschema doesn't try to fetch by default — verify which.**

```
.venv/bin/pytest tests/test_core.py::test_validate_raises_on_remote_ref -v
```

If the test PASSES already (jsonschema/referencing doesn't fetch by default), proceed to Step 3 to ADD an explicit guard anyway, since the default behavior may change in future versions. If it FAILS by hanging/fetching, Step 3 is required to make it pass.

- [ ] **Step 3: Add a `NoNetwork` retriever to `_validate.py`:**

```python
class _NoNetwork:
    """Retriever that raises instead of fetching unknown $ref URIs.

    Mirrors JHE's pattern in jupyterhealth-exchange/core/utils.py:24-26.
    """
    def __call__(self, uri: str):
        raise RuntimeError(f"Remote $ref blocked (not preloaded): {uri}")


@lru_cache(maxsize=1)
def _registry() -> Registry:
    schemas_pkg = importlib.resources.files("omh_shim.schemas")
    resources = []
    for subdir in ("metadata", "data", "utility"):
        for entry in schemas_pkg.joinpath(subdir).iterdir():
            name = entry.name
            if not name.endswith(".json"):
                continue
            with entry.open("r", encoding="utf-8") as f:
                doc = json.load(f)
            resources.append((name, Resource.from_contents(doc, default_specification=DRAFT7)))
    return Registry(retrieve=_NoNetwork()).with_resources(resources)
```

- [ ] **Step 4: Run the test, expect PASS. Run full suite, expect 84 (81 + 2 from Task 4 + 1 new).**

- [ ] **Step 5: Commit:**

```
git add omh_shim/_validate.py tests/test_core.py
git commit -m "feat(validate): block remote \$ref fetches with NoNetwork retriever

Unknown \$ref URIs now raise RuntimeError instead of attempting a
network fetch. Matches JHE's pattern."
```

---

## Task 6: Vendor IEEE 1752.1 metadata schemas + utility deps

**Files:** new files under `omh_shim/schemas/metadata/` and `omh_shim/schemas/utility/`; `_pinned.json` updated.

- [ ] **Step 1: Download IEEE metadata schemas at tag 1.0.2.** From the worktree root:

```bash
mkdir -p omh_shim/schemas/metadata
for f in data-point-1.0 data-series-1.0 header-1.0 schema-id-1.0; do
  curl -fsSL "https://opensource.ieee.org/omh/1752/-/raw/1.0.2/schemas/metadata/${f}.json" \
    -o "omh_shim/schemas/metadata/${f}.json"
done
ls omh_shim/schemas/metadata/
```

Expected: 4 files.

- [ ] **Step 2: Walk IEEE metadata $refs and download missing utility deps.** From earlier reconnaissance, the IEEE metadata schemas reference `date-time-1.0.json`, `schema-id-1.0.json`, `frequency-unit-value-1.0.json`, and `header-1.0.json`. `schema-id-1.0.json` and `header-1.0.json` are metadata (already downloaded). `date-time-1.0.json` and `frequency-unit-value-1.0.json` are utility.

Note: there's already a `date-time-1.x.json` (OMH version) under `utility/`. IEEE has a different version (`date-time-1.0.json`). Both need to coexist with different filenames.

```bash
for f in date-time-1.0 frequency-unit-value-1.0; do
  curl -fsSL "https://opensource.ieee.org/omh/1752/-/raw/1.0.2/schemas/utility/${f}.json" \
    -o "omh_shim/schemas/utility/${f}.json"
done
```

- [ ] **Step 3: Walk the newly-downloaded utility schemas for further $refs.** Use Python to verify the closure:

```bash
.venv/bin/python -c "
import json
import sys
sys.path.insert(0, 'tools')
import refresh_schemas
from pathlib import Path

schema_dir = Path('omh_shim/schemas')
all_refs = set()
for p in schema_dir.rglob('*.json'):
    refs = refresh_schemas.walk_refs(json.loads(p.read_text()))
    all_refs.update(refs)

missing = []
existing = {p.name for p in schema_dir.rglob('*.json')}
for ref in all_refs:
    if ref not in existing:
        missing.append(ref)

print('Missing transitive deps:', missing or 'none')
"
```

If anything's missing, download it from IEEE utility or OMH (depending on what's referenced). Re-run until the missing set is empty.

- [ ] **Step 4: Add the IEEE entry to `_pinned.json`:**

```json
{
  "omh": {
    "ref": "36078a89e5e5efeba8dfc590a81cc42fd140c815",
    "fetched": "2026-04-09",
    "source": "https://github.com/openmhealth/schemas"
  },
  "ieee": {
    "ref": "1.0.2",
    "fetched": "2026-05-24",
    "source": "https://opensource.ieee.org/omh/1752"
  }
}
```

- [ ] **Step 5: Run the full test suite. Expect 84 passed, nothing broken by the new vendored files.**

```
.venv/bin/pytest -q
```

- [ ] **Step 6: Commit:**

```
git add -A omh_shim/schemas/metadata omh_shim/schemas/utility omh_shim/schemas/_pinned.json
git commit -m "feat(schemas): vendor IEEE 1752.1 metadata + utility deps at tag 1.0.2

Adds envelope schemas (data-point, data-series, header, schema-id) and
their transitive utility refs. Records the IEEE pin in _pinned.json."
```

---

## Task 7: Register schemas under multiple URI bases

**Files:**
- Modify: `omh_shim/_validate.py`

JHE registers each schema under both bare filename AND its canonical w3id URL. This means `$ref: "header-1.0.json"` AND `$ref: "https://w3id.org/ieee/ieee-1752-schema/header-1.0.json"` both resolve. Mirror that.

- [ ] **Step 1: Add a test in `tests/test_core.py`:**

```python
def test_registry_resolves_w3id_refs():
    """A schema referencing a w3id IEEE URL must resolve from the local registry."""
    from omh_shim._validate import _registry
    from jsonschema import Draft7Validator

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$ref": "https://w3id.org/ieee/ieee-1752-schema/header-1.0.json"
    }
    validator = Draft7Validator(schema, registry=_registry())
    # If the $ref doesn't resolve, this raises. Validating an empty object
    # against the IEEE header should produce errors (required fields missing),
    # not a fetch attempt.
    errors = list(validator.iter_errors({}))
    assert errors  # missing required fields
    assert all("Remote" not in str(e) for e in errors), \
        "Should not have hit NoNetwork — w3id ref should resolve locally"
```

- [ ] **Step 2: Run the test, expect FAIL** (the registry only has bare filenames).

- [ ] **Step 3: Update `_registry()` to register under multiple URIs:**

```python
@lru_cache(maxsize=1)
def _registry() -> Registry:
    ieee_base = "https://w3id.org/ieee/ieee-1752-schema/"
    omh_base = "https://w3id.org/openmhealth/schemas/omh/"

    schemas_pkg = importlib.resources.files("omh_shim.schemas")
    resources = []

    def load(entry):
        with entry.open("r", encoding="utf-8") as f:
            return json.load(f)

    for subdir in ("metadata", "data", "utility"):
        for entry in schemas_pkg.joinpath(subdir).iterdir():
            name = entry.name
            if not name.endswith(".json"):
                continue
            doc = load(entry)
            res = Resource.from_contents(doc, default_specification=DRAFT7)
            resources.append((name, res))
            # Also register under the w3id permalinks so refs like
            # "https://w3id.org/ieee/ieee-1752-schema/<name>" resolve.
            if subdir in ("metadata", "utility"):
                resources.append((ieee_base + name, res))
            if subdir == "utility":
                resources.append((omh_base + name, res))

    return Registry(retrieve=_NoNetwork()).with_resources(resources)
```

- [ ] **Step 4: Run the test, expect PASS. Run full suite, expect 85.**

- [ ] **Step 5: Commit:**

```
git add omh_shim/_validate.py tests/test_core.py
git commit -m "feat(validate): register schemas under bare + w3id URI bases

Matches JHE's referencing.Registry setup. Schemas resolve whether \$refs
are written as bare filenames or canonical w3id permalinks."
```

---

## Task 8: Add `--ieee-ref` to refresh script + IEEE targets

**Files:**
- Modify: `tools/refresh_schemas.py`

- [ ] **Step 1: Add an `IEEE_TARGETS` list and a second URL base near `TARGETS`:**

```python
IEEE_RAW_BASE = "https://opensource.ieee.org/omh/1752/-/raw"

IEEE_METADATA_TARGETS: list[tuple[str, str]] = [
    ("metadata/data-point-1.0.json", "metadata/data-point-1.0.json"),
    ("metadata/data-series-1.0.json", "metadata/data-series-1.0.json"),
    ("metadata/header-1.0.json", "metadata/header-1.0.json"),
    ("metadata/schema-id-1.0.json", "metadata/schema-id-1.0.json"),
]

IEEE_UTILITY_TARGETS: list[tuple[str, str]] = [
    ("utility/date-time-1.0.json", "utility/date-time-1.0.json"),
    ("utility/frequency-unit-value-1.0.json", "utility/frequency-unit-value-1.0.json"),
    # If Task 6's $ref closure surfaced more, add them here.
]
```

- [ ] **Step 2: Add `--ieee-ref` to argparse and a second refresh loop in `main()`:**

```python
parser.add_argument("--ieee-ref", help="Tag or SHA from opensource.ieee.org/omh/1752. "
                    "Defaults to the ref in _pinned.json.")

# ... existing OMH resolve + loop ...

# IEEE side
ieee_ref, ieee_was_explicit = _resolve_ref(args.ieee_ref, family="ieee")
print(f"opensource.ieee.org/omh/1752 ref: {ieee_ref}")
print()

ieee_diffs: dict[str, tuple[str, str]] = {}
for vendored, upstream in IEEE_METADATA_TARGETS + IEEE_UTILITY_TARGETS:
    url = f"{IEEE_RAW_BASE}/{ieee_ref}/schemas/{upstream}"
    new_content = fetch(url)
    local_path = SCHEMAS_DIR / vendored
    old_content = local_path.read_text() if local_path.exists() else ""

    if old_content == new_content:
        print(f"  unchanged: {vendored}")
        continue

    diff = "\n".join(
        difflib.unified_diff(
            old_content.splitlines(), new_content.splitlines(),
            fromfile=f"current/{vendored}", tofile=f"upstream/{vendored}",
            lineterm="",
        )
    )
    ieee_diffs[vendored] = (new_content, diff)
    print(f"  CHANGED:   {vendored}")
    print(diff)
    print()

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
    print(f"  updated _pinned.json omh ref -> {ref} ({today})")

if ieee_was_explicit:
    today = datetime.date.today().isoformat()
    write_pinned(PINNED_PATH, family="ieee", new_ref=ieee_ref, today=today)
    print(f"  updated _pinned.json ieee ref -> {ieee_ref} ({today})")
```

- [ ] **Step 3: Run end-to-end:**

```
.venv/bin/python tools/refresh_schemas.py
```

Expected: 6 OMH "unchanged" + 6 IEEE "unchanged" (4 metadata + 2 utility) + "All vendored schemas are up to date."

- [ ] **Step 4: Test the `--help`:**

```
.venv/bin/python tools/refresh_schemas.py --help
```

Both `--omh-ref` and `--ieee-ref` should appear.

- [ ] **Step 5: Run full test suite, expect 85 still passing.**

- [ ] **Step 6: Commit:**

```
git add tools/refresh_schemas.py
git commit -m "feat(refresh): add --ieee-ref + IEEE 1752.1 source

Refresh script now pulls from two repos with independent pins.
Both refs recorded in _pinned.json."
```

---

## Task 9: Update `omh_shim/schemas/README.md` for human consumption

**Files:**
- Modify: `omh_shim/schemas/README.md`

Replace the SHA-bearing line and the "Refresh procedure" section. The README becomes pure human documentation.

- [ ] **Step 1: Rewrite the README. The new content:**

```markdown
# Vendored Schemas

Schemas are vendored from two upstream sources:

- **OMH:** `https://github.com/openmhealth/schemas` — body schemas (heart-rate, step-count, etc.)
- **IEEE 1752.1:** `https://opensource.ieee.org/omh/1752` — envelope schemas (header, data-point, schema-id) and shared utility refs

Pinned versions are recorded in [`_pinned.json`](_pinned.json). Don't edit that file by hand — use `tools/refresh_schemas.py` (see below).

## Layout

```
omh_shim/schemas/
  metadata/     # IEEE 1752.1 envelope (data-point, data-series, header, schema-id)
  data/         # OMH body schemas (heart-rate, step-count, sleep-*, physical-activity, oxygen-saturation, hr-variability)
  utility/      # Shared $ref deps (time-frame, unit-value, descriptive-statistic, ...)
```

## Body schemas (the 7 that `convert()` validates against)

| Filename | Source | Notes |
|---|---|---|
| `data/omh_heart-rate_2-0.json` | OMH `schema/omh/heart-rate-2.0.json` | |
| `data/omh_step-count_3-0.json` | OMH `schema/omh/step-count-3.0.json` | |
| `data/omh_sleep-duration_2-0.json` | OMH `schema/omh/sleep-duration-2.0.json` | |
| `data/omh_sleep-episode_1-1.json` | OMH `schema/omh/sleep-episode-1.1.json` | |
| `data/omh_physical-activity_1-2.json` | OMH `schema/omh/physical-activity-1.2.json` | |
| `data/omh_oxygen-saturation_2-0.json` | OMH `schema/omh/oxygen-saturation-2.0.json` | |
| `data/local_heart-rate-variability_1-0.json` | local placeholder | Open mHealth has no canonical HRV schema. Locally-authored. |

## Refresh procedure

Default mode verifies the vendored files match the recorded refs in `_pinned.json`:

```bash
python tools/refresh_schemas.py
```

To bump either pin, pass the corresponding flag:

```bash
python tools/refresh_schemas.py --omh-ref <tag-or-sha>
python tools/refresh_schemas.py --ieee-ref 1.0.3
python tools/refresh_schemas.py --omh-ref <tag-or-sha> --ieee-ref 1.0.3
```

The script shows diffs, prompts for confirmation, writes the schema files, and updates `_pinned.json` (only for families where you passed a flag — default-mode runs never write).

## Body validation source decision

For the 7 implemented data types, body validation uses the OMH schemas. Some of these (`physical-activity`, `step-count`, `sleep-episode`) also have IEEE 1752.1 versions; migration is deferred pending [JHE#443](https://github.com/jupyterhealth/jupyterhealth-exchange/issues/443) (JHE schemas drift from canonical sources).

Header validation uses the IEEE 1752.1 envelope (`metadata/header-1.0.json`) — added in [omh-shim#10](https://github.com/jupyterhealth/omh-shim/issues/10).
```

- [ ] **Step 2: Verify the file renders sensibly:**

```bash
head -50 omh_shim/schemas/README.md
```

- [ ] **Step 3: Commit:**

```
git add omh_shim/schemas/README.md
git commit -m "docs(schemas): rewrite README as human documentation only

State is recorded in _pinned.json; README now describes the layout,
sources, and refresh procedure without embedding parseable state."
```

---

## Task 10: Manual end-to-end verification

- [ ] **Check 1: Default-mode run reports unchanged for OMH and IEEE.**

```
.venv/bin/python tools/refresh_schemas.py
```

Expected: ref line for OMH, 6 "unchanged" body schemas, ref line for IEEE, 6 "unchanged" envelope+utility schemas, "All vendored schemas are up to date."

- [ ] **Check 2: `--omh-ref` with a different SHA produces diffs and updates `_pinned.json`.**

Corrupt a body file:

```
cp omh_shim/schemas/data/omh_heart-rate_2-0.json /tmp/hr.snap
cp omh_shim/schemas/_pinned.json /tmp/pinned.snap
echo '{"corrupted": true}' > omh_shim/schemas/data/omh_heart-rate_2-0.json
echo "y" | .venv/bin/python tools/refresh_schemas.py --omh-ref 36078a89e5e5efeba8dfc590a81cc42fd140c815
```

Expected output ends with: `updated _pinned.json omh ref -> 36078a89e5e5efeba8dfc590a81cc42fd140c815 (<today>)`. Verify `_pinned.json` shows today's date for omh.fetched. Restore: `cp /tmp/hr.snap omh_shim/schemas/data/omh_heart-rate_2-0.json && cp /tmp/pinned.snap omh_shim/schemas/_pinned.json`.

- [ ] **Check 3: `--ieee-ref 1.0.1` produces diffs.**

```
.venv/bin/python tools/refresh_schemas.py --ieee-ref 1.0.1
```

Expect some CHANGED files (1.0.1 was the previous release). Answer `n` to abort. Verify `_pinned.json` unchanged.

- [ ] **Check 4: Empty `_pinned.json` triggers fail-loud.**

```
cp omh_shim/schemas/_pinned.json /tmp/pinned.snap
echo '{}' > omh_shim/schemas/_pinned.json
.venv/bin/python tools/refresh_schemas.py; echo "exit: $?"
cp /tmp/pinned.snap omh_shim/schemas/_pinned.json
```

Expect non-zero exit with a message about `--omh-ref` and `_pinned.json`.

- [ ] **Check 5: Remote $ref is blocked.** Already covered by a unit test in Task 5; just confirm pytest is green.

```
.venv/bin/pytest -q
```

- [ ] **Check 6: Full mock-JHE test still works.** Run the inline script from the earlier conversation that validates shim output against JHE's vendored schemas. Verify the 10/12 pass rate is preserved (sleep_episode still fails because of JHE-side drift, tracked at JHE#443).

---

## Self-Review

**Spec coverage:**
- Restructure `omh_shim/schemas/` into `metadata/`, `data/`, `utility/` → Task 3
- Add `--ieee-ref` to refresh script → Task 8
- Add IEEE 1752.1 as a second source → Tasks 6 + 8
- Replace README parsing with structured `_pinned.json` → Tasks 1 + 2
- Block remote `$ref` fetches → Task 5
- Register schemas under bare filename + w3id URLs → Task 7
- Walk transitive `$ref`s to know what utilities to vendor → Task 4 + Task 6 Step 3
- Update `README.md` to be human-oriented → Task 9
- Manual verification → Task 10

**Placeholder scan:** None. Every step has concrete code, commands, and expected output.

**Type consistency:** `read_pinned(path, *, family) -> str`, `write_pinned(path, *, family, new_ref, today) -> None`, `_resolve_ref(arg_ref, family) -> tuple[str, bool]`, `walk_refs(node) -> set[str]`, `_NoNetwork.__call__(uri) -> RuntimeError`. All consistent across tasks.
