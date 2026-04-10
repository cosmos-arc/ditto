# Ditto 统一特征/因子引擎最终落地设计（2026-03-04）

## 0. 文档信息

- **状态**: 基线主设计（后续控制面与治理收敛以较新的 ADR 与整改方案为准）
- **作者**: Codex（基于当前仓库代码与用户方案整合）
- **适用范围**: `packages/core` + `packages/data` + `apps/port`
- **当前配套文档**:
  - `docs/design/unified-feature-factor-engine/decisions/adr-032` ~ `adr-043`
  - `docs/plans/2026-03-13-unified-feature-factor-engine-remediation-design.md`
- **约束前提**:
  - 不引入 Bronze/Silver/Gold/Platinum 命名
  - 不引入 Iceberg/Delta/Hudi
  - 保持现有 Ditto 分层与 DataHub 路径体系一致

> **说明**: 本文档是 2026-03-04 的基线主设计。若与 2026-03-12 之后新增的控制面 ADR、文档收敛整改方案存在冲突，以较新的 ADR 和整改方案为准。

---

## 0.1 核心原则（Four Iron Rules）

> 这些原则是整个因子引擎设计的基础约束，所有架构决策必须服从这些原则。

### 原则一：Single Source of Truth（唯一真相源）

**Parquet 是历史数据的唯一真相源。**

- QuestDB/Others 热层仅作为查询加速层，不承担数据持久化责任
- 所有历史回看、回补、灾备恢复均以 Parquet 为基准
- 热层数据丢失后，通过上游重放或 Parquet 历史数据重建

### 原则二：Hot Layer Stores Only Necessary Lookback（热层最小化）

**热层只存储必要的回看窗口，不做全量镜像。**

- 分钟线数据：仅保留最近 N 个交易日（可配置，默认 5 日）
- 日线数据：仅保留最近 M 个交易日（可配置，默认 30 日）
- 标准化 `bar_1m` 与最小必要 replay / audit 元数据在 Parquet 额外保留 30 天，用于回放与重建
- TTL 只承担回收，不承担 invalidation 或发布正确性
- 在线查询默认不因热层 TTL 自动降级到 Parquet；研究/审计路径需显式进入离线或降级模式

### 原则三：State/Analysis Separation（状态与分析分离）

**因子状态与查询分析走不同路径。**

- **状态路径**：因子最新控制面状态与 latest snapshot 存储在 Kvrocks，用于增量计算、水位追踪与冷启动
- **服务查询路径**：latest / serving 查询默认走 QuestDB / Kvrocks 热层，不与状态存储耦合
- **研究数据集路径**：PIT 提取与训练数据集构建显式读取 Parquet / artifact 真相层
- 状态变更不影响历史数据，仅影响增量计算边界

### 原则四：Unified Semantics with Layered Physical Execution（统一语义、分层执行）

**上层语义统一，底层物理执行分层。**

- **统一语义**：用户通过统一的 DSL/CLI/API 表达因子计算意图
- **分层执行**：引擎根据 FactorServeMode 选择不同的物理执行路径
  - `SERIES`：纯时序，走 QuestDB ILP 高速写入
  - `STATE`：状态类，走 Kvrocks 状态存储
  - `DERIVE`：派生类，走 DuckDB ADHOC 计算
  - `OFFLINE`：离线类，仅走 Parquet 批处理
- 查询时自动路由到合适的存储层，用户无感知

---

## 1. 设计目标与非目标

### 1.1 目标

1. 统一 Feature 与 Factor 的计算、物化、增量、发布流程。
2. 建立 Pratt 表达式引擎与静态分析能力，支持 `deps/lookback/scope/requires_full_day` 推导。
3. 全量与增量逻辑收敛到同一执行引擎，仅由 `RunConfig` 改变执行边界。
4. 与当前 Ditto 架构和命名兼容：`market/fundamental/capital/macro/features/factors/runtime`。
5. 保障本地盘并发写的一致性：锁 + 原子提交 + Catalog 事务更新。

### 1.2 非目标

1. 不做分布式计算调度（Spark/Flink/K8s）。
2. 不做 lakehouse 表格式事务层。
3. 不在当前阶段实现复杂 DSL 语言特性（宏、模块、用户函数脚本化）。
4. 不修改现有 T0/T1/T2/T3 主摄取职责，仅在其后挂接衍生物化。

---

## 2. 对用户方案的评估与最终裁决

### 2.1 结论摘要

用户方案整体方向正确，尤其是以下三点应完整采纳：

1. **表达式先编译后执行**（Pratt + AST + Analyzer + Codegen）。
2. **统一全量/增量执行链路**（仅边界规划不同）。
3. **静态分析驱动增量裁剪**（lookback/requires_full_day 是关键）。

同时需做四项仓库对齐调整：

1. 命名与目录必须使用 Ditto 现有域，不采用 Bronze/Silver/Gold/Platinum。
2. DataHub 当前主分区是按年（`YYYY.parquet`），第一阶段先兼容年分区，再演进到 year/month。
3. 现有 Feature/Factor Service 偏查询，需要补齐 Materialize 写入 API。
4. Catalog 不能只保留单表最简版，至少要有 run 与 state 维度，才能支持可观测与重试。

### 2.2 评估矩阵

| 议题 | 用户方案 | 最终决策 | 原因 |
|---|---|---|---|
| 分层命名 | Bronze/Silver/Gold/Platinum | 改为现有 Domain 命名 | 与现有路径、团队认知、代码一致 |
| 计算语言 | Pratt DSL | 采纳 | 满足量化公式与静态分析 |
| 执行引擎 | Polars | 采纳 | 现有栈已使用 Polars |
| 增量机制 | watermark-lookback 覆盖写 | 采纳 | 本地盘可控、实现成本低 |
| 分区策略 | year/month | **阶段化**：先 year，后 year/month | 与现有 `YearlyPartition` 兼容 |
| Catalog | 单表 | 扩展为多表 | 需要 run-level 可追踪性 |
| 并发控制 | 锁 + rename | 采纳并细化锁键 | 匹配现有 `FileLockManager` |
| 事务一致性 | 文件与元数据一致 | 采纳 | 防止"数据写了但 catalog 未更新" |

### 2.3 取长补短融合版

#### A. 直接沿用你方案（保持不改）

1. `Pratt Parser -> AST -> Analyzer -> Polars` 的编译链路。
2. TS/CS 作用域模型与 `requires_full_day` 语义。
3. 增量算法核心：`watermark - lookback` 回退预热 + 覆盖写分区。
4. 因子默认标准化管线：`cs_rank -> cs_zscore`。
5. 因子 PIT 强制化（`effective_from/effective_to`）。

#### B. 补强的落地项（保证可工程化）

1. 与 Ditto 现有 Domain 命名对齐，不引入 Bronze/Silver/Gold/Platinum。
2. 以当前 `YearlyPartition` 为第一阶段兼容基线，避免一次性改造所有读写链路。
3. Catalog 从"单表"提升为 `spec/state/run/partition/invalidation`，保证重试、追踪、排障可用。
4. 增加 Artifact 层，兼顾"版本复现"与现有 Serving 路径兼容。
5. 明确锁粒度和提交顺序，确保本地盘并发写不会出现元数据漂移。
6. 在 Port 层引入 materialization flow，不破坏现有 `T0/T1/T2/T3` 摄取职责边界。

#### C. 暂缓项（后续版本）

1. 分布式计算框架接入。
2. lakehouse 表格式（Iceberg/Delta/Hudi）。
3. DSL 高级语法（宏、模块系统、用户扩展函数）。
4. 全面切换到 year/month serving 分区（先通过 artifact 验证收益）。

---

## 3. 仓库现状对齐（As-Is）

### 3.1 架构边界（必须遵守）

1. 分层由 Import Linter 强约束：`Port -> Core -> DataHub -> Infra`。
2. Core 对 DataHub 依赖受限，当前规则仅放行 `ditto_data.models.*`。
3. Port 运行路径不允许直接访问 DataHub stores/runtime（registry 装配例外）。

### 3.2 现有数据与任务结构

1. 摄取编排已实现 `T0_META -> T1_INCREMENTAL -> T3_QUALITY`。
2. 存储路径已稳定：
   - `features/technical/indicators_narrow`
   - `factors/factors_narrow`
3. Runtime 已有：
   - `FileLockManager`
   - `FreezeManager`
   - `ingestion_log`

### 3.3 当前短板

1. `FeatureService/FactorService` 主要是查询接口，缺少 materialize 级别写入契约。
2. 缺少统一表达式引擎、Spec、执行计划、增量失效集模型。
3. 摄取日志表不足以承载衍生物化的版本与水位元数据。
4. Feature/Factor provider 传入路径存在与 store 内 `_dataset` 重复拼接风险（需优先修正）。

---

## 4. 最终架构（To-Be）

### 4.1 分层职责

#### A. `apps/port`（应用编排层）

1. 接收 CLI/API/Flow 请求，组装 `RunConfig`。
2. 调度 `MaterializeService` 执行 feature/factor 物化。
3. 处理发布（latest 指针）、报告、告警。

#### B. `packages/core`（计算引擎层，新增核心能力）

1. `ExpressionEngine`：Pratt 编译链路。
2. `Analyzer`：静态分析与增量边界推导。
3. `FeatureEngine`/`FactorEngine`：执行计划 + 标准化 + PIT 规整。
4. `NormalizationPipeline`：`cs_rank/cs_zscore/winsorize/neutralize`。

#### C. `packages/data`（存储与元数据层）

1. 读取 source domains 输入数据。
2. 写入 derived domains（features/factors）。
3. 管理 Catalog（spec/version/watermark/run/coverage/partition stats）。
4. 通过锁与原子提交保障一致性。

#### D. `packages/infra`（横切能力）

1. 文件锁、原子写、日志、指标、追踪。
2. 提供可复用并发与 I/O 原语。

### 4.2 端到端数据流

```text
T1 摄取完成
  -> materialize_features (full/inc)
  -> materialize_factors  (full/inc)
  -> minimal_dq
  -> compatibility_manifest
  -> shadow_publish / dual_read_diff
  -> certify / promote / latest
```

研究与生产均走同一条链路，只是 `mode`、`coverage`、`universe_policy` 不同。

---

## 5. 模块设计与文件落点

### 5.1 Core 新增模块

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

### 5.2 DataHub 新增模块

建议目录：

```text
packages/data/src/ditto_data/
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

### 5.3 Port 新增模块

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

### 6.1 Spec 模型（Core）

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
    # PIT 由引擎根据 StoreSchema.pit_columns 自动处理（见 ADR-021）
    output_columns: list[str] = Field(default_factory=lambda: ["value"])

class FactorSpec(BaseSpec):
    # PIT 由引擎根据 StoreSchema.pit_columns 自动处理（见 ADR-021）
    normalization_pipeline: list[NormalizationStage] = Field(
        default_factory=lambda: [
            NormalizationStage(method="cs_rank"),
            NormalizationStage(method="cs_zscore"),
        ]
    )
```

> **补充说明**:
> 1. 统一语义根模型、`entity_keys/calendar/grain/time_keys` 的正式定义以 [ADR-032](decisions/core/adr-032-unified-derived-semantic-model.md) 为准。
> 2. 研究/训练左表契约与数据集快照不并入 `FeatureSpec/FactorSpec`，而是由 [ADR-041](decisions/research/adr-041-research-dataset-spine-availability-contract.md) 定义 `SpineSpec`、`ResearchDatasetSpec`、`DatasetSnapshot`。

### 6.2 RunConfig（应用层传入）

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

### 6.3 MaterializeResult（统一输出）

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

### 7.1 编译链路

```text
expression(str)
  -> Lexer(tokens with span)
  -> Pratt Parser(AST)
  -> Analyzer(deps/scope/lookback/requires_full_day)
  -> DAG/CSE(可选优化)
  -> Codegen(Polars Expr / Lazy plan)
  -> ExecutionPlan
```

### 7.2 AST 节点

1. `Const(value)`
2. `Column(name, namespace)`:
   - `$close`（市场列）
   - `$$pe_ttm`（PIT/基本面列）
3. `Call(name, args, kwargs)`
4. `Unary(op, expr)`
5. `Binary(op, left, right)`

### 7.3 算子元信息（OperatorRegistry）

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

### 7.4 作用域与嵌套规则

> 详细设计见 [ADR-001: TS/CS 嵌套策略](decisions/adr-001-ts-cs-nesting.md)

1. TS 算子：`Ref/Mean/Std/Delta/PctChange`
2. CS 算子：`CSRank/CSZScore/Neutralize`
3. **支持任意合法嵌套**（自动分层执行）：
   - `TS(CS(x))` - 如 `ts_rank(rank(low), 9)`
   - `CS(TS(x))` - 如 `rank(ts_delta(close, 20))`
   - `TS(CS(x), CS(y))` - 如 `correlation(rank(open), rank(volume), 10)`
4. 编译期属性自动推导：
   - `lookback`、`requires_full_day`、`scope` 向上传播
   - 若子表达式 `requires_full_day=True`，父表达式继承该约束

### 7.5 Lookback 与边界推导

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

### 8.1 FeatureEngine

输入：source domain DataFrame（通常来自 market/capital/fundamental）。

流程：

1. 解析并编译 expression。
2. 按 execution plan 计算 `value` 或多列输出。
3. 可选标准化（feature 默认不做 CS 标准化）。
4. 输出并交由 DataHub writer 落盘与记录 catalog。

### 8.2 FactorEngine

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

### 9.1 Full 模式

1. 输入 `[request_start, request_end]`。
2. `compute_start = request_start - lookback`（交易日意义）。
3. 计算后截断仅写 `[request_start, request_end]`。

### 9.2 Incremental 模式

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
2. 若 `requires_full_day=True`，对受影响日做"整日全截面"重算。

### 9.3 Invalidation 机制

来源：

1. source domain 写入后的 `snapshot_id` 与变更摘要。
2. 复权、PIT 修订、基础面重述、公司行为追溯等。

扩展规则：

1. TS 因子：以 `(instrument_id, date)` 为粒度扩展 lookback。
2. CS 因子：任一标的变化会放大为该 `trade_date` 全截面。

---

## 10. PIT 语义与实现

遵循现有 PIT 规则：`as_of_date in [effective_from, effective_to)`。

### 10.1 何时强制 PIT

1. Factor：强制 PIT。
2. Feature：
   - 技术类可选 PIT（默认 false）
   - 基本面衍生必须 PIT（true）

### 10.2 规则

1. 新版本写入时：
   - 旧记录 `effective_to` 被截断到新记录 `effective_from`
2. 查询时：
   - `effective_to` 为 null 表示当前有效

### 10.3 场景

1. 行情类：通常 `effective_from = trade_date`。
2. 基本面：`effective_from = knowledge_date/announcement_date`。
3. 修订：会导致历史窗口回溯重算。

### 10.4 Availability-Time 与研究数据集

在研究/训练链路中，PIT 不仅依赖 `effective_from/effective_to`，还需要显式区分：

1. `event_time`：业务事件发生时间。
2. `availability_time`：该数据在系统中可被合法读取的最早时间。
3. `known_at`：某个样本行构建时允许读取数据的上界。

默认规则：

1. 研究数据集构建使用 `SpineSpec` 作为左表，保留左表样本基数。
2. join 时只允许读取 `availability_time <= known_at` 的记录。
3. 迟到数据默认触发新 `DatasetSnapshot` 或重建，不静默改写既有快照。

---

## 11. 存储与 Catalog 设计（DataHub）

### 11.1 目录策略（最终）

#### A. Serving 路径（兼容现有）

1. `features/technical/indicators_narrow/YYYY.parquet`
2. `factors/factors_narrow/YYYY.parquet`

#### B. Artifact 路径（新增，版本化工件）

```text
runtime/materialization/artifacts/
  features/{feature_id}/spec={spec_hash}/year=YYYY/month=MM/part-*.parquet
  factors/{factor_id}/spec={spec_hash}/year=YYYY/month=MM/part-*.parquet
```

说明：

1. Serving 层继续服务查询兼容。
2. Artifact 层用于可复现与离线排障。
3. 标准化 `bar_1m` 与 replay / audit 元数据额外保留 30 天，用于热层回补与审计。
4. 发布时将 artifact 同步/投影到 serving 层（或直接双写），但热层投影不是长期权威副本。

### 11.2 元数据（metadata.json）

每次物化工件目录写入：

```json
{
  "entity_type": "factor",
  "entity_id": "alpha_001",
  "version": 3,
  "spec_hash": "xxxx",
  "engine_version": "expr-v0",
  "compatibility_manifest": {
    "engine_codegen_version": "v1",
    "analysis_version": "v1",
    "polars_version": "1.38.1",
    "expr_serialization_format": "polars-binary-v1",
    "operator_fingerprint": "sha256:abcd",
    "time_semantics_version": "v1"
  },
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

### 11.3 Catalog 存储架构

> 详细设计见 [ADR-010: Catalog 完整表结构与存储架构](decisions/adr-010-catalog-schema.md)

采用 **SQLite + Kvrocks 混合方案**：

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
│   │
│   └── derived.sqlite           # 物化层
│       ├── derived_run          # 运行历史
│       └── derived_partition    # 分区元数据
│
└── (Kvrocks)                    # 状态存储
    ├── ditto:derived:state:{entity_type}:{entity_id}  # watermark, coverage, latest_run
    ├── ditto:derived:state:{entity_type}:{entity_id}:snapshot:{instance_key}
    ├── ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}
    └── ditto:derived:invalidation:{id}  # 失效队列
```

**SQLite 表结构（derived.sqlite）**：

```sql
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
```

**Kvrocks Key 结构**：

```
ditto:derived:state:{entity_type}:{entity_id}
    → JSON {watermark, coverage_start, coverage_end, coverage_gaps, latest_run_id, updated_at}

ditto:derived:state:{entity_type}:{entity_id}:snapshot:{instance_key}
    → HASH/BLOB {value/state payload, ts, trade_date, calc_ver}

ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}
    → JSON {status, rows_written, checksum, started_at, completed_at}（TTL 7 天）

ditto:derived:invalidation:{priority}:{timestamp}:{id}
    → JSON {entity_type, entity_id, trigger_source, affected_range, status}
```

---

## 12. 并发与原子提交策略

### 12.1 锁粒度

推荐锁键：

1. 计算锁：`derived/{entity_type}/{entity_id}/v{version}`
2. 分区写锁：`derived/{entity_type}/{entity_id}/v{version}/{partition_key}`

规则：

1. 同 `entity_id + version` 串行。
2. 不同实体可并行。
3. 读操作无锁或短锁。

### 12.2 提交顺序（必须）

1. 获取锁（Kvrocks 分布式锁）。
2. 计算并写临时目录。
3. 校验（schema/row_count/checksum）。
4. 原子替换目标分区（同文件系统 rename）。
5. SQLite 事务写入 `derived_partition + derived_run`。
6. Kvrocks 写入 `ditto:derived:state:*`、`ditto:derived:state:*:snapshot:*` 和 `ditto:derived:checkpoint:*`。
7. 提交事务，释放锁。

### 12.3 故障恢复

1. RUNNING 超时 run 自动标记 FAILED。
2. 清理孤儿临时目录。
3. 基于 `derived_run` 支持幂等重跑。

---

## 13. 与现有摄取流程集成

### 13.1 Flow 级集成策略

1. 保持现有 `daily_ingestion_flow` 不变。
2. 新增 `daily_materialization_flow`：
   - 输入：trade_date, mode, ids
   - 输出：features/factors 物化结果
3. 组合 `daily_pipeline_flow`：
   - `daily_ingestion_flow` 成功后触发 `daily_materialization_flow`

### 13.2 T2_REPAIR / backfill 集成

1. repair/backfill 完成后，生成对应 source snapshot invalidation。
2. 触发受影响实体的增量重算。
3. 对 `requires_full_day` 因子按日全截面回补。

### 13.3 CLI 设计

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

### 14.1 指标

1. `materialize_run_total{entity_type,status}`
2. `materialize_duration_seconds`
3. `materialize_rows_written`
4. `materialize_null_rate`
5. `materialize_watermark_lag_days`

### 14.2 日志字段

每次 run 至少记录：

1. `run_id`
2. `entity_type/entity_id/version/spec_hash`
3. `request_start/end`
4. `compute_start/end`
5. `lookback/requires_full_day`
6. `partitions_written`

### 14.3 DQ 最小规则

1. schema 校验（关键列/类型）。
2. 空值率阈值阻断。
3. 新鲜度门禁（`freshness_sla`）。

这些规则只构成“最小 DQ”，用于阻断明显坏数据；不承担完整发布安全认证。

### 14.4 发布安全与认证治理

1. `shadow_publish` 不新增生命周期状态，candidate 仍保持 `MATERIALIZED`。
2. `dual_read_diff` 负责对比 candidate 与 baseline 的 value / coverage / latency / fallback 等差异。
3. `shadow_ready` 与 `publish_ready` 作为认证 gate，建立在最小 DQ、shadow diff 与 compatibility manifest 之上。
4. `CompatibilityManifest` 必须进入 artifact metadata、publication record 与 dataset snapshot。

---

## 15. 约束一致性（架构与工程规则）

### 15.1 分层一致性

1. Port 编排，Core 计算，DataHub 存储。
2. Core 不直接操作文件系统。
3. DataHub 不依赖 Core。

### 15.2 现有路径一致性

1. 继续以 `DataStoreSettings` 为唯一路径真源。
2. 修复 provider 中"已拼接路径 + store 内 `_dataset` 再拼接"的不一致问题。

### 15.3 PIT 一致性

严格使用半开区间语义：

```text
effective_from <= as_of_date < effective_to(or null)
```

---

## 16. 分阶段实施计划（可直接执行）

### Phase 0（1-2 周）：内核可跑通

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

### Phase 1（2-3 周）：增量与并发完善

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

### Phase 2（3-4 周）：PIT 与研究生产闭环

目标：研究/生产统一。

交付：

1. 基本面修订触发区间回算。
2. feature_sets 宽表输出。
3. publish/latest 与回滚机制。
4. `SpineSpec` / `ResearchDatasetSpec` / `DatasetSnapshot` 研究数据集闭环。
5. shadow publish / dual-read diff / role-profile certification 控制面闭环。
6. 丰富算子与标准化流程（neutralize/group neutralize）。

验收：

1. 研究回放与生产日更使用同一引擎代码路径。
2. 质量与可观测指标达标。

### 16.4 联合执行顺序（按优先级）

1. **先做任务 2（Parser 内核）**：
   - `lexer.py`、`ast.py`、`parser.py` + 对应 pytest。
2. **再做任务 3（Analyzer/Registry）**：
   - `analyzer.py` + 首批算子注册（`Ref/Mean/Std` 起步）。
3. **随后做任务 1（Spec + Catalog）**：
   - `specs.py` 与 `derived_*` Catalog 表结构。
4. **最后做任务 4（执行器联调）**：
   - `executor.py` + Polars LazyFrame 端到端断言。

---

## 17. 测试策略（TDD 维度）

### 17.1 Core 单元测试

1. Lexer token 测试。
2. Parser AST 结构快照测试。
3. Analyzer lookback/scope 测试。
4. Operator codegen 与 Polars 结果对齐测试。

### 17.2 DataHub 单元/集成测试

1. Catalog CRUD + 事务一致性。
2. 锁竞争测试（并发写同实体）。
3. 原子提交失败回滚测试。

### 17.3 Port 集成测试

1. `daily_ingestion -> materialization` 串联。
2. backfill/repair 后 invalidation 触发。

### 17.4 验证命令

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

详细的架构决策记录已拆分为独立文件，请参阅 [README.md](README.md) 获取完整索引。
