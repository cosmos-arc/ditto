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
| A2 | 统一查询契约（Query/Result）优先于实现改造 | 统一服务入口模式 | 🟡 |
| A3 | 全仓命名迁移：`sid/src_code` → `instrument_id/source_ticker` | 代码、Schema、SQL、DQ 配置、测试同步替换 | ✅ |
| A4 | DataHub 入口与域服务重建，去除旧漂移模式 | `hub.py`、域服务聚合、依赖注入修复 | 🟡 |
| A5 | Source-Adapter-Service 链路标准化 | SourceSchema 输出 + Adapter 映射 + Service 收口 | 🟡 |
| A6 | DI 装配稳定化（运行时类型/注入问题） | `apps/port/registry` 与运行时注入修复 | ✅ |

### 阶段 B：v5 能力补齐与 Port 收敛

| 编号 | 任务 | 产物 | 状态 |
|---|---|---|---|
| B1 | 数据集矩阵补齐（registry/enum/任务流/入口） | ingestion registry 与任务映射覆盖 v5 目标矩阵 | 🟡 |
| B2 | Port 轻量 API 分层收敛（router/DTO/service） | DTO 边界明确，错误映射标准化 | 🟡 |
| B3 | 清理 Port 业务路径直连 Store/Source | 业务路径统一走 DataHub Service | ✅ |
| B4 | README/设计文档同步与过时叙述清理 | 文档与实现对齐 | 🟡 |

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
| D3 | 剩余差距收口（最终清零） | 阶段 A/B 的 `🟡` 项全部转 `✅` | 🟡 |

---

## 4. 当前进度快照（截至 2026-02-08）

### 4.1 分支与提交

`main..feature/v5-architecture-refactor` 关键提交：

1. `86730de` refactor(architecture): 收口v5架构约束并修复关键链路
2. `538c222` refactor(datahub): 统一source_ticker与instrument_id摄取契约
3. `6a42de1` refactor(datahub): 按v5架构收口instrument_id/source_ticker标识体系
4. `6ac323a` refactor(runtime): 去除sid字段兼容投影并统一instrument_id命名
5. `7abaa6d` refactor(datahub): 全量收口 sid 命名到 instrument_id 语义
6. `ebc5726` chore(architecture): 强化 v5 门禁并收口术语文档
7. `921da53` refactor(datahub): 统一 capital/fundamental Service 的 Query 契约

统计（`main..HEAD`）：

- 变更文件：`156`
- 代码变更：`+3899 / -2539`

### 4.2 门禁结果

最近一次 `pixi run -e dev ci`：

- `2201 passed, 20 skipped`
- coverage `92.71%`
- `Architecture check passed`

---

## 5. 已完成项（可验收）

1. `instrument_id/source_ticker` 语义在代码与配置层面已落地，并加上自动扫描门禁（`ARCH500/ARCH510`）。
2. Port 架构边界门禁完成：非 registry 禁止直接依赖 Store/Source/Runtime；registry 仅允许 DI 装配。
3. `CapitalService`、`FundamentalService` 已切换为统一 `query()/write()` 契约，并补齐契约单测。
4. CI 链路中 `arch-check` 已成为强制依赖（`check` 与 `ci` 均包含）。
5. 核心规则文档已同步 v5 约束，避免“代码做了、规范没收口”。

---

## 6. 剩余差距与后续执行顺序

### P0（下一优先级，必须完成）

1. **Metadata/Market 服务契约统一收口**
当前 `MetadataService`、`MarketService` 仍以多方法签名为主，尚未完全统一为 `Query/Result` 模式。
输出：统一 Query/Result 类型 + `query()/write()` 主入口 + 调用方迁移。

2. **ingestion 写入路径统一走 Service**
`capital_ingestion.py`、`fundamental_ingestion.py` 仍有 `_capital_store/_fundamental_store.write_*` 直接调用。
输出：改为 Service 写入接口，保持链路一致性与可审计性。

### P1（随后完成）

1. **Port 数据集矩阵补齐**
`apps/port/src/ditto_port/models/config.py` 当前 registry 主要覆盖 T0/T1 核心集，需对齐 v5 数据集矩阵。

2. **文档清理最终收口**
继续修订 DataHub/Port 相关 README 中历史叙述，确保与 v5 最终实现一致。

---

## 7. 风险与注意事项

1. 本地存在与任务无关修改：`.factory/settings.json`（提交时需持续排除）。
2. `ci` 中 Prefect 停服日志有已知输出噪声（`ValueError: I/O operation on closed file`），当前不影响门禁结果。

---

## 8. 下一次更新规则

每完成一个可独立提交的批次，更新本文件以下内容：

1. 章节 3 的任务状态（`🟡`→`✅`）。
2. 章节 4 的提交清单与门禁结果。
3. 章节 6 的剩余差距（实时收敛为零）。
