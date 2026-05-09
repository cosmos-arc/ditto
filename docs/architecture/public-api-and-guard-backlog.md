# Public API And Guard Backlog

> Date: 2026-05-08
> Source: full module review execution under `docs/reviews/audit/modules/`

This backlog records the guard and public API work that should follow the review findings. It is not an implementation plan for one package; it is the cross-package enforcement list that keeps future changes from reopening the same ambiguity.

## Public API Tables To Add

| Area | Trigger Findings | Required Table |
|---|---|---|
| Kernel stable/candidate/internal symbols | `KERNEL-P2-01`, `KERNEL-P2-02` | Stable root exports, candidate runtime/reference symbols, leaf-only internals. |
| Portfolio/strategy/execution/application names | `PORT-P2-01`, `STRAT-P2-01`, `APP-P2-02` | Strategy target weights vs portfolio target store vs execution actual position vs app read model. |
| Features service surface | `FEAT-P2-02` | Stable service facades vs internal stores/readers/writers. |
| Application DTOs and ports | `APP-P1-01`, `APP-P1-04`, `APP-P2-02` | App-owned ports, concrete provider allowances, DTO/read-model names. |
| Analysis research and reserved namespaces | `ANALYSIS-P1-01`, `ANALYSIS-P2-01` | Research control-plane API vs reserved reports/diagnostics/experiments/screeners. |

## Architecture Guards To Add Or Tighten

| Guard | Trigger Findings | Enforcement Source |
|---|---|---|
| Public `__all__` budget and stable symbol table | `KERNEL-P2-01`, `FEAT-P2-02` | Package `CLAUDE.md` or generated `docs/architecture/public-api.md`. |
| Dataset enum budget and maturity requirement | `DATA-P1-02`, `APP-P1-03`, `APPS-P1-02` | `capability-maturity.md` until a YAML derivative exists. |
| DataCatalog/Lineage runtime honesty | `DATA-P1-01`, `FEAT-P1-01` | DataCatalog runtime marker plus maturity manifest. |
| SQL/noqa budget | `PLAT-P1-01`, `DATA-P2-02`, `FEAT-P2-02` | `scripts/architecture/check_architecture_smells.py` plus per-helper allowlist. |
| Consumer-owned data/research ports | `DATA-P1-03`, `APP-P1-04`, `ANALYSIS-P1-01` | Import smell check for data provider and analysis concrete service imports. |
| Apps maturity-aware route/help text | `APPS-P1-02` | Route/model/help text scanner against maturity manifest. |
| Golden E2E proof lane | `APPS-P1-01` | CI-required synthetic fixture lane separate from optional TDX/Tushare tests. |
| Reserved namespace source of truth | `ANALYSIS-P2-01` | Maturity/public API manifest instead of hard-coded script-only list. |

## Reopen Rules

Reopen this backlog before any change that:

- Adds a root package export.
- Adds a new `Dataset` enum member, route family, template family, broker/gateway, or analysis namespace.
- Adds a SQL `S608` suppression or string-built SQL helper.
- Adds application or apps imports of concrete capability/data/research services outside an existing owner/reason allowance.
- Claims paper/live/global-market capability readiness in public docs, API text, or CLI help.

