# Ditto v5 全量重构执行计划与进度跟踪

**创建日期**: 2026-02-08
**最后更新**: 2026-02-08
**当前分支**: `feature/v5-architecture-refactor`
**基线分支**: `main`（`d29fe62`）
**目标文档**: `docs/plans/2026-02-07-ditto-architecture-v5.md`

---

## 1. 目标与验收定义

本次重构采用“无兼容负担”策略，完成定义如下：

1. 代码结构、命名、接口、分层关系与 v5 文档一致。
2. `sid/src_code` 在代码与配置中完成替换为 `instrument_id/source_ticker`（保留门禁测试样例除外）。
3. Port 层仅作为 API 边界，业务路径不直接调用 DataHub Store/Source。
4. 架构约束自动化接入 CI，违反即失败。
5. `pixi run -e dev ci` 全绿，并且文档与实现一致。

当前强制门禁命令：

```bash
pixi run -e dev lint
pixi run -e dev fmt-check
pixi run -e dev type --all
pixi run -e dev test --unit
pixi run -e dev test --integration
pixi run -e dev arch-check
pixi run -e dev ci
```

---

## 2. 执行原则（已锁定）

1. 不做兼容层，不保留旧接口，不做历史迁移。
2. 文档与实现冲突时，以 v5 文档为准。
3. Port `registry` 可导入 Store/Source 做 DI 装配；业务路径禁止直接调用。
4. 所有架构约束必须可自动检测，禁止“仅靠约定”。

---

## 3. 完整执行计划（WBS）与当前状态

状态图例：`✅ 已完成` | `🟡 进行中` | `⏳ 未开始`

### 阶段 A：架构与命名一次性切换

| 编号 | 任务 | 产物 | 状态 |
|---|---|---|---|
| A1 | 按 v5 建立差异清单并分域拆解 | Market/Metadata/Fundamental/Capital/Macro/Feature/Factor 改造路径 | ✅ |
| A2 | 统一查询契约（Query/Result）优先于实现改造 | 统一服务入口模式 | ✅ |
| A3 | 全仓命名迁移：`sid/src_code` → `instrument_id/source_ticker` | 代码、Schema、SQL、DQ 配置、测试同步替换 | ✅ |
| A4 | DataHub 入口与域服务重建，去除旧漂移模式 | `hub.py`、域服务聚合、依赖注入修复 | ✅ |
| A5 | Source-Adapter-Service 链路标准化 | SourceSchema 输出 + Adapter 映射 + Service 收口 | ✅ |
| A6 | DI 装配稳定化（运行时类型/注入问题） | `apps/port/registry` 与运行时注入修复 | ✅ |

### 阶段 B：v5 能力补齐与 Port 收敛

| 编号 | 任务 | 产物 | 状态 |
|---|---|---|---|
| B1 | 数据集矩阵补齐（registry/enum/任务流/入口） | ingestion registry 与任务映射覆盖 v5 目标矩阵 | ✅ |
| B2 | Port 轻量 API 分层收敛（router/DTO/service） | DTO 边界明确，错误映射标准化 | ✅ |
| B3 | 清理 Port 业务路径直连 Store/Source | 业务路径统一走 DataHub Service | ✅ |
| B4 | README/设计文档同步与过时叙述清理 | 文档与实现对齐 | ✅ |

### 阶段 C：架构约束收口（最终门禁）

| 编号 | 任务 | 产物 | 状态 |
|---|---|---|---|
| C1 | 规则文档更新（架构边界、命名规范、Port 特例） | `/.claude/CLAUDE.md`、`/.claude/rules/architecture.md`、`/.claude/rules/core.md` | ✅ |
| C2 | 自动化架构检查脚本增强 | `scripts/check_architecture.py` | ✅ |
| C3 | 架构测试补齐 | `apps/port/tests/unit/test_architecture_check_unit.py` | ✅ |
| C4 | CI 接入与门禁链路打通 | `pixi.toml` 中 `arch-check` 接入 `check/ci` | ✅ |
| C5 | Port 特例规则自动化 | 非 registry 禁止导入；registry 禁止直接业务调用 | ✅ |

### 阶段 D：终验与发布准备

| 编号 | 任务 | 产物 | 状态 |
|---|---|---|---|
| D1 | 全量回归验证 | `pixi run -e dev ci` 通过 | ✅ |
| D2 | 进度与执行计划文档化 | 本文档 | ✅ |
| D3 | 剩余差距收口（最终清零） | 阶段 A/B 的 `🟡` 项全部转 `✅` | ✅ |

---

## 4. 当前进度快照（截至 2026-02-08）

### 4.1 分支与提交

`main..feature/v5-architecture-refactor` 关键提交：

1. `eda06be` docs(plan): 更新 instrument 表命名收口与门禁快照
2. `d3e262d` refactor(metadata): 收口 instrument 表命名并清理 legacy 语义
3. `18a9f0b` docs(plan): 同步 metadata 命名收口与门禁进度
4. `8ab106d` refactor(metadata): 统一 instrument 查询命名并增强门禁
5. `20d49e0` docs(readme): 收口核心示例到 v5 查询接口
6. `9260d15` test(architecture): 增强 legacy 别名门禁并收口 DataHub 文档
7. `86730de` refactor(architecture): 收口 v5 架构约束并修复关键链路
8. `46094e3` docs(plan): 更新 v5 重构进度与门禁快照
9. `81f4343` refactor(ingestion): 统一 write 入口并补齐 stock_status 矩阵
10. `57fc6d3` feat(ingestion): 补齐 fundamental/capital 数据集矩阵与写入链路
11. `12e3134` feat(ingestion): 补齐 macro 指标摄取闭环并统一宏观服务契约
12. `5c8f271` docs(readme): 同步 macro 摄取能力与重构进度
13. `03a5e74` refactor(datahub): 收口 DataHub 别名并统一 Port 与域服务查询契约

统计（`main..HEAD`）：

- 变更文件：`200`
- 代码变更：`+6812 / -3541`

### 4.2 门禁结果

最近一次 `pixi run -e dev ci`：

- `2243 passed, 20 skipped`
- coverage `92.63%`
- `Architecture check passed`

---

## 5. 已完成项（可验收）

1. `instrument_id/source_ticker` 语义在代码与配置层面已落地，并加上自动扫描门禁（`ARCH500/ARCH510`）。
2. Port 架构边界门禁完成：非 registry 禁止直接依赖 Store/Source/Runtime；registry 仅允许 DI 装配。
3. `CapitalService`、`FundamentalService` 已切换为统一 `query()/write()` 契约，并补齐契约单测。
4. CI 链路中 `arch-check` 已成为强制依赖（`check` 与 `ci` 均包含）。
5. 核心规则文档已同步 v5 约束，避免“代码做了、规范没收口”。
6. `MarketService`、`MetadataService` 已补齐统一 `query()/write()` 主入口，DataHub 与 DQ 主链路已迁移到统一契约调用。
7. `capital_ingestion`、`fundamental_ingestion` 写入链路已从直连 Store 切换为 Service `write()`，并完成对应测试。
8. Port 摄取写入入口已统一为 `market.write` / `metadata.write`，`write_bars/write_adj_factor` 兼容入口已从 `DataHub` 与 `MarketService` 删除。
9. `stock_status` 已纳入 T1 数据集矩阵（enum/registry/coordinator/source-protocol/market-write），并通过单测回归。
10. Fundamental/Capital 数据集已纳入 Port ingestion 矩阵：`balance_sheet` / `income_statement` / `cash_flow` / `dividend` / `valuation_metrics` / `margin_trading` / `pledge_ratio`（含 enum/registry/protocol/coordinator/writer/task 回归）。
11. `DataSource` 抽象与 `TushareSource` 委托已补齐跨域抓取入口，`CapitalTushareAdapter` 的财报抓取签名已支持全市场模式（`ts_code` 可选）。
12. `cachebox` TTL 在并发 CI 环境下的抖动导致的偶发红灯已通过测试稳态策略收口，不影响主链路门禁通过。
13. `macro_indicators` 已纳入 Port ingestion 矩阵：`Dataset enum / DATASET_REGISTRY / Coordinator fetch / DataWriter write / DataSource Protocol / TushareSource` 全链路完成；`MacroService` 已补齐统一 `query()/write()` 契约并通过回归。
14. DataHub/Port README 已完成与 Macro 迁移相关的关键信息同步（macro 存储结构、`query()/write()` 契约、Port 摄取矩阵）。
15. DataHub Facade 已移除 `securities/calendar/universe/index/ingestion_log` 兼容别名，Port 业务代码统一改为 `hub.metadata` 与 `hub.ingestion_log_store` 正式入口。
16. Features/Factors/Macro 服务契约已统一为 `query()`（去除 `get_indicators()/get_factors()` 旧命名），相关单测与调用示例同步更新。
17. 架构门禁新增 `ARCH520`：禁止 DataHub/Port 源码使用 `hub.calendar/hub.universe/hub.index/hub.securities/hub.ingestion_log` legacy 别名。
18. DataHub 单测新增 Facade 暴露约束验证：仅允许 `metadata/market/ingestion_log_store` 等 v5 正式入口，禁止 legacy alias 回归。
19. DataHub README 示例继续去兼容收口：统一展示容器注入 DataHub/QualityEngine 的用法，移除过时 `hub = DataHub()` 与 `hub.dq_checker` 路径。
20. Core/DataHub README 示例进一步收口：移除 `hub.bars.*` / `sids` 旧写法，统一为 `MarketBarsQuery + hub.market.query(...)`。
21. Metadata 命名语义进一步收口：`MetadataQuery.dataset` 统一为 `instrument/industry`，便捷 API 统一为 `get_instruments`，移除 `securities/industries/get_securities` 旧命名。
22. 架构门禁新增 `ARCH530~ARCH533`：禁止 `dataset='securities'`、`dataset='industries'`、`SecuritiesQuerySpec`、`get_securities()` 回归。
23. Metadata 注册/解析接口进一步统一为 instrument 语义：`register_instrument`、`register_instruments_batch`、`resolve_or_create_instruments_batch`，Port ingestion 与测试调用已同步。
24. 底层 SQLite 命名与约束完成收口：`security/security_mapping` 全量迁移为 `instrument/instrument_mapping`（schema、store、sql engine、dq 配置、测试全部同步）。
25. 架构门禁新增 `ARCH540~ARCH541`：禁止旧表名/语义 `security_mapping`、`security` 回归。
26. 本轮全量门禁已通过：`pixi run -e dev ci` => `2243 passed, 20 skipped`, coverage `92.63%`。

---

## 6. 剩余差距与后续执行顺序

### 6.1 本计划范围内

当前执行清单已全部收口（A/B/C/D 全部 `✅`）。

### 6.2 全量架构落地（计划外）待收口项

以下差距不属于本次 `datahub-v2-refactoring` 计划的原始范围，但属于 v5 全量架构目标的剩余工作：

1. Core 目录结构仍为骨架状态：`engine/strategy/portfolio` 仅保留 `__init__.py` 与 README，尚未落地 `backtest/factor/risk/regime` 与策略/组合实现模块。
2. Port API 分层未按 v5 目录示例落地：当前无 `apps/port/src/ditto_port/api/routes`，路由仍集中在 `main.py`。
3. DataHub 模型层尚未拆分为 `models/market|trading|portfolio|strategy` 子结构，当前仍是 `models/common.py|ingestion.py|storage.py`。
4. `futures`、`corporate_actions` 在 DataHub 域服务存在实现，但尚未进入统一 `Dataset enum + Port ingestion coordinator/data_writer` 主链路。
5. 摄取质量与告警链路仍有待办（告警发送、quarantine 落库等）注释项，未形成闭环实现。

### 6.3 建议执行顺序

1. 先完成 Core/Port/DataHub 的目录与边界收口（结构性改造）。
2. 再打通 `futures/corporate_actions` 到统一 ingestion 主链路（功能闭环）。
3. 最后收口 DQ 告警与 quarantine（运维闭环），并补齐对应架构门禁。

---

## 7. 风险与注意事项

1. 本地存在与任务无关修改：`.factory/settings.json`、`.tmp/`（提交时需持续排除）。
2. `ci` 中 Prefect 停服日志有已知输出噪声（`ValueError: I/O operation on closed file`），当前不影响门禁结果。

---

## 8. 下一次更新规则

每完成一个可独立提交的批次，更新本文件以下内容：

1. 章节 3 的任务状态（`🟡`→`✅`）。
2. 章节 4 的提交清单与门禁结果。
3. 章节 6 的剩余差距（实时收敛为零）。
