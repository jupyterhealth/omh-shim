#!/usr/bin/env python3
"""Watch the two upstream signals that can invalidate omh-shim's resolved schema ids.

**Primary — upstream Open mHealth deprecation.** For every ``omh:`` id in
``omh_shim.known_ids()`` (resolved candidates *and* served-only schemas), fetch the
schema from ``openmhealth/schemas`` at ``main`` and report a ``DEPRECATED`` finding
when it carries a top-level ``deprecation`` block. This is the signal the publisher
actively sends, and it fired for years on schemas this repo emitted. Upstream rather
than the vendored copy, because the import-time invariant in ``omh_shim`` already
rejects a deprecated vendored *candidate* — the only deprecation that can reach a
running system is one OMH added after the pin.

A deprecation on a **served-only** schema whose declared successor is already vendored
is expected, not actionable: those schemas are retained deliberately (they are the
evidence the successor invariant reads, and consumers still validate historical
records against them). Those are reported as ``ok (served-only, successor vendored)``.

**Secondary — IEEE 1752.1 publication.** Whether IEEE has published a measure omh-shim
still resolves to OMH (``ADOPT``), or a newer version of one it already resolves to
IEEE (``NEWER``). Scoped to stable IEEE 1752.1 (``omh/1752``) only — ``omh/1752-2``'s
draft metabolic schemas live on an unmerged branch, and watching drafts would churn
every commit. IEEE coverage is a plain dictionary lookup keyed by the *resolved id's*
measure name — which under rule 3 can differ from the data type's (``sleep_duration``
resolves to ``total-sleep-time``).

Run from the repo root, against an editable install (``pip install -e .``) — the tool
imports ``omh_shim`` to read the resolved schema ids and the vendored successor evidence::

    python tools/check_schema_adoption.py                  # check against the pinned IEEE ref
    python tools/check_schema_adoption.py --ref 1.0.3       # check a different IEEE ref
    python tools/check_schema_adoption.py --json            # machine-readable output

Exit 0 whether or not findings were reported — findings are informational, not a
build failure. Exit non-zero only when the check itself could not run (a network
failure, an unparseable IEEE response, or a fetch that fails the canary sanity
check below). A single OMH schema that cannot be fetched is a ``::warning::`` naming
that schema, not an abort.

Standard library only — no extra deps.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_schemas import PINNED_PATH, RAW_BASE, USER_AGENT, read_pinned  # noqa: E402

IMPORT_ERROR = ""
try:
    # _successor_name is imported rather than reimplemented so the tool reads supersededBy
    # exactly as the resolver does. This import runs omh-shim's resolution invariants, and
    # the weekly job reaches it *after* refresh_schemas.py has rewritten the vendored tree:
    # the week upstream deprecates a live candidate, the invariant is what fails here.
    from omh_shim import SCHEMA_IDS, _successor_name, known_ids, load_schema  # noqa: E402
except RuntimeError as e:
    IMPORT_ERROR = str(e)
    SCHEMA_IDS = {}

IEEE_API_BASE = "https://opensource.ieee.org/api/v4"
DEFAULT_PROJECT = "omh%2F1752"
DEFAULT_PATH = "schemas"
OMH_REF = "main"

# A parsed upstream JSON schema document, the shape omh_shim._schema_loader.load returns.
SchemaDoc = dict[str, Any]
MAX_PAGES = 50  # a well-behaved API pages in single digits; this only guards against one that ignores ?page=
URLOPEN_TIMEOUT = 30  # seconds; a hung socket must not block until the job timeout

_MEASURE_RE = re.compile(r"^(?P<name>.+)-(?P<ver>\d+\.\d+)\.json$")


class Finding(NamedTuple):
    data_type: str  # "" for a served-only schema, which no data type resolves to
    measure: str
    kind: str  # "ADOPT", "NEWER" or "DEPRECATED"
    versions: tuple[str, ...]
    current: str
    superseded_by: str = ""
    deprecation_date: str = ""


class SourceResult(NamedTuple):
    """One upstream source's outcome.

    ``ran`` false means the check learned nothing. ``ran`` true with a non-empty ``failed``
    means it learned something about everything except those ids — a partial result, which
    is not the same as a clean one.
    """

    ran: bool
    error: str
    findings: list[Finding]
    data: Any
    fetched: int = 0
    failed: tuple[str, ...] = ()


def _parse_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as e:
        raise RuntimeError(f"unparseable version segment in {version!r}: {e}") from e


def build_measure_index(paths: list[str]) -> tuple[dict[str, set[str]], list[str]]:
    """Measure name -> versions, from schemas/**.json paths. Skips metadata/ and utility/.

    Also returns the basenames the version regex didn't match, so a naming scheme it
    doesn't anticipate (e.g. a three-segment version, or a non-numeric one) becomes a
    visible warning instead of a silently dropped measure.
    """
    index: dict[str, set[str]] = {}
    unparsed: list[str] = []
    for path in paths:
        rel = path.removeprefix("schemas/")
        if rel.startswith(("metadata/", "utility/")):
            continue
        basename = rel.rsplit("/", 1)[-1]
        match = _MEASURE_RE.match(basename)
        if not match:
            unparsed.append(basename)
            continue
        index.setdefault(match.group("name"), set()).add(match.group("ver"))
    return index, unparsed


def missing_canaries(index: Mapping[str, set[str]], schema_ids: Mapping[str, str]) -> list[str]:
    """Canary measures already resolved to an ``ieee:`` id that are absent from ``index``.

    Every such data type was vendored from this exact IEEE project+ref (see
    ``tools/refresh_schemas.py``'s ``IEEE_DATA_TARGETS``), so its absence means the
    fetch or the ``schemas/`` path is wrong — not that IEEE deleted a published
    measure. A non-empty result means the index cannot be trusted. Pure, no network.
    """
    canaries = {c.split(":")[1] for c in schema_ids.values() if c.startswith("ieee:")}
    return sorted(m for m in canaries if m not in index)


def find_findings(index: Mapping[str, set[str]], schema_ids: Mapping[str, str]) -> list[Finding]:
    """Pure. Returns ADOPT/NEWER findings; empty when the table is current."""
    findings: list[Finding] = []
    for data_type, current in schema_ids.items():
        measure = current.split(":")[1]
        versions = index.get(measure)
        if not versions:
            continue
        sorted_versions = tuple(sorted(versions, key=_parse_version))
        if not current.startswith("ieee:"):
            findings.append(Finding(data_type, measure, "ADOPT", sorted_versions, current))
            continue
        current_version = current.rsplit(":", 1)[-1]
        newest = max(versions, key=_parse_version)
        if _parse_version(newest) > _parse_version(current_version):
            findings.append(Finding(data_type, measure, "NEWER", sorted_versions, current))
    return findings


def successor_evidence() -> dict[str, frozenset[str]]:
    """Measure name -> vendored schema ids of that measure carrying no ``deprecation`` block.

    A deprecated vendored schema is not evidence that its own successor is covered, so
    those are excluded here and the chain deprecated -> deprecated cannot read as ok.
    """
    evidence: dict[str, set[str]] = {}
    for schema_id in known_ids():
        if load_schema(schema_id).get("deprecation"):
            continue
        evidence.setdefault(schema_id.split(":")[1], set()).add(schema_id)
    return {name: frozenset(ids) for name, ids in evidence.items()}


def is_expected_deprecation(
    schema_id: str,
    superseded_by: str,
    schema_ids: Mapping[str, str],
    evidence: Mapping[str, frozenset[str]],
) -> bool:
    """True when an upstream deprecation is one this repo has already acted on.

    A schema omh-shim only *serves* — nothing in ``schema_ids`` resolves to it — whose
    declared successor is already vendored as a live schema was retained deliberately (it
    is the evidence the successor invariant reads, and consumers still validate historical
    records against it). Reporting those every week would train the reader to ignore the
    check. Everything else is actionable: a deprecation on a schema omh-shim resolves to,
    one whose successor it does not vendor, and one whose only vendored successor is itself
    deprecated. Pure, no network.
    """
    if schema_id in set(schema_ids.values()):
        return False
    if not superseded_by:
        return False
    successor = _successor_name(superseded_by)
    # A schema may not be its own evidence: OMH's usual shape is a newer version of the
    # same measure, whose name the deprecated schema supplies itself.
    return bool(evidence.get(successor, frozenset()) - {schema_id})


def find_deprecations(
    schemas: Mapping[str, SchemaDoc],
    schema_ids: Mapping[str, str] | None = None,
    evidence: Mapping[str, frozenset[str]] | None = None,
) -> list[Finding]:
    """Pure. Actionable DEPRECATED findings from upstream schema bodies keyed by schema id."""
    schema_ids = SCHEMA_IDS if schema_ids is None else schema_ids
    evidence = successor_evidence() if evidence is None else evidence
    data_type_of = {resolved: data_type for data_type, resolved in schema_ids.items()}
    findings: list[Finding] = []
    for schema_id, schema in sorted(schemas.items()):
        deprecation = schema.get("deprecation")
        if not isinstance(deprecation, Mapping):
            continue
        superseded_by = str(deprecation.get("supersededBy") or "")
        if is_expected_deprecation(schema_id, superseded_by, schema_ids, evidence):
            continue
        findings.append(Finding(
            data_type=data_type_of.get(schema_id, ""),
            measure=schema_id.split(":")[1],
            kind="DEPRECATED",
            versions=(schema_id.rsplit(":", 1)[-1],),
            current=schema_id,
            superseded_by=superseded_by,
            deprecation_date=str(deprecation.get("date") or ""),
        ))
    return findings


def omh_schema_url(schema_id: str, ref: str = OMH_REF) -> str:
    """Upstream raw URL for an ``omh:<name>:<version>`` id."""
    _namespace, name, version = schema_id.split(":")
    return f"{RAW_BASE}/{ref}/schema/omh/{name}-{version}.json"


def fetch_omh_schemas(
    schema_ids: list[str], ref: str = OMH_REF
) -> tuple[dict[str, SchemaDoc], list[str]]:
    """Fetch each ``omh:`` schema from upstream. Returns (schemas, per-id failure messages).

    One schema that cannot be fetched or parsed is reported and skipped — it must not
    take the other checks down with it.
    """
    schemas: dict[str, SchemaDoc] = {}
    failures: list[str] = []
    for schema_id in sorted(schema_ids):
        url = omh_schema_url(schema_id, ref)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=URLOPEN_TIMEOUT) as resp:
                schemas[schema_id] = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError, TimeoutError) as e:
            failures.append(f"{schema_id} from {url}: {type(e).__name__}: {e}")
    return schemas, failures


def fetch_schema_paths(project: str, ref: str, *, path: str = DEFAULT_PATH) -> list[str]:
    """Page the GitLab tree API for every ``{path}/**.json`` blob path at ref."""
    paths: list[str] = []
    page = 1
    while True:
        if page > MAX_PAGES:
            raise RuntimeError(
                f"exceeded {MAX_PAGES} pages fetching the '{path}' tree for {project}@{ref} "
                f"— the API may not be honoring '?page='"
            )
        url = (
            f"{IEEE_API_BASE}/projects/{project}/repository/tree"
            f"?ref={ref}&path={path}&recursive=true&per_page=100&page={page}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=URLOPEN_TIMEOUT) as resp:
                text = resp.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            raise RuntimeError(f"request failed for {url}: {e}") from e
        try:
            entries = json.loads(text)
        except json.JSONDecodeError as e:
            # A WAF challenge answers 200 with HTML; refuse to treat it as a tree listing.
            raise RuntimeError(f"non-JSON response from {url}: {text[:200]!r}") from e
        if not entries:
            break
        paths.extend(
            entry["path"] for entry in entries
            if entry.get("type") == "blob" and entry["path"].endswith(".json")
        )
        page += 1
    return paths


def _print_table(
    findings: list[Finding], index: Mapping[str, set[str]], schema_ids: Mapping[str, str]
) -> None:
    kinds_by_type: dict[str, list[str]] = {}
    for finding in findings:
        if finding.data_type:
            kinds_by_type.setdefault(finding.data_type, []).append(finding.kind)
    header = f"{'data_type':<20} {'resolved id':<28} {'ieee versions':<18} verdict"
    print(header)
    print("-" * len(header))
    for data_type, current in sorted(schema_ids.items()):
        measure = current.split(":")[1]
        versions = ", ".join(sorted(index.get(measure, set()), key=_parse_version)) or "-"
        verdict = "+".join(kinds_by_type.get(data_type, [])) or "ok"
        print(f"{data_type:<20} {current:<28} {versions:<18} {verdict}")


def _print_deprecation_table(
    schemas: Mapping[str, SchemaDoc],
    schema_ids: Mapping[str, str],
    evidence: Mapping[str, frozenset[str]],
) -> None:
    deprecated = {
        schema_id: schema["deprecation"]
        for schema_id, schema in sorted(schemas.items())
        if isinstance(schema.get("deprecation"), Mapping)
    }
    header = f"{'omh schema id':<28} {'supersededBy':<58} verdict"
    print(header)
    print("-" * len(header))
    for schema_id, deprecation in deprecated.items():
        superseded_by = str(deprecation.get("supersededBy") or "")
        verdict = (
            "ok (served-only, successor vendored)"
            if is_expected_deprecation(schema_id, superseded_by, schema_ids, evidence)
            else "DEPRECATED"
        )
        print(f"{schema_id:<28} {superseded_by or '-':<58} {verdict}")
    print()
    print(
        f"{len(schemas) - len(deprecated)} of {len(schemas)} fetched omh: schema(s) "
        f"carry no upstream deprecation."
    )


def run_omh_check(
    ref: str, schema_ids: Mapping[str, str], evidence: Mapping[str, frozenset[str]]
) -> SourceResult:
    """Primary check: upstream Open mHealth deprecations. Warns per schema on stderr.

    Fetching none of the ``omh:`` schemas is the same failure shape as the IEEE canary
    check — a rate limit or an outage would otherwise read as "nothing is deprecated".
    A partial fetch still runs, but every id that could not be read is carried in
    ``failed``: a permanent 404 after an upstream rename would otherwise leave that
    schema's deprecation status unchecked every week, visible only on stderr.
    """
    omh_ids = sorted(schema_id for schema_id in known_ids() if schema_id.startswith("omh:"))
    schemas, failures = fetch_omh_schemas(omh_ids, ref)
    for failure in failures:
        print(f"::warning::check_schema_adoption could not fetch {failure}", file=sys.stderr)
    if omh_ids and not schemas:
        error = (
            f"0 of {len(omh_ids)} omh: schema(s) could be fetched from "
            f"openmhealth/schemas@{ref}"
            + (f" — first error: {failures[0]}" if failures else "")
        )
        print(
            f"::warning::check_schema_adoption could not run the Open mHealth deprecation "
            f"check: {error}",
            file=sys.stderr,
        )
        return SourceResult(False, error, [], {}, 0, tuple(failures))
    return SourceResult(
        True, "", find_deprecations(schemas, schema_ids, evidence), schemas,
        len(schemas), tuple(failures),
    )


def run_ieee_check(project: str, ref: str, path: str, schema_ids: Mapping[str, str]) -> SourceResult:
    """Secondary check: IEEE 1752.1 publication. Warns on stderr; never raises."""
    try:
        paths = fetch_schema_paths(project, ref, path=path)
    except RuntimeError as e:
        print(f"::warning::check_schema_adoption could not run the IEEE check: {e}", file=sys.stderr)
        return SourceResult(False, str(e), [], {})

    index, unparsed = build_measure_index(paths)

    missing = missing_canaries(index, schema_ids)
    if missing or not index:
        tree_url = (
            f"{IEEE_API_BASE}/projects/{project}/repository/tree"
            f"?ref={ref}&path={path}&recursive=true&per_page=100"
        )
        if not index:
            reason = "the fetched index is completely empty"
        else:
            reason = f"canary measure(s) already vendored from this project+ref are missing: {missing}"
        error = (
            f"{reason} — either the '{path}' path is wrong for {project}@{ref}, or (only "
            f"possible on a manually-passed --ref; the pinned tag this workflow runs at is "
            f"immutable) IEEE genuinely retired a previously-published canary measure. "
            f"URL: {tree_url}"
        )
        print(f"::warning::check_schema_adoption could not run the IEEE check: {error}", file=sys.stderr)
        return SourceResult(False, error, [], {})

    if unparsed:
        # stderr, not stdout: --json's stdout is the machine-readable artifact (schema-drift.yml
        # pipes it straight into json.load()) and must stay pure JSON.
        print(
            f"::warning::check_schema_adoption: {len(unparsed)} schema filename(s) did not match "
            f"the '<name>-<major>.<minor>.json' pattern and were skipped: {sorted(unparsed)}",
            file=sys.stderr,
        )

    try:
        findings = find_findings(index, schema_ids)
    except RuntimeError as e:
        print(f"::warning::check_schema_adoption could not run the IEEE check: {e}", file=sys.stderr)
        return SourceResult(False, str(e), [], {})
    return SourceResult(True, "", findings, index)


def _print_finding(finding: Finding) -> None:
    if finding.kind == "DEPRECATED":
        when = f" on {finding.deprecation_date}" if finding.deprecation_date else ""
        print(f"  DEPRECATED {finding.current}: Open mHealth deprecated it{when} in favor of "
              f"{finding.superseded_by or 'an unnamed successor'}")
    elif finding.kind == "ADOPT":
        print(f"  ADOPT {finding.data_type}: IEEE now publishes {finding.measure} "
              f"({', '.join(finding.versions)}); currently resolved to {finding.current}")
    else:
        print(f"  NEWER {finding.data_type}: IEEE publishes {finding.measure} "
              f"({', '.join(finding.versions)}) newer than resolved {finding.current}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check upstream Open mHealth deprecations and IEEE 1752.1 publication "
                    "against omh-shim's resolved schema ids."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="IEEE GitLab project id (URL-encoded).")
    parser.add_argument("--ref", help="IEEE ref to check. Defaults to the pinned ref in _pinned.json.")
    parser.add_argument(
        "--path", default=DEFAULT_PATH,
        help=f"Tree path to fetch (default {DEFAULT_PATH!r}). For debugging path-drift only.",
    )
    parser.add_argument(
        "--omh-ref", default=OMH_REF,
        help=f"openmhealth/schemas ref to read deprecations from (default {OMH_REF!r}).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a table.")
    args = parser.parse_args(argv)

    if IMPORT_ERROR:
        # ::error:: not ::warning::: this is a build-breaking state, not a flaky fetch.
        print(
            f"::error::check_schema_adoption cannot run: importing omh_shim failed because "
            f"the resolver refused a candidate its publisher has deprecated. If this run "
            f"refreshed the vendored schemas, upstream just deprecated a live candidate — "
            f"point it at the successor it declares, in omh_shim/__init__.py's "
            f"_SCHEMA_CANDIDATES. Invariant: {IMPORT_ERROR}",
            file=sys.stderr,
        )
        return 1

    ieee_ref = args.ref or read_pinned(PINNED_PATH, family="ieee")
    evidence = successor_evidence()

    # The two sources live on different hosts and fail independently: an IEEE WAF block
    # must not discard the Open mHealth result, or vice versa.
    omh = run_omh_check(args.omh_ref, SCHEMA_IDS, evidence)
    ieee = run_ieee_check(args.project, ieee_ref, args.path, SCHEMA_IDS)
    findings = omh.findings + ieee.findings

    if args.json:
        print(json.dumps({
            "omh": {
                "ran": omh.ran, "error": omh.error, "ref": args.omh_ref,
                "fetched": omh.fetched, "failed": list(omh.failed),
            },
            "ieee": {"ran": ieee.ran, "error": ieee.error, "ref": ieee_ref},
            "findings": [f._asdict() for f in findings],
        }, indent=2))
        return 0 if (omh.ran or ieee.ran) else 1

    print(f"openmhealth/schemas @ {args.omh_ref}")
    print()
    if omh.ran:
        _print_deprecation_table(omh.data, SCHEMA_IDS, evidence)
        if omh.failed:
            print()
            print(f"PARTIALLY evaluated: {len(omh.failed)} schema(s) could not be fetched and "
                  f"were NOT checked for deprecation:")
            for failure in omh.failed:
                print(f"  {failure}")
    else:
        print(f"NOT evaluated: {omh.error}")
    print()
    print(f"IEEE {args.project} @ {ieee_ref}")
    print()
    if ieee.ran:
        _print_table(findings, ieee.data, SCHEMA_IDS)
    else:
        print(f"NOT evaluated: {ieee.error}")
    print()
    if findings:
        print(f"{len(findings)} finding(s):")
        for finding in findings:
            _print_finding(finding)
    elif omh.ran and ieee.ran:
        print("No findings. The resolved schema ids are current with both publishers.")
    elif omh.ran or ieee.ran:
        ran = "Open mHealth" if omh.ran else "IEEE"
        print(f"Nothing to report from {ran} — the other source was NOT evaluated this run, "
              f"which is not the same as a clean result.")
    else:
        print("Neither source was evaluated this run — nothing was learned.")

    return 0 if (omh.ran or ieee.ran) else 1


if __name__ == "__main__":
    sys.exit(main())
