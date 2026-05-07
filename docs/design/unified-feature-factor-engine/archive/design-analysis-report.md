> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# 统一派生引擎设计分析报告与优化建议

> **状态**: 历史分析，仅供参考。
> **说明**: 本文档保留 2026-03-12 的评审结论，但其中部分缺口状态、ADR 待创建描述和实施优先级已被后续文档覆盖。当前执行请优先参考：
> - [README.md](README.md)
> - [main-design.md](main-design.md)
> - [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)

> **文档状态**: 综合分析
> **创建日期**: 2026-03-12
> **基于版本**: 31 个 ADR + design-decisions 文档
> **分析目标**: 全面评估设计成熟度、识别差距、给出业界对标与优化建议

---

## 1. 设计总览评估

### 1.1 设计成熟度评分

| 维度 | 完成度 | 评分 | 说明 |
|------|--------|------|------|
| **核心架构** | 95% | ⭐⭐⭐⭐⭐ | Pratt Parser + Polars IR 执行链路清晰，分层合理 |
| **算子系统** | 90% | ⭐⭐⭐⭐⭐ | 52 个算子 + 5 层增量分类，覆盖 WorldQuant Alpha101 |
| **增量计算** | 85% | ⭐⭐⭐⭐ | Watermark + Invalidation 机制完备，但级联传播待细化 |
| **存储架构** | 90% | ⭐⭐⭐⭐⭐ | 冷热分层 + Hash/Blob 双模式，职责清晰 |
| **因子分级** | 85% | ⭐⭐⭐⭐ | SERIES/STATE/DERIVE/OFFLINE 分级清晰，但与 Feature 统一待补强 |
| **查询边界** | 85% | ⭐⭐⭐⭐ | Serving/Research/MixedSource 三类场景定义清晰 |
| **统一模型** | 75% | ⭐⭐⭐ | DerivedSpec 双轴模型已定义，但完整字段待细化 |
| **控制面协议** | 65% | ⭐⭐⭐ | 发布/版本/门禁协议框架已有，细节待补强 |
| **测试策略** | 80% | ⭐⭐⭐⭐ | 分层测试 + 内存后端，但算子数学正确性验证待补充 |
| **性能基准** | 60% | ⭐⭐⭐ | SLO 定义存在，但基准测试与 CI 门禁待实现 |
| **数据治理** | 70% | ⭐⭐⭐ | DQ 规则框架已有，但完整规则待补充 |
| **可观测性** | 85% | ⭐⭐⭐⭐ | 指标/告警设计完善，在线访问边界控制清晰 |
| **总体** | **80%** | **⭐⭐⭐⭐** | **设计成熟，核心架构已定型，控制面与治理待补强** |

### 1.2 业界对标对比

| 能力维度 | Ditto | Qlib | DolphinDB | Feast | Tecton | 评价 |
|---------|-------|------|-----------|-------|--------|------|
| **表达式 DSL** | ✅ Pratt | ✅ | ✅ | ❌ | ✅ | **与业界持平** |
| **TS/CS 嵌套** | ✅ 自动分层 | ✅ | ✅ | ❌ | ✅ | **与业界持平** |
| **增量计算** | ✅ | ⚠️ 有限 | ✅ | ✅ | ✅ | **与业界持平** |
| **PIT 一致性** | ✅ | ✅ | ✅ | ✅ | ✅ | **与业界持平** |
| **流批一体** | ⏸️ Phase 2 | ❌ | ✅ | ✅ | ✅ | **差距项** |
| **多市场日历** | ❌ 待设计 | ✅ | ✅ | ❌ | ✅ | **差距项** |
| **算子缓存** | ⚠️ Phase 1 | ✅ 两级 | ✅ JIT | ❌ | ✅ | **可优化** |
| **Pushdown** | ✅ 三层 | ❌ | N/A | ❌ | ⚠️ | **领先** |
| **Feature Store** | ⚠️ 部分 | ❌ | ❌ | ✅ | ✅ | **差距项** |
| **Entity/Time 语义** | ⚠️ 待补强 | ✅ | ✅ | ✅ | ✅ | **差距项** |
| **Lineage 血缘** | ⚠️ 表级 | ⚠️ | ❌ | ✅ | ✅ | **可优化** |
| **质量门禁** | ⚠️ 框架 | ⚠️ | ❌ | ✅ | ✅ | **差距项** |

---

## 2. 核心设计优势

### 2.1 架构亮点

1. **统一语义 + 分层执行**
   - 上层通过 `DerivedSpec + role + materialization_profile` 双轴模型统一语义
   - 底层根据场景选择不同物理执行路径（Parquet/QuestDB/Kvrocks）
   - 研究与生产共享同一执行引擎代码

2. **Pushdown 三层判定机制**
   - 能力层：判定算子能否下推
   - 模式层：判定执行模式是否适合
   - 开关层：运行时开关控制
   - 这在业界是领先的设计

3. **四层在线访问边界保护**
   - 接口隔离、运行时模式、可观测性、显式降级
   - 确保盘中主链路稳定性

4. **Hash/Blob 双模式状态快照**
   - 简单状态用 Hash（高效），复杂状态用 Blob（完整）
   - 平衡性能与表达能力

5. **Incremental Watermark + Invalidation 双保险**
   - 增量边界推导有理论支撑
   - 失效扩展规则覆盖 TS/CS 两种场景

### 2.2 设计决策完备性

- **31 个 ADR 决策记录**，覆盖核心架构、算子系统、增量计算、存储、服务、运维
- **D1-D14 设计决策**已明确：统一引擎定位、非纯流式路线、冷热分层、查询边界、层级边界

---

## 3. 待优化项与差距补齐清单

### 3.1 必须新建的 ADR（P0 - 核心阻塞项）

| ADR 编号 | 标题 | 优先级 | 依赖 | 核心问题 | 阻塞点 |
|---------|------|-------|------|---------|--------|
| **ADR-032** | Unified Derived Semantic Model | **P0** | 无 | DerivedSpec 完整字段、role/profile 双轴、Entity/Time 语义 | Phase 0 实施 |
| **ADR-033** | Derived Query Architecture and Layer Boundary | **P0** | ADR-032 | Port facade / DataHub implementation 边界、同步/异步风格 | 查询层实现 |
| **ADR-034** | Derived Publication Lifecycle and Version Contract | **P1** | ADR-032 | 发布/认证/版本协议、publication state machine | 控制面实现 |
| **ADR-035** | Derived Rebuild, Invalidation, and Correction Protocol | **P1** | ADR-032,034 | backfill/invalidation/correction 协议、级联传播策略 | 增量正确性 |
| **ADR-036** | Derived Quality, Benchmark, and Certification Gates | **P1** | ADR-032,034 | 质量/性能/认证门禁、benchmark gate | 上线验收 |
| **ADR-037** | Hot/Cold Retention and Minute Data Policy | **P2** | ADR-032,035 | 分钟数据保留、TTL 策略、存储成本 | 运维策略 |

### 3.2 ADR-032: Unified Derived Semantic Model 详细待定义项

```python
@dataclass
class DerivedSpec(BaseModel):
    """统一派生数据规格 - 待定义的完整字段"""

    # === 身份（已定义）===
    id: str
    version: int

    # === 双轴核心（已定义）===
    role: Literal["feature", "factor", "signal", "label"]
    materialization_profile: Literal["SERIES", "STATE", "DERIVE", "OFFLINE"]

    # === 表达式（已定义）===
    expression: str
    spec_hash: str

    # === 待补充：实体语义（P0）===
    entity_keys: list[str] = field(default_factory=lambda: ["instrument_id"])
    # 或更复杂的 join 场景：["instrument_id", "exchange"]

    # === 待补充：时间语义（P0）===
    event_time_column: str = "trade_date"      # 事件时间
    availability_time_column: str | None = None  # 数据可用时间（PIT 场景）
    calendar: str = "cn_trading"               # 交易日历
    timezone: str = "Asia/Shanghai"            # 时区

    # === 待补充：粒度语义（P1）===
    grain: Literal["ticker", "daily", "minute"] = "daily"
    aggregation_policy: Literal["last", "sum", "mean"] = "last"

    # === Profile 配置（已定义框架，待细化字段）===
    profile_config: FeatureProfile | FactorProfile

    # === 治理字段（已有）===
    owner: str = ""
    freshness_sla: str = "T+1"
    validation_policy: Literal["strict", "lenient"] = "strict"

    # === 分析结果（编译时填充）===
    lookback: int = 0
    requires_full_day: bool = False
    dependencies: list[str] = field(default_factory=list)
    operator_versions: dict[str, int] = field(default_factory=dict)  # 待补充
```

#### 3.2.1 Entity/Time 语义契约（P0 阻塞项）

```python
@dataclass
class EntitySpec(BaseModel):
    """实体语义 - 待定义"""
    join_keys: list[str] = field(default_factory=lambda: ["instrument_id"])
    # 多实体 join 场景支持
    join_policy: Literal["inner", "left", "outer"] = "inner"

@dataclass
class TimeSpec(BaseModel):
    """时间语义 - 待定义"""
    event_time: str              # "trade_date" 或 "announcement_date"
    availability_time: str       # 数据可用时间（可能 = event_time 或有延迟）
    calendar: str                # "cn_trading" / "us_trading" / "hk_trading"
    timezone: str                # "Asia/Shanghai" / "America/New_York"
```

**验收标准**：
- [ ] `BaseSpec` 包含 `entity: EntitySpec` 和 `time: TimeSpec`
- [ ] 增量计算使用 `calendar` 做精确 lookback
- [ ] 多市场因子可按 `calendar` 分区计算

### 3.3 ADR-033: 查询架构与层级边界待定义项

| 接口 | DataHub 层职责 | Port 层职责 | 待定义 |
|------|---------------|------------|--------|
| **ServingDerivedQuery** | QuestDB/Kvrocks 读取、路由逻辑 | 参数校验、权限控制、响应模型转换 | 接口 Protocol |
| **ResearchDerivedQuery** | Parquet 读取、as_of 查询、版本过滤 | 研究场景默认值、快照管理 | 返回模型 |
| **MixedSourceDerivedQuery** | 多源查询、diff 检测 | 差异报告生成、排障接口 | DiffReport 结构 |

#### 3.3.1 待定义的 Port Facade 接口

```python
# 待定义：Port 层 Facade 接口
class ServingDerivedQueryFacade(Protocol):
    """在线查询 Facade（Port 层）"""

    async def get_latest(
        self,
        derived_id: str,
        instrument_ids: list[str],
    ) -> dict[str, float]: ...

    async def get_series(
        self,
        derived_id: str,
        instrument_id: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame: ...

# 待定义：DataHub 层实现接口
class DerivedQueryImplementation(Protocol):
    """派生查询实现（DataHub 层）"""

    async def query(
        self,
        spec: DerivedSpec,
        query_mode: QueryMode,
        params: QueryParams,
    ) -> pl.DataFrame: ...
```

#### 3.3.2 返回类型统一

| 层级 | 返回类型 | 转换责任 |
|------|---------|---------|
| **DataHub** | `pl.DataFrame` | 保持现有风格 |
| **Port Facade** | `dict` / `Response Model` | Facade 负责转换 |
| **API Response** | `JSON` | FastAPI 负责序列化 |

### 3.4 ADR-034: 发布生命周期待定义项

#### 3.4.1 状态机定义

```
                   ┌──────────────┐
                   │   DRAFT      │
                   └──────┬───────┘
                          │ validate
                          ▼
                   ┌──────────────┐
                   │  VALIDATED   │
                   └──────┬───────┘
                          │ materialize
                          ▼
                   ┌──────────────┐
                   │ MATERIALIZE  │
                   └──────┬───────┘
                          │ certify (可选)
                          ▼
                   ┌──────────────┐
    ┌─────────────│  CERTIFIED   │◄────────────┐
    │             └──────┬───────┘             │
    │ rollback           │ publish             │ rollback
    │                    ▼                     │
    │             ┌──────────────┐             │
    └────────────►│  PUBLISHED   │─────────────┘
                  └──────┬───────┘
                         │ deprecate
                         ▼
                  ┌──────────────┐
                  │  DEPRECATED  │
                  └──────────────┘
```

#### 3.4.2 待定义的发布契约

```python
@dataclass
class PublicationContract:
    """发布契约 - 待定义"""

    # 发布状态
    status: Literal["draft", "validated", "materialized", "certified", "published", "deprecated"]

    # 版本信息
    version: int
    is_primary: bool = False      # 是否是主版本
    is_online: bool = False       # 是否在线可用

    # 发布时间
    published_at: datetime | None = None

    # 回滚支持
    rollback_from: int | None = None  # 从哪个版本回滚
    rollback_window_hours: int = 24   # 回滚窗口

    # 门禁结果
    quality_gate_passed: bool = False
    benchmark_gate_passed: bool = False
    certification_passed: bool = False
```

### 3.5 ADR-035: Invalidation 级联传播待定义项

```python
@dataclass
class InvalidationPropagation:
    """失效传播配置 - 待定义"""

    # 传播深度限制
    max_depth: int = 10

    # 传播模式
    mode: Literal["eager", "lazy"] = "lazy"

    # 批量处理
    batch_size: int = 100

    # 待定义：传播策略
    cross_role_propagation: bool = False  # 是否跨 role 传播（feature → factor）
    cross_profile_propagation: dict[str, bool] = field(default_factory=dict)
```

#### 3.5.1 失效事件结构

```python
@dataclass
class InvalidationEvent:
    """失效事件 - 待定义完整结构"""

    id: str                              # 事件 ID
    entity_type: Literal["feature", "factor"]
    entity_id: str

    # 触发源
    trigger_source: Literal[
        "source_correction",    # 源数据更正
        "spec_change",          # 规格变更
        "operator_upgrade",     # 算子升级
        "manual_trigger",       # 手动触发
    ]

    # 影响范围
    affected_range: DateRange | list[tuple[str, date]]  # (instrument_id, date) 列表

    # 扩展规则
    expansion_rule: Literal["ts", "cs", "ts_cs"]

    # 传播追踪
    propagated_to: list[str] = field(default_factory=list)
    propagation_depth: int = 0

    # 状态
    status: Literal["pending", "processing", "completed", "failed"]
```

### 3.6 ADR-036: 质量门禁待定义项

#### 3.6.1 DQ 规则分类

| 规则类型 | 优先级 | 描述 | 阈值示例 |
|---------|--------|------|---------|
| **Schema 校验** | P1 | 输出列名/类型匹配 | 强制 |
| **空值率阈值** | P1 | 列空值率检查 | ≤ 5% |
| **数据新鲜度** | P1 | 延迟检查 | ≤ T+1 |
| **分布漂移** | P2 | KS/PSI 检测 | PSI ≤ 0.1 |
| **极端值检测** | P2 | Winsorize 检查 | 自动标记 |
| **Feature Parity** | P1 | 研究/生产一致性 | ≥ 99.9% |
| **Factor Evaluation** | P1 | 因子评估指标 | Rank IC ≥ 0.02 |

#### 3.6.2 Benchmark Gate

```python
@dataclass
class PerformanceSLO:
    """性能 SLO - 待定义"""

    # 增量计算延迟
    incremental_latency_p50_ms: int = 5000   # 5s
    incremental_latency_p99_ms: int = 30000  # 30s

    # 全量计算吞吐
    full_throughput_rows_per_sec: int = 100000  # 10万行/秒

    # 因子日更吞吐
    daily_factors_throughput: int = 100  # 100 因子/10min

    # API 查询延迟
    query_latency_p50_ms: int = 10
    query_latency_p99_ms: int = 50
```

### 3.7 ADR-037: 存储策略待决策项

| 决策点 | 选项 A | 选项 B | 影响 |
|--------|--------|--------|------|
| **分钟数据进 Parquet** | 不保留 | 保留 30 日 | 研究可复现性 |
| **QuestDB TTL** | 分钟 5 日 / 日线 30 日 | 120/180/365 天类 | 存储成本 |
| **STATE 热序列** | 不需要 | 可选上下文热序列 | 增量性能 |
| **Kvrocks Key 拆分** | 统一 namespace | 按类型拆分 | 可维护性 |

---

## 4. 需要扩展的既有 ADR

| ADR 编号 | 扩展内容 | 优先级 | 说明 |
|---------|---------|-------|------|
| **ADR-014** | 表达式复杂度限制、缓存失效策略、持久化 | P1 | 防止编译/执行时间过长 |
| **ADR-007** | 算子版本管理、Breaking Change 检测 | P1 | 因子可复现性 |
| **ADR-022** | 失效传播级联策略、跨因子依赖传播 | P1 | 增量正确性 |
| **ADR-019** | 算子黄金数据集、数学正确性验证 | P1 | 与 TA-Lib 对齐 |
| **ADR-024** | Feature/Factor 统一生命周期、Schema Evolution | P1 | 统一版本管理 |
| **ADR-010** | Entity/Time 语义字段（已部分完成） | P1 | 多市场/多实体支持 |
| **ADR-027** | DQ 完整规则（P2 部分） | P2 | 分布漂移检测 |
| **ADR-029** | 扩展到 feature + factor、DERIVE 路径统一 | P1 | 统一物化契约 |
| **ADR-030** | 三类查询语义接口细化 | P1 | Port/DataHub 接口 |
| **ADR-031** | 扩展到 derived 视角、namespace 统一 | P2 | 状态快照 ABI |

---

## 5. 冲突口径统一清单

| 序号 | 冲突项 | 当前状态 | 建议决策 | 责任 ADR |
|------|--------|---------|---------|---------|
| 1 | **DERIVE 执行定位** | DuckDB ADHOC vs QuestDB+Polars 现算 | QuestDB 热基础数据 + Polars 现算 | ADR-029 扩展 |
| 2 | **热层 TTL** | 5/30 日 vs 120/180/365 天 | 需结合负载测试定案，建议 5/30 日 | ADR-037 |
| 3 | **状态 Key 命名** | `derived:state:*` vs `state:feature:*` | 统一为 `derived:state:{type}:{id}` | ADR-031 扩展 |
| 4 | **分钟数据进 Parquet** | 不保留 vs 保留 | 建议保留 30 日用于对拍 | ADR-037 |
| 5 | **表达式缓存持久化** | 内存 only vs 内存+磁盘 | 内存 + 可选磁盘两级缓存 | ADR-032 |
| 6 | **Feature/Factor 发布门禁** | 分离 vs 共享 | 共享门禁框架，差异化阈值 | ADR-034/036 |

---

## 6. 业界对标详细差距分析

### 6.1 Feature Store 能力差距（vs Feast/Tecton）

| 能力 | Ditto 现状 | Feast | Tecton | 差距级别 |
|------|-----------|-------|--------|---------|
| Entity/Time 语义 | 待定义 | ✅ | ✅ | **高** |
| Feature View 版本化 | Factor 仅有 | ✅ | ✅ | **中** |
| 在线/离线存储分离 | ✅ | ✅ | ✅ | **无** |
| PIT 正确性 | ✅ | ✅ | ✅ | **无** |
| 声明式定义 | ✅ | ✅ | ✅ | **无** |
| 增量计算支持 | ✅ | ✅ | ✅ | **无** |
| Lineage 血缘 | 表级 | ✅ | ✅ | **中** |

### 6.2 量化平台能力差距（vs Qlib/DolphinDB）

| 能力 | Ditto 现状 | Qlib | DolphinDB | 差距级别 |
|------|-----------|------|-----------|---------|
| 表达式 DSL | ✅ Pratt | ✅ | ✅ | **无** |
| TS/CS 嵌套 | ✅ | ✅ | ✅ | **无** |
| 多市场日历 | 待设计 | ✅ | ✅ | **中** |
| JIT/缓存 | Phase 1 | ✅ 两级 | ✅ JIT | **中** |
| 流批一体 | Phase 2 | ❌ | ✅ | **低** |

### 6.3 数据治理能力差距（vs Hopsworks）

| 能力 | Ditto 现状 | Hopsworks | 差距级别 |
|------|-----------|-----------|---------|
| Spec 治理字段 | 已有 | ✅ 完整 | **低** |
| DQ 规则 | P1 最小 | ✅ 完整框架 | **中** |
| Lineage 可视化 | 无 | ✅ | **低** |
| 自动 Drift 检测 | 无 | ✅ | **中** |

---

## 7. 实施优先级与依赖关系

### 7.1 必须完成的前置项（无依赖）

```
ADR-032: Unified Derived Semantic Model
    │
    ├── DerivedSpec 完整字段定义
    ├── Entity/Time 语义契约
    └── FeatureProfile / FactorProfile 边界
```

### 7.2 依赖 ADR-032 的后续项

```
ADR-032
    │
    ├── ADR-033: Derived Query Architecture
    │       └── DataHub/Port 边界、返回类型
    │
    ├── ADR-034: Publication Lifecycle
    │       └── 状态机、版本协议
    │
    └── ADR-035: Invalidation Protocol
            └── 级联传播、Correction 协议
```

### 7.3 依赖 ADR-034 的后续项

```
ADR-034
    │
    └── ADR-036: Quality/Benchmark Gates
            └── DQ 规则、性能 SLO、Certification
```

### 7.4 建议的实施顺序

```
Week 1:
├── ADR-032: Unified Derived Semantic Model
│   ├── DerivedSpec 完整字段
│   ├── EntitySpec / TimeSpec 定义
│   └── FeatureProfile / FactorProfile 细化

Week 2:
├── ADR-033: Derived Query Architecture
│   ├── DataHub 实现层 Protocol
│   ├── Port Facade 接口
│   └── 返回类型统一

Week 3:
├── ADR-034: Publication Lifecycle
│   ├── 状态机定义
│   ├── 版本协议
│   └── Rollback 契约

Week 4:
├── ADR-035: Invalidation Protocol
│   ├── 失效事件结构
│   ├── 级联传播策略
│   └── Correction 协议

Week 5:
├── ADR-036: Quality/Benchmark Gates
│   ├── P1 DQ 规则实现
│   ├── Benchmark 脚本
│   └── CI 门禁集成

Week 6:
├── ADR-037: Hot/Cold Retention Policy
│   ├── TTL 最终口径
│   ├── 分钟数据保留策略
│   └── State namespace 统一
```

---

## 8. 风险与对策

| 风险 | 级别 | 概率 | 对策 |
|------|------|------|------|
| DerivedSpec 模型变更频繁 | 高 | 中 | 预留 `spec_json` 存储完整定义，支持向后兼容 |
| 查询边界语义混淆 | 中 | 中 | 明确 facade 注释 + 类型标记，编写迁移指南 |
| 增量计算正确性 | 高 | 低 | 黄金数据集 + 回归测试 + 双写校验 |
| 存储分层策略不一致 | 中 | 低 | CI 门禁 + 代码审查 + 文档强制更新 |
| 性能 SLO 达标 | 中 | 中 | 基准测试 + 回归告警 + 分段优化 |
| 迁移路径复杂 | 高 | 高 | 分阶段迁移 + 兼容 facade + 详细迁移文档 |
| Feature/Factor 统一不彻底 | 中 | 中 | 明确共享与分离边界，编写对比文档 |

---

## 9. 验收标准汇总

### 9.1 模型层验收

- [ ] `DerivedSpec` 支持 feature/factor/signal/label
- [ ] `EntitySpec` 支持多实体 join
- [ ] `TimeSpec` 支持多市场日历
- [ ] `FeatureProfile` / `FactorProfile` 边界清晰

### 9.2 查询层验收

- [ ] 三类查询边界（Serving/Research/MixedSource）语义正确
- [ ] DataHub 返回 `pl.DataFrame`，Port Facade 负责转换
- [ ] MixedSource 支持差异报告输出

### 9.3 控制面验收

- [ ] 发布状态机完整实现
- [ ] 版本/Primary/Online 契约正确
- [ ] Rollback 支持一键回滚（24h 窗口）

### 9.4 质量层验收

- [ ] P1 DQ 规则全部实现
- [ ] Benchmark 脚本覆盖增量/全量/查询
- [ ] CI 门禁集成，回退超过 20% 则失败

### 9.5 存储层验收

- [ ] 冷热数据一致性校验通过
- [ ] TTL 策略生效，自动清理
- [ ] State namespace 统一

---

## 10. 附录：相关文档索引

### 10.1 核心设计文档

- [main-design.md](main-design.md) - 主设计文档
- [README.md](README.md) - ADR 索引
- [issues.md](issues.md) - 缺口清单
- [optimization-review.md](optimization-review.md) - 优化评审

### 10.2 关键 ADR

- [ADR-010: Catalog 完整表结构](decisions/adr-010-catalog-schema.md)
- [ADR-029: 盘中/盘后路径](decisions/adr-029-intraday-postmarket-paths.md)
- [ADR-030: Online Data Access Boundary](decisions/adr-030-online-data-access-boundary.md)
- [ADR-031: State Snapshot ABI](decisions/storage/adr-031-state-snapshot-abi.md)

### 10.3 派生查询设计决策

- [2026-03-11-unified-derived-query-design-decisions.md](../../plans/2026-03-11-unified-derived-query-design-decisions.md)

### 10.4 业界参考

- [industry-benchmarks.md](reference/industry-benchmarks.md)
- [worldquant-alpha101.md](reference/worldquant-alpha101.md)

---

## 11. 变更日志

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-03-12 | 创建综合分析报告，整合 optimization-review 和 design-decisions | 设计评审 |
