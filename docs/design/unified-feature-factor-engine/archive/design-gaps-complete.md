> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# 统一派生引擎 - 设计缺口与优化完整清单

> **文档状态**: 完整评审版
> **创建日期**: 2026-03-12
> **基于版本**: 31 个 ADR + optimization-review.md + unified-derived-query-design-decisions.md
> **目标**: 全面梳理设计缺口，不留死角，为实施阶段做准备

---

## 1. 设计成熟度总览

### 1.1 评分矩阵

| 维度 | 完成度 | 评分 | 关键缺口 |
|------|--------|------|---------|
| **核心架构** | 95% | ⭐⭐⭐⭐⭐ | Pratt Parser + Polars IR 执行链路清晰 |
| **统一模型** | 70% | ⭐⭐⭐ | DerivedSpec 字段不完整、entity_keys/time_keys 未定义 |
| **算子系统** | 85% | ⭐⭐⭐⭐ | 52 个算子，缺少版本管理机制 |
| **增量计算** | 80% | ⭐⭐⭐⭐ | Watermark + Invalidation 完备，级联传播未细化 |
| **存储架构** | 95% | ⭐⭐⭐⭐⭐ | 冷热分层清晰，一致性校验待补充 |
| **查询边界** | 85% | ⭐⭐⭐⭐ | 三类场景定义清晰，DataHub/Port 接口待细化 |
| **控制面** | 50% | ⭐⭐⭐ | 发布/版本/质量门禁协议待设计 |
| **测试策略** | 70% | ⭐⭐⭐⭐ | 框架清晰，黄金数据集/性能基准待补充 |
| **总体** | **78%** | **⭐⭐⭐⭐** | **可进入实施，但需补齐控制面和统一模型** |

### 1.2 业界对标差距

| 能力维度 | Ditto | Qlib | DolphinDB | Feast | 评价 |
|---------|-------|------|-----------|-------|------|
| 表达式 DSL | ✅ Pratt | ✅ | ✅ | ❌ | **持平** |
| TS/CS 嵌套 | ✅ 自动分层 | ✅ | ✅ | ❌ | **持平** |
| 增量计算 | ✅ | ⚠️ 有限 | ✅ | ✅ | **持平** |
| PIT 一致性 | ✅ | ✅ | ✅ | ✅ | **持平** |
| **Pushdown 策略** | ✅ 三层判定 | ❌ | N/A | ❌ | **领先** |
| **Online 边界保护** | ✅ 四层隔离 | ❌ | ❌ | ⚠️ 部分 | **领先** |
| **统一语义模型** | ⚠️ 70% | ✅ | ✅ | ✅ | **需补齐** |
| **算子版本管理** | ❌ 待补充 | ✅ 两级缓存 | ✅ JIT | ❌ | **需补齐** |
| **多市场日历** | ❌ 待设计 | ✅ | ✅ | ❌ | **需补齐** |
| **自定义算子** | ❌ 待设计 | ✅ | ✅ UDF | ❌ | **需补齐** |
| **流批一体** | ⚠️ 微批 | ❌ | ✅ 纯流 | ✅ | **可选** |

---

## 2. 必须新建的 ADR 清单

### 2.1 ADR-032: Unified Derived Semantic Model

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **阻塞项** | Phase 0 实施、多实体 join、增量边界计算 |
| **依赖** | 无 |

#### 核心问题

1. `DerivedSpec` 完整字段清单是什么？
2. `entity_keys / time_keys / grain / calendar / timezone` 如何定义？
3. `FeatureProfile` 与 `FactorProfile` 的边界如何划分？
4. `signal / label` 是否本期纳入？

#### 需要定义的模型

```python
@dataclass
class DerivedSpec(BaseModel):
    """统一派生数据规格"""

    # === 身份 ===
    id: str                          # "rsi_14", "alpha_momentum_12m"
    version: int                     # 版本号

    # === 双轴核心 ===
    role: Literal["feature", "factor", "signal", "label"]
    materialization_profile: Literal["SERIES", "STATE", "DERIVE", "OFFLINE"]

    # === 表达式 ===
    expression: str                  # "ts_mean(market.close, 14)"
    spec_hash: str                   # 规格哈希

    # === 实体与时间语义（待定义）===
    entity_keys: list[str] = field(default_factory=lambda: ["instrument_id"])
    time_keys: TimeSpec | None = None

    # === Profile 配置（按 role 分离）===
    profile_config: FeatureProfile | FactorProfile | SignalProfile | LabelProfile

    # === 分析结果（编译时）===
    lookback: int = 0
    requires_full_day: bool = False
    dependencies: list[str] = field(default_factory=list)


@dataclass
class TimeSpec(BaseModel):
    """时间语义"""
    event_time: str                  # "trade_date" 或 "announcement_date"
    availability_time: str           # 数据可用时间
    calendar: str                    # "cn_trading" / "us_trading" / "hk_trading"
    timezone: str                    # "Asia/Shanghai" / "America/New_York"


@dataclass
class FeatureProfile(BaseModel):
    """Feature 专属配置"""
    serving_enabled: bool = True
    training_enabled: bool = True
    parity_policy: Literal["strict", "warn", "none"] = "warn"
    null_policy: Literal["propagate", "fill", "drop"] = "propagate"
    consumer_group: str = "default"


@dataclass
class FactorProfile(BaseModel):
    """Factor 专属配置"""
    normalization_policy: str = "cs_zscore"
    neutralization_policy: list[str] = field(default_factory=lambda: ["sector"])
    exposure_domain: str = "cn_a_share"
    evaluation_policy: str = "default"
```

#### 验收标准

- [ ] ADR-032 文档完成
- [ ] `DerivedSpec` 包含 `entity_keys` 和 `TimeSpec`
- [ ] `FeatureProfile` 和 `FactorProfile` 边界明确
- [ ] 决定 `signal / label` 是否本期纳入

---

### 2.2 ADR-033: Derived Query Architecture and Layer Boundary

| 属性 | 值 |
|------|-----|
| **优先级** | P0 |
| **阻塞项** | DataHub/Port 接口设计 |
| **依赖** | ADR-032 |

#### 核心问题

1. `Serving / Research / MixedSource` 是服务实现还是 facade？
2. `datahub` 与 `port` 各自负责什么？
3. DataHub 是否统一返回 `pl.DataFrame`？
4. Query DTO、source routing、publication filtering 放在哪一层？
5. 同步/异步风格如何统一？

#### 分层职责

```
┌─────────────────────────────────────────────────────────────────┐
│                         Port Layer                               │
│                                                                  │
│  ServingDerivedQueryFacade    ResearchDerivedQueryFacade        │
│  MixedSourceDerivedQueryFacade                                   │
│                                                                  │
│  职责: 用例 facade、参数整形、权限控制、默认策略、返回模型转换    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DataHub Layer                             │
│                                                                  │
│  DerivedQueryService                                             │
│  ├── source routing (QuestDB / Kvrocks / Parquet / SQLite)      │
│  ├── version / publication / as_of / source_scope 过滤          │
│  └── 统一返回 pl.DataFrame                                       │
│                                                                  │
│  职责: 底层查询实现、数据源路由、版本过滤                        │
└─────────────────────────────────────────────────────────────────┘
```

#### 三类查询边界

| 查询边界 | 目标场景 | 允许数据源 | 关键约束 | 返回模型 |
|---------|---------|-----------|----------|---------|
| **Serving** | 盘中/在线主链路 | QuestDB + Kvrocks | 不默认读 Parquet | 最新值/短窗口 |
| **Research** | 研究/回测/训练 | Parquet + catalog snapshot | 可复现、时间旅行 | 历史序列 |
| **MixedSource** | 对拍/核验/排障 | Parquet + QuestDB + Kvrocks | 明确跨源标记 | 差异报告 |

#### 验收标准

- [ ] ADR-033 文档完成
- [ ] Port facade 接口定义清晰
- [ ] DataHub query service 接口定义清晰
- [ ] 三类查询边界的精确语义

---

### 2.3 ADR-034: Derived Publication Lifecycle and Version Contract

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **阻塞项** | 生产发布、回滚 |
| **依赖** | ADR-032 |

#### 核心问题

1. `register -> validate -> materialize -> certify -> publish` 是否成立？
2. `status / online / primary / published_at / rollback_from` 如何协同？
3. 哪些变更必须升版本？
4. publication state 与 materialization state 如何分离？

#### 发布状态机

```
                    ┌──────────────┐
                    │    DRAFT     │
                    └──────┬───────┘
                           │ validate
                           ▼
                    ┌──────────────┐
                    │  VALIDATED   │
                    └──────┬───────┘
                           │ materialize
                           ▼
                    ┌──────────────┐
                    │ MATERIALIZED │
                    └──────┬───────┘
                           │ certify (optional)
                           ▼
                    ┌──────────────┐
                    │  CERTIFIED   │
                    └──────┬───────┘
                           │ publish
                           ▼
                    ┌──────────────┐
           ┌────────│   PUBLISHED  │◄───────┐
           │        └──────────────┘        │
           │ rollback                        │
           ▼                                 │
    ┌──────────────┐                         │
    │   ROLLED_BACK│─────────────────────────┘
    └──────────────┘     re-publish
```

#### Schema Evolution 规则

| 变更类型 | 示例 | 处理方式 |
|---------|------|---------|
| **Breaking** | 算子变更、参数类型变更、输出列删除/重命名 | 必须升版本 |
| **Additive** | 新增可选参数、新增输出列 | 允许原地兼容 |
| **Data-only** | 时间范围扩展、universe 变化 | 触发 backfill，不升版本 |

#### 验收标准

- [ ] ADR-034 文档完成
- [ ] 发布状态机定义完整
- [ ] Schema Evolution 规则明确
- [ ] Rollback 协议定义

---

### 2.4 ADR-035: Derived Rebuild, Invalidation, and Correction Protocol

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **阻塞项** | 增量正确性、更正处理 |
| **依赖** | ADR-032, ADR-034 |

#### 核心问题

1. `append / correction / spec_change` 三类触发的统一事件模型？
2. `STATE` 的重建锚点与顺推机制？
3. correction 与系统故障恢复如何区分？
4. `SERIES / STATE / DERIVE / OFFLINE` 在重物化上的差异？
5. 跨因子依赖的级联传播如何处理？

#### Invalidation Event 结构

```python
@dataclass
class InvalidationEvent(BaseModel):
    """失效事件"""
    id: str
    entity_type: Literal["feature", "factor"]
    entity_id: str
    trigger_source: Literal["source_change", "correction", "spec_change", "manual"]
    trigger_time: datetime

    # 受影响范围
    affected_range: AffectedRange

    # 传播配置
    propagation: InvalidationPropagation


@dataclass
class AffectedRange(BaseModel):
    """受影响范围"""
    instrument_ids: list[str] | Literal["ALL"]
    date_range: tuple[date, date]
    expand_lookback: bool = True      # TS 算子是否扩展 lookback
    expand_full_day: bool = False     # CS 算子是否整日重算


@dataclass
class InvalidationPropagation(BaseModel):
    """失效传播配置"""
    max_depth: int = 10
    mode: Literal["eager", "lazy"] = "lazy"
    batch_size: int = 100
```

#### Invalidation 扩展规则

| 因子类型 | 失效扩展规则 |
|---------|-------------|
| **TS 因子** | 以 `(instrument_id, date)` 为粒度扩展 lookback |
| **CS 因子** | 任一标的变化放大为该 `trade_date` 全截面 |
| **STATE 因子** | 从最近的 checkpoint 重建锚点开始顺推 |
| **DERIVE 因子** | 重新计算依赖后现算 |

#### 验收标准

- [ ] ADR-035 文档完成
- [ ] InvalidationEvent 结构定义
- [ ] 级联传播策略明确
- [ ] STATE 重建机制设计

---

### 2.5 ADR-036: Derived Quality, Benchmark, and Certification Gates

| 属性 | 值 |
|------|-----|
| **优先级** | P1 |
| **阻塞项** | 发布门禁、质量保证 |
| **依赖** | ADR-032, ADR-034 |

#### 核心问题

1. `feature` 的 parity / freshness / null gate？
2. `factor` 的 evaluation / exposure / quality gate？
3. `SERIES / STATE / DERIVE / OFFLINE` 的 benchmark gate？
4. certification 是否单独建模？

#### DQ 规则框架

```python
class DQSeverity(str, Enum):
    ERROR = "error"      # 阻断发布
    WARNING = "warning"  # 告警但继续
    INFO = "info"        # 仅记录


@dataclass
class DQRule(BaseModel):
    """数据质量规则"""
    name: str
    description: str
    severity: DQSeverity
    check_fn: Callable[[pl.DataFrame], DQResult]


class BuiltinDQRules:
    """内置 DQ 规则"""

    @staticmethod
    def null_rate_threshold(column: str, max_rate: float) -> DQRule:
        """空值率阈值检查"""
        ...

    @staticmethod
    def distribution_drift(
        column: str,
        reference_mean: float,
        reference_std: float,
        max_psi: float = 0.1,
    ) -> DQRule:
        """分布漂移检测（PSI）"""
        ...
```

#### P1 必须规则

| 规则 | 阈值 | 说明 |
|------|------|------|
| Schema 校验 | 强制 | 输出列名/类型必须匹配 spec |
| 空值率阈值 | ≤ 5% | 超过则 ERROR |
| 数据新鲜度 | ≤ T+1 | 延迟超过 1 天则 WARNING |
| 分布漂移 | PSI ≤ 0.1 | 超过则 WARNING |

#### 性能 SLO

| 指标 | 目标 | 说明 |
|------|------|------|
| 增量计算延迟 P50 | ≤ 5s | 1000 标的 × 1 日增量 |
| 增量计算延迟 P99 | ≤ 30s | 1000 标的 × 1 日增量 |
| 全量计算吞吐 | ≥ 100,000 行/秒 | 批量处理 |
| 日更吞吐 | 100 因子/10min | 全量因子日更 |

#### 验收标准

- [ ] ADR-036 文档完成
- [ ] DQ 规则框架实现
- [ ] P1 规则全部实现
- [ ] 性能基准测试脚本

---

### 2.6 ADR-037: Hot/Cold Retention and Minute Data Policy

| 属性 | 值 |
|------|-----|
| **优先级** | P2 |
| **阻塞项** | 存储成本、研究可复现性 |
| **依赖** | ADR-032, ADR-035 |

#### 核心问题

1. 分钟数据是否进入 Parquet？
2. QuestDB 热层 TTL 最终口径？
3. `STATE` 是否需要可选 QuestDB 上下文序列？
4. `derived:state:*` 与 `state:feature:*` namespace 如何统一？

#### 存储策略选项

| 数据类型 | 热层 TTL | 冷层保留 | 建议 |
|---------|---------|---------|------|
| 分钟行情 | 5 日 | **建议保留 30 日** | 用于对拍 |
| 日线行情 | 30 日 | 永久 | 已确认 |
| 分钟因子 | 5 日 | 可选 30 日 | 待定 |
| 日线因子 | 30 日 | 永久 | 已确认 |
| STATE 快照 | 7 日 | 无 | 从 Parquet 重建 |

#### State Key 命名统一

```
# 统一为
ditto:derived:state:{entity_type}:{entity_id}
    → JSON {watermark, coverage_start, coverage_end, ...}

ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}
    → "1" (TTL 7天)

ditto:derived:invalidation:{priority}:{timestamp}:{id}
    → JSON {entity_type, entity_id, trigger_source, ...}
```

#### 验收标准

- [ ] ADR-037 文档完成
- [ ] 分钟数据保留策略定案
- [ ] TTL 口径统一
- [ ] State Key 命名统一

---

## 3. 需要扩展的既有 ADR

### 3.1 扩展 ADR-014: 表达式引擎核心

#### 待补充内容

##### 问题 1：表达式缓存持久化

**现状**：Spec 级缓存 + CSE 缓存设计已定义，但缓存失效策略、跨 Session 持久化未明确

**补充设计**：

```python
@dataclass
class CacheConfig:
    """缓存配置"""
    # 内存缓存
    memory_max_entries: int = 256
    memory_ttl_seconds: int = 3600  # 1 小时

    # 磁盘缓存（可选）
    disk_enabled: bool = False
    disk_path: Path = Path("runtime/cache/expressions")
    disk_max_size_mb: int = 100


class ExpressionCacheManager:
    """表达式缓存管理器"""

    def invalidate(self, spec_hash: str) -> None:
        """缓存失效（当算子实现变更时）"""
        self._memory_cache.pop(spec_hash, None)
        if self._disk_cache:
            self._disk_cache.delete(spec_hash)

    def invalidate_by_operator(self, op_name: str, op_version: int) -> None:
        """按算子版本失效缓存"""
        for spec_hash in self._find_specs_using_operator(op_name, op_version):
            self.invalidate(spec_hash)
```

##### 问题 2：表达式复杂度限制

**现状**：无复杂度检查，可能导致编译/执行时间过长

**补充设计**：

```python
@dataclass
class ExpressionLimits:
    """表达式复杂度限制"""
    max_length: int = 500          # 最大字符长度
    max_depth: int = 10            # 最大嵌套深度
    max_nodes: int = 100           # 最大 AST 节点数
    max_lookback: int = 252        # 最大 lookback（交易日）

    # 运行时限制
    max_execution_time_ms: int = 30000  # 最大执行时间
    max_memory_mb: int = 512            # 最大内存占用


class ComplexityAnalyzer:
    """复杂度分析器"""

    def analyze(self, ast: ASTNode) -> ComplexityReport:
        return ComplexityReport(
            depth=self._calc_depth(ast),
            node_count=self._count_nodes(ast),
            max_lookback=self._extract_max_lookback(ast),
            estimated_memory=self._estimate_memory(ast),
        )

    def validate(self, ast: ASTNode, limits: ExpressionLimits) -> None:
        report = self.analyze(ast)
        if report.depth > limits.max_depth:
            raise CompileError(f"Expression too deep: {report.depth} > {limits.max_depth}")
```

**验收标准**：
- [ ] 缓存持久化机制设计
- [ ] 复杂度限制规则定义
- [ ] 编译期复杂度检查实现

---

### 3.2 扩展 ADR-007: 算子注册表

#### 待补充内容：算子版本管理

**现状**：算子清单完整，但缺少版本化机制

**补充设计**：

```python
@dataclass
class OperatorVersion:
    """算子版本"""
    name: str
    version: int
    checksum: str  # 实现哈希
    change_log: str
    breaking_change: bool


class OperatorRegistry:
    """算子注册表（支持版本化）"""

    _operators: dict[str, list[OperatorVersion]] = {}

    @classmethod
    def register(cls, name: str, impl: Callable, change_log: str = "") -> None:
        """注册算子新版本"""
        checksum = compute_checksum(impl)
        versions = cls._operators.get(name, [])

        if versions and versions[-1].checksum == checksum:
            return  # 无变更，跳过

        breaking = cls._detect_breaking_change(impl, versions[-1] if versions else None)
        versions.append(OperatorVersion(
            name=name,
            version=len(versions) + 1,
            checksum=checksum,
            change_log=change_log,
            breaking_change=breaking,
        ))
        cls._operators[name] = versions

        if breaking:
            cls._trigger_cache_invalidation(name)

    @classmethod
    def get_current_version(cls, name: str) -> OperatorVersion:
        return cls._operators[name][-1]


# Spec 中记录算子版本
class BaseSpec(BaseModel):
    # ... 现有字段 ...
    operator_versions: dict[str, int] = {}  # {"ts_mean": 2, "cs_rank": 1}
```

**验收标准**：
- [ ] 算子版本注册机制实现
- [ ] Spec 记录依赖算子版本
- [ ] Breaking Change 自动触发缓存失效

---

### 3.3 扩展 ADR-019: 测试策略

#### 待补充内容：算子黄金数据集

**现状**：测试策略清晰，但缺少算子数学验证的黄金数据集

**补充设计**：

```python
@dataclass
class GoldenTestCase:
    """黄金测试用例"""
    operator: str
    description: str
    input_data: dict
    expected_output: list[float]
    tolerance: float = 1e-6


# 黄金数据集来源
# 1. TA-Lib 参考实现
# 2. WorldQuant Alpha101 验证数据
# 3. 手工构造的边界情况

# 示例：ts_mean 黄金数据
TS_MEAN_GOLDEN = [
    GoldenTestCase(
        operator="ts_mean",
        description="标准窗口计算",
        input_data={"values": [1.0, 2.0, 3.0, 4.0, 5.0], "window": 3},
        expected_output=[1.0, 1.5, 2.0, 3.0, 4.0],
    ),
    GoldenTestCase(
        operator="ts_mean",
        description="窗口大于数据量",
        input_data={"values": [1.0, 2.0, 3.0], "window": 5},
        expected_output=[1.0, 1.5, 2.0],
    ),
    GoldenTestCase(
        operator="ts_mean",
        description="包含 NULL 值",
        input_data={"values": [1.0, None, 3.0, 4.0], "window": 2},
        expected_output=[1.0, None, None, 3.5],
    ),
]
```

**验收标准**：
- [ ] P0 算子全部有黄金测试用例
- [ ] 黄金数据集与 TA-Lib 对齐
- [ ] CI 集成黄金测试

---

### 3.4 扩展 ADR-029/030/031: 盘中盘后路径

#### 待补充内容

##### ADR-029 扩展

- `materialization_profile` 从 factor-only 扩展到 feature + factor
- 四类 profile 作为统一物化契约
- `DERIVE` 路径统一到 "QuestDB 热基础数据 + Polars 现算"

##### ADR-030 扩展

- `Serving / Research / MixedSource` 三类查询边界
- online 主链路默认不允许跨级回退到 Parquet
- Port facade / DataHub implementation 的接口隔离方式

##### ADR-031 扩展

- `STATE` 从 factor-only 扩展到 derived 视角
- snapshot ABI 与 `role`、`profile` 的关系
- state namespace 统一策略

---

## 4. 冲突口径统一清单

| 序号 | 冲突项 | 口径 A | 口径 B | **建议决策** | 责任 ADR |
|------|--------|--------|--------|-------------|---------|
| 1 | **DERIVE 执行定位** | DuckDB ADHOC | QuestDB + Polars | ✅ 采用 B | ADR-029 扩展 |
| 2 | **热层 TTL** | 分钟 5 日/日线 30 日 | 120/180/365 天 | 需结合负载测试定案 | ADR-037 |
| 3 | **状态 Key 命名** | `derived:state:*` | `state:feature:{id}:{inst}` | 统一为 `derived:state:{type}:{id}` | ADR-031 扩展 |
| 4 | **分钟数据进 Parquet** | 不保留 | 需要保留 | **建议保留 30 日用于对拍** | ADR-037 |
| 5 | **表达式缓存持久化** | 未明确 | 需明确 | 内存 + 磁盘两级缓存 | ADR-014 扩展 |
| 6 | **算子变更触发失效** | 未明确 | 需明确 | Breaking Change 自动失效 | ADR-007 扩展 |

---

## 5. 缺口汇总矩阵

### 5.1 新建 ADR

| ADR | 标题 | 优先级 | 阻塞项 | 状态 |
|-----|------|-------|--------|------|
| **ADR-032** | Unified Derived Semantic Model | P0 | Phase 0 实施 | 🔴 待创建 |
| **ADR-033** | Derived Query Architecture | P0 | DataHub/Port 接口 | 🔴 待创建 |
| **ADR-034** | Publication Lifecycle | P1 | 生产发布 | 🔴 待创建 |
| **ADR-035** | Invalidation Protocol | P1 | 增量正确性 | 🔴 待创建 |
| **ADR-036** | Quality Gates | P1 | 发布门禁 | 🔴 待创建 |
| **ADR-037** | Retention Policy | P2 | 存储成本 | 🔴 待创建 |

### 5.2 扩展 ADR

| ADR | 扩展内容 | 优先级 | 状态 |
|-----|---------|-------|------|
| ADR-007 | 算子版本管理 | P1 | 🔴 待扩展 |
| ADR-014 | 缓存持久化、复杂度限制 | P1 | 🔴 待扩展 |
| ADR-019 | 算子黄金数据集 | P1 | 🔴 待扩展 |
| ADR-024 | 升级为 Derived 版本管理 | P1 | 🔴 待扩展 |
| ADR-029 | 扩展到 feature + factor | P1 | 🔴 待扩展 |
| ADR-030 | 三类查询边界 | P1 | 🔴 待扩展 |
| ADR-031 | Derived 视角的 STATE | P2 | 🔴 待扩展 |

---

## 6. 实施路线图

### Stage 1: 锁定根抽象（1-2 周）

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| ADR-032 | Unified Derived Semantic Model | DerivedSpec 完整字段定义 |
| ADR-033 | Derived Query Architecture | Port/DataHub 边界明确 |

### Stage 2: 补齐控制面（2-3 周）

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| ADR-034 | Publication Lifecycle | 发布状态机完整 |
| ADR-035 | Invalidation Protocol | 级联失效机制 |
| ADR-036 | Quality Gates | DQ 门禁通过率 > 99% |

### Stage 3: 统一存储策略（1 周）

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| ADR-037 | Retention Policy | TTL 策略定案 |
| ADR-014 扩展 | 缓存持久化 | 两级缓存实现 |
| ADR-007 扩展 | 算子版本管理 | 版本追溯可用 |

### Stage 4: 验证与黄金测试（1 周）

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| ADR-019 扩展 | 算子黄金数据集 | P0 算子 100% 覆盖 |
| 性能基准 | Benchmark 脚本 | CI 门禁可用 |

---

## 7. 风险与对策

| 风险 | 级别 | 概率 | 对策 |
|------|------|------|------|
| DerivedSpec 模型变更频繁 | 高 | 中 | 预留 `spec_json` 存储完整定义 |
| 查询边界语义混淆 | 中 | 中 | 明确 facade 注释 + 类型标记 |
| 表达式缓存一致性 | 中 | 中 | 算子版本变更自动失效缓存 |
| 增量计算正确性 | 高 | 低 | 黄金数据集 + 回归测试 |
| 性能 SLO 达标 | 中 | 中 | 基准测试 CI 门禁 + 回归告警 |
| 算子 Breaking Change 影响 | 高 | 中 | 版本管理 + 自动 Invalidation |

---

## 变更日志

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-03-12 | 创建完整设计缺口清单 | 综合评审 |
| 2026-03-12 | 整合 optimization-review.md 和 unified-derived-query-design-decisions.md | 文档整合 |
