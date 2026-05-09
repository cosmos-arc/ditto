# Analysis Review Report

> Date: 2026-05-08
> Scope: `packages/analysis`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Analysis is the pure research analysis plane. Current runtime surface is the research dataset control-plane: research domain models, catalog/artifact services, storage, DI, and contracts. Reports, diagnostics, experiments, and screeners are reserved/future namespaces with empty public API.

The package boundary is healthy: analysis depends on kernel/platform and does not depend on production domain packages or application/apps. Guard coverage is stronger than average: production-to-analysis imports and reserved namespace honesty are checked by architecture smell tests.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 19 Python source files, 10 test files, about 1,116 source LOC. |
| Largest files | `research/domain.py` 225, `research/reader.py` 218, `research/writer.py` 161, `artifact_service.py` 147. |
| Root API | `ditto_analysis.__all__` exports `AnalysisError`, `ResearchDatasetError`, and `ResearchDatasetSpec`. |
| Reserved namespaces | `reports`, `diagnostics`, `experiments`, `screeners` each say reserved/future, no public runtime API, production code must not depend on them, and export empty `__all__`. |
| Research model | `ResearchDatasetSpec` validates v1 as `left_preserving_pit` and derived inputs only; `SpineSpec` validates `cn_stock`, `1d`, `instrument_id`. |
| Late arrivals | `SHIFT_TO_NEXT_SNAPSHOT` currently warns and returns unchanged; `REQUIRE_REBUILD` raises. |
| Guards | `check_analysis_placeholder_honesty` and active-doc checks prevent reserved namespaces being described as implemented capabilities. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| ANALYSIS-P1-01 | P1 | `ResearchDatasetFacade` lives in application and directly imports analysis services/domain. | The only runtime research use-case is owned above analysis, making analysis ports less reusable and harder to guard. | Add application-owned research ports or move a neutral facade contract into analysis with application orchestration only. |
| ANALYSIS-P1-02 | P1 | `SHIFT_TO_NEXT_SNAPSHOT` warns and returns unchanged in v1. | A named late-arrival policy can look implemented while preserving potentially late data. | Mark SHIFT policy reserved/unsupported in maturity docs or implement actual shift semantics before exposing it. |
| ANALYSIS-P1-03 | P1 | Research v1 validates `cn_stock`, `1d`, and derived-only inputs, but product roadmap language is global/full-market. | Research capability may be overclaimed beyond current v1 constraints. | Keep research control-plane initial-focus for A-share daily derived datasets; all broader research products remain experimental/reserved. |
| ANALYSIS-P2-01 | P2 | Reserved namespace guards exist but are partly hard-coded in architecture script paths/phrases. | New reserved analysis namespace may bypass guard unless script is updated. | Move reserved namespace list into maturity/public API manifest or add a single enforcement source. |

No P0 finding was confirmed. Analysis is intentionally narrow and guarded; the main work is application port ownership and policy honesty.

## 4. TDD 整改计划

1. Research ports:
   - RED: prove application can build a research dataset through ports rather than concrete analysis services.
   - GREEN: add protocol layer or move facade boundary.
   - REFACTOR: keep storage/DI in analysis and orchestration in application/apps.

2. Late arrival policy:
   - RED: test that SHIFT either changes snapshot membership or is rejected as unsupported.
   - GREEN: implement shift semantics or raise a clear unsupported error.
   - REFACTOR: document policy maturity.

3. Reserved namespace guard:
   - RED: add a fake reserved namespace and assert guard catches missing maturity/public API entry.
   - GREEN: make maturity manifest or a small config the enforcement source.
   - REFACTOR: reduce hard-coded phrase drift.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-analysis-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/analysis/tests && pixi run -e dev arch-check && pixi run -e dev check`.

