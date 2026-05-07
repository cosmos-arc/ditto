> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# 统一特征/因子引擎 - 缺口清单

> **状态**: 历史参考，不再作为当前事实基础。
> **说明**: 本文档保留 2026-03-06 ~ 2026-03-07 的早期缺口视角，其中 ADR 编号、缺口状态和优先级口径已部分过期。当前执行请优先参考：
> - [README.md](README.md)
> - [main-design.md](main-design.md)
> - [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)

> 本文档记录设计中识别出的缺口、阻塞项和待补充内容。
> 创建日期：2026-03-06
> 最后更新：2026-03-07

---

## 优先级说明

| 级别 | 含义 | 处理时机 |
|------|------|---------|
| **P0** | 阻塞 Phase 0 实施 | 立即处理 |
| **P1** | 影响架构决策 | Phase 0 开始前 |
| **P2** | 改进项，非阻塞 | Phase 1/2 期间 |

---

## P0 - 阻塞项

### P0-1: Entity/Time 语义契约

| 属性 | 值 |
|------|-----|
| **缺口** | 当前 `BaseSpec` 缺少 Entity/Time 语义定义，导致 join、时间回溯、多市场支持无统一契约 |
| **阻塞** | Phase 0 多实体 join、增量边界计算、多市场日历 |
| **需要 ADR** | **是** → ADR-029（新建） |

**当前状态**：

```python
# main-design 6.1 节
class BaseSpec(BaseModel):
    id: str
    expression: str
    universe_policy: str = "tradable"
    # 缺少 Entity/Time 语义
```

**需要定义**：

```python
class EntitySpec(BaseModel):
    """实体语义"""
    join_keys: list[str] = ["instrument_id"]  # 或 ["instrument_id", "exchange"]

class TimeSpec(BaseModel):
    """时间语义"""
    event_time: str            # "trade_date" 或 "announcement_date"
    availability_time: str     # 数据可用时间（可能 = event_time 或有延迟）
    calendar: str              # "cn_trading" / "us_trading" / "hk_trading"
    timezone: str              # "Asia/Shanghai" / "America/New_York"
```

**验收标准**：

- [ ] ADR-029 文档完成
- [ ] `BaseSpec` 包含 `entity: EntitySpec` 和 `time: TimeSpec`
- [ ] 增量计算使用 `calendar` 做精确 lookback
- [ ] 多市场因子可按 `calendar` 分区计算

**参考**: ADR-006 增量计算策略, ADR-026 交易日历接口

---

## P1 - 架构决策项

### P1-1: 执行引擎接口分离

| 属性 | 值 |
|------|-----|
| **缺口** | 原设计 P0-1 建议统一 `ExecutionEngine` 包含 streaming，但会把 streaming 复杂度拉回 MVP |
| **阻塞** | 无（可并行开发） |
| **需要 ADR** | 否（复用 ADR-011） |

**决策**：

Phase 0 显式分离两个独立 Protocol，streaming 保持 Phase 2 独立接口：

```python
class BatchExecutionEngine(Protocol):
    """批量执行引擎"""
    def execute(self, ast: AST, config: RunConfig) -> ExecutionResult: ...

class IncrementalExecutionEngine(Protocol):
    """增量执行引擎"""
    def execute(self, ast: AST, config: RunConfig, watermark: date) -> ExecutionResult: ...

# Phase 2 再定义
class StreamingExecutionEngine(Protocol):
    """流式执行引擎"""
    ...
```

**验收标准**：

- [ ] `BatchExecutionEngine` Protocol 定义完成
- [ ] `IncrementalExecutionEngine` Protocol 定义完成
- [ ] 两个接口独立，无 streaming 依赖

**参考**: ADR-011 流式模式架构

---

### P1-2: 运行时错误处理策略

| 属性 | 值 |
|------|-----|
| **缺口** | ADR-014 定义了编译期错误格式，但运行期错误处理不够明确 |
| **阻塞** | 无（可并行开发） |
| **需要 ADR** | **是** → ADR-025 |

**必须进入 P1 的内容**：

| 场景 | 需要补充 |
|------|---------|
| 错误分类 | 可重试错误 vs 不可重试错误的分类标准 |
| 重试边界 | 哪些操作可重试、重试次数、退避策略 |
| 幂等策略 | 如何保证重试幂等（checkpoint / dedup） |

**P2 可延后的内容**：

- Checkpoint 损坏详细处理流程
- 复杂降级方案

**验收标准**：

- [ ] ADR-025 文档完成
- [ ] 错误分类枚举定义（`RetryableError` / `FatalError`）
- [ ] 重试装饰器实现（`tenacity` 配置）
- [ ] 幂等性保证机制（checkpoint key 设计）

**参考**: ADR-014 编译期错误设计, ADR-012 状态管理架构

---

### P1-3: 交易日历统一接口

| 属性 | 值 |
|------|-----|
| **缺口** | ADR-006 增量计算依赖交易日历做精确 lookback，但多市场日历支持未设计 |
| **阻塞** | 多市场支持 |
| **需要 ADR** | **是** → ADR-026 |

**需要定义**：

```python
class TradingCalendar(Protocol):
    """交易日历协议"""
    @property
    def market(self) -> Literal["cn", "us", "hk"]: ...

    def is_trading_day(self, date: date) -> bool: ...
    def next_trading_day(self, date: date) -> date: ...
    def prev_trading_day(self, date: date) -> date: ...
    def lookback(self, date: date, n: int) -> date: ...
        """回溯 n 个交易日"""
```

**验收标准**：

- [ ] ADR-026 文档完成
- [ ] `TradingCalendar` Protocol 定义
- [ ] CN 市场日历实现（基于现有 `metadata.trading_calendar`）
- [ ] US/HK 日历预留扩展点

**参考**: ADR-006 增量计算策略, Qlib `qlib.data.calendar`

---

### P1-4: Feature/Factor 统一生命周期

| 属性 | 值 |
|------|-----|
| **缺口** | ADR-024 只覆盖 Factor 版本管理，Feature 未纳入同一发布/回滚/默认版本模型 |
| **阻塞** | Feature 版本化发布 |
| **需要 ADR** | **是** → 扩展 ADR-024 |

**需要补充**：

1. **统一生命周期**：
   - `entity_type: Literal["feature", "factor"]` 区分
   - 共享同一套状态机（draft / active / deprecated / archived）

2. **Publication 契约**：
   - publish 操作的原子性保证（artifact → serving 层同步）
   - `primary` 指针切换的原子性

3. **Rollback 契约**：
   - 回滚窗口（如 primary 切换后 24h 内可一键回滚）
   - 回滚的数据清理策略

**验收标准**：

- [ ] ADR-024 扩展为 "Feature/Factor 版本管理"
- [ ] `FactorVersion` 重命名为 `DerivedVersion`，增加 `entity_type` 字段
- [ ] Publication 流程文档化（artifact → serving 同步）
- [ ] Rollback 命令和回滚窗口定义

**参考**: ADR-024 因子版本管理, MLflow Model Registry

---

### P1-5: Spec 治理字段

| 属性 | 值 |
|------|-----|
| **缺口** | 当前 `derived_spec` 缺少业界 feature store 常规治理字段 |
| **阻塞** | 生产治理、责任追溯 |
| **需要 ADR** | **是** → 扩展 ADR-010 |

**需要补充**：

```sql
-- derived_spec 表扩展
ALTER TABLE derived_spec ADD COLUMN owner TEXT;           -- 责任人（如 "team-alpha"）
ALTER TABLE derived_spec ADD COLUMN freshness_sla TEXT;   -- 新鲜度承诺（如 "T+1"）
ALTER TABLE derived_spec ADD COLUMN validation_policy TEXT; -- 校验策略（如 "strict"/"lenient"）
```

**验收标准**：

- [ ] ADR-010 扩展，补充治理字段定义
- [ ] `derived_spec` 表结构更新
- [ ] CLI 命令支持 `--owner` / `--freshness-sla` 参数

**参考**: ADR-010 Catalog 完整表结构, Hopsworks Feature Store

---

### P1-6: Schema Evolution / Breaking Change 策略

| 属性 | 值 |
|------|-----|
| **缺口** | 有版本管理（ADR-024）和 `spec_hash` 变更检测，但没有显式定义变更分类规则 |
| **阻塞** | 实现者不清楚什么变更必须升版本、什么可以兼容 |
| **需要 ADR** | **是** → 扩展 ADR-024 |

**需要定义**：

| 变更类型 | 示例 | 处理方式 |
|---------|------|---------|
| **Breaking** | 算子变更、参数类型变更、输出列删除/重命名 | 必须升版本 |
| **Additive** | 新增可选参数、新增输出列 | 允许原地兼容（spec_hash 可能变） |
| **Data-only** | 时间范围扩展、universe 变化 | 触发 backfill，不升版本 |

**验收标准**：

- [ ] ADR-024 扩展，补充 Schema Evolution 章节
- [ ] 定义变更分类规则和判断方法
- [ ] CLI `create` 命令能自动检测 breaking change 并提示

**参考**: ADR-024 因子版本管理, Feast Feature View Evolution

---

### P1-7: DQ 最小发布门禁

| 属性 | 值 |
|------|-----|
| **缺口** | 完整 DQ 规则可以 P2，但最小发布门禁需要 P1 |
| **阻塞** | 无法验收增量方案 |
| **需要 ADR** | **是** → ADR-027（部分前置） |

**必须进入 P1 的规则**：

| 规则 | 阈值 | 说明 |
|------|------|------|
| Schema 校验 | 强制 | 输出列名/类型必须匹配 spec |
| 空值率阈值 | ≤ 5% | 超过则告警 |
| 数据新鲜度 | ≤ T+1 | 延迟超过 1 天则告警 |

**P2 可延后的规则**：

- 分布漂移检测（KS 检验 / PSI）
- 极端值自动处理（Winsorize）
- 复杂统计监控

**验收标准**：

- [ ] ADR-027 文档创建，明确 P1/P2 规则划分
- [ ] Schema 校验实现
- [ ] 空值率检查实现
- [ ] 新鲜度检查实现

**参考**: main-design 14.3 节, ADR-018 监控与告警

---

### P1-8: 性能最小 Benchmark Gate

| 属性 | 值 |
|------|-----|
| **缺口** | 完整 SLO 可以 P2，但最小 benchmark gate 需要 P1，否则无法验收增量方案 |
| **阻塞** | 无法验收增量方案 |
| **需要 ADR** | **是** → ADR-028（部分前置） |

**必须进入 P1 的指标**：

| 指标 | 目标 | 说明 |
|------|------|------|
| 单因子增量延迟 | ≤ 30s | 1000 标的 × 1 日增量 |
| 100 因子日更吞吐 | ≤ 10min | 全量因子日更完成时间 |

**P2 可延后的指标**：

- API 查询延迟 P50/P95/P99
- 并发写入压力测试
- 内存峰值限制

**验收标准**：

- [ ] ADR-028 文档创建，明确 P1/P2 指标划分
- [ ] 基准测试脚本（`scripts/benchmark_factor.py`）
- [ ] CI 集成性能门禁检查

**参考**: ADR-015 DAG 优化策略

---

### P1-9: 灾备恢复策略（已暂缓）

| 属性 | 值 |
|------|-----|
| **缺口** | QuestDB/Kvrocks 故障后的恢复流程未明确 |
| **阻塞** | 生产部署 |
| **需要 ADR** | **是** → ADR-023（已有，待激活） |

**待决策项**：

| 决策点 | 选项 | 说明 |
|--------|------|------|
| 分钟级数据灾备 | 本地冷备 / 上游重发 | 影响存储架构 |
| Kvrocks 状态恢复 | 从 Checkpoint 重建 / QuestDB 重放 | 影响恢复时间 |
| RTO/RPO 目标 | 秒级 / 分钟级 / 小时级 | 影响架构复杂度 |

**建议时机**: Phase 1 结束前完成

**参考**: ADR-023 灾备恢复策略

---

## P2 - 改进项

### P2-1: DQ 完整规则

| 属性 | 值 |
|------|-----|
| **缺口** | 分布漂移、极端值检测等完整 DQ 规则 |
| **阻塞** | 无 |
| **需要 ADR** | 扩展 ADR-027 |

**需要定义**：

| 规则类型 | 需要补充 |
|---------|---------|
| 分布漂移 | 检测算法（KS 检验？PSI？）、阈值 |
| 极端值检测 | Winsorize 参数、是否自动处理 |

**参考**: Hopsworks 数据质量框架

---

### P2-2: 性能完整 SLO

| 属性 | 值 |
|------|-----|
| **缺口** | API 查询延迟、并发写入、内存峰值等完整 SLO |
| **阻塞** | 无 |
| **需要 ADR** | 扩展 ADR-028 |

**需要定义**：

| 指标 | 需要补充 |
|------|---------|
| API 查询延迟 | P50/P95/P99 目标 |
| 并发写入 | 最大并发因子数 |
| 内存峰值 | 单因子/全局内存限制 |

---

### P2-3: 可复现实验/训练快照

| 属性 | 值 |
|------|-----|
| **缺口** | 只有 artifact，没有显式的 snapshot manifest / saved dataset 概念 |
| **阻塞** | 无 |
| **需要 ADR** | 待定 |

**P1 已满足**：

当前 metadata.json 已有 `input_snapshots` 字段，P1 阶段可复用。

**P2 扩展**：

- 完整 Snapshot Manifest（所有依赖的精确版本）
- Saved Dataset（用于训练/回测的可复现数据集快照）

---

### P2-4: Lineage 可视化

| 属性 | 值 |
|------|-----|
| **缺口** | `derived_dependency` 表支持 Lineage 查询，但缺少可视化 |
| **阻塞** | 无 |
| **需要 ADR** | 否 |

**建议**：

- 补充 Grafana Lineage 面板设计
- 或集成第三方工具（如 Marquez）

**参考**: ADR-010 Catalog 表结构, Hopsworks Feature Lineage

---

### P2-5: OpenAPI 规范

| 属性 | 值 |
|------|-----|
| **缺口** | ADR-017 API 设计缺少正式的 OpenAPI 规范 |
| **阻塞** | 无 |
| **需要 ADR** | 否 |

**建议**: 补充 `reference/api-spec.yaml`

---

### P2-6: 测试用例模板

| 属性 | 值 |
|------|-----|
| **缺口** | ADR-019 测试策略清晰但缺具体测试用例模板 |
| **阻塞** | 无 |
| **需要 ADR** | 否 |

**建议**: 补充 `reference/test-templates.md`

---

## 缺口汇总矩阵

| 缺口项 | 优先级 | ADR | 阻塞点 | 状态 |
|--------|--------|-----|--------|------|
| Entity/Time 语义契约 | **P0** | ADR-029 新建 | Phase 0 多实体/多市场 | 🔴 待处理 |
| 执行引擎接口分离 | P1 | 复用 ADR-011 | 无 | 🔴 待处理 |
| 运行时错误处理（核心） | P1 | ADR-025 新建 | 无 | 🔴 待处理 |
| 交易日历统一接口 | P1 | ADR-026 新建 | 多市场支持 | 🔴 待处理 |
| Feature/Factor 统一生命周期 | P1 | 扩展 ADR-024 | Feature 版本化 | 🔴 待处理 |
| Spec 治理字段 | P1 | 扩展 ADR-010 | 生产治理 | 🟢 已完成 |
| Schema Evolution 策略 | P1 | 扩展 ADR-024 | 变更分类不明确 | 🔴 待处理 |
| DQ 最小发布门禁 | P1 | ADR-027 新建 | 无法验收 | 🔴 待处理 |
| 性能最小 Benchmark Gate | P1 | ADR-028 新建 | 无法验收 | 🔴 待处理 |
| 灾备恢复策略 | P1 | ADR-023 激活 | 生产部署 | 🟡 已有暂缓 |
| DQ 完整规则 | P2 | 扩展 ADR-027 | 无 | ⚪ 可延后 |
| 性能完整 SLO | P2 | 扩展 ADR-028 | 无 | ⚪ 可延后 |
| 可复现实验快照 | P2 | 待定 | 无 | ⚪ 可延后 |
| Lineage 可视化 | P2 | 否 | 无 | ⚪ 可延后 |
| OpenAPI 规范 | P2 | 否 | 无 | ⚪ 可延后 |
| 测试用例模板 | P2 | 否 | 无 | ⚪ 可延后 |

---

## 业界对标差距

| 差距 | 对标平台 | 当前状态 | 优先级 | 需要 ADR |
|------|---------|---------|--------|---------|
| Entity/Time 语义 | Feast | 缺失 | P0 | ADR-029 |
| 多日历内置 | Qlib | 待设计 ADR-026 | P1 | 是 |
| 统一版本生命周期 | MLflow | 仅 Factor | P1 | 扩展 ADR-024 |
| Spec 治理字段 | Hopsworks | 缺失 | P1 | 扩展 ADR-010 |
| 状态自动持久化 | DolphinDB | Kvrocks 手动管理 | P1 | 否 |
| Lineage 可视化 | Hopsworks | 无 | P2 | 否 |
| 自动 Drift 检测 | Hopsworks | 无 | P2 | 否 |

---

## 变更日志

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-03-06 | 创建问题跟踪文档 | 设计评审 |
| 2026-03-06 | 重排为 P0/P1/P2 + 阻塞关系格式 | 文档清理 |
| 2026-03-07 | 重构为可执行缺口清单 | 用户反馈 |
| 2026-03-07 | 新增 P0-1 Entity/Time 语义契约 | 用户反馈 |
| 2026-03-07 | 调整原 P0-1 流批一体为 P1-1 执行引擎接口分离 | 用户反馈 |
| 2026-03-07 | 拆分 ADR-025/027/028 为 P1 核心部分 + P2 完整部分 | 用户反馈 |
| 2026-03-07 | 新增 P1-4 Feature/Factor 统一生命周期（扩展 ADR-024） | 用户反馈 |
| 2026-03-07 | 新增 P1-5 Spec 治理字段（扩展 ADR-010） | 用户反馈 |
| 2026-03-07 | 新增 P1-6 Schema Evolution/Breaking Change 策略 | 设计评审 |
| 2026-03-07 | 合并 ADR-016 到 ADR-010，废弃 ADR-016 | 设计收口 |
| 2026-03-07 | 修复旧路径引用（realtime-stream-pipeline-design.md） | 文档清理 |
| 2026-03-07 | 修复 PIT 示例漂移（多文件补充 closed="left"） | 安全窗口 |
| 2026-03-07 | P1-5 Spec 治理字段状态更新为已完成 | 已合并到 ADR-010 |
