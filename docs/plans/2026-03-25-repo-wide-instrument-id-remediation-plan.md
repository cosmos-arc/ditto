# Repo-Wide Instrument ID Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在全仓范围内彻底收口 `instrument_id` 语义，使内部运行时与数据访问统一使用 canonical `InstrumentId(int)`，外部输入边界显式区分 `instrument_id` / `standard_ticker` / `ticker` / `source_ticker`，消除“同名不同义”的接口与实现。

**Architecture:** 保持现有四层标识符体系不变，但明确边界：Core/DataHub 内部查询主键一律为 `InstrumentId`；Source/ingestion 边界继续使用 `source_ticker`；Port 查询边界允许多种用户输入，但必须先显式解析为 canonical `InstrumentId` 再进入 DataHub 查询服务。审计控制面不再用“字符串 `instrument_id`”混合承载真实 ID 与组合级 sentinel。

**Tech Stack:** Python 3.13, FastAPI, Typer, Polars, SQLite, basedpyright, pytest, import-linter

---

## Current Review Summary

### 已收口

- Strategy / Backtest / Execution / Rules 主链已经切换到 `ditto_kernel.identity.InstrumentId`
- 回测 benchmark、display_map、portfolio-wide risk token 三个已知高优先级问题已修复
- 全量门禁当前通过：`pixi run -e dev check`

### 全仓仍残留的语义分叉

1. `capital` / `fundamental` 查询链路仍把 `instrument_id` 定义为 `str`
2. Port query API / CLI / response model 中 `instrument_id` 仍承载字符串语义
3. DataHub audit DTO 仍以 `str instrument_id` 承载真实 ID 与组合级 `"*"` token
4. 底层表 schema 实际已经使用 `INTEGER instrument_id`，说明上层字符串语义主要是接口/命名遗留，不是存储约束

### 参考实现（应复用，不要另起一套）

- `apps/port/src/ditto_port/api/routes/source.py`
- `packages/datahub/src/ditto_datahub/services/metadata_service.py`
- `packages/datahub/src/ditto_datahub/services/metadata/instrument.py`

这些文件已经定义了比较清晰的“多标识符输入 -> 规范解析”模式，应作为全仓 query 边界整改的唯一模板。

## North Star Contract

### 内部契约

- Core: 一律使用 `InstrumentId`
- DataHub service / reader / writer: 一律使用 `InstrumentId` 或 `int`
- 持久化表中的 `instrument_id` 一律表示 canonical 内部主键

### 外部边界契约

- `instrument_id`: 仅表示 canonical 内部 ID，类型为 `int`
- `standard_ticker`: Ditto 标准展示代码，如 `000001.XSHE`
- `ticker`: 裸代码，如 `000001`
- `source_ticker`: 数据源原始代码，如 `000001.SZ`
- 如果接口接受多种输入，必须显式声明这几个字段，而不是把字符串输入继续命名为 `instrument_id`

### 审计契约

- 审计记录中的真实标的主键应是 canonical `InstrumentId`
- 组合级事件应使用显式 `scope` / `kind`，不要再让 `"*"` 和真实 ID 共用同一个“假装叫 instrument_id 的字符串字段”

## Non-Goals

- 不改 ingestion / source 侧以 `source_ticker` 为核心的边界设计
- 不对 archive 文档做大规模内容重写，只做 superseded/备注处理
- 不做 API / job flow 产品化扩展

---

### Task 1: 收口共享标识符解析契约

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/metadata/instrument.py`
- Modify: `packages/datahub/src/ditto_datahub/services/metadata_service.py`
- Create: `packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py`

**目标**

新增统一入口，例如 `resolve_instrument_identifier(...) -> InstrumentId`，支持：

- `instrument_id: int | None`
- `standard_ticker: str | None`
- `ticker: str | None`
- `asset_class`
- `source`
- `asof`

内部复用现有 `resolve_source_ticker()` + `resolve_instrument_id()`；不要在 Port 层重复拼装解析逻辑。

**Implementation Notes**

- `instrument_id` 已给出时直接返回
- `standard_ticker` / `ticker` 先解析成 `source_ticker`
- 再调用现有 `resolve_instrument_id(source_ticker, source, asof)`
- 错误类型沿用现有 `IdentifierNotFoundError` / `AmbiguousTickerError`

**Tests**

- `instrument_id` 直通
- `standard_ticker -> InstrumentId`
- `ticker -> InstrumentId`
- 未提供任何标识符时报错
- 解析后找不到映射时报错

**Run**

`pixi run -e dev pytest packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py --no-cov -q`

**Commit**

`git commit -m "refactor(metadata): add canonical instrument identifier resolver"`

---

### Task 2: 迁移 Capital 查询链路到 canonical InstrumentId

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/capital_service.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/margin/margin_trading_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/pledge/pledge_ratio_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/valuation/valuation_metrics_reader.py`
- Modify: `apps/port/src/ditto_port/api/routes/capital.py`
- Modify: `apps/port/src/ditto_port/cli/commands/query/capital.py`
- Modify: `apps/port/src/ditto_port/models/capital.py`
- Create: `apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py`
- Create: `packages/datahub/tests/unit/services/test_capital_service_identifier_unit.py`

**目标**

把 Capital query 路径从“字符串 `instrument_id`”改成显式多标识符边界：

- `instrument_id: int | None`
- `standard_ticker: str | None`
- `ticker: str | None`

Port 层先解析成 canonical `InstrumentId`，DataHub 内部只接收 `InstrumentId`。

**Implementation Notes**

- Port API / CLI 复用 Task 1 的统一解析入口
- DataHub `CapitalService` 和底层 readers 全部改为 `instrument_id: int`
- Port response model 中 `instrument_id` 改为 `int`
- 如果需要保留可读展示，新增 `standard_ticker` 字段，不要把展示字段混成 `instrument_id`

**Tests**

- API 通过 `instrument_id` 查询成功
- API 通过 `standard_ticker` 查询成功
- API 通过 `ticker` 查询成功
- CLI 三种输入模式都正确
- Service / reader 使用 `int instrument_id`

**Run**

`pixi run -e dev pytest apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py packages/datahub/tests/unit/services/test_capital_service_identifier_unit.py packages/datahub/tests/unit/stores/capital --no-cov -q`

**Commit**

`git commit -m "refactor(capital): unify query path on canonical instrument id"`

---

### Task 3: 迁移 Fundamental 查询链路到 canonical InstrumentId

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/fundamental_service.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/corporate/dividend_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/corporate/corporate_actions_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/forecast/express_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/forecast/forecast_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/financial/balance_sheet_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/financial/cash_flow_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/fundamental/financial/income_statement_reader.py`
- Modify: `apps/port/src/ditto_port/api/routes/fundamental.py`
- Modify: `apps/port/src/ditto_port/cli/commands/query/fundamental.py`
- Modify: `apps/port/src/ditto_port/models/fundamental.py`
- Create: `apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py`
- Create: `packages/datahub/tests/unit/services/test_fundamental_service_identifier_unit.py`

**目标**

按与 Task 2 相同的边界模式，统一 Fundamental query 路径：

- Port 边界接受多标识符输入
- DataHub 内部统一 `InstrumentId`
- response model 中 `instrument_id` 改回真实 canonical int

**Implementation Notes**

- 和 Capital 一样复用 Task 1 的统一解析入口
- 不再允许 `def get_xxx(instrument_id: str, ...)`
- `corporate_actions` 的 range query 同步迁移

**Tests**

- Balance sheet / income statement / cash flow / dividend / forecast / express / corporate actions 全部覆盖
- API / CLI 三种输入模式覆盖
- reader/service 端 `int instrument_id` 类型覆盖

**Run**

`pixi run -e dev pytest apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py packages/datahub/tests/unit/services/test_fundamental_service_identifier_unit.py packages/datahub/tests/unit/stores/fundamental --no-cov -q`

**Commit**

`git commit -m "refactor(fundamental): unify query path on canonical instrument id"`

---

### Task 4: 清理 Audit / Control Plane 的字符串 instrument_id 语义

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/models/strategy_audit.py`
- Modify: `packages/datahub/src/ditto_datahub/services/audit/execution_audit_service.py`
- Modify: `packages/datahub/src/ditto_datahub/scripts/schema.sql`
- Modify: `apps/port/src/ditto_port/services/strategy/backtest_service.py`
- Modify: `packages/datahub/tests/unit/services/test_execution_audit_service_unit.py`
- Modify: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`

**目标**

把审计层从“字符串 `instrument_id` 既表示真实 ID 又表示 `"*"`”改成显式语义模型。推荐目标结构：

- `instrument_id: int | None`
- `instrument_scope: "instrument" | "portfolio"`

**Implementation Notes**

- `PORTFOLIO_WIDE_ID` 不再通过 `"*"` 混入 `instrument_id`
- SQLite schema 新增 `instrument_scope`，`instrument_id` 改为 `INTEGER NULL`
- 查询返回中保留兼容展示字段可选，但内部 DTO 不再用字符串 `instrument_id`
- 若当前运行时不需要兼容旧表，按项目约束可直接 schema 迁移，不保留历史双写

**Tests**

- 风控记录写入真实标的 ID
- 组合级风控记录写入 `instrument_scope="portfolio"` 且 `instrument_id is NULL`
- 盘前决策记录写入 `instrument_scope="instrument"`
- query 结果字段齐全且语义一致

**Run**

`pixi run -e dev pytest packages/datahub/tests/unit/services/test_execution_audit_service_unit.py apps/port/tests/unit/services/strategy/test_backtest_service_unit.py --no-cov -q`

**Commit**

`git commit -m "refactor(audit): make instrument scope explicit in audit records"`

---

### Task 5: 清理 Port 模型命名与文档门禁

**Files:**
- Modify: `apps/port/src/ditto_port/models/capital.py`
- Modify: `apps/port/src/ditto_port/models/fundamental.py`
- Modify: `docs/reviews/2026-03-25-instrument-id-unification-post-audit.md`
- Modify: `docs/plans/2026-03-24-instrument-id-semantics-unification-implementation-plan.md`
- Modify: `docs/plans/2026-03-25-instrument-id-unification-v2-implementation-plan.md`
- Create: `scripts/` 内扫描脚本或对应 lint/test（若现有门禁可承载则直接补测试）

**目标**

- 清理残留的“字符串也叫 `instrument_id`”文档与模型描述
- 为后续回归增加门禁，避免再引入 `def ...(instrument_id: str, ...)` 这类接口

**Implementation Notes**

- archive 文档只加 superseded/历史说明，不做逐段重写
- 新增 repo-level grep test 或 lint guard，至少约束 `packages/datahub/src` 与 `apps/port/src` 中 query/service/api/model 不再出现新的 `instrument_id: str`
- 保留 `source_ticker` 的 ingestion/source 边界用法，不纳入误报

**Tests / Verification**

- grep guard / unit test
- `pixi run -e dev check`

**Commit**

`git commit -m "docs: align repo-wide instrument id terminology"`

---

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5

## Why This Order

- Task 1 先提供统一解析入口，避免 Capital/Fundamental 各自发明 resolver
- Task 2 / Task 3 优先收口“名字错、类型也错、底层表却是 int”的主查询链路
- Task 4 最后处理 audit，因为它涉及 DTO / schema / persistence 语义调整
- Task 5 作为门禁与文档收尾，防止回归

## Acceptance Criteria

- `packages/datahub/src` 和 `apps/port/src` 中不再存在新的 query/service/api/model 级 `instrument_id: str` 用法，audit DTO 除外；audit 完成后也应清零
- Capital / Fundamental API 与 CLI 支持 `instrument_id` / `standard_ticker` / `ticker` 三种输入
- DataHub Capital / Fundamental readers 与 services 统一使用 `int instrument_id`
- Audit 层不再用字符串 `instrument_id` 混合表示真实主键与组合级 sentinel
- `pixi run -e dev check` 通过

## Risks

- Audit schema 调整会影响已有本地 SQLite 数据；需要明确是否允许直接重建
- Port query 接口一旦切换为多标识符边界，需要同步 API 文档与 CLI help
- 若不先加门禁，后续新模块很容易再次引入 `instrument_id: str`

## Notes For Implementer

- 不要触碰 ingestion/source 的 `source_ticker` 主边界设计；那是正确分层，不是待整改对象
- 不要把 “支持多种输入” 理解成 “内部继续保留字符串 instrument_id”
- 不要新增第二套 resolver；统一收敛到 MetadataService
