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
| Public `__all__` budget and stable symbol table | `KERNEL-P2-01`, `FEAT-P2-02` | Root `__all__` coverage is guarded for 12/12 packages as of 2026-06-08; `docs/architecture/public-api.md` now records the 12-package root stable export table and is drift-guarded against each root `__all__`. Remaining work is leaf-level candidate/internal symbol tables for high-churn packages. |
| Dataset enum budget and maturity requirement | `DATA-P1-02`, `APP-P1-03`, `APPS-P1-02` | `capability-maturity.md` until a YAML derivative exists. |
| DataCatalog/Lineage runtime honesty | `DATA-P1-01`, `FEAT-P1-01` | DataCatalog runtime marker plus maturity manifest. |
| SQL/noqa budget | `DATA-P2-02`, `FEAT-P2-02`; `PLAT-P1-01` resolved by `SQLiteClient.count()` identifier/WHERE validation | `scripts/architecture/check_architecture_smells.py` plus per-helper allowlist. |
| Consumer-owned data/research ports | `DATA-P1-03`, `APP-P1-04`, `ANALYSIS-P1-01` | Import smell check for data provider and analysis concrete service imports. |
| Apps maturity-aware route/help text | `APPS-P1-02` | Route/model/help text scanner against maturity manifest. |
| Golden E2E proof lane | `APPS-P1-01` | CI-required synthetic fixture lane separate from optional TDX/Tushare tests. |
| Reserved namespace source of truth | `ANALYSIS-P2-01` | Maturity/public API manifest instead of hard-coded script-only list. |

## 命名消歧表（B3 产出）

> 跨包同名类型的语义区分与归属定义。

### PositionReader — 3 个定义（已消歧）

| 包 | 类型 | 建议消歧名 | 角色 |
|---|---|---|---|
| `ditto_portfolio.positions` | `PositionReader` (Protocol) | 保持不变（portfolio 是 Position 领域所有者） | 组合持仓快照读取：`get_position(portfolio_id, instrument_id, snapshot_date)` |
| `ditto_application.processes.execution.ports` | `PositionReader` (Protocol) | `PositionReadPort` | 执行流程端口：`get_current_positions(strategy_id) -> dict[int, float]` |
| `ditto_execution.storage.sqlite.trade.positions` | `PositionReader` (concrete) | `TradePositionReader` | SQLite 实际持仓读取：`get_latest(strategy_id, instrument_id)` |

**消歧策略**：application 和 execution 的 `PositionReader` 应重命名以消除歧义。portfolio 的 `PositionReader` 作为领域所有者保持不变。

### TargetPortfolio — 已通过 B3.1 消解

| 包 | 状态 | 说明 |
|---|---|---|
| `ditto_portfolio.target_portfolios` | **已删除**（B3.1） | 投机性持久化 DTO，零生产消费者 |
| `ditto_strategy.alpha.models` | **保留** | 30+ 跨包消费者，等同 LEAN `PortfolioTarget` |
| `ditto_execution.targets.TargetPortfolioLike` | **保留** | 消费端定义的 Protocol，正确实践 |

未来 portfolio 需要持久化层时，应使用 `TargetWeightRecord` + `TargetWeightStore` 命名。

### Signal — 语义区分（无需重命名）

| 类型 | 包 | 角色 |
|---|---|---|
| `Signal` | `ditto_strategy.models` | 领域信号模型（type/strength/confidence） |
| `SignalRecord` | `ditto_strategy.signals.models` | 持久化信号 DTO（strategy_id/run_id/score） |
| `SignalSnapshot` | `ditto_strategy.alpha.models` | 管线输出（`dict[InstrumentId, float]`） |

三个类型无名称冲突，但语义重叠。消费者应按职责选用：领域建模用 `Signal`、存储用 `SignalRecord`、管线传递用 `SignalSnapshot`。

## Reopen Rules

Reopen this backlog before any change that:

- Adds a root package export.
- Adds a new `Dataset` enum member, route family, template family, broker/gateway, or analysis namespace.
- Adds a SQL `S608` suppression or string-built SQL helper.
- Adds application or apps imports of concrete capability/data/research services outside an existing owner/reason allowance.
- Claims paper/live/global-market capability readiness in public docs, API text, or CLI help.
