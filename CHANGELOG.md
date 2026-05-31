# Changelog

All notable changes to omh-shim are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
