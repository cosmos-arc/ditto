# Features 层架构规范

## 定位

Features 是**因子、表达式、衍生数据与发布安全能力平面**，负责：
- 表达式语言（词法分析、语法解析、编译、代码生成）
- 因子定义（spec、primitives、category implementations）
- 物化计划（依赖推导、计划编排）
- 因子评估（IC、Fama-MacBeth、暴露分析、归因分析）
- 衍生数据服务（artifact 持久化、并发物化、GC）
- 发布安全记录服务与发布安全运行时存储（manifest、minimal DQ、shadow report、certification）

**核心原则**：
- 表达式、因子和物化计划保持纯计算；feature-owned 的运行时/存储适配位于 `storage/`，通过 contracts/Protocols 与服务交互
- `expression` 不依赖 `materialization`（单向依赖）
- 因子定义依赖表达式和 spec，不依赖上层编排

## 允许依赖

```
ditto_features → ditto_kernel ✅
ditto_features → ditto_platform ✅
```

外部依赖：polars, numpy, cachebox, orjson

## 禁止依赖

```
ditto_features → ditto_strategy ❌
ditto_features → ditto_portfolio ❌
ditto_features → ditto_risk ❌
ditto_features → ditto_execution ❌
ditto_features → ditto_backtest ❌
ditto_features → ditto_analysis ❌
ditto_features → ditto_application ❌
ditto_features → ditto_apps ❌
```

## 内部目录职责

```
ditto_features/
├── di/                   # Features Provider 注册
│   └── storage.py        # Feature-owned storage Provider
├── expression/           # 表达式语言引擎
│   ├── lexer.py          # 词法分析
│   ├── parser.py         # 语法解析 → AST
│   ├── ast.py            # AST 节点定义
│   ├── analyzer.py       # 语义分析（类型推断、依赖收集）
│   ├── compiler.py       # AST → 可执行编译产物
│   ├── codegen.py        # 代码生成
│   ├── contracts.py      # 表达式契约类型
│   ├── diagnostics.py    # 诊断信息
│   └── registry.py       # 算子注册表
├── factors/              # 因子定义
│   ├── spec.py           # FactorSpec 基类
│   ├── factor_specs.py   # 因子规格注册
│   ├── primitives.py     # 原始因子
│   ├── validate.py       # 因子校验
│   ├── alpha.py          # Alpha 因子
│   ├── value.py          # 价值因子
│   ├── size.py           # 规模因子
│   ├── momentum.py       # 动量因子
│   ├── volatility.py     # 波动率因子
│   ├── liquidity.py      # 流动性因子
│   ├── quality.py        # 质量因子
│   ├── growth.py         # 成长因子
│   ├── fundamental.py    # 基本面因子
│   ├── technical.py      # 技术因子
│   └── alternative.py    # 另类因子
├── materialization/      # 物化计划
│   ├── contracts.py      # 物化契约
│   ├── models.py         # 物化模型
│   └── planner.py        # 依赖推导与计划编排
├── evaluation/           # 因子评估
│   ├── evaluator.py      # 评估执行器
│   ├── report.py         # 评估报告
│   └── metrics/          # 评估指标
│       ├── _math.py         # 数学工具
│       ├── attribution.py   # 归因分析
│       ├── exposure.py      # 暴露分析
│       ├── factor_analysis.py # 因子分析
│       ├── fama_macbeth.py  # Fama-MacBeth 回归
│       ├── ic.py            # IC 指标
│       ├── orthogonalization.py # 正交化
│       ├── portfolio.py     # 组合指标
│       └── tail_risk.py     # 尾部风险
├── models/               # 数据模型
│   ├── features.py       # Feature 模型
│   ├── factors.py        # Factor 模型
│   └── derived.py        # 衍生数据模型
├── services/             # 衍生数据服务
│   ├── derived_catalog_service.py
│   ├── derived_shadow_slot_service.py
│   ├── publication_safety_record_service.py
│   └── derived/          # 衍生数据子服务
│       ├── queries.py           # 查询接口
│       ├── query_service.py     # 查询服务
│       ├── artifact_persistence_service.py
│       ├── artifact_reader.py
│       ├── concurrent_materializer.py
│       ├── garbage_collector.py
│       └── gc_models.py
├── config/               # 配置
│   └── artifact_store.py # Artifact 存储配置
├── observability/        # 可观测性
│   └── metrics.py        # 指标
├── storage/              # Feature-owned 存储适配
│   ├── derived_artifact_writer.py
│   ├── parquet/          # 因子/特征 Parquet 存储
│   ├── runtime/          # 发布运行时记录存储
│   │   ├── publication_safety/
│   │   └── publication_shadow_sqlite/
│   └── sqlite/           # 衍生 artifact SQLite 存储
├── errors.py             # 错误定义
├── validation.py         # 校验工具
├── publication_safety.py # 发布安全
└── compile_cache.py      # 编译缓存
```

**内部依赖方向**：
```
contracts/models → expression → factors → materialization → evaluation
```

## 测试位置

```
packages/features/tests/
├── unit/
│   ├── test_expression_engine_unit.py
│   ├── test_expression_parser_unit.py
│   ├── test_expression_type_check_unit.py
│   ├── test_expression_diagnostics_unit.py
│   ├── test_codegen_unit.py
│   ├── test_publication_safety_unit.py
│   ├── test_validation_unit.py
│   ├── test_materialization_models_unit.py
│   ├── test_operator_golden_data.py
│   ├── evaluation/
│   │   ├── test_metrics_unit.py
│   │   ├── test_evaluator_unit.py
│   │   ├── test_fama_macbeth_unit.py
│   │   ├── test_factor_exposure_unit.py
│   │   ├── test_representative_factor_ic.py
│   │   ├── test_evaluation_metrics_unit.py
│   │   ├── test_evaluation_regime_unit.py
│   │   └── test_evaluation_attribution_unit.py
│   └── factors/
│       ├── test_alternative_factors_unit.py
│       ├── test_technical_specs_unit.py
│       ├── test_factor_data_availability.py
│       ├── test_factor_definitions.py
│       └── test_factor_context_unit.py
```

## 典型导入示例

```python
# 表达式编译
from ditto_features.expression import compile_expression

# 因子定义
from ditto_features.factors.spec import FactorSpec

# 物化计划
from ditto_features.materialization.planner import MaterializationPlanner

# 因子评估
from ditto_features.evaluation.evaluator import FactorEvaluator

# 衍生数据查询
from ditto_features.services.derived.query_service import DerivedQueryService

# 发布安全记录
from ditto_features.services.publication_safety_record_service import PublicationSafetyRecordService
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/features/tests/unit -q
pixi run -e dev type packages/features/src
pixi run -e dev arch-check
```
