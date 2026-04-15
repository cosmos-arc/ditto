# Analytics 层架构规范

## 定位

Analytics 层是 **Analysis Layer（分析层）**，负责因子表达式编译、物化计划、因子计算、因子评估和研究数据集。

**核心原则**：
- 知识密集的分析计算（表达式编译、因子计算、评估指标）
- 可依赖 Data 层获取数据（通过 `ditto_data.errors` 访问错误类型）
- 无 I/O 操作，纯计算

## 依赖

```
ditto_analytics → ditto_kernel ✅
ditto_analytics → ditto_data.errors ✅（仅错误类型，DerivedNotImplementedError 等）
ditto_analytics → ditto_infra ✅（importlinter 允许，但当前源码无实际 import）
```

## 模块结构

```
ditto_analytics/
├── expression/          # 表达式语言（词法分析 → AST → 代码生成 → 编译）
│   ├── lexer.py       # 词法分析
│   ├── ast.py         # 抽象语法树定义
│   ├── parser.py      # 语法分析（AST 生成）
│   ├── analyzer.py    # 语义分析
│   ├── codegen.py      # 代码生成
│   ├── compiler.py    # 编译入口
│   ├── diagnostics.py # 诊断信息
│   └── registry.py    # 函数注册表
├── factors/             # 内置因子库（15 个模块）
│   ├── spec.py         # FactorSpec 定义
│   ├── factor_specs.py # 因子规格注册
│   ├── validate.py     # 因子验证
│   ├── primitives.py  # 基础因子
│   ├── technical.py    # 技术因子
│   ├── fundamental.py  # 基本面因子
│   ├── alpha.py        # Alpha 因子
│   ├── alternative.py  # 另类因子
│   ├── growth.py       # 成长因子
│   ├── liquidity.py    # 流动性因子
│   ├── momentum.py     # 动量因子
│   ├── quality.py      # 质量因子
│   ├── size.py         # 规模因子
│   ├── value.py        # 价值因子
│   └── volatility.py   # 波动率因子
├── evaluation/          # 因子评估
│   ├── evaluator.py    # 评估引擎
│   ├── report.py       # 评估报告
│   └── metrics/       # 评估指标
│       ├── _math.py        # 数学工具函数
│       ├── ic.py           # IC 系列
│       ├── factor_analysis.py  # 因子分析
│       ├── portfolio.py    # 组合分析
│       └── tail_risk.py    # 尾部风险
├── materialization/     # 物化计划
│   ├── contracts.py   # 物化契约
│   ├── models.py       # 物化模型
│   └── planner.py      # 物化计划器
├── models/             # 数据模型
│   ├── factors.py      # 因子模型
│   └── features.py     # 特征模型
├── research/            # 研究数据集
│   └── domain.py       # 领域模型
├── compile_cache.py      # 表达式编译缓存
├── publication_safety.py # 发布安全检查
└── validation.py        # 输入验证
```

## 依赖规则

```
┌─────────────────────────────────────┐
│  Analytics 可依赖                    │
│  analytics → kernel ✅                │
│  analytics → data.errors ✅            │
│  analytics → infra ✅（importlinter 允许） │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Analytics 禁止依赖                  │
│  analytics → data（除 errors） ❌      │
│  analytics → engine ❌                │
│  analytics → interfaces ❌            │
│  analytics → app ❌                   │
└─────────────────────────────────────┘

## 测试规范

```
packages/analytics/
├── src/ditto_analytics/
└── tests/
    ├── unit/
    └── integration/
```

### 运行测试

```bash
pixi run -e dev pytest packages/analytics/tests/
```
