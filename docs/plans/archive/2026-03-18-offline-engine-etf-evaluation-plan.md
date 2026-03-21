# 离线引擎 ETF 因子评估实现计划

**日期**: 2026-03-18
**分支**: `feature/unified-feature-factor-engine-phase-1`
**状态**: Done
**前置依赖**: v1.0 Convergence Plan 全部完成（2254 tests passed, 0 arch-check broken）

---

## 1. 背景与目标

### 1.1 当前状态

统一因子引擎 v1.0 已落地，离线日频率链路完整闭环：

- Expression DSL（29 算子）→ 编译 → 物化 → Parquet artifact → 发布 → Research 数据集
- 仅支持 `market.*`（股票）数据源，ETF 无法作为因子计算输入
- 因子评估（IC、分层收益等）完全缺失
- `ExecutionPolicy` 已定义但未被编译/物化管线消费

### 1.2 目标

1. **ETF 数据贯通**：让因子引擎能以 ETF 行情为输入计算因子
2. **因子评估**：提供因子质量的量化评估能力（Rank IC、ICIR、分层收益、换手率、IC 衰减、IC 自相关、因子正交化、Turnover-adjusted IR）
3. **代码质量收敛**：修复裸异常、消费 ExecutionPolicy、清理代码异味

### 1.3 非目标

- 实时链路（QuestDB/Kvrocks）—— 继续搁置
- 策略/回测/组合/风控模块 —— 用户自研
- `grain="1m"` 分钟级支持 —— 继续阻断
- BrokerAdapter / 实盘执行 —— 不在范围

### 1.4 设计原则

- **YAGNI**：只做 ETF 因子评估所需的最小改动，不提前抽象
- **TDD**：每个修改点先写测试
- **与现有体系对齐**：遵循 Core → DataHub → Port 三层架构

---

## 2. Phase 1: ETF 数据贯通因子引擎

### 2.1 命名空间设计

**决策**：引入 `etf.*` 命名空间，与现有 `market.*`（股票）并行。

表达式写法：

```
# 股票因子（现有，不变）
ts_delta(market.close, 20) / ts_std(market.close, 20)

# ETF 因子（新增）
ts_delta(etf.close, 20) / ts_std(etf.close, 20)
ts_rank(etf.volume, 5) / ts_std(etf.pct_change, 20)
```

**列名映射**：

| 表达式引用 | 解析数据集 | 可用列 |
|-----------|-----------|--------|
| `etf.close` | `etf.daily` | open, high, low, close, pre_close, volume, amount, pct_change |
| `market.close` | `market.stock_daily` | open, high, low, close, pre_close, volume, amount（不变） |

**歧义解决**：`etf.*` 和 `market.*` 是两个独立命名空间，同一列名（如 `close`）在不同空间中引用不同数据源，不存在歧义。

### 2.2 ETF 复权显式控制

**决策**：在 `ExecutionPolicy` 上新增 `adj_type` 字段，支持显式控制。

```python
# specs.py 修改
@dataclass(frozen=True)
class ExecutionPolicy:
    pit_required: bool = True
    normalization_preset: str = "default"
    adj_type: AdjType = AdjType.NONE  # 新增
```

因子定义示例：

```python
DerivedSpec(
    id="etf.momentum_20d",
    expression="ts_delta(etf.close, 20) / ts_std(etf.close, 20)",
    execution_policy=ExecutionPolicy(adj_type=AdjType.QFQ),
    universe_id="sw_industry_etf",
)
```

**一举两得**：既实现 ETF 复权控制，又让 ExecutionPolicy 开始被消费（消除 P1 技术债 TD-01）。

### 2.3 修改清单

#### 2.3.1 Core 层

**文件: `packages/core/src/ditto_core/engine/specs.py`**

- [ ] `ExecutionPolicy` 新增 `adj_type: AdjType = AdjType.NONE` 字段
- [ ] 从 `datahub.models.enums` 或 `datahub.services.market_service` 导入 `AdjType`
  - **注意**：`AdjType` 定义在 `packages/datahub/` 下，Core 层不能依赖 DataHub
  - **方案**：将 `AdjType` 提取为 Core 层的枚举（`Literal["none", "qfq", "hfq"]`），DataHub 层做映射
  - 或者：在 Core 层定义独立的 `AdjustmentType` 枚举

**文件: `packages/core/src/ditto_core/engine/expression/analyzer.py`**

- [ ] 依赖提取逻辑识别 `etf.*` 前缀，标记为 ETF 类型依赖
- [ ] Analyzer 输出的 `Analysis` dataclass 新增 `etf_dependencies: frozenset[str]` 字段
  - 或在现有 `dependencies` 字段中保持原样，由 runtime_input 层区分

**文件: `packages/core/src/ditto_core/engine/expression/registry.py`**

- [ ] 确认现有 `P0_OPERATOR_SPECS` 对 `etf.close` 等 ETF 引用无限制
  - 当前算子不感知数据源类型，纯粹操作列名，应无需改动

#### 2.3.2 DataHub 层

**文件: `packages/datahub/src/ditto_datahub/services/market_service.py`**

- [ ] 新增 `get_etf_bars(start, end, adj=None)` 便捷方法
  - 参考 `get_stock_bars()` (行 591-628) 实现
  - 路由到 `self._read_ports.etf_bars.read()`
  - 支持 `adj` 参数：当 `adj != AdjType.NONE` 且 `self._read_ports.etf_adj is not None` 时，读取 ETF 复权因子并应用

- [ ] 新增 `_apply_etf_adjustment(df, adj, start, end)` 方法
  - 参考 `_apply_adjustment()` (行 447-513) 实现
  - 使用 `self._read_ports.etf_adj.read()` 替代 `self._read_ports.stock_adj.read()`
  - 复用 `apply_qfq_adj()` / `apply_hfq_adj()` 纯函数（在 `adjustment.py` 中）

- [ ] 新增 `save_etf_adj_factor(df, year, on_duplicate)` 方法
  - 当前 `save_adj_factor()` (行 815-870) 硬编码为 stock_adj
  - 为 ETF 复权因子写入提供通道
  - 或泛化 `save_adj_factor()` 支持 `asset_class` 参数

#### 2.3.3 Port 层

**文件: `apps/port/src/ditto_port/services/derived/runtime_input.py`**

- [ ] 新增 `_ETF_DATASET_COLUMNS` 映射（行 17-33 旁）：

```python
_ETF_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "etf.daily": frozenset({
        "open", "high", "low", "close", "pre_close",
        "volume", "amount", "pct_change",
    }),
}
```

- [ ] `_resolve_market_dependency()` (行 133-141) 支持 `etf.*` 前缀
  - 当 `dep.startswith("etf.")` 时，去掉 `etf.` 前缀后在 `_ETF_DATASET_COLUMNS` 中查找

- [ ] `load_input()` (行 53-130) 新增 ETF 依赖处理分支
  - 分离 `etf_deps` 和 `market_deps`
  - `etf.daily` → `self._market_service.get_etf_bars(start, end, adj=context.execution_policy.adj_type)`
  - 列名映射：`etf.close` → `close`（去掉 `etf.` 前缀）

**文件: `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py`**

- [ ] 确认 `apply_cs_amplification()` 对 ETF universe 的兼容性
  - 当前实现调用 `UniverseProvider.get_universe(spec.universe_id, asof=...)`
  - UniverseReader 已支持 ETF instrument_ids（asset_class 存储在 instrument 表中）
  - 预计无需改动，需验证

#### 2.3.4 摄取链路

**文件: `apps/port/src/ditto_port/services/ingestion/coordinator.py`**

- [ ] 确认 `FUND_ADJ` 数据集写入走通
  - 当前 `FUND_ADJ` 摄取已实现（ETFTushareAdapter.fetch_fund_adj()）
  - 需确认写入目标路径正确（`market/etf/adj/` vs `market/stock/adj/`）

### 2.4 测试清单

| 测试文件 | 覆盖内容 |
|---------|---------|
| `apps/port/tests/unit/services/derived/test_runtime_input_unit.py` | ETF 依赖解析、ETF 数据加载、列名映射 |
| `apps/port/tests/unit/services/derived/test_materialization_flows_unit.py` | ETF 因子端到端物化 |
| `packages/datahub/tests/unit/services/test_market_service_etf_unit.py` | get_etf_bars、ETF 复权逻辑 |
| `packages/core/tests/unit/engine/test_expression_analyzer_unit.py` | etf.* 依赖提取 |

---

## 3. Phase 2: 因子评估模块（扩展集）

### 3.1 设计定位

因子评估是因子引擎和策略/回测之间的桥梁：

```
因子 Artifact (Parquet) → FactorEvaluator → FactorEvaluationReport
                                              ├── Rank IC / IC Summary (含 ICIR)
                                              ├── IC 衰减
                                              ├── IC 自相关
                                              ├── 分层收益
                                              ├── 多空收益 (含 Factor Portfolio IR)
                                              ├── 换手率
                                              ├── Turnover-adjusted IR
                                              ├── 因子正交化
```

**放置位置**：
- 纯计算逻辑 → `packages/core/src/ditto_core/engine/evaluation/`
- 前向收益计算（需要 I/O）→ `packages/datahub/src/ditto_datahub/services/`
- 编排 Facade → `apps/port/src/ditto_port/services/derived/`

### 3.2 核心指标

#### 基础指标

| 指标 | 计算方式 | 输入 | 输出 |
|------|---------|------|------|
| **Rank IC** | 逐日 Spearman rank correlation | factor_values, forward_returns | `pl.DataFrame` (date, ic) |
| **Pearson IC** | 逐日 Pearson correlation（辅助参考） | factor_values, forward_returns | `pl.DataFrame` (date, ic) |
| **IC Summary** | IC 序列的均值、标准差、ICIR、t-stat、p-value、IC > 0 占比 | ic_series | `ICSummary` dataclass |
| **分层收益** | 按因子值分 N 组，计算各组平均收益 | factor_values, forward_returns | `pl.DataFrame` (date, quantile, return) |
| **多空收益** | Top 组 - Bottom 组 的累计收益、Sharpe、Sortino、Max Drawdown | quantile_returns | `dict[str, float]` |
| **换手率** | Two-way: `0.5 * sum(|w_t - w_{t-1}|)` + One-way: `min(buys, sells) / AUM` | weight_t, weight_{t-1} | `pl.DataFrame` (date, turnover) |

#### IR 体系（三层信息比率）

| IR 类型 | 公式 | 含义 | 输入 | 输出 |
|---------|------|------|------|------|
| **ICIR** | `Mean(IC) / Std(IC)` | 因子预测力的时间稳定性 | ic_series | `float`（含在 ICSummary） |
| **Factor Portfolio IR** | `Mean(R_LS - R_f) / Std(R_LS - R_f)` | 多空组合相对于无风险利率的风险调整收益 | ls_returns, risk_free_rate | `float` |
| **Turnover-adjusted IR** | `IC * sqrt(BR_effective)` | 考虑 IC 自相关对有效 Breadth 的折减 | IC, ic_autocorr, rebalance_freq | `float` |

> **IR 层级关系**：
> - ICIR 是基础——衡量因子预测力是否稳定（高 Mean IC + 低 ICIR = 不可靠）
> - Factor Portfolio IR 是结果——衡量多空组合扣除无风险利率后的主动收益质量
> - Turnover-adjusted IR 是修正——Fundamental Law `IR = IC * sqrt(BR)` 在 IC 自相关时高估 BR，需折减

#### 扩展指标

| 指标 | 计算方式 | 输入 | 输出 |
|------|---------|------|------|
| **IC 衰减** | 不同 lag (1/2/3/5/10/20 日) 的 Rank IC + IC half-life 拟合 | factor_values, returns_at_various_lags | `list[tuple[int, float]]` + `float \| None` |
| **IC 自相关** | IC 序列的自相关系数 (ACF)，lag-1 用于 Turnover-adjusted IR | ic_series | `list[tuple[int, float]]` |
| **因子正交化** | Sequential OLS 回归残差 / Symmetric 特征值分解 | target_factor, other_factors | `pl.DataFrame` (正交化后因子值) |
| **子期 IC 稳定性** | 按自然年/按 regime 分段计算 IC Summary | ic_series, sub_periods | `dict[str, ICSummary]` |
| **净收益** | 毛收益 - 换手率 × 单位交易成本 (bps) | gross_return, turnover, cost_bps | `float` |

### 3.3 模块结构

```
packages/core/src/ditto_core/engine/evaluation/
├── __init__.py           # 公开 API
├── metrics.py            # 纯 Polars 向量化计算函数
├── report.py             # FactorEvaluationReport 数据类
└── evaluator.py          # FactorEvaluator 编排类
```

#### `metrics.py` — 纯计算函数

```python
def rank_ic(factor_df: pl.DataFrame, return_df: pl.DataFrame,
            *, factor_col: str = "value", return_col: str = "forward_return",
            date_col: str = "trade_date", entity_col: str = "instrument_id") -> pl.DataFrame:
    """逐日计算 Spearman Rank IC.
    要求 factor_df 和 return_df 包含 (date, entity) 联合键。
    返回: pl.DataFrame[date, ic]
    """

def pearson_ic(factor_df: pl.DataFrame, return_df: pl.DataFrame,
               *, factor_col: str = "value", return_col: str = "forward_return",
               date_col: str = "trade_date", entity_col: str = "instrument_id") -> pl.DataFrame:
    """逐日计算 Pearson IC（辅助参考，对线性模型有意义）。"""

def ic_summary(ic_df: pl.DataFrame, *, ic_col: str = "ic",
               date_col: str = "trade_date") -> ICSummary:
    """IC 均值、标准差、ICIR (= IR_1)、t-stat、p-value、IC > 0 占比 (win rate)。"""

def ic_decay(factor_df: pl.DataFrame, close_df: pl.DataFrame,
             *, lags: list[int] | None = None, ...) -> tuple[list[tuple[int, float]], float | None]:
    """不同 lag 的 Rank IC，默认 lags = [1, 2, 3, 5, 10, 20]。
    同时拟合 IC half-life（IC 降至峰值一半所需天数）。
    返回: (decay_list, half_life)"""

def ic_autocorrelation(ic_df: pl.DataFrame, *, max_lag: int = 10,
                       ic_col: str = "ic") -> list[tuple[int, float]]:
    """IC 序列的自相关系数 (ACF)，lag-1 值用于 Turnover-adjusted IR 计算。"""

def turnover_adjusted_ir(
    mean_ic: float,
    ic_autocorr_lag1: float,
    rebalance_freq: int = 5,
    total_periods: int = 244,
) -> float:
    """Turnover-adjusted IR: 修正 Fundamental Law 中 IC 自相关对有效 Breadth 的高估。
    公式: IR_adj = IC * sqrt(BR * (1 - rho^2) / (1 - 2*rho*cos(pi/T) + rho^2))
    参考: Gordon Ritter (IAQF), Grinold & Kahn "Active Portfolio Management" """

def quantile_returns(factor_df: pl.DataFrame, return_df: pl.DataFrame,
                     *, n_quantiles: int = 5, ...) -> pl.DataFrame:
    """按因子值分 N 组（等频分组），计算各组平均前向收益。
    返回: pl.DataFrame[date, quantile, mean_return, count]"""

def long_short_returns(quantile_ret_df: pl.DataFrame, *,
                       quantile_col: str = "quantile",
                       return_col: str = "mean_return",
                       top_quantile: int = 5, bottom_quantile: int = 1,
                       risk_free_rate: float = 0.0,
                       periods_per_year: int = 244) -> LongShortResult:
    """多空组合的年化收益、年化波动率、Sharpe (IR_2)、Sortino、Max Drawdown。
    risk_free_rate 为年化无风险利率，用于计算 Factor Portfolio IR。"""

def turnover(current_weights: pl.DataFrame, previous_weights: pl.DataFrame,
             *, entity_col: str = "instrument_id", weight_col: str = "weight") -> pl.DataFrame:
    """Two-way 换手率 = 0.5 * sum(|w_t - w_{t-1}|)。
    返回: pl.DataFrame[date, turnover_two_way, turnover_one_way]"""

def net_returns(gross_return: float, avg_turnover: float,
                cost_bps: float = 20.0) -> float:
    """净收益 = 毛收益 - 换手率 × 单位交易成本 (bps)。"""

def orthogonalize(target: pl.DataFrame, factors: pl.DataFrame,
                  *, entity_col: str = "instrument_id",
                  date_col: str = "trade_date",
                  method: Literal["sequential", "symmetric"] = "sequential",
                  min_cross_section: int = 30) -> pl.DataFrame:
    """因子正交化：对 target 做多因子回归，取残差作为正交化后因子值。
    factors 为已有多因子的暴露矩阵。
    method="sequential" (默认): OLS 残差，顺序依赖。
    method="symmetric": 特征值分解，顺序无关。
    返回: pl.DataFrame[date, entity, orthogonalized_value]"""

def sub_period_ic(ic_df: pl.DataFrame, *, ic_col: str = "ic",
                  date_col: str = "trade_date",
                  freq: Literal["year", "quarter"] = "year") -> dict[str, ICSummary]:
    """按自然年/季度分段计算 IC Summary，评估因子在不同子期的稳定性。"""
```

#### `report.py` — 评估报告

```python
@dataclass(frozen=True)
class ICSummary:
    """IC 时间序列的统计摘要（Rank IC 和 Pearson IC 共用此结构）。"""
    mean: float              # IC 均值
    std: float                # IC 标准差
    icir: float               # ICIR = mean / std（即 IR_1: 因子预测力稳定性）
    t_stat: float             # t = mean / (std / sqrt(T))
    p_value: float            # t 检验 p-value
    win_rate: float           # IC > 0 的天数占比

@dataclass(frozen=True)
class LongShortResult:
    """多空组合的风险指标。"""
    annual_return: float      # 年化收益
    annual_volatility: float  # 年化波动率
    sharpe: float             # Sharpe = return / vol（R_f=0 时即 IR_2）
    portfolio_ir: float       # Factor Portfolio IR = (return - R_f) / vol
    sortino: float            # Sortino = return / downside_dev
    max_drawdown: float       # 最大回撤

@dataclass(frozen=True)
class FactorEvaluationReport:
    """单次因子评估的完整结果。"""
    factor_id: str
    factor_version: int
    evaluation_period: tuple[str, str]       # (start, end)
    holding_period: int                      # 前向收益持仓天数
    n_quantiles: int                         # 分组数

    # ── IC 分析（IR 第一层）──
    rank_ic_summary: ICSummary               # Rank IC 的完整统计
    pearson_ic_summary: ICSummary            # Pearson IC 的完整统计（辅助参考）

    # ── IC 稳定性与衰减 ──
    ic_decay: list[tuple[int, float]]        # [(lag, mean_ic), ...]
    ic_half_life: float | None               # IC 半衰期（天）
    ic_autocorrelation: list[tuple[int, float]]  # [(lag, acf), ...]

    # ── 分层收益（IR 第二层）──
    quantile_annual_returns: dict[int, float]   # {quantile: 年化收益}
    long_short: LongShortResult              # 多空组合完整风险指标

    # ── 换手率与成本 ──
    avg_turnover: float                      # 平均 two-way 换手率
    net_return_after_cost: float             # 净收益（毛收益 - 成本）

    # ── IR 第三层 ──
    turnover_adjusted_ir: float              # Turnover-adjusted IR

    # ── 子期稳定性 ──
    sub_period_ic: dict[str, ICSummary]      # {year: ICSummary}

    # ── 元信息 ──
    n_observations: int                      # 总观测数
    n_dates: int                             # 回测期天数
    computed_at: str                         # ISO 时间戳
```

#### `evaluator.py` — 编排类

```python
class FactorEvaluator:
    """因子评估编排：协调前向收益计算和各指标计算。"""

    def __init__(self, forward_return_provider: ForwardReturnProvider):
        self._fr_provider = forward_return_provider

    def evaluate(
        self,
        factor_df: pl.DataFrame,
        *,
        start: str | None = None,
        end: str | None = None,
        holding_period: int = 5,
        n_quantiles: int = 5,
        ic_lags: list[int] | None = None,
        ic_autocorr_lag: int = 10,
        risk_free_rate: float = 0.0,
        cost_bps: float = 20.0,
    ) -> FactorEvaluationReport:
        """端到端因子评估。

        1. 数据准备（join + null 清理 + winsorize）
        2. 计算 Rank IC + Pearson IC → ICSummary（IR 第一层）
        3. 计算 IC 衰减 + half-life
        4. 计算 IC 自相关（lag-1 用于 IR 第三层）
        5. 计算 Turnover-adjusted IR（IR 第三层）
        6. 计算分层收益 → LongShortResult（IR 第二层）
        7. 计算换手率 → 净收益
        8. 计算子期 IC 稳定性
        9. 组装 Report
        """
```

### 3.4 前向收益服务

**文件: `packages/datahub/src/ditto_datahub/services/forward_return_service.py`**

```python
class ForwardReturnService:
    """计算前向收益率。"""

    def __init__(self, market_service: MarketService):
        self._market_service = market_service

    def compute(
        self,
        asset_class: str,
        start: str,
        end: str,
        holding_period: int = 5,
        adj: AdjType = AdjType.NONE,
    ) -> pl.DataFrame:
        """计算前向收益率 = close[t+T] / close[t] - 1。

        返回: pl.DataFrame[instrument_id, trade_date, forward_return]
        注意：最后 holding_period 天的数据没有前向收益，不产出。
        """
```

### 3.5 Port 层 Facade

**文件: `apps/port/src/ditto_port/services/derived/evaluation_facade.py`**

```python
class FactorEvaluationFacade:
    """Port 层因子评估入口。"""

    def evaluate(
        self,
        factor_id: str,
        version: int,
        *,
        start: str | None = None,
        end: str | None = None,
        holding_period: int = 5,
        n_quantiles: int = 5,
        ic_lags: list[int] | None = None,
    ) -> FactorEvaluationReport:
        """编排：加载 artifact → 计算前向收益 → 评估 → 返回报告。"""

    def evaluate_orthogonal(
        self,
        target_factor_id: str,
        target_version: int,
        other_factor_ids: list[tuple[str, int]],
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> pl.DataFrame:
        """因子正交化评估。"""
```

### 3.6 正交化服务

**文件: `packages/datahub/src/ditto_datahub/services/factor_orthogonalization_service.py`**

```python
class FactorOrthogonalizationService:
    """因子正交化：通过回归去除已有因子暴露。"""

    def __init__(self, artifact_reader: DerivedArtifactReader):
        self._artifact_reader = artifact_reader

    def orthogonalize(
        self,
        target_df: pl.DataFrame,
        other_factor_dfs: list[pl.DataFrame],
    ) -> pl.DataFrame:
        """对目标因子做截面回归，取残差。
        other_factor_dfs 为其他因子的 (date, entity, value) 数据。
        使用 OLS 逐日回归。
        """
```

### 3.7 DI 注册

**文件: `apps/port/src/ditto_port/registry/datahub/derived.py`**

- [ ] 注册 `ForwardReturnService`（依赖 `MarketService`）
- [ ] 注册 `FactorOrthogonalizationService`（依赖 `DerivedArtifactReader`）

**文件: `apps/port/src/ditto_port/registry/contexts/materialization.py`**

- [ ] 在 `MaterializationBundle` 中可选包含 `FactorEvaluationFacade`

### 3.8 测试清单

| 测试文件 | 覆盖内容 |
|---------|---------|
| `packages/core/tests/unit/engine/evaluation/test_metrics_unit.py` | rank_ic, pearson_ic, ic_summary, quantile_returns, turnover, net_returns |
| `packages/core/tests/unit/engine/evaluation/test_ir_unit.py` | ICIR, turnover_adjusted_ir, portfolio_ir, IR 三层计算 |
| `packages/core/tests/unit/engine/evaluation/test_ic_decay_unit.py` | IC 衰减、IC half-life、IC 自相关 |
| `packages/core/tests/unit/engine/evaluation/test_orthogonalize_unit.py` | 因子正交化（sequential + symmetric） |
| `packages/core/tests/unit/engine/evaluation/test_evaluator_unit.py` | FactorEvaluator 编排 |
| `packages/datahub/tests/unit/services/test_forward_return_service_unit.py` | 前向收益计算 |
| `packages/datahub/tests/unit/services/test_factor_orthogonalization_service_unit.py` | 正交化服务 |
| `apps/port/tests/unit/services/derived/test_evaluation_facade_unit.py` | Port Facade 端到端 |

---

## 4. Phase 3: 代码质量收敛

### 4.1 裸异常替换

| ID | 文件 | 行号 | 修改 |
|----|------|------|------|
| ERR-01 | `apps/port/src/ditto_port/models/config.py` | ~645 | `KeyError` → `DerivedNotFoundError` |
| ERR-02 | `apps/port/src/ditto_port/services/derived/research.py` | ~383 | `KeyError` → `DerivedNotFoundError` |
| ERR-03 | `apps/port/src/ditto_port/services/derived/publication.py` | ~103 | `ValueError` → `PublicationPreconditionError` |

### 4.2 代码异味清理

| ID | 文件 | 说明 | 处理 |
|----|------|------|------|
| SM-01 | `query_facade.py:124` | `_ = self._mode_resolver.resolve()` 丢弃返回值 | 赋值给有意义的变量或删除调用 |
| SM-02 | `golden.py:112-149` | 4 处 `# type: ignore` | 逐个评估，重构消除或添加注释 |
| SM-03 | `deploy.py:81-92` | 3 处 `return-value` ignore | 逐个评估 |
| SM-04 | `bond_yield.py:248-262` | 2 处 `arg-type` ignore | 逐个评估 |

### 4.3 ExecutionPolicy 消费

Phase 1 已在 `RuntimeDerivedInputProvider` 中消费 `ExecutionPolicy.adj_type`。

额外考虑：
- [ ] `ExecutionPolicy.pit_required` 是否应在 `ResearchDatasetFacade` 中消费（控制 PIT join 行为）
- [ ] `ExecutionPolicy.normalization_preset` 是否应在物化管线中消费（控制因子标准化方式）

### 4.4 Research Spec 版本化

当前 `spec_version` 在 Research 数据集构建中硬编码为 1。

- [ ] `ResearchDatasetFacade.build()` 从 Catalog 读取 Spec 的真实版本
- [ ] `DatasetSnapshot` 绑定真实的 `spec_version`

---

## 5. 完整文件变更矩阵

### Phase 1: ETF 数据贯通

| 操作 | 文件路径 | 修改类型 |
|------|---------|---------|
| 修改 | `packages/core/src/ditto_core/engine/specs.py` | ExecutionPolicy + AdjType |
| 修改 | `packages/core/src/ditto_core/engine/expression/analyzer.py` | etf.* 依赖识别 |
| 修改 | `packages/datahub/src/ditto_datahub/services/market_service.py` | get_etf_bars, ETF 复权 |
| 修改 | `apps/port/src/ditto_port/services/derived/runtime_input.py` | ETF 数据路由 |
| 修改 | `apps/port/src/ditto_port/services/derived/materialization_orchestrator.py` | 验证 ETF universe 兼容 |
| 新建 | `packages/datahub/tests/unit/services/test_market_service_etf_unit.py` | ETF 查询测试 |
| 修改 | `apps/port/tests/unit/services/derived/test_runtime_input_unit.py` | ETF 路由测试 |
| 修改 | `packages/core/tests/unit/engine/test_expression_engine_unit.py` | ETF 依赖提取测试 |

### Phase 2: 因子评估

| 操作 | 文件路径 | 修改类型 |
|------|---------|---------|
| 新建 | `packages/core/src/ditto_core/engine/evaluation/__init__.py` | 模块 |
| 新建 | `packages/core/src/ditto_core/engine/evaluation/metrics.py` | 纯计算 |
| 新建 | `packages/core/src/ditto_core/engine/evaluation/report.py` | 报告模型 |
| 新建 | `packages/core/src/ditto_core/engine/evaluation/evaluator.py` | 编排 |
| 新建 | `packages/datahub/src/ditto_datahub/services/forward_return_service.py` | 前向收益 |
| 新建 | `packages/datahub/src/ditto_datahub/services/factor_orthogonalization_service.py` | 正交化 |
| 新建 | `apps/port/src/ditto_port/services/derived/evaluation_facade.py` | Port Facade |
| 修改 | `apps/port/src/ditto_port/registry/datahub/derived.py` | DI 注册 |
| 新建 | `packages/core/tests/unit/engine/evaluation/test_metrics_unit.py` | 指标测试 |
| 新建 | `packages/core/tests/unit/engine/evaluation/test_ir_unit.py` | IR 三层体系测试 |
| 新建 | `packages/core/tests/unit/engine/evaluation/test_ic_decay_unit.py` | IC 衰减测试 |
| 新建 | `packages/core/tests/unit/engine/evaluation/test_orthogonalize_unit.py` | 正交化测试 |
| 新建 | `packages/core/tests/unit/engine/evaluation/test_evaluator_unit.py` | 编排测试 |
| 新建 | `packages/datahub/tests/unit/services/test_forward_return_service_unit.py` | 前向收益测试 |
| 新建 | `packages/datahub/tests/unit/services/test_factor_orthogonalization_service_unit.py` | 正交化服务测试 |
| 新建 | `apps/port/tests/unit/services/derived/test_evaluation_facade_unit.py` | Facade 测试 |

### Phase 3: 代码质量

| 操作 | 文件路径 | 修改类型 |
|------|---------|---------|
| 修改 | `apps/port/src/ditto_port/models/config.py` | ERR-01 |
| 修改 | `apps/port/src/ditto_port/services/derived/research.py` | ERR-02 |
| 修改 | `apps/port/src/ditto_port/services/derived/publication.py` | ERR-03 |
| 修改 | `apps/port/src/ditto_port/services/derived/query_facade.py` | SM-01 |
| 修改 | `apps/port/src/ditto_port/services/derived/research.py` | Research 版本化 |

### 合计

| 类别 | 修改 | 新建 | 合计 |
|------|------|------|------|
| Phase 1 | 6 | 1 | 7 |
| Phase 2 | 2 | 14 | 16 |
| Phase 3 | 5 | 0 | 5 |
| **合计** | **13** | **15** | **28** |

---

## 6. 依赖关系

```
Phase 1 (ETF 数据贯通) ──────────────────────────────┐
  ├─ 1.1 ExecutionPolicy.adj_type + AdjType 定义       │
  ├─ 1.2 Analyzer 识别 etf.* 依赖                     │
  ├─ 1.3 MarketService ETF 查询 + 复权                 │
  ├─ 1.4 RuntimeInput ETF 路由                         │
  └─ 1.5 摄取链路 FUND_ADJ 验证                        │
                                                       ↓
Phase 2 (因子评估) ────────────────────────────────────┤
  ├─ 2.1 evaluation/metrics.py (纯计算)               │
  ├─ 2.2 evaluation/report.py (数据模型)              │
  ├─ 2.3 evaluation/evaluator.py (编排)               │
  ├─ 2.4 ForwardReturnService (DataHub)              │
  ├─ 2.5 FactorOrthogonalizationService (DataHub)    │
  └─ 2.6 FactorEvaluationFacade (Port)               │
                                                       │
Phase 3 (代码质量) ──── 可与 Phase 1/2 并行 ──────────┘
  ├─ 3.1 裸异常替换
  ├─ 3.2 代码异味清理
  ├─ 3.3 ExecutionPolicy 进一步消费
  └─ 3.4 Research Spec 版本化
```

---

## 7. 执行策略

### TDD 流程

每个修改点遵循 RED → GREEN → REFACTOR：

1. **RED**: 先写失败测试，定义预期行为
2. **GREEN**: 最小实现使测试通过
3. **REFACTOR**: 清理代码，确保风格一致

### 验证检查

每个 Phase 完成后运行：

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev arch-check  # 层边界检查
```

### 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `AdjType` 在 DataHub 层定义，Core 层无法直接引用 | 编译依赖问题 | Core 层定义独立的 `AdjustmentType` 枚举 |
| ETF 复权因子数据不完整（部分 ETF 缺失 adj） | 复权计算异常 | `get_etf_bars()` 对缺失 adj 的 ETF 返回原始价格 |
| 因子正交化 OLS 回归在截面较小时不稳定 | 正交化结果不可靠 | 添加最小截面样本数守卫（如 N < 30 跳过正交化） |

---

## 8. 验收标准

### Phase 1

- [ ] 表达式 `ts_delta(etf.close, 20)` 可编译、物化、产出 Parquet artifact
- [ ] `ExecutionPolicy(adj_type=AdjType.QFQ)` 正确控制 ETF 复权行为
- [ ] ETF 因子端到端测试通过（定义 → 物化 → 读取 → 验证）
- [ ] `pixi run -e dev check` 全绿

### Phase 2

- [ ] `FactorEvaluator.evaluate()` 可对任意因子 artifact 产出完整评估报告
- [ ] Rank IC、Pearson IC、分层收益、换手率、IC 衰减、IC 自相关、正交化全部可计算
- [ ] IR 三层体系完整：ICIR (IR_1) + Factor Portfolio IR (IR_2) + Turnover-adjusted IR (IR_3)
- [ ] `turnover_adjusted_ir()` 正确处理 IC 自相关对有效 Breadth 的折减
- [ ] 子期 IC 稳定性分析可按年/季度输出
- [ ] 评估结果可通过 Port Facade 访问
- [ ] `pixi run -e dev check` 全绿

### Phase 3

- [ ] ERR-01/02/03 全部替换为业务异常
- [ ] SM-01~04 逐个评估并处理
- [ ] `ExecutionPolicy` 两个保留字段（pit_required, normalization_preset）有明确消费计划
- [ ] `pixi run -e dev check` 全绿

---

## 附录 A: AdjType 跨层依赖方案

**问题**：`AdjType` 定义在 `packages/datahub/` 下（`services/market_service.py`），但 `ExecutionPolicy` 在 `packages/core/` 下，Core 层不能依赖 DataHub。

**方案 A（推荐）**：Core 层定义独立枚举

```python
# packages/core/src/ditto_core/engine/specs.py
class AdjustmentType(StrEnum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"

@dataclass(frozen=True)
class ExecutionPolicy:
    pit_required: bool = True
    normalization_preset: str = "default"
    adj_type: AdjustmentType = AdjustmentType.NONE
```

DataHub 层做映射：

```python
# packages/datahub/src/ditto_datahub/services/market_service.py
_ADJ_TYPE_MAP = {
    AdjustmentType.NONE: AdjType.NONE,
    AdjustmentType.QFQ: AdjType.QFQ,
    AdjustmentType.HFQ: AdjType.HFQ,
}
```

**优点**：零耦合，各层独立演进。
**缺点**：两个概念相同的枚举需要维护映射。

**方案 B**：将 `AdjType` 下沉到 Foundation 层

- 将 `AdjType` 移到 `packages/foundation/` 或 `packages/core/` 的公共类型模块
- DataHub 和 Core 都依赖同一来源
- **缺点**：需要改动现有 `AdjType` 的所有引用点，且 Foundation 层是否有这个职责存疑

**选择方案 A**：最小改动，不影响现有代码。

---

## 附录 B: IR 三层体系理论参考

### B.1 IR_1: ICIR（因子预测力稳定性）

```
ICIR = Mean(IC) / Std(IC)
```

- 来源：Grinold & Kahn "Active Portfolio Management" (2000)
- 含义：衡量因子每天的截面预测能力是否**一致稳定**
- 阈值：> 0.5 可用, > 1.0 优秀, > 1.5 疑似过拟合
- 与 Fundamental Law 的关系：`IR = IC * sqrt(BR)`，ICIR 直接反映等号左端

### B.2 IR_2: Factor Portfolio IR（多空组合信息比率）

```
IR_portfolio = Mean(R_LS - R_f) / Std(R_LS - R_f)
```

- 来源：Sharpe Ratio 的主动管理版本
- 含义：衡量多空组合相对于无风险利率的**主动收益质量**
- 与 ICIR 的区别：ICIR 关注预测力，Portfolio IR 关注实际组合收益
- 当 R_f = 0 时，Portfolio IR = Sharpe

### B.3 IR_3: Turnover-adjusted IR（换手率调整信息比率）

```
IR_adj = IC * sqrt(BR_effective)

BR_effective = BR * (1 - rho^2) / (1 - 2*rho*cos(pi/T) + rho^2)

其中:
  rho = IC autocorrelation at lag-1
  T = 调仓周期（天）
  BR = 年交易日数 / T（理论独立决策次数）
```

- 来源：Gordon Ritter "Optimal Turnover, Liquidity and Autocorrelation" (IAQF)
- 含义：修正 Fundamental Law 中 IC 自相关对有效 Breadth 的高估
- 问题的本质：IC 自相关高 → 排名变化慢 → 实际独立决策次数少于 BR
- 直觉：IC autocorrelation = 1 时，排名永不变化，BR_effective → 0

### B.4 三者关系

```
IR_1 (ICIR)     → 因子是否"稳定地"预测收益？
IR_2 (Portfolio) → 多空组合扣除成本后"实际"表现如何？
IR_3 (Adj IR)   → 扣除换手成本后因子"理论上限"是多少？

理想因子：IR_1 高 + IR_2 接近 IR_3（说明换手成本低，信号有效转化为收益）
问题因子：IR_1 高 + IR_2 << IR_3（说明换手成本吞噬了大量理论收益）
```

### B.5 Turnover-adjusted IR 的简化近似

对于周频调仓（T=5）的 ETF 轮动策略，可以做以下简化：
- 当 `rho < 0.3`（低自相关）时，`BR_effective ≈ BR * (1 - rho^2)`，近似直接折扣
- 当 `rho > 0.7`（高自相关）时，有效 Breadth 可能仅为 BR 的 10-30%
- 实现时使用完整公式，但报告中可同时输出 `BR` 和 `BR_effective` 以便诊断
