# Apps Review Report

> Date: 2026-05-08
> Scope: `packages/apps`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Apps is the application boundary layer: FastAPI routes, CLI commands, Prefect jobs, configuration loading, and the Dishka composition root. The current architecture explicitly allows registry composition to import capabilities and keeps ordinary routes/CLI/jobs on application facades, with one narrow DQ host-composition allowance in `jobs/context.py`.

The boundary has meaningful guard coverage. The key remaining risks are end-to-end proof strength, registry/config fan-in, and preventing API/CLI text from overclaiming reserved or experimental maturity.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 109 Python source files, 136 test files, about 12,094 source LOC. |
| Largest files | `api/routes/backtest.py` 526, `api/routes/trade.py` 412, `jobs/tasks/dq_batch.py` 397, `main.py` 352, `models/fundamental.py` 322, `models/backtest.py` 317. |
| Composition boundary | Capability imports are concentrated under `registry/**`; non-registry direct imports scan finds only `jobs/context.py` DQ allowance. |
| Guard source | `APPS_HOST_COMPOSITION_ALLOWANCES` and `APPS_REGISTRY_COMPOSITION_ALLOWANCES` encode exact path/module allowances with owner and reason. |
| Config | `registry/infra/config.py` loads platform/data/features/app settings and derives data-root directories. |
| E2E skips | E2E fixtures skip if TDX samples or PIT snapshots are missing; full check currently reports 25 skips. |
| API models | Apps expose broad market/fundamental/fx/commodity/backtest/trade models even when maturity varies. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| APPS-P1-01 | P1 | E2E tests require local TDX samples and PIT snapshots; when missing they skip. | Full check can pass without proving the most important end-to-end data/runtime path. | Add a small committed synthetic golden dataset or CI artifact path for one complete E2E lane. |
| APPS-P1-02 | P1 | API/CLI surface covers broad domains while maturity manifest marks many as experimental/reserved. | Users can infer current production readiness from endpoint/model presence alone. | Add maturity-aware docs/route metadata and forbid reserved capability wording in API/CLI help. |
| APPS-P1-03 | P1 | `registry/infra/config.py` and registry contexts own broad infra/capability composition. | Composition root is correct but can accumulate business facts and become hard to audit. | Keep registry as composition only; move dataset/maturity/runtime facts to architecture manifests or application/data configs. |
| APPS-P2-01 | P2 | Large route/job files mix request parsing, facade calls, response shaping, and status mapping. | Route changes become harder to review for thin-boundary compliance. | Split large routes/jobs by subresource or response mapping once behavior snapshots exist. |
| APPS-P2-02 | P2 | Single DQ host-composition allowance exists in `jobs/context.py`. | Narrow exception can expand by copy/paste if not watched. | Keep exact allowance as the enforcement source and require owner/reason for any new exception. |

No P0 finding was confirmed. The boundary is guarded; E2E evidence and maturity-aware API text are the main hardening items.

## 4. TDD 整改计划

1. Golden E2E lane:
   - RED: add an E2E test that fails when the committed synthetic fixtures are absent.
   - GREEN: add tiny deterministic data snapshots and route/CLI smoke test.
   - REFACTOR: keep external TDX/Tushare tests optional but separate from core proof.

2. Maturity-aware API:
   - RED: test route/help text does not claim reserved/experimental capabilities as production-ready.
   - GREEN: expose maturity metadata or doc annotations sourced from the manifest.
   - REFACTOR: centralize capability labels.

3. Registry budget:
   - RED: add guard for new registry capability imports without exact allowance owner/reason.
   - GREEN: update allowance list only for deliberate composition.
   - REFACTOR: keep configs declarative.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-apps-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/apps/tests && pixi run -e dev arch-check && pixi run -e dev check`.

