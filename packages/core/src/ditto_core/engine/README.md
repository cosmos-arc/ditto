# Unified Derived Engine

**最后更新**: 2026-03-19
**状态**: v1.0 — 已落地

> 设计总入口: `docs/design/unified-feature-factor-engine/main-design.md`

## 概要

统一特征因子引擎。通过 Expression DSL 定义因子表达式，经 Pratt Parser 解析为 AST，由 Semantic Analyzer 提取依赖与回看窗口，最终 Codegen 为 Polars 表达式执行。

## 目录结构

```
engine/
├── __init__.py              # 顶层 re-export（38 个公共符号）
├── compile_cache.py         # 两级编译缓存（L1 内存 + L2 SQLite）
├── publication_safety.py    # 发布安全模型（认证、兼容性、Shadow Diff）
├── research.py              # 研究 Spine/Dataset 快照模型
├── specs.py                 # 核心语义合约（DerivedSpec、枚举、常量）
├── expression/              # 表达式编译器子包
│   ├── compiler.py          # ExpressionCompiler 门面（tokenize → parse → analyze → codegen）
│   ├── lexer.py             # 手写词法分析器
│   ├── parser.py            # Pratt 解析器（运算符优先级）
│   ├── ast.py               # AST 节点定义（9 种节点类型）
│   ├── analyzer.py          # 语义分析（依赖提取、回看窗口、作用域判定）
│   ├── codegen.py           # Polars 表达式代码生成
│   ├── registry.py          # 运算符注册表（29 个算子）
│   └── diagnostics.py       # 编译诊断与错误类型
├── evaluation/              # 因子评估子包
│   ├── report.py            # 评估报告数据模型（ICSummary, LongShortResult, FamaMacBethResult, ...）
│   ├── evaluator.py         # 评估编排器（FactorEvaluator），支持 FM、暴露分析、Regime IC 等开关
│   └── metrics.py           # 纯 Polars 向量化指标函数（rank_ic, fama_macbeth, regime_adjusted_ic, ...）
└── materialization/         # 物化子包
    ├── contracts.py         # 编译与执行合约
    ├── models.py            # 运行时状态与生命周期枚举
    └── planner.py           # 执行规划器（计算窗口、分区）
```

## 核心概念

### Expression DSL

因子通过文本表达式定义，由编译器管线处理：

```
Expression → Lexer → Tokens → Parser → AST → Analyzer → Codegen → pl.Expr
```

支持的运算符类别：

| 类别 | 示例 | 数量 |
|------|------|------|
| 标量函数 | `abs`, `log`, `exp`, `sqrt`, `sign`, `power`, `max2`, `min2`, `clip`, `if_else` | 10 |
| 时序滚动 | `ts_mean`, `ts_std`, `ts_rank`, `ts_argmax`, `ts_argmin`, `ts_delta`, `ts_sum`, ... | 17 |
| 截面统计 | `cs_rank`, `cs_scale`, `cs_zscore`, `cs_demean`, `cs_winsorize` | 5 |
| 二元运算 | `+`, `-`, `*`, `/`, `<`, `<=`, `>`, `>=`, `==`, `!=`, `and`, `or` | 12 |

所有 `ts_*` 滚动运算自动应用 `shift(1)` 防止数据泄漏。

### DerivedSpec

统一的语义合约，定义一个 Derived Artifact 的完整元数据：

```python
DerivedSpec(
    id="factor.momentum_20d",
    version=1,
    role=DerivedRole.FACTOR,           # feature / factor / signal / label
    materialization_profile=MaterializationProfile.SERIES,  # series / state / derive / offline
    expression="ts_delta(market.close, 20) / ts_std(market.close, 20)",
    entity_keys=("instrument_id",),
    grain="1d",
    time_keys=("trade_date",),
    calendar="cn_stock",
)
```

当前 v1 合同边界：

- 仅 `feature / factor` 为已激活 role
- 仅单键 `instrument_id`
- 仅 `grain="1d"`
- `SIGNAL / LABEL`、复合键、`grain="1m"` 仍是预留能力

### 生命周期

版本状态流转：`DRAFT → MATERIALIZED → PUBLISHED → DEPRECATED → ARCHIVED`

- **物化**（materialize）：编译表达式、计算、写入 Parquet artifact
- **发布**（publish）：Shadow 对比 → 认证 → Promote 为 PUBLISHED
- Research 绑定仅 `PUBLISHED` 版本

### 编译缓存

两级缓存机制，避免重复编译：
- **L1**：进程内 dict，命中直接返回 `pl.Expr`
- **L2**：SQLite 持久化，命中时跳过 tokenize/parse/analyze，仅重新 codegen

## 层级定位

```
Port（编排层）
  ├── ExpressionCompiler.compile()     ← 调用 Core 编译
  ├── DerivedExecutionPlanner.plan()   ← 调用 Core 规划
  ├── FactorEvaluationFacade           ← 因子评估编排
  ├── FactorOrthogonalizationService   ← 因子正交化编排
  └── ArtifactPersistenceService       ← 调用 DataHub 持久化

Core（本模块）
  ├── Expression DSL → AST → pl.Expr   ← 纯计算，无 I/O
  ├── DerivedSpec / models              ← 语义合约定义
  ├── Compile cache contracts           ← 缓存协议
  └── evaluation/                       ← 因子评估指标与报告模型

DataHub
  ├── DerivedCatalogService             ← 版本/规格目录
  ├── ForwardReturnService              ← 前向收益率计算
  └── Artifact persistence              ← Parquet 文件 I/O
```

## 评估指标体系（Layer 4 完成）

### 核心 IC 指标

| 指标 | 函数 | 说明 |
|------|------|------|
| Rank IC | `rank_ic()` | Spearman 相关系数 |
| Pearson IC | `pearson_ic()` | Pearson 相关系数 |
| IC Summary | `ic_summary()` | mean, std, ICIR, t-stat, p-value, win rate |
| IC Decay | `ic_decay()` | 多 lag IC + 半衰期拟合 |
| IC Autocorrelation | `ic_autocorrelation()` | ACF(1..max_lag) |
| Sub-Period IC | `sub_period_ic()` | 按年/季度分段统计 |

### 组合分析

| 指标 | 函数 | 说明 |
|------|------|------|
| Quantile Returns | `quantile_returns()` | 等频分位组合收益 |
| Long-Short Returns | `long_short_returns()` | Sharpe(含 rf), Sortino, MaxDD, Calmar, Tail Risk |
| Tail Risk | `tail_risk_metrics()` | CVaR 95/99, 偏度, 超额峰度, 最大单日损失 |
| Turnover | `turnover()` | 单向/双向换手率 |
| Net Returns | `net_returns()` | 扣除交易成本后净收益 |

### 高级分析（Layer 4 新增）

| 指标 | 函数 | 说明 |
|------|------|------|
| Grinold-Kahn IR | `grinold_kahn_ir()` | Gordon Ritter 自相关修正 IR |
| Fama-MacBeth | `fama_macbeth()` | 两步截面回归，支持多因子 |
| Factor Exposure | `factor_exposure()` | 正交化暴露分析 + 相关矩阵 + 残差 IC |
| Regime-Adjusted IC | `regime_adjusted_ic()` | Markov Regime Switching + 转移矩阵 |
| IC Momentum | `ic_momentum()` | IC 趋势 OLS 斜率 + p-value |
| Performance Attribution | `performance_attribution()` | Selection/Timing/Interaction 分解 |

### 失效传播韧性

| 能力 | 说明 |
|------|------|
| 修复失败不终止 | `RepairBatchResult` 记录成功/失败，单条失败不阻断 batch |
| 死信队列 | 3 次重试后转入 `dead_letter`，不再被调度 |
| 优先级队列 | signal > factor > label > feature 同深度排序 |
| 跨事件去重 | NOT EXISTS 子查询 + 子集范围自动愈合 |
