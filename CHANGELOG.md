# Changelog

All notable changes to omh-shim are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] — 2026-09-07

### Changed (BREAKING)

- Body schemas now resolve **IEEE 1752 first, Open mHealth second**, and
  **omh-shim never emits a schema its publisher has deprecated**. `SCHEMA_IDS`
  is derived from a candidate table ranked by namespace precedence rather than
  hand-written, and import-time guards reject a vendored candidate carrying a
  `deprecation` block, an unknown namespace, a candidate whose measure name is
  neither its data type's nor the successor that measure's Open mHealth schema
  declares in `deprecation.supersededBy`, a malformed schema id, more than one
  candidate per namespace, and any data type that resolves to no vendored
  schema. Following a dated `supersededBy` pointer is the publisher's own
  instruction, not inference — the successor name is read from the vendored
  file at import, so nobody can declare a successor the publisher did not.
- `sleep_duration` emits `ieee:total-sleep-time:1.0` (was
  `omh:sleep-duration:2.0`, which OMH deprecated on 2020-05-05 in favor of
  `omh:total-sleep-time:1.x`, itself since deprecated in favor of IEEE's
  `total-sleep-time`). The body field is renamed `sleep_duration` ->
  `total_sleep_time`; values and time frames are unchanged.
- `physical_activity` now emits `base_movement_quantity` (unit `steps`) when the
  source record carries a step count. Both sources' `physical_activity` bodies
  carry it: Oura's `steps` (from `daily_activity`) and OW's `steps` (from
  `ActivitySummary`).
- `physical_activity` emits `ieee:physical-activity:1.0` (was
  `omh:physical-activity:1.2`). No converter change — IEEE's `activity_name` is
  a free-form string and both required fields were already emitted.
- `sleep_episode` emits `ieee:sleep-episode:1.0` (was `omh:sleep-episode:1.1`),
  and its efficiency field is renamed `sleep_maintenance_efficiency_percentage`
  -> `sleep_efficiency_percentage` to match IEEE. **Note:**
  `ieee:sleep-episode:1.0` does not set `additionalProperties: false`, so the
  old field name would have validated cleanly while IEEE-aware consumers
  dropped it.

### Removed (BREAKING)

- `step_count` is no longer a supported data type. OMH deprecated
  `omh:step-count:3.0` on 2022-12-01 in favor of `ieee:physical-activity:1.0`,
  "which models also number of steps", so steps now ride on `physical_activity`
  as `base_movement_quantity` (unit `steps`) — in **both** sources' bodies. Both
  `physical_activity` converters already read the record that carries `steps`
  (Oura `daily_activity`, OW `ActivitySummary`), so keeping `step_count` would
  have emitted two physical-activity observations per day from one record. The
  `ow_normalized` per-minute step timeseries shape has no IEEE home and is gone
  with it.
- `heart_rate_variability` is no longer a supported data type, and the
  hand-written `local:heart-rate-variability:1.0` schema is deleted. Neither
  IEEE 1752 nor Open mHealth publishes an HRV body schema. omh-shim no longer
  emits any non-standard schema; the `local:` namespace is gone.

### Changed

- The weekly adoption checker is renamed `tools/check_ieee_adoption.py` ->
  `tools/check_schema_adoption.py` and gains the primary signal it was missing:
  every `omh:` id in `known_ids()` — resolved and served-only — is fetched from
  `openmhealth/schemas` at `main` and reported as `DEPRECATED` when upstream
  carries a `deprecation` block. A deprecation on a served-only schema whose
  declared successor is vendored as a live (non-deprecated) schema is expected
  and reported as ok, so the four schemas listed under Added do not open an
  issue every week. The IEEE ADOPT/NEWER check stays as the secondary signal,
  and the two sources now run and fail independently — an IEEE outage no longer
  discards the Open mHealth result.

### Why these two moved (the publisher said so)

Neither change is a semantic judgment by omh-shim. Open mHealth ships a
machine-readable `deprecation` block in the schemas themselves, and both of
these have carried one for years — nested inside the schema, which is why a
top-level `deprecated`/`supersededBy` check never saw them:

- `step-count-3.0.json`, `date: "2022-12-01"` (committed upstream 2023-07-17),
  `supersededBy: "https://w3id.org/ieee/ieee-1752-schema/physical-activity.json"` —
  > "This schema is now deprecated, in favor of the IEEE 1752.1
  > physical-activity schema which models also number of steps."
- `sleep-duration-2.0.json`, `date: "2020-05-05"`,
  `supersededBy: "omh:total-sleep-time:1.x"` —
  > "This schema is now deprecated, in favor of the more precisely named
  > total-sleep-time."

Following a dated `supersededBy` pointer is the publisher's own instruction,
not inference. `omh:total-sleep-time:1.x` was itself deprecated upstream on
2026-06-18 in favor of IEEE's `total-sleep-time`, so IEEE-first resolution
lands on `ieee:total-sleep-time:1.0`.

### Added

- Vendored `ieee:physical-activity:1.0`, `ieee:sleep-episode:1.0` and
  `ieee:total-sleep-time:1.0` at IEEE ref 1.0.2, with physical-activity's
  `$ref` closure (`length`/`kcal`/`speed-unit-value-1.0`).
- `omh:step-count:3.0`, `omh:sleep-duration:2.0`, `omh:physical-activity:1.2`
  and `omh:sleep-episode:1.1` stay vendored as served-only schemas: all four are
  deprecated upstream, they are the evidence the successor invariant reads, and
  downstream consumers still validate historical records against them.
- Vendored IEEE's `descriptive-statistic-1.0` under `schemas/utility/ieee/`,
  alongside the Open mHealth schema of the same filename.

### Fixed

- IEEE bodies were being validated against Open mHealth's narrower
  `descriptive-statistic` enum. IEEE's has 17 values (it adds `count`,
  percentiles, quartiles and quintiles) where OMH's draft-04 variant has 7, and
  the validation registry registered the single vendored OMH file under the bare
  filename *and* both w3id permalinks — so `ieee:physical-activity:1.0` and
  `ieee:sleep-stage-summary:1.0` rejected `descriptive_statistic: "count"`,
  which IEEE explicitly permits. Both variants are now vendored and each is
  registered under the URI its own standard implies: an OMH body carries no
  `$id`, so its relative `$ref`s resolve to the bare filename and still get the
  7-value enum, while an IEEE body's `$id` re-bases its relative `$ref`s onto
  `https://w3id.org/ieee/ieee-1752-schema/`, which now serves IEEE's variant.
  Six OMH bodies (`blood-glucose:4.0`, `blood-pressure:4.0`,
  `body-temperature:4.0`, `body-weight:3.0`, `forced-vital-capacity:1.0`,
  `forced-expiratory-volume-1-second:1.0`) `$ref` the absolute IEEE URL rather
  than the filename, so they now accept IEEE's full enum — a widening upstream
  OMH wrote deliberately. `omh:step-count:3.0` is the only OMH body using the
  bare relative `$ref` and is unchanged.

- `tools/refresh_schemas.py`'s IEEE fetches were silently vendoring HTML: the
  WAF in front of the `/-/raw/` endpoint answers this tool's requests with a
  challenge page at HTTP 200, and `fetch()` treated that response as success.
  The fix is two-part — every response is now parsed as JSON unless explicitly
  exempted, and the request sends a User-Agent the WAF accepts (a bare tool
  name got the challenge page; a `curl`-prefixed UA does not). Measurement
  showed the transport was never the problem — the User-Agent was the only
  variable — so the endpoint is unchanged.

### Upgrading

- `heart_rate`, `oxygen_saturation` and `blood_glucose` keep their schema ids and
  stay on OMH, because IEEE 1752 defines no equivalent body. Their **validation**
  is not unchanged: the six OMH bodies that `$ref` IEEE's `descriptive-statistic`
  by absolute URL — `blood-glucose:4.0` among them — now accept IEEE's full
  17-value enum where 1.5.0 raised `ValidationError` on e.g.
  `descriptive_statistic: "count"`. That is a widening, so nothing that validated
  before stops validating; see Fixed. Every other type moved: `physical_activity`
  and `sleep_episode` to their IEEE namesakes, `sleep_duration` to
  `ieee:total-sleep-time:1.0`, and `step_count` is gone.
- Observations already stored under `omh:physical-activity:1.2`,
  `omh:sleep-episode:1.1`, `omh:step-count:3.0` or `omh:sleep-duration:2.0` keep
  those codes. New records use the new ids — a historical split, not a
  validation failure. All four Open mHealth schemas stay vendored and remain
  available through `known_ids()` / `load_schema()`, so consumers can keep
  validating those historical records.
- JupyterHealth Exchange already seeds `ieee:physical-activity:1.0` and
  `ieee:sleep-episode:1.0` CodeableConcepts, vendors both IEEE schemas, and
  resolves the `ieee:` namespace. It needs one more row: an
  `ieee:total-sleep-time:1.0` CodeableConcept, without which `sleep_duration`
  records have no code to land under. Deployments seeded before those rows
  existed need a re-seed.
- Consumers that read `heart_rate_variability` must drop it; JHE never ingested
  it, because it resolves only the `omh` and `ieee` namespaces.

## [1.5.0] — 2026-08-31

### Added

- Vendored `ieee:total-sleep-time:1.0` and `ieee:time-in-bed:1.0`, covering the
  two sleep codes JHE seeds that omh-shim did not serve. Both come from IEEE
  1752.1: OMH deprecated its own `total-sleep-time` on 2026-06-18 with
  `supersededBy` pointing at the IEEE schema of the same name, and OMH has no
  time-in-bed schema at all. Both are served-only, with no converter, like the
  other clinical bodies.

### Fixed

- `tools/refresh_schemas.py` sent a bare `omh-shim-refresh/1.0` User-Agent, which
  IEEE's WAF answers with a `200` HTML challenge page. The tool wrote that HTML
  over the vendored IEEE schemas without noticing. It now sends a CLI-client UA,
  applies the socket timeout, and refuses any response that is not JSON (the `.x`
  pointer fetches excepted). Backported from the 2.0.0 branch.

- `ow_normalized.blood_glucose` converter, mapping an OW `TimeSeriesSample` with
  `type=blood_glucose` to `omh:blood-glucose:4.0`. The vendored blood-glucose
  schema moves out of the served-only set into `SCHEMA_IDS`. Oura does not
  currently expose glucose through its API, so there is no `oura_raw`
  counterpart; glucose reaches Open Wearables through the mobile SDK.

## [1.4.0] — 2026-06-21

### Added

- Vendored the IEEE 1752 body schema `ieee:sleep-stage-summary:1.0` (and its
  IEEE utility refs `percent-unit-value-1.0` and
  `descriptive-statistic-denominator-1.0`) — the first `ieee:`-namespaced body
  schema served. Like the other clinical bodies it is served via `known_ids()` /
  `load_schema()` with no converter; tracked by `tools/refresh_schemas.py` and
  the offline `$ref`-closure test.

## [1.3.0] — 2026-06-11

### Added

- Vendored the clinical OMH pulmonary schemas `forced-vital-capacity:1.0` and
  `forced-expiratory-volume-1-second:1.0` plus their `volume-unit-value`
  utility ref. Served via `known_ids()` / `load_schema()` (no converters),
  like the other clinical schemas; tracked by `tools/refresh_schemas.py` and
  the offline `$ref`-closure test.

### Fixed

- Refreshed vendored schemas to OMH ref `c64fca0`, picking up the upstream fix
  for `body-weight-3.0`'s `$id` (previously self-referenced
  `body-weight-2.0.json`); removed the README note documenting that typo.

## [1.2.0] — 2026-06-03

### Added

- Vendored the clinical OMH body schema `body-weight:3.0` plus its
  `mass-unit-value` utility ref. Served via `known_ids()` / `load_schema()` (no
  converter), like the other clinical schemas; tracked by
  `tools/refresh_schemas.py` and the offline `$ref`-closure test.

## [1.1.0] — 2026-05-31

### Added

- `oura_raw.oxygen_saturation` converter — maps Oura's `daily_spo2`
  shape (`{day, spo2_percentage: {average}}`) to `omh:oxygen-saturation:2.0`.
  Both `oura_raw` and `ow_normalized` sources now support all 7 data types.
- Fixture files and parameterized test coverage for `oxygen_saturation`
  across both sources (`oura_raw` and `ow_normalized`). The
  `ow_normalized` converter existed previously but lacked test fixtures.
- `known_ids()` and `load_schema()` are now public (re-exported from the
  top-level package) so downstream consumers can enumerate and load any
  vendored schema by id without reaching into private modules.
- Vendored the clinical OMH body schemas `blood-glucose:4.0`,
  `blood-pressure:4.0`, `body-temperature:4.0`, `respiratory-rate:2.0`, and
  `rr-interval:1.0`, plus their transitive utility refs. These are served via
  `known_ids()` / `load_schema()` for downstream consumers (e.g. the
  JupyterHealth Exchange MCP server) that need to serve and validate OMH
  bodies; omh-shim has no wearable converter that produces them, so they are
  not part of `SCHEMA_IDS` / `convert()`. `tools/refresh_schemas.py` now tracks
  them for drift detection, and `tests/test_schema_coverage.py` asserts each
  one's full transitive `$ref` closure resolves offline.

## [1.0.1] — 2026-05-13

### Fixed

- `oura_raw` samples now produce an `external_datasheets` entry in the IEEE
  1752.1 header (`{datasheet_reference: "Oura Ring"}`). Previously the header
  omitted `external_datasheets` for `oura_raw` because raw samples don't carry
  a nested `source` dict, leaving downstream consumers without manufacturer
  provenance. Nested `source.device`/`source.provider` metadata still wins
  when present.

## [1.0.0] — 2026-05-13

### Changed — BREAKING

- `convert()` now takes a keyword-only ``tz`` parameter. Daily data types
  (`step_count`, `physical_activity`, `sleep_duration`) REQUIRE an explicit
  timezone so day boundaries reflect the user's local calendar day rather
  than silently assuming UTC. A Tokyo user's "April 9" is not UTC "April 9"
  — the previous behavior misaligned daily summaries by up to 24 hours for
  any non-UTC user.
- Naive (timezone-less) datetimes are now rejected with `ConversionError`
  at parse time. Silent coercion to UTC previously misrecorded a Tokyo
  user's "22:30" local time as "22:30 UTC".
- `heart_rate_variability` schema id renamed from
  `omh:heart-rate-variability:1.0` to `local:heart-rate-variability:1.0`.
  Open mHealth has not published a canonical HRV schema; the `local:`
  namespace prevents downstream consumers from assuming OMH-standard
  interoperability. Callers pinning the old id must update.
- `convert()` now wraps any `KeyError`/`ValueError`/`TypeError` from
  converters as `ConversionError` so the public contract ("invalid sample
  shape raises ConversionError") actually holds. Previously converters
  leaked raw `KeyError` in several paths.
- Converters raise `ConversionError` directly for domain errors (HRV
  normalized-score rejection, step_count unknown-shape rejection) rather
  than raw `KeyError`. The exception type is part of the contract, not an
  implementation detail of the `convert()` wrapper — callers invoking
  converters directly now see `ConversionError` as documented.
- `SCHEMA_IDS` is now a public mapping on the top-level package (was the
  private `_SCHEMA_ID`), and is wrapped in ``types.MappingProxyType`` so it
  is read-only at runtime. Use it to enumerate supported data types.
- Converter `tz` parameter is now keyword-only, matching `convert()`'s
  keyword-only `tz` kwarg. Internal dispatch passes `tz=tz` explicitly.
  `day_interval()` is also keyword-only `tz` for symmetry.
- `oura_raw.heart_rate` no longer silently rounds `bpm` to 1 decimal. It
  passes the value through unchanged so downstream consumers see the full
  precision the upstream API reported.

### Added

- Positive and negative regression tests for all timezone behavior,
  parametrized across every (source, data_type) pair that parses datetimes
  or aggregates days.
- DST regression tests (`test_day_interval_handles_spring_forward` and
  `..._fall_back`) that lock in correct wall-clock day boundaries across
  March 8 and November 1 2026 Los Angeles transitions.
- `validate=True` / `validate=False` regression tests confirming the
  opt-out actually bypasses schema validation (tests monkeypatch at
  ``omh_shim._validate.validate_output`` — the single stable location
  both the production code and the tests target).
- Fractional-precision regression tests for `oura_raw.heart_rate` and
  `ow_normalized.sleep_duration` (the latter proving the minutes→seconds
  scale runs BEFORE the int cast so 32.5 min → 1950 s, not 1920 s).
- Read-only invariants locked in by tests:
  `test_schema_ids_is_read_only`, `test_registry_is_read_only`,
  `test_registry_not_leaked_at_top_level`.
- Two import-time invariants (`raise RuntimeError`, not `assert`, so they
  survive `python -O`):
    1. `REGISTRY` and `SCHEMA_IDS` must stay in sync.
    2. `SCHEMA_IDS` values must match the explicit filename table in
       `_schema_loader`, preventing latent drift.
- `_Converter` is now a `typing.Protocol` with the correct
  `(sample, *, tz) -> dict` signature. mypy catches any converter whose
  shape diverges from the protocol at type-check time.
- `REGISTRY` and `SCHEMA_IDS` are wrapped in `types.MappingProxyType` so
  external code cannot inject converters or schema ids at runtime.
- mypy `--strict` in CI (via `.github/workflows/test.yml` and
  `[tool.mypy] strict = true` in `pyproject.toml`). The library is now
  fully type-annotated (parameterized `dict[str, Any]` throughout).

### Fixed

- `_validate.Draft7Validator` is now cached per schema id via
  `lru_cache(maxsize=16)` instead of rebuilt on every `convert()` call.
- `_schema_loader` uses an explicit `schema_id -> filename` lookup table
  instead of string substitution. The old derivation (`:`→`_`, `.`→`-`)
  had a latent collision: `omh:a.b:1.0` and `omh:a-b:1.0` would map to
  the same filename. Fix eliminates the hazard.
- `set_opt()` applies `scale` BEFORE `cast`, preserving precision for
  fractional inputs: ``int(32.5 * 60) = 1950`` rather than
  ``int(32.5) * 60 = 1920``. Existing integer callsites produce the same
  results; fractional inputs are now correct.
- `ow_normalized.sleep_duration` follows the same scale-then-cast order.
- `convert()` error messages now include the wrapped exception type name
  (``KeyError: 'bpm'`` rather than a bare ``'bpm'`` that looked like a
  stray quoted string).
- `day_interval` error message no longer hardcodes the enumeration of
  daily data types (would have gone stale if a 4th were added).
- Fixture `tests/fixtures/ow_normalized/heart_rate_expected.json`
  normalized to `72.0` to match what the converter actually produces
  (previously `72` int relied on Python dict equality to pass).

### Fixed

- `_validate.Draft7Validator` is now cached per schema id via `lru_cache`
  instead of rebuilt on every `convert()` call — real speedup for bulk
  ingest workloads.

## [0.1.0] — 2026-04-09

### Added

- Initial release of `omh-shim`.
- Public API: `convert(source, data_type, sample, *, validate=True) -> dict`,
  `ConversionError`, `ValidationError`.
- Sources: `ow_normalized` (Open Wearables read-API response shapes) and
  `oura_raw` (Oura v2 API response items).
- Data types: `heart_rate`, `heart_rate_variability`, `step_count`,
  `sleep_duration`, `sleep_episode`, `physical_activity` — 12 converters total.
- Vendored OMH JSON schemas (5 standard + 1 local HRV placeholder + 13
  transitive `$ref` dependencies) loaded via `importlib.resources`.
- `referencing.Registry`-based ref resolution so `Draft7Validator` resolves
  cross-schema `$ref` strings to local files without network access.
- Output validation by default with `validate=False` opt-out.
- 26 unit tests covering all 12 converters plus edge cases.

### Attribution

- `omh_shim/sources/oura_raw/` ports converter mapping logic from
  [dicristea/oura-clinical-workbench/data_syn](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn)
  with permission. Each `oura_raw` source file carries an attribution header.

### Known limitations

- No real-data fixtures yet; the test fixtures are hand-written from OW's
  pydantic response schemas and Oura v2 API docs. Real-data validation will
  happen when JupyterHealth Exchange's polling pipeline starts consuming
  this library against live OW and Oura sandbox endpoints.
- The `oura_raw.heart_rate_variability` converter requires an explicit
  millisecond value (`rmssd` or `contributors.hrv_balance_ms`); it refuses
  to convert Oura's normalized 0–100 `hrv_balance` score because that score
  is not a valid HRV measurement in milliseconds.
- `omh:physical-activity:1.2` is the latest version available upstream. The
  spec mentioned 2.0; that version does not exist in `openmhealth/schemas`.
