# Capability Architecture 100 Point Review

Date: 2026-05-05

## Final Score

| Area | Points | Result | Evidence |
| --- | ---: | --- | --- |
| Import architecture | 24 | Pass | Import-linter reported `Contracts: 36 kept, 0 broken.` |
| Semantic ownership | 32 | Pass | Data, platform, execution, and legacy publication ownership searches are clean except documented guardrail-test references. |
| Machine guardrails | 20 | Pass | `pixi run -e dev arch-check`, `pixi run -e dev check`, and `pixi run -e dev ci` passed. |
| Public contracts | 12 | Pass | Registry and capability contracts expose protocol/DTO surfaces without concrete storage leakage. |
| Documentation and source terminology | 4 | Pass | Platform notification docstrings and templates no longer own product-specific alert semantics. |
| Final verification record | 8 | Pass | This review records exact commands, exit statuses, results, and ownership alignment. |
| **Total** | **100** | **Pass** | Semantic ownership and machine guardrails agree. |

## Commands Run

| Command | Exit | Result |
| --- | ---: | --- |
| `pixi run -e dev arch-check` | 1 | RED reproduced. Import-linter reported `Contracts: 36 kept, 0 broken.` Smell check found 7 platform semantic-ownership issues. |
| `pixi run -e dev pytest packages/application/tests/unit/process/test_quality_patrol_unit.py packages/apps/tests/unit/jobs/tasks/test_dq_batch_unit.py packages/apps/tests/registry/test_notification_provider_unit.py packages/application/tests/integration/process/execution/test_delivery_integration.py packages/platform/tests/unit/notification packages/apps/tests/unit/notifications/test_manager_unit.py` | 1 | 75 tests passed, then the partial-suite global coverage threshold failed at 41.54%. |
| `pixi run -e dev pytest --no-cov packages/application/tests/unit/process/test_quality_patrol_unit.py packages/apps/tests/unit/jobs/tasks/test_dq_batch_unit.py packages/apps/tests/registry/test_notification_provider_unit.py packages/application/tests/integration/process/execution/test_delivery_integration.py packages/platform/tests/unit/notification packages/apps/tests/unit/notifications/test_manager_unit.py` | 0 | Focused behavior/template verification passed: `75 passed`. |
| `pixi run -e dev arch-check` | 0 | GREEN. Import-linter analyzed 803 files / 2384 dependencies and reported `Contracts: 36 kept, 0 broken.` Architecture smell check passed. Contract count stayed 36; analyzed file/dependency counts dropped because `ditto_platform.services.notification.business` was removed. |
| `pixi run -e dev check` | 1 | First full run passed lint/format/type, then `test-fast` exposed data-test observability isolation failure: data histogram metrics were registered after a worker had already configured metrics. |
| `pixi run -e dev pytest -v --import-mode=importlib -m 'not slow and not integration and not snapshot' --no-cov -q -x --tb=short` | 2 | Minimal reproduction for the developer-gate failure. First error: `Histogram metric definitions must be registered before configure_metrics()`. Fixed by resetting observability before data test metric registration. |
| `pixi run -e dev check` | 0 | Final developer gate passed. `ruff check .` passed; `ruff format .` left 1478 files unchanged; basedpyright reported `0 errors, 0 warnings, 0 notes`; fast tests reported `6160 passed, 25 skipped`; import-linter reported `Contracts: 36 kept, 0 broken`; architecture smell check passed. |
| `pixi run -e dev ci` | 0 | CI gate passed. `ruff check .` passed; `ruff format --check .` reported 1478 files already formatted; basedpyright normal and test projects reported `0 errors, 0 warnings, 0 notes`; coverage tests reported `6769 passed, 126 skipped`; total coverage was 93.37%; import-linter reported `Contracts: 36 kept, 0 broken`; architecture smell check passed. |
| `pixi run -e dev python -c "..."` | 1 | Post-review RED reproduced. After `make_app_container().get(MarketService)`, `Metrics.data_records` raised `AttributeError`. |
| `pixi run -e dev pytest --no-cov packages/apps/tests/unit/registry/infra/test_observability_flags_unit.py::test_make_app_container_registers_capability_metric_catalogs packages/apps/tests/unit/registry/infra/test_config_init_unit.py::test_config_provider_init_coordinator_creates_feature_artifact_dirs packages/apps/tests/unit/cli/commands/test_init_unit.py::TestInitConfigCommand::test_make_coordinator_registers_feature_artifact_dirs` | 1 | Post-review RED tests failed on missing app-container metric registration, unwired `FeatureArtifactStoreSettings` in `ConfigProvider`, and missing feature/factor directories in CLI init wiring. |
| Same targeted post-review pytest command | 0 | GREEN after wiring fixes: `3 passed`. |
| `pixi run -e dev pytest --no-cov packages/apps/tests/unit/registry/infra/test_observability_flags_unit.py packages/apps/tests/unit/registry/infra/test_config_init_unit.py packages/apps/tests/unit/cli/commands/test_init_unit.py` | 0 | Focused post-review behavior suite passed: `13 passed`. |
| `pixi run -e dev arch-check` | 1 | Post-review boundary regression caught. Import-linter kept all 36 contracts, but smell check rejected a CLI direct import of `ditto_features.config`. |
| `pixi run -e dev arch-check` | 0 | GREEN after moving feature artifact directory derivation behind the registry composition helper. Import-linter analyzed 803 files / 2385 dependencies and reported `Contracts: 36 kept, 0 broken`; architecture smell check passed. |
| `pixi run -e dev check` | 0 | Post-review developer gate passed. `ruff check .` passed; `ruff format .` left 1479 files unchanged; basedpyright reported `0 errors, 0 warnings, 0 notes`; fast tests reported `6163 passed, 25 skipped`; import-linter reported `Contracts: 36 kept, 0 broken`; architecture smell check passed. |
| `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --dist loadfile --no-cov -x` | 2 | Post-review full-suite RED reproduced cross-package observability ordering. First run failed in apps integration setup after platform metrics initialized first; second run exposed the same late histogram registration after platform tests reset app metric catalogs mid-worker. |
| `pixi run -e dev pytest --no-cov packages/apps/tests/unit/registry/infra/test_observability_flags_unit.py::test_make_app_container_handles_platform_initialized_metrics -q` | 1 | RED regression reproduced app container creation after platform-only `init(...)`: capability histogram registration raised `RuntimeError`. |
| Same targeted platform-initialized app-container pytest command | 0 | GREEN after app metric registration resets stale pytest observability state before retrying: `1 passed`. |
| `pixi run -e dev pytest --no-cov packages/apps/tests/unit/registry/infra/test_observability_flags_unit.py packages/apps/tests/unit/registry/infra/test_config_init_unit.py packages/apps/tests/unit/cli/commands/test_init_unit.py packages/apps/tests/integration/flows/test_derived_materialization_query_repair_integration.py::TestDerivedMaterializationQueryRepairIntegration::test_materialize_query_and_repair_flow_share_one_artifact_chain -q` | 0 | Focused post-review suite passed after the cross-package observability fix: `15 passed`. |
| `pixi run -e dev pytest --no-cov packages/platform/tests/unit/config/test_data_root_provider_unit.py -q` | 1 | RED reproduced final-review residual risk. Existing data roots with missing configured child directories were incorrectly treated as already initialized. |
| `pixi run -e dev pytest --no-cov packages/platform/tests/unit/config/test_data_root_provider_unit.py packages/apps/tests/unit/registry/infra/test_config_init_unit.py packages/apps/tests/unit/cli/commands/test_init_unit.py::TestInitConfigCommand::test_make_coordinator_registers_feature_artifact_dirs -q` | 0 | GREEN after `DataRootInitProvider.check()` began checking configured child directories: `4 passed`. |
| `pixi run -e dev pytest --no-cov packages/apps/tests/unit/cli/commands/test_init_unit.py::TestInitConfigCommand::test_init_config_uses_default_data_root packages/apps/tests/integration/cli/test_init_commands_integration.py::test_init_config_with_data_root -q` | 1 | RED reproduced final-review CLI scope issue. Non-force `ditto init config` used `InitScope.MANUAL`, so registered STARTUP providers did not create feature/factor directories or metadata DB. |
| `pixi run -e dev pytest --no-cov packages/apps/tests/unit/cli/commands/test_init_unit.py packages/apps/tests/integration/cli/test_init_commands_integration.py::test_init_config_with_data_root -q` | 0 | GREEN after CLI init commands use STARTUP scope by default and ALWAYS scope only with `--force`: `8 passed`. |
| `pixi run -e dev check` | 0 | Final developer gate passed. `ruff check .` passed; `ruff format .` left 1480 files unchanged; basedpyright reported `0 errors, 0 warnings, 0 notes`; fast tests reported `6166 passed, 25 skipped`; import-linter reported `Contracts: 36 kept, 0 broken`; architecture smell check passed. |
| `pixi run -e dev ci` | 0 | Final CI gate passed. `ruff check .` passed; `ruff format --check .` reported 1480 files already formatted; basedpyright normal and test projects reported `0 errors, 0 warnings, 0 notes`; coverage tests reported `6775 passed, 126 skipped`; import-linter reported `Contracts: 36 kept, 0 broken`; architecture smell check passed. |
| `rg -n "publication_safety|publication_shadow_sqlite|features/|factors/" packages/data/src -g '*.py'` | 1 | Pass. No matches; `rg` exit 1 is expected for no matches. |
| `rg -n "instrument_id|trade_date|factor_|portfolio_|risk\\.|dq_|golden_dataset|ticker" packages/platform/src -g '*.py'` | 1 | Pass. No matches; `rg` exit 1 is expected for no matches. |
| `rg -n "TYPE_CHECKING|__getattr__|import_module" packages/execution/src/ditto_execution/storage/sqlite/trade -g '*.py'` | 1 | Pass. No matches; `rg` exit 1 is expected for no matches. |
| `rg -n "ditto_data\\.storage\\.runtime\\.publication|ditto_data\\.ingestion\\.publication_safety" packages -g '*.py'` | 0 | Pass with documented false positives in `packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py:41` and `:42`, where stale import paths are asserted as forbidden guardrail terms. |

## Scope Confirmed

- Platform now owns only generic notification primitives and technical cache examples.
- DQ and signal notification templates are owned by the apps composition root.
- DQ alert context is built at application/apps call sites and sent through the generic `AlertManager`.
- Data tests reset observability before registering data-owned histogram metrics, so xdist worker ordering no longer creates late-registration failures.
- App container creation registers capability-owned metric catalogs before domain services access `Metrics.*`.
- App metric registration recovers from pytest workers where platform observability tests initialized or reset metrics before later app container creation.
- App and CLI data-root initialization include feature/factor artifact directories through the registry composition root.
- Data-root initialization now repairs existing roots that are missing any configured child directory.
- Non-force CLI init commands run STARTUP providers, so `ditto init config --data-root ...` creates the expected directory tree and metadata database without requiring `--force`.
- Data no longer owns derived feature/factor publication semantics.
- Execution trade storage no longer uses lazy import shims.
- Registry public bundle fields expose stable protocols instead of storage implementations.

## Remaining Out Of Scope

No architecture cleanup items remain for the 100 point gate. Product/environment gaps remain outside this remediation, including skipped tests that require TDX sample data, Prefect API server availability, Tushare credentials, or FRED credentials.

## Guardrail Agreement

The semantic ownership rules and machine guardrails now agree: import-linter accepts the 12-package dependency structure, the architecture smell checker passes, and targeted ownership searches show no active source ownership drift outside explicit guardrail-test strings.
