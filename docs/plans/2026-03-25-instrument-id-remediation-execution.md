# Instrument ID 全仓收口 — 执行计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## 概述

- **Sprint**: phase4 | **Phase**: instrument-id-remediation
- **创建**: 2026-03-25
- **前置计划**: [repo-wide-instrument-id-remediation-plan](2026-03-25-repo-wide-instrument-id-remediation-plan.md)
- **审计报告**: [instrument-id-unification-post-audit](../reviews/2026-03-25-instrument-id-unification-post-audit.md)
- **状态**: 未开始

## 背景

Core/DataHub/Port 策略/回测主链已完成 `InstrumentId` 统一（v1/v2 计划 Phase 0-4 全部 COMPLETED），但 post-audit 发现 3 个 bug（#1 P0 benchmark 二次 resolve、#2 P0 PORTFOLIO_WIDE_ID 映射断裂、#3 P1 factory display_map 丢失），同时 Capital/Fundamental/Audit 查询链路仍残留 `instrument_id: str` 语义。

本计划在 brainstorming 分析基础上，整合修复与收口，按依赖顺序执行。

## 技术方案

### 关键决策

| 决策 | 结论 | 理由 |
|------|------|------|
| P0 bug 处理顺序 | 先修 P0 再执行收口 | #1 阻塞验收，基线不健康则后续改动不可信 |
| API/CLI 多标识符 UX | 三参数显式声明 | `--instrument-id` / `--ticker` / `--standard-ticker`，类型安全无歧义 |
| Audit scope 拆分深度 | 全链路同步改 | Core + DataHub + Port 三层同步消灭哨兵值，语义最干净 |
| scope 类型 | `Literal["instrument", "portfolio"]` | 仅两个值，Literal 足够，无需 Enum |
| 统一解析入口归属 | 逻辑在 `InstrumentService`，入口在 `MetadataService` | MetadataService 是 Port 的统一 facade |
| 多参数互斥策略 | 优先级 `instrument_id > standard_ticker > ticker`，多余静默忽略 | 简单直觉，与现有 source.py 模式一致 |

### North Star Contract

**内部契约**：Core / DataHub service / reader / writer 一律使用 `InstrumentId` 或 `int`

**外部边界契约**：
- `instrument_id: int` — canonical 内部 ID
- `standard_ticker: str` — Ditto 标准展示代码，如 `000001.XSHE`
- `ticker: str` — 裸代码，如 `000001`

**审计契约**：
- 真实标的主键：`instrument_id: InstrumentId`
- 组合级事件：`instrument_id: None` + `scope: "portfolio"`

### Non-Goals

- 不改 ingestion/source 侧以 `source_ticker` 为核心的边界设计
- 不对 archive 文档做大规模内容重写，只做 superseded/备注
- 不做 API / job flow 产品化扩展

---

## 任务清单

### Task 0: 修复 post-audit P0/P1 bug `[S]`

**目标**：修复 3 个已知 bug，建立健康基线

**依赖**：无

**文件**：
- Modify: `apps/port/src/ditto_port/services/strategy/market_data_feed.py`
- Modify: `apps/port/src/ditto_port/services/strategy/factory.py`
- Modify: `apps/port/tests/unit/services/strategy/test_market_service_data_feed_unit.py`
- Modify: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`
- Modify: `apps/port/tests/unit/services/strategy/test_strategy_service_factory_unit.py`

**子任务**：

- [ ] 0.1 修复 benchmark 二次 resolve
  - `market_data_feed.py` `_load_benchmark_close_map()`: 删除 `str(self._config.benchmark_id)` + `resolve_instrument_id()` 调用，直接使用 `int(self._config.benchmark_id)`
  - 验收: benchmark 路径走 canonical ID 直通，不再调用 resolver

- [ ] 0.2 修复 factory display_map 透传
  - `factory.py` `_build_backtest_options()`: 补充 `display_map` 字段传递
  - `factory.py` `build_backtest_service_from_catalog()`: 从 `runtime.data_feed.display_map` 接入
  - 验收: artifact 输出中包含 `instrument_symbol` 展示字段

- [ ] 0.3 更新测试 fixture
  - 3 个测试文件中 benchmark fixture 从字符串 `"000300.SH"` 改为 `InstrumentId`
  - 补 canonical benchmark 路径回归测试
  - 补 factory + artifact 透传集成测试

**Commit**: `fix(port): resolve post-audit P0/P1 bugs — benchmark resolve + display_map passthrough`

**验收**：
- `pixi run -e dev pytest apps/port/tests/unit/services/strategy/ -v` 通过
- `pixi run -e dev check` 通过

---

### Task 1: 收口共享标识符解析契约 `[M]`

**目标**：新增统一解析入口 `resolve_instrument_identifier()`，支持 `instrument_id` / `standard_ticker` / `ticker` 三种输入

**依赖**：Task 0

**文件**：
- Modify: `packages/datahub/src/ditto_datahub/services/metadata/instrument.py`
- Modify: `packages/datahub/src/ditto_datahub/services/metadata_service.py`
- Create: `packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py`

**实现要点**：

1. `InstrumentService` 新增方法：
   ```python
   def resolve_standard_ticker(self, standard_ticker: str, source: str) -> str | None:
       """standard_ticker -> source_ticker（利用 exchange 映射）"""

   def resolve_ticker(self, ticker: str, source: str) -> str | None:
       """ticker -> source_ticker"""
   ```

2. `MetadataService` 新增统一入口：
   ```python
   def resolve_instrument_identifier(
       self,
       *,
       instrument_id: int | None = None,
       standard_ticker: str | None = None,
       ticker: str | None = None,
       asset_class: str | None = None,
       source: str,
       asof: str | None = None,
   ) -> InstrumentId:
       """统一解析入口。优先级: instrument_id > standard_ticker > ticker"""
   ```

3. 错误处理：
   - 全部未提供 → `NoIdentifierProvidedError(ValueError 子类)`
   - `instrument_id` 已给 → 直接返回 `InstrumentId(instrument_id)`
   - `standard_ticker`/`ticker` → 先解析成 `source_ticker`，再调用 `resolve_instrument_id()`
   - 找不到映射 → 复用现有 `IdentifierNotFoundError` / `AmbiguousTickerError`

**测试**：
- `instrument_id` 直通返回
- `standard_ticker` → `InstrumentId`
- `ticker` → `InstrumentId`
- 优先级：同时传 `instrument_id` + `ticker` 时 `instrument_id` 优先
- 未提供任何标识符时报 `NoIdentifierProvidedError`
- 解析后找不到映射时报 `IdentifierNotFoundError`

**Commit**: `refactor(metadata): add canonical instrument identifier resolver`

**验收**：
- `pixi run -e dev pytest packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py -v` 通过
- `pixi run -e dev check` 通过

---

### Task 2: 迁移 Capital 查询链路 `[M]`

**目标**：Capital query 路径从 `instrument_id: str` 改为显式多标识符边界

**依赖**：Task 1

**文件**：
- Modify: `packages/datahub/src/ditto_datahub/services/capital_service.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/margin/margin_trading_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/pledge/pledge_ratio_reader.py`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/valuation/valuation_metrics_reader.py`
- Modify: `apps/port/src/ditto_port/api/routes/capital.py`
- Modify: `apps/port/src/ditto_port/cli/commands/query/capital.py`
- Modify: `apps/port/src/ditto_port/models/capital.py`
- Create: `apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py`
- Create: `packages/datahub/tests/unit/services/test_capital_service_identifier_unit.py`

**实现要点**：

1. **Port API**：三参数 Query params，至少提供一个
   ```python
   @router.get("/capital/margin-trading")
   def get_margin_trading(
       instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
       ticker: str | None = Query(None, description="裸代码，如 000001"),
       standard_ticker: str | None = Query(None, description="标准代码，如 000001.XSHE"),
       ...
   ):
   ```

2. **Port CLI**：三参数 typer.Option
   ```python
   instrument_id: int | None = typer.Option(None, "--instrument-id", "-i"),
   ticker: str | None = typer.Option(None, "--ticker", "-t"),
   standard_ticker: str | None = typer.Option(None, "--standard-ticker", "-s"),
   ```

3. **Port response model**：
   - `instrument_id: str` → `instrument_id: int`
   - `from_row()` 中 `instrument_id=str(row["instrument_id"])` → `instrument_id=int(row["instrument_id"])`
   - 如需可读展示，新增 `standard_ticker: str | None = None` 字段

4. **DataHub service + reader**：`instrument_id: str` → `instrument_id: int`

5. **Port → DataHub 调用链**：API/CLI 先调 Task 1 的 `resolve_instrument_identifier()` 解析为 `InstrumentId`，再传给 DataHub service

**测试**：
- API 通过 `instrument_id` 查询成功
- API 通过 `standard_ticker` 查询成功
- API 通过 `ticker` 查询成功
- API 三个都不传 → 422 错误
- CLI 三种输入模式正确
- Service/reader 使用 `int instrument_id`
- Response model `instrument_id` 为 `int` 类型

**Commit**: `refactor(capital): unify query path on canonical instrument id`

**验收**：
- `pixi run -e dev pytest apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py packages/datahub/tests/unit/services/test_capital_service_identifier_unit.py packages/datahub/tests/unit/stores/capital -v` 通过
- `pixi run -e dev check` 通过

---

### Task 3: 迁移 Fundamental 查询链路 `[L]`

**目标**：按 Task 2 相同的边界模式，统一 Fundamental query 路径

**依赖**：Task 1

**文件**：
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

**实现要点**：

与 Task 2 完全相同的模式：
1. Port API/CLI 三参数显式声明
2. Port response model `instrument_id: str` → `int`，`from_row()` 清理 `str()` 强制转换
3. DataHub service 7 个方法 + reader 签名 `instrument_id: str` → `int`
4. Port 层复用 Task 1 统一解析入口

**测试**：
- Balance sheet / income statement / cash flow / dividend / forecast / express / corporate actions 全部覆盖
- API / CLI 三种输入模式覆盖
- Service/reader `int instrument_id` 类型覆盖

**Commit**: `refactor(fundamental): unify query path on canonical instrument id`

**验收**：
- `pixi run -e dev pytest apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py packages/datahub/tests/unit/services/test_fundamental_service_identifier_unit.py packages/datahub/tests/unit/stores/fundamental -v` 通过
- `pixi run -e dev check` 通过

---

### Task 4: Audit 层 scope 拆分 — 全链路同步改 `[L]`

**目标**：消灭 `PORTFOLIO_WIDE_ID = InstrumentId(0)` 哨兵值，全链路改为 `instrument_id: InstrumentId | None` + `scope: Literal["instrument", "portfolio"]`

**依赖**：Task 0（#2 修复基线），可 Task 2/3 并行

**文件**：
- Modify: `packages/core/src/ditto_core/backtest/risk/post_trade.py` — 删除 `PORTFOLIO_WIDE_ID`
- Modify: `packages/core/src/ditto_core/backtest/audit/records.py` — `RiskScanRecord` / `PreTradeDecisionRecord` 增加 scope
- Modify: `packages/datahub/src/ditto_datahub/models/strategy_audit.py` — DTO 增加 scope，`instrument_id` 改为 `int | None`
- Modify: `packages/datahub/src/ditto_datahub/services/audit/execution_audit_service.py` — SQL schema + 读写逻辑适配
- Modify: `packages/datahub/src/ditto_datahub/scripts/schema.sql` — 审计表增加 `instrument_scope` 列
- Modify: `apps/port/src/ditto_port/services/strategy/backtest_service.py` — 持久化适配
- Modify: `packages/core/tests/unit/backtest/test_post_trade_unit.py`
- Modify: `packages/core/tests/unit/backtest/test_audit_collector_unit.py`
- Modify: `packages/datahub/tests/unit/services/test_execution_audit_service_unit.py`
- Modify: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`

**实现要点**：

1. **Core 层**（先改）：
   ```python
   # post_trade.py — 删除哨兵值
   # PORTFOLIO_WIDE_ID = InstrumentId(0)  ← 删除

   # records.py — 增加显式 scope
   @dataclass(frozen=True)
   class RiskScanRecord:
       instrument_id: InstrumentId | None  # None = portfolio-wide
       scope: Literal["instrument", "portfolio"]
       ...
   ```
   - `PostTradeGuard` 产出 portfolio-wide 事件时：`instrument_id=None, scope="portfolio"`
   - `PostTradeGuard` 产出 instrument 事件时：`instrument_id=X, scope="instrument"`

2. **DataHub DTO 层**：
   ```python
   @dataclass(frozen=True)
   class RiskScanPayload:
       instrument_id: int | None
       scope: Literal["instrument", "portfolio"]
       ...
   ```
   - SQL schema：`instrument_id INTEGER NULL`，新增 `instrument_scope TEXT NOT NULL DEFAULT 'instrument'`

3. **Port 持久化层**：
   - 删除 `str(r.instrument_id)` 转换
   - 按 `scope` 和 `instrument_id` 分别写入对应列
   - 读取时组装为 Core `RiskScanRecord`

4. **`scope` 类型定义位置**：`Literal["instrument", "portfolio"]` 定义在 `ditto_datahub.models.strategy_audit`，Core 通过 `typing` import

**测试**：
- Core: portfolio-wide 风控记录 `instrument_id=None, scope="portfolio"`
- Core: instrument 风控记录 `instrument_id=X, scope="instrument"`
- DataHub: DTO 序列化/反序列化正确
- Port: 持久化写入/读取 scope 正确
- Port: 回测集成测试验证 audit 链路完整

**Commit**: `refactor(audit): make instrument scope explicit — eliminate PORTFOLIO_WIDE_ID sentinel`

**验收**：
- `pixi run -e dev pytest packages/core/tests/unit/backtest/ packages/datahub/tests/unit/services/test_execution_audit_service_unit.py apps/port/tests/unit/services/strategy/test_backtest_service_unit.py -v` 通过
- `pixi run -e dev pytest packages/core/tests/integration/backtest/test_risk_integration.py -v` 通过
- `pixi run -e dev check` 通过
- grep 确认 Core 层无 `PORTFOLIO_WIDE_ID` 残留

---

### Task 5: 清理模型命名 + 增加门禁 `[M]`

**目标**：清理残留文档/模型描述，增加 grep guard 防止 `instrument_id: str` 回归

**依赖**：Task 2, Task 3, Task 4

**文件**：
- Modify: `docs/plans/2026-03-24-instrument-id-semantics-unification-implementation-plan.md` — 加 superseded 备注
- Modify: `docs/plans/2026-03-25-instrument-id-unification-v2-implementation-plan.md` — 加 superseded 备注
- Modify: `docs/plans/2026-03-25-repo-wide-instrument-id-remediation-plan.md` — 加 superseded 备注
- Modify: `packages/core/src/ditto_core/strategy/pipeline.py` — `DecisionFrame` 文档中 `instrument_id: str` 改为 `InstrumentId`
- Create: `packages/datahub/tests/unit/test_instrument_id_type_guard.py` — grep guard 测试

**实现要点**：

1. **文档清理**：archive 文档只加 superseded/历史说明，不做逐段重写

2. **Grep guard 测试**：
   ```python
   """Guard: service/api/model 层不应出现 instrument_id: str"""
   import subprocess

   EXCLUDED_PATTERNS = ["source_ticker", "# type: ignore", "TYPE_CHECKING"]
   SCANNED_DIRS = [
       "packages/datahub/src/ditto_datahub/services/",
       "packages/datahub/src/ditto_datahub/models/",
       "apps/port/src/ditto_port/services/",
       "apps/port/src/ditto_port/api/",
       "apps/port/src/ditto_port/models/",
   ]

   def test_no_str_instrument_id_in_public_interfaces():
       for dir_path in SCANNED_DIRS:
           result = subprocess.run(
               ["grep", "-rn", "instrument_id.*:.*str", dir_path],
               capture_output=True, text=True,
           )
           assert result.returncode != 0, (
               f"Found instrument_id: str in {dir_path}:\n{result.stdout}"
           )
   ```
   - 保留 `source_ticker` 的 ingestion/source 边界用法（排除 `source_ticker` 相关行）
   - `execution_audit_service.py` 的 SQL 层面 `TEXT` 除外（Task 4 已修复 DTO 层面）

**Commit**: `docs: align repo-wide instrument id terminology + add type guard`

**验收**：
- grep guard 测试通过
- `pixi run -e dev check` 通过
- `pixi run -e dev ci` 全绿

---

## 执行顺序与依赖图

```
Task 0 (P0/P1 修复)
   │
   ▼
Task 1 (统一解析入口)
   │
   ├──→ Task 2 (Capital)  ──┐
   │                        │
   └──→ Task 3 (Fundamental)──┤
                            │
Task 0 ──→ Task 4 (Audit) ──┤
                            │
                            ▼
                        Task 5 (门禁 + 文档)
```

Task 2 / Task 3 / Task 4 可并行（Task 2、3 依赖 Task 1，Task 4 仅依赖 Task 0）。

## 验收标准

- [ ] `packages/datahub/src` 和 `apps/port/src` 中不再存在 query/service/api/model 级 `instrument_id: str`
- [ ] Capital / Fundamental API 与 CLI 支持 `instrument_id` / `standard_ticker` / `ticker` 三种输入
- [ ] DataHub Capital / Fundamental readers 与 services 统一使用 `int instrument_id`
- [ ] Audit 层不再用字符串 `instrument_id` 混合表示真实主键与组合级 sentinel
- [ ] Core 层无 `PORTFOLIO_WIDE_ID` 哨兵值残留
- [ ] benchmark 路径不再二次 resolve
- [ ] factory display_map 正确透传到 artifact 输出
- [ ] grep guard 测试通过
- [ ] `pixi run -e dev ci` 全绿

## 风险

| 风险 | 控制 |
|------|------|
| Task 4 全链路 audit 改动波及 Core 层 | 每步 `pixi run -e dev check` + 集成测试 `test_risk_integration.py` |
| Task 2/3 Port API 接口 breaking change | 开发阶段无外部消费者，直接改 |
| SQLite schema 变更影响本地数据 | 开发阶段，直接重建，不保留历史数据 |
| grep guard 误报（source_ticker 边界） | 测试中排除 `source_ticker` 相关模式 |
| Task 1 解析入口多参数歧义（纯数字 ticker vs instrument_id） | 三参数显式声明避免歧义，`instrument_id` 优先级最高 |
