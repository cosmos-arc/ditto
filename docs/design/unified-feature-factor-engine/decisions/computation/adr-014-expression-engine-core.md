# ADR-014: 表达式引擎核心设计

**状态**: 已决策（2026-03-05）| 更新（2026-03-12）

---

## 背景

表达式引擎是因子计算的核心组件，需要明确以下关键设计点：
1. Codegen 输出目标（生成什么级别的代码）
2. 表达式缓存策略（是否缓存编译结果）
3. 空值处理策略（运行时 null 如何传播）
4. 错误报告格式（编译期错误如何呈现）
5. 表达式复杂度限制（防止性能问题和资源耗尽）

---

## 决策

### 1. Codegen 输出目标：Polars Expr

生成 `pl.Expr` 对象，而非完整的 LazyFrame。

```python
# 表达式: ts_mean(close, 20)
# Codegen 输出:
pl.col("close").rolling_mean(window_size=20, min_periods=1, closed="left")
```

**理由**:
- **可组合性**：Expr 可以自由组合成复杂表达式
- **延迟执行**：Polars Lazy 执行引擎自动优化
- **灵活性**：单因子计算和研究场景友好
- **业界一致**：Qlib、BigQuant 均采用表达式级别输出

---

### 2. 表达式缓存：Spec 级缓存 + CSE（直接 Phase 1）

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

---

### 3. 空值处理：严格模式（Null 传播）

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
        .rolling_mean(window_size=window, min_periods=1, closed="left")
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

---

### 4. 编译期错误报告：带位置高亮的详细错误

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

---

### 5. 表达式复杂度限制：编译期门禁

为防止性能问题和资源耗尽，在编译期对表达式复杂度进行强制检查。

#### 5.1 限制类型

| 类型 | 指标 | 阈值 | 行为 |
|------|------|------|------|
| **硬限制** | `max_length` | 500 | 编译期拒绝 |
| **硬限制** | `max_depth` | 10 | 编译期拒绝 |
| **硬限制** | `max_nodes` | 100 | 编译期拒绝 |
| **硬限制** | `max_lookback` | 252 | 编译期拒绝 |
| **软估计** | `estimated_execution_time` | - | 告警 |
| **软估计** | `estimated_memory` | - | 告警 |

#### 5.2 硬限制 vs 软估计

**硬限制（编译期拒绝）**：
- 静态、可确定的复杂度指标
- 超限时抛出 `CompileError`，拒绝编译
- 保证 spec 可移植性和环境一致性

**软估计（编译期告警）**：
- 运行时成本预估
- 超限时记录警告日志，不阻止编译
- 用于辅助决策，不作为门禁

#### 5.3 阈值说明

| 指标 | 阈值 | 理由 |
|------|------|------|
| `max_length = 500` | 对齐 WorldQuant Brain 经验值，足够覆盖大多数单表达式 alpha |
| `max_depth = 10` | 防止嵌套失控，与 WorldQuant 上限一致 |
| `max_nodes = 100` | 比字符数更能反映 AST 复杂度，能拦住"字符不长但结构很碎"的表达式 |
| `max_lookback = 252` | 一个交易年为上限，超过应通过物化/特征分层表达 |

#### 5.4 实现要点

```python
@dataclass
class ComplexityReport:
    """复杂度检查报告"""
    length: int
    depth: int
    node_count: int
    max_lookback: int
    estimated_time: float | None = None
    estimated_memory: int | None = None

    # 告警信息
    warnings: list[str] = field(default_factory=list)


class ComplexityAnalyzer:
    """复杂度分析器"""

    HARD_LIMITS = ComplexityLimits(
        max_length=500,
        max_depth=10,
        max_nodes=100,
        max_lookback=252,
    )

    def validate(self, ast: ASTNode) -> ComplexityReport:
        """验证表达式复杂度（编译期门禁）"""
        report = self._analyze(ast)

        # 硬限制检查：超限即拒绝
        errors = []
        if report.length > self.HARD_LIMITS.max_length:
            errors.append(f"表达式长度 {report.length} 超过限制 {self.HARD_LIMITS.max_length}")
        if report.depth > self.HARD_LIMITS.max_depth:
            errors.append(f"嵌套深度 {report.depth} 超过限制 {self.HARD_LIMITS.max_depth}")
        if report.node_count > self.HARD_LIMITS.max_nodes:
            errors.append(f"节点数 {report.node_count} 超过限制 {self.HARD_LIMITS.max_nodes}")
        if report.max_lookback > self.HARD_LIMITS.max_lookback:
            errors.append(f"回溯窗口 {report.max_lookback} 超过限制 {self.HARD_LIMITS.max_lookback}")

        if errors:
            raise CompileError(
                message="表达式复杂度超限",
                error_code="E050_COMPLEXITY_EXCEEDED",
                details=errors,
            )

        # 软估计：超限告警
        if report.estimated_time and report.estimated_time > ESTIMATED_TIME_WARN_THRESHOLD:
            report.warnings.append(f"预估执行时间较长: {report.estimated_time:.2f}s")

        return report
```

#### 5.5 白名单策略

**不提供普通白名单**，原因：
- 破坏 spec 可移植性
- 导致 cache、CI、生产行为不一致
- 容易变成"先放开再说"，最后架空限制

**例外处理**：
- 如有特殊需求（如极少数长期窗口需求），走"新算子/新特征分层/离线预计算"方案
- 不让单表达式突破门禁

#### 5.6 配置策略

**只配阈值，不配"是否拒绝"**：
- 避免环境漂移（同一表达式在 A 环境能过、B 环境被拒）
- 可根据环境调整阈值宽松度：
  - 研发环境：阈值略宽
  - 生产环境：阈值更严
- 超过阈值后的行为始终是拒绝

#### 5.7 业界对标

| 平台 | 长度限制 | 深度限制 | 节点限制 | lookback 限制 |
|------|---------|---------|---------|---------------|
| WorldQuant Brain | 500 字符 | 10 层 | - | - |
| Qlib | - | - | - | 警告 |
| **Ditto** | **500 字符** | **10 层** | **100 节点** | **252（硬限制）** |

---

## 决策汇总

| 决策点 | 决策 | 理由 |
|-------|------|------|
| **Codegen 输出** | Polars Expr | 可组合、延迟执行、易于优化 |
| **表达式缓存** | Spec 级 + CSE（Phase 1） | Qlib 验证有效，避免重复计算 |
| **空值处理** | 严格模式（null 传播） | 数据质量问题可见，便于排查 |
| **错误报告** | 带位置高亮的详细错误 | 类似 Rust 编译器，开发体验好 |
| **复杂度限制** | 编译期硬限制 + 软估计告警 | 防止性能问题，保证 spec 可移植性 |

---

## 更新记录

### 2026-03-12
- 新增决策 5：表达式复杂度限制（P1-3）
- 定义四项硬限制：length=500, depth=10, nodes=100, lookback=252
- 明确不提供普通白名单，只配阈值不配行为

### 2026-03-05
- 初始版本
- 决策：Codegen 输出、表达式缓存、空值处理、错误报告
