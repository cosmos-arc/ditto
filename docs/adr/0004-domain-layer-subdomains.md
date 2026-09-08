# ADR 0004: Domain Layer 子领域分层定位

**状态**: 已接受
**日期**: 2026-01-17
**决策者**: 架构团队
**相关 ADR**: [ADR 0002](0002-monorepo-structure.md), [ADR 0003](0003-data-storage-strategy.md)

---

## 背景

在量化交易系统的架构设计中，核心子领域（dq、ml、factor、risk、strategy、signal、execution）的分层定位存在模糊性。具体问题包括：

1. **dq（数据质量）** 被视为"技术约束"放在 datahub 层，但实际上包含量化业务规则（如 OHLC 一致性、涨跌停检测）
2. **ml/models** 的 "models" 产生歧义：是 ML 算法实现（Domain Layer）还是数据模型（Infrastructure Layer）？
3. **factor（因子）** 的计算逻辑与数据存储边界不清晰
4. 缺乏统一的子领域分层判断标准

这些问题导致：
- 职责边界模糊
- 依赖关系不清晰
- 违反 DDD（领域驱动设计）原则
- 与业界最佳实践不一致

---

## 决策

### 决策 1：dq（数据质量）是 Domain Layer

**定位**：`packages/data/src/ditto_data/quality/`

**理由**：

1. **dq 包含量化业务规则**，不是通用技术约束：
   - OHLC 价格一致性（close ≥ low ≤ high）- 金融知识
   - 涨跌停检测 - 交易规则
   - 成交量异常 - 市场微观结构
   - 价格合理性 - 不可能收益率检测

2. **dq 与 factor/ml/risk 并列**，都是量化子领域：
   - 有业务规则配置（YAML）
   - 有领域知识实现（checkers）
   - 不是所有系统都有 dq，但所有量化系统必须有

3. **依赖关系正确性**：
   - dq 规则由 Application Service 编排调用
   - dq 结果由 Infrastructure Layer 持久化

**组件**：

```
packages/data/src/ditto_data/quality/
├── __init__.py
├── engine.py              # QualityEngine
├── checkers/
│   ├── __init__.py
│   ├── technical.py       # L1: 技术校验（非空、唯一、类型）
│   ├── business.py        # L2: 业务规则（OHLC、涨跌停）
│   └── statistical.py     # L3: 统计异常（Z-score、分布）
└── models.py              # QualityResult, QualityIssue
```

**调用关系**：

```python
# Application Layer 编排
class IngestionService:
    def ingest_bars(self, date):
        df = self.source.fetch()

        # 调用 Domain Service
        quality = self.quality_engine.check(df, dataset="stock_daily")
        if not quality.is_valid:
            return self._handle_failure(quality)

        # 调用 Infrastructure
        self.repo.save(df)
```

---

### 决策 2：ml/models 是 Domain Layer

**澄清**：

`ml/models` 中的 "models" 指 **ML 算法实现**，不是数据模型（ORM、DTO）。

**定位**：`packages/kernel/src/ditto_kernel/ml/models/`

**理由**：

1. **ML 算法是业务逻辑**：
   - `RandomForestRegressor.fit()` - 领域算法
   - `FeatureSelector.select()` - 领域知识
   - `SharpeRatio.calculate()` - 业务指标

2. **不是数据访问**：
   - 不涉及数据库操作
   - 不涉及文件 I/O（模型持久化由 Infrastructure 负责）
   - 纯计算逻辑（输入 → 输出）

3. **类比其他子领域**：
   - `factor.calculators` - 因子算法（Domain）
   - `risk.engine` - 风险模型（Domain）
   - `ml.models` - ML 算法（Domain）

**组件**：

```
packages/kernel/src/ditto_kernel/ml/
├── __init__.py
├── engine.py              # MLEngine（训练、预测、评估）
├── models/
│   ├── __init__.py
│   ├── regressors.py      # 回归器（RandomForest, XGBoost）
│   ├── classifiers.py     # 分类器
│   └── feature_selectors.py  # 特征选择算法
└── metrics/
    ├── __init__.py
    ├── sharpe_ratio.py    # Sharpe 比率
    └── ic_rank.py         # IC Rank
```

**调用关系**：

```python
# Application Layer 编排
class MLTrainingService:
    def train_factor_model(self, date):
        # 1. 特征工程
        features = self._build_features(date)

        # 2. 调用 Domain Service 训练
        model = self.ml_engine.train(
            features=features,
            method="random_forest"
        )

        # 3. 调用 Infrastructure 保存
        self.model_registry.save(model)
```

---

### 决策 3：统一子领域分层模式

**判断标准**：

**问题：这个组件属于哪一层？**

1. ✅ 是否是**业务逻辑/规则**？ → **Domain Layer** (`packages/strategy/`, `packages/portfolio/`, `packages/risk/`, `packages/execution/`, `packages/backtest/`, `packages/kernel/`)
2. ✅ 是否是**用例编排**？ → **Application Layer** (`interfaces/services/`)
3. ✅ 是否是**数据访问**？ → **Infrastructure Layer** (`packages/data/`)

**完整映射表**：

| 子领域 | Domain Layer | Application Layer | Infrastructure Layer |
|--------|-------------|-------------------|---------------------|
| **quality** | `core.quality.*`<br>检查规则算法 | `port.services.ingestion.*`<br>编排 dq 检查 | `datahub.repositories.*`<br>保存结果、隔离数据 |
| **factor** | `core.factor.*`<br>因子计算算法 | `port.services.factor.*`<br>编排计算流程 | `datahub.stores.factors`<br>因子数据 |
| **ml** | `core.ml.*`<br>训练、预测、评估 | `port.services.ml.*`<br>编排训练流程 | `datahub.stores.models`<br>模型持久化 |
| **risk** | `core.risk.*`<br>风险模型 | `port.services.risk.*`<br>风险监控 | `datahub.stores.risk_metrics`<br>风险指标 |
| **strategy** | `core.strategy.*`<br>策略逻辑 | `port.services.trading.*`<br>交易编排 | `datahub.stores.orders`<br>订单存储 |
| **signal** | `core.strategy.signal.*`<br>信号生成 | `port.services.signal.*`<br>信号管理 | `datahub.stores.signals`<br>信号存储 |
| **execution** | `core.strategy.execution.*`<br>执行逻辑 | `port.services.execution.*`<br>执行编排 | `datahub.stores.trades`<br>成交存储 |

---

## 决策理由

### 1. DDD 原则：Domain Service 封装业务逻辑

根据 [Domain vs Application Services](https://enterprisecraftsmanship.com/posts/domain-vs-application-services/)：

- **Domain Service**：封装不属于实体/值对象的业务逻辑
- **Application Service**：编排领域工作流，不持有领域逻辑

**应用到量化系统**：

| Domain Service 示例 | 业务逻辑 |
|---------------------|---------|
| `QualityEngine.check()` | OHLC 一致性、涨跌停检测 |
| `FactorEngine.calc()` | 因子计算公式 |
| `MLEngine.train()` | 模型训练算法 |
| `RiskEngine.check()` | 回撤检测、风险度量 |

### 2. 业界实践：WorldQuant / Two Sigma

根据 [DDD in Trading Applications](https://www.infoq.com/news/2015/03/ddd-trading-example/) 和 [Quant 2.0 Architecture](https://altstreet.investments/blog/quant-2-architecture-modern-trading-stack-ai-mlops)：

**领先量化公司的架构模式**：

- dq 作为独立的 **Research Platform** 模块（Domain Layer）
- ML 作为独立的 **Alpha Discovery** 模块（Domain Layer）
- 因子作为独立的 **Factor Library** 模块（Domain Layer）
- 各模块有自己的 **Domain Service** + **Application Service**

### 3. 依赖规则：单向依赖

```
Application Layer
    ↓ 依赖
Domain Layer (packages/{strategy,portfolio,risk,execution,backtest}/, packages/kernel/)
    ↓ 依赖
Infrastructure Layer (packages/data/)
    ↓ 依赖
Foundation Layer (packages/platform/)
```

**允许的依赖**：
- ✅ Application → Domain
- ✅ Application → Infrastructure
- ✅ Domain → Infrastructure
- ✅ Infrastructure → Foundation

**禁止的依赖**：
- ❌ Infrastructure → Domain（反向依赖）
- ❌ Foundation → 其他层（零依赖）

---

## 影响分析

### 正面影响

1. ✅ **职责边界清晰**：Domain、Application、Infrastructure 各司其职
2. ✅ **依赖关系正确**：单向依赖，无循环
3. ✅ **符合 DDD 原则**：Domain Layer 封装业务逻辑
4. ✅ **与业界一致**：符合 WorldQuant/Two Sigma 的架构模式
5. ✅ **可测试性提升**：Domain Service 是纯函数，易于单元测试
6. ✅ **可扩展性增强**：新子领域可按统一模式添加

### 需要调整的部分

1. **重构 dq 模块**：
   - 从 `packages/data/src/ditto_data/dq/`
   - 移至 `packages/data/src/ditto_data/quality/`

2. **更新依赖关系**：
   - `datahub.repositories` 移除 dq 依赖
   - `port.services` 添加 `core.quality` 依赖

3. **更新配置路径**：
   - 从 `packages/data/config/dq/`
   - 移至 `data_root/config/dq/`

4. **更新文档**：
   - 架构规范（`.claude/rules/architecture.md`）
   - 系统设计（`docs/design/01_system_design.md`）

---

## 实施计划

### Phase 1: 文档更新（本 ADR）

- ✅ 创建 ADR 文档
- ⏳ 更新架构规范
- ⏳ 更新系统设计文档

### Phase 2: 代码重构（后续）

1. 创建 `packages/data/src/ditto_data/quality/`
2. 移动 dq 代码
3. 更新导入语句
4. 更新测试

### Phase 3: 验证

- 运行测试套件
- 检查依赖关系
- 验证配置加载

---

## 相关文档

- [架构规范](../architecture/README.md)
- [系统设计](../../docs/design/archive/01_system_design.md)
- [引擎设计](../../docs/design/archive/03_engine_design.md)
- [ADR 0002: Monorepo 结构](0002-monorepo-structure.md)
- [ADR 0003: 数据存储策略](0003-data-storage-strategy.md)

---

## 参考资料

### 业界实践

1. [DDD in Trading Applications - InfoQ](https://www.infoq.com/news/2015/03/ddd-trading-example/)
2. [Domain vs Application Services - Enterprise Craftsmanship](https://enterprisecraftsmanship.com/posts/domain-vs-application-services/)
3. [A Modular Architecture for Quantitative Trading - Medium](https://hiya31.medium.com/a-modular-architecture-for-systematic-quantitative-trading-systems-2a8d46463570)
4. [Quant 2.0 Architecture: AI Era - AltStreet](https://altstreet.investments/blog/quant-2-architecture-modern-trading-stack-ai-mlops)
5. [ML Pipeline Architecture - Neptune.ai](https://neptune.ai/blog/ml-pipeline-architecture-design-patterns)

### DDD 经典文献

- [Domain-Driven Design](https://www.domainlanguage.com/ddd/) - Eric Evans
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) - Uncle Bob

---

**文档版本**: 1.0
**最后更新**: 2026-01-17
