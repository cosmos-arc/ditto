# ditto-analytics

**版本**: v0.3.0
**最后更新**: 2026-04-07
**状态**: 分析层（表达式编译 + 物化 + 因子 + 研究）

## 概要

分析层 -- 因子表达式编译、物化计划、因子计算、因子评估和研究数据集管理。

## 模块结构

```
ditto_analytics/
├── expression/          # 表达式语言（词法分析 → AST → 代码生成 → 编译）
│   ├── lexer.py       # 词法分析
│   ├── parser.py      # 语法分析（AST 生成）
│   ├── analyzer.py    # 语义分析
│   ├── codegen.py      # 代码生成
│   ├── compiler.py    # 编译入口
│   ├── diagnostics.py # 诊断信息
│   └── registry.py    # 函数注册表
├── factors/             # 内置因子库
│   ├── spec.py         # FactorSpec 定义
│   ├── primitives.py  # 基础因子
│   ├── technical.py    # 技术因子
│   ├── fundamental.py  # 基本面因子
│   └── alpha.py        # Alpha 因子
├── evaluation/          # 因子评估
│   ├── evaluator.py    # 评估引擎
│   ├── report.py       # 评估报告
│   └── metrics/       # 评估指标（IC / 因子分析 / 组合分析 / 尾部风险）
├── materialization/     # 物化计划
│   ├── contracts.py   # 物化契约
│   ├── models.py       # 物化模型
│   └── planner.py      # 物化计划器
├── models/             # 数据模型（因子 / 特征 / 研究）
├── research/            # 研究数据集领域模型
├── compile_cache.py      # 表达式编译缓存（SQLite）
├── publication_safety.py # 发布安全检查
└── validation.py        # 输入验证
```

## 架构定位

```
interfaces → analytics → kernel
                        → data.errors（仅错误类型）
                        → infra.foundation（仅 logger）
```

**允许的依赖**:

| 依赖 | 用途 |
|------|------|
| `ditto_kernel` | 共享类型（DerivedRole / MaterializationProfile / TimeSpec） |
| `ditto_data.errors` | 错误类型（DerivedNotImplementedError 等） |
| `ditto_infra.foundation` | 日志（仅 logger） |

**禁止依赖**: data（除 errors）/ engine / interfaces / app

## 核心功能

| 模块 | 关键组件 | 说明 |
|------|---------|------|
| expression | Lexer → Parser → Analyzer → Codegen → Compiler | 表达式编译流水线 |
| factors | FactorSpec + 4 类内置因子 | 因子定义与注册 |
| evaluation | Evaluator + Report + Metrics | IC / 因子分析 / 组合分析 / 尾部风险 |
| materialization | Contracts + Planner | 物化计划与执行 |
| research | DatasetSnapshot / KnownAtPolicy | 研究数据集领域模型 |

## 使用示例

### 表达式编译

```python
from ditto_analytics.expression import compile_expression

compiled = compile_expression("rs(close, 20) + momentum(close, 60)")
```

### 因子评估

```python
from ditto_analytics.evaluation import FactorEvaluator, FactorEvaluationReport

evaluator = FactorEvaluator()
report: FactorEvaluationReport = evaluator.evaluate(factor_values, forward_returns)
```

## 设计原则

1. **纯计算** -- 无 I/O 操作，数据通过参数注入
2. **PIT 安全** -- 代码生成器通过 `shift(1)` 预防数据泄漏
3. **编译缓存** -- SQLite 编译缓存避免重复编译
4. **发布安全** -- 物化前检查兼容性和发布状态

## 相关文档

- [Analytics 层规范](CLAUDE.md)
- [PIT 安全指南](../../.claude/rules/pit.md)
