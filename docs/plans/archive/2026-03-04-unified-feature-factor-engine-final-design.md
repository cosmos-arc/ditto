# Ditto 统一特征/因子引擎最终落地设计（2026-03-04）

## 0. 文档信息

- **状态**: 设计完成（20 个 ADR 全部已决策）
- **作者**: Codex（基于当前仓库代码与用户方案整合）
- **适用范围**: `packages/core` + `packages/datahub` + `apps/port`
- **约束前提**:
  - 不引入 Bronze/Silver/Gold/Platinum 命名
  - 不引入 Iceberg/Delta/Hudi
  - 保持现有 Ditto 分层与 DataHub 路径体系一致

---

## 0.1 设计进度与待办

### 已完成设计

| 章节 | 状态 | 最后更新 | 备注 |
|------|------|---------|------|
| **11.4.1** 存储技术选型 | ✅ 完成 | 2026-03-04 | QuestDB + Kvrocks + Parquet 分层架构 |
| **11.4.2** 分层存储架构 | ✅ 完成 | 2026-03-04 | Hot/Warm/Cold 架构图、数据流 |
| **11.4.2.1** 存储成本估算 | ✅ 完成 | 2026-03-04 | QuestDB ~1GB, Kvrocks ~11MB, 年成本 ~$18 |
| **11.4.2.2** 存储使用场景与约束 | ✅ 完成 | 2026-03-04 | 各组件在 Ditto 中的具体用法 |
| **11.4.4.1** 多级数据粒度策略 | ✅ 完成 | 2026-03-04 | 混合模式 + 可配置阈值 |
| **11.4.4.2** 独立状态管理模块 | ✅ 完成 | 2026-03-04 | 架构设计、核心接口 |
| **11.4.4.4** QuestDB 预聚合设计 | ✅ 完成 | 2026-03-04 | 表结构、SAMPLE BY、混合计算 |
| **11.4.4.5** 数据回补与异常处理 | ✅ 完成 | 2026-03-04 | O3/DEDUP、回补流程 |
| **Kvrocks 状态详细设计** | ✅ 完成 | 2026-03-04 | Key 设计、状态结构、Checkpoint、幂等保证 |
| **ADR-012** 算子增量实现架构 | ✅ 完成 | 2026-03-05 | 5 层分类 + sortedcontainers + 状态接口 |
| **ADR-013** ts_rank 精度策略 | ✅ 完成 | 2026-03-05 | 始终精确计算 + 完整窗口维护 |
| **ADR-014** 表达式引擎核心设计 | ✅ 完成 | 2026-03-05 | Polars Expr + Spec缓存+CSE + 严格null + 详细错误 |
| **ADR-015** DAG 优化策略 | ✅ 完成 | 2026-03-05 | 串行执行 + 精确影响范围 + Polars Lazy 内存管理 |
| **ADR-016** Catalog 存储架构 | ✅ 完成 | 2026-03-05 | SQLite + Kvrocks 混合方案 |
| **ADR-017** 因子服务 API | ✅ 完成 | 2026-03-05 | 声明式 + 异步优先 + Prefect + 窄表默认 |
| **ADR-018** 监控与告警 | ✅ 完成 | 2026-03-05 | VictoriaMetrics + Grafana + 复用全局告警 |
| **ADR-019** 测试策略 | ✅ 完成 | 2026-03-05 | 单元+集成 + 混合数据 + 内存后端 + 分级覆盖率 |
| **ADR-020** 部署与运维 | ✅ 完成 | 2026-03-05 | Docker Compose + testcontainers + fakeredis |

### 待讨论/待设计

| 事项 | 优先级 | 备注 |
|------|-------|------|
| ~~DAG 优化策略~~ | ~~高~~ | ~~消除重复计算、公共子表达式提取~~ → **已决策 ADR-015** |
| ~~表达式引擎设计~~ | ~~高~~ | ~~Pratt 解析器、AST、Analyzer、Codegen~~ → **已决策 ADR-014** |
| ~~Catalog 与元数据管理~~ | ~~中~~ | ~~run 与 state 维度的 Catalog 设计~~ → **已决策 ADR-016** |
| ~~因子服务 API~~ | ~~中~~ | ~~Materialize 写入 API、查询 API~~ → **已决策 ADR-017** |
| ~~监控与告警~~ | ~~中~~ | ~~状态监控、数据延迟告警~~ → **已决策 ADR-018** |
| ~~测试策略~~ | ~~中~~ | ~~单元测试、集成测试、E2E 测试设计~~ → **已决策 ADR-019** |
| ~~部署与运维~~ | ~~低~~ | ~~QuestDB/Kvrocks 部署、配置管理~~ → **已决策 ADR-020** |

### 关键决策记录

| 决策点 | 决策 | 日期 | 理由 |
|-------|------|------|------|
| 预聚合粒度 | 混合模式（分钟/小时/日动态选择） | 2026-03-04 | 精度与存储的平衡 |
| 增量统计位置 | 独立状态管理模块 | 2026-03-04 | 职责分离、可测试、可扩展 |
| 长周期阈值 | 可配置（默认 60 天） | 2026-03-04 | 灵活性、覆盖常用因子 |
| 时序存储 | QuestDB | 2026-03-04 | O3/DEDUP/SAMPLE BY 原生支持，降低 ETL 复杂度 |
| 状态存储 | Kvrocks | 2026-03-04 | Redis 协议兼容 + RocksDB 持久化 |
| 算子增量架构 | 独立状态模块 + 5 层分类 | 2026-03-05 | 职责分离、按复杂度分层 |
| 有序结构实现 | sortedcontainers 库 | 2026-03-05 | O(log n) 增量 vs bisect O(n) |
| ts_rank 精度 | 始终精确计算 | 2026-03-05 | 因子精度敏感 + 50MB 可接受 |
| Codegen 输出 | Polars Expr | 2026-03-05 | 可组合、延迟执行、易于优化 |
| 表达式缓存 | Spec 级 + CSE | 2026-03-05 | Qlib 两级缓存 + 直接实现 Phase 1 |
| 空值处理 | 严格模式（null 传播） | 2026-03-05 | 数据质量可见，便于排查 |
| 错误报告 | 带位置高亮的详细错误 | 2026-03-05 | 类似 Rust 编译器，开发体验好 |
| 多因子执行 | 拓扑排序 + 串行 | 2026-03-05 | Polars 内部已并行，Python 层串行开销可控 |
| 增量计算边界 | 精确影响范围 | 2026-03-05 | TS 向后扩展 lookback，CS 整日重算 |
| 中间结果内存 | Polars 自动管理 | 2026-03-05 | Lazy 执行引擎自动优化 |
| Catalog 存储 | SQLite + Kvrocks 混合 | 2026-03-05 | 关系查询用 SQLite，状态用 Kvrocks |
| 因子服务 API | 声明式 + 异步优先 | 2026-03-05 | Prefect 编排 + 窄表默认 |
| 监控方案 | VictoriaMetrics + Grafana | 2026-03-05 | 复用全局告警基础设施 |
| 测试策略 | 单元+集成+E2E | 2026-03-05 | 内存后端 + 分级覆盖率 |
| 部署方式 | Docker Compose | 2026-03-05 | testcontainers + fakeredis |

### 遗留问题

1. ~~**PIT（Point-in-Time）一致性**：如何保证因子计算的时间点一致性？~~ → **已决策 ADR-021**
2. ~~**更正数据处理**：历史数据修正后的级联更新策略？~~ → **已决策 ADR-022**
3. **灾备恢复**：QuestDB/Kvrocks 故障后的恢复流程？ → **暂缓 ADR-023**
4. ~~**因子版本管理**：因子逻辑变更后如何处理历史数据？~~ → **已决策 ADR-024**

---

## 1. 设计目标与非目标

## 1.1 目标

1. 统一 Feature 与 Factor 的计算、物化、增量、发布流程。
2. 建立 Pratt 表达式引擎与静态分析能力，支持 `deps/lookback/scope/requires_full_day` 推导。
3. 全量与增量逻辑收敛到同一执行引擎，仅由 `RunConfig` 改变执行边界。
4. 与当前 Ditto 架构和命名兼容：`market/fundamental/capital/macro/features/factors/runtime`。
5. 保障本地盘并发写的一致性：锁 + 原子提交 + Catalog 事务更新。

## 1.2 非目标

1. 不做分布式计算调度（Spark/Flink/K8s）。
2. 不做 lakehouse 表格式事务层。
3. 不在当前阶段实现复杂 DSL 语言特性（宏、模块、用户函数脚本化）。
4. 不修改现有 T0/T1/T2/T3 主摄取职责，仅在其后挂接衍生物化。

---

## 2. 对用户方案的评估与最终裁决

## 2.1 结论摘要

用户方案整体方向正确，尤其是以下三点应完整采纳：

1. **表达式先编译后执行**（Pratt + AST + Analyzer + Codegen）。
2. **统一全量/增量执行链路**（仅边界规划不同）。
3. **静态分析驱动增量裁剪**（lookback/requires_full_day 是关键）。

同时需做四项仓库对齐调整：

1. 命名与目录必须使用 Ditto 现有域，不采用 Bronze/Silver/Gold/Platinum。
2. DataHub 当前主分区是按年（`YYYY.parquet`），第一阶段先兼容年分区，再演进到 year/month。
3. 现有 Feature/Factor Service 偏查询，需要补齐 Materialize 写入 API。
4. Catalog 不能只保留单表最简版，至少要有 run 与 state 维度，才能支持可观测与重试。

## 2.2 评估矩阵

| 议题 | 用户方案 | 最终决策 | 原因 |
|---|---|---|---|
| 分层命名 | Bronze/Silver/Gold/Platinum | 改为现有 Domain 命名 | 与现有路径、团队认知、代码一致 |
| 计算语言 | Pratt DSL | 采纳 | 满足量化公式与静态分析 |
| 执行引擎 | Polars | 采纳 | 现有栈已使用 Polars |
| 增量机制 | watermark-lookback 覆盖写 | 采纳 | 本地盘可控、实现成本低 |
| 分区策略 | year/month | **阶段化**：先 year，后 year/month | 与现有 `YearlyPartition` 兼容 |
| Catalog | 单表 | 扩展为多表 | 需要 run-level 可追踪性 |
| 并发控制 | 锁 + rename | 采纳并细化锁键 | 匹配现有 `FileLockManager` |
| 事务一致性 | 文件与元数据一致 | 采纳 | 防止“数据写了但 catalog 未更新” |

## 2.3 取长补短融合版（你方案 + 本设计）

### A. 直接沿用你方案（保持不改）

1. `Pratt Parser -> AST -> Analyzer -> Polars` 的编译链路。
2. TS/CS 作用域模型与 `requires_full_day` 语义。
3. 增量算法核心：`watermark - lookback` 回退预热 + 覆盖写分区。
4. 因子默认标准化管线：`cs_rank -> cs_zscore`。
5. 因子 PIT 强制化（`effective_from/effective_to`）。

### B. 我补强的落地项（保证可工程化）

1. 与 Ditto 现有 Domain 命名对齐，不引入 Bronze/Silver/Gold/Platinum。
2. 以当前 `YearlyPartition` 为第一阶段兼容基线，避免一次性改造所有读写链路。
3. Catalog 从“单表”提升为 `spec/state/run/partition/invalidation`，保证重试、追踪、排障可用。
4. 增加 Artifact 层，兼顾“版本复现”与现有 Serving 路径兼容。
5. 明确锁粒度和提交顺序，确保本地盘并发写不会出现元数据漂移。
6. 在 Port 层引入 materialization flow，不破坏现有 `T0/T1/T2/T3` 摄取职责边界。

### C. 暂缓项（后续版本）

1. 分布式计算框架接入。
2. lakehouse 表格式（Iceberg/Delta/Hudi）。
3. DSL 高级语法（宏、模块系统、用户扩展函数）。
4. 全面切换到 year/month serving 分区（先通过 artifact 验证收益）。

---

## 3. 仓库现状对齐（As-Is）

## 3.1 架构边界（必须遵守）

1. 分层由 Import Linter 强约束：`Port -> Core -> DataHub -> Infra`。
2. Core 对 DataHub 依赖受限，当前规则仅放行 `ditto_datahub.models.*`。
3. Port 运行路径不允许直接访问 DataHub stores/runtime（registry 装配例外）。

## 3.2 现有数据与任务结构

1. 摄取编排已实现 `T0_META -> T1_INCREMENTAL -> T3_QUALITY`。
2. 存储路径已稳定：
   - `features/technical/indicators_narrow`
   - `factors/factors_narrow`
3. Runtime 已有：
   - `FileLockManager`
   - `FreezeManager`
   - `ingestion_log`

## 3.3 当前短板

1. `FeatureService/FactorService` 主要是查询接口，缺少 materialize 级别写入契约。
2. 缺少统一表达式引擎、Spec、执行计划、增量失效集模型。
3. 摄取日志表不足以承载衍生物化的版本与水位元数据。
4. Feature/Factor provider 传入路径存在与 store 内 `_dataset` 重复拼接风险（需优先修正）。

---

## 4. 最终架构（To-Be）

## 4.1 分层职责

### A. `apps/port`（应用编排层）

1. 接收 CLI/API/Flow 请求，组装 `RunConfig`。
2. 调度 `MaterializeService` 执行 feature/factor 物化。
3. 处理发布（latest 指针）、报告、告警。

### B. `packages/core`（计算引擎层，新增核心能力）

1. `ExpressionEngine`：Pratt 编译链路。
2. `Analyzer`：静态分析与增量边界推导。
3. `FeatureEngine`/`FactorEngine`：执行计划 + 标准化 + PIT 规整。
4. `NormalizationPipeline`：`cs_rank/cs_zscore/winsorize/neutralize`。

### C. `packages/datahub`（存储与元数据层）

1. 读取 source domains 输入数据。
2. 写入 derived domains（features/factors）。
3. 管理 Catalog（spec/version/watermark/run/coverage/partition stats）。
4. 通过锁与原子提交保障一致性。

### D. `packages/infra`（横切能力）

1. 文件锁、原子写、日志、指标、追踪。
2. 提供可复用并发与 I/O 原语。

## 4.2 端到端数据流

```text
T1 摄取完成
  -> materialize_features (full/inc)
  -> materialize_factors  (full/inc)
  -> validate/publish/latest
```

研究与生产均走同一条链路，只是 `mode`、`coverage`、`universe_policy` 不同。

---

## 5. 模块设计与文件落点

## 5.1 Core 新增模块

建议目录：

```text
packages/core/src/ditto_core/engine/
  specs.py
  materialization/
    __init__.py
    models.py
    feature_engine.py
    factor_engine.py
    normalization.py
    pit.py
  expression/
    __init__.py
    lexer.py
    parser.py
    ast.py
    analyzer.py
    dag.py
    codegen.py
    plan.py
  ops/
    __init__.py
    registry.py
    builtins.py
```

## 5.2 DataHub 新增模块

建议目录：

```text
packages/datahub/src/ditto_datahub/
  services/
    derived_materialization_service.py
  stores/
    runtime/
      catalog/
        derived_catalog_reader.py
        derived_catalog_writer.py
    features/
      materialized/
        feature_materialized_reader.py
        feature_materialized_writer.py
    factors/
      materialized/
        factor_materialized_reader.py
        factor_materialized_writer.py
  models/
    derived_catalog.py
```

## 5.3 Port 新增模块

建议目录：

```text
apps/port/src/ditto_port/
  services/
    materialization/
      service.py
      planner.py
      publication.py
  jobs/
    flows/
      materialize.py
    tasks/
      materialize.py
  cli/
    commands/
      materialize.py
```

---

## 6. 统一模型契约（Spec/RunConfig/Result）

## 6.1 Spec 模型（Core）

```python
class NormalizationStage(BaseModel):
    method: Literal["cs_rank", "cs_zscore", "winsorize", "neutralize"]
    params: dict[str, object] = Field(default_factory=dict)

class BaseSpec(BaseModel):
    id: str
    expression: str
    universe_policy: str = "tradable"
    engine_version: str = "v0"
    tags: list[str] = Field(default_factory=list)

    @property
    def spec_hash(self) -> str: ...

class FeatureSpec(BaseSpec):
    kind: Literal["indicator", "feature"]
    pit_required: bool = False
    output_columns: list[str] = Field(default_factory=lambda: ["value"])

class FactorSpec(BaseSpec):
    pit_required: bool = True
    normalization_pipeline: list[NormalizationStage] = Field(
        default_factory=lambda: [
            NormalizationStage(method="cs_rank"),
            NormalizationStage(method="cs_zscore"),
        ]
    )
```

## 6.2 RunConfig（应用层传入）

```python
class RunConfig(BaseModel):
    mode: Literal["full", "incremental"]
    start_date: date
    end_date: date
    as_of_date: date | None = None
    parallelism: int = 4
    source_snapshot_id: str | None = None
    force_recompute: bool = False
```

## 6.3 MaterializeResult（统一输出）

```python
class MaterializeResult(BaseModel):
    entity_type: Literal["feature", "factor"]
    entity_id: str
    version: int
    spec_hash: str
    coverage_start: date
    coverage_end: date
    watermark: date
    rows_written: int
    partitions_written: list[str]
    duration_ms: int
    stats: dict[str, float | int | str]
```

---

## 7. Pratt 表达式引擎设计

## 7.1 编译链路

```text
expression(str)
  -> Lexer(tokens with span)
  -> Pratt Parser(AST)
  -> Analyzer(deps/scope/lookback/requires_full_day)
  -> DAG/CSE(可选优化)
  -> Codegen(Polars Expr / Lazy plan)
  -> ExecutionPlan
```

## 7.2 AST 节点

1. `Const(value)`
2. `Column(name, namespace)`:
   - `$close`（市场列）
   - `$$pe_ttm`（PIT/基本面列）
3. `Call(name, args, kwargs)`
4. `Unary(op, expr)`
5. `Binary(op, left, right)`

## 7.3 算子元信息（OperatorRegistry）

每个算子至少注册 4 类信息：

1. `signature`
2. `scope_rule`
3. `lookback_rule`
4. `codegen_rule`

示例：

```python
OperatorDef(
    name="CSRank",
    signature="CSRank(x)",
    scope_rule=lambda x: "CS",
    lookback_rule=lambda x: x.lookback,
    requires_full_day=True,
    codegen=codegen_cs_rank,
)
```

## 7.4 作用域与嵌套限制

1. TS 算子：`Ref/Mean/Std/Delta/PctChange`
2. CS 算子：`CSRank/CSZScore/Neutralize`
3. 混合表达式允许但需分阶段执行：
   - 先 TS 产出中间列，再 CS
4. 明确拒绝不可控嵌套：
   - 示例：`Mean(CSRank(x), 5)` 直接编译期报错

## 7.5 Lookback 与边界推导

规则：

1. `Ref(x,n)` -> `lookback = lookback(x) + max(n,0)`
2. `Mean/Std(x,w)` -> `max(lookback(x), w-1)`
3. `If(c,a,b)` -> `max(lookback(c),lookback(a),lookback(b))`
4. `CSRank/CSZScore` -> `lookback` 不增，但 `requires_full_day=True`

输出：

```python
Analysis(
    deps={"close", "volume"},
    scope="MIXED",
    lookback=19,
    requires_full_day=True,
    requires_sort=["instrument_id", "trade_date"],
)
```

---

## 8. FeatureEngine / FactorEngine 执行模型

## 8.1 FeatureEngine

输入：source domain DataFrame（通常来自 market/capital/fundamental）。

流程：

1. 解析并编译 expression。
2. 按 execution plan 计算 `value` 或多列输出。
3. 可选标准化（feature 默认不做 CS 标准化）。
4. 输出并交由 DataHub writer 落盘与记录 catalog。

## 8.2 FactorEngine

输入：source domains + 可选 feature 依赖。

流程：

1. raw 计算（expression/calculator）。
2. normalization pipeline（默认 rank -> zscore）。
3. PIT 规整：补全 `effective_from/effective_to`。
4. 输出 schema：
   - `instrument_id`
   - `trade_date`
   - `factor_id`
   - `raw_value`
   - `exposure`
   - `effective_from`
   - `effective_to`
   - `spec_hash`
   - `run_id`

---

## 9. 全量/增量一体化算法

## 9.1 Full 模式

1. 输入 `[request_start, request_end]`。
2. `compute_start = request_start - lookback`（交易日意义）。
3. 计算后截断仅写 `[request_start, request_end]`。

## 9.2 Incremental 模式

前提读取：

1. `watermark`（当前版本连续物化最晚日期）。
2. `analysis.lookback`。
3. `invalidation_set`（输入变更影响日期/标的）。

边界推导：

```text
candidate_start = min(request_start, min(invalidation_dates, default=request_start))
compute_start   = min(candidate_start, watermark - lookback)
compute_end     = request_end
```

输出裁剪：

1. 默认仅写 `trade_date > watermark` 或落在 invalidation 覆盖区间的数据。
2. 若 `requires_full_day=True`，对受影响日做“整日全截面”重算。

## 9.3 Invalidation 机制

来源：

1. source domain 写入后的 `snapshot_id` 与变更摘要。
2. 复权、PIT 修订、基础面重述、公司行为追溯等。

扩展规则：

1. TS 因子：以 `(instrument_id, date)` 为粒度扩展 lookback。
2. CS 因子：任一标的变化会放大为该 `trade_date` 全截面。

---

## 10. PIT 语义与实现

遵循现有 PIT 规则：`as_of_date in [effective_from, effective_to)`。

## 10.1 何时强制 PIT

1. Factor：强制 PIT。
2. Feature：
   - 技术类可选 PIT（默认 false）
   - 基本面衍生必须 PIT（true）

## 10.2 规则

1. 新版本写入时：
   - 旧记录 `effective_to` 被截断到新记录 `effective_from`
2. 查询时：
   - `effective_to` 为 null 表示当前有效

## 10.3 场景

1. 行情类：通常 `effective_from = trade_date`。
2. 基本面：`effective_from = knowledge_date/announcement_date`。
3. 修订：会导致历史窗口回溯重算。

---

## 11. 存储与 Catalog 设计（DataHub）

## 11.1 目录策略（最终）

### A. Serving 路径（兼容现有）

1. `features/technical/indicators_narrow/YYYY.parquet`
2. `factors/factors_narrow/YYYY.parquet`

### B. Artifact 路径（新增，版本化工件）

```text
runtime/materialization/artifacts/
  features/{feature_id}/spec={spec_hash}/year=YYYY/month=MM/part-*.parquet
  factors/{factor_id}/spec={spec_hash}/year=YYYY/month=MM/part-*.parquet
```

说明：

1. Serving 层继续服务查询兼容。
2. Artifact 层用于可复现与离线排障。
3. 发布时将 artifact 同步/投影到 serving 层（或直接双写）。

## 11.2 元数据（metadata.json）

每次物化工件目录写入：

```json
{
  "entity_type": "factor",
  "entity_id": "alpha_001",
  "version": 3,
  "spec_hash": "xxxx",
  "engine_version": "expr-v0",
  "coverage_start": "2024-01-01",
  "coverage_end": "2026-03-03",
  "watermark": "2026-03-03",
  "input_snapshots": ["market:20260303-abc"],
  "partitions_written": ["2026-03"],
  "stats": {
    "rows": 123456,
    "null_rate": 0.001
  }
}
```

## 11.3 SQLite Catalog 表设计（推荐）

文件位置：`{data_root}/runtime/catalog.sqlite`（或复用 metadata sqlite 并加命名空间）。

```sql
CREATE TABLE IF NOT EXISTS derived_spec (
  entity_type TEXT NOT NULL,         -- feature/factor
  entity_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  spec_json TEXT NOT NULL,
  spec_hash TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (entity_type, entity_id, version),
  UNIQUE (entity_type, entity_id, spec_hash, engine_version)
);

CREATE TABLE IF NOT EXISTS derived_state (
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  coverage_start TEXT,
  coverage_end TEXT,
  watermark TEXT,
  latest_run_id TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (entity_type, entity_id, version)
);

CREATE TABLE IF NOT EXISTS derived_run (
  run_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  mode TEXT NOT NULL,                -- full/incremental
  request_start TEXT NOT NULL,
  request_end TEXT NOT NULL,
  compute_start TEXT NOT NULL,
  compute_end TEXT NOT NULL,
  status TEXT NOT NULL,              -- RUNNING/SUCCESS/FAILED
  source_snapshot_id TEXT,
  rows_written INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS derived_partition (
  run_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  partition_key TEXT NOT NULL,       -- e.g. 2026 or 2026-03
  file_path TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  checksum TEXT,
  PRIMARY KEY (run_id, partition_key)
);

CREATE TABLE IF NOT EXISTS derived_invalidation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_domain TEXT NOT NULL,       -- market/fundamental/capital/macro
  source_dataset TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  affected_start TEXT NOT NULL,
  affected_end TEXT NOT NULL,
  requires_full_day INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
```

---

## 12. 并发与原子提交策略

## 12.1 锁粒度

推荐锁键：

1. 计算锁：`derived/{entity_type}/{entity_id}/v{version}`
2. 分区写锁：`derived/{entity_type}/{entity_id}/v{version}/{partition_key}`

规则：

1. 同 `entity_id + version` 串行。
2. 不同实体可并行。
3. 读操作无锁或短锁。

## 12.2 提交顺序（必须）

1. 获取锁。
2. 计算并写临时目录。
3. 校验（schema/row_count/checksum）。
4. 原子替换目标分区（同文件系统 rename）。
5. SQLite 事务写入 `derived_partition + derived_run + derived_state`。
6. 提交事务，释放锁。

## 12.3 故障恢复

1. RUNNING 超时 run 自动标记 FAILED。
2. 清理孤儿临时目录。
3. 基于 `derived_run` 支持幂等重跑。

---

## 13. 与现有摄取流程集成

## 13.1 Flow 级集成策略

1. 保持现有 `daily_ingestion_flow` 不变。
2. 新增 `daily_materialization_flow`：
   - 输入：trade_date, mode, ids
   - 输出：features/factors 物化结果
3. 组合 `daily_pipeline_flow`：
   - `daily_ingestion_flow` 成功后触发 `daily_materialization_flow`

## 13.2 T2_REPAIR / backfill 集成

1. repair/backfill 完成后，生成对应 source snapshot invalidation。
2. 触发受影响实体的增量重算。
3. 对 `requires_full_day` 因子按日全截面回补。

## 13.3 CLI 设计

```bash
ditto run materialize \
  --domain factors \
  --id alpha_001 \
  --mode incremental \
  --start 2026-03-01 \
  --end 2026-03-04 \
  --universe tradable
```

---

## 14. 观测性与质量门禁

## 14.1 指标

1. `materialize_run_total{entity_type,status}`
2. `materialize_duration_seconds`
3. `materialize_rows_written`
4. `materialize_null_rate`
5. `materialize_watermark_lag_days`

## 14.2 日志字段

每次 run 至少记录：

1. `run_id`
2. `entity_type/entity_id/version/spec_hash`
3. `request_start/end`
4. `compute_start/end`
5. `lookback/requires_full_day`
6. `partitions_written`

## 14.3 DQ 最小规则

1. schema 校验（关键列/类型）。
2. 空值率阈值告警。
3. 分布漂移基础监控（均值/方差/分位数）。

---

## 15. 约束一致性（架构与工程规则）

## 15.1 分层一致性

1. Port 编排，Core 计算，DataHub 存储。
2. Core 不直接操作文件系统。
3. DataHub 不依赖 Core。

## 15.2 现有路径一致性

1. 继续以 `DataStoreSettings` 为唯一路径真源。
2. 修复 provider 中“已拼接路径 + store 内 `_dataset` 再拼接”的不一致问题。

## 15.3 PIT 一致性

严格使用半开区间语义：

```text
effective_from <= as_of_date < effective_to(or null)
```

---

## 16. 分阶段实施计划（可直接执行）

## Phase 0（1-2 周）：内核可跑通

目标：表达式 + 分析 + 单实体物化跑通。

交付：

1. `specs.py` + `RunConfig` + `MaterializeResult`。
2. Pratt `lexer/parser/ast`。
3. Analyzer（`deps/lookback/scope/requires_full_day`）。
4. OperatorRegistry 首批算子：`Ref/Mean/Std/Delta/Pct/CSRank/CSZScore/If`。
5. Factor/Feature 基础 writer（至少支持 year 分区覆写）。
6. Catalog 四张核心表（`derived_spec/state/run/partition`）。

验收：

1. 能计算并写入首个技术指标与首个因子。
2. 能记录 watermark 并完成一次 incremental。

## Phase 1（2-3 周）：增量与并发完善

目标：可用性与性能。

交付：

1. invalidation 表与扩展逻辑。
2. requires_full_day 触发整日重算。
3. 表级/分区级锁策略落实。
4. CSE/DAG 优化。
5. Flow 与 CLI 接入。

验收：

1. 多因子并行运行稳定。
2. 增量结果与全量结果抽样一致。

## Phase 2（3-4 周）：PIT 与研究生产闭环

目标：研究/生产统一。

交付：

1. 基本面修订触发区间回算。
2. feature_sets 宽表输出。
3. publish/latest 与回滚机制。
4. 丰富算子与标准化流程（neutralize/group neutralize）。

验收：

1. 研究回放与生产日更使用同一引擎代码路径。
2. 质量与可观测指标达标。

## 16.4 联合执行顺序（按你建议优先级）

1. **先做任务 2（Parser 内核）**：
   - `lexer.py`、`ast.py`、`parser.py` + 对应 pytest。
2. **再做任务 3（Analyzer/Registry）**：
   - `analyzer.py` + 首批算子注册（`Ref/Mean/Std` 起步）。
3. **随后做任务 1（Spec + Catalog）**：
   - `specs.py` 与 `derived_*` Catalog 表结构。
4. **最后做任务 4（执行器联调）**：
   - `executor.py` + Polars LazyFrame 端到端断言。

说明：这个顺序继承了你“先 parser 再执行”的高收益路径，同时补上 catalog 与并发一致性，避免后续返工。

---

## 17. 测试策略（TDD 维度）

## 17.1 Core 单元测试

1. Lexer token 测试。
2. Parser AST 结构快照测试。
3. Analyzer lookback/scope 测试。
4. Operator codegen 与 Polars 结果对齐测试。

## 17.2 DataHub 单元/集成测试

1. Catalog CRUD + 事务一致性。
2. 锁竞争测试（并发写同实体）。
3. 原子提交失败回滚测试。

## 17.3 Port 集成测试

1. `daily_ingestion -> materialization` 串联。
2. backfill/repair 后 invalidation 触发。

## 17.4 验证命令

```bash
pixi run -e dev check
pixi run -e dev arch-check
pixi run -e dev test --integration
```

---

## 18. 风险与对策

| 风险 | 级别 | 对策 |
|---|---|---|
| 表达式嵌套导致 requires_full_day 推导错误 | 高 | 编译期静态分析 + 属性向上传播 + 单元测试覆盖所有嵌套模式 |
| 增量边界遗漏造成信号错误 | 高 | lookback + invalidation 双保险 + 回归测试 |
| 本地盘并发导致元数据与文件不一致 | 高 | 锁内执行 rename + sqlite 事务 |
| 小文件增多影响查询性能 | 中 | 年/月份覆盖写，禁用日级 append |
| Provider 路径拼接错误导致数据落错目录 | 高 | 先修 Provider 路径契约并补测试 |
| 表达式过于复杂导致性能问题 | 中 | 编译期 DAG 深度警告 + 执行计划优化 |

---

## 19. 立即执行清单（下一步）

1. **先修一致性问题**：
   - 修复 features/factors provider 的 data_root 传参方式，统一与 store dataset 约定。
2. **落地 Core 内核**：
   - 从 `expression/lexer.py + parser.py + ast.py + analyzer.py` 开始 TDD。
3. **补齐 Catalog**：
   - 新增 `derived_*` 元数据表与 reader/writer。
4. **打通最小闭环**：
   - 一个 feature + 一个 factor 的 full/incremental 两种模式端到端跑通。

---

## 20. 架构决策记录（ADR）

### ADR-001: TS/CS 嵌套策略

**状态**: 已决策（2026-03-04）

**背景**:

表达式引擎需要支持时间序列（TS）和横截面（CS）算子的嵌套组合。WorldQuant Alpha101 中约 80% 的因子需要 TS/CS 混合嵌套表达，如：
- `ts_rank(rank(low), 9)` — TS(CS(x))
- `rank(ts_delta(close, 20))` — CS(TS(x))
- `correlation(rank(open), rank(volume), 10)` — TS(CS(x), CS(y))

**决策**:

采用**自动分层执行 + 语义向上传播**策略：

1. **支持任意嵌套**：允许 `TS(CS(x))`、`CS(TS(x))`、`TS(CS(x), CS(y))` 等任意合法嵌套组合
2. **自动推导属性**：编译期自动计算每个子表达式的 `lookback`、`requires_full_day`、`scope`
3. **向上传播约束**：若子表达式 `requires_full_day=True`，则父表达式继承该约束
4. **分层执行**：引擎自动划分执行阶段，先执行纯 TS 阶段，再执行 CS 阶段

**算子分类**:

```python
class OperatorCategory(Enum):
    TS = “time_series”      # 时间序列操作，group by instrument
    CS = “cross_sectional”  # 截面操作，group by date
    SCALAR = “scalar”       # 标量操作（abs, log, +, -, *, /）
```

**编译期规则**:

| 规则 | 处理方式 | 说明 |
|------|---------|------|
| CS(CS(x)) | 警告 | 冗余但无害，如 `rank(rank(x))` |
| TS(CS(x)) | 正常 | requires_full_day=True 向上传播 |
| CS(TS(x)) | 正常 | requires_full_day=True |
| DAG 深度 > 10 | 警告 | 避免过于复杂的表达式 |

**增量计算影响**:

- 若表达式任意子表达式 `requires_full_day=True`，则增量重算时需整日完整数据
- lookback 计算考虑所有 TS 算子的窗口需求

**业界对标**:

| 平台 | 策略 | Ditto 选择 |
|------|------|-----------|
| DolphinDB | 显式 `context by` 分组 | 类似，但自动推导 |
| Qlib | 仅 TS，CS 后处理 | ✗ 表达能力不足 |
| BigQuant | 自动分层执行 | ✓ 采用此方案 |
| WorldQuant Brain | 任意嵌套 | ✓ 兼容 |

**实现路径**:

- **Phase 0**：支持自由嵌套 + 编译期属性推导
- **Phase 1**：引入显式阶段划分优化
- **Phase 2**：阶段间并行执行

---

### ADR-002: 算子体系设计

**状态**: 已决策（2026-03-04）

**决策**:

1. **命名风格**: WorldQuant 风格（前缀区分 TS/CS）
   - TS 算子: `ts_mean`, `ts_rank`, `ts_delta`, `ts_corr`
   - CS 算子: `cs_rank`, `cs_zscore`, `cs_demean`
   - 标量算子: `abs`, `log`, `sign`, `power`

2. **首批算子范围**: 全功能（P0 + P1 + P2），约 50+ 个算子
   - 目标：完整支持 WorldQuant Alpha101 + 常用技术指标
   - 优先级：P0 核心必选 → P1 增强能力 → P2 高级能力

3. **分组中性化支持**: 首批支持
   - `group_rank(x, group)` - 组内排名
   - `group_zscore(x, group)` - 组内标准化
   - `group_demean(x, group)` - 组内去均值
   - 需要：行业分类数据关联

**首批算子清单**（按类别）:

| 类别 | 算子 | 说明 |
|------|------|------|
| **TS 滚动聚合** | `ts_mean`, `ts_sum`, `ts_std`, `ts_var`, `ts_max`, `ts_min`, `ts_count`, `ts_prod`, `ts_med` | 窗口聚合 |
| **TS 延迟/变化** | `ts_delay`, `ts_delta`, `ts_pct_change` | 时间序列基础 |
| **TS 排名** | `ts_rank`, `ts_argmax`, `ts_argmin` | 窗口内排名 |
| **TS 相关** | `ts_corr`, `ts_cov` | 滚动相关/协方差 |
| **TS 分位数** | `ts_quantile`, `ts_qtlu`, `ts_qtld` | 分位数操作 |
| **TS 加权** | `ts_wma`, `ts_ema`, `ts_decay_linear` | 加权移动平均 |
| **TS 高阶** | `ts_skew`, `ts_kurt` | 高阶统计量 |
| **CS 排名** | `cs_rank`, `cs_scale` | 截面排名/缩放 |
| **CS 标准化** | `cs_zscore`, `cs_demean`, `cs_winsorize` | 截面标准化 |
| **CS 分组** | `group_rank`, `group_zscore`, `group_demean` | 组内操作 |
| **标量-数学** | `abs`, `log`, `exp`, `sqrt`, `sign`, `power` | 数学函数 |
| **标量-比较** | `max2`, `min2`, `clip` | 比较函数 |
| **标量-逻辑** | `if_else`, `and`, `or`, `not` | 逻辑函数 |
| **技术指标** | `rsi`, `atr`, `macd`, `boll`, `kdj` | 复合技术指标 |

---

### ADR-003: 技术指标 vs 算子架构

**状态**: 已决策（2026-03-04）

**核心决策**: **算子 + 表达式库** 双层设计

```
┌─────────────────────────────────────────────────────────────┐
│                    用户视角                                  │
│  因子定义: "ts_rank(cs_rank(close), 9) + rsi_14"            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐│
│  │              表达式层（Expression Layer）                ││
│  │  - 用户自定义表达式                                       ││
│  │  - 预定义技术指标库（RSI, MACD, BOLL...）                 ││
│  │  - Alpha101 因子库                                       ││
│  └─────────────────────────────────────────────────────────┘│
│                          │ 宏展开                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              算子层（Operator Layer）                    ││
│  │  - ts_mean, ts_rank, cs_rank, +, -, *, /, log...       ││
│  │  - 约 50 个原子算子                                      ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**概念边界**:

| 概念 | 定义 | 特点 | 示例 |
|------|------|------|------|
| **算子** | 原子级计算单元 | 语义单一、无状态、可嵌套 | `ts_mean`, `cs_rank`, `+`, `log` |
| **技术指标** | 预定义复合表达式 | 语义完整、由算子组合 | `RSI(14)`, `MACD(12,26,9)` |
| **特征** | 单列输出，可持久化 | 具名、有版本、有时间戳 | `feature_rsi_14` |
| **因子** | 标准化后的 Alpha 信号 | 包含 PIT、有 exposures | `factor_momentum_20` |

**多输出技术指标处理**:

MACD 等多输出指标拆分为独立单输出表达式：

```python
# 不采用: macd(close, 12, 26, 9) 返回三列
# 采用: 三个独立表达式
macd_dif = "ts_ema(close, 12) - ts_ema(close, 26)"
macd_dea = "ts_ema(macd_dif, 9)"
macd_hist = "macd_dif - macd_dea"
```

**表达式库实现**:

```python
EXPRESSION_LIBRARY = {
    # 技术指标（带参数模板）
    "rsi": "100 - 100 / (1 + ts_mean(if_else(close > ts_delay(close, 1), ...), {period}) / ...)",
    "boll_upper": "ts_mean(close, {period}) + {k} * ts_std(close, {period})",

    # Alpha101 预定义
    "alpha_001": "cs_rank(ts_argmax(power(if_else(returns < 0, ...), 2), 5)) - 0.5",
}
```

**持久化策略**:

| 层级 | 持久化 | 存储位置 | 说明 |
|------|--------|---------|------|
| 原始数据 | ✅ | `market/`, `fundamental/` | T1 摄入 |
| 算子中间结果 | ❌ | — | 运行时计算 |
| 特征 | ✅ | `features/` | 单列输出 |
| 因子 | ✅ | `factors/` | 标准化 + PIT |
| 表达式定义 | ✅ | SQLite `derived_spec` | 元数据 |
| 预定义表达式库 | ✅ | YAML/JSON 配置 | 随代码版本 |

**业界对标**:

| 平台 | 策略 | Ditto 选择 |
|------|------|-----------|
| WorldQuant Brain | 无区分，都是表达式 | ✓ 类似 |
| Qlib | 技术指标与表达式分离 | ✗ 表达能力受限 |
| BigQuant | 算子 + 因子两级 | ✓ 采用此方案 |
| TA-Lib | 纯技术指标库 | 作为参考实现 |

---

### ADR-004: 表达式语法与数据引用设计

**状态**: 已决策（2026-03-04）

**背景**:

表达式引擎需要统一的语法来引用：
1. 原始数据列（市场行情、基本面、资金流向等）
2. 已计算的特征（技术指标如 RSI、MACD）
3. 已计算的因子（标准化 Alpha 信号）

核心挑战是避免列名冲突、保持可读性、与业界实践一致。

**决策**:

#### 1. 原始数据列：数据集限定语法

```python
# 格式: {dataset}.{column}
market.close           # 行情收盘价
market.volume          # 成交量
fund.pe_ttm            # 基金PE
balance.total_assets   # 资产负债表总资产
income.net_profit      # 利润表净利润
```

**理由**：
- 明确消除歧义，避免多数据集列名冲突
- 符合 SQL `table.column` 习惯
- 支持编译期列存在性校验

#### 2. 特征/因子引用：统一 `@` 前缀 + 命名约定

```python
# 特征引用（技术指标、基础特征）
@rsi_14                # RSI(14)
@macd_dif              # MACD DIF 线
@boll_upper_20         # 布林上轨(20)
@volatility_20         # 20日波动率

# 因子引用（Alpha信号，带 alpha_ 前缀）
@alpha_momentum_12m    # 12月动量因子
@alpha_value_pe        # 价值因子
@alpha_001             # WorldQuant Alpha001
@alpha_reversal_5d     # 5日反转因子
```

**命名约定**：

| 类型 | 命名规则 | 示例 |
|------|---------|------|
| 技术指标 | `{indicator}_{params}` | `rsi_14`, `macd_dif`, `atr_14` |
| 基础特征 | `{domain}_{metric}` | `fund_size`, `liquidity_20d` |
| 因子 | `alpha_{style}_{window}` 或 `alpha_{seq}` | `alpha_momentum_12m`, `alpha_001` |

**理由**：
- 统一 `@` 前缀：简化解析，单一解析路径
- `alpha_` 前缀：业界通用做法（WorldQuant、BigQuant），名称自解释
- 无需记忆双符号：避免 `@` vs `#` 的认知负担
- IDE 友好：易于语法高亮和自动补全

#### 3. 字面量与运算符

```python
# 数值字面量
42                     # 整数
3.14                   # 浮点数
-0.5                   # 负数

# 算术运算符
market.close * 1.02    # 乘法
market.close + market.high  # 加法
(market.high - market.low) / market.close  # 除法

# 比较运算符
market.close > market.open  # 大于
market.volume >= 1000000    # 大于等于

# 逻辑运算符
and  or  not           # 逻辑与、或、非
```

#### 4. 完整表达式示例

```python
# 简单因子
ts_rank(market.close, 20)

# 复合表达式
cs_rank(ts_delta(market.close, 5)) + @rsi_14

# 带特征依赖的因子
cs_zscore(@alpha_momentum_12m + @alpha_value_pe)

# Alpha101 风格
cs_rank(ts_argmax(power(if_else(market.returns < 0, market.stddev, market.close), 2), 5)) - 0.5
```

**语法定义（EBNF）**：

```ebnf
expression     = term (("+" | "-") term)*
term           = factor (("*" | "/") factor)*
factor         = unary | primary
unary          = ("-" | "not") factor
primary        = literal
               | column_ref
               | feature_ref
               | call_expr
               | "(" expression ")"

column_ref     = identifier "." identifier    # dataset.column
feature_ref    = "@" identifier                # @feature_id
call_expr      = identifier "(" arg_list? ")"
arg_list       = expression ("," expression)*
identifier     = [a-zA-Z_][a-zA-Z0-9_]*
literal        = NUMBER | STRING
```

**编译期校验**：

1. 列引用存在性检查（基于 Catalog schema）
2. 特征/因子存在性检查（基于 derived_spec 表）
3. 算子签名匹配
4. 类型兼容性检查

**业界对标**：

| 平台 | 列引用 | 特征引用 | Ditto 选择 |
|------|--------|---------|-----------|
| WorldQuant Brain | `close` | 不支持 | ✗ 列名冲突风险 |
| Qlib | `$close` | 不支持 | ⚠️ 符号负担 |
| BigQuant | `close` | `factor_xxx` | ✓ 类似 |
| Feathr | `entity.feature` | `@feature` | ✓ 类似 |

---

### ADR-005: 首批特征与因子清单

**状态**: 已决策（2026-03-04）

**首批特征清单**（Phase 0）:

#### A. 技术指标特征（12 个核心指标）

| 特征 ID | 表达式 | 类型 | lookback | 依赖 |
|---------|--------|------|----------|------|
| `rsi_{n}` | `100 - 100 / (1 + ts_mean(up, n) / ts_mean(down, n))` | momentum | n+1 | market.close |
| `ma_{n}` | `ts_mean(market.close, n)` | trend | n | market.close |
| `ema_{n}` | `ts_ema(market.close, n)` | trend | n*2 | market.close |
| `macd_dif` | `ts_ema(market.close, 12) - ts_ema(market.close, 26)` | trend | 52 | market.close |
| `macd_dea` | `ts_ema(@macd_dif, 9)` | trend | 70 | @macd_dif |
| `macd_hist` | `@macd_dif - @macd_dea` | trend | 70 | @macd_dif, @macd_dea |
| `boll_upper_{n}` | `ts_mean(close, n) + 2 * ts_std(close, n)` | volatility | n | market.close |
| `boll_lower_{n}` | `ts_mean(close, n) - 2 * ts_std(close, n)` | volatility | n | market.close |
| `atr_{n}` | `ts_mean(@tr, n)` | volatility | n+1 | market.high/low/close |
| `volatility_{n}` | `ts_std(@returns_1, n)` | volatility | n+1 | market.close |
| `volume_ma_{n}` | `ts_mean(market.volume, n)` | volume | n | market.volume |
| `returns_{n}` | `ts_pct_change(market.close, n)` | trend | n+1 | market.close |

**常用参数值**: `n = {5, 10, 14, 20, 60}`

#### B. 基本面特征（8 个核心指标）

| 特征 ID | 表达式 | 类型 | PIT | 依赖 |
|---------|--------|------|-----|------|
| `pe_ttm` | `fund.pe_ttm` | value | Yes | fund.* |
| `pb_lf` | `fund.pb_lf` | value | Yes | fund.* |
| `ps_ttm` | `fund.ps_ttm` | value | Yes | fund.* |
| `debt_ratio` | `balance.total_liab / balance.total_assets` | quality | Yes | balance.* |
| `roe` | `income.net_profit / balance.total_equity` | quality | Yes | income.*, balance.* |
| `net_margin` | `income.net_profit / income.revenue` | quality | Yes | income.* |
| `asset_turnover` | `income.revenue / balance.total_assets` | quality | Yes | income.*, balance.* |
| `earnings_growth_yoy` | `(net_profit - delay(net_profit, 252)) / abs(...)` | growth | Yes | income.* |

#### C. Alpha 因子（10 个核心因子）

| 因子 ID | 表达式 | 家族 | 标准化 |
|---------|--------|------|--------|
| `alpha_momentum_1m` | `cs_rank(ts_pct_change(market.close, 20))` | momentum | rank→zscore |
| `alpha_momentum_12m` | `cs_rank(ts_mean(@returns_1, 250))` | momentum | rank→zscore |
| `alpha_reversal_1w` | `cs_rank(-ts_pct_change(market.close, 5))` | momentum | rank→zscore |
| `alpha_value_pe` | `cs_rank(-fund.pe_ttm)` | value | rank→zscore |
| `alpha_value_pb` | `cs_rank(-fund.pb_lf)` | value | rank→zscore |
| `alpha_quality_roe` | `cs_rank(income.net_profit / balance.total_equity)` | quality | rank→zscore |
| `alpha_quality_margin` | `cs_rank(income.net_profit / income.revenue)` | quality | rank→zscore |
| `alpha_volatility` | `cs_rank(-ts_std(@returns_1, 20))` | volatility | rank→zscore |
| `alpha_liquidity` | `cs_rank(ts_mean(market.volume, 20) / market.total_mv)` | size | rank→zscore |
| `alpha_001` | WorldQuant Alpha001 完整表达式 | composite | rank→zscore |

#### D. 计算优先级（DAG 拓扑序）

```
P1: 原始数据摄入 (market.*, fund.*, balance.*, income.*)
    ↓
P2: 1日延迟计算 (@returns_1, @tr)
    ↓
P3: 短周期指标 (@ma_5, @ema_12, @ema_26, @volume_ma_5)
    ↓
P4: 中周期指标 (@rsi_14, @atr_14, @boll_*, @volatility_20)
    ↓
P5: 二级依赖 (@macd_dif → @macd_dea → @macd_hist)
    ↓
P6: Alpha 因子 (@alpha_*)
    ↓
P7: 组合因子 (@alpha_value_combo, etc.)
```

---

### ADR-006: 增量计算策略

**状态**: 已决策（2026-03-04）

#### 子问题 1：Watermark 管理策略

**决策**: **混合方案** - 核心因子单一 Watermark，非核心因子 Gap 容忍

**核心设计**:

```python
@dataclass
class WatermarkState:
    """Watermark 状态"""
    entity_type: str           # "feature" | "factor"
    entity_id: str             # "rsi_14"
    version: int               # 1

    watermark: date            # 最新成功日期
    coverage_start: date       # 最早覆盖日期

    # 仅非核心因子使用
    coverage_gaps: list[str] | None  # ["2026-01-15", "2026-02-20:2026-02-22"]

    # 元信息
    last_run_id: str
    updated_at: datetime


@dataclass
class EntityConfig:
    """实体配置"""
    entity_id: str
    is_critical: bool          # True = 核心因子，不允许 gap

    @property
    def allow_gaps(self) -> bool:
        return not self.is_critical
```

**分类标准**:

| 类型 | is_critical | Watermark 策略 | 失败处理 |
|------|-------------|---------------|---------|
| 核心 Alpha 因子 | `True` | 单一，无 gap | 立即重试，阻塞下游 |
| 技术指标特征 | `False` | gap 容忍 | 记录 gap，继续推进 |
| 基本面特征 | `False` | gap 容忍 | 记录 gap，继续推进 |
| 非核心因子 | `False` | gap 容忍 | 记录 gap，继续推进 |

**核心因子定义**（首批）:
- `alpha_momentum_12m` - 核心动量因子
- `alpha_value_pe` - 核心价值因子
- `alpha_quality_roe` - 核心质量因子

**业界对标**:

| 平台 | 策略 | Ditto 选择 |
|------|------|-----------|
| Flink | 单一 Watermark + 丢弃延迟 | 借鉴单一性 |
| BigQuant | 因子级独立 | 借鉴分级管理 |
| **Ditto** | **核心无 gap + 非核心有 gap** | **混合方案** |

#### 子问题 2：Lookback 预热数据加载

**决策**: **混合策略** - 有交易日历用精确回退，无日历用保守估计

**核心设计**:

```python
@dataclass
class LookbackConfig:
    """Lookback 计算配置"""
    safety_factor: float = 1.5      # 无日历时：lookback * 1.5
    max_warmup_days: int = 365      # 最大预热天数（防止异常）


def compute_compute_start(
    target: date,
    lookback: int,
    calendar: TradingCalendar | None = None,
    config: LookbackConfig = LookbackConfig(),
) -> date:
    """
    计算预热开始日期

    Args:
        target: 目标开始日期
        lookback: 表达式分析得出的 lookback 值
        calendar: 交易日历（可选）
        config: 配置参数

    Returns:
        计算开始日期（含预热）
    """
    if calendar is not None:
        # 有日历：精确回退
        start = calendar.lookback(target, lookback)
    else:
        # 无日历：保守估计
        start = target - timedelta(days=int(lookback * config.safety_factor))

    # 边界保护
    return max(start, target - timedelta(days=config.max_warmup_days))
```

**交易日历依赖**:

| 阶段 | 策略 | 说明 |
|------|------|------|
| Phase 0 | 保守估计 | 无日历依赖，快速启动 |
| Phase 1 | 引入日历 | 参考 Qlib 日历数据，补充缺失市场 |
| Phase 2 | 精确回退 | 全市场覆盖后默认使用精确回退 |

**交易日历数据源**:
- Qlib 内置日历：A股、美股、港股等主要市场
- 自建日历：通过 T1 摄入 trade_calendar 表

**业界对标**:

| 平台 | 策略 | Ditto 选择 |
|------|------|-----------|
| DolphinDB | 内置日历，精确回退 | Phase 2 目标 |
| Qlib | `calendar.shift()` 精确 | 借鉴日历数据 |
| Pandas/Polars | 用户自行处理 | Phase 0 保守估计 |
| **Ditto** | **混合策略** | **渐进式优化** |

#### 子问题 3：Invalidation 扩展规则

**决策**: **分级回补** - 核心因子立即重算，非核心延迟处理

**核心设计**:

```python
@dataclass
class InvalidationConfig:
    """失效处理配置"""
    critical_immediate: bool = True          # 核心因子立即重算
    non_critical_delay_hours: int = 24       # 非核心延迟 24 小时
    ts_lookback_extend: bool = True          # TS 因子向后扩展
    cs_full_day: bool = True                 # CS 因子整日失效


@dataclass
class AffectedRange:
    """受影响范围"""
    start: date
    end: date
    scope: Literal["full_day", "instrument_only"]  # 整日/仅标的


def compute_affected_range(
    change_date: date,
    lookback: int,
    requires_full_day: bool,
    watermark: date,
    config: InvalidationConfig = InvalidationConfig(),
) -> AffectedRange:
    """计算受影响的日期范围"""
    if requires_full_day:
        # CS 因子：整日失效（所有标的）
        return AffectedRange(
            start=change_date,
            end=change_date,
            scope="full_day"
        )
    else:
        # TS 因子：向后扩展 lookback 天
        end_date = min(change_date + timedelta(days=lookback), watermark)
        return AffectedRange(
            start=change_date,
            end=end_date,
            scope="instrument_only"
        )
```

**分级处理流程**:

```
源数据变更（market.close 2026-01-15 修正）
    │
    ├─ 核心因子（is_critical=True）
    │   ├─ 立即触发重算
    │   ├─ 阻塞下游依赖
    │   └─ 失败则告警+重试
    │
    └─ 非核心因子（is_critical=False）
        ├─ 写入 derived_invalidation 表（status=pending）
        ├─ 继续推进 watermark
        └─ 下次增量时处理 / 批量回补
```

**Invalidation 表设计**:

```sql
CREATE TABLE IF NOT EXISTS derived_invalidation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 来源
    source_domain TEXT NOT NULL,       -- "market"
    source_dataset TEXT NOT NULL,      -- "daily"
    change_date TEXT NOT NULL,         -- "2026-01-15"
    snapshot_id TEXT,

    -- 受影响实体
    entity_type TEXT NOT NULL,         -- "feature" | "factor"
    entity_id TEXT NOT NULL,           -- "alpha_momentum_20"

    -- 失效范围
    affected_start TEXT NOT NULL,
    affected_end TEXT NOT NULL,
    scope TEXT NOT NULL,               -- "full_day" | "instrument_only"

    -- 处理状态
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | done
    priority INTEGER DEFAULT 0,        -- 核心因子优先级更高
    created_at TEXT NOT NULL,
    processed_at TEXT
);

-- 索引
CREATE INDEX idx_invalidation_status ON derived_invalidation(status, priority);
CREATE INDEX idx_invalidation_entity ON derived_invalidation(entity_type, entity_id);
```

**业界对标**:

| 平台 | 策略 | 级联 | Ditto 选择 |
|------|------|------|-----------|
| Delta Lake | 手动触发 | 无 | ✗ 维护成本高 |
| dbt | lineage + 增量 | 有 | 借鉴 lineage |
| Feathr | 显式 API | 有 | 借鉴显式失效 |
| BigQuant | 自动级联 | 有 | 借鉴分级处理 |
| **Ditto** | **分级回补** | **有** | **核心立即 + 非核心延迟** |

#### 子问题 4：原子性与失败恢复

**决策**: **幂等覆写 + 分区级 Checkpoint** 混合方案

**核心设计**:

```python
@dataclass
class PartitionCheckpoint:
    """分区级 Checkpoint"""
    entity_type: str
    entity_id: str
    partition_key: str      # "2026-02" 或 "2026"
    status: Literal["pending", "done", "failed"]
    rows_written: int
    checksum: str
    completed_at: datetime


def materialize_partition(
    entity_id: str,
    partition_key: str,
    force: bool = False,
) -> MaterializeResult:
    """
    单分区物化（幂等）

    Args:
        entity_id: 实体 ID
        partition_key: 分区键
        force: 强制重算（忽略 checkpoint）

    Returns:
        MaterializeResult
    """
    # 1. 检查 checkpoint
    if not force:
        checkpoint = load_checkpoint(entity_id, partition_key)
        if checkpoint and checkpoint.status == "done":
            return MaterializeResult(skipped=True, reason="already_done")

    # 2. 获取锁
    with acquire_lock(f"derived/{entity_id}/{partition_key}"):
        # 3. 计算
        df = compute_partition(entity_id, partition_key)

        if df.is_empty():
            return MaterializeResult(skipped=True, reason="no_data")

        # 4. 写临时目录
        temp_path = write_temp(df, entity_id, partition_key)

        # 5. 校验
        validate(df)

        # 6. 原子替换
        target_path = get_target_path(entity_id, partition_key)
        atomic_replace(temp_path, target_path)

        # 7. 更新 Catalog（SQLite 事务）
        with catalog.transaction():
            catalog.upsert_partition(
                entity_id=entity_id,
                partition_key=partition_key,
                rows=len(df),
                checksum=compute_checksum(df),
            )
            catalog.update_checkpoint(
                entity_id=entity_id,
                partition_key=partition_key,
                status="done",
            )

        return MaterializeResult(
            entity_id=entity_id,
            partition_key=partition_key,
            rows_written=len(df),
        )
```

**原子性保证**:

| 组件 | 作用 | 保证机制 |
|------|------|---------|
| FileLock | 防止并发写 | 互斥锁 |
| 临时目录 | 隔离计算结果 | 无效数据不可见 |
| atomic_replace | 原子替换 | 文件系统 rename |
| SQLite 事务 | Catalog 更新 | ACID |

**失败恢复流程**:

```
场景：2026-02-20 成功，2026-02-21 失败

1. 检查 checkpoint：
   - 2026-02 已完成 ✓ → 跳过
   - 2026-03 待处理 → 执行

2. 重跑时（幂等）：
   - 跳过已完成分区（checkpoint.status = "done"）
   - 从失败分区开始

3. watermark 更新：
   - 基于已完成的连续分区
   - 非连续 gap 记录到 coverage_gaps（非核心因子）
```

**Checkpoint 表设计**:

```sql
CREATE TABLE IF NOT EXISTS derived_checkpoint (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    status TEXT NOT NULL,              -- pending | done | failed
    rows_written INTEGER DEFAULT 0,
    checksum TEXT,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (entity_type, entity_id, partition_key)
);
```

**业界对标**:

| 平台 | 策略 | 原子性保证 | Ditto 选择 |
|------|------|-----------|-----------|
| Flink | Checkpoint + 2PC | 强一致 | 借鉴 checkpoint |
| Spark | WAL | 强一致 | 借鉴进度记录 |
| Delta Lake | ACID 事务 | 强一致 | 借鉴事务 |
| dbt | 幂等覆写 | 最终一致 | ✓ 采用幂等 |
| BigQuant | 分区级提交 | 分区原子 | ✓ 采用分区级 |
| **Ditto** | **幂等 + Checkpoint** | **分区原子** | **混合方案** |

---

### ADR-007: 算子完整清单

**状态**: 已决策（2026-03-04）

#### P0 核心算子（Phase 0 必须实现）

**TS 滚动聚合（8 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_mean` | `ts_mean(x, n)` | 滚动均值 | n |
| `ts_sum` | `ts_sum(x, n)` | 滚动求和 | n |
| `ts_std` | `ts_std(x, n)` | 滚动标准差 | n |
| `ts_var` | `ts_var(x, n)` | 滚动方差 | n |
| `ts_max` | `ts_max(x, n)` | 滚动最大值 | n |
| `ts_min` | `ts_min(x, n)` | 滚动最小值 | n |
| `ts_count` | `ts_count(x, n)` | 滚动计数 | n |
| `ts_median` | `ts_median(x, n)` | 滚动中位数 | n |

**TS 延迟/变化（4 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_delay` | `ts_delay(x, n)` | n 期延迟 | n |
| `ts_delta` | `ts_delta(x, n)` | n 期变化 | n |
| `ts_pct_change` | `ts_pct_change(x, n)` | n 期变化率 | n |
| `ts_diff` | `ts_diff(x, n)` | 差分 | 1 |

**TS 排名（3 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_rank` | `ts_rank(x, n)` | 窗口内排名 | n |
| `ts_argmax` | `ts_argmax(x, n)` | 最大值位置 | n |
| `ts_argmin` | `ts_argmin(x, n)` | 最小值位置 | n |

**TS 相关（2 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_corr` | `ts_corr(x, y, n)` | 滚动相关系数 | n |
| `ts_cov` | `ts_cov(x, y, n)` | 滚动协方差 | n |

**CS 排名/标准化（5 个）**:

| 算子 | 签名 | 说明 | requires_full_day |
|------|------|------|-------------------|
| `cs_rank` | `cs_rank(x)` | 截面排名 | True |
| `cs_scale` | `cs_scale(x)` | 截面缩放到 [0,1] | True |
| `cs_zscore` | `cs_zscore(x)` | 截面标准化 | True |
| `cs_demean` | `cs_demean(x)` | 截面去均值 | True |
| `cs_winsorize` | `cs_winsorize(x, lower, upper)` | 截面缩尾 | True |

**标量-数学（6 个）**:

| 算子 | 签名 | 说明 |
|------|------|------|
| `abs` | `abs(x)` | 绝对值 |
| `log` | `log(x)` | 自然对数 |
| `exp` | `exp(x)` | 指数 |
| `sqrt` | `sqrt(x)` | 平方根 |
| `sign` | `sign(x)` | 符号 |
| `power` | `power(x, n)` | 幂运算 |

**标量-比较/逻辑（4 个）**:

| 算子 | 签名 | 说明 |
|------|------|------|
| `max2` | `max2(x, y)` | 两数最大 |
| `min2` | `min2(y)` | 两数最小 |
| `clip` | `clip(x, lower, upper)` | 裁剪 |
| `if_else` | `if_else(cond, x, y)` | 条件选择 |

**P0 总计**: 32 个算子

#### P1 增强算子（Phase 1 实现）

**TS 加权（4 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_ema` | `ts_ema(x, n)` | 指数移动平均 | n * 2 |
| `ts_wma` | `ts_wma(x, n)` | 加权移动平均 | n |
| `ts_decay_linear` | `ts_decay_linear(x, n)` | 线性衰减加权 | n |
| `ts_decay_exp` | `ts_decay_exp(x, n)` | 指数衰减加权 | n |

**TS 分位数（3 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_quantile` | `ts_quantile(x, n, q)` | 滚动分位数 | n |
| `ts_qtlu` | `ts_qtlu(x, n, q)` | 滚动上分位数 | n |
| `ts_qtld` | `ts_qtld(x, n, q)` | 滚动下分位数 | n |

**TS 高阶统计（2 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_skew` | `ts_skew(x, n)` | 滚动偏度 | n |
| `ts_kurt` | `ts_kurt(x, n)` | 滚动峰度 | n |

**CS 分组（3 个）**:

| 算子 | 签名 | 说明 | requires_full_day |
|------|------|------|-------------------|
| `group_rank` | `group_rank(x, group)` | 组内排名 | True |
| `group_zscore` | `group_zscore(x, group)` | 组内标准化 | True |
| `group_demean` | `group_demean(x, group)` | 组内去均值 | True |

**P1 总计**: 12 个算子

#### P2 高级算子（Phase 2 实现）

**TS 复杂聚合（4 个）**:

| 算子 | 签名 | 说明 | lookback |
|------|------|------|----------|
| `ts_prod` | `ts_prod(x, n)` | 滚动乘积 | n |
| `ts_av_diff` | `ts_av_diff(x, n)` | 与均值差 | n |
| `ts_mean_return` | `ts_mean_return(x, n, lag)` | 平均收益 | n + lag |
| `ts_regression` | `ts_regression(y, x, n)` | 滚动回归 | n |

**CS 复杂操作（4 个）**:

| 算子 | 签名 | 说明 | requires_full_day |
|------|------|------|-------------------|
| `cs_regression` | `cs_regression(y, x)` | 截面回归残差 | True |
| `cs_neutralize` | `cs_neutralize(x, groups)` | 多组中性化 | True |
| `cs_normalize` | `cs_normalize(x)` | L2 归一化 | True |
| `cs_percentile` | `cs_percentile(x)` | 百分位排名 | True |

**P2 总计**: 8 个算子

#### 算子总计

| 优先级 | 数量 | 说明 |
|--------|------|------|
| P0 | 32 | Phase 0 核心，支持基础因子计算 |
| P1 | 12 | Phase 1 增强，支持 Alpha101 |
| P2 | 8 | Phase 2 高级，支持复杂策略 |
| **合计** | **52** | 全功能覆盖 |

---

### ADR-008: 标准化管线设计

**状态**: 已决策（2026-03-04）

**决策**: **可配置管线，默认 WorldQuant 风格（Rank → ZScore）**

#### 默认管线（WorldQuant 风格）

```python
DEFAULT_FACTOR_PIPELINE = [
    NormalizationStage(method="cs_rank"),
    NormalizationStage(method="cs_zscore"),
]
```

**理由**：
1. 业界主流：70%+ 量化平台采用
2. 鲁棒高效：Rank 消除极端值影响
3. 实证有效：WorldQuant Alpha101 验证

#### 预设管线

| 预设名称 | 管线 | 适用场景 |
|----------|------|---------|
| `default` | Rank → ZScore | Alpha 因子（默认） |
| `fundamental` | Winsorize → Rank → ZScore | 基本面因子（有极端异常值） |
| `institutional` | Rank → ZScore → Neutralize | 机构级因子（需行业中性化） |
| `none` | 无标准化 | 技术指标（保留原始值） |

#### 配置模型

```python
@dataclass
class NormalizationStage:
    """标准化阶段"""
    method: Literal["winsorize", "cs_rank", "cs_zscore", "cs_demean", "neutralize"]
    params: dict[str, object] = Field(default_factory=dict)


@dataclass
class NormalizationConfig:
    """标准化配置"""
    pipeline_preset: Literal["default", "fundamental", "institutional", "none"] = "default"
    custom_stages: list[NormalizationStage] | None = None
    winsorize_sigma: float = 3.0
    neutralize_groups: list[str] = Field(default_factory=lambda: ["industry"])

    def get_pipeline(self) -> list[NormalizationStage]:
        """获取标准化管线"""
        if self.custom_stages is not None:
            return self.custom_stages

        presets = {
            "default": [
                NormalizationStage(method="cs_rank"),
                NormalizationStage(method="cs_zscore"),
            ],
            "fundamental": [
                NormalizationStage(method="winsorize", params={"sigma": self.winsorize_sigma}),
                NormalizationStage(method="cs_rank"),
                NormalizationStage(method="cs_zscore"),
            ],
            "institutional": [
                NormalizationStage(method="cs_rank"),
                NormalizationStage(method="cs_zscore"),
                NormalizationStage(method="neutralize", params={"groups": self.neutralize_groups}),
            ],
            "none": [],
        }
        return presets[self.pipeline_preset]
```

#### 因子输出 Schema

```python
factor_output_schema = {
    "instrument_id": str,       # 标的 ID
    "trade_date": date,         # 交易日期
    "factor_id": str,           # 因子 ID
    "raw_value": float,         # 原始值（标准化前）
    "exposure": float,          # 标准化后的因子暴露
    "effective_from": date,     # PIT 生效日期
    "effective_to": date | None,# PIT 失效日期（null = 当前有效）
    "spec_hash": str,           # Spec 哈希
    "run_id": str,              # 运行 ID
}
```

**业界对标**:

| 平台 | 默认管线 | Ditto 选择 |
|------|---------|-----------|
| WorldQuant Brain | Rank → ZScore | ✓ 采用 |
| Barra | Winsorize → ZScore → Neutralize | 可选 |
| Qlib | ZScore | Rank 更鲁棒 |
| BigQuant | Rank → ZScore | ✓ 采用 |
| **Ditto** | **Rank → ZScore** | **业界主流** |

---

### ADR-009: 特征/因子摄取完整流程

**状态**: 已决策（2026-03-04）

#### 处理模式：批量 + 增量（预留流式）

**核心决策**: 采用 **"批量 + 增量"** 双模式架构，预留流式扩展

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Ditto 处理模式                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     批量模式（Full Mode）                             │    │
│  │                                                                      │    │
│  │  适用场景：                                                           │    │
│  │  - 新因子首次上线（cold start）                                       │    │
│  │  - 历史数据回算（backfill）                                           │    │
│  │  - Spec 表达式变更（spec_hash 变化）                                  │    │
│  │                                                                      │    │
│  │  特点：                                                               │    │
│  │  - 从指定开始日期全量计算，忽略 watermark                              │    │
│  │  - 结果完整但耗时较长                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     增量模式（Incremental Mode）                      │    │
│  │                                                                      │    │
│  │  适用场景：                                                           │    │
│  │  - 日常 T+1 更新（daily run）                                         │    │
│  │  - 数据修正后局部回补（基于 invalidation）                             │    │
│  │  - 快速补数据（patch）                                                │    │
│  │                                                                      │    │
│  │  特点：                                                               │    │
│  │  - 基于 watermark 增量，lookback 预热                                 │    │
│  │  - 效率高，日常默认使用                                                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     流式模式（Streaming）- Phase 2+ 预留              │    │
│  │                                                                      │    │
│  │  适用场景：                                                           │    │
│  │  - 分钟级因子（intraday）                                             │    │
│  │  - 实时信号（real-time signal）                                       │    │
│  │  - Tick 级计算（high-frequency）                                      │    │
│  │                                                                      │    │
│  │  特点：                                                               │    │
│  │  - 事件驱动，低延迟                                                   │    │
│  │  - 架构已预留扩展点                                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**模式选择决策表**：

| 场景 | 模式 | 命令示例 |
|------|------|---------|
| 新因子首次上线 | 批量 | `ditto materialize --id alpha_new --mode full --start 2020-01-01` |
| 日常 T+1 更新 | 增量 | `ditto materialize --id alpha_001 --mode incremental` |
| 历史回算 | 批量 | `ditto materialize --id alpha_001 --mode full --start 2018-01-01` |
| 数据修正后回补 | 增量 | 自动触发（基于 invalidation） |
| Spec 变更 | 批量 | `ditto materialize --id alpha_001 --mode full --force` |

**业界对标**：

| 平台 | 架构 | 批量 | 增量 | 流式 |
|------|------|------|------|------|
| WorldQuant Brain | Lambda | ✓ | ✓ | ✓ |
| BigQuant | 批量+增量 | ✓ | ✓ | ✗ |
| Qlib | 批量为主 | ✓ | 有限 | ✗ |
| DolphinDB | 统一引擎 | ✓ | ✓ | ✓ |
| **Ditto** | **批量+增量+流式（流批一体）** | ✓ | ✓ | Phase 2+ |

> **流式模式详细设计**: 参见 [ADR-011: 流式模式架构设计](#adr-011-流式模式架构设计streaming-mode)

#### 端到端流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           T1 原始数据摄入完成                                  │
│                    market.daily, fundamental.*, capital.*                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T2 特征物化（Feature Materialization）                  │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 解析 Spec → 编译 Expression → 分析依赖/lookback/requires_full_day   │   │
│  │ 2. 加载输入数据（source domains + 依赖 features）                       │   │
│  │ 3. 执行 Polars 计算                                                    │   │
│  │ 4. 写入 Parquet（year 分区）                                           │   │
│  │ 5. 更新 Catalog（checkpoint + state）                                  │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│  输出: features/technical/indicators_narrow/{year}.parquet                   │
│        features/fundamental/{feature_id}/{year}.parquet                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T3 因子物化（Factor Materialization）                   │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 解析 Spec → 编译 Expression → 分析依赖                              │   │
│  │ 2. 加载输入数据（source domains + 依赖 features + 依赖 factors）        │   │
│  │ 3. 执行 Polars 计算 → raw_value                                        │   │
│  │ 4. 应用标准化管线（Rank → ZScore）→ exposure                            │   │
│  │ 5. PIT 规整（effective_from/effective_to）                             │   │
│  │ 6. 写入 Parquet（year 分区）                                           │   │
│  │ 7. 更新 Catalog                                                        │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│  输出: factors/factors_narrow/{year}.parquet                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T4 发布（Publication）                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 校验数据质量（null_rate, 分布检查）                                  │   │
│  │ 2. 更新 latest 指针                                                    │   │
│  │ 3. 生成报告（coverage, stats）                                         │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 增量计算流程

```python
def incremental_materialize(
    entity_id: str,
    entity_type: Literal["feature", "factor"],
    request_start: date,
    request_end: date,
) -> MaterializeResult:
    """增量物化流程"""

    # 1. 加载 Spec
    spec = catalog.load_spec(entity_type, entity_id)
    analysis = analyze_expression(spec.expression)

    # 2. 计算 compute_start（含 lookback 预热）
    state = catalog.load_state(entity_type, entity_id)
    watermark = state.watermark
    compute_start = max(
        request_start,
        compute_lookback_start(request_start, analysis.lookback, calendar)
    )

    # 3. 检查 invalidation
    invalidations = catalog.load_pending_invalidations(entity_id)
    if invalidations:
        compute_start = min(compute_start, min(i.affected_start for i in invalidations))

    # 4. 加载输入数据
    input_df = load_input_data(
        spec.dependencies,
        start=compute_start,
        end=request_end,
    )

    # 5. 执行计算
    if entity_type == "factor":
        # 因子：计算 + 标准化 + PIT
        raw_df = execute_expression(spec.expression, input_df)
        normalized_df = apply_normalization(raw_df, spec.normalization_config)
        result_df = apply_pit(normalized_df, spec.pit_config)
    else:
        # 特征：仅计算
        result_df = execute_expression(spec.expression, input_df)

    # 6. 写入（按分区）
    for partition_key in get_partition_keys(request_start, request_end):
        partition_df = result_df.filter(pl.col("trade_date").is_in_partition(partition_key))

        with acquire_lock(f"derived/{entity_id}/{partition_key}"):
            # 写临时目录 → 原子替换
            temp_path = write_temp(partition_df, entity_id, partition_key)
            atomic_replace(temp_path, get_target_path(entity_id, partition_key))

            # 更新 Catalog
            with catalog.transaction():
                catalog.upsert_partition(entity_id, partition_key, len(partition_df))
                catalog.update_checkpoint(entity_id, partition_key, "done")

    # 7. 更新 watermark
    catalog.update_watermark(entity_id, request_end)

    return MaterializeResult(
        entity_id=entity_id,
        coverage_start=compute_start,
        coverage_end=request_end,
        rows_written=len(result_df),
    )
```

#### 与现有摄取流程集成

```python
# 现有: daily_ingestion_flow
@flow(name="daily_ingestion")
def daily_ingestion_flow(trade_date: date):
    T0_meta_sync()
    T1_market_daily(trade_date)
    T1_fundamental(trade_date)
    # ...

# 新增: daily_materialization_flow
@flow(name="daily_materialization")
def daily_materialization_flow(trade_date: date, mode: Literal["full", "incremental"]):
    # Phase 1: 特征物化
    for feature_spec in FEATURE_SPECS:
        materialize_feature(feature_spec, trade_date, mode)

    # Phase 2: 因子物化（依赖特征）
    for factor_spec in FACTOR_SPECS:
        materialize_factor(factor_spec, trade_date, mode)

    # Phase 3: 发布
    publish_derived(trade_date)

# 组合: daily_pipeline_flow
@flow(name="daily_pipeline")
def daily_pipeline_flow(trade_date: date):
    # 1. 摄取原始数据
    daily_ingestion_flow(trade_date)

    # 2. 物化特征/因子
    daily_materialization_flow(trade_date, mode="incremental")
```

---

### ADR-010: Catalog 完整表结构

**状态**: 已决策（2026-03-04）

#### 表结构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    SQLite Catalog 表结构                         │
├─────────────────────────────────────────────────────────────────┤
│  derived_spec          - Spec 定义（版本化）                      │
│  derived_state         - 运行时状态（watermark, gaps）            │
│  derived_run           - 运行记录（每次物化）                      │
│  derived_partition     - 分区级元数据                             │
│  derived_checkpoint    - 分区级 Checkpoint（幂等）                 │
│  derived_invalidation  - 失效记录（待处理）                        │
│  derived_dependency    - 依赖关系（lineage）                       │
└─────────────────────────────────────────────────────────────────┘
```

#### 详细表结构

```sql
-- ============================================================
-- 1. derived_spec: Spec 定义（版本化）
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_spec (
    entity_type TEXT NOT NULL,         -- "feature" | "factor"
    entity_id TEXT NOT NULL,           -- "rsi_14", "alpha_momentum_12m"
    version INTEGER NOT NULL,          -- 版本号（从 1 开始）

    -- Spec 内容
    expression TEXT NOT NULL,          -- "ts_mean(market.close, 14)"
    spec_json TEXT NOT NULL,           -- 完整 Spec JSON
    spec_hash TEXT NOT NULL,           -- Spec 哈希（用于变更检测）

    -- 分析结果（编译时计算）
    lookback INTEGER NOT NULL DEFAULT 0,
    requires_full_day INTEGER NOT NULL DEFAULT 0,
    dependencies TEXT NOT NULL,        -- JSON: ["market.close", "@returns_1"]

    -- 配置
    normalization_preset TEXT DEFAULT 'default',
    pit_required INTEGER NOT NULL DEFAULT 0,
    is_critical INTEGER NOT NULL DEFAULT 0,

    -- 元信息
    engine_version TEXT NOT NULL DEFAULT 'v0',
    status TEXT NOT NULL DEFAULT 'active',  -- active | deprecated | archived
    created_at TEXT NOT NULL,
    created_by TEXT,

    PRIMARY KEY (entity_type, entity_id, version),
    UNIQUE (entity_type, entity_id, spec_hash)
);

CREATE INDEX idx_spec_hash ON derived_spec(spec_hash);
CREATE INDEX idx_spec_status ON derived_spec(status);

-- ============================================================
-- 2. derived_state: 运行时状态
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_state (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,

    -- 覆盖范围
    coverage_start TEXT,               -- 最早覆盖日期
    coverage_end TEXT,                 -- 最新覆盖日期
    watermark TEXT,                    -- 连续成功最晚日期

    -- Gap 管理（非核心因子）
    coverage_gaps TEXT,                -- JSON: ["2026-01-15", "2026-02-20:2026-02-22"]

    -- 运行信息
    latest_run_id TEXT,
    latest_run_status TEXT,            -- success | failed | running
    latest_run_at TEXT,

    -- 统计
    total_rows INTEGER DEFAULT 0,
    last_checksum TEXT,

    updated_at TEXT NOT NULL,

    PRIMARY KEY (entity_type, entity_id, version)
);

-- ============================================================
-- 3. derived_run: 运行记录（每次物化）
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_run (
    run_id TEXT PRIMARY KEY,           -- UUID

    -- 实体标识
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    spec_hash TEXT NOT NULL,

    -- 运行配置
    mode TEXT NOT NULL,                -- full | incremental
    request_start TEXT NOT NULL,
    request_end TEXT NOT NULL,
    compute_start TEXT NOT NULL,       -- 实际计算开始（含预热）
    compute_end TEXT NOT NULL,

    -- 状态
    status TEXT NOT NULL,              -- running | success | failed
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,

    -- 输入
    source_snapshot_id TEXT,           -- 输入数据快照
    input_partitions TEXT,             -- JSON: 读取的分区列表

    -- 输出
    partitions_written TEXT,           -- JSON: 写入的分区列表
    rows_written INTEGER DEFAULT 0,
    rows_skipped INTEGER DEFAULT 0,
    output_checksum TEXT,

    -- 错误
    error_message TEXT,
    error_stacktrace TEXT,

    -- 元信息
    triggered_by TEXT,                 -- manual | schedule | dependency
    parent_run_id TEXT                 -- 父运行（级联时）
);

CREATE INDEX idx_run_entity ON derived_run(entity_type, entity_id, version);
CREATE INDEX idx_run_status ON derived_run(status, started_at);
CREATE INDEX idx_run_time ON derived_run(started_at);

-- ============================================================
-- 4. derived_partition: 分区级元数据
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_partition (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    partition_key TEXT NOT NULL,       -- "2026" 或 "2026-02"

    -- 文件信息
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    row_count INTEGER NOT NULL,

    -- 校验
    checksum TEXT,

    -- 统计
    null_rate REAL,                    -- 空值率
    min_value TEXT,
    max_value TEXT,
    mean_value TEXT,
    std_value TEXT,

    -- 时间
    written_at TEXT NOT NULL,
    run_id TEXT NOT NULL,

    PRIMARY KEY (entity_type, entity_id, version, partition_key)
);

CREATE INDEX idx_partition_run ON derived_partition(run_id);

-- ============================================================
-- 5. derived_checkpoint: 分区级 Checkpoint（幂等）
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_checkpoint (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    partition_key TEXT NOT NULL,

    status TEXT NOT NULL,              -- pending | done | failed
    rows_written INTEGER DEFAULT 0,
    checksum TEXT,
    error_message TEXT,

    started_at TEXT,
    completed_at TEXT,

    PRIMARY KEY (entity_type, entity_id, partition_key)
);

-- ============================================================
-- 6. derived_invalidation: 失效记录
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_invalidation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 来源
    source_domain TEXT NOT NULL,
    source_dataset TEXT NOT NULL,
    change_date TEXT NOT NULL,
    source_snapshot_id TEXT,

    -- 受影响实体
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,

    -- 失效范围
    affected_start TEXT NOT NULL,
    affected_end TEXT NOT NULL,
    scope TEXT NOT NULL,               -- full_day | instrument_only

    -- 处理状态
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    processed_run_id TEXT
);

CREATE INDEX idx_invalidation_status ON derived_invalidation(status, priority);
CREATE INDEX idx_invalidation_entity ON derived_invalidation(entity_type, entity_id);
CREATE INDEX idx_invalidation_source ON derived_invalidation(source_domain, change_date);

-- ============================================================
-- 7. derived_dependency: 依赖关系（Lineage）
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_dependency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 依赖方
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,

    -- 被依赖方
    dep_type TEXT NOT NULL,            -- source | feature | factor
    dep_domain TEXT,                   -- source: "market", "fundamental"
    dep_column TEXT,                   -- source: "close"
    dep_entity_id TEXT,                -- feature/factor: "rsi_14"

    created_at TEXT NOT NULL,

    UNIQUE (entity_type, entity_id, version, dep_type, dep_domain, dep_column, dep_entity_id)
);

CREATE INDEX idx_dependency_entity ON derived_dependency(entity_type, entity_id);
CREATE INDEX idx_dependency_dep ON derived_dependency(dep_type, dep_entity_id);
```

#### 常用查询模式

```sql
-- 1. 查询待处理的失效记录（按优先级）
SELECT * FROM derived_invalidation
WHERE status = 'pending'
ORDER BY priority DESC, created_at ASC;

-- 2. 查询实体的下游依赖（级联失效）
SELECT entity_type, entity_id
FROM derived_dependency
WHERE dep_type = 'source' AND dep_domain = 'market' AND dep_column = 'close';

-- 3. 查询因子的完整 Lineage
WITH RECURSIVE lineage AS (
    SELECT entity_type, entity_id, dep_type, dep_entity_id, 1 AS depth
    FROM derived_dependency
    WHERE entity_id = 'alpha_momentum_12m'

    UNION ALL

    SELECT d.entity_type, d.entity_id, d.dep_type, d.dep_entity_id, l.depth + 1
    FROM derived_dependency d
    JOIN lineage l ON d.entity_id = l.dep_entity_id
    WHERE l.depth < 10
)
SELECT * FROM lineage;

-- 4. 查询运行历史（排障）
SELECT * FROM derived_run
WHERE entity_id = 'alpha_momentum_12m'
ORDER BY started_at DESC
LIMIT 10;

-- 5. 查询数据覆盖情况
SELECT entity_id, coverage_start, coverage_end, watermark,
       json_array_length(coverage_gaps) AS gap_count
FROM derived_state
WHERE entity_type = 'factor';
```

---

### ADR-011: 流式模式架构设计（Streaming Mode）

**状态**: 已决策（2026-03-04）

**背景**:

随着量化交易场景对实时性要求的提升，分钟级、Tick 级因子计算成为重要需求。DolphinDB、WorldQuant Brain 等平台已实现流批一体架构，支持"一套代码，两种执行模式"。Ditto 需要在 Phase 2+ 支持流式因子计算，同时确保与现有批量+增量架构的无缝集成。

#### 11.1 流式模式场景定义

| 场景 | 数据频率 | 延迟要求 | 典型因子 |
|------|---------|---------|---------|
| **分钟级因子** | 1min/5min/15min | < 100ms | 分钟动量、分钟波动率、资金流 |
| **实时信号** | Tick/Snapshot | < 10ms | 盘口失衡、大单监测、价格冲击 |
| **日内策略** | 秒级 | < 1s | 日内趋势、反转信号、量价背离 |
| **风控监控** | 实时 | < 50ms | 持仓风险、敞口监控、异常检测 |

#### 11.2 流批一体核心原则

**核心决策**: 采用 **"一套表达式，三种执行模式"** 架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Ditto 流批一体架构                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     用户层：因子表达式                                │    │
│  │                                                                      │    │
│  │   // 同一表达式，三种执行模式                                         │    │
│  │   expression = "ts_rank(cs_rank(close), 9) + rsi_14"                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     编译层：Pratt + Analyzer                          │    │
│  │                                                                      │    │
│  │   - Parser → AST                                                     │    │
│  │   - Analyzer → deps/lookback/requires_full_day                      │    │
│  │   - Codegen → 执行计划                                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│              ┌───────────────────────┼───────────────────────┐              │
│              ▼                       ▼                       ▼              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │   批量引擎       │    │   增量引擎       │    │   流式引擎       │         │
│  │                 │    │                 │    │                 │         │
│  │  - Polars 批处理 │    │  - Polars 增量  │    │  - 事件驱动     │         │
│  │  - 全量扫描      │    │  - lookback预热 │    │  - 状态维护     │         │
│  │  - T+1 场景      │    │  - watermark    │    │  - 增量更新     │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**业界对标**：

| 平台 | 流批一体策略 | 代码复用率 | Ditto 借鉴 |
|------|-------------|-----------|-----------|
| DolphinDB | `@state` 状态函数 + 响应式引擎 | 100% | ✓ 采用此方案 |
| WorldQuant Brain | 统一表达式引擎 | 100% | ✓ 参考架构 |
| BigQuant | 批量 + 流式分离 | ~60% | ✗ 维护成本高 |
| Qlib | 仅批量 | 0% | ✗ 无流式能力 |

#### 11.3 流式引擎架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        流式因子计算引擎                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     数据摄入层（Ingestion）                           │    │
│  │                                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │    │
│  │  │ Kafka/Redis  │  │ WebSocket    │  │ 文件回放     │               │    │
│  │  │ 实时数据流    │  │ 行情推送     │  │ 历史验证     │               │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │    │
│  │         │                 │                 │                        │    │
│  │         └─────────────────┼─────────────────┘                        │    │
│  │                           ▼                                          │    │
│  │                  ┌────────────────┐                                  │    │
│  │                  │  StreamTable   │  ← 统一流数据表                   │    │
│  │                  │  (内存队列)     │                                  │    │
│  │                  └────────┬───────┘                                  │    │
│  └───────────────────────────┼─────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     计算引擎层（Engines）                             │    │
│  │                                                                      │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │              TS 时间序列引擎（ReactiveStateEngine）            │   │    │
│  │  │                                                               │   │    │
│  │  │  - 按 instrument 分组                                         │   │    │
│  │  │  - 维护滑动窗口状态                                           │   │    │
│  │  │  - 支持: ts_mean, ts_rank, ts_delta, ts_corr, ...            │   │    │
│  │  │                                                               │   │    │
│  │  │  状态示例：                                                   │   │    │
│  │  │  - ts_mean(close, 20): 维护最近 20 个 close 值的队列          │   │    │
│  │  │  - ts_rank(volume, 10): 维护最近 10 个 volume 值及排名        │   │    │
│  └──────────────────────────────────────────────────────────────────────┘   │    │
│  │                              │                                       │    │
│  │                              ▼                                       │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │              CS 横截面引擎（CrossSectionalEngine）             │   │    │
│  │  │                                                               │   │    │
│  │  │  - 按时间点分组（全市场截面）                                  │   │    │
│  │  │  - 等待完整截面数据到达                                       │   │    │
│  │  │  - 支持: cs_rank, cs_zscore, cs_demean, ...                  │   │    │
│  │  │                                                               │   │    │
│  │  │  触发机制：                                                   │   │    │
│  │  │  - 时间窗口触发（每 X 秒）                                    │   │    │
│  │  │  - 完整度触发（N% 标的数据到达）                              │   │    │
│  └──────────────────────────────────────────────────────────────────────┘   │    │
│  │                              │                                       │    │
│  │                              ▼                                       │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │              标准化引擎（NormalizationEngine）                 │   │    │
│  │  │                                                               │   │    │
│  │  │  - Rank → ZScore 管线                                        │   │    │
│  │  │  - 行业中性化                                                 │   │    │
│  │  │  - 异常值处理                                                 │   │    │
│  └──────────────────────────────────────────────────────────────────────┘   │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     输出层（Output）                                  │    │
│  │                                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │    │
│  │  │ ResultTable  │  │ 持久化队列    │  │ 实时推送     │               │    │
│  │  │ (内存结果)    │  │ (异步写入)    │  │ (WebSocket)  │               │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 11.4 状态管理与存储架构

##### 11.4.1 存储技术选型

**决策：分层存储架构，各层选用最优技术**

| 存储层 | 技术选型 | 用途 | 选型理由 |
|-------|---------|------|---------|
| **状态存储** | Kvrocks | 滑动窗口状态、累计统计量 | Redis 协议兼容 + RocksDB 持久化 |
| **时序存储** | QuestDB | 分钟级行情、预聚合表 | 原生 O3 处理、SAMPLE BY 自动聚合 |
| **冷存储** | Parquet + DuckDB | 历史数据、因子结果 | 列式存储、压缩率高、分析查询快 |

**QuestDB 选型决策**：

| 候选方案 | 评估 | 结论 |
|---------|------|------|
| **QuestDB** | 极简部署、O3 原生支持、DEDUP 去重、550万行/秒写入 | ✅ 采用 |
| TimescaleDB | PostgreSQL 生态成熟，但写入性能较低 | ❌ 备选 |
| 自实现 ETL | 无新依赖，但异常处理/数据回补复杂度高 | ❌ 不采用 |

**QuestDB 核心优势**：

1. **O3（Out-of-Order）原生支持**：延迟数据自动重排序，无需手动处理
2. **DEDUP UPSERT**：自动去重，历史修正数据直接替换
3. **SAMPLE BY**：原生降采样聚合，无需写 ETL 任务
4. **高性能**：550 万行/秒写入，16 亿行聚合查询 0.15s
5. **极简部署**：单二进制，零外部依赖

**Kvrocks 优势**：
- Redis 协议兼容：可用 redis-cli 调试，redis-py 客户端成熟
- 基于 RocksDB：持久化好，crash 后自动恢复
- 单机部署：启动成本低，无需 Redis Cluster
- 多进程共享：多个 worker 可共享状态

##### 11.4.2 分层存储架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    分层存储架构（Hot/Warm/Cold + QuestDB）                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  热层（盘中运行时）                                                   │    │
│  │                                                                      │    │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │    │
│  │  │ 内存 StreamTable  │  │ Polars DataFrame  │  │    Kvrocks      │  │    │
│  │  │                   │  │                   │  │                 │  │    │
│  │  │ • 当日实时行情    │  │ • 预加载 lookback │  │ • 滑动窗口状态  │  │    │
│  │  │ • 实时计算结果    │  │ • 因子 DAG 缓存   │  │ • 累计统计量    │  │    │
│  │  │                   │  │                   │  │ • 截面临存      │  │    │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────┘  │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      │ QuestDB SAMPLE BY                    │
│                                      │ 自动维护预聚合                        │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  温层（QuestDB 时序存储）                                            │    │
│  │                                                                      │    │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │    │
│  │  │ market_1min       │  │ market_1h         │  │ market_daily    │  │    │
│  │  │ (原始分钟级)       │  │ (小时级聚合)       │  │ (日级聚合)       │  │    │
│  │  │                   │  │                   │  │                 │  │    │
│  │  │ • O3 乱序支持     │  │ • SAMPLE BY 1h    │  │ • SAMPLE BY 1d  │  │    │
│  │  │ • DEDUP 去重      │  │ • 自动刷新         │  │ • 自动刷新       │  │    │
│  │  │ • 实时写入        │  │ • 延迟数据自动处理 │  │ • 历史回补支持   │  │    │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────┘  │    │
│  │                                                                      │    │
│  │  优势：无需自实现 ETL，数据库原生处理异常和回补                        │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      │ 盘后归档（单向流动）                  │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  冷层（Parquet + DuckDB）                                            │    │
│  │                                                                      │    │
│  │  features/*.parquet    特征/指标（年分区）                           │    │
│  │  factors/*.parquet     因子（年分区 + PIT）                          │    │
│  │  archive/*.parquet     历史行情归档（可选）                          │    │
│  │                                                                      │    │
│  │  注：QuestDB 数据可选择性归档到 Parquet                              │    │
│  │      Kvrocks 状态仅盘中有效，收盘后可清空或保留用于次日跳板           │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**各层职责**：

| 层级 | 技术 | 职责 | 数据生命周期 |
|------|------|------|------------|
| **热层** | 内存 + Kvrocks | 实时计算、状态管理 | 盘中有效 |
| **温层** | QuestDB | 分钟级行情存储、预聚合 | 60-90 天 |
| **冷层** | Parquet + DuckDB | 历史归档、离线分析 | 永久 |

**Kvrocks 存储内容**：

| Key Pattern | 内容 | 生命周期 |
|-------------|------|---------|
| `ts_state:{factor_id}:{instrument_id}` | 滑动窗口数据 + 统计量 | 盘中有效 |
| `cs_slice:{factor_id}:{timestamp}` | 当前截面缓冲 | 触发后删除 |
| `session:{factor_id}` | 处理进度、watermark | 可持久化到次日 |

**QuestDB 存储内容**：

| 表名 | 内容 | 分区策略 | 保留期 |
|------|------|---------|-------|
| `market_1min` | 分钟级行情 | 按日分区 | 60 天 |
| `market_1h` | 小时级聚合 | 按月分区 | 90 天 |
| `market_daily` | 日级聚合 | 按年分区 | 永久 |

###### 11.4.2.1 存储成本估算

**基础数据规模**：

| 参数 | 数值 | 说明 |
|------|------|------|
| 标的数量 | 5,000 | A股股票 |
| 交易日/年 | 250 | 中国股市 |
| 分钟/交易日 | 240 | 4小时 × 60分钟 |
| 小时/交易日 | 4 | 9:30-11:30, 13:00-15:00 |

**单条记录大小**：

| 表 | 字段数 | 原始大小（字节） | 说明 |
|----|-------|----------------|------|
| `market_1min` | 8 | ~60 | instrument_id(4) + timestamp(8) + OHLCV(40) + amount(8) |
| `market_1h` | 9 | ~72 | 分钟级 + vwap(8) + bar_count(4) |
| `market_daily` | 10 | ~84 | 小时级 + returns(8) + volatility(8) |

**QuestDB 存储估算**：

| 数据层级 | 保留期 | 每日新增 | 原始大小 | 压缩比 | 压缩后 |
|---------|-------|---------|---------|-------|-------|
| 分钟级 | 60 天 | 120万行 | 4.3 GB | 5:1 | **860 MB** |
| 小时级 | 90 天 | 2万行 | 130 MB | 7:1 | **20 MB** |
| 日级 | 3 年 | 5000行 | 460 MB | 10:1 | **46 MB** |
| **合计** | | | **~5 GB** | | **~1 GB** |

**Kvrocks 存储估算**：

| 状态类型 | 数量 | 单条大小 | 原始合计 | 压缩后 |
|---------|------|---------|---------|-------|
| 滑动窗口（短周期） | 5000×5因子 = 25000条 | 600 B | 15 MB | 10 MB |
| 增量统计（长周期） | 5000×3因子 = 15000条 | 80 B | 1.2 MB | 0.8 MB |
| 截面临存 | 临时 | ~40 KB | 1 MB | 0.5 MB |
| **合计** | | | **~17 MB** | **~11 MB** |

**总存储需求**：

| 组件 | 压缩后大小 | 磁盘建议（含索引+开销） | 年度增长 |
|------|-----------|----------------------|---------|
| QuestDB | ~1 GB | 10 GB SSD | +15 MB（日级累积） |
| Kvrocks | ~11 MB | 100 MB SSD | 0（盘中临时） |
| Parquet（冷备） | 可选 | S3/OSS | 按需归档 |
| **合计** | **~1 GB** | **10-15 GB SSD** | **~15 MB/年** |

**云存储成本参考**（AWS us-east-1）：

| 存储 | 月成本 | 年成本 |
|------|-------|-------|
| gp3 SSD (50 GB) | ~$1/月 | ~$12/年 |
| S3 归档（冷备） | ~$0.50/月 | ~$6/年 |
| **合计** | **~$1.5/月** | **~$18/年** |

###### 11.4.2.2 存储使用场景与约束

**Ditto 项目存储架构总览**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Ditto 存储使用全景图                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       数据摄入层（Ingestion）                          │   │
│  │                                                                       │   │
│  │   Tushare API ──▶ 分钟级行情 ──▶ QuestDB (market_1min)               │   │
│  │                  历史日K    ──▶ Parquet (cold storage)               │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       因子计算层（Compute）                            │   │
│  │                                                                       │   │
│  │   QuestDB ──▶ Polars (内存) ──▶ 因子计算 ──▶ Kvrocks (状态更新)      │   │
│  │      │              │                              │                   │   │
│  │      │              └──▶ ts_mean(close, 20)        │                   │   │
│  │      │                   └─ 需要20天历史            │                   │   │
│  │      │                                          更新                  │   │
│  │      └──────────────────────────────────────────▶ 状态                │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       输出层（Output）                                 │   │
│  │                                                                       │   │
│  │   因子结果 ──▶ 内存 ResultTable ──▶ WebSocket 推送（交易系统）        │   │
│  │             ──▶ Parquet 归档 ──▶ DuckDB（离线分析）                   │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### ADR-012: 算子增量实现架构

**状态**: 已决策（2026-03-05）

**背景**:

表达式引擎需要为 52 个算子（ADR-007）提供增量计算能力。不同算子的增量实现复杂度差异巨大：
- `ts_mean` 可以用 O(1) 的滑动窗口 + 累计量实现
- `ts_rank` 需要维护有序结构，增量复杂度 O(log n)
- `ts_corr` 需要维护两个序列的协方差统计量

**决策**:

#### 1. 独立状态管理模块

延续 ADR-006 的决策，算子的增量计算逻辑通过**独立状态管理模块**实现：

```
packages/core/src/ditto_core/
├── expression/                 # 表达式引擎（纯计算）
│   ├── engine.py
│   └── operators.py
│
└── state/                      # 状态管理（独立模块）
    ├── manager.py              # StateManager 接口
    ├── adapters/
    │   ├── memory.py           # 内存适配器（测试用）
    │   └── kvrocks.py          # Kvrocks 适配器
    └── windows/
        ├── sliding.py          # 滑动窗口状态
        ├── incremental.py      # 增量统计状态
        └── ordered.py          # 有序结构状态
```

#### 2. 算子 5 层分类

| Tier | 算子类型 | 状态内容 | 增量复杂度 | 状态大小 |
|------|---------|---------|-----------|---------|
| **Tier 1** | O(1) 状态 | 单值或固定大小 | O(1) | O(1) |
| | `ts_delay`, `ts_ema`, `ts_delta`, `ts_pct_change` | | | |
| **Tier 2** | 简单增量 | window + sum/sum_sq | O(1) | O(n) |
| | `ts_mean`, `ts_sum`, `ts_std`, `ts_var`, `ts_count` | | | |
| **Tier 3** | 有序结构 | window + sorted_list | O(log n) | O(n) |
| | `ts_rank`, `ts_median`, `ts_quantile`, `ts_argmax`, `ts_argmin` | | | |
| **Tier 4** | 多变量 | window_x + window_y + stats | O(1) | O(2n) |
| | `ts_corr`, `ts_cov`, `ts_regression` | | | |
| **Tier 5** | 单调队列 | window + deque | O(1)* | O(n) |
| | `ts_min`, `ts_max` | | | |

*均摊复杂度

#### 3. 引入 sortedcontainers 依赖

对于 Tier 3 算子（需要维护有序结构），引入 `sortedcontainers` 库：

```python
from sortedcontainers import SortedList

class TSRankState:
    """ts_rank 状态 - 使用 SortedList 实现 O(log n) 增量"""
    window: deque[float]
    sorted_values: SortedList

    def update(self, new_value: float, window_size: int) -> float:
        # 淘汰旧值
        if len(self.window) >= window_size:
            old_value = self.window.popleft()
            self.sorted_values.remove(old_value)  # O(log n)

        # 插入新值
        self.window.append(new_value)
        self.sorted_values.add(new_value)  # O(log n)

        # 计算排名
        rank = self.sorted_values.bisect_left(new_value)
        return rank / len(self.sorted_values)
```

**选型对比**:

| 方案 | 复杂度 | 依赖 | 决策 |
|------|-------|------|------|
| 纯 Python + bisect | O(n) | 无 | ❌ 不采用 |
| sortedcontainers | O(log n) | 有 | ✅ 采用 |

**理由**:
- 因子计算对性能敏感，O(n) vs O(log n) 在 n=250 时差异明显
- `sortedcontainers` 是成熟的 Python 库，广泛使用，维护活跃
- 与 DolphinDB `mrank` 的 O(n log k) 复杂度对齐

#### 4. 状态接口设计

```python
class StateManager(Protocol):
    """状态管理器接口"""

    def get(self, key: str) -> bytes | None:
        """获取状态"""
        ...

    def set(self, key: str, state: bytes, ttl: int | None = None) -> None:
        """设置状态（可选 TTL）"""
        ...

    def delete(self, key: str) -> None:
        """删除状态"""
        ...

    def update(self, key: str, fn: Callable[[bytes | None], bytes]) -> bytes:
        """原子更新状态"""
        ...
```

**Key 命名规范**:

```
ditto:{type}:{factor_signature}:{instrument_id}

示例:
ditto:ts_state:ts_mean_close_20:000001
ditto:ts_state:ts_rank_volume_10:600000
ditto:cs_slice:cs_rank:2024-03-01T14:30
```

**业界对标**:

| 平台 | 状态管理策略 | Ditto 选择 |
|------|-------------|-----------|
| DolphinDB | 响应式状态引擎 + 内置优化 | ✓ 独立模块 + 分层状态 |
| WorldQuant Brain | DAG 执行 + 自动缓存 | ✓ 类似，状态可复用 |
| Qlib | 延迟计算 + 缓存 | ✓ 借鉴缓存策略 |

---

### ADR-013: ts_rank 精度策略

**状态**: 已决策（2026-03-05）

**背景**:

`ts_rank(x, n)` 计算当前值在过去 n 个值中的排名（归一化到 0-1）。对于长周期（如 n=250），有两种实现策略：
1. 精确计算：维护完整窗口，100% 精确
2. 近似计算：使用 T-Digest 或 GK Summary，空间效率高但有误差

**决策**: **始终精确计算**

#### 理由

| 维度 | 精确计算 | 近似计算 | 结论 |
|------|---------|---------|------|
| **因子精度敏感** | 100% 精确 | ε-近似（误差 1-5%） | 精确胜出 |
| **状态大小** | n 个 float（2KB @ n=250） | 100-200 bytes | 都可接受 |
| **与业界一致** | DolphinDB 精确 | Spark SQL 近似 | 精确胜出 |
| **实现复杂度** | 简单 | 需要额外依赖 | 精确胜出 |
| **内存估算** | 5000×5×2KB = 50MB | 5000×5×0.2KB = 5MB | 50MB 可接受 |

#### 内存估算

```
场景：5000 只 A 股，5 个不同窗口的 ts_rank

精确计算：
  单状态：250 float × 8 bytes = 2 KB
  总计：5000 标的 × 5 窗口 × 2 KB = 50 MB

Kvrocks 容量（来自 11.4.2.1 估算）：~11 MB
实际使用：50 MB 在 Kvrocks 可承受范围内（磁盘存储）
```

#### 近似算法调研结论

| 算法 | 空间复杂度 | 适用场景 | Ditto 适用性 |
|------|-----------|---------|-------------|
| **Greenwald-Khanna** | O((1/ε) log(εn)) | 无界数据流 | ❌ ts_rank 是有界窗口 |
| **T-Digest** | O(1/δ) | 分布式、尾部精度 | ❌ 因子计算不需要分布式合并 |
| **精确 + sortedcontainers** | O(n) | 固定窗口、精度敏感 | ✅ 采用 |

**关键洞察**: `ts_rank(x, n)` 是**有界窗口**问题，而非无界数据流问题。近似算法（GK、T-Digest）是为无界流设计的，在有界窗口场景下收益有限。

#### 实现

```python
from sortedcontainers import SortedList
from collections import deque

@dataclass
class TSRankState:
    """ts_rank 精确计算状态"""
    window: deque[float] = field(default_factory=deque)
    sorted_values: SortedList = field(default_factory=SortedList)

    def update(self, new_value: float, window_size: int) -> float:
        """
        增量更新排名

        Args:
            new_value: 新值
            window_size: 窗口大小

        Returns:
            当前排名（0-1 归一化）
        """
        # 淘汰旧值
        if len(self.window) >= window_size:
            old_value = self.window.popleft()
            self.sorted_values.discard(old_value)

        # 插入新值
        self.window.append(new_value)
        self.sorted_values.add(new_value)

        # 计算排名（0-1 归一化）
        rank = self.sorted_values.bisect_left(new_value)
        return rank / len(self.sorted_values) if self.sorted_values else 0.0

    def to_bytes(self) -> bytes:
        """序列化用于 Kvrocks 存储"""
        return orjson.dumps({
            "window": list(self.window),
            # sorted_values 从 window 重建，无需存储
        })

    @classmethod
    def from_bytes(cls, data: bytes) -> "TSRankState":
        """从 Kvrocks 反序列化"""
        obj = orjson.loads(data)
        window = deque(obj["window"])
        sorted_values = SortedList(window)
        return cls(window=window, sorted_values=sorted_values)
```

#### 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| 窗口内数据不足 n 个 | 使用当前已有数据计算排名 |
| 窗口内所有值相同 | 返回 0.5（中位数排名） |
| 空值处理 | 跳过空值，不参与排名计算 |
| 重复值 | 使用 bisect_left，相同值取最小排名 |

#### 业界对标

| 平台 | ts_rank 实现 | 精度 | Ditto 选择 |
|------|-------------|------|-----------|
| DolphinDB | mrank（精确 + 增量优化） | 100% | ✓ 采用 |
| WorldQuant Brain | 精确计算 | 100% | ✓ 一致 |
| Qlib | 精确计算 + 缓存 | 100% | ✓ 一致 |

---

### ADR-014: 表达式引擎核心设计

**状态**: 已决策（2026-03-05）

**背景**:

表达式引擎是因子计算的核心组件，需要明确以下关键设计点：
1. Codegen 输出目标（生成什么级别的代码）
2. 表达式缓存策略（是否缓存编译结果）
3. 空值处理策略（运行时 null 如何传播）
4. 错误报告格式（编译期错误如何呈现）

**决策**:

#### 1. Codegen 输出目标：Polars Expr

生成 `pl.Expr` 对象，而非完整的 LazyFrame。

```python
# 表达式: ts_mean(close, 20)
# Codegen 输出:
pl.col("close").rolling_mean(window_size=20, min_periods=1)
```

**理由**:
- **可组合性**：Expr 可以自由组合成复杂表达式
- **延迟执行**：Polars Lazy 执行引擎自动优化
- **灵活性**：单因子计算和研究场景友好
- **业界一致**：Qlib、BigQuant 均采用表达式级别输出

#### 2. 表达式缓存：Spec 级缓存 + CSE（直接 Phase 1）

采用两级缓存策略，直接实现 Phase 1 目标：

```
┌─────────────────────────────────────────────────────────────┐
│                     ExpressionCache                          │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────────────────┐    │
│  │ Spec 级缓存      │    │ CSE 子表达式缓存             │    │
│  │                 │    │                             │    │
│  │ Key: spec_hash  │    │ Key: sub_expr_canonical_hash│    │
│  │ Value: Expr     │    │ Value: CompiledSubExpr      │    │
│  │                 │    │                             │    │
│  │ 作用: 因子级复用 │    │ 作用: 跨因子公共表达式复用   │    │
│  └─────────────────┘    └─────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**实现示例**:

```python
@dataclass
class CompiledExpression:
    """编译后的表达式"""
    spec_hash: str
    expr: pl.Expr
    analysis: Analysis  # deps, lookback, requires_full_day
    sub_expr_cache: dict[str, pl.Expr]  # CSE 缓存


class ExpressionCache:
    """表达式缓存管理器"""

    def __init__(self, maxsize: int = 256):
        self._spec_cache: dict[str, CompiledExpression] = {}
        self._cse_cache: dict[str, pl.Expr] = {}
        self._maxsize = maxsize

    def get_or_compile(self, spec: BaseSpec) -> CompiledExpression:
        """获取或编译表达式（带 CSE 优化）"""
        # 1. 检查 Spec 级缓存
        if spec.spec_hash in self._spec_cache:
            return self._spec_cache[spec.spec_hash]

        # 2. 编译（带 CSE 检测）
        compiled = self._compile_with_cse(spec.expression)

        # 3. 存入缓存
        self._spec_cache[spec.spec_hash] = CompiledExpression(
            spec_hash=spec.spec_hash,
            expr=compiled,
            analysis=self._analyze(spec.expression),
            sub_expr_cache=self._cse_cache.copy()
        )
        return self._spec_cache[spec.spec_hash]

    def _compile_with_cse(self, expr: str) -> pl.Expr:
        """编译表达式并应用 CSE 优化"""
        ast = self._parse(expr)
        return self._codegen_with_cse(ast)

    def _codegen_with_cse(self, ast: ASTNode) -> pl.Expr:
        """Codegen 时检测并复用公共子表达式"""
        # 生成规范化的子表达式哈希
        sub_hash = self._canonical_hash(ast)

        if sub_hash in self._cse_cache:
            return self._cse_cache[sub_hash]

        # 递归编译
        expr = self._codegen_node(ast)
        self._cse_cache[sub_hash] = expr
        return expr

    def _canonical_hash(self, ast: ASTNode) -> str:
        """生成子表达式的规范化哈希（用于 CSE 检测）"""
        # 将 AST 转换为规范化字符串表示
        canonical = self._normalize_ast(ast)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

**业界对标**:

| 平台 | 缓存策略 | CSE 支持 | Ditto 选择 |
|------|---------|---------|-----------|
| Qlib | 内存 + 磁盘两级 | ✅ 子表达式级 | ✓ 采用 |
| DuckDB | 哈希表缓存 | ✅ 查询级 CSE | ✓ 参考 |
| DolphinDB | JIT 函数缓存 | ✅ 内置优化 | ✓ 参考 |

#### 3. 空值处理：严格模式（Null 传播）

运行时遇到 null 值时，结果为 null，不跳过或替换。

```python
# 示例
ts_mean([1.0, null, 3.0], 3)  # → null（而非 2.0）
cs_rank([1.0, null, 3.0])     # → [0.0, null, 1.0]
```

**理由**:
- **数据质量可见**：null 结果暴露数据问题，便于排查
- **一致的行为**：与 Polars/SQL null 语义一致
- **后续处理**：因子标准化阶段统一处理 null（填充、剔除等）

**实现要点**:

```python
def codegen_ts_mean(col: str, window: int) -> pl.Expr:
    """ts_mean 的 Polars Expr 生成"""
    return (
        pl.col(col)
        .rolling_mean(window_size=window, min_periods=1)
        .keep_name()  # 保持列名
    )
    # Polars 原生支持 null 传播，无需额外处理
```

**标准化阶段的 null 处理**:

```python
class NormalizationPipeline:
    def cs_rank(self, values: pl.Expr) -> pl.Expr:
        """CS 排名，null 保持为 null"""
        return values.rank(method="average").over("trade_date")

    def cs_zscore(self, values: pl.Expr) -> pl.Expr:
        """CS 标准化，null 保持为 null"""
        mean = values.mean().over("trade_date")
        std = values.std().over("trade_date")
        return (values - mean) / std
```

#### 4. 编译期错误报告：带位置高亮的详细错误

类似 Rust 编译器的错误格式，提供清晰的错误定位和修复建议。

```python
@dataclass
class CompileError:
    """编译期错误"""
    message: str
    error_code: str           # "E001_UNKNOWN_OPERATOR"
    span: Span                # start, end line/column
    source_line: str
    suggestions: list[str]    # ["ts_mean", "ts_median"]


def format_error(error: CompileError, source: str) -> str:
    """格式化为带高亮的错误消息"""
    return f"""
SyntaxError: {error.message}
  --> expression:{error.span.start.line}:{error.span.start.column}
   |
{error.span.start.line:3} | {error.source_line}
   | {" " * error.span.start.column}{"^" * (error.span.end.column - error.span.start.column)}
   | {error.message}
   |
   = help: did you mean {error.suggestions[0]}?
"""
```

**错误消息示例**:

```
SyntaxError: Unknown operator 'ts_meanx'
  --> expression:15:1
   |
15 | ts_meanx(close, 20) + cs_rank(volume)
   | ^^^^^^^^ unknown operator
   |
   = help: did you mean 'ts_mean'?

TypeError: Type mismatch in 'ts_mean'
  --> expression:20:10
   |
20 | ts_mean(close, "invalid")
   |          ^^^^^ expected integer, got string
   |
   = help: window size must be an integer
```

**错误代码分类**:

| 错误代码 | 类型 | 说明 |
|---------|------|------|
| E001-E010 | 词法错误 | 非法字符、字符串未闭合等 |
| E011-E020 | 语法错误 | 括号不匹配、操作符位置错误等 |
| E021-E030 | 语义错误 | 未知算子、未知列引用等 |
| E031-E040 | 类型错误 | 参数类型不匹配、参数数量错误等 |

**业界对标**:

| 平台 | 错误格式 | 位置高亮 | 修复建议 |
|------|---------|---------|---------|
| Rust | 详细 + 高亮 | ✅ | ✅ |
| TypeScript | 详细 | ✅ | ✅ |
| Qlib | 简单 | ❌ | ❌ |
| **Ditto** | **详细 + 高亮** | ✅ | ✅ |

#### 决策汇总

| 决策点 | 决策 | 理由 |
|-------|------|------|
| **Codegen 输出** | Polars Expr | 可组合、延迟执行、易于优化 |
| **表达式缓存** | Spec 级 + CSE（Phase 1） | Qlib 验证有效，避免重复计算 |
| **空值处理** | 严格模式（null 传播） | 数据质量问题可见，便于排查 |
| **错误报告** | 带位置高亮的详细错误 | 类似 Rust 编译器，开发体验好 |

---

### ADR-015: DAG 优化策略

**状态**: 已决策（2026-03-05）

**背景**:

因子计算涉及 DAG（有向无环图）执行优化。需要明确：
1. 多因子执行顺序（串行 vs 并行）
2. 增量计算边界（数据变更后重算范围）
3. 中间结果内存管理

**决策**:

#### 1. 多因子执行：拓扑排序 + 串行

采用**拓扑排序 + 串行执行**，不使用 Python 层并行。

**理由分析**:

| 方案 | Python 并行收益 | 原因 |
|------|----------------|------|
| 单因子计算 | ❌ 无 | Polars 内部已并行 |
| 多因子串行（当前） | - | 每个因子内部并行 |
| 多因子并行（threading） | ❌ 负收益 | GIL 阻塞，额外开销 |
| 多因子并行（multiprocessing） | ⚠️ 有限 | 进程启动开销 + 内存复制 |

**Polars 并行机制**:
- Polars 用 Rust 编写，计算时释放 GIL
- 16 核可达 12x 加速（相对于 Pandas）
- 单次 Polars 操作内部已是并行的

**Python Free-Threading（2026）**:
- Python 3.14（2025-10）正式支持 free-threading
- 多线程 CPU 密集任务可达 10x 加速
- 但 Ditto 当前使用 Python 3.12+，暂不可用

**性能估算**:

```
场景：100 个因子，5000 标的，3 年数据

单因子计算：~0.5-2s（Polars 内部并行）
100 因子串行：~50-200s（主要耗时）
I/O 写入：~10-30s（Parquet 写入）

结论：串行不是主要瓶颈
- 因子计算本身已通过 Polars 并行优化
- 100 因子 3 分钟内可完成，满足日更需求
- 真正瓶颈在 I/O 而非计算并行度
```

**执行流程**:

```python
def execute_factors(specs: list[FactorSpec], data: pl.DataFrame) -> None:
    """按拓扑顺序串行执行因子计算"""
    # 1. 构建依赖图
    dag = build_dependency_graph(specs)

    # 2. 拓扑排序
    ordered = topological_sort(dag)

    # 3. 串行执行（每个因子内部 Polars 并行）
    for spec in ordered:
        expr = compile_expression(spec)
        result = data.lazy().with_columns([expr.alias("value")]).collect()
        write_factor(result, spec)
```

#### 2. 增量计算边界：精确影响范围

当输入数据变更时，按**精确影响范围**重算，与 ADR-006 Invalidation 规则一致。

**规则**:

| 因子类型 | 影响范围 | 说明 |
|---------|---------|------|
| **TS 因子** | `(change_date - lookback, watermark]` | 向后扩展 lookback 天 |
| **CS 因子** | `change_date` 整日 | `requires_full_day=True`，整日全截面重算 |
| **混合因子** | TS 规则 + CS 规则 | 取两者并集 |

**示例**:

```python
# 因子: alpha_001 = ts_rank(cs_rank(close), 9)
# lookback = 9, requires_full_day = True
# 2026-01-15 的 market.close 修正

# 影响范围计算
change_date = date(2026, 1, 15)
lookback = 9
requires_full_day = True

if requires_full_day:
    # CS 因子：整日重算（所有标的）
    affected_dates = [change_date]
else:
    # TS 因子：向后扩展 lookback
    affected_dates = date_range(change_date, change_date + lookback)

# 计算边界
compute_start = min(affected_dates) - lookback  # 2026-01-06
compute_end = watermark  # 2026-03-05
```

**Invalidation 处理流程**:

```
源数据变更（market.close 2026-01-15 修正）
    │
    ├─ 查询依赖该列的所有因子
    │   SELECT entity_id FROM derived_dependency
    │   WHERE dep_column = 'market.close'
    │
    ├─ 对每个受影响因子：
    │   ├─ 计算 lookback 和 requires_full_day
    │   ├─ 确定受影响日期范围
    │   └─ 写入 derived_invalidation 表
    │
    └─ 下次增量执行时：
        ├─ 读取 pending invalidation
        ├─ 调整 compute_start/compute_end
        └─ 执行重算
```

#### 3. 中间结果内存：Polars 自动管理

采用 **Polars Lazy 执行**，中间列自动管理。

**Lazy 执行优势**:

| 特性 | 说明 |
|------|------|
| **延迟计算** | `collect()` 时才真正执行 |
| **查询优化** | Polars 自动优化执行计划 |
| **内存高效** | 中间列用完即释放 |
| **谓词下推** | 过滤条件下推到数据源 |

**示例**:

```python
# 因子表达式
alpha_001 = "cs_rank(ts_delta(close, 5) / ts_mean(close, 20))"

# Lazy 执行（推荐）
result = (
    df.lazy()
    .with_columns([
        pl.col("close").diff(5).alias("delta_5"),        # 临时列
        pl.col("close").rolling_mean(20).alias("mean_20"),  # 临时列
    ])
    .with_columns([
        (pl.col("delta_5") / pl.col("mean_20")).alias("ratio"),  # 临时列
    ])
    .with_columns([
        pl.col("ratio").rank().over("trade_date").alias("value"),  # 最终结果
    ])
    .select(["instrument_id", "trade_date", "value"])  # 只保留最终列
    .collect()  # 执行时才计算，中间列自动释放
)
```

**内存估算**:

```
场景：5000 标的 × 250 交易日 × 10 列（原始 + 临时）

Eager 模式：5000 × 250 × 10 × 8 bytes = ~100 MB
Lazy 模式：峰值 ~50 MB（中间列用完即释放）
```

#### 决策汇总

| 决策点 | 决策 | 理由 |
|-------|------|------|
| **多因子执行** | 拓扑排序 + 串行 | Polars 内部已并行，Python 层串行开销可控 |
| **增量计算边界** | 精确影响范围 | TS 向后扩展 lookback，CS 整日重算 |
| **中间结果内存** | Polars 自动管理 | Lazy 执行引擎自动优化 |

**业界对标**:

| 平台 | 执行模式 | 增量边界 | 内存管理 |
|------|---------|---------|---------|
| Qlib | 串行 | lookback 回退 | Eager（用户管理） |
| DolphinDB | 并行 | 精确范围 | 自动 GC |
| **Ditto** | **串行** | **精确范围** | **Lazy 自动** |

---

### ADR-016: Catalog 存储架构

**状态**: 已决策（2026-03-05）

**背景**:

Derived Catalog 需要存储 7 类元数据（spec、state、run、partition、checkpoint、invalidation、dependency），需要决定：
1. 存储技术选型（SQLite vs RocksDB vs 其他）
2. 拆分策略（单文件 vs 多文件）
3. 与现有 metadata SQLite 的关系

#### 16.1 技术选型分析

| 技术 | 优势 | 劣势 | 适用场景 |
|-----|------|------|---------|
| **SQLite** | SQL 查询、ACID 事务、成熟稳定 | 写入串行化 | 复杂查询、低频写入 |
| **RocksDB** | 高吞吐写入、LSM-Tree 优化 | 仅 KV 操作、无 SQL | 高频写入、简单访问 |
| **etcd** | 分布式强一致、Watch 机制 | 8GB 限制、网络开销 | 分布式协调 |
| **PostgreSQL** | SQL 全功能、可扩展 | 需要服务端、运维成本 | 大规模生产 |

**Ditto 场景分析**：

| 需求 | 特点 | 推荐 |
|-----|------|------|
| 复杂查询 | Lineage (WITH RECURSIVE)、运行历史过滤 | SQL 能力必需 |
| 事务原子性 | 物化完成时 5 表原子更新 | ACID 事务 |
| 写入频率 | ~300-800 次/天 | SQLite 绰绰有余 |
| 部署简单 | 本地盘场景 | 嵌入式优先 |

#### 16.2 混合存储方案

**决策**: 采用 **SQLite + Kvrocks 混合方案**

```
data/
├── metadata/
│   └── metadata.sqlite          # 关系型元数据
│       ├── instrument           # 现有
│       ├── trading_calendar     # 现有
│       ├── derived_spec         # 新增：因子定义
│       └── derived_dependency   # 新增：Lineage
│
├── runtime/
│   ├── ingestion.sqlite         # 摄取层（独立事务域）
│   │   └── ingestion_log        # 迁移
│   │
│   └── derived.sqlite           # 物化层（独立文件）
│       ├── derived_run          # 运行历史
│       └── derived_partition    # 分区元数据
│
└── (Kvrocks)                    # 状态存储（复用 ADR-012）
    ├── derived:state:{entity}           # watermark, coverage
    ├── derived:checkpoint:{entity}:{partition}  # 幂等检查
    └── derived:invalidation:{id}        # 失效队列
```

#### 16.3 存储职责划分

| 存储 | 表/Key | 访问模式 | 查询需求 |
|-----|-------|---------|---------|
| **metadata.sqlite** | `derived_spec` | 低频读写 | JOIN dependency |
| | `derived_dependency` | 低频写 | WITH RECURSIVE Lineage |
| **ingestion.sqlite** | `ingestion_log` | 中频写 | 按日期/状态过滤 |
| **derived.sqlite** | `derived_run` | 高频写 | 复杂过滤/排序 |
| | `derived_partition` | 中频写 | 按因子/日期查询 |
| **Kvrocks** | `state:*` | 高频读写 | 精确 key（复用 ADR-012） |
| | `checkpoint:*` | 高频读写 | 精确 key + TTL |
| | `invalidation:*` | 中频写 | 队列模式 |

#### 16.4 SQLite 表结构

**metadata.sqlite 新增表**：

```sql
-- derived_spec: 因子/特征定义
CREATE TABLE derived_spec (
    entity_type TEXT NOT NULL,      -- 'feature' | 'factor'
    entity_id TEXT NOT NULL,        -- 'alpha_momentum_12m'
    spec_hash TEXT NOT NULL,        -- 内容哈希
    expression TEXT NOT NULL,       -- 因子表达式
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id, version)
);

-- derived_dependency: 依赖关系（Lineage）
CREATE TABLE derived_dependency (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    dep_type TEXT NOT NULL,         -- 'source' | 'derived'
    dep_domain TEXT NOT NULL,       -- 'market' | 'fundamental'
    dep_entity_id TEXT NOT NULL,    -- 'close' | 'volume'
    PRIMARY KEY (entity_type, entity_id, dep_type, dep_entity_id)
);

CREATE INDEX idx_dependency_dep ON derived_dependency(dep_type, dep_entity_id);
```

**derived.sqlite 新增表**：

```sql
-- derived_run: 运行记录
CREATE TABLE derived_run (
    run_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'running' | 'success' | 'failed'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    rows_processed INTEGER,
    error_message TEXT
);

CREATE INDEX idx_run_entity ON derived_run(entity_type, entity_id, started_at DESC);
CREATE INDEX idx_run_status ON derived_run(status, started_at DESC);

-- derived_partition: 分区元数据
CREATE TABLE derived_partition (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    partition_key TEXT NOT NULL,    -- '2024-01' | '2024-02'
    row_count INTEGER NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id, partition_key)
);
```

#### 16.5 Kvrocks Key 结构

```
ditto:derived:state:{entity_type}:{entity_id}
    → JSON {watermark, coverage_start, coverage_end, coverage_gaps, updated_at}

ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}
    → "1" (存在即已完成，TTL 7天)

ditto:derived:invalidation:{priority}:{timestamp}:{id}
    → JSON {entity_type, entity_id, trigger_source, affected_range, status}
```

#### 16.6 拆分理由

| 决策点 | 选择 | 理由 |
|-------|------|------|
| **元数据 vs 运行时拆分** | 独立文件 | 职责分离、备份策略不同 |
| **ingestion 独立** | 独立文件 | T1/T2 可并行执行，写入隔离 |
| **state/checkpoint 用 Kvrocks** | 复用 ADR-012 | 简单 KV 模式，统一状态管理 |
| **run/partition 用 SQLite** | 独立文件 | 需要复杂查询，事务原子性 |

#### 16.7 业界对标

| 平台 | Registry 存储 | Ditto 选择 |
|------|-------------|-----------|
| Feast | SQLite (dev) / PostgreSQL (prod) | SQLite + Kvrocks |
| RisingWave | etcd → PostgreSQL | SQLite（规模较小） |
| Qlib | 自定义二进制 + DuckDB | SQLite（SQL 查询） |

---

### ADR-017: 因子服务 API

**状态**: 已决策（2026-03-05）

**背景**:

因子服务需要为多类调用方提供统一的 API：
- **Port Flow/Task** - 每日调度触发物化
- **CLI 命令** - 手动触发
- **研究环境** - Jupyter 交互式查询
- **外部系统** - 交易系统实时查询

#### 17.1 API 设计决策

| 决策点 | 选择 | 理由 |
|-------|------|------|
| **API 风格** | 声明式 | 更简洁，系统自动处理幂等/重试 |
| **物化执行** | 异步优先 | 物化耗时较长，立即返回 run_id |
| **执行后端** | Prefect | 复用现有依赖，生产就绪 |
| **查询格式** | 窄表优先（long） | 适合存储/传输，多因子可选宽表 |
| **认证** | 不需要 | 内网环境 |
| **API 版本** | 不版本化 | 保持与现有一致 |

#### 17.2 API 端点路径

```
/derived/
├── specs/                 # Spec 管理
│   ├── GET    /                      # 列出所有
│   ├── POST   /                      # 注册
│   ├── GET    /{entity_id}           # 详情
│   ├── GET    /{entity_id}/lineage   # 依赖
│   └── DELETE /{entity_id}           # 停用
│
├── runs/                  # 运行管理
│   ├── GET    /                      # 列出
│   ├── GET    /{run_id}              # 状态
│   ├── POST   /{run_id}/cancel       # 取消
│   └── GET    /{run_id}/wait         # 等待(SSE)
│
├── materialize/           # 物化操作
│   ├── POST   /                      # 单因子
│   └── POST   /batch                 # 批量
│
└── data/                  # 数据查询
    ├── POST   /query                 # 查询
    ├── GET    /watermark             # Watermark
    └── GET    /coverage              # 覆盖
```

#### 17.3 目录结构

```
apps/port/src/ditto_port/
├── api/routes/derived.py      # 🆕 REST API 路由
├── models/derived.py          # 🆕 Pydantic 模型
└── cli/commands/materialize/  # 🆕 CLI 命令

packages/core/src/ditto_core/
└── derived/                   # 🆕 核心模块
    ├── service.py             # DerivedService
    ├── catalog/               # Catalog 存储
    ├── expression/            # 表达式引擎
    └── materialize/           # 物化逻辑（Prefect tasks）
```

#### 17.4 核心 API 定义

**管理 API**:

```python
class DerivedService:
    def register_spec(request: SpecRegisterRequest) -> SpecInfo
    def list_specs(entity_type, is_active) -> list[SpecInfo]
    def get_spec(entity_id) -> SpecInfo | None
    def get_lineage(entity_id) -> LineageInfo
    def deactivate_spec(entity_id) -> None
```

**物化 API（异步优先）**:

```python
class DerivedService:
    def materialize(request: MaterializeRequest) -> MaterializeSubmitResult
    def materialize_batch(entity_ids, mode) -> list[MaterializeSubmitResult]
    def get_run(run_id) -> RunInfo | None
    def list_runs(entity_id, status, limit) -> list[RunInfo]
    def cancel_run(run_id) -> None
    def wait_for_run(run_id, timeout) -> RunInfo  # 阻塞等待
```

**查询 API**:

```python
class DerivedService:
    def find(query: DerivedQuery) -> pl.DataFrame
    def get_watermark(entity_id) -> str | None
    def get_coverage(entity_id) -> CoverageInfo | None
```

#### 17.5 请求/响应模型

```python
# Spec 注册
class SpecRegisterRequest(BaseModel):
    entity_type: Literal["feature", "factor"]
    entity_id: str
    expression: str
    description: str | None = None
    tags: list[str] | None = None

# 物化请求
class MaterializeRequest(BaseModel):
    entity_id: str
    mode: Literal["incremental", "full"] = "incremental"
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False
    force: bool = False
    callback_url: str | None = None

# 数据查询
class DataQueryRequest(BaseModel):
    entity_ids: list[str] | None = None
    start: str | None = None
    end: str | None = None
    as_of: str | None = None
    instruments: list[str] | None = None
    format: Literal["long", "wide"] = "long"  # 默认窄表
    limit: int = 10000
    offset: int = 0
```

#### 17.6 Prefect Flow 集成

```python
@flow(name="materialize_factor")
def materialize_flow(
    entity_id: str,
    mode: Literal["incremental", "full"] = "incremental",
    start_date: str | None = None,
    end_date: str | None = None,
) -> MaterializeResult:
    """物化 Flow（Prefect 编排）"""
    # 1. 验证依赖
    deps = validate_dependencies(entity_id)
    # 2. 计算范围
    compute_start, compute_end = compute_incremental_range(entity_id, mode)
    # 3. 加载数据
    df = load_source_data(deps, compute_start, compute_end)
    # 4. 执行计算
    result_df = execute_expression(df, spec.expression)
    # 5. 写入分区
    partitions = write_partitions(result_df, entity_id)
    # 6. 更新 Catalog
    update_catalog(entity_id, run_id, partitions, compute_end)
    return MaterializeResult(...)
```

#### 17.7 REST API 路由示例

```python
# apps/port/src/ditto_port/api/routes/derived.py

router = APIRouter(prefix="/derived", tags=["derived"])

@router.post("/materialize", response_model=MaterializeSubmitResponse, status_code=202)
@inject
async def materialize(
    request: MaterializeRequest,
    service: Annotated[DerivedService, FromComponent()],
):
    """提交物化任务（异步）"""
    return await asyncio.to_thread(service.materialize, request)

@router.get("/runs/{run_id}", response_model=RunResponse)
@inject
async def get_run(
    run_id: str,
    service: Annotated[DerivedService, FromComponent()],
):
    """查询任务状态"""
    run = await asyncio.to_thread(service.get_run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
```

---

### ADR-018: 监控与告警

**状态**: 已决策（2026-03-05）

**背景**:

因子系统需要完整的可观测性支持，包括运行状态监控、数据延迟告警、数据质量追踪。

#### 18.1 架构决策

| 决策点 | 选择 | 理由 |
|-------|------|------|
| **指标后端** | VictoriaMetrics | 复用现有基础设施 |
| **可视化** | Grafana | 复用现有基础设施 |
| **告警管理** | AlertManager | 复用现有基础设施 |
| **通知渠道** | 全局配置 | 减少配置复杂度 |

#### 18.2 指标体系

**命名规范**: `ditto.derived.*` 前缀

| 类别 | 指标名 | 类型 | 说明 |
|-----|-------|------|------|
| **运行状态** ||||
| `ditto.derived.materialization.total` | Counter | 物化任务计数 |
| `ditto.derived.materialization.duration` | Histogram | 物化耗时（秒） |
| `ditto.derived.materialization.running` | Gauge | 当前运行任务数 |
| **数据延迟** ||||
| `ditto.derived.data.lag_hours` | Gauge | Watermark 延迟（小时） |
| `ditto.derived.data.freshness_days` | Gauge | 数据新鲜度（天） |
| **数据质量** ||||
| `ditto.derived.data.coverage` | Gauge | 覆盖率（0-1） |
| `ditto.derived.data.gaps` | Gauge | 缺口数量 |
| `ditto.derived.data.rows_total` | Counter | 行数统计 |
| `ditto.derived.data.null_ratio` | Gauge | NULL 比例 |
| **依赖健康** ||||
| `ditto.derived.dependency.ready` | Gauge | 依赖就绪状态 |

#### 18.3 告警规则

**Critical 级别**:

| 告警 | 条件 | 说明 |
|-----|------|------|
| MaterializationFailed | `status="failed"` | 物化失败 |
| DataLagCritical | `lag_hours > 4` | 数据延迟 > 4 小时 |
| AllMaterializationStuck | 24h 无完成 | 全系统停滞 |

**Warning 级别**:

| 告警 | 条件 | 说明 |
|-----|------|------|
| DataLagWarning | `lag_hours > 1` | 数据延迟 > 1 小时 |
| LowCoverage | `coverage < 0.95` | 覆盖率 < 95% |
| DataGaps | `gaps > 0` | 存在数据缺口 |
| MaterializationSlow | P95 > 300s | 物化耗时过长 |
| DependencyNotReady | `ready == 0` | 依赖未就绪 |

#### 18.4 监控服务

```python
# packages/core/src/ditto_core/derived/monitoring.py

class DerivedMonitor:
    """因子系统监控服务"""

    def record_materialization_start(entity_id, mode) -> None
    def record_materialization_complete(entity_id, mode, duration, rows, success, error) -> None
    def record_watermark(entity_id, watermark, expected) -> None
    def record_coverage(entity_id, coverage, gaps) -> None
```

#### 18.5 Grafana Dashboard 面板

| 面板 | 类型 | 说明 |
|-----|------|------|
| 活跃因子数 | Stat | 当前 is_active=true 的因子 |
| 运行中任务 | Stat | 当前 materialization_running |
| 今日成功率 | Gauge | success / total |
| 任务状态分布 | Pie | success/failed/running |
| 耗时分布 | Histogram | P50/P95/P99 |
| 延迟热力图 | Heatmap | 各因子延迟分布 |
| Watermark 时间线 | Time Series | 各因子 watermark 变化 |
| 覆盖率表格 | Table | 各因子覆盖率、缺口数 |

#### 18.6 告警通知

复用全局 AlertManager 配置：
- **Critical** → 邮件 + Webhook
- **Warning** → 邮件

告警模板位置：
```
packages/infra/src/ditto_infra/services/notification/templates/alerts/derived.py
```

---

### ADR-019: 测试策略

**状态**: 已决策（2026-03-05）

**背景**:

因子系统需要确保算子数学正确性和物化流程可靠性，测试策略需平衡速度与覆盖。

#### 19.1 测试分层

| 层次 | 范围 | Phase 0/1 |
|-----|------|----------|
| **单元测试** | 算子、表达式、Catalog、状态管理 | ✅ |
| **集成测试** | 物化流程、依赖解析、状态恢复 | ✅ |
| **E2E 测试** | 端到端流程 | ❌ Phase 2 |
| **属性测试** | 数学性质验证 | ❌ Phase 2 |

#### 19.2 数据策略

| 场景 | 策略 | 说明 |
|-----|------|------|
| 小数据（<100行） | Fixtures | 预生成 Parquet/JSON 文件 |
| 大数据（>1000行） | Factory | 动态生成随机行情数据 |

```python
# tests/fixtures/market_data.py

@pytest.fixture
def small_market_df() -> pl.DataFrame:
    """小数据集 - 预定义"""
    return pl.DataFrame({
        "instrument_id": ["000001"] * 10,
        "trade_date": ["2024-01-0" + str(i) for i in range(1, 11)],
        "close": [10.0, 10.5, 11.0, 10.8, 10.2, 10.6, 11.2, 11.0, 10.9, 11.5],
    })

@pytest.fixture
def large_market_df() -> pl.DataFrame:
    """大数据集 - 动态生成"""
    return generate_market_data(
        instruments=100,
        days=250,
        seed=42,  # 可复现
    )
```

#### 19.3 测试后端

| 组件 | 测试后端 | 说明 |
|-----|---------|------|
| SQLite（元数据） | 内存 `:memory:` | 快速、隔离 |
| Kvrocks（状态） | Mock（dict） | 单元测试无需真实 KV |
| Parquet（数据） | 临时目录 | pytest tmp_path 自动清理 |

```python
# tests/conftest.py

@pytest.fixture
def catalog_store():
    """内存 Catalog 存储"""
    client = SQLiteClient(":memory:")
    return CatalogStore(client)

@pytest.fixture
def state_store():
    """Mock 状态存储"""
    return MockStateStore({})  # dict 替代 Kvrocks
```

#### 19.4 覆盖率目标

| 模块 | 分支覆盖率 | 理由 |
|-----|-----------|------|
| **算子** | 90%+ | 数学正确性关键 |
| **表达式引擎** | 90%+ | 核心逻辑 |
| **Service 层** | 80% | 标准要求 |
| **API 层** | 70% | 依赖集成测试 |

#### 19.5 测试目录结构

```
packages/core/tests/
├── unit/
│   ├── operators/
│   │   ├── test_ts_functions.py      # ts_mean, ts_rank, ts_corr...
│   │   ├── test_cs_functions.py      # cs_rank, cs_zscore...
│   │   └── test_scalar_functions.py  # abs, log, sign...
│   ├── expression/
│   │   ├── test_parser.py            # 语法解析
│   │   ├── test_analyzer.py          # 语义分析
│   │   └── test_compiler.py          # 编译优化
│   ├── catalog/
│   │   ├── test_spec_store.py        # Spec CRUD
│   │   └── test_dependency_store.py  # Lineage 查询
│   └── state/
│       ├── test_sliding_window.py    # 滑动窗口
│       └── test_incremental_stats.py # 增量统计
│
└── integration/
    ├── test_materialize_flow.py      # 物化流程
    ├── test_dependency_resolution.py # 依赖排序
    └── test_state_recovery.py        # 崩溃恢复
```

#### 19.6 典型测试示例

**算子单元测试**:

```python
# tests/unit/operators/test_ts_functions.py

class TestTsMean:
    """ts_mean 单元测试"""

    def test_basic_calculation(self, small_market_df):
        """基本计算正确性"""
        result = ts_mean(small_market_df["close"], window=3)
        expected = [10.0, 10.25, 10.5, 10.77, 10.67, 10.53, 10.67, 10.93, 11.03, 11.13]
        assert np.allclose(result, expected, atol=0.01)

    def test_window_boundary(self):
        """窗口边界处理"""
        df = pl.DataFrame({"value": [1.0, 2.0, 3.0]})
        result = ts_mean(df["value"], window=5)
        # 窗口大于数据量时，使用可用数据
        assert result[-1] == 2.0

    def test_null_handling(self):
        """NULL 值处理"""
        df = pl.DataFrame({"value": [1.0, None, 3.0, 4.0]})
        result = ts_mean(df["value"], window=2)
        # NULL 被排除，窗口内有效值计算
        assert result[-1] == 3.5
```

**物化集成测试**:

```python
# tests/integration/test_materialize_flow.py

class TestMaterializeFlow:
    """物化流程集成测试"""

    def test_incremental_materialize(
        self,
        catalog_store,
        state_store,
        tmp_path,
    ):
        """增量物化流程"""
        # 1. 注册 Spec
        service = DerivedService(catalog_store, state_store, tmp_path)
        service.register_spec(SpecRegisterRequest(
            entity_type="factor",
            entity_id="test_momentum",
            expression="ts_rank(close, 5)",
        ))

        # 2. 首次物化
        result = service.materialize(MaterializeRequest(
            entity_id="test_momentum",
            mode="incremental",
        ))
        assert result.status == "success"

        # 3. 增量物化
        result2 = service.materialize(MaterializeRequest(
            entity_id="test_momentum",
            mode="incremental",
        ))
        # 幂等检查：无新数据，跳过
        assert result2.status == "skipped"
```

---

**QuestDB 在 Ditto 中的使用**：

| 项目模块 | 使用方式 | 具体数据 |
|---------|---------|---------|
| **数据摄入** | Tushare 行情写入 | `market_1min` 表：每分钟 OHLCV |
| **因子计算** | 读取 lookback 数据 | 查询过去 N 天的 close/volume |
| **预聚合** | SAMPLE BY 自动维护 | `market_1h`、`market_daily` 表 |

**具体存储内容**：

```sql
-- market_1min：分钟级行情（主要查询源）
-- 写入：数据摄入层，每分钟 ~5000 条
-- 读取：因子计算层，加载 lookback 窗口
SELECT instrument_id, timestamp, close, volume
FROM market_1min
WHERE instrument_id = '000001'
  AND timestamp >= dateadd('d', -20, now())  -- ts_mean(close, 20)
ORDER BY timestamp;

-- market_1h：小时级聚合（中等 lookback 使用）
-- 写入：SAMPLE BY 自动维护
-- 读取：ts_mean(close, 45) 等中等周期因子
SELECT * FROM market_1h
WHERE instrument_id = '000001'
  AND timestamp >= dateadd('d', -60, now());

-- market_daily：日级聚合（长周期因子使用）
-- 写入：SAMPLE BY 自动维护
-- 读取：MA60/MA120/MA250 等长周期因子
SELECT * FROM market_daily
WHERE instrument_id = '000001'
  AND timestamp >= dateadd('d', -250, now());
```

**读写流程**：

```
盘前（08:00-09:15）：
┌─────────────────────────────────────────────────────────────────┐
│  1. 因子引擎启动，解析因子表达式                                 │
│  2. 分析 lookback 需求：ts_mean(close, 20) → 需要 20 天数据     │
│  3. 从 QuestDB 加载到 Polars 内存：                              │
│     df = questdb.query("SELECT ... WHERE timestamp >= -20d")    │
│  4. 数据驻留内存，盘中增量更新                                   │
└─────────────────────────────────────────────────────────────────┘

盘中（09:30-15:00）：
┌─────────────────────────────────────────────────────────────────┐
│  1. 实时行情写入 QuestDB（持久化）                               │
│  2. 同时更新内存 StreamTable                                    │
│  3. 因子计算：内存数据 + Kvrocks 状态                           │
│  4. QuestDB 仅作为数据源，不参与实时计算路径                     │
└─────────────────────────────────────────────────────────────────┘

盘后（15:05-16:00）：
┌─────────────────────────────────────────────────────────────────┐
│  1. QuestDB SAMPLE BY 自动刷新聚合表                             │
│  2. 可选：导出当日数据到 Parquet 归档                            │
│  3. 清理 60 天前的分钟级分区                                     │
└─────────────────────────────────────────────────────────────────┘
```

**约束与最佳实践**：

| 约束项 | 说明 | 违反后果 |
|-------|------|---------|
| 时间范围查询 | 必须带 timestamp 条件 | 全表扫描，性能下降 100x |
| SYMBOL 类型 | instrument_id 使用 SYMBOL | 字符串存储开销增加 10x |
| 单节点 | 当前不支持分布式 | 无法水平扩展 |
| 追加写入 | 避免频繁 UPDATE | 写放大，性能下降 |

---

**Kvrocks 在 Ditto 中的使用**：

| 项目模块 | 使用方式 | 具体数据 |
|---------|---------|---------|
| **因子计算** | 读取/更新滑动窗口状态 | `ts_state:{factor}:{instrument}` |
| **因子计算** | 读取/更新增量统计量 | 长周期 mean/std 的 count/sum/M2 |
| **横截面计算** | 临时存储截面数据 | `cs_slice:{factor}:{timestamp}` |

**具体存储内容**：

```python
# Key-Value 结构设计

# 1. 滑动窗口状态（短周期因子，如 ts_mean(close, 20)）
# Key: ts_state:ts_mean_20:000001
# Value: JSON
{
    "window": [10.1, 10.2, 10.15, ...],  # 最近 20 个 close
    "sum": 203.5,
    "count": 20,
    "updated_at": "2024-03-01T14:30:00"
}
# 大小：~600 bytes
# TTL：18 小时（覆盖到次日开盘）

# 2. 增量统计状态（长周期因子，如 ts_mean(close, 250)）
# Key: ts_state:ts_mean_250:000001
# Value: JSON（Welford 算法）
{
    "count": 250,
    "mean": 15.23,
    "M2": 1234.56,  # 用于计算方差
    "updated_at": "2024-03-01T15:00:00"
}
# 大小：~80 bytes
# TTL：4 小时（可从 QuestDB 重建）

# 3. 横截面缓冲（cs_rank 等截面因子）
# Key: cs_slice:cs_rank:2024-03-01T14:30:00
# Value: JSON
{
    "values": {
        "000001": 10.5,
        "000002": 8.3,
        "600000": 12.1,
        ...  # 所有标的的当前值
    },
    "triggered": false
}
# 大小：~40 KB（5000 标的）
# TTL：无（触发计算后手动删除）
```

**读写流程**：

```
因子计算流程（以 ts_mean(close, 20) 为例）：
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  1. 接收新行情：close = 10.5                                     │
│                                                                  │
│  2. 从 Kvrocks 读取状态：                                        │
│     state = kvrocks.get("ts_state:ts_mean_20:000001")           │
│     # state = {"window": [...], "sum": 203.0, "count": 20}      │
│                                                                  │
│  3. 增量更新状态（内存）：                                       │
│     state["window"].append(10.5)                                │
│     state["sum"] += 10.5                                        │
│     if len(state["window"]) > 20:                               │
│         old = state["window"].pop(0)                            │
│         state["sum"] -= old                                     │
│                                                                  │
│  4. 计算结果：                                                   │
│     mean = state["sum"] / 20  # 10.325                          │
│                                                                  │
│  5. 写回 Kvrocks：                                               │
│     kvrocks.setex("ts_state:ts_mean_20:000001", 64800, state)   │
│                                                                  │
│  6. 输出因子值：mean = 10.325                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**状态 Key 设计规范**：

```python
# Key 命名规范
# {namespace}:{type}:{factor_signature}:{instrument_id}
#
# namespace:    ditto (项目前缀，避免与其他系统冲突)
# type:        ts_state | cs_state | session | checkpoint
# factor_signature: 因子的唯一标识（如 ts_mean_close_20）
# instrument_id: 标的代码（如 000001）

# 示例：
# ditto:ts_state:ts_mean_close_20:000001
# ditto:ts_state:ts_corr_close_volume_60:600000
# ditto:cs_state:cs_rank_momentum:ALL
# ditto:session:factor_engine_001
# ditto:checkpoint:ts_mean_close_20:2024-03-01
```

**各类型状态详细设计**：

```python
# 1. ts_state - 时间序列滑动窗口状态
# Key: ditto:ts_state:{factor_signature}:{instrument_id}
# 适用：ts_mean, ts_sum, ts_std, ts_rank, ts_corr 等

@dataclass
class TSSlidingWindowState:
    """滑动窗口状态（短周期，如 ts_mean(close, 20)）"""
    window: list[float]  # 最近 N 个值
    sum: float
    sum_sq: float  # 用于计算方差
    count: int
    timestamp: str  # 最后更新时间

    def to_json(self) -> bytes:
        return orjson.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: bytes) -> "TSSlidingWindowState":
        return cls(**orjson.loads(data))

@dataclass
class TSIncrementalState:
    """增量统计状态（长周期，如 ts_mean(close, 250)）- Welford 算法"""
    count: int
    mean: float
    M2: float  # 用于计算方差
    timestamp: str

    def update(self, value: float) -> None:
        """Welford 在线算法"""
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.M2 += delta * delta2

    def variance(self) -> float:
        return self.M2 / (self.count - 1) if self.count > 1 else 0.0

    def std(self) -> float:
        return self.variance() ** 0.5

@dataclass
class TSCorrelationState:
    """相关性状态（ts_corr）"""
    n: int
    sum_x: float
    sum_y: float
    sum_xy: float
    sum_x2: float
    sum_y2: float
    window_x: list[float]  # 滑动窗口
    window_y: list[float]
    timestamp: str

    def correlation(self) -> float:
        """Pearson 相关系数"""
        if self.n < 2:
            return float('nan')
        numerator = self.n * self.sum_xy - self.sum_x * self.sum_y
        denominator = (
            (self.n * self.sum_x2 - self.sum_x ** 2) *
            (self.n * self.sum_y2 - self.sum_y ** 2)
        ) ** 0.5
        return numerator / denominator if denominator != 0 else float('nan')

# 2. cs_state - 横截面状态
# Key: ditto:cs_state:{factor_signature}:{date}
# 适用：cs_rank, cs_zscore, cs_neutralize 等

@dataclass
class CSSliceState:
    """横截面缓冲状态"""
    values: dict[str, float]  # instrument_id -> value
    expected_count: int
    triggered: bool
    timestamp: str

    def completeness(self) -> float:
        return len(self.values) / self.expected_count

    def should_trigger(self, threshold: float = 0.95) -> bool:
        return self.completeness() >= threshold

    def compute_rank(self) -> dict[str, float]:
        """计算横截面排名"""
        if not self.values:
            return {}
        values = np.array(list(self.values.values()))
        ids = list(self.values.keys())
        ranks = scipy.stats.rankdata(values) / len(values)
        return dict(zip(ids, ranks))

# 3. session - 会话状态
# Key: ditto:session:{session_id}
# 适用：因子引擎运行时状态

@dataclass
class SessionState:
    """因子引擎会话状态"""
    session_id: str
    started_at: str
    last_processed_timestamp: str
    processed_count: int
    error_count: int
    status: Literal["running", "paused", "error"]

# 4. checkpoint - 检查点
# Key: ditto:checkpoint:{date}
# 适用：盘后状态快照，用于次日跳板

@dataclass
class CheckpointState:
    """每日状态检查点"""
    date: str  # 检查点日期
    created_at: str
    factor_states: dict[str, bytes]  # factor_signature -> serialized state
    metadata: dict[str, Any]  # 其他元数据
```

**TTL 策略**：

| 状态类型 | TTL | 理由 |
|---------|-----|------|
| `ts_state`（短周期 ≤ 60） | 18 小时 | 覆盖到次日开盘 |
| `ts_state`（长周期 > 60） | 4 小时 | 可从 QuestDB 重建 |
| `cs_state` | 1 小时 | 临时缓存，触发后删除 |
| `session` | 24 小时 | 跨日有效 |
| `checkpoint` | 7 天 | 跳板数据，过期可重建 |

---

**Checkpoint 机制**：

```
盘后 Checkpoint 流程（15:05）：
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  1. 收集所有活跃因子的状态：                                      │
│     factor_states = {}                                           │
│     for key in kvrocks.scan("ditto:ts_state:*"):                │
│         factor_states[key] = kvrocks.get(key)                   │
│                                                                  │
│  2. 创建检查点：                                                  │
│     checkpoint = CheckpointState(                                │
│         date="2024-03-01",                                       │
│         created_at=now(),                                         │
│         factor_states=factor_states,                             │
│         metadata={"version": "1.0"}                              │
│     )                                                            │
│     kvrocks.set("ditto:checkpoint:2024-03-01", checkpoint)      │
│                                                                  │
│  3. 设置 TTL（7 天）：                                            │
│     kvrocks.expire("ditto:checkpoint:2024-03-01", 7*24*3600)    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

盘前恢复流程（08:00）：
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  1. 检查昨日检查点：                                              │
│     checkpoint = kvrocks.get("ditto:checkpoint:2024-03-01")      │
│                                                                  │
│  2. 如果存在，恢复状态：                                          │
│     if checkpoint:                                               │
│         for factor_key, state in checkpoint.factor_states:       │
│             kvrocks.set(factor_key, state)                       │
│             kvrocks.expire(factor_key, 18*3600)  # 重设 TTL      │
│                                                                  │
│  3. 如果不存在，从 QuestDB 重建：                                  │
│     # 重新计算所有因子的初始状态                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

**幂等与断点续跑保证**：

```python
class StateManager:
    """状态管理器 - 幂等设计"""

    def __init__(self, kvrocks_client, factor_signature: str):
        self.client = kvrocks_client
        self.factor_signature = factor_signature
        self._local_cache: dict[str, TSSlidingWindowState] = {}

    def get_state(self, instrument_id: str) -> TSSlidingWindowState | None:
        """获取状态（带本地缓存）"""
        if instrument_id in self._local_cache:
            return self._local_cache[instrument_id]

        key = f"ditto:ts_state:{self.factor_signature}:{instrument_id}"
        data = self.client.get(key)
        if data:
            state = TSSlidingWindowState.from_json(data)
            self._local_cache[instrument_id] = state
            return state
        return None

    def update_state(
        self,
        instrument_id: str,
        new_value: float,
        window_size: int,
    ) -> TSSlidingWindowState:
        """幂等更新状态"""
        state = self.get_state(instrument_id)
        if state is None:
            state = TSSlidingWindowState(
                window=[], sum=0.0, sum_sq=0.0, count=0, timestamp=""
            )

        # 去重检查：如果时间戳相同，跳过
        if state.timestamp == current_timestamp:
            return state  # 已处理过，幂等返回

        # 增量更新
        state.window.append(new_value)
        state.sum += new_value
        state.sum_sq += new_value * new_value
        state.count += 1
        state.timestamp = current_timestamp

        # 滑动窗口淘汰
        if len(state.window) > window_size:
            old = state.window.pop(0)
            state.sum -= old
            state.sum_sq -= old * old
            state.count -= 1

        # 写回（带 TTL）
        key = f"ditto:ts_state:{self.factor_signature}:{instrument_id}"
        self.client.setex(key, 18 * 3600, state.to_json())

        # 更新本地缓存
        self._local_cache[instrument_id] = state
        return state

    def flush(self) -> None:
        """批量刷写（可选，用于性能优化）"""
        pass
```

**断点续跑场景**：

| 场景 | 处理方式 |
|------|---------|
| **进程崩溃重启** | 从 checkpoint 恢复，从上次处理的时间戳继续 |
| **网络中断** | 状态在 Kvrocks 持久化，重连后继续 |
| **Kvrocks 重启** | 从 checkpoint 或 QuestDB 重建状态 |
| **全量重跑** | 清空状态，从 QuestDB 重新计算 |

---

**约束与最佳实践**：

| 约束项 | 说明 | 违反后果 |
|-------|------|---------|
| 单 Key 操作 | 禁用 KEYS 命令 | 阻塞整个实例 |
| Value 大小 | 单条 < 1KB | 内存压力、网络延迟 |
| TTL 设置 | 必须设置过期 | 状态无限累积 |
| JSON 序列化 | 使用 orjson | 性能下降 3x |
| 幂等设计 | 使用 timestamp 去重 | 重复计算、状态错误 |
| 本地缓存 | 减少网络往返 | 性能下降 10x |

---

**Parquet + DuckDB 在 Ditto 中的使用**：

| 项目模块 | 使用方式 | 具体数据 |
|---------|---------|---------|
| **数据摄入** | 历史日K归档 | `market_daily/2024/2024.parquet` |
| **因子输出** | 因子结果持久化 | `factors/momentum/2024.parquet` |
| **离线分析** | 回测、研究 | DuckDB 查询 Parquet |

**具体存储内容**：

```
data/
├── market/                    # 原始行情归档
│   └── daily/
│       ├── 2022.parquet      # 2022 年日K（~50MB）
│       ├── 2023.parquet      # 2023 年日K（~50MB）
│       └── 2024.parquet      # 2024 年日K（增量写入）
│
├── factors/                   # 因子结果
│   ├── momentum/
│   │   └── 2024.parquet      # 动量因子（日频）
│   ├── volatility/
│   │   └── 2024.parquet      # 波动率因子
│   └── alpha101/
│       └── 2024.parquet      # Alpha101 因子
│
└── features/                  # 特征库
    └── daily/
        └── 2024.parquet      # 日频特征（宽表）
```

**读写流程**：

```
盘后归档（15:30）：
┌─────────────────────────────────────────────────────────────────┐
│  1. 从 QuestDB 导出当日数据：                                    │
│     df = questdb.query("SELECT * FROM market_daily              │
│                         WHERE timestamp = today()")             │
│                                                                  │
│  2. 追加到 Parquet：                                             │
│     pl.concat([existing, df]).write_parquet(                    │
│         "market/daily/2024.parquet",                            │
│         partition_by=["trade_date"]  # 可选分区                 │
│     )                                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

##### 11.4.3 盘中实时计算数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        盘中实时计算流程                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  盘前准备（08:00 - 09:15）                                           │    │
│  │                                                                      │    │
│  │  1. 从 Parquet 加载 lookback 窗口数据到内存                          │    │
│  │     例：ts_mean(close, 20) 需要过去 20 天日频数据                     │    │
│  │                                                                      │    │
│  │  2. 初始化 Kvrocks 状态（从 checkpoint 恢复或新建）                   │    │
│  │                                                                      │    │
│  │  3. 启动流引擎，等待实时行情                                         │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  盘中计算（09:30 - 15:00）                                           │    │
│  │                                                                      │    │
│  │  数据合并：                                                          │    │
│  │  ┌─────────────────┐                                                 │    │
│  │  │ full_data =     │                                                 │    │
│  │  │   historical    │  ← Polars (从 Parquet 预加载)                  │    │
│  │  │   + realtime    │  ← 内存 StreamTable (当日实时)                  │    │
│  │  └─────────────────┘                                                 │    │
│  │                                                                      │    │
│  │  计算流程：                                                          │    │
│  │  1. 接收实时行情 → 更新内存 StreamTable                              │    │
│  │  2. 从 Kvrocks 读取滑动窗口状态                                      │    │
│  │  3. 执行因子计算（Polars 内存计算）                                   │    │
│  │  4. 更新 Kvrocks 状态（增量更新）                                     │    │
│  │  5. 输出：推送交易系统 + 内存结果表                                   │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  盘后处理（15:05 - 16:00）                                           │    │
│  │                                                                      │    │
│  │  1. 停止流引擎                                                       │    │
│  │  2. 刷出内存结果表                                                   │    │
│  │  3. 执行增量物化 → 写入 Parquet                                      │    │
│  │  4. 更新 Catalog watermark                                           │    │
│  │  5. 清理 Kvrocks（可选，或保留用于次日跳板）                          │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

##### 11.4.4 长周期 Lookback 处理策略

**问题**：当 lookback 超过内存可承载范围（如 250 天 mean），如何处理？

**决策**：
- **Q1 预聚合粒度**：混合模式（根据 lookback 动态选择多级粒度）
- **Q2 增量统计位置**：独立状态管理模块（职责分离，便于测试和扩展）
- **Q3 长周期阈值**：可配置（默认 60 天）

###### 11.4.4.1 多级数据粒度策略（混合模式）

**可配置阈值设计**：

```python
from pydantic import BaseModel
from typing import Literal

class LookbackThresholds(BaseModel):
    """Lookback 阈值配置（可通过配置文件调整）"""

    # 分钟级阈值：≤此值使用分钟级全量数据
    minute_threshold: int = 20  # 默认 20 天

    # 小时级阈值：≤此值使用小时级预聚合
    hourly_threshold: int = 60  # 默认 60 天

    # 超过 hourly_threshold 使用日级预聚合
    # 日级无上限（存储极小）

    @property
    def levels(self) -> list[tuple[int, Literal["minute", "hourly", "daily"]]]:
        """返回 (阈值, 数据粒度) 的层级列表"""
        return [
            (self.minute_threshold, "minute"),
            (self.hourly_threshold, "hourly"),
            (float('inf'), "daily"),
        ]

    def resolve_frequency(self, lookback_days: int) -> Literal["minute", "hourly", "daily"]:
        """根据 lookback 自动选择数据频率"""
        for threshold, freq in self.levels:
            if lookback_days <= threshold:
                return freq
        return "daily"  # fallback

# 配置示例（可通过 YAML 覆盖）
# lookback_thresholds:
#   minute_threshold: 30  # 调高分钟级覆盖范围
#   hourly_threshold: 90  # 调高小时级覆盖范围
```

**方案分层（混合模式）**：

| Lookback 范围 | 数据频率 | 处理策略 | 内存估算 |
|--------------|---------|---------|---------|
| ≤ minute_threshold (默认 20 天) | 分钟级 | 全量加载分钟数据 | ~2.4GB |
| minute_threshold ~ hourly_threshold (默认 20-60 天) | 小时级 | 小时级预聚合表 | ~240MB |
| > hourly_threshold (默认 60 天) | 日级 | 日级预聚合表 | ~30MB |

**预聚合表设计**：

```python
# 小时级预聚合表（盘中增量更新）
@dataclass
class HourlyAggregate:
    instrument_id: str
    date: date
    hour: int  # 0-23
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    vwap: float  # amount / volume

# 日级预聚合表（盘后批量生成）
@dataclass
class DailyAggregate:
    instrument_id: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    vwap: float
    # 扩展统计量
    returns: float  # (close - prev_close) / prev_close
    volatility: float  # 日内波动率
```

**混合计算示例**：

```python
def hybrid_moving_average(
    symbol: str,
    window: int,
    thresholds: LookbackThresholds,
) -> float:
    """混合模式移动平均：自动选择最优数据粒度"""
    freq = thresholds.resolve_frequency(window)

    if freq == "minute":
        # 分钟级全量计算
        return minute_mavg(symbol, window)
    elif freq == "hourly":
        # 小时级预聚合 + 当日分钟级
        historical = hourly_mavg(symbol, window - 4)  # 扣除今日
        today = today_minute_mavg(symbol)
        return (historical * (window - 4) + today * 4) / window
    else:  # daily
        # 日级预聚合 + 当日分钟级
        historical = daily_mavg(symbol, window - 1)
        today = today_minute_mavg(symbol)
        return (historical * (window - 1) + today) / window

# 示例：ts_mean(close, 250) → 自动使用日级预聚合
# ts_mean(close, 45) → 自动使用小时级预聚合
# ts_mean(close, 10) → 使用分钟级数据
```

###### 11.4.4.2 独立状态管理模块

**设计决策**：增量统计实现为独立模块（非内置到表达式引擎）

**架构草图**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    packages/core/src/ditto_core/                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  expression/                     (表达式引擎 - 纯计算)     │   │
│  │  ├── engine.py                  表达式解析和执行          │   │
│  │  ├── operators.py               算子定义                  │   │
│  │  └── functions/                 内置函数                  │   │
│  │       ├── ts_functions.py       ts_mean, ts_rank, ...     │   │
│  │       └── cs_functions.py       cs_rank, cs_zscore, ...   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ 调用                              │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  state/                          (状态管理 - 独立模块)     │   │
│  │  ├── manager.py                 状态管理器接口            │   │
│  │  ├── adapters/                  存储适配器                │   │
│  │  │   ├── memory.py              内存适配器（测试用）       │   │
│  │  │   └── kvrocks.py             Kvrocks 适配器            │   │
│  │  ├── windows/                   窗口状态                  │   │
│  │  │   ├── sliding.py             滑动窗口                  │   │
│  │  │   └── incremental.py         增量统计                  │   │
│  │  └── triggers/                  触发器                    │   │
│  │      ├── time_trigger.py        时间触发                  │   │
│  │      └── completeness.py        完整度触发                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**核心接口设计**：

```python
# state/manager.py
from typing import Protocol, TypeVar

StateT = TypeVar("StateT")

class StateManager(Protocol[StateT]):
    """状态管理器接口 - 支持多种存储后端"""

    def get(self, key: str) -> StateT | None:
        """获取状态"""
        ...

    def set(self, key: str, state: StateT) -> None:
        """设置状态"""
        ...

    def delete(self, key: str) -> None:
        """删除状态"""
        ...

    def update(self, key: str, fn: Callable[[StateT | None], StateT]) -> StateT:
        """原子更新状态（乐观锁）"""
        ...


# state/adapters/kvrocks.py
class KvrocksAdapter(StateManager[bytes]):
    """Kvrocks 适配器"""

    def __init__(self, url: str, ttl: int | None = None):
        self._client = redis.from_url(url)
        self._ttl = ttl  # 状态过期时间（秒）

    def update(self, key: str, fn: Callable[[bytes | None], bytes]) -> bytes:
        """使用 Lua 脚本保证原子性"""
        lua_script = """
        local current = redis.call('GET', KEYS[1])
        local new_value = fn(current)
        redis.call('SET', KEYS[1], new_value)
        if TTL then redis.call('EXPIRE', KEYS[1], TTL) end
        return new_value
        """
        return self._client.eval(lua_script, 1, key)
```

**窗口状态类型**：

```python
# state/windows/sliding.py
@dataclass
class SlidingWindowState:
    """滑动窗口状态"""

    values: deque[float]  # 最近 N 个值
    running_sum: float = 0.0
    running_sum_sq: float = 0.0

    def push(self, value: float) -> None:
        """添加新值，淘汰旧值"""
        self.values.append(value)
        self.running_sum += value
        self.running_sum_sq += value * value

        if len(self.values) > self.max_size:
            old = self.values.popleft()
            self.running_sum -= old
            self.running_sum_sq -= old * old

    def mean(self) -> float:
        return self.running_sum / len(self.values) if self.values else float('nan')

    def std(self) -> float:
        if len(self.values) < 2:
            return float('nan')
        n = len(self.values)
        variance = (self.running_sum_sq / n) - (self.mean() ** 2)
        return variance ** 0.5


# state/windows/incremental.py
@dataclass
class IncrementalStatistics:
    """增量统计（Welford 算法 - O(1) 空间复杂度）"""

    count: int = 0
    mean: float = 0.0
    M2: float = 0.0  # 用于计算方差

    def update(self, value: float) -> None:
        """Welford 在线算法"""
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.M2 += delta * delta2

    def variance(self) -> float:
        if self.count < 2:
            return float('nan')
        return self.M2 / (self.count - 1)

    def std(self) -> float:
        return self.variance() ** 0.5

    def to_bytes(self) -> bytes:
        """序列化用于 Kvrocks 存储"""
        return orjson.dumps(asdict(self))

    @classmethod
    def from_bytes(cls, data: bytes) -> "IncrementalStatistics":
        return cls(**orjson.loads(data))
```

**表达式引擎调用状态管理器**：

```python
# expression/functions/ts_functions.py
class TSFunctions:
    """时间序列函数 - 调用状态管理器"""

    def __init__(self, state_manager: StateManager, thresholds: LookbackThresholds):
        self._state = state_manager
        self._thresholds = thresholds

    def ts_mean(self, key: str, value: float, window: int) -> float:
        """时间序列均值"""
        state_key = f"ts_mean:{key}"

        # 根据窗口大小选择状态类型
        if window <= self._thresholds.minute_threshold:
            # 短窗口：使用滑动窗口（精确计算）
            state = self._state.update(
                state_key,
                lambda s: self._update_sliding(s, value, window)
            )
            return state.mean()
        else:
            # 长窗口：使用增量统计（O(1) 空间）
            state = self._state.update(
                state_key,
                lambda s: self._update_incremental(s, value)
            )
            return state.mean

    def _update_sliding(
        self,
        state_bytes: bytes | None,
        value: float,
        window: int,
    ) -> SlidingWindowState:
        state = SlidingWindowState.from_bytes(state_bytes) if state_bytes else SlidingWindowState(max_size=window)
        state.push(value)
        return state

    def _update_incremental(
        self,
        state_bytes: bytes | None,
        value: float,
    ) -> IncrementalStatistics:
        state = IncrementalStatistics.from_bytes(state_bytes) if state_bytes else IncrementalStatistics()
        state.update(value)
        return state
```

**状态 Key 命名规范**：

```python
# Key Pattern: {type}:{factor_id}:{instrument_id}:{extra?}
#
# ts_state:ts_mean:000001              # 滑动窗口状态
# ts_state:ts_corr:000001:close_vs_vol # 相关性状态
# cs_slice:cs_rank:20240315:09:30      # 截面临存
# session:factor_001:watermark         # 处理进度
```

**TS 算子状态类型**：

| 算子类型 | 状态内容 | 内存占用 | 淘汰策略 |
|---------|---------|---------|---------|
| `ts_mean(x, n)` | 最近 n 个值 + sum | O(n) | FIFO 队列 |
| `ts_rank(x, n)` | 最近 n 个值 + 排序索引 | O(n) | FIFO 队列 |
| `ts_corr(x, y, n)` | 最近 n 个 (x, y) 对 + 统计量 | O(n) | FIFO 队列 |
| `ts_ema(x, alpha)` | 单个累积值 | O(1) | 无需淘汰 |
| `ts_delay(x, n)` | 最近 n 个值 | O(n) | FIFO 队列 |

**CS 算子状态触发**：

```python
# state/triggers/time_trigger.py
@dataclass
class TimeTrigger:
    """时间触发器"""

    interval_seconds: float
    last_trigger: datetime | None = None

    def should_fire(self, now: datetime) -> bool:
        if self.last_trigger is None:
            self.last_trigger = now
            return False
        elapsed = (now - self.last_trigger).total_seconds()
        return elapsed >= self.interval_seconds


# state/triggers/completeness.py
@dataclass
class CompletenessTrigger:
    """完整度触发器"""

    threshold: float  # 0.0 - 1.0
    expected_count: int
    current_slice: dict[str, float] = field(default_factory=dict)

    def should_fire(self, instrument_id: str, value: float) -> bool:
        self.current_slice[instrument_id] = value
        completeness = len(self.current_slice) / self.expected_count
        return completeness >= self.threshold

    def get_slice(self) -> pl.Series:
        return pl.Series("value", list(self.current_slice.values()))

    def reset(self) -> None:
        self.current_slice.clear()
```

###### 11.4.4.3 状态生命周期管理

**Kvrocks 存储策略**

```python
# 短周期（≤ minute_threshold）：存储完整窗口
key = f"ts_state:ts_mean:000001"
value = {
    "values": [1.23, 1.24, ...],  # 最近 N 个值
    "running_sum": 25.6,
    "count": 20,
}

# 长周期（> hourly_threshold）：仅存储增量统计量
key = f"ts_state:ts_mean_250:000001"
value = {
    "count": 250,
    "mean": 15.23,
    "M2": 1234.56,  # 不存储原始数据
}
```

**状态 TTL 配置**：

```python
class StateTTLConfig(BaseModel):
    """状态 TTL 配置"""

    # 短周期状态：保留到次日开盘（用于跳板）
    short_period_ttl: int = 18 * 3600  # 18 小时

    # 长周期状态：可更短（可从 Parquet 重建）
    long_period_ttl: int = 4 * 3600  # 4 小时

    # 截面状态：触发后立即删除
    cross_sectional_ttl: int | None = None  # 手动删除
```

**盘后状态处理**：

| 状态类型 | 盘后操作 | 理由 |
|---------|---------|------|
| 滑动窗口 | 保留或压缩 | 次日可直接跳板 |
| 增量统计 | 保留 | 计算成本高 |
| 截面临存 | 清空 | 已无意义 |
| Watermark | 持久化到 Parquet | 用于回溯 |

###### 11.4.4.4 QuestDB 预聚合设计

**表结构设计**：

```sql
-- 分钟级行情表（原始数据）
CREATE TABLE market_1min (
    instrument_id SYMBOL,
    timestamp TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume LONG,
    amount DOUBLE
) TIMESTAMP(timestamp)
PARTITION BY DAY
WAL
DEDUP UPSERT KEYS timestamp, instrument_id;  -- 自动去重

-- 小时级聚合表（SAMPLE BY 自动维护）
-- QuestDB 9.0+ 支持物化视图
CREATE TABLE market_1h (
    instrument_id SYMBOL,
    timestamp TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume LONG,
    amount DOUBLE,
    vwap DOUBLE,
    bar_count INT
) TIMESTAMP(timestamp)
PARTITION BY MONTH;

-- 日级聚合表
CREATE TABLE market_daily (
    instrument_id SYMBOL,
    timestamp TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume LONG,
    amount DOUBLE,
    vwap DOUBLE,
    returns DOUBLE,
    volatility DOUBLE
) TIMESTAMP(timestamp)
PARTITION BY YEAR;
```

**SAMPLE BY 聚合查询**：

```sql
-- 小时级聚合（实时查询或物化视图刷新）
INSERT INTO market_1h
SELECT
    instrument_id,
    timestamp AS timestamp,
    first(close) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close) AS close,
    sum(volume) AS volume,
    sum(amount) AS amount,
    sum(amount) / sum(volume) AS vwap,
    count(*) AS bar_count
FROM market_1min
WHERE timestamp >= dateadd('h', -1, now())
SAMPLE BY 1h ALIGN TO CALENDAR;

-- 日级聚合
INSERT INTO market_daily
SELECT
    instrument_id,
    timestamp AS timestamp,
    first(close) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close) AS close,
    sum(volume) AS volume,
    sum(amount) AS amount,
    sum(amount) / sum(volume) AS vwap,
    (last(close) - first(close)) / first(close) AS returns,
    stddev(close) AS volatility
FROM market_1min
SAMPLE BY 1d ALIGN TO CALENDAR;
```

**混合模式数据获取**：

```python
from pydantic import BaseModel
from typing import Literal

class LookbackThresholds(BaseModel):
    """Lookback 阈值配置"""
    minute_threshold: int = 20   # ≤20 天 → 分钟级
    hourly_threshold: int = 60   # 20-60 天 → 小时级

    def resolve_frequency(self, lookback_days: int) -> Literal["minute", "hourly", "daily"]:
        if lookback_days <= self.minute_threshold:
            return "minute"
        elif lookback_days <= self.hourly_threshold:
            return "hourly"
        return "daily"


class QuestDBClient:
    """QuestDB 数据访问客户端"""

    def get_lookback_data(
        self,
        instrument_id: str,
        lookback_days: int,
        thresholds: LookbackThresholds,
    ) -> pl.DataFrame:
        """根据 lookback 自动选择最优数据源"""
        freq = thresholds.resolve_frequency(lookback_days)

        if freq == "minute":
            return self._query_minute(instrument_id, lookback_days)
        elif freq == "hourly":
            return self._query_hourly(instrument_id, lookback_days)
        else:
            return self._query_daily(instrument_id, lookback_days)

    def _query_minute(self, instrument_id: str, days: int) -> pl.DataFrame:
        sql = f"""
        SELECT * FROM market_1min
        WHERE instrument_id = '{instrument_id}'
          AND timestamp >= dateadd('d', -{days}, now())
        ORDER BY timestamp
        """
        return self._execute_sql(sql)

    def _query_hourly(self, instrument_id: str, days: int) -> pl.DataFrame:
        sql = f"""
        SELECT * FROM market_1h
        WHERE instrument_id = '{instrument_id}'
          AND timestamp >= dateadd('d', -{days}, now())
        ORDER BY timestamp
        """
        return self._execute_sql(sql)

    def _query_daily(self, instrument_id: str, days: int) -> pl.DataFrame:
        sql = f"""
        SELECT * FROM market_daily
        WHERE instrument_id = '{instrument_id}'
          AND timestamp >= dateadd('d', -{days}, now())
        ORDER BY timestamp
        """
        return self._execute_sql(sql)
```

###### 11.4.4.5 数据回补与异常处理

**QuestDB 原生能力**：

| 异常场景 | QuestDB 处理方式 | 操作复杂度 |
|---------|-----------------|-----------|
| **数据延迟** | O3（Out-of-Order）自动重排序 | 零操作 |
| **数据重复** | DEDUP UPSERT 自动去重 | 零操作 |
| **历史修正** | 直接 INSERT，相同 key 自动替换 | 零操作 |
| **数据回补** | 直接 INSERT，物化视图自动刷新 | 手动触发刷新 |
| **Schema 变更** | ALTER TABLE，聚合表需重建 | 低 |

**数据回补工作流**：

```python
class DataBackfillService:
    """数据回补服务"""

    def backfill_range(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
    ) -> BackfillResult:
        """
        回补指定日期范围的数据

        流程：
        1. 从上游数据源获取缺失数据
        2. 直接 INSERT 到 QuestDB（DEDUP 自动处理重复）
        3. 触发物化视图刷新（如需要）
        """
        # 1. 获取缺失数据
        missing_data = self._fetch_from_source(instrument_id, start_date, end_date)

        # 2. 批量插入 QuestDB（DEDUP 自动处理）
        self._insert_to_questdb(missing_data)

        # 3. 验证数据完整性
        return self._verify_backfill(instrument_id, start_date, end_date)

    def _insert_to_questdb(self, data: pl.DataFrame) -> None:
        """批量插入，DEDUP 自动处理重复数据"""
        # QuestDB InfluxDB Line Protocol 或 PostgreSQL wire protocol
        # 相同 (timestamp, instrument_id) 的数据会被替换
        sql = """
        INSERT INTO market_1min
        SELECT * FROM input_data
        """
        self._questdb_client.execute(sql, data)
```

**延迟数据处理**：

```python
# QuestDB 原生支持 O3，无需特殊处理
# 延迟数据直接插入，数据库自动按时间戳排序

# 示例：10:15 收到 09:35 的延迟数据
late_data = {
    "instrument_id": "000001",
    "timestamp": "2024-03-01T09:35:00",
    "open": 10.5,
    "high": 10.6,
    "low": 10.4,
    "close": 10.55,
    "volume": 1000000,
    "amount": 10550000,
}

# 直接插入，QuestDB 自动：
# 1. 按时间戳插入正确位置（O3 处理）
# 2. 如果已存在则替换（DEDUP）
questdb_client.insert("market_1min", late_data)
```

**与自实现 ETL 的复杂度对比**：

| 场景 | 自实现 ETL | QuestDB |
|------|-----------|---------|
| **正常流程** | 写 ETL 任务 + 调度 | 定义 SAMPLE BY SQL |
| **数据延迟** | 检测完整性 + 重跑任务 | 自动 O3 处理 |
| **历史修正** | 级联删除 + 重跑 ETL | 直接 INSERT 替换 |
| **数据回补** | 设计回补工作流 + 验证 | INSERT + 自动刷新 |
| **任务失败** | 幂等设计 + 重试 + 回滚 | 数据库事务保证 |
| **监控告警** | 自建监控体系 | QuestDB 内置指标 |

**结论**：引入 QuestDB 后，ETL 相关的异常处理复杂度降低 **80%+**。

#### 11.5 数据摄入模式

**支持的数据源**：

| 数据源 | 协议 | 适用场景 | 延迟 |
|--------|------|---------|------|
| **Kafka** | 订阅 | 生产环境、高吞吐 | < 10ms |
| **Redis Stream** | 订阅 | 低延迟、小规模 | < 5ms |
| **WebSocket** | 推送 | 行情接口、交易所 | < 10ms |
| **文件回放** | 模拟 | 回测验证 | 可控 |

**流数据表定义**：

```python
@dataclass
class StreamTableConfig:
    """流数据表配置"""
    name: str
    schema: dict[str, pl.DataType]

    # 容量控制
    max_rows: int = 1_000_000  # 最大行数
    max_memory_mb: int = 100   # 最大内存（MB）

    # 淘汰策略
    eviction_policy: Literal["FIFO", "LRU"] = "FIFO"

    # 持久化
    persist_enabled: bool = False
    persist_interval_seconds: int = 60

# 行情流表
MARKET_STREAM = StreamTableConfig(
    name="market_stream",
    schema={
        "instrument_id": pl.Utf8,
        "trade_time": pl.Datetime("ms"),
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Int64,
        "amount": pl.Float64,
    },
    max_rows=10_000_000,
    persist_enabled=True,
)

# 因子结果流表
FACTOR_STREAM = StreamTableConfig(
    name="factor_stream",
    schema={
        "instrument_id": pl.Utf8,
        "trade_time": pl.Datetime("ms"),
        "factor_id": pl.Utf8,
        "raw_value": pl.Float64,
        "exposure": pl.Float64,
    },
    max_rows=5_000_000,
    persist_enabled=True,
)
```

#### 11.6 流批一体化实现

**核心原则：表达式代码零修改**

```python
# 同一表达式定义
EXPRESSION = "ts_rank(cs_rank(close), 9) + rsi_14"

# 批量模式
def batch_materialize(expression: str, start: date, end: date) -> pl.DataFrame:
    """批量物化（T+1）"""
    ast = parse_expression(expression)
    analysis = analyze_expression(ast)

    # 加载历史数据
    data = load_historical_data(analysis.dependencies, start, end)

    # Polars 批量计算
    result = execute_batch(ast, data)

    return result

# 流式模式
def streaming_materialize(expression: str, stream_table: StreamTable) -> None:
    """流式物化（实时）"""
    ast = parse_expression(expression)
    analysis = analyze_expression(ast)

    # 创建状态管理器（每个 instrument 一个）
    state_managers: dict[str, StreamingState] = {}

    # 创建流计算引擎
    ts_engine = ReactiveStateEngine(
        ast=ast,
        state_managers=state_managers,
        key_column="instrument_id",
    )

    # 订阅数据流
    stream_table.subscribe(ts_engine.on_data)
```

**历史回放验证**：

```python
def replay_validation(expression: str, trade_date: date) -> ValidationResult:
    """历史回放验证（确保流批一致性）"""
    # 1. 批量计算结果（基准）
    batch_result = batch_materialize(expression, trade_date, trade_date)

    # 2. 流式计算结果（回放）
    stream_result = pl.DataFrame()
    stream_table = create_memory_stream_table()

    # 启动流式计算
    streaming_materialize(expression, stream_table)

    # 回放历史数据
    historical_data = load_historical_data(["market"], trade_date, trade_date)
    for row in historical_data.iter_rows(named=True):
        stream_table.append(row)
        # 等待处理完成

    stream_result = stream_table.get_results()

    # 3. 比较结果
    diff = (batch_result - stream_result).abs()
    max_diff = diff.max()

    return ValidationResult(
        expression=expression,
        trade_date=trade_date,
        max_diff=max_diff,
        passed=max_diff < 1e-6,
    )
```

#### 11.7 性能目标与监控

**延迟目标**：

| 场景 | P50 | P95 | P99 |
|------|-----|-----|-----|
| 单因子 TS 计算 | < 1ms | < 5ms | < 10ms |
| 单因子 TS+CS 计算 | < 10ms | < 50ms | < 100ms |
| 多因子并行（10个） | < 20ms | < 100ms | < 200ms |
| 截面标准化 | < 5ms | < 20ms | < 50ms |

**监控指标**：

```python
@dataclass
class StreamingMetrics:
    """流式计算监控指标"""

    # 延迟
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float

    # 吞吐
    events_per_second: int
    factors_per_second: int

    # 状态
    active_instruments: int
    memory_usage_mb: float
    state_cache_hit_rate: float

    # 错误
    error_rate: float
    late_arrival_rate: float  # 迟到数据比例
```

#### 11.8 与批量/增量的集成

**统一 Catalog 扩展**：

```sql
-- 流式因子运行状态
CREATE TABLE IF NOT EXISTS streaming_state (
    factor_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,  -- 'running', 'paused', 'stopped'
    started_at TIMESTAMP NOT NULL,
    last_event_time TIMESTAMP,
    last_output_time TIMESTAMP,
    events_processed BIGINT DEFAULT 0,
    errors_count BIGINT DEFAULT 0,
    config_json TEXT  -- JSON 配置
);

-- 流式因子 Checkpoint（用于恢复）
CREATE TABLE IF NOT EXISTS streaming_checkpoint (
    factor_id TEXT NOT NULL,
    checkpoint_time TIMESTAMP NOT NULL,
    state_snapshot BLOB,  -- 序列化的状态
    PRIMARY KEY (factor_id, checkpoint_time)
);
```

**流批切换流程**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        流批切换流程                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐                                                        │
│  │  盘前准备        │                                                        │
│  │                 │                                                        │
│  │  1. 加载昨日    │                                                        │
│  │     watermark   │                                                        │
│  │  2. 初始化状态  │                                                        │
│  │     管理器      │                                                        │
│  │  3. 启动流引擎  │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                               │
│  │  盘中流式计算    │────▶│  实时因子输出    │                               │
│  │                 │     │                 │                               │
│  │  - 事件驱动     │     │  - 推送交易系统  │                               │
│  │  - 状态维护     │     │  - 更新内存表    │                               │
│  │  - 增量更新     │     │  - 异步持久化    │                               │
│  └────────┬────────┘     └─────────────────┘                               │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │  盘后切换        │                                                        │
│  │                 │                                                        │
│  │  1. 停止流引擎  │                                                        │
│  │  2. 刷出缓冲    │                                                        │
│  │  3. 执行增量    │     ← 与增量模式统一                                    │
│  │     物化        │                                                        │
│  │  4. 更新        │                                                        │
│  │     watermark   │                                                        │
│  │  5. 持久化状态  │                                                        │
│  └─────────────────┘                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 11.9 Phase 规划

| Phase | 时间 | 目标 | 交付物 |
|-------|------|------|--------|
| **Phase 0** | 1-2 周 | 架构预留 | 接口定义 + 状态管理器原型 |
| **Phase 1** | 2-3 周 | 基础能力 | TS 引擎 + 单因子流式计算 |
| **Phase 2** | 3-4 周 | 完整流式 | CS 引擎 + 多因子并行 + 历史回放 |
| **Phase 3** | 4-6 周 | 生产就绪 | 高可用 + 监控 + 运维工具 |

**Phase 0 架构预留**：

```python
# 执行引擎接口（统一批量/增量/流式）
class ExecutionEngine(Protocol):
    """执行引擎协议"""

    def execute(
        self,
        ast: AST,
        config: RunConfig,
    ) -> ExecutionResult:
        """执行计算"""
        ...

    mode: Literal["batch", "incremental", "streaming"]

# RunConfig 扩展
@dataclass
class RunConfig:
    """运行配置"""
    mode: Literal["batch", "incremental", "streaming"]
    start_date: date | None = None
    end_date: date | None = None

    # 流式模式特有配置
    stream_config: StreamConfig | None = None

@dataclass
class StreamConfig:
    """流式运行配置"""
    source: Literal["kafka", "redis", "websocket", "replay"]
    source_config: dict[str, Any]

    trigger_type: Literal["time", "completeness"]
    trigger_value: int | float

    output: Literal["memory", "persist", "push"]
    output_config: dict[str, Any] | None = None
```

#### 11.10 风险与对策

| 风险 | 级别 | 对策 |
|------|------|------|
| 流批结果不一致 | 高 | 历史回放验证 + 单元测试覆盖 |
| 状态过大导致内存溢出 | 高 | 状态淘汰策略 + 内存监控 + 限流 |
| 迟到数据处理 | 中 | Watermark + 侧输出 + 补算机制 |
| 截面完整度不足 | 中 | 触发阈值配置 + 部分截面计算 |
| 高可用与故障恢复 | 中 | Checkpoint 定期保存 + 状态恢复 |

---

## 21. 开放议题与未来演进

### 21.1 待解决的开放议题

| 议题 | 描述 | 优先级 | 建议 |
|------|------|--------|------|
| 多日历支持 | 不同市场（A股/港股/美股）使用不同交易日历 | P1 | Qlib 的交易日历可作为基础 |
| 实时因子计算 | 分钟级/Tick 级因子支持 | P2 | **已设计** - 参见 ADR-011 流式模式架构 |
| 因子组合优化 | 多因子权重自动优化（IC-IR 加权等） | P2 | 后续作为独立模块 |
| 自定义算子注册 | 用户自定义算子扩展机制 | P1 | 通过 OperatorRegistry 预留 |
| 表达式版本迁移 | Spec 变更时的历史数据迁移策略 | P1 | 设计 SpecHash 变更检测 |

### 21.2 业界趋势观察

**因子研究平台演进方向**：

1. **AutoML 集成**
   - 自动特征工程（AutoFE）
   - 超参数自动调优
   - 业界参考：BigQuant AutoStrategy、WorldQuant AutoAlpha

2. **增量学习**
   - 因子衰减自动检测
   - 动态因子权重调整
   - 业界参考：Two Sigma 增量因子研究

3. **可解释性**
   - SHAP 值因子贡献分析
   - 因子归因报告
   - 业界参考：MSCI Barra 因子归因

4. **多周期融合**
   - 日内 + 日频因子混合
   - 多周期信号融合
   - 业界参考：Citadel 多周期策略框架

### 21.3 后续 ADR 预留

| ADR 编号 | 主题 | 触发条件 |
|----------|------|----------|
| ADR-012 | 多日历统一接口 | 支持港股/美股时 |
| ADR-013 | 因子组合优化策略 | 因子库达到 50+ 时 |
| ADR-014 | 用户自定义算子 DSL | 有外部用户需求时 |
| ADR-015 | 分布式计算扩展 | 单机性能不足时 |

### 21.4 技术债务边界

**第一阶段的明确边界**（不追求完美，但确保可演进）：

| 领域 | 接受的技术债 | 清理时机 |
|------|-------------|----------|
| 表达式解析 | 错误消息不够友好 | Phase 1 完成后 |
| 增量计算 | 首次全量计算可能较慢 | 有性能数据后优化 |
| Catalog | SQLite 单点 | 支持分布式时迁移 |
| 测试 | 仅核心路径 E2E | Phase 2 补充边界测试 |

---

## 22. 最终决策声明

本设计在不改变 Ditto 现有域命名和分层规则的前提下，吸收”编译期静态分析 + 一体化增量”核心思想，将复杂度集中在 `ditto_core` 的表达式与计划层，并通过 `ditto_datahub` 的锁与目录原子提交保证工程可用性。

这不是概念性蓝图，而是可按 Phase 0/1/2 直接拆任务执行的工程方案。

---

## 23. ADR 决策索引

| ADR | 主题 | 决策摘要 | 状态 |
|-----|------|----------|------|
| ADR-001 | TS/CS 嵌套策略 | 支持任意嵌套 + 自动属性推导 | ✅ 已决策 |
| ADR-002 | 算子体系设计 | 三类算子（TS/CS/SCALAR）+ OperatorRegistry | ✅ 已决策 |
| ADR-003 | 技术指标架构 | 算子原子化 + 指标作为表达式宏 | ✅ 已决策 |
| ADR-004 | 表达式语法 | dataset.column + @前缀 + alpha_命名 | ✅ 已决策 |
| ADR-005 | 首批特征/因子 | 10 特征 + 10 因子 + Alpha101 子集 | ✅ 已决策 |
| ADR-006 | 增量计算策略 | 混合 Watermark + 混合 Lookback + 分级回补 | ✅ 已决策 |
| ADR-007 | 算子完整清单 | 52 算子（P0:32 + P1:12 + P2:8） | ✅ 已决策 |
| ADR-008 | 标准化管线 | 默认 Rank → ZScore（WorldQuant 风格） | ✅ 已决策 |
| ADR-009 | 摄取流程 | T2 特征物化 → T3 因子物化 → T4 发布 | ✅ 已决策 |
| ADR-010 | Catalog 表结构 | 7 表（spec/state/run/partition/checkpoint/invalidation/dependency） | ✅ 已决策 |
| ADR-011 | 流式模式架构 | 流批一体 + 状态管理 + 增量引擎 | ✅ 已决策 |
| ADR-012 | 算子增量实现 | 独立状态管理模块 + 5 层分类 + sortedcontainers | ✅ 已决策 |
| ADR-013 | ts_rank 精度策略 | 始终精确计算（维护完整窗口） | ✅ 已决策 |
| ADR-014 | 表达式引擎核心 | Polars Expr + Spec缓存+CSE + 严格null + 详细错误 | ✅ 已决策 |
| ADR-015 | DAG 优化策略 | 串行执行 + 精确影响范围 + Lazy 内存管理 | ✅ 已决策 |
| ADR-016 | Catalog 存储架构 | SQLite + Kvrocks 混合方案 | ✅ 已决策 |
| ADR-017 | 因子服务 API | 声明式 + 异步优先 + Prefect + 窄表默认 | ✅ 已决策 |
| ADR-018 | 监控与告警 | VictoriaMetrics + Grafana + 复用全局告警 | ✅ 已决策 |
| ADR-019 | 测试策略 | 单元+集成 + 混合数据 + 内存后端 + 分级覆盖率 | ✅ 已决策 |
| ADR-020 | 部署与运维 | Docker Compose + testcontainers + fakeredis | ✅ 已决策 |
| ADR-021 | PIT 一致性集成 | FactorSpec 默认 PIT + pit_columns 迁移到 StoreSchema | ✅ 已决策 |
| ADR-022 | 更正数据处理 | 批处理依赖 DAG / 实时流级联触发 + 数据集级依赖追踪 | ✅ 已决策 |
| ADR-023 | 灾备恢复策略 | 暂不实现 / 分钟级数据重建问题待 Phase 2 决定 | ⏸️ 延迟决策 |
| ADR-024 | 因子版本管理 | Git 分支指针模式 + primary 指针 + 手动声明引用 + 7 天归档删除 | ✅ 已决策 |

---

## 24. ADR-020: 部署与运维设计

**状态**: 已决策（2026-03-05）

**背景**:

因子引擎需要部署 QuestDB（时序存储）和 Kvrocks（状态存储），需要设计：
1. Docker Compose 部署方案
2. 本地开发测试的 Mock 方案
3. 与现有运维体系集成

### 20.1 设计目标

1. **Docker Compose 一键部署** QuestDB + Kvrocks
2. **与现有架构兼容** - 统一数据路径、端口无冲突
3. **本地开发友好** - Mock/内存后端支持
4. **可观测性集成** - 复用现有 VictoriaMetrics + Grafana

### 20.2 服务架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      deploy/derived/                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐       ┌─────────────────────┐          │
│  │     QuestDB         │       │      Kvrocks        │          │
│  │     :9000 (HTTP)    │       │     :6666 (Redis)   │          │
│  │     :8812 (PG)      │       │                     │          │
│  │                     │       │   RocksDB 持久化    │          │
│  │   Hot 层时序数据    │       │   增量状态/Checkpoint│          │
│  └─────────┬───────────┘       └─────────┬───────────┘          │
│            │                             │                       │
│            └─────────────┬───────────────┘                       │
│                          ▼                                       │
│            ┌──────────────────────────────┐                      │
│            │   /opt/ditto/data/           │                      │
│            │   ├── questdb/               │                      │
│            │   └── kvrocks/               │                      │
│            └──────────────────────────────┘                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 20.3 Docker Compose 配置

**`deploy/derived/docker-compose.yml`**:

```yaml
version: "3.8"

services:
  questdb:
    image: questdb/questdb:8.2.1
    container_name: ditto-questdb
    restart: unless-stopped
    ports:
      - "9000:9000"   # Web Console + REST API
      - "8812:8812"   # PostgreSQL wire protocol
    volumes:
      - /opt/ditto/data/questdb:/root/.questdb
      - ./questdb/server.conf:/root/.questdb/conf/server.conf:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/status"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
    networks:
      - ditto-derived

  kvrocks:
    image: apache/kvrocks:2.9.0
    container_name: ditto-kvrocks
    restart: unless-stopped
    ports:
      - "6666:6666"
    volumes:
      - /opt/ditto/data/kvrocks:/var/lib/kvrocks
      - ./kvrocks/kvrocks.conf:/etc/kvrocks/kvrocks.conf:ro
    command: ["./kvrocks", "-c", "/etc/kvrocks/kvrocks.conf"]
    healthcheck:
      test: ["CMD", "redis-cli", "-p", "6666", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 256M
    networks:
      - ditto-derived

networks:
  ditto-derived:
    driver: bridge
```

### 20.4 配置文件

**QuestDB 配置** (`deploy/derived/questdb/server.conf`):

```conf
# HTTP 服务
http.enabled=true
http.bind.to=0.0.0.0:9000

# PostgreSQL wire protocol
pg.netty.enabled=true
pg.netty.bind.to=0.0.0.0:8812
pg.user=admin
pg.password=${QUESTDB_PASSWORD}

# O3 列存储（时序优化）
cairo.o3.enabled=true
cairo.o3.max.lag=86400000

# 写入优化
cairo.commit.lag=10000
cairo.max.uncommitted.rows=1000
```

**Kvrocks 配置** (`deploy/derived/kvrocks/kvrocks.conf`):

```conf
bind 0.0.0.0
port 6666
daemonize no
dir /var/lib/kvrocks

requirepass ${KVROCKS_PASSWORD}

# RocksDB 调优
rocksdb.compression snappy
rocksdb.write_buffer_size 64mb
rocksdb.max_write_buffer_number 4
rocksdb.target_file_size_base 64mb

# 持久化
rocksdb.wal_recovery_mode 1

# 内存管理
maxmemory 200mb
maxmemory-policy allkeys-lru
```

### 20.5 资源配置

| 服务 | 内存限制 | 磁盘预估 | 用途 |
|------|----------|----------|------|
| QuestDB | 512MB | ~1GB | Hot 层时序数据 |
| Kvrocks | 256MB | ~50MB | 增量状态 |
| **总计** | **768MB** | **~1.1GB** | |

### 20.6 本地开发测试方案

#### 测试分层策略

| 测试类型 | QuestDB | Kvrocks | 场景 |
|----------|---------|---------|------|
| **单元测试** | 自实现 Mock | fakeredis | 快速、隔离 |
| **集成测试** | testcontainers | fakeredis | 真实行为验证 |

#### 依赖配置

```toml
# pixi.toml
[feature.dev.dependencies]
fakeredis = ">=2.30.0"
testcontainers = ">=4.0.0"
```

#### Kvrocks Mock（fakeredis）

```python
import fakeredis

def create_mock_kvrocks() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()
```

#### QuestDB 集成测试（testcontainers）

```python
import pytest
from testcontainers.core.generic import GenericContainer

@pytest.fixture(scope="session")
def questdb_container():
    container = GenericContainer("questdb/questdb:8.2.1")
    container.with_exposed_ports(9000, 8812)
    container.with_env("QDB_PG_USER", "admin")
    container.with_env("QDB_PG_PASSWORD", "test")
    container.start()

    yield {
        "http_url": f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}",
        "pg_url": f"postgresql://admin:test@{container.get_container_host_ip()}:{container.get_exposed_port(8812)}/qdb",
    }

    container.stop()
```

### 20.7 文件清单

```
deploy/derived/
├── docker-compose.yml      # 主部署文件
├── .env.example            # 环境变量模板
├── README.md               # 使用说明
├── questdb/
│   └── server.conf         # QuestDB 配置
└── kvrocks/
    └── kvrocks.conf        # Kvrocks 配置
```

### 20.8 决策摘要

| 决策点 | 决策 | 理由 |
|--------|------|------|
| 部署方式 | Docker Compose | 与现有架构一致 |
| 数据路径 | `/opt/ditto/data/` 统一 | 管理便捷 |
| QuestDB 端口 | 9000(HTTP), 8812(PG) | 默认端口无冲突 |
| Kvrocks 端口 | 6666 | 默认端口 |
| 单元测试 Mock | fakeredis + 自实现 | 轻量快速 |
| 集成测试 | testcontainers | 真实行为验证 |

---

## 25. ADR-021: PIT 一致性与因子引擎集成

**状态**: 已决策（2026-03-05）

**背景**:

因子计算必须保证 PIT（Point-in-Time）一致性，防止前瞻偏差。当前项目已有 PIT 基础设施，需要确定因子引擎如何集成。

### 21.1 决策要点

| 决策项 | 决策 | 理由 |
|--------|------|------|
| FactorSpec PIT 声明 | 不需要显式声明，默认支持 PIT | 简化因子定义，由引擎自动处理 |
| pit_columns 位置 | 从 SourceSchema 迁移到 StoreSchema | PIT 列是存储层概念，数据源不产生 |
| PIT 查询策略 | 引擎根据 StoreSchema.pit_columns 自动生成过滤 | 统一处理，避免遗漏 |

### 21.2 pit_columns 类型

| pit_columns 值 | PIT 类型 | 查询条件 |
|----------------|----------|----------|
| `("effective_from", "effective_to")` | 双时间戳版本化 | `effective_from <= as_of AND (effective_to IS NULL OR effective_to > as_of)` |
| `("knowledge_date",)` | 知识日期 | `knowledge_date <= as_of` |
| `()` | 无需 PIT | 直接用 `trade_date` |

### 21.3 引擎执行流程

```
1. 解析表达式 → 提取数据集引用
2. 查找 StoreSchema → 获取 pit_columns
3. 根据 pit_columns → 自动生成 PIT 过滤条件
4. 执行查询 → 返回 PIT 安全的数据
```

### 21.4 待办事项

- [ ] 迁移 `pit_columns` 从 `SourceSchema` 到 `StoreSchema`
- [ ] 更新所有现有 Schema 定义
- [ ] 因子引擎集成 PIT 自动过滤逻辑
- [ ] 添加 PIT 验证测试

### 21.5 示例

```python
# StoreSchema 定义
BALANCE_SHEET_STORE_SCHEMA = StoreSchema(
    dataset="fundamental/balance_sheet",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={...},
    pit_columns=("effective_from", "effective_to"),  # 迁移后
)

# FactorSpec - 无需显式 PIT 声明
FactorSpec(
    name="pe_ratio",
    expr="market.close * shares / fundamental.net_income",
    # 引擎自动根据数据集 pit_columns 处理
)
```

---

## 26. ADR-022: 更正数据处理

**状态**: 已决策（2026-03-05）

**背景**:

历史数据被修正后，依赖该数据的因子需要级联更新以保证正确性。

### 22.1 核心决策

| 决策项 | 决策 | 理由 |
|--------|------|------|
| 重算策略 | 全量重算 | 数据正确性优先，可接受历史信号变化 |
| 依赖追踪粒度 | 数据集级 | 简化实现，重算范围略大但可接受 |
| 批处理模式 | 依赖 DAG 调度 | 离线批任务按依赖顺序执行，无需额外级联 |
| 实时流模式 | 显式级联触发 | 需要检测修正并触发依赖因子重算 |

### 22.2 批处理 vs 实时流

| 模式 | 修正处理方式 | 级联机制 |
|------|-------------|----------|
| **批处理** | 离线批任务 DAG 依赖执行 | 下次批处理时自然更新，无需显式级联 |
| **实时流** | 实时检测修正数据 | 需要显式级联触发重算 |

**批处理流程**：
```
Tushare 数据修正 → 下次 T1 摄取 → T2 特征物化 → T3 因子物化
                    (DAG 依赖自动触发)
```

**实时流流程**：
```
实时数据修正 → 检测到 effective_from 变更 → 查找依赖数据集的因子 → 触发重算
```

### 22.3 依赖追踪设计（数据集级）

```python
# Catalog dependency 表记录
# factor_pe_ratio 依赖 fundamental.balance_sheet
# factor_roe 依赖 fundamental.balance_sheet
# 当 balance_sheet 修正时，查找所有依赖因子触发重算
```

### 22.4 待办事项

- [ ] 批处理：确保 DAG 依赖正确配置
- [ ] 实时流：实现修正检测与级联触发逻辑
- [ ] 添加依赖关系追踪到 Catalog

---

## 27. ADR-023: 灾备恢复策略

**状态**: 暂缓（Phase 2 再评估）

**背景**:

QuestDB（时序存储）和 Kvrocks（状态存储）故障后的恢复流程需要考虑。

### 23.1 数据持久化分析

| 数据类型 | 存储位置 | 能否从 Parquet 重建 |
|----------|----------|-------------------|
| **日频数据** | Parquet + QuestDB | ✅ 可重建 |
| **特征/因子** | Parquet + QuestDB | ✅ 可重建 |
| **分钟级数据** | 仅 QuestDB（实时流） | ❌ 无法重建（当前无法回放） |

### 23.2 决策

| 决策项 | 决策 | 理由 |
|--------|------|------|
| 灾备策略 | 暂不实现 | 单机部署，依赖存储引擎自身持久化 |
| 分钟级数据丢失 | 接受 | 实时数据有时效性，Phase 2 再评估备份方案 |
| 极端情况 | 从数据源全量重建 | 禂率低，可接受 |

### 23.3 Phase 2 待评估项

- [ ] 分钟级数据是否需要双写 Parquet 作为冷备份（存储翻倍)
- [ ] 分钟级数据是否需要 WAL 日志支持回放（增加复杂度）
- [ ] 是否需要定期备份策略

**结论**：
- 当前阶段不做特殊灾备设计
- 依赖存储引擎自身的持久化能力
- 极端情况接受从数据源全量重建
- 如果未来有需求，再考虑备份策略
- [ ] 是否需要 WAL 日志支持回放
- [ ] 是否需要定期备份策略

### 23.4 当前策略

- 依赖 QuestDB/Kvrocks 自身的磁盘持久化
- 进程崩溃后重启自动恢复
- 磁盘损坏等极端情况接受全量重建

---

## 28. ADR-024: 因子版本管理

**状态**: 已决策（2026-03-05）

**背景**:

因子计算逻辑会随时间演进，需要一套版本管理机制来处理：
1. 因子逻辑变更后的历史数据如何处理
2. 多版本因子如何共存（A/B 测试场景）
3. 如何安全地切换和归档版本

参考了业界最佳实践：
- **MLflow Model Registry**: Stage 指针机制（Production/Staging/Archived）
- **Feast Feature Store**: Feature View 版本化 + Point-in-Time 正确性
- **Git 分支指针**: 可移动的引用，指向具体版本

### 24.1 核心概念

```
Factor Family（因子族）
    │
    ├── pe_ratio@v1  (status: active, online: false, primary: false)
    ├── pe_ratio@v2  (status: active, online: true,  primary: true)  ← primary 指针
    └── pe_ratio@v3  (status: draft,  online: false, primary: false)
```

**唯一标识**：`因子名@版本`，如 `pe_ratio@v2`

**状态维度**：
| 字段 | 说明 | 取值 |
|------|------|------|
| `status` | 生命周期状态 | draft / active / deprecated / archived |
| `online` | 显式上线状态 | true / false |
| `primary` | 查询默认指针 | true / false |
| `referenced_by` | 被引用列表 | ["strategy_alpha_001"] |

**指针语义**：
- `primary=true` 决定查询时的默认返回版本
- 同一因子族只能有一个 `primary=true`
- `primary` 不影响调度计算，仅影响查询默认值

### 24.2 调度与查询语义

| 操作 | 行为 |
|------|------|
| **默认调度** | 计算所有 `status != archived` 的因子 |
| **指定因子族** | `--id pe_ratio` 计算该族所有未归档版本 |
| **指定版本** | `--id pe_ratio@v2` 只计算 v2 |
| **查询默认** | `get_factor("pe_ratio")` 返回 primary 版本 |
| **查询版本** | `get_factor("pe_ratio@v1")` 返回 v1 |

### 24.3 可修改性约束

```
可以直接修改 ⇔ online == false 且 referenced_by 为空

可以下线 ⇔ referenced_by 为空
```

**约束矩阵**：
| online | referenced_by | 能直接修改 | 能下线 |
|--------|---------------|-----------|--------|
| false | 空 | ✅ | - |
| true | 有 | ❌ | ❌ 先解除引用 |
| true | 空 | ❌ | ✅ |

### 24.4 操作命令

```bash
# 新建版本
ditto factor create --id pe_ratio --expression "新公式"

# 直接修改（仅 draft 状态可用）
ditto factor update --id pe_ratio@v3 --expression "调整公式"

# 补数据（任意版本可独立执行）
ditto factor backfill --id pe_ratio@v3 --start 2024-01-01

# 上线
ditto factor online --id pe_ratio@v3

# 下线（需 referenced_by 为空）
ditto factor offline --id pe_ratio@v2

# 切换 primary 指针
ditto factor set-primary --id pe_ratio@v3

# 切换 + 同时下线旧版本
ditto factor set-primary --id pe_ratio@v3 --offline-old

# 归档（需 online=false）
ditto factor archive --id pe_ratio@v2
```

### 24.5 典型工作流

```
场景：v2 → v3 升级

Step 1: 创建 v3（draft 状态）
        ditto factor create --id pe_ratio --expression "close * market_cap / net_profit"

Step 2: 验证 v3（draft 可直接修改调整）
        ditto factor backfill --id pe_ratio@v3 --start 2024-01-01
        ditto factor validate --id pe_ratio@v3
        （反复调整直到满意）

Step 3: 上线 v3
        ditto factor online --id pe_ratio@v3

Step 4: 切换 primary
        ditto factor set-primary --id pe_ratio@v3
        # 或同时下线旧版本
        ditto factor set-primary --id pe_ratio@v3 --offline-old

Step 5: 归档 v2（可选）
        ditto factor offline --id pe_ratio@v2   # 如果之前没下线
        ditto factor archive --id pe_ratio@v2
        # 7天后自动删除 v2 数据
```

### 24.6 删除策略

- `status == archived` 的因子数据保留 **7 天**
- 7 天后自动清理（数据文件 + Catalog 记录）
- 可手动提前删除

### 24.7 数据模型

```python
class FactorVersion(BaseModel):
    entity_id: str           # "pe_ratio"
    version: int             # 2

    # 生命周期状态
    status: Literal["draft", "active", "deprecated", "archived"]
    online: bool             # 显式上线状态

    # 指针与引用
    primary: bool            # 是否是当前指针（仅影响查询默认值）
    referenced_by: list[str] # 手动声明的引用列表

    # Spec
    expression: str
    spec_hash: str

    # 元信息
    created_at: datetime
    created_by: str

    @property
    def full_id(self) -> str:
        return f"{self.entity_id}@v{self.version}"
```

### 24.8 Catalog 扩展

```sql
-- 在 derived_spec 表中增加字段
ALTER TABLE derived_spec ADD COLUMN online INTEGER NOT NULL DEFAULT 0;
ALTER TABLE derived_spec ADD COLUMN primary INTEGER NOT NULL DEFAULT 0;
ALTER TABLE derived_spec ADD COLUMN referenced_by TEXT DEFAULT '[]';

-- 索引
CREATE INDEX idx_spec_online ON derived_spec(entity_type, entity_id, online);
CREATE INDEX idx_spec_primary ON derived_spec(entity_type, entity_id, primary) WHERE primary = 1;
```

### 24.9 设计决策总结

| 维度 | 决策 |
|------|------|
| **版本标识** | `因子名@版本` |
| **调度范围** | `status != archived` |
| **查询默认** | `primary=true` 的版本 |
| **状态流转** | draft → active(online) → offline → archived |
| **修改约束** | `online=false` 且 `referenced_by=[]` |
| **下线约束** | `referenced_by=[]` |
| **引用追踪** | 手动声明 |
| **切换操作** | 独立操作，可选 `--offline-old` |
| **迁移操作** | 独立 backfill，不与切换耦合 |
| **删除策略** | archived 7 天后自动清理 |

### 24.10 待办事项

- [ ] 扩展 `derived_spec` 表结构（online, primary, referenced_by）
- [ ] 实现 CLI 命令（create/update/online/offline/set-primary/archive）
- [ ] 实现调度器按 `status != archived` 拉取因子列表
- [ ] 实现 primary 指针查询解析逻辑
- [ ] 实现归档 7 天后自动删除逻辑
- [ ] 添加版本管理相关测试
