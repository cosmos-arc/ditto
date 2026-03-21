# Ditto vs 业界顶尖量化系统 - 全面对比分析

## 0. 文档信息

- **状态**: 完成
- **作者**: Claude
- **日期**: 2026-03-05
- **适用范围**: 整体架构评估与演进建议

---

## 1. 执行摘要

### 1.1 核心结论

> **Ditto 是一个设计精良的个人量化系统，架构水平已接近机构级入门标准。** 在保持"个人可维护"的前提下，通过有选择地引入业界最佳实践，可以进一步提升系统的专业性和扩展性。

### 1.2 关键优势

| 优势领域 | 评价 |
|---------|------|
| 分层架构 | ⭐⭐⭐⭐⭐ 六层 DDD 设计，职责清晰 |
| 数据质量 | ⭐⭐⭐⭐ T0-T3 分层 + DQ 体系 |
| 技术选型 | ⭐⭐⭐⭐⭐ Polars/Pixi/DuckDB 现代栈 |
| PIT 一致性 | ⭐⭐⭐⭐ Point-in-Time 设计完善 |
| 工程质量 | ⭐⭐⭐⭐ 测试/类型/规范严格 |

### 1.3 主要差距

| 差距领域 | 评价 | 建议优先级 |
|---------|------|-----------|
| Online Feature Store | ⭐⭐ 缺失 | 🔴 高 |
| 多源数据冗余 | ⭐⭐ 单源依赖 | 🔴 高 |
| 向量化回测 | ⭐⭐⭐ 部分支持 | 🟡 中 |
| 实时风控 | ⭐⭐ 盘后为主 | 🟡 中 |
| 自动化因子挖掘 | ⭐⭐ 手动为主 | 🟢 低 |

---

## 2. 整体架构对比

### 2.1 开源框架对比矩阵

| 维度 | **Ditto** | **Zipline** | **VNPY** | **Backtrader** | **VectorBT** |
|------|-----------|-------------|----------|----------------|--------------|
| **架构模式** | 六层 DDD | 事件驱动 | 插件化 | 面向对象 | 向量化计算 |
| **数据层** | Parquet+SQLite+DuckDB | Bundles | 内存/数据库 | CSV/DB | NumPy/Pandas |
| **回测模式** | 日频为主 | 事件驱动 | 事件驱动 | 事件驱动 | 向量化 |
| **实时交易** | ✅ MiniQMT | ⚠️ 需扩展 | ✅ CTP直连 | ⚠️ 需扩展 | ❌ 纯回测 |
| **A股适配** | ✅ 原生 | ⚠️ 需适配 | ✅ 原生 | ⚠️ 需适配 | ⚠️ 通用 |
| **因子管理** | ✅ Feature Store | Pipeline | 简单 | 无 | 无 |
| **风控系统** | ✅ 多层 | ⚠️ 基础 | ✅ 完善 | ⚠️ 基础 | ❌ 无 |
| **ML 集成** | ✅ Advisor 模式 | ⚠️ 需扩展 | ⚠️ 需扩展 | ⚠️ 需扩展 | ✅ 原生 |
| **活跃度** | 🔴 个人项目 | 🟡 社区维护 | 🟢 活跃 | 🟡 稳定 | 🟢 活跃 |

### 2.2 与机构级系统对比

| 维度 | **Ditto** | **Two Sigma/WorldQuant** | **机构标准** |
|------|-----------|--------------------------|--------------|
| **数据管道** | T0-T3 批处理 | 实时流 + 批处理 | Kafka + Flink |
| **特征存储** | QuestDB + Parquet | 专用 Feature Store | Tecton/Feast |
| **研究平台** | Jupyter + 回测引擎 | 专用研究 IDE | 内部平台 |
| **执行系统** | MiniQMT | 智能路由 | VWAP/TWAP 算法 |
| **风控系统** | 多层规则引擎 | 实时风险监控 | VaR/CVaR + 实时 |
| **团队规模** | 1人 | 100+ | 10-50 |

---

## 3. 数据摄取层对比

### 3.1 Ditto 当前设计

```
┌──────────────────────────────────────────────────────────────┐
│  T0: Meta (8:00-9:00)    → calendar, stock_basic, etf_basic │
│  T1: Incremental (18:00) → stock_daily, etf_daily, adj_factor│
│  T2: Repair (2:00 AM)    → 空洞扫描 + 回填                   │
│  T3: Quality (T1后)      → DQC 批量检查                      │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 业界最佳实践对比

| 实践 | **Ditto 当前** | **业界标准** | **差距** | **建议** |
|------|---------------|-------------|----------|---------|
| **数据源冗余** | 单源 (Tushare) | 多源校验 (主+备) | 🔴 高 | 增加 AKShare 备用 |
| **增量更新** | ✅ 基于日期 | Watermark + Checkpoint | ✅ 无 | 保持 |
| **数据质量检查** | L1-L3 分层 | Great Expectations + TFDV | 🟡 中 | 考虑引入 GE |
| **延迟监控** | 无 | SLA 告警 | 🔴 高 | 添加监控 |
| **Schema 演进** | 手动 | Schema Registry | 🟡 中 | 自动化 |

### 3.3 具体建议

#### 建议 1：多源数据校验

```python
# 建议增强：多源数据交叉验证
class DataSourceValidator:
    """多源数据交叉验证"""

    def __init__(self, primary: str, secondary: str):
        self.primary = primary  # Tushare
        self.secondary = secondary  # AKShare

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        # 1. 价格合理性检查 (OHLC 关系)
        # 2. 与备用源交叉验证 (偏差 < 0.1%)
        # 3. 历史一致性检查 (无跳变)
        return ValidationResult(...)
```

#### 建议 2：数据延迟 SLA 监控

```python
# 建议增强：数据到达延迟监控
class DataSLAMonitor:
    """数据到达延迟监控"""

    SLA = {
        "T0_META": "09:00:00",
        "T1_INCREMENTAL": "18:30:00",
        "T3_QUALITY": "20:00:00",
    }

    def check_sla(self, dataset: str, actual_time: datetime) -> Alert:
        expected = self.SLA.get(dataset)
        if actual_time > expected:
            return Alert(
                level="WARNING",
                message=f"{dataset} 延迟 {actual_time - expected}",
            )
```

---

## 4. Feature Store 对比

### 4.1 业界 Feature Store 架构

```
┌────────────────────────────────────────────────────────────────┐
│                      Feature Store 架构                        │
├────────────────────────────────────────────────────────────────┤
│  Online Store (Redis/Bigtable)  ←→  Offline Store (Parquet)   │
│            ↑ 毫秒级查询                    ↑ 批量训练          │
│            │                              │                    │
│  ┌─────────┴──────────────────────────────┴─────────┐         │
│  │              Feature Registry                    │         │
│  │  • Schema Definition  • Lineage Tracking        │         │
│  │  • Version Control    • Statistics              │         │
│  └──────────────────────────────────────────────────┘         │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 Ditto Feature Store 现状

**当前实现**：
- QuestDB (时序数据) + Parquet (历史数据)
- 统一特征因子引擎（Pratt 表达式解析）
- 5 层分类的增量计算

**对比 Tecton/Feast**：

| 功能 | **Ditto** | **Tecton** | **Feast** | **差距** |
|------|-----------|------------|-----------|----------|
| 在线服务 | ❌ | ✅ | ✅ | 🔴 高 |
| 离线存储 | ✅ Parquet | ✅ | ✅ | ✅ 无 |
| 特征血缘 | ⚠️ 部分 | ✅ 完整 | ⚠️ 基础 | 🟡 中 |
| 版本管理 | ⚠️ 手动 | ✅ 自动 | ✅ | 🟡 中 |
| 增量计算 | ✅ | ✅ | ⚠️ | ✅ 优势 |
| 时间旅行 | ✅ PIT | ✅ | ✅ | ✅ 无 |

### 4.3 建议增强

#### 建议 1：特征元数据注册表

```python
@dataclass
class FeatureMetadata:
    """特征元数据定义"""
    name: str
    expression: str  # 因子表达式
    data_dependencies: list[str]
    computation_layer: int  # T1/T2/T3

    # 新增字段
    owner: str  # 负责人
    created_at: datetime
    last_updated: datetime
    statistics: FeatureStatistics  # 均值、标准差、缺失率
    lineage: list[str]  # 数据血缘

@dataclass
class FeatureStatistics:
    """特征统计信息"""
    mean: float
    std: float
    min: float
    max: float
    null_rate: float
    ic_mean: float  # Rank IC 均值
    ic_std: float
```

#### 建议 2：特征健康度监控

```python
class FeatureHealthMonitor:
    """特征退化监控"""

    def check_drift(self, feature: str, window: int = 60) -> DriftReport:
        """检测特征分布漂移"""
        # 比较最近 window 天与历史分布
        pass

    def check_ic_decay(self, feature: str) -> ICReport:
        """检测 IC 衰减"""
        # 计算滚动 IC 趋势
        # 趋势显著为负时发出警告
        pass

    def get_health_score(self, feature: str) -> float:
        """综合健康度评分 (0-100)"""
        # 结合 IC、分布、使用频率等
        pass
```

---

## 5. 回测引擎对比

### 5.1 回测引擎设计对比

| 维度 | **Ditto** | **Zipline** | **VectorBT** | **Backtrader** |
|------|-----------|-------------|--------------|----------------|
| **计算模式** | 批处理 | 事件驱动 | 向量化 | 事件驱动 |
| **性能** | 中等 | 中等 | 极快 (10-100x) | 中等 |
| **真实度** | ✅ 高 | ✅ 高 | ⚠️ 中等 | ✅ 高 |
| **灵活性** | ✅ 高 | ✅ 高 | ⚠️ 中等 | ✅ 高 |
| **滑点模型** | ✅ 完整 | ✅ 完整 | ⚠️ 简化 | ✅ 完整 |
| **交易成本** | ✅ 完整 | ✅ 完整 | ⚠️ 简化 | ✅ 完整 |

### 5.2 参考业界：VectorBT 向量化加速

```python
# VectorBT 的核心思想：向量化计算
# 适合大规模参数优化场景

import vectorbt as vbt

# 一次计算多个参数组合
price = vbt.YFData.download('AAPL').get('Close')
ma_fast = vbt.MA.run(price, [10, 20, 30])
ma_slow = vbt.MA.run(price, [50, 100, 200])

# 向量化信号生成
entries = ma_fast.ma_crossed_above(ma_slow)
exits = ma_fast.ma_crossed_below(ma_slow)

# 一次回测所有组合
pf = vbt.Portfolio.from_signals(price, entries, exits)
print(pf.stats())  # 所有组合的性能指标
```

### 5.3 建议

**场景分离**：
- **策略验证**：使用当前事件驱动引擎（高真实度）
- **参数优化**：引入向量化计算（高效率）

```python
# 建议增加：向量化参数优化模式
class VectorizedOptimizer:
    """向量化参数优化器"""

    def optimize(
        self,
        strategy: Strategy,
        param_grid: dict[str, list],
        data: pl.DataFrame,
    ) -> OptimizationResult:
        """向量化批量回测"""
        # 1. 展开参数网格
        # 2. 向量化计算所有信号
        # 3. 批量计算收益指标
        # 4. 返回最优参数组合
        pass
```

---

## 6. 风控系统对比

### 6.1 Ditto 风控设计（PRD 定义）

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Risk Guardian                         │
├─────────────────────────────────────────────────────────────┤
│  实时风险仪表盘                                              │
│  • 日/周/月度收益 & 回撤                                     │
│  • 总仓位 / 各资产桶仓位                                     │
│  • 行业暴露 / 风格暴露                                       │
│                                                             │
│  规则引擎                                                    │
│  • 仓位上限 / 单标 / 行业集中度                              │
│  • 回撤熔断（分级 + 速度）                                   │
│  • Kill Switch                                              │
│                                                             │
│  策略健康度监控                                              │
│  • 滚动 Sharpe                                              │
│  • 滚动 IC                                                  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 业界机构级风控对比

| 风控维度 | **Ditto** | **机构标准** | **差距** |
|----------|-----------|-------------|----------|
| **VaR/CVaR** | ⚠️ 简化版 | ✅ 完整实现 | 🟡 中 |
| **实时监控** | ⚠️ 盘后 | ✅ 毫秒级 | 🔴 高 |
| **压力测试** | ⚠️ 手动 | ✅ 自动化 | 🟡 中 |
| **相关性风险** | ⚠️ 滚动相关 | ✅ DCC-GARCH | 🟡 中 |
| **流动性风险** | ✅ Amihud | ✅ 完整指标 | ✅ 无 |
| **尾部风险** | ⚠️ 基础 | ✅ 极值理论 | 🟡 中 |

### 6.3 建议

#### 建议 1：增强 VaR/CVaR 计算

```python
class RiskMetrics:
    """风险管理指标计算"""

    def var_historical(
        self,
        returns: pl.Series,
        confidence: float = 0.95,
    ) -> float:
        """历史模拟法 VaR"""
        return returns.quantile(1 - confidence)

    def var_parametric(
        self,
        returns: pl.Series,
        confidence: float = 0.95,
    ) -> float:
        """参数法 VaR (假设正态分布)"""
        mu = returns.mean()
        sigma = returns.std()
        z = norm.ppf(1 - confidence)
        return mu + z * sigma

    def cvar(
        self,
        returns: pl.Series,
        confidence: float = 0.95,
    ) -> float:
        """条件风险价值 (Expected Shortfall)"""
        var = self.var_historical(returns, confidence)
        return returns.filter(returns <= var).mean()
```

#### 建议 2：实时风险监控

```python
class RealTimeRiskMonitor:
    """实时风险监控"""

    def __init__(self, threshold_config: dict):
        self.thresholds = threshold_config
        self.alerts = []

    def check_position_limit(self, position: Position) -> Alert | None:
        """检查仓位限制"""
        pass

    def check_drawdown(self, portfolio_value: float) -> Alert | None:
        """检查回撤"""
        pass

    def check_concentration(self, positions: list[Position]) -> Alert | None:
        """检查集中度"""
        pass
```

---

## 7. ML 集成对比

### 7.1 Ditto ML 定位（Advisor Only）

根据 PRD：
- ML 仅做"参谋"，不直接下单
- 用于因子权重学习、策略有效性评估、风险预算建议

### 7.2 业界 ML 量化实践对比

| 应用场景 | **Ditto** | **业界前沿** | **差距** |
|----------|-----------|-------------|----------|
| **因子挖掘** | 手动定义 | 遗传规划 / 深度学习 | 🔴 高 |
| **因子组合** | ⚠️ 线性加权 | Transformer / Attention | 🔴 高 |
| **市场 Regime** | ⚠️ 规则分类 | HMM / 深度学习 | 🟡 中 |
| **执行优化** | ❌ | RL (强化学习) | 🟡 中 |
| **风险预测** | ⚠️ 历史模拟 | ML 预测 | 🟡 中 |

### 7.3 参考业界：自动化因子挖掘

```python
# 参考 WorldQuant/Alpha101 的遗传规划因子挖掘
class GeneticFactorMiner:
    """遗传规划因子挖掘"""

    def __init__(
        self,
        base_features: list[str],
        operators: list[str],
        population_size: int = 100,
    ):
        self.base_features = base_features
        self.operators = operators  # +, -, *, /, rank, delta, etc.
        self.population_size = population_size

    def evolve(
        self,
        data: pl.DataFrame,
        target: pl.Series,
        generations: int = 50,
    ) -> list[Factor]:
        """进化搜索有效因子"""
        # 1. 初始化随机因子种群
        # 2. 计算因子 IC 作为适应度
        # 3. 选择、交叉、变异
        # 4. 返回高 IC 因子
        pass
```

---

## 8. 综合建议

### 8.1 短期优化（1-3 个月）

| 优先级 | 建议 | 预期收益 | 工作量 |
|--------|------|----------|--------|
| 🔴 高 | 增加多源数据校验（Tushare + AKShare） | 提升数据可靠性 | 2-3 天 |
| 🔴 高 | 完善特征元数据注册表 | 提升可维护性 | 3-5 天 |
| 🔴 高 | 增加数据延迟 SLA 监控 | 及时发现问题 | 1-2 天 |
| 🟡 中 | 引入 Great Expectations 数据质量框架 | 提升数据质量 | 5-7 天 |

### 8.2 中期演进（3-6 个月）

| 优先级 | 建议 | 预期收益 | 工作量 |
|--------|------|----------|--------|
| 🔴 高 | 实现 Online Feature Store | 支持实时策略 | 2-3 周 |
| 🔴 高 | 引入向量化回测引擎 | 大幅提升优化效率 | 1-2 周 |
| 🟡 中 | 完善因子健康度监控 | 早期发现因子衰减 | 1 周 |
| 🟡 中 | 增强 VaR/CVaR 计算 | 提升风控能力 | 3-5 天 |

### 8.3 长期演进（6-12 个月）

| 优先级 | 建议 | 预期收益 | 工作量 |
|--------|------|----------|--------|
| 🔴 高 | 自动化因子挖掘 | 提升研究效率 | 3-4 周 |
| 🟡 中 | 引入 ML 驱动的 Regime 识别 | 提升适应性 | 2 周 |
| 🟡 中 | 实现智能订单路由 | 降低交易成本 | 2-3 周 |
| 🟢 低 | 考虑分布式架构 | 支持更大规模 | 待评估 |

---

## 9. 参考资源

### 9.1 开源框架

- [Zipline](https://github.com/quantopian/zipline) - Quantopian 的回测引擎
- [VNPY](https://github.com/vnpy/vnpy) - Python 量化交易框架
- [Backtrader](https://github.com/mementum/backtrader) - Python 回测框架
- [VectorBT](https://github.com/polakowo/vectorbt) - 向量化回测框架
- [Feast](https://github.com/feast-dev/feast) - 开源 Feature Store

### 9.2 业界文章

- [Uber Michelangelo](https://www.uber.com/blog/michelangelo-machine-learning-platform/) - ML 平台设计
- [Tecton Feature Store](https://www.tecton.ai/blog/what-is-a-feature-store/) - Feature Store 最佳实践
- [WorldQuant Alpha101](https://arxiv.org/abs/1601.00991) - 因子挖掘论文

### 9.3 数据源

- [Tushare](https://tushare.pro/) - A 股金融数据
- [AKShare](https://github.com/akfamily/akshare) - 开源金融数据接口
- [Baostock](http://baostock.com/) - 证券宝数据

---

## 10. 变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-03-05 | 初始文档创建 | Claude |
