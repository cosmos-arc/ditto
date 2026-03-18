# Unified Feature/Factor Engine - 优化与改进建议

> **状态**: 历史评审，仅供参考。
> **说明**: 本文档形成于 ADR-032 ~ ADR-039 完成前后交界期，部分“待新增 ADR”与“待补充项”已被后续 ADR 或整改方案吸收。当前执行请优先参考：
> - [README.md](README.md)
> - [main-design.md](main-design.md)
> - [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)

> **文档状态**: 评审中
> **创建日期**: 2026-03-10
> **基于版本**: 31 个 ADR 决策记录

---

## 1. 设计总览评估

### 1.1 成熟度评分

| 维度 | 完成度 | 评分 | 说明 |
|------|--------|------|------|
| 核心架构 | 95% | ⭐⭐⭐⭐⭐ | Pratt Parser + Polars IR 执行链路清晰 |
| 算子系统 | 90% | ⭐⭐⭐⭐⭐ | 52 个算子 + 5 层增量分类 |
| 增量计算 | 85% | ⭐⭐⭐⭐ | Watermark + Invalidation 机制完备 |
| 存储架构 | 90% | ⭐⭐⭐⭐⭐ | 冷热分层 + Hash/Blob 双模式 |
| 因子分级 | 85% | ⭐⭐⭐⭐ | SERIES/STATE/DERIVE/OFFLINE 分级清晰 |
| 测试策略 | 80% | ⭐⭐⭐⭐ | 分层测试 + 内存后端 |
| **总体** | **87%** | **⭐⭐⭐⭐** | **设计成熟，可进入实施** |

### 1.2 业界对标对比

| 能力维度 | Ditto | Qlib | DolphinDB | Feast | 评价 |
|---------|-------|------|-----------|-------|------|
| 表达式 DSL | ✅ Pratt | ✅ | ✅ | ❌ | 与业界持平 |
| TS/CS 嵌套 | ✅ 自动分层 | ✅ | ✅ | ❌ | 与业界持平 |
| 增量计算 | ✅ | ⚠️ 有限 | ✅ | ✅ | 与业界持平 |
| PIT 一致性 | ✅ | ✅ | ✅ | ✅ | 与业界持平 |
| 流批一体 | ⏸️ Phase 2 | ❌ | ✅ | ✅ | **差距项** |
| 多市场日历 | ❌ 待设计 | ✅ | ✅ | ❌ | **差距项** |
| 算子缓存 | ⚠️ Phase 1 | ✅ 两级 | ✅ JIT | ❌ | **可优化** |
| Pushdown | ✅ 三层 | ❌ | N/A | ❌ | **领先** |

---

## 2. 核心优化建议

### 2.1 表达式引擎优化

#### 问题 1：表达式缓存策略不完整

**现状（ADR-014）**：
- Spec 级缓存 + CSE 缓存设计已定义
- 但缓存失效策略、跨 Session 持久化未明确

**业界最佳实践（Qlib）**：
```python
# Qlib 的两级缓存
class ExpressionCache:
    # 内存缓存：进程内快速访问
    memory_cache: dict[str, CompiledPlan]

    # 磁盘缓存：跨 Session 持久化
    disk_cache: DiskCache  # LRU + TTL
```

**优化建议**：

```python
# 建议新增 ADR-032: 表达式缓存完整策略

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

    def __init__(self, config: CacheConfig):
        self._memory_cache: OrderedDict[str, CacheEntry] = {}
        self._disk_cache: DiskCache | None = None
        self._config = config

    def get(self, spec_hash: str) -> CompiledPlan | None:
        # 1. 检查内存缓存
        if entry := self._memory_cache.get(spec_hash):
            if not entry.is_expired():
                return entry.plan
            del self._memory_cache[spec_hash]

        # 2. 检查磁盘缓存
        if self._disk_cache:
            if plan := self._disk_cache.get(spec_hash):
                # 回填内存缓存
                self._set_memory(spec_hash, plan)
                return plan

        return None

    def invalidate(self, spec_hash: str) -> None:
        """缓存失效（当算子实现变更时）"""
        self._memory_cache.pop(spec_hash, None)
        if self._disk_cache:
            self._disk_cache.delete(spec_hash)
```

**验收标准**：
- [ ] 实现 `ExpressionCacheManager` 支持内存 + 磁盘两级缓存
- [ ] 定义缓存失效触发条件（算子版本变更、引擎升级）
- [ ] 添加缓存命中率监控指标

---

#### 问题 2：缺少表达式复杂度限制

**现状**：无复杂度检查，可能导致编译/执行时间过长

**业界最佳实践**：
- WorldQuant Brain：表达式长度限制 500 字符，嵌套深度限制 10 层
- BigQuant：AST 节点数量限制

**优化建议**：

```python
# 建议新增到 ADR-014 或 ADR-032

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
            raise CompileError(
                f"Expression too deep: {report.depth} > {limits.max_depth}"
            )
        if report.node_count > limits.max_nodes:
            raise CompileError(
                f"Expression too complex: {report.node_count} nodes > {limits.max_nodes}"
            )
```

---

### 2.2 算子系统优化

#### 问题 3：缺少算子版本管理

**现状（ADR-007）**：算子清单完整，但缺少版本化机制

**风险**：
- 算子实现 Bug 修复后，无法追踪哪些因子使用了旧实现
- 算子语义变更无法自动触发因子重算

**优化建议**：

```python
# 建议新增 ADR-033: 算子版本管理

# packages/core/src/ditto_core/ops/registry.py

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
            cls._trigger_invalidation(name)

    @classmethod
    def get_current_version(cls, name: str) -> OperatorVersion:
        """获取算子当前版本"""
        return cls._operators[name][-1]

# Spec 中记录算子版本
class BaseSpec(BaseModel):
    # ... 现有字段 ...
    operator_versions: dict[str, int] = {}  # {"ts_mean": 2, "cs_rank": 1}
```

**验收标准**：
- [ ] 实现算子版本注册机制
- [ ] Spec 记录依赖算子版本
- [ ] 算子 Breaking Change 自动触发相关因子 Invalidation

---

#### 问题 4：缺少自定义算子扩展机制

**现状**：只有内置算子，无用户自定义扩展路径

**业界最佳实践**：
- Qlib：支持自定义 Expression 算子
- DolphinDB：用户定义函数（UDF）

**优化建议**：

```python
# 建议新增 ADR-034: 自定义算子扩展机制

from typing import Protocol

class CustomOperator(Protocol):
    """自定义算子协议"""

    @property
    def name(self) -> str: ...

    @property
    def signature(self) -> str: ...

    def validate_args(self, *args, **kwargs) -> None: ...

    def lookback_rule(self, *args) -> int: ...

    def codegen(self, *args, **kwargs) -> pl.Expr: ...

    def incremental_impl(self, state: Any, new_value: Any) -> tuple[Any, Any]:
        """增量实现（可选）"""
        raise NotImplementedError("Not incrementally computable")

# 注册自定义算子
class OperatorRegistry:
    @classmethod
    def register_custom(cls, op: CustomOperator) -> None:
        """注册自定义算子"""
        cls._custom_operators[op.name] = op
        cls._build_cache[op.name] = op.codegen
```

**注意事项**：
- 自定义算子需要显式声明 `lookback_rule` 和 `requires_full_day`
- 增量实现可选，无增量实现则只能全量计算
- 建议 Phase 2 再开放

---

### 2.3 增量计算优化

#### 问题 5：Invalidation 级联传播策略不完整

**现状（ADR-006）**：
- TS/CS 算子的失效扩展规则已定义
- 但跨因子依赖的级联传播未明确

**优化建议**：

```python
# 扩展 ADR-022: 更正数据处理

@dataclass
class InvalidationPropagation:
    """失效传播配置"""

    # 传播深度限制
    max_depth: int = 10

    # 传播模式
    mode: Literal["eager", "lazy"] = "lazy"

    # 批量处理
    batch_size: int = 100

class InvalidationEngine:
    """失效传播引擎"""

    async def propagate(
        self,
        source: InvalidationEvent,
        config: InvalidationPropagation,
    ) -> list[InvalidationTask]:
        """传播失效事件"""
        tasks = []
        visited = set()
        queue = [(source, 0)]

        while queue:
            event, depth = queue.pop(0)

            if depth > config.max_depth:
                continue

            if event.id in visited:
                continue
            visited.add(event.id)

            # 查找下游依赖
            dependents = await self.catalog.find_dependents(
                entity_type=event.entity_type,
                entity_id=event.entity_id,
            )

            for dep in dependents:
                task = self._create_task(event, dep)
                tasks.append(task)

                # 继续传播
                queue.append((
                    InvalidationEvent(
                        entity_type=dep.entity_type,
                        entity_id=dep.entity_id,
                        trigger=event,
                    ),
                    depth + 1,
                ))

        return tasks
```

---

#### 问题 6：Lookback 预热效率问题

**现状**：每次增量计算都需要 `lookback` 天预热数据

**优化建议**：引入 **Rolling State** 缓存

```python
# 建议新增 ADR-035: Rolling State 缓存

class RollingStateCache:
    """滚动状态缓存

    对于高频因子（如每日计算），缓存预热窗口数据
    """

    def __init__(self, kv: KvrocksClient, ttl_days: int = 7):
        self._kv = kv
        self._ttl_days = ttl_days

    async def get_warmup_data(
        self,
        factor_id: str,
        instrument_id: str,
        lookback: int,
        end_date: date,
    ) -> pl.DataFrame | None:
        """获取预热数据（如果缓存有效）"""
        key = f"warmup:{factor_id}:{instrument_id}"

        cached = await self._kv.get(key)
        if not cached:
            return None

        data = orjson.loads(cached)
        cached_end = date.fromisoformat(data["end_date"])

        # 缓存数据有效且足够
        if cached_end >= end_date - timedelta(days=1):
            return pl.read_parquet(data["parquet_path"])

        return None

    async def save_warmup_data(
        self,
        factor_id: str,
        instrument_id: str,
        df: pl.DataFrame,
        end_date: date,
    ) -> None:
        """保存预热数据"""
        key = f"warmup:{factor_id}:{instrument_id}"

        # 写入临时 Parquet
        temp_path = self._temp_dir / f"{factor_id}_{instrument_id}.parquet"
        df.write_parquet(temp_path)

        await self._kv.set(
            key,
            orjson.dumps({
                "end_date": end_date.isoformat(),
                "parquet_path": str(temp_path),
            }),
            ex=self._ttl_days * 86400,
        )
```

---

### 2.4 存储架构优化

#### 问题 7：QuestDB 与 Parquet 数据一致性

**现状**：Parquet 是唯一真相源，但缺乏热冷数据一致性校验机制

**优化建议**：

```python
# 建议新增 ADR-036: 数据一致性校验

@dataclass
class ConsistencyCheckResult:
    """一致性校验结果"""
    factor_id: str
    partition: str
    parquet_rows: int
    questdb_rows: int
    consistent: bool
    diff_sample: list[dict] | None  # 差异样本

class ConsistencyChecker:
    """数据一致性校验器"""

    async def check_partition(
        self,
        factor_id: str,
        partition: str,
        sample_size: int = 100,
    ) -> ConsistencyCheckResult:
        """校验分区数据一致性"""

        # 1. 从 Parquet 读取
        parquet_df = await self.parquet_reader.read_partition(
            factor_id, partition
        )

        # 2. 从 QuestDB 读取
        questdb_df = await self.questdb_reader.read_partition(
            factor_id, partition
        )

        # 3. 行数对比
        if len(parquet_df) != len(questdb_df):
            return ConsistencyCheckResult(
                factor_id=factor_id,
                partition=partition,
                parquet_rows=len(parquet_df),
                questdb_rows=len(questdb_df),
                consistent=False,
                diff_sample=self._sample_diff(parquet_df, questdb_df),
            )

        # 4. 抽样值对比
        sample = parquet_df.sample(sample_size)
        for row in sample.iter_rows(named=True):
            key = (row["instrument_id"], row["trade_date"])
            qdb_row = questdb_df.filter(
                (pl.col("instrument_id") == key[0]) &
                (pl.col("trade_date") == key[1])
            )

            if len(qdb_row) == 0 or not self._values_equal(row, qdb_row.row(0)):
                return ConsistencyCheckResult(
                    factor_id=factor_id,
                    partition=partition,
                    parquet_rows=len(parquet_df),
                    questdb_rows=len(questdb_df),
                    consistent=False,
                    diff_sample=[row],
                )

        return ConsistencyCheckResult(
            factor_id=factor_id,
            partition=partition,
            parquet_rows=len(parquet_df),
            questdb_rows=len(questdb_df),
            consistent=True,
            diff_sample=None,
        )
```

---

### 2.5 性能优化

#### 问题 8：缺少性能基准与 SLO

**现状**：issues.md 中的 P1-8 性能基准待补充

**优化建议**：

```python
# 建议新增 ADR-037: 性能 SLO 与基准测试

@dataclass
class PerformanceSLO:
    """性能 SLO"""
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

class PerformanceBenchmark:
    """性能基准测试"""

    @staticmethod
    def run_incremental_benchmark() -> BenchmarkResult:
        """运行增量计算基准测试"""
        # 1000 标的 × 1 日增量
        df = generate_test_data(instruments=1000, days=1)

        start = time.perf_counter()
        result = factor_engine.compute_incremental(spec, df)
        latency_ms = (time.perf_counter() - start) * 1000

        return BenchmarkResult(
            name="incremental_1000_instruments",
            latency_ms=latency_ms,
            rows_processed=len(df),
            rows_per_sec=len(df) / (latency_ms / 1000),
        )
```

**建议的 CI 门禁**：

```yaml
# .github/workflows/performance-check.yml
- name: Performance Benchmark
  run: |
    pixi run -e dev python scripts/benchmark_factor.py \
      --check-slo \
      --fail-on-regression 20%  # 回退超过 20% 则失败
```

---

### 2.6 数据治理优化

#### 问题 9：DQ 规则框架不完整

**现状（issues.md P1-7）**：最小门禁已定义，但完整 DQ 框架待补充

**优化建议**：

```python
# 建议扩展 ADR-027: DQ 完整规则

from enum import Enum

class DQSeverity(str, Enum):
    ERROR = "error"      # 阻断发布
    WARNING = "warning"  # 告警但继续
    INFO = "info"        # 仅记录

@dataclass
class DQRule:
    """数据质量规则"""
    name: str
    description: str
    severity: DQSeverity
    check_fn: Callable[[pl.DataFrame], DQResult]

# 内置规则
class BuiltinDQRules:
    @staticmethod
    def null_rate_threshold(column: str, max_rate: float) -> DQRule:
        """空值率阈值检查"""
        return DQRule(
            name=f"null_rate_{column}",
            description=f"{column} 空值率不能超过 {max_rate:.1%}",
            severity=DQSeverity.ERROR if max_rate < 0.1 else DQSeverity.WARNING,
            check_fn=lambda df: DQResult(
                passed=df[column].null_count() / len(df) <= max_rate,
                actual_value=df[column].null_count() / len(df),
                threshold=max_rate,
            ),
        )

    @staticmethod
    def distribution_drift(
        column: str,
        reference_mean: float,
        reference_std: float,
        max_psi: float = 0.1,
    ) -> DQRule:
        """分布漂移检测（PSI）"""
        def check(df: pl.DataFrame) -> DQResult:
            current_mean = df[column].mean()
            current_std = df[column].std()

            psi = calculate_psi(
                current_mean, current_std,
                reference_mean, reference_std,
            )

            return DQResult(
                passed=psi <= max_psi,
                actual_value=psi,
                threshold=max_psi,
            )

        return DQRule(
            name=f"drift_{column}",
            description=f"{column} 分布漂移 PSI 不能超过 {max_psi}",
            severity=DQSeverity.WARNING,
            check_fn=check,
        )

class DQValidator:
    """数据质量校验器"""

    def __init__(self, rules: list[DQRule]):
        self.rules = rules

    def validate(self, df: pl.DataFrame) -> DQReport:
        """执行所有规则"""
        results = []

        for rule in self.rules:
            result = rule.check_fn(df)
            results.append((rule, result))

            if rule.severity == DQSeverity.ERROR and not result.passed:
                raise DQValidationError(rule, result)

        return DQReport(results=results)
```

---

### 2.7 测试策略优化

#### 问题 10：缺少算子数学正确性验证

**现状（ADR-019）**：测试策略清晰，但缺少算子数学验证的黄金数据集

**优化建议**：

```python
# 建议新增 reference/operator-golden-datasets.md

# 黄金数据集来源
# 1. TA-Lib 参考实现
# 2. WorldQuant Alpha101 验证数据
# 3. 手工构造的边界情况

@dataclass
class GoldenTestCase:
    """黄金测试用例"""
    operator: str
    description: str
    input_data: dict
    expected_output: list[float]
    tolerance: float = 1e-6

# 示例：ts_mean 黄金数据
TS_MEAN_GOLDEN = [
    GoldenTestCase(
        operator="ts_mean",
        description="标准窗口计算",
        input_data={
            "values": [1.0, 2.0, 3.0, 4.0, 5.0],
            "window": 3,
        },
        expected_output=[1.0, 1.5, 2.0, 3.0, 4.0],
    ),
    GoldenTestCase(
        operator="ts_mean",
        description="窗口大于数据量",
        input_data={
            "values": [1.0, 2.0, 3.0],
            "window": 5,
        },
        expected_output=[1.0, 1.5, 2.0],  # 使用可用数据
    ),
    GoldenTestCase(
        operator="ts_mean",
        description="包含 NULL 值",
        input_data={
            "values": [1.0, None, 3.0, 4.0],
            "window": 2,
        },
        expected_output=[1.0, None, None, 3.5],
    ),
]

# 自动化测试生成
class TestOperatorGolden:
    """基于黄金数据的算子测试"""

    @pytest.mark.parametrize("case", TS_MEAN_GOLDEN)
    def test_ts_mean_golden(self, case: GoldenTestCase):
        result = ts_mean(**case.input_data)
        np.testing.assert_allclose(
            result, case.expected_output,
            rtol=case.tolerance,
            equal_nan=True,
        )
```

---

## 3. 缺口清单补充

### 3.1 必须补充的 ADR

| ADR 编号 | 标题 | 优先级 | 状态 | 阻塞项 |
|---------|------|-------|------|--------|
| ADR-032 | 表达式缓存完整策略 | P1 | 🔴 待创建 | 算子缓存复用 |
| ADR-033 | 算子版本管理 | P1 | 🔴 待创建 | 因子可复现性 |
| ADR-034 | 自定义算子扩展机制 | P2 | 🔴 待创建 | Phase 2 |
| ADR-035 | Rolling State 缓存 | P1 | 🔴 待创建 | 增量性能 |
| ADR-036 | 数据一致性校验 | P1 | 🔴 待创建 | 数据质量 |
| ADR-037 | 性能 SLO 与基准测试 | P1 | 🔴 待创建 | 验收门禁 |

### 3.2 需要扩展的 ADR

| ADR 编号 | 扩展内容 | 优先级 |
|---------|---------|-------|
| ADR-014 | 表达式复杂度限制 | P1 |
| ADR-022 | 失效传播级联策略 | P1 |
| ADR-027 | DQ 完整规则 | P2 |
| ADR-019 | 算子黄金数据集 | P1 |

---

## 4. 可执行的实施清单

### Phase 0（当前阶段）- 补齐缺口

| 序号 | 任务 | 预估 | 验收标准 |
|-----|------|------|---------|
| 0.1 | 创建 ADR-032 表达式缓存策略 | 0.5d | 内存+磁盘两级缓存设计完成 |
| 0.2 | 创建 ADR-033 算子版本管理 | 0.5d | Spec 记录算子版本 |
| 0.3 | 创建 ADR-037 性能 SLO | 0.5d | 基准测试脚本 + CI 门禁 |
| 0.4 | 补充 ADR-014 复杂度限制 | 0.25d | 编译期复杂度检查 |
| 0.5 | 补充 ADR-019 黄金数据集 | 1d | P0 算子全部有黄金测试 |

### Phase 1（增量与并发）- 性能优化

| 序号 | 任务 | 预估 | 验收标准 |
|-----|------|------|---------|
| 1.1 | 实现 Rolling State 缓存（ADR-035） | 1d | 增量预热时间减少 50% |
| 1.2 | 实现失效传播引擎（扩展 ADR-022） | 1d | 级联失效自动触发 |
| 1.3 | 实现数据一致性校验（ADR-036） | 1d | CLI 命令 `ditto check consistency` |
| 1.4 | 实现 DQ 完整规则（扩展 ADR-027） | 1d | 空值率/分布漂移检测 |

### Phase 2（实时流集成）- 扩展能力

| 序号 | 任务 | 预估 | 验收标准 |
|-----|------|------|---------|
| 2.1 | 自定义算子扩展（ADR-034） | 2d | 用户可注册自定义算子 |
| 2.2 | 流式模式激活（ADR-011） | 3d | 实时因子计算链路跑通 |

---

## 5. 风险与对策

| 风险 | 级别 | 对策 |
|------|------|------|
| 表达式缓存一致性 | 中 | 算子版本变更自动失效缓存 |
| 增量计算正确性 | 高 | 黄金数据集 + 回归测试 |
| 性能 SLO 达标 | 中 | 基准测试 CI 门禁 + 自动告警 |
| 多市场日历 | 低 | Phase 2 再处理，当前仅支持 CN |

---

## 附录 A：业界对标详情

### A.1 Qlib 架构

```
Expression
    ↓
Expression Engine (解析 + 编译)
    ↓
Static Analyzer (lookback + deps)
    ↓
DAG Executor
    ↓
Data Cache (两级缓存)
```

**Ditto 借鉴点**：
- ✅ 两级缓存设计（已纳入 ADR-014）
- ⚠️ 缓存持久化（需补充 ADR-032）

### A.2 DolphinDB 架构

```
SQL-like Query
    ↓
Query Optimizer
    ↓
JIT Compiler
    ↓
Vectorized Execution
    ↓
Streaming Engine
```

**Ditto 借鉴点**：
- ✅ QuestDB 下推（ADR-027）
- ⚠️ 流式计算（Phase 2）

### A.3 Feast 架构

```
Feature Definition (YAML)
    ↓
Feature Registry (PostgreSQL)
    ↓
Online Store (Redis) + Offline Store (Parquet)
    ↓
Feature Serving
```

**Ditto 借鉴点**：
- ✅ Feature View 版本化
- ✅ PIT 正确性
- ⚠️ Entity/Time 语义（需补充）

---

## 6. 派生查询架构设计分析

> 基于文档 `docs/plans/2026-03-11-unified-derived-query-design-decisions.md`

### 6.1 架构定位评估

**设计成熟度**: ⭐⭐⭐⭐ (85%)

| 维度 | 评分 | 说明 |
|------|------|------|
| 统一模型 | 90% | `DerivedSpec + role + materialization_profile` 双轴模型清晰 |
| 存储分层 | 95% | Parquet/QuestDB/Kvrocks/SQLite 职责明确 |
| 查询边界 | 85% | Serving/Research/MixedSource 三类场景定义清晰 |
| 层级边界 | 80% | Port facade / DataHub implementation 分层合理但接口细节待补充 |
| 控制面 | 70% | 发布/版本/质量门禁协议待细化 |

### 6.2 核心模型设计

#### DerivedSpec 双轴模型

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

    # === Profile 配置（按 role 分离）===
    profile_config: FeatureProfile | FactorProfile | SignalProfile | LabelProfile

    # === 分析结果（编译时）===
    lookback: int = 0
    requires_full_day: bool = False
    dependencies: list[str] = field(default_factory=list)


@dataclass
class FeatureProfile:
    """Feature 专属配置"""
    serving_enabled: bool = True
    training_enabled: bool = True
    parity_policy: Literal["strict", "warn", "none"] = "warn"
    null_policy: Literal["propagate", "fill", "drop"] = "propagate"
    consumer_group: str = "default"


@dataclass
class FactorProfile:
    """Factor 专属配置"""
    normalization_policy: str = "cs_zscore"
    neutralization_policy: list[str] = field(default_factory=lambda: ["sector"])
    exposure_domain: str = "cn_a_share"
    evaluation_policy: str = "default"
```

### 6.3 三类查询边界

| 查询边界 | 目标场景 | 允许数据源 | 关键约束 | 返回模型 |
|---------|---------|-----------|----------|---------|
| **Serving** | 盘中/在线主链路 | QuestDB + Kvrocks | 不默认读 Parquet | 最新值/短窗口 |
| **Research** | 研究/回测/训练 | Parquet + catalog snapshot | 可复现、时间旅行 | 历史序列 |
| **MixedSource** | 对拍/核验/排障 | Parquet + QuestDB + Kvrocks | 明确跨源标记 | 差异报告 |

### 6.4 存储职责矩阵

| 组件 | 定位 | 负责 | 不负责 |
|------|------|------|--------|
| **Parquet** | 唯一真相层 | 长期历史、研究、回放、重算基准 | 盘中低延迟服务 |
| **QuestDB** | 热序列/MV层 | 热表、时间窗口查询、热点分钟因子 | 状态快照、长期真相 |
| **Kvrocks** | latest/snapshot | 最新值、状态快照、checkpoint、lock | 长期历史、复杂聚合 |
| **SQLite** | catalog/run | 元数据、运行记录、发布状态 | 热查询 |
| **Polars** | 统一语义引擎 | 复杂计算、最终裁决 | 作为持久化层 |
| **DuckDB** | ADHOC工具 | 联查、临时分析、对拍 | 常驻服务 |

### 6.5 已确认的设计决策（D1-D14）

| 决策 | 结论 | 状态 |
|------|------|------|
| D1 | 统一引擎定位为"派生数据物化与查询编排系统" | ✅ 已确认 |
| D2 | 不采用纯流式状态引擎路线 | ✅ 已确认 |
| D3 | 冷热分层职责固定 | ✅ 已确认 |
| D4 | QuestDB 预聚合 + Polars 精算 | ✅ 已确认 |
| D5 | Pushdown 升级为分段执行计划 | ✅ 已确认 |
| D6 | feature 与 factor 同期一等支持 | ✅ 已确认 |
| D7 | 根抽象升级为 Derived | ✅ 已确认 |
| D8 | 采用 role + materialization_profile 双轴模型 | ✅ 已确认 |
| D9 | feature/factor 共享底座，分离评估语义 | ✅ 已确认 |
| D10 | 查询边界分为 Serving/Research/MixedSource | ✅ 已确认 |
| D11 | MixedSource 命名确认 | ✅ 已确认 |
| D12 | 场景化查询在 Port 做 facade | ✅ 已确认 |
| D13 | 整合到 DataHub 但不硬塞进基础数据服务 | ✅ 已确认 |
| D14 | DataHub 边界优先返回 pl.DataFrame | ✅ 已确认 |

### 6.6 待解决的冲突口径

| 冲突项 | 口径 A | 口径 B | 建议 |
|--------|--------|--------|------|
| **DERIVE 执行定位** | DuckDB ADHOC | QuestDB 热数据 + Polars 现算 | ✅ 采用 B |
| **热层 TTL** | 分钟 5 日 / 日线 30 日 | 120/180/365 天类 | ⏸️ 待定 |
| **状态 Key 抽象** | `derived:state:*` | `state:feature:{id}:{inst}` | ⏸️ 待统一 |
| **分钟数据进 Parquet** | 不保留 | 需要保留 | ⏸️ 待定 |

### 6.7 未完善的设计部分

| 领域 | 缺口 | 优先级 |
|------|------|--------|
| **统一语义模型** | DerivedSpec 完整字段、entity_keys/time_keys | P0 |
| **查询实现层** | DataHub 实现结构、Port/DataHub 精确接口 | P0 |
| **DataHub 风格** | 同步/异步、返回类型一致性 | P1 |
| **物化控制面** | register → validate → materialize → publish 协议 | P1 |
| **DQ/门禁** | feature parity gate、factor evaluation gate | P1 |
| **回补/更正** | correction 协议、invalidation event 结构 | P1 |
| **存储策略** | 分钟数据保留、TTL 最终口径 | P2 |

---

## 7. 综合优化建议清单

### 7.1 ADR Backlog 汇总

#### 必须新建 ADR（跨层关键决策）

| ADR 编号 | 标题 | 优先级 | 依赖 | 核心问题 |
|---------|------|-------|------|---------|
| **ADR-032** | Unified Derived Semantic Model | P0 | 无 | DerivedSpec 完整字段、role/profile 双轴 |
| **ADR-033** | Derived Query Architecture and Layer Boundary | P0 | ADR-032 | Port facade / DataHub implementation 边界 |
| **ADR-034** | Derived Publication Lifecycle and Version Contract | P1 | ADR-032 | 发布/认证/版本协议 |
| **ADR-035** | Derived Rebuild, Invalidation, and Correction Protocol | P1 | ADR-032,034 | backfill/invalidation/correction 协议 |
| **ADR-036** | Derived Quality, Benchmark, and Certification Gates | P1 | ADR-032,034 | 质量/性能/认证门禁 |
| **ADR-037** | Hot/Cold Retention and Minute Data Policy | P2 | ADR-032,035 | 分钟数据保留、TTL 策略 |

#### 扩展既有 ADR

| ADR 编号 | 扩展内容 | 优先级 |
|---------|---------|-------|
| ADR-014 | 表达式复杂度限制、缓存失效策略 | P1 |
| ADR-022 | 失效传播级联策略 | P1 |
| ADR-027 | DQ 完整规则 | P2 |
| ADR-019 | 算子黄金数据集 | P1 |
| ADR-029 | 盘中/盘后路径（扩展到 feature + factor） | P1 |
| ADR-030 | 在线访问边界（三类查询语义） | P1 |
| ADR-031 | State Snapshot ABI（扩展到 derived 视角） | P2 |

### 7.2 冲突口径统一清单

| 序号 | 冲突项 | 当前状态 | 建议决策 | 责任 ADR |
|------|--------|---------|---------|---------|
| 1 | DERIVE 执行定位 | 口径冲突 | QuestDB 热数据 + Polars 现算 | ADR-029 扩展 |
| 2 | 热层 TTL | 口径冲突 | 需结合负载测试定案 | ADR-037 |
| 3 | 状态 Key 命名 | 命名不一致 | 统一为 `derived:state:{type}:{id}` | ADR-031 扩展 |
| 4 | 分钟数据进 Parquet | 待定 | 建议保留 30 日用于对拍 | ADR-037 |
| 5 | 表达式缓存持久化 | 未明确 | 内存 + 磁盘两级缓存 | ADR-032 |

### 7.3 实施时间线

```
Week 1-2 (Phase 0 - 补齐缺口):
├── Day 1-2:  ADR-032 Unified Derived Semantic Model
├── Day 3-4:  ADR-033 Derived Query Architecture
├── Day 5:    ADR-037 Hot/Cold Retention Policy
└── Day 6-7:  扩展 ADR-014/019/022

Week 3-4 (Phase 1 - 核心实现):
├── Day 1-3:  DerivedSpec 模型实现 + 单元测试
├── Day 4-6:  DataHub derived query 层实现
├── Day 7-10: Port facade 层实现
└── Day 11-14: 集成测试 + 文档更新

Week 5-6 (Phase 2 - 控制面):
├── Day 1-3:  ADR-034 Publication Lifecycle
├── Day 4-6:  ADR-035 Invalidation Protocol
├── Day 7-9:  ADR-036 Quality Gates
└── Day 10-14: 控制面实现 + 端到端测试
```

### 7.4 验收标准汇总

| 层级 | 验收标准 | 检查方式 |
|------|---------|---------|
| **模型层** | DerivedSpec 支持 feature/factor/signal/label | 单元测试覆盖 |
| **查询层** | 三类查询边界语义正确 | 集成测试 |
| **存储层** | 冷热数据一致性校验通过 | CI 门禁 |
| **性能层** | 满足 SLO（增量 P50 < 5s） | 基准测试 |
| **质量层** | DQ 门禁通过率 > 99% | 监控告警 |

### 7.5 风险与对策

| 风险 | 级别 | 概率 | 对策 |
|------|------|------|------|
| DerivedSpec 模型变更频繁 | 高 | 中 | 预留 `spec_json` 存储完整定义 |
| 查询边界语义混淆 | 中 | 中 | 明确 facade 注释 + 类型标记 |
| 存储分层策略不一致 | 中 | 低 | CI 门禁 + 代码审查 |
| 性能 SLO 达标 | 中 | 中 | 基准测试 + 回归告警 |
| 迁移路径复杂 | 高 | 高 | 分阶段迁移 + 兼容 facade |

---

## 附录 A：业界对标详情

### A.1 Qlib 架构

```
Expression
    ↓
Expression Engine (解析 + 编译)
    ↓
Static Analyzer (lookback + deps)
    ↓
DAG Executor
    ↓
Data Cache (两级缓存)
```

**Ditto 借鉴点**：
- ✅ 两级缓存设计（已纳入 ADR-014）
- ⚠️ 缓存持久化（需补充 ADR-032）

### A.2 DolphinDB 架构

```
SQL-like Query
    ↓
Query Optimizer
    ↓
JIT Compiler
    ↓
Vectorized Execution
    ↓
Streaming Engine
```

**Ditto 借鉴点**：
- ✅ QuestDB 下推（ADR-027）
- ⚠️ 流式计算（Phase 2）

### A.3 Feast 架构

```
Feature Definition (YAML)
    ↓
Feature Registry (PostgreSQL)
    ↓
Online Store (Redis) + Offline Store (Parquet)
    ↓
Feature Serving
```

**Ditto 借鉴点**：
- ✅ Feature View 版本化
- ✅ PIT 正确性
- ⚠️ Entity/Time 语义（需补充）

### A.4 RisingWave 架构

```
SQL Query
    ↓
Stream Planner
    ↓
Stateful Stream Executor
    ↓
State Backend (RocksDB)
    ↓
Materialized View
```

**Ditto 借鉴点**：
- ⚠️ 流批一体（Ditto 选择微批而非纯流式）
- ✅ 状态快照模式（Hash/Blob 双模式）
- ⚠️ MV 维护（QuestDB 承担部分职责）

---

## 附录 B：参考资源

### B.1 学术论文
- *101 Formulaic Alphas* - Kakushadze, 2015
- *The Barra China Equity Model* - MSCI

### B.2 开源项目
- [Qlib](https://github.com/microsoft/qlib) - 微软量化平台
- [Feast](https://feast.dev/) - 特征存储
- [DolphinDB](https://dolphindb.com/) - 时序数据库
- [RisingWave](https://risingwave.com/) - 流式数据库

### B.3 内部文档
- [issues.md](issues.md) - 待解决问题清单
- [main-design.md](main-design.md) - 主设计文档
- [industry-benchmarks.md](reference/industry-benchmarks.md) - 业界对标
- [2026-03-11-unified-derived-query-design-decisions.md](../../plans/2026-03-11-unified-derived-query-design-decisions.md) - 派生查询设计决策
