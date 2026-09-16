"""Unit tests for tools/check_schema_adoption.py. No network in any test."""

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_schema_adoption  # noqa: E402

from omh_shim import SCHEMA_IDS  # noqa: E402

# Captured before the autouse stub below replaces it, for the tests that exercise it directly.
_REAL_FETCH_OMH_SCHEMAS = check_schema_adoption.fetch_omh_schemas


@pytest.fixture(autouse=True)
def _no_omh_network(monkeypatch):
    """Every main() call would otherwise fetch 14 schemas from openmhealth/schemas."""
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas", lambda ids, ref="main": ({}, [])
    )


# --- build_measure_index ---


def test_build_measure_index_parses_versioned_filename():
    index, unparsed = check_schema_adoption.build_measure_index(["schemas/sleep/sleep-episode-1.0.json"])
    assert index == {"sleep-episode": {"1.0"}}
    assert unparsed == []


def test_build_measure_index_skips_metadata_and_utility():
    index, unparsed = check_schema_adoption.build_measure_index([
        "schemas/metadata/header-1.0.json",
        "schemas/utility/time-frame-1.0.json",
    ])
    assert index == {}
    assert unparsed == []


def test_build_measure_index_ignores_unparseable_filename():
    index, unparsed = check_schema_adoption.build_measure_index(["schemas/README.md"])
    assert index == {}
    assert unparsed == ["README.md"]


def test_build_measure_index_merges_multiple_versions_of_same_measure():
    index, unparsed = check_schema_adoption.build_measure_index([
        "schemas/sleep/sleep-episode-1.0.json",
        "schemas/sleep/sleep-episode-2.0.json",
    ])
    assert index == {"sleep-episode": {"1.0", "2.0"}}
    assert unparsed == []


# --- build_measure_index: finding 2 — non-<major>.<minor> filenames must surface, not vanish ---


@pytest.mark.parametrize("basename", [
    "heart-rate-1.0.1.json",
    "heart-rate-1.x.json",
    "heart-rate-2.json",
    "heart-rate-1.0-draft.json",
])
def test_build_measure_index_reports_unparseable_measure_filenames(basename):
    index, unparsed = check_schema_adoption.build_measure_index([f"schemas/heart_rate/{basename}"])
    assert index == {}
    assert basename in unparsed


def test_main_warns_on_unparsed_filenames(monkeypatch, capsys):
    monkeypatch.setattr(
        check_schema_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_schema_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/sleep/total-sleep-time-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.1.json",
        ],
    )
    status = check_schema_adoption.main(["--ref", "1.0.2"])
    assert status == 0
    captured = capsys.readouterr()
    # stderr, like every other warning in this tool — stdout is reserved for --json's artifact.
    assert "::warning::" in captured.err
    assert "heart-rate-1.0.1.json" in captured.err
    assert "heart-rate-1.0.1.json" not in captured.out


def test_main_json_stdout_stays_pure_json_when_filenames_are_unparsed(monkeypatch, capsys):
    # NEW BREAKAGE 1: schema-drift.yml pipes --json's stdout straight into json.load(). A
    # warning leaking onto stdout there corrupts the artifact and kills the workflow step.
    monkeypatch.setattr(
        check_schema_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_schema_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/sleep/total-sleep-time-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.1.json",
        ],
    )
    status = check_schema_adoption.main(["--ref", "1.0.2", "--json"])
    assert status == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)  # raises if the warning leaked onto stdout
    assert report["findings"] == []
    assert report["ieee"]["ran"] is True
    assert "::warning::" in captured.err
    assert "heart-rate-1.0.1.json" in captured.err
    assert "heart-rate-1.0.1.json" not in captured.out


# --- find_findings: real current state ---


def test_find_findings_empty_for_real_current_state():
    index = {"physical-activity": {"1.0"}, "sleep-episode": {"1.0"}}
    assert check_schema_adoption.find_findings(index, SCHEMA_IDS) == []


# --- find_findings: non-vacuity (tests 5 and 6 from the brief) ---


def test_find_findings_detects_adopt():
    # heart_rate resolves to omh:heart-rate:2.0; IEEE publishing heart-rate-1.0 must flag ADOPT.
    index = {"heart-rate": {"1.0"}}
    findings = check_schema_adoption.find_findings(index, SCHEMA_IDS)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.data_type == "heart_rate"
    assert finding.kind == "ADOPT"
    assert finding.current == "omh:heart-rate:2.0"
    assert finding.versions == ("1.0",)


def test_find_findings_detects_newer():
    # sleep_episode resolves to ieee:sleep-episode:1.0; a published 2.0 must flag NEWER.
    index = {"sleep-episode": {"1.0", "2.0"}}
    findings = check_schema_adoption.find_findings(index, SCHEMA_IDS)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.data_type == "sleep_episode"
    assert finding.kind == "NEWER"
    assert finding.current == "ieee:sleep-episode:1.0"


def test_find_findings_gutted_classification_would_fail_these():
    # A classifier that always returns [] (the vacuous "all clear" failure mode) fails both.
    index = {"heart-rate": {"1.0"}, "sleep-episode": {"1.0", "2.0"}}
    findings = check_schema_adoption.find_findings(index, SCHEMA_IDS)
    kinds = {f.kind for f in findings}
    assert kinds == {"ADOPT", "NEWER"}


# --- version comparison ---


def test_version_comparison_is_numeric_not_lexicographic():
    schema_ids = {"heart_rate": "ieee:heart-rate:1.9"}
    index = {"heart-rate": {"1.10"}}
    findings = check_schema_adoption.find_findings(index, schema_ids)
    assert len(findings) == 1
    assert findings[0].kind == "NEWER"


def test_version_comparison_does_not_flag_lexicographically_smaller_but_numerically_equal():
    schema_ids = {"heart_rate": "ieee:heart-rate:1.10"}
    index = {"heart-rate": {"1.9"}}
    assert check_schema_adoption.find_findings(index, schema_ids) == []


def test_find_findings_raises_on_unparseable_current_version():
    schema_ids = {"heart_rate": "ieee:heart-rate:1.0-rc1"}
    index = {"heart-rate": {"1.0"}}
    with pytest.raises(RuntimeError, match="unparseable version"):
        check_schema_adoption.find_findings(index, schema_ids)


def test_main_routes_unparseable_version_through_warning_path(monkeypatch, capsys):
    # heart-rate is present in the fetched index (so the finding-1 canary check passes) but the
    # patched SCHEMA_IDS entry has a version find_findings can't parse — that must still surface
    # as a ::warning:: exit, not an uncaught traceback.
    monkeypatch.setattr(
        check_schema_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_schema_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/sleep/total-sleep-time-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.json",
        ],
    )
    monkeypatch.setattr(check_schema_adoption, "SCHEMA_IDS", {**SCHEMA_IDS, "heart_rate": "ieee:heart-rate:1.0-rc1"})
    status = check_schema_adoption.main(["--ref", "1.0.2"])
    assert status == 1
    assert "::warning::" in capsys.readouterr().err


# --- no finding when IEEE doesn't publish the measure ---


def test_find_findings_no_finding_for_unpublished_measure():
    index = {"some-other-measure": {"1.0"}}
    assert check_schema_adoption.find_findings(index, SCHEMA_IDS) == []


# --- missing_canaries: finding 1 — a wrong/renamed path must not read as "all clear" ---


def test_missing_canaries_empty_when_ieee_resolved_types_are_present():
    index = {"physical-activity": {"1.0"}, "sleep-episode": {"1.0"}, "total-sleep-time": {"1.0"}}
    assert check_schema_adoption.missing_canaries(index, SCHEMA_IDS) == []


def test_missing_canaries_flags_absent_ieee_resolved_measure():
    # sleep-episode is missing even though sleep_episode already resolves to ieee:sleep-episode:1.0.
    index = {"physical-activity": {"1.0"}, "total-sleep-time": {"1.0"}}
    assert check_schema_adoption.missing_canaries(index, SCHEMA_IDS) == ["sleep-episode"]


def test_missing_canaries_flags_all_when_index_is_empty():
    assert sorted(check_schema_adoption.missing_canaries({}, SCHEMA_IDS)) == [
        "physical-activity", "sleep-episode", "total-sleep-time",
    ]


def test_missing_canaries_keys_on_resolved_measure_not_data_type():
    """sleep_duration resolves to total-sleep-time; IEEE never published sleep-duration."""
    index = {"physical-activity": {"1.0"}, "sleep-episode": {"1.0"}, "sleep-duration": {"1.0"}}
    assert check_schema_adoption.missing_canaries(index, SCHEMA_IDS) == ["total-sleep-time"]


def test_main_errors_on_empty_index_instead_of_reporting_no_findings(monkeypatch, capsys):
    # Simulates a renamed/missing 'schemas/' path: GitLab answers HTTP 200 with an empty list.
    monkeypatch.setattr(
        check_schema_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_schema_adoption.DEFAULT_PATH: [],
    )
    status = check_schema_adoption.main(["--ref", "1.0.2"])
    assert status == 1
    captured = capsys.readouterr()
    assert "::warning::" in captured.err
    assert "No findings" not in captured.out
    assert "No findings" not in captured.err


def test_main_errors_when_canary_measures_missing(monkeypatch, capsys):
    # Path fetch "succeeds" but only returns unrelated measures — sleep-episode/physical-activity
    # (already vendored from this project+ref) are absent, so the fetch itself is suspect.
    monkeypatch.setattr(
        check_schema_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_schema_adoption.DEFAULT_PATH: [
            "schemas/environment/ambient-light-1.0.json",
        ],
    )
    status = check_schema_adoption.main(["--ref", "1.0.2"])
    assert status == 1
    captured = capsys.readouterr()
    assert "sleep-episode" in captured.err
    assert "physical-activity" in captured.err
    assert "No findings" not in captured.out


# --- fetch_schema_paths: paging and error visibility, no network ---


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_schema_paths_pages_until_empty(monkeypatch):
    responses = {
        1: [
            {"type": "blob", "path": "schemas/sleep/sleep-episode-1.0.json"},
            {"type": "tree", "path": "schemas/sleep"},
            {"type": "blob", "path": "schemas/README.md"},
        ],
        2: [],
    }
    requested_pages: list[int] = []

    def fake_urlopen(req, timeout=None):
        page = int(re.search(r"[?&]page=(\d+)", req.full_url).group(1))
        requested_pages.append(page)
        return _FakeResponse(json.dumps(responses[page]).encode())

    monkeypatch.setattr(check_schema_adoption.urllib.request, "urlopen", fake_urlopen)
    paths = check_schema_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")
    assert paths == ["schemas/sleep/sleep-episode-1.0.json"]
    # Proves each request actually asked for the next page — a fixed page=1 implementation
    # (which would still pass a naive test popping a canned list) would fail this.
    assert requested_pages == [1, 2]


def test_fetch_schema_paths_raises_on_non_json(monkeypatch):
    # A WAF challenge answers 200 with HTML; this must surface as an error, never as [].
    monkeypatch.setattr(
        check_schema_adoption.urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(b"<html>blocked</html>"),
    )
    with pytest.raises(RuntimeError, match="non-JSON"):
        check_schema_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")


def test_fetch_schema_paths_raises_on_request_failure(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise check_schema_adoption.urllib.error.URLError("boom")

    monkeypatch.setattr(check_schema_adoption.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="request failed"):
        check_schema_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")


def test_fetch_schema_paths_raises_when_page_cap_exceeded(monkeypatch):
    # An API that ignores '?page=' and always returns the same non-empty page must not loop forever.
    monkeypatch.setattr(
        check_schema_adoption.urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(json.dumps(
            [{"type": "blob", "path": "schemas/x/y-1.0.json"}]
        ).encode()),
    )
    with pytest.raises(RuntimeError, match="exceeded"):
        check_schema_adoption.fetch_schema_paths("omh%2F1752", "1.0.2")


# --- main(): exit codes ---


def test_main_returns_zero_with_findings_and_reports_them(monkeypatch):
    monkeypatch.setattr(
        check_schema_adoption, "fetch_schema_paths",
        lambda project, ref, path=check_schema_adoption.DEFAULT_PATH: [
            "schemas/physical_activity/physical-activity-1.0.json",
            "schemas/sleep/sleep-episode-1.0.json",
            "schemas/sleep/total-sleep-time-1.0.json",
            "schemas/heart_rate/heart-rate-1.0.json",
        ],
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        status = check_schema_adoption.main(["--ref", "1.0.2", "--json"])
    assert status == 0
    report = json.loads(buf.getvalue())
    assert report["findings"] == [
        {"data_type": "heart_rate", "measure": "heart-rate", "kind": "ADOPT",
         "versions": ["1.0"], "current": "omh:heart-rate:2.0",
         "superseded_by": "", "deprecation_date": ""},
    ]
    assert report["ieee"] == {"ran": True, "error": "", "ref": "1.0.2"}


def test_main_returns_nonzero_on_fetch_failure(monkeypatch, capsys):
    def fake_fetch(project, ref, path=check_schema_adoption.DEFAULT_PATH):
        raise RuntimeError("network is down")

    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", fake_fetch)
    assert check_schema_adoption.main(["--ref", "1.0.2"]) == 1
    assert "network is down" in capsys.readouterr().err


# --- find_deprecations: the primary signal (pure, no network) ---


def _deprecated(superseded_by, date="2022-12-01"):
    return {"deprecation": {"reason": "superseded", "supersededBy": superseded_by, "date": date}}


def test_find_deprecations_flags_a_resolved_schema():
    # heart_rate resolves to omh:heart-rate:2.0, so a deprecation on it is actionable.
    schemas = {"omh:heart-rate:2.0": _deprecated("https://w3id.org/ieee/ieee-1752-schema/heart-rate.json")}
    findings = check_schema_adoption.find_deprecations(schemas)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == "DEPRECATED"
    assert finding.current == "omh:heart-rate:2.0"
    assert finding.data_type == "heart_rate"
    assert finding.superseded_by == "https://w3id.org/ieee/ieee-1752-schema/heart-rate.json"
    assert finding.deprecation_date == "2022-12-01"


def test_find_deprecations_ignores_schema_without_deprecation_block():
    assert check_schema_adoption.find_deprecations({"omh:heart-rate:2.0": {"type": "object"}}) == []


def test_find_deprecations_reports_only_the_deprecated_ones_in_a_mixed_set():
    schemas = {
        "omh:heart-rate:2.0": _deprecated("omh:pulse:1.0"),
        "omh:blood-glucose:4.0": {"type": "object"},
        "omh:oxygen-saturation:2.0": _deprecated("omh:spo2:1.0"),
    }
    findings = check_schema_adoption.find_deprecations(schemas)
    assert [f.current for f in findings] == ["omh:heart-rate:2.0", "omh:oxygen-saturation:2.0"]


def test_find_deprecations_treats_the_four_served_only_schemas_as_expected():
    """The real state: deprecated, served-only, successor already vendored — not a finding."""
    schemas = {
        "omh:step-count:3.0": _deprecated("https://w3id.org/ieee/ieee-1752-schema/physical-activity.json"),
        "omh:sleep-duration:2.0": _deprecated("omh:total-sleep-time:1.x", date="2020-05-05"),
        "omh:physical-activity:1.2": _deprecated("https://w3id.org/ieee/ieee-1752-schema/physical-activity.json"),
        "omh:sleep-episode:1.1": _deprecated("https://w3id.org/ieee/ieee-1752-schema/sleep-episode.json"),
    }
    assert check_schema_adoption.find_deprecations(schemas) == []


def test_find_deprecations_flags_served_only_schema_whose_successor_is_not_vendored():
    # Non-vacuity proof for the expected-deprecation branch: same served-only shape as the
    # four above, but omh-shim vendors nothing named 'heart-rate-variability', so it is real.
    schemas = {
        "omh:rr-interval:1.0": _deprecated(
            "https://w3id.org/ieee/ieee-1752-schema/heart-rate-variability.json"
        ),
    }
    findings = check_schema_adoption.find_deprecations(schemas)
    assert len(findings) == 1
    assert findings[0].current == "omh:rr-interval:1.0"
    assert findings[0].data_type == ""


def test_find_deprecations_flags_a_resolved_schema_even_when_successor_is_vendored():
    """The served-only exemption must not swallow a deprecation on something we emit."""
    schema_ids = {**SCHEMA_IDS, "sleep_episode": "omh:sleep-episode:1.1"}
    schemas = {
        "omh:sleep-episode:1.1": _deprecated("https://w3id.org/ieee/ieee-1752-schema/sleep-episode.json"),
    }
    findings = check_schema_adoption.find_deprecations(schemas, schema_ids)
    assert [f.kind for f in findings] == ["DEPRECATED"]


def test_find_deprecations_flags_a_deprecation_with_no_supersededby():
    schemas = {"omh:rr-interval:1.0": {"deprecation": {"reason": "retired"}}}
    findings = check_schema_adoption.find_deprecations(schemas)
    assert len(findings) == 1
    assert findings[0].superseded_by == ""


def test_is_expected_deprecation_both_branches():
    evidence = check_schema_adoption.successor_evidence()
    assert check_schema_adoption.is_expected_deprecation(
        "omh:step-count:3.0",
        "https://w3id.org/ieee/ieee-1752-schema/physical-activity.json",
        SCHEMA_IDS, evidence,
    )
    assert not check_schema_adoption.is_expected_deprecation(
        "omh:step-count:3.0",
        "https://w3id.org/ieee/ieee-1752-schema/step-cadence.json",
        SCHEMA_IDS, evidence,
    )


# --- fetching upstream OMH schemas ---


def test_omh_schema_url_uses_the_upstream_layout():
    assert check_schema_adoption.omh_schema_url("omh:step-count:3.0", "main") == (
        "https://raw.githubusercontent.com/openmhealth/schemas/main/schema/omh/step-count-3.0.json"
    )


def test_fetch_omh_schemas_reports_one_failure_without_losing_the_others(monkeypatch):
    def fake_urlopen(req, timeout=None):
        if "heart-rate" in req.full_url:
            raise check_schema_adoption.urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        return _FakeResponse(json.dumps({"type": "object"}).encode())

    monkeypatch.setattr(check_schema_adoption.urllib.request, "urlopen", fake_urlopen)
    schemas, failures = _REAL_FETCH_OMH_SCHEMAS(["omh:heart-rate:2.0", "omh:blood-glucose:4.0"])
    assert list(schemas) == ["omh:blood-glucose:4.0"]
    assert len(failures) == 1
    assert "omh:heart-rate:2.0" in failures[0]


def test_fetch_omh_schemas_reports_non_json_as_a_failure(monkeypatch):
    # A WAF challenge answers 200 with HTML; that must be a named failure, not a schema.
    monkeypatch.setattr(
        check_schema_adoption.urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(b"<html>blocked</html>"),
    )
    schemas, failures = _REAL_FETCH_OMH_SCHEMAS(["omh:heart-rate:2.0"])
    assert schemas == {}
    assert "omh:heart-rate:2.0" in failures[0]


# --- main(): the deprecation check is wired into both output modes ---


def _ieee_paths(project, ref, path=None):
    return [
        "schemas/physical_activity/physical-activity-1.0.json",
        "schemas/sleep/sleep-episode-1.0.json",
        "schemas/sleep/total-sleep-time-1.0.json",
    ]


def test_main_json_carries_deprecation_findings(monkeypatch, capsys):
    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", _ieee_paths)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": _deprecated("omh:pulse:1.0")}, []),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [f["kind"] for f in report["findings"]] == ["DEPRECATED"]
    assert report["findings"][0]["superseded_by"] == "omh:pulse:1.0"
    assert report["omh"]["ran"] is True


def test_main_table_shows_served_only_deprecations_as_ok(monkeypatch, capsys):
    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", _ieee_paths)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({
            "omh:step-count:3.0": _deprecated(
                "https://w3id.org/ieee/ieee-1752-schema/physical-activity.json"
            ),
        }, []),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2"]) == 0
    out = capsys.readouterr().out
    assert "omh:step-count:3.0" in out
    assert "ok (served-only, successor vendored)" in out
    assert "No findings." in out


def test_main_warns_per_schema_on_an_omh_fetch_failure(monkeypatch, capsys):
    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", _ieee_paths)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({}, ["omh:heart-rate:2.0 from https://example: HTTPError: 404"]),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2", "--json"]) == 0
    captured = capsys.readouterr()
    assert "::warning::" in captured.err
    assert "omh:heart-rate:2.0" in captured.err
    assert json.loads(captured.out)["findings"] == []


# --- is_expected_deprecation: the successor must be real, live, and not the schema itself ---


def test_find_deprecations_flags_a_newer_version_of_the_same_measure():
    """OMH's usual deprecation shape: <measure> N -> <measure> N+1, which we do not vendor.

    Matching the successor by measure name alone reads its own name back out of the
    deprecated schema and calls it ok forever.
    """
    schemas = {"omh:rr-interval:1.0": _deprecated("omh:rr-interval:2.0")}
    findings = check_schema_adoption.find_deprecations(schemas)
    assert [f.current for f in findings] == ["omh:rr-interval:1.0"]
    assert findings[0].superseded_by == "omh:rr-interval:2.0"


def test_find_deprecations_flags_when_the_only_vendored_successor_is_itself_deprecated():
    """The chain case: omh:step-count:3.0 is vendored under the name 'step-count' but is
    deprecated, so it is not evidence that anything was acted on."""
    schemas = {
        "omh:rr-interval:1.0": _deprecated("https://w3id.org/ieee/ieee-1752-schema/step-count.json"),
    }
    assert [f.current for f in check_schema_adoption.find_deprecations(schemas)] == [
        "omh:rr-interval:1.0"
    ]


def test_successor_evidence_excludes_deprecated_vendored_schemas():
    evidence = check_schema_adoption.successor_evidence()
    assert evidence["physical-activity"] == frozenset({"ieee:physical-activity:1.0"})
    # Every vendored schema named step-count / sleep-duration carries a deprecation block.
    assert "step-count" not in evidence
    assert "sleep-duration" not in evidence


def test_find_deprecations_still_accepts_a_cross_namespace_successor_of_the_same_name():
    """omh:physical-activity:1.2 -> IEEE physical-activity shares the measure name but is a
    different, live vendored schema — the acted-on case must stay ok."""
    schemas = {
        "omh:physical-activity:1.2": _deprecated(
            "https://w3id.org/ieee/ieee-1752-schema/physical-activity.json"
        ),
    }
    assert check_schema_adoption.find_deprecations(schemas) == []


# --- run_omh_check: fetching nothing is "did not run", not "nothing is deprecated" ---


def test_run_omh_check_treats_zero_fetched_as_not_having_run(monkeypatch, capsys):
    failures = [f"omh:schema-{i}:1.0 from https://example: HTTPError: HTTP Error 429" for i in range(14)]
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas", lambda ids, ref="main": ({}, failures)
    )
    result = check_schema_adoption.run_omh_check(
        "main", SCHEMA_IDS, check_schema_adoption.successor_evidence()
    )
    assert result.ran is False
    assert result.findings == []
    assert "0 of 14 omh: schema(s)" in result.error
    assert "429" in result.error
    err = capsys.readouterr().err
    assert "::warning::" in err
    assert "0 of 14" in err


def test_run_omh_check_runs_when_at_least_one_schema_was_fetched(monkeypatch):
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": {"type": "object"}}, ["one failed"]),
    )
    result = check_schema_adoption.run_omh_check(
        "main", SCHEMA_IDS, check_schema_adoption.successor_evidence()
    )
    assert result.ran is True
    assert result.findings == []


# --- main(): the two sources fail independently ---


def test_main_still_reports_omh_findings_when_the_ieee_fetch_fails(monkeypatch, capsys):
    """The 2026-08-31/09-07 WAF block must not discard the primary signal."""
    def fake_ieee(project, ref, path=check_schema_adoption.DEFAULT_PATH):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", fake_ieee)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": _deprecated("omh:pulse:1.0")}, []),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2", "--json"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["omh"]["ran"] is True
    assert report["ieee"]["ran"] is False
    assert "403" in report["ieee"]["error"]
    assert [f["current"] for f in report["findings"]] == ["omh:heart-rate:2.0"]
    assert "::warning::" in captured.err


def test_main_table_names_a_source_that_did_not_run(monkeypatch, capsys):
    def fake_ieee(project, ref, path=check_schema_adoption.DEFAULT_PATH):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", fake_ieee)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": {"type": "object"}}, []),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2"]) == 0
    out = capsys.readouterr().out
    assert "NOT evaluated" in out
    assert "No findings. The resolved schema ids are current with both publishers." not in out


def test_main_returns_nonzero_only_when_both_sources_fail(monkeypatch, capsys):
    def fake_ieee(project, ref, path=check_schema_adoption.DEFAULT_PATH):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", fake_ieee)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas", lambda ids, ref="main": ({}, ["all down"])
    )
    assert check_schema_adoption.main(["--ref", "1.0.2"]) == 1
    out = capsys.readouterr().out
    assert "Neither source was evaluated" in out
    assert "No findings" not in out


def test_main_json_reports_both_sources_down_and_exits_nonzero(monkeypatch, capsys):
    def fake_ieee(project, ref, path=check_schema_adoption.DEFAULT_PATH):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", fake_ieee)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas", lambda ids, ref="main": ({}, ["all down"])
    )
    assert check_schema_adoption.main(["--ref", "1.0.2", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["omh"]["ran"] is False
    assert report["ieee"]["ran"] is False
    assert report["findings"] == []


# --- a partial OMH fetch is a partial result, not a clean one ---


def test_run_omh_check_carries_the_ids_it_could_not_fetch(monkeypatch):
    """1-of-14 failing still runs, but the unchecked id must not vanish into stderr:
    an upstream rename gives a permanent 404 and that schema then goes unchecked forever."""
    failure = "omh:rr-interval:1.0 from https://raw...: HTTPError: HTTP Error 404: Not Found"
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": {"type": "object"}}, [failure]),
    )
    result = check_schema_adoption.run_omh_check(
        "main", SCHEMA_IDS, check_schema_adoption.successor_evidence()
    )
    assert result.ran is True
    assert result.fetched == 1
    assert result.failed == (failure,)


def test_run_omh_check_reports_no_failures_on_a_complete_fetch(monkeypatch):
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": {"type": "object"}}, []),
    )
    result = check_schema_adoption.run_omh_check(
        "main", SCHEMA_IDS, check_schema_adoption.successor_evidence()
    )
    assert result.failed == ()
    assert result.fetched == 1


def test_main_json_carries_the_partial_fetch_shape(monkeypatch, capsys):
    failure = "omh:rr-interval:1.0 from https://raw...: HTTPError: HTTP Error 404: Not Found"
    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", _ieee_paths)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": {"type": "object"}}, [failure]),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2", "--json"]) == 0
    omh = json.loads(capsys.readouterr().out)["omh"]
    assert omh["ran"] is True
    assert omh["fetched"] == 1
    assert omh["failed"] == [failure]


def test_main_table_names_a_partially_evaluated_source(monkeypatch, capsys):
    failure = "omh:rr-interval:1.0 from https://raw...: HTTPError: HTTP Error 404: Not Found"
    monkeypatch.setattr(check_schema_adoption, "fetch_schema_paths", _ieee_paths)
    monkeypatch.setattr(
        check_schema_adoption, "fetch_omh_schemas",
        lambda ids, ref="main": ({"omh:heart-rate:2.0": {"type": "object"}}, [failure]),
    )
    assert check_schema_adoption.main(["--ref", "1.0.2"]) == 0
    out = capsys.readouterr().out
    assert "PARTIALLY evaluated" in out
    assert "omh:rr-interval:1.0" in out


# --- the resolver refusing a newly-deprecated candidate must be diagnosed, not guessed at ---


def test_main_reports_an_omh_shim_import_failure_as_an_error(monkeypatch, capsys):
    """The weekly job runs this step after the refresh has rewritten the vendored tree, so
    the rule-3 invariant can fire here — and 'the WAF blocked us' is the wrong diagnosis."""
    invariant = (
        "heart_rate: candidate 'omh:heart-rate:2.0' is deprecated by its publisher in "
        "favor of '.../heart-rate.json' — omh-shim never emits a deprecated schema"
    )
    monkeypatch.setattr(check_schema_adoption, "IMPORT_ERROR", invariant)
    assert check_schema_adoption.main(["--ref", "1.0.2"]) == 1
    captured = capsys.readouterr()
    assert "::error::" in captured.err
    assert "_SCHEMA_CANDIDATES" in captured.err
    assert invariant in captured.err
    assert captured.out == ""
