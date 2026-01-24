# DataHub 数据架构设计方案

> 创建日期: 2026-01-24
> 版本: v1.0
> 状态: 设计草案

> **目的**: 基于 ETF 行业轮动策略的需求，设计一套符合量化业界最佳实践的数据架构，支持基础数据、特征和因子的分层管理，同时考虑实时和批量计算的需求。

---

## 一、背景与问题陈述

### 1.1 当前问题

在 DataHub 数据存储结构分析和数据集字段映射的基础上，识别出以下核心问题：

1. **数据集划分是否符合业界最佳实践？**
   - 当前有 `stock_daily`、`etf_daily`、`adj_factor` 等，都是基础数据
   - 缺少明确的基础数据/特征/因子分层

2. **source 字段如何设计？**
   - sid 是标的唯一标识符
   - 但同一标的可能来自不同数据源（如新闻、分钟行情）
   - source 字段是否需要下沉到每个数据集层级？

3. **DataHub 是否需要拆分？**
   - 当前 DataHub 包含所有功能，显得过大
   - 需要按基础/特征/因子等大类拆分

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **逻辑分域，物理统一** | 保持一个 DataHub 包，内部通过 domain 分层 |
| **主源优先，多源协同** | tushare 作为主源，其他源用于质量校验和补充 |
| **特征因子持久化** | 支持增量计算、版本管理和追溯 |
| **PIT 友好** | 所有时序数据支持 Point-in-Time 查询 |
| **统一读写接口** | 不同数据域使用统一的 Store/Accessor 模式 |

---

## 二、核心概念定义

### 2.1 基础数据 vs 特征 vs 因子

基于业界调研（WorldQuant、Quantopian、DolphinDB 等），三者的精确区分如下：

#### 基础数据

**定义**: 从外部获取的原始数据，未经复杂计算。

**特点**:
- 从外部数据源获取
- 未经复杂计算
- 是"事实"而非"观点"
- 通常是时序数据或横截面数据

**示例**:
```python
# 市场数据
{
    "sid": 1000001,
    "trade_date": "2024-01-15",
    "open": 10.5,
    "close": 10.8,
    "volume": 1000000
}

# 基本面数据
{
    "sid": 1000001,
    "report_date": "2024-03-31",
    "pe_ratio": 15.2,
    "pb_ratio": 2.3,
    "roe": 0.18
}
```

#### 特征

**定义**: 对基础数据进行**单步或简单转换**得到的数据。

**特点**:
- 通过**简单计算**从基础数据转换
- 不一定有金融理论支撑
- 用于描述数据模式，供 ML 模型使用
- 计算通常是确定性的

**示例**:
```python
# 技术指标特征（WorldQuant 风格）
特征1: ts_mean(close, 20)              # 20日均线
特征2: ts_delta(close, 1) / close      # 日收益率
特征3: rank(volume)                    # 成交量排名
特征4: correlation(close, volume, 10)  # 价量相关性

# 实现示例
def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI 特征"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

#### 因子

**定义**: **具有金融理论支撑**的标准化暴露度，可直接用于组合构建和风险归因。

**特点**:
- 有**金融理论支撑**（如 Fama-French 三因子）
- 经过**标准化**（z-score）
- 经过**去极值**（winsorize）
- 经过**正交化**（行业中性化）
- 可直接用于组合构建和风险归因

**示例**:
```python
# 价值因子（多步计算）
def compute_value_factor(df: pd.DataFrame) -> pd.Series:
    """
    计算价值因子暴露度
    步骤：
    1. 计算基础特征：PE、PB
    2. 去极值：3σ 剪裁
    3. 标准化：z-score
    4. 行业中性化：残差化
    5. 合成：加权平均
    """
    # 1. 基础特征
    pe_inv = 1 / df['pe_ratio']      # 市盈率倒数
    pb_inv = 1 / df['pb_ratio']      # 市净率倒数

    # 2. 去极值（MAD 方法）
    def winsorize(series: pd.Series, n: int = 3) -> pd.Series:
        median = series.median()
        mad = (series - median).abs().median()
        upper = median + n * mad
        lower = median - n * mad
        return series.clip(lower, upper)

    pe_inv_clean = winsorize(pe_inv)
    pb_inv_clean = winsorize(pb_inv)

    # 3. 标准化
    def standardize(series: pd.Series) -> pd.Series:
        return (series - series.mean()) / series.std()

    pe_z = standardize(pe_inv_clean)
    pb_z = standardize(pb_inv_clean)

    # 4. 行业中性化（回归取残差）
    def neutralize(factor: pd.Series, industry: pd.Series) -> pd.Series:
        """对行业哑变量回归，取残差"""
        from sklearn.linear_model import LinearRegression
        X = pd.get_dummies(industry).astype(float)
        model = LinearRegression()
        model.fit(X, factor)
        return factor - model.predict(X)

    pe_neutral = neutralize(pe_z, df['industry'])
    pb_neutral = neutralize(pb_z, df['industry'])

    # 5. 合成因子
    value_factor = 0.5 * pe_neutral + 0.5 * pb_neutral

    return value_factor
```

#### 对比总结表

| 维度 | 基础数据 | 特征 | 因子 |
|------|---------|------|------|
| **数据来源** | 外部获取 | 计算得到 | 计算得到 |
| **计算复杂度** | 无 | 低（1-2步） | 高（多步） |
| **理论支撑** | 事实 | 无需 | 必需 |
| **标准化处理** | 无 | 无 | 必须标准化 |
| **行业中性化** | 无 | 无 | 通常需要 |
| **使用场景** | 输入 | ML 特征、辅助分析 | 组合构建、风险归因 |
| **示例** | close=10.8 | RSI=65.5 | 价值因子暴露度=1.2σ |

---

## 三、DataHub 内部分层架构

### 3.1 目录结构设计

```
packages/datahub/src/ditto_datahub/
├── hub.py                      # 统一入口（保持不变）
│
├── domains/                    # 新增：数据域分层
│   ├── __init__.py
│   │
│   ├── raw/                    # 原始市场数据域
│   │   ├── __init__.py
│   │   ├── market/             # 市场行情
│   │   │   ├── bars_accessor.py
│   │   │   ├── bars_store.py
│   │   │   └── adj_factor_accessor.py
│   │   ├── corporate/          # 公司行为（分红、拆股）
│   │   ├── fundamental/        # 基本面数据
│   │   │   ├── financial_accessor.py
│   │   │   └── financial_store.py
│   │   └── reference/          # 参考数据
│   │       ├── security_accessor.py
│   │       ├── calendar_accessor.py
│   │       └── universe_accessor.py
│   │
│   ├── feature/                # 特征数据域
│   │   ├── __init__.py
│   │   ├── technical/          # 技术指标特征
│   │   │   ├── price_feature_accessor.py
│   │   │   ├── volume_feature_accessor.py
│   │   │   └── momentum_feature_accessor.py
│   │   ├── fundamental/        # 基本面特征
│   │   │   ├── valuation_feature_accessor.py
│   │   │   └── growth_feature_accessor.py
│   │   └── alternative/        # 另类数据特征
│   │       └── sentiment_feature_accessor.py
│   │
│   └── factor/                 # 因子数据域
│       ├── __init__.py
│       ├── style/              # 风格因子
│       │   ├── value_factor_accessor.py
│       │   ├── momentum_factor_accessor.py
│       │   ├── quality_factor_accessor.py
│       │   └── volatility_factor_accessor.py
│       ├── industry/           # 行业因子
│       │   └── industry_factor_accessor.py
│       └── risk/               # 风险因子
│           └── risk_factor_accessor.py
│
├── sources/                    # 数据源层（保持不变）
├── stores/                     # 通用存储组件
├── runtime/                    # 运行时支持
└── meta/                       # 元数据和配置
```

### 3.2 Hub 入口设计

```python
# hub.py
class DataHub:
    """统一数据访问入口"""

    # ============ Raw Data Domain ============
    @property
    def raw(self) -> RawDataDomain:
        return RawDataDomain()

    # ============ Feature Domain ============
    @property
    def feature(self) -> FeatureDomain:
        return FeatureDomain()

    # ============ Factor Domain ============
    @property
    def factor(self) -> FactorDomain:
        return FactorDomain()

    # ============ 兼容现有代码 ============
    @property
    def bars(self) -> BarsAccessor:
        return self.raw.market.bars

    @property
    def securities(self) -> SecuritiesAccessor:
        return self.raw.reference.securities

    @property
    def calendar(self) -> CalendarAccessor:
        return self.raw.reference.calendar

# 使用示例
hub.raw.market.bars.get(...)
hub.feature.technical.momentum.get(...)
hub.factor.style.value.get(...)
```

---

## 四、source 字段设计策略

### 4.1 分层 source 策略

基于你的需求（主源 + 质量校验 + 补充数据），推荐以下设计：

| 数据域 | source 策略 | 键列设计 | 原因 |
|--------|------------|---------|------|
| **Raw Market** | 主源必需，辅助源可选 | `(sid, trade_date, source)` | 支持多源质量对比 |
| **Reference** | 主键包含 source | `(sid, source)` 或单独 mapping 表 | 支持多源映射 |
| **Feature** | 计算来源追踪 | `(sid, trade_date, feature_id, source?)` | feature_id 标识特征类型 |
| **Factor** | 不需要 source | `(sid, trade_date, factor_id)` | 因子是计算产物，与源无关 |

### 4.2 质量校验数据存储方案

针对"数据结构无法对齐"的问题，建议：

```python
# 新增：QualityComparisonStore
class QualityComparisonStore:
    """跨数据源质量对比存储"""

    def write_comparison(
        self,
        sid: int,
        trade_date: date,
        primary_source: str,      # "tushare"
        compare_source: str,      # "tdx"
        field: str,               # "close"
        primary_value: float,
        compare_value: float,
        diff_abs: float,
        diff_pct: float,
        is_match: bool
    ):
        """存储字段级别的质量对比结果"""
        pass
```

**存储路径**：`meta/quality_comparison/{primary_source}_{compare_source}.parquet`

---

## 五、因子存储策略：窄表 vs 宽表

根据 DolphinDB 和 Feature Store 的实践，**推荐窄表为主，宽表为辅**。

### 5.1 窄表存储

**特点**：`[sid, trade_date, factor_id, exposure, version]`

| 优点 | 缺点 |
|------|------|
| 新增因子无需改表结构 | 查询多因子需要 JOIN |
| 支持高并发写入 | 单次查询性能较低 |
| 版本管理简单 | 需要透视操作用于分析 |
| 历史追溯方便 | 存储空间可能更大 |

**适用场景**：
- 因子数量多且频繁增删（研究阶段）
- 需要严格版本管理
- 增量更新频繁

### 5.2 宽表存储

**特点**：`[sid, trade_date, value_factor, momentum_factor, quality_factor, ...]`

| 优点 | 缺点 |
|------|------|
| 查询性能高 | 新增因子需要改表结构 |
| 直接用于 ML 训练 | 版本管理困难 |
| OLAP 分析友好 | 不适合频繁变更 |

**适用场景**：
- 因子数量相对固定
- 生产环境的高性能查询
- 已验证的稳定因子

### 5.3 推荐的混合策略

```
┌─────────────────────────────────────────────────────────────────────┐
│                         存储层架构                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  主存储：窄表 (Factor Narrow Table)                          │   │
│  │                                                             │   │
│  │  路径：factors/narrow/{year}.parquet                        │   │
│  │  键列：(sid, trade_date, factor_id, version)                │   │
│  │  数据列：exposure, metadata                                   │   │
│  │                                                             │   │
│  │  用途：                                                      │   │
│  │  - 所有因子的主存储                                          │   │
│  │  - 支持增量写入                                              │   │
│  │  - 版本管理                                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              │ 定期 Pivot                           │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  辅助存储：宽表 (Factor Wide Table)                          │   │
│  │                                                             │   │
│  │  路径：factors/wide/{version}/{year}.parquet                 │   │
│  │  键列：(sid, trade_date)                                     │   │
│  │  数据列：value_factor, momentum_factor, ...                  │   │
│  │                                                             │   │
│  │  用途：                                                      │   │
│  │  - 生产环境高性能查询                                        │   │
│  │  - ML 模型训练                                               │   │
│  │  - OLAP 分析                                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 六、因子元数据管理

### 6.1 因子注册表

```sql
-- factor_registry 表结构
CREATE TABLE factor_registry (
    -- 基础信息
    factor_id          VARCHAR(50) PRIMARY KEY,     -- 如 "value_pe", "momentum_20d"
    factor_name        VARCHAR(100) NOT NULL,       -- 显示名称 "PE 价值因子"
    factor_category    VARCHAR(50) NOT NULL,        -- 类别: style/industry/risk/technical
    factor_subcategory VARCHAR(50),                 -- 子类别: value/momentum/quality

    -- 方法学定义
    description        TEXT,                        -- 因子描述
    economic_hypothesis TEXT,                       -- 经济学假设
    formula            TEXT,                        -- 计算公式或表达式
    implementation_code TEXT,                       -- 代码仓库路径 + commit hash

    -- 参数配置
    parameters         JSON,                        -- 参数定义: {"window": 20, "method": "rank"}

    -- 数据依赖
    data_sources       JSON,                        -- 依赖的数据源: ["close", "volume", "pe_ratio"]
    dependent_factors  JSON,                        -- 依赖的其他因子: []

    -- 后处理方法
    winsorization_method VARCHAR(50),               -- 去极值方法: mad/std/percentile
    winsorization_params JSON,                      -- 去极值参数: {"n": 3}
    neutralization_factors JSON,                    -- 中性化因子: ["industry", "market_cap"]
    standardization_method VARCHAR(50),             -- 标准化方法: zscore/minmax/robust

    -- 绩效指标（沙箱验证后更新）
    ic_mean            FLOAT,
    ic_std             FLOAT,
    icir               FLOAT,
    sharpe_ratio       FLOAT,
    max_drawdown       FLOAT,
    turnover_rate      FLOAT,

    -- 相关性分析
    correlation_matrix JSON,                        -- 与其他因子的相关性

    -- 状态管理
    status             VARCHAR(20) NOT NULL,        -- draft/implemented/sandbox/production/archived
    version            VARCHAR(20) NOT NULL,        -- v1.0, v1.1, v2.0
    parent_factor_id   VARCHAR(50),                 -- 父因子ID（用于版本演进）

    -- 权责信息
    owner              VARCHAR(100) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    last_validated_at  TIMESTAMP,

    -- 审批信息
    approved_by        VARCHAR(100),
    approved_at        TIMESTAMP,
    approval_notes     TEXT
);
```

### 6.2 因子版本管理

```sql
-- factor_versions 表（记录每次变更）
CREATE TABLE factor_versions (
    version_id         VARCHAR(50) PRIMARY KEY,
    factor_id          VARCHAR(50) NOT NULL,
    version            VARCHAR(20) NOT NULL,

    -- 变更内容
    change_type        VARCHAR(20) NOT NULL,        -- created/modified/parameter_changed/deprecated
    change_description TEXT,
    changes_diff       JSON,                        -- 具体变更内容

    -- 代码快照
    code_snapshot      TEXT,                        -- 代码内容
    code_hash          VARCHAR(64),                 -- Git commit hash

    -- 配置快照
    config_snapshot    JSON,                        -- 完整配置快照

    -- 元数据
    created_by         VARCHAR(100) NOT NULL,
    created_at         TIMESTAMP NOT NULL,

    FOREIGN KEY (factor_id) REFERENCES factor_registry(factor_id)
);
```

### 6.3 因子血缘关系

```sql
-- factor_lineage 表（数据血缘）
CREATE TABLE factor_lineage (
    lineage_id         VARCHAR(50) PRIMARY KEY,
    factor_id          VARCHAR(50) NOT NULL,
    dependency_type    VARCHAR(20) NOT NULL,        -- data_source/factor/feature
    dependency_id      VARCHAR(100) NOT NULL,       -- 数据源ID或因子ID

    -- 依赖详情
    dependency_path    JSON,                        -- 依赖路径树

    -- 元数据
    created_at         TIMESTAMP NOT NULL,

    FOREIGN KEY (factor_id) REFERENCES factor_registry(factor_id)
);
```

---

## 七、完整的数据目录结构

```
data_root/
│
├── meta/                           # 元数据库（SQLite）
│   └── meta.sqlite                 # 包含所有注册表
│       ├── factor_registry
│       ├── factor_versions
│       ├── factor_lineage
│       ├── feature_registry
│       └── ...
│
├── raw/                            # 基础数据域
│   ├── market/
│   │   ├── stock_daily/{year}.parquet
│   │   ├── etf_daily/{year}.parquet
│   │   └── adj_factor/{year}.parquet
│   └── reference/
│       └── securities.sqlite
│
├── features/                       # 特征数据域
│   ├── technical/
│   │   ├── price/
│   │   │   ├── rsi_{version}/{year}.parquet
│   │   │   ├── macd_{version}/{year}.parquet
│   │   │   └── bollinger_bands_{version}/{year}.parquet
│   │   └── volume/
│   │       ├── obv_{version}/{year}.parquet
│   │       └── money_flow_{version}/{year}.parquet
│   └── fundamental/
│       └── valuation/
│           ├── pe_ratio_{version}/{year}.parquet
│           └── pb_ratio_{version}/{year}.parquet
│
└── factors/                        # 因子数据域
    ├── narrow/                     # 窄表（主存储）
    │   └── {year}.parquet
    │       # Schema: (sid, trade_date, factor_id, exposure, version)
    │
    ├── wide/                       # 宽表（辅助存储）
    │   ├── style/
    │   │   ├── value_v1.0/{year}.parquet
    │   │   ├── momentum_v1.0/{year}.parquet
    │   │   └── quality_v1.0/{year}.parquet
    │   └── industry/
    │       └── industry_neutral_v1.0/{year}.parquet
    │
    └── snapshots/                  # 快照（用于回测）
        └── backtest_v1.0/
            └── {date}.parquet      # 特定日期的所有因子快照
```

---

## 八、表达式引擎设计

### 8.1 表达式引擎架构

```python
class ExpressionEngine:
    """因子/特征表达式引擎"""

    def __init__(self):
        self.operators = {
            # 时间序列算子
            'ts_mean': self.ts_mean,
            'ts_sum': self.ts_sum,
            'ts_delta': self.ts_delta,
            'ts_rank': self.ts_rank,
            'ts_std': self.ts_std,
            'ts_max': self.ts_max,
            'ts_min': self.ts_min,

            # 横截面算子
            'rank': self.rank,
            'zscore': self.zscore,
            'group_rank': self.group_rank,

            # 逻辑算子
            'sign': self.sign,
            'abs': self.abs,
            'log': self.log,
            'power': self.power,

            # 高级算子
            'correlation': self.correlation,
            'decay_linear': self.decay_linear,
        }

    def evaluate(self, expression: str, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        """解析并计算表达式"""
        # 1. 词法分析
        tokens = self._tokenize(expression)

        # 2. 语法分析（构建 AST）
        ast = self._parse(tokens)

        # 3. 执行计算
        result = self._execute(ast, data)

        return result

    # ============ 时间序列算子 ============
    def ts_mean(self, data: pl.Series, window: int) -> pl.Series:
        """时间序列移动平均"""
        return data.shift(1).rolling_mean(window_size=window)

    def ts_delta(self, data: pl.Series, periods: int) -> pl.Series:
        """时间序列差分"""
        return data.shift(1).diff(periods)

    def ts_rank(self, data: pl.Series, window: int) -> pl.Series:
        """时间序列滚动排名（在窗口内排名）"""
        def rank_in_window(s):
            return (s.rank(pct=True) - 0.5) * 2

        return data.rolling_map(window_size=window, function=rank_in_window)

    # ============ 横截面算子 ============
    def rank(self, data: pl.Series) -> pl.Series:
        """横截面排序（每个时间点上，对所有股票排序）"""
        return data.rank(pct=True) * 2 - 1  # 归一化到 [-1, 1]

    def zscore(self, data: pl.Series) -> pl.Series:
        """横截面标准化"""
        mean = data.mean()
        std = data.std()
        return (data - mean) / std

    def group_rank(self, data: pl.Series, group: pl.Series) -> pl.Series:
        """分组内排序"""
        return data.groupby(group).rank(pct=True) * 2 - 1
```

### 8.2 使用示例

```python
# 初始化引擎
engine = ExpressionEngine()

# 加载数据
data = {
    'close': load_close_prices(),
    'volume': load_volume(),
    'industry': load_industry()
}

# 计算特征
momentum = engine.evaluate(
    expression="ts_delta(close, 5) / ts_mean(close, 120)",
    data=data
)

volume_rank = engine.evaluate(
    expression="rank(volume)",
    data=data
)

# 组合表达式
complex_factor = engine.evaluate(
    expression="correlation(ts_rank(close, 5), ts_rank(volume, 5), 10)",
    data=data
)
```

---

## 九、实时与批量数据架构

### 9.1 Lambda 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         数据源层                                    │
│   Tushare API / AkShare / 实时行情接口 / 新闻API                      │
└─────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│      批处理层               │  │      流处理层                 │
│   (Batch Layer)              │  │   (Speed Layer)                  │
│                              │  │                                  │
│  - 日终批量计算因子            │  │  - 实时计算监控指标               │
│  - 全历史数据回测              │  │  - 盘中风险预警                   │
│  - 特征工程                   │  │  - 实时信号推送                   │
│  - 存储到数据仓库              │  │  - 增量更新实时视图               │
│                              │  │                                  │
│  引擎：Prefect/Dask          │  │  引擎：Faust/asyncio             │
└──────────────────────────────┘  └──────────────────────────────────┘
                    │                       │
                    ▼                       ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│    批量数据存储               │  │    实时数据存储                  │
│  Parquet（年分区）            │  │  Redis/SQLite（热数据）           │
│  SQLite（元数据）             │  │  时序数据库（可选）                │
└──────────────────────────────┘  └──────────────────────────────────┘
                    │                       │
                    └───────────┬───────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         服务层                        │
│   - 统一 API：同时支持批量查询和实时查询                              │
│   - 自动路由：根据查询时间范围选择存储层                              │
│   - 数据合并：批量和实时数据无缝拼接                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 针对你的策略的建议

**对于 ETF 行业轮动策略**：

```
主流程：批量处理（收盘后）
├─ 数据摄入：收盘后 T+1 获取完整日线数据
├─ 因子计算：批量计算所有因子
├─ 信号生成：生成调仓信号
└─ 执行决策：次日开盘执行

可选增强：实时监控（盘中）
├─ 波动率监控：实时计算 VIX 指数恐慌水平
├─ 极端行情：检测市场暴跌（>3% 单日跌幅）
└─ 风险控制：触发止损或降低仓位
```

**核心结论**：你的 ETF 行业轮动策略**不需要实时计算因子**，批量处理完全满足需求。实时计算仅用于可选的风险监控。

---

## 十、实施路线图

### 10.1 分阶段实施

**阶段 1：当前阶段（批量处理为主）**

```yaml
# 只实现批量处理
features:
  - 批量数据摄入
  - 批量因子计算
  - 日线信号生成
  - 历史回测

resources:
  - 单机部署
  - SQLite + Parquet 存储
  - Prefect 定时任务

不需要:
  - 实时数据流
  - 流处理引擎
  - 复杂的实时监控
```

**阶段 2：增强阶段（可选的实时监控）**

```yaml
# 增加轻量级实时监控
features:
  - 盘中波动率监控
  - 极端行情警报
  - 组合风险实时追踪

resources:
  - Redis 缓存
  - 简单的异步任务
  - 警报通知（Telegram/钉钉）

不需要:
  - 复杂的流式计算
  - 高频交易支持
```

### 10.2 优先级任务清单

| 优先级 | 任务 | 说明 |
|--------|------|------|
| **P0** | 完善 source 字段支持 | 所有多数据源数据集的键列包含 source |
| **P0** | 实现域内分层 | raw/feature/factor 逻辑分离 |
| **P1** | 因子元数据管理 | factor_registry, factor_versions, factor_lineage |
| **P1** | 窄表存储实现 | factors/narrow/{year}.parquet |
| **P2** | 表达式引擎 | 支持常见算子的解析和计算 |
| **P2** | 宽表生成 | 从窄表定期透视到宽表 |
| **P3** | 实时监控（可选） | 波动率、极端行情监控 |

---

## 十一、关键设计决策总结

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **DataHub 拆分** | 逻辑分域，物理统一 | 降低复杂度，保持统一入口 |
| **source 字段** | 多数据源数据必需，单数据源可选 | 支持质量校验和补充数据 |
| **因子存储格式** | 窄表为主，宽表为辅 | 灵活性 vs 性能的平衡 |
| **版本管理** | 因子定义 + 数据双版本锁 | 确保可复现性 |
| **元数据存储** | SQLite（meta.sqlite） | 轻量级、事务支持、易于管理 |
| **实时计算** | 日线策略不需要，可选风险监控 | 按需扩展 |
| **表达式引擎** | 支持 WorldQuant 风格算子 | 研究友好、灵活性高 |

---

## 十二、参考资料

### 12.1 业界最佳实践调研

1. **WorldQuant 101 Alphas** - 表达式引擎设计
2. **Quantopian/Alphalens** - 因子分析框架
3. **DolphinDB** - 高频因子计算实践
4. **AWS 实时量化交易** - Lambda 架构应用
5. **Feature Store 设计模式** - 元数据管理

### 12.2 相关文档

- [02_data_design.md](./02_data_design.md) - 数据层设计文档
- [2026-01-23-dataset-field-mapping.md](../plans/2026-01-23-dataset-field-mapping.md) - 数据集字段映射
- [2026-01-23-datahub-storage-structure-analysis.md](../plans/2026-01-23-datahub-storage-structure-analysis.md) - 存储结构分析

---

## 附录：完整数据集分类

### A.1 Raw Market Data（当前数据集）

| 类别 | 数据集 | 存储类型 | source 策略 |
|------|--------|---------|------------|
| **Market Data** | `stock_daily`, `etf_daily` | Parquet | 必需 `(sid, trade_date, source)` |
| **Corporate Actions** | `adj_factor` | Parquet | 必需 `(sid, trade_date, source)` |
| **Reference** | `securities`, `calendar` | SQLite | mapping 表方式 |
| **Status** | `stock_status` | Parquet | 可选（单一权威源） |
| **Universe** | `universe_constituent`, `index_weight` | SQLite | 必需 `(id, sid, effective_from, source)` |

### A.2 Feature Data（新增）

| 类别 | 特征示例 | 存储路径 |
|------|---------|---------|
| **Price Features** | RSI, MACD, 布林带 | `features/technical/price/{feature_id}/{year}.parquet` |
| **Volume Features** | 量比, 换手率, 资金流 | `features/technical/volume/{feature_id}/{year}.parquet` |
| **Fundamental Features** | PE, PB, ROE, 营收增长 | `features/fundamental/{category}/{feature_id}/{year}.parquet` |

### A.3 Factor Data（新增）

| 类别 | 因子示例 | 存储路径 |
|------|---------|---------|
| **Style Factors** | 价值、动量、质量、波动率 | `factors/style/{factor_id}/{year}.parquet` |
| **Industry Factors** | 行业分类、行业中性化 | `factors/industry/{factor_id}/{year}.parquet` |
| **Risk Factors** | 规模、流动性 | `factors/risk/{factor_id}/{year}.parquet` |

---

## 十三、因子存储分区策略详解

### 13.1 为什么不能把所有因子写在一个 Parquet 里

基于业界最佳实践（DolphinDB、Feature Store）和 Parquet 性能特性，**禁止将所有因子存储在单个文件中**的原因：

| 问题 | 原因 | 后果 |
|------|------|------|
| **文件过大** | 几百个因子 × 几千个标的 × 250交易日 = 数十亿行 | 查询必须扫描全表，无法利用分区剪裁 |
| **写入冲突** | 所有因子计算任务竞争同一个文件锁 | 高并发写入失败，性能瓶颈 |
| **版本管理困难** | 单个因子版本变更需要重写整个文件 | I/O 开销巨大，无法增量更新 |
| **查询性能差** | 无法利用 Parquet 的列剪裁优化 | 读取单个因子也需要加载全量数据 |
| **无法独立演进** | 因子无法独立生命周期管理 | 归档、退役因子影响整体 |

### 13.2 推荐的分区策略

#### 13.2.1 窄表分区设计（主存储）

```
factors/narrow/
├── style/                          # 风格因子
│   ├── value/{year}.parquet        # 价值因子（所有版本）
│   ├── momentum/{year}.parquet     # 动量因子
│   ├── quality/{year}.parquet      # 质量因子
│   └── volatility/{year}.parquet   # 波动率因子
├── industry/                       # 行业因子
│   └── industry_neutral/{year}.parquet
└── risk/                           # 风险因子
    ├── size/{year}.parquet         # 规模因子
    └── liquidity/{year}.parquet    # 流动性因子
```

**Schema（每个文件）**:
```python
schema = {
    'sid': pl.Int32,                # 标的 ID
    'trade_date': pl.Date,          # 交易日期
    'factor_id': pl.String,         # 因子标识（如 "value_pe_pb"）
    'version': pl.String,           # 版本号（如 "v1.0"）
    'exposure': pl.Float64,         # 因子暴露度
    'metadata': pl.String           # JSON 元数据（可选）
}
```

**分区键**: `factor_category / factor_id / year`

**查询优化示例**:
```python
# ✅ 高效查询：利用分区剪裁
df = pl.read_parquet(
    'factors/narrow/style/value/2024.parquet',
    filters=[
        (pl.col('version') == 'v1.0'),
        (pl.col('trade_date') >= date(2024, 1, 1))
    ]
)

# ❌ 低效查询：扫描所有文件
# df = pl.read_parquet('factors/narrow/**/*.parquet')
```

#### 13.2.2 宽表分区设计（辅助存储）

```
factors/wide/
├── style/
│   ├── value_v1.0/
│   │   ├── 2024.parquet           # 2024年价值因子宽表
│   │   └── 2025.parquet
│   └── momentum_v1.0/
│       └── 2024.parquet
└── snapshots/                     # 回测快照
    └── backtest_20240101/         # 特定日期所有因子
        └── all_factors.parquet
```

**Schema（宽表）**:
```python
schema = {
    'sid': pl.Int32,
    'trade_date': pl.Date,
    'value_factor': pl.Float64,     # 每个因子一列
    'momentum_factor': pl.Float64,
    'quality_factor': pl.Float64,
    # ...
}
```

### 13.3 分区策略对比

| 维度 | 窄表分区 | 宽表分区 |
|------|---------|---------|
| **文件数量** | 按因子类型分区（10-50个文件） | 按因子版本分区（100+个文件） |
| **单文件大小** | 中等（100MB-1GB） | 小（10-100MB） |
| **写入性能** | 高（追加写入） | 中（需要重写） |
| **查询性能** | 中（需要 JOIN） | 高（直接列读取） |
| **版本管理** | 简单（version 列） | 需要新目录 |
| **使用场景** | 研究阶段、频繁变更 | 生产环境、ML 训练 |

### 13.4 Parquet 分区最佳实践

基于业界调研（Parquet Performance Best Practices）：

```python
# 推荐的分区策略
partition_strategy = {
    '第一级': 'factor_category',   # style/industry/risk
    '第二级': 'factor_id',         # value/momentum/quality
    '第三级': 'year',              # 2024/2025/2026
    '第四级（可选）': 'month'      # 仅高频因子需要
}

# 分区大小目标
target_partition_size = {
    '最小': '256 MB',              # HDFS 块大小
    '推荐': '512 MB - 1 GB',       # 平衡扫描和并行度
    '最大': '2 GB'                 # 避免内存压力
}

# 行组大小（Row Group Size）
row_group_size = {
    '推荐': '64 MB - 128 MB',      # Parquet 默认
    '原因': '允许谓词下推和列剪裁'
}
```

---

## 十四、特征元数据管理

### 14.1 特征注册表

与因子类似，特征也需要元数据管理，但更简单：

```sql
-- feature_registry 表结构
CREATE TABLE feature_registry (
    -- 基础信息
    feature_id         VARCHAR(50) PRIMARY KEY,     -- 如 "rsi_14", "macd_standard"
    feature_name       VARCHAR(100) NOT NULL,       -- 显示名称
    feature_category   VARCHAR(50) NOT NULL,        -- technical/fundamental/alternative
    feature_subcategory VARCHAR(50),                -- price/volume/momentum/valuation

    -- 方法定义
    description        TEXT,                        -- 特征描述
    formula            TEXT,                        -- 计算公式或表达式
    implementation_code TEXT,                       -- 代码路径

    -- 参数配置
    parameters         JSON,                        -- {"period": 14, "method": "sma"}

    -- 数据依赖
    data_sources       JSON,                        -- ["close", "volume"]

    -- 统计信息（自动计算后更新）
    mean               FLOAT,
    std                FLOAT,
    min                FLOAT,
    max                FLOAT,
    null_ratio         FLOAT,                       -- 缺失值比例

    -- 质量指标
    outlier_ratio      FLOAT,                       -- 异常值比例
    stability_score    FLOAT,                       -- 稳定性得分（0-1）

    -- 状态管理
    status             VARCHAR(20) NOT NULL,        -- draft/active/deprecated
    version            VARCHAR(20) NOT NULL,

    -- 元数据
    owner              VARCHAR(100) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL
);
```

### 14.2 特征血缘关系

```sql
-- feature_lineage 表（数据血缘）
CREATE TABLE feature_lineage (
    lineage_id         VARCHAR(50) PRIMARY KEY,
    feature_id         VARCHAR(50) NOT NULL,
    dependency_type    VARCHAR(20) NOT NULL,        -- data_source/feature
    dependency_id      VARCHAR(100) NOT NULL,

    -- 依赖详情
    dependency_path    JSON,                        -- 依赖路径树

    created_at         TIMESTAMP NOT NULL,

    FOREIGN KEY (feature_id) REFERENCES feature_registry(feature_id)
);
```

### 14.3 因子 vs 特征元数据对比

| 元数据字段 | 特征 | 因子 |
|-----------|------|------|
| **经济学假设** | 无 | 必需 |
| **后处理方法** | 无 | 去极值/标准化/中性化 |
| **绩效指标** | 无 | IC/ICIR/夏普/换手率 |
| **相关性分析** | 可选 | 必需 |
| **审批流程** | 简单 | 严格 |
| **状态** | draft/active/deprecated | draft/implemented/sandbox/production/archived |

---

## 十五、完整 ETL Pipeline 流程

### 15.1 数据流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         外部数据源                                  │
│     Tushare / AkShare / 通达信 / 财报API / 新闻API                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Data Ingestion Layer                             │
│   - Prefect 定时调度                                              │
│   - API 调用、限流（tenacity）、重试                                │
│   - 增量检测（游标管理）                                            │
│   - 数据质量检查（DQ Engine L1: 技术校验）                           │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Raw Data Storage (基础数据)                       │
│   Parquet: stock_daily, etf_daily, adj_factor                      │
│   SQLite: securities, calendar, universe                            │
│   键列: (sid, trade_date, source)                                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│    Feature Engine            │  │    Factor Engine                 │
│   (特征计算引擎)               │  │   (因子计算引擎)                  │
│                              │  │                                  │
│  Input: Raw Data             │  │  Input: Features + Raw Data     │
│  Output: Features            │  │  Output: Factors                 │
│                              │  │                                  │
│  - Expression Engine         │  │  - Expression Engine             │
│  - UDF Library               │  │  - Standardization Pipeline      │
│  - Incremental Compute       │  │  - Neutralization                │
└──────────────────────────────┘  └──────────────────────────────────┘
                    │                       │
                    ▼                       ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│    Feature Storage           │  │    Factor Storage                │
│   features/technical/         │  │   factors/narrow/                │
│   features/fundamental/       │  │   factors/wide/                  │
│                              │  │                                  │
│  Schema:                     │  │  Schema:                         │
│  (sid, trade_date,           │  │  (sid, trade_date,               │
│   feature_id, value)          │  │   factor_id, exposure, version)  │
└──────────────────────────────┘  └──────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Strategy Engine                                  │
│   - 因子组合                                                        │
│   - 信号生成                                                        │
│   - 组合优化                                                        │
│   - 回测模拟                                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 15.2 阶段 1：数据摄入（已有实现）

```python
from prefect import flow, task
from ditto_datahub.sources import TushareSource
from ditto_datahub.domains.raw.market.bars_store import BarsStore
from ditto_observability.dq import DQEngine

@flow(name="daily_data_ingestion")
async def ingest_daily_data(trade_date: date):
    """每日数据摄入流程"""

    # 1. 获取行情数据
    source = TushareSource()
    bars = await source.daily(trade_date=trade_date)

    # 2. 数据质量检查（L1: 技术校验）
    dq_engine = DQEngine()
    issues = dq_engine.check(
        bars,
        rules=[
            "no_nulls",              # 无空值
            "positive_volume",        # 成交量 > 0
            "valid_price",            # 价格合理性
            "no_duplicates"           # 无重复记录
        ]
    )

    # 3. 处理质量问题
    if issues.has_failures:
        # 进入隔离区
        quarantine_store.save(bars, issues)
        raise DataQualityError(f"数据质量检查失败: {issues.summary}")
    else:
        # 通过则存储
        bars_store = BarsStore()
        await bars_store.write(bars, source="tushare")
        logger.info(f"成功摄入 {len(bars)} 条行情数据")
```

### 15.3 阶段 2：特征计算（新增）

```python
from ditto_datahub.domains.feature.technical import FeatureEngine
from ditto_datahub.meta.feature_registry import FeatureRegistry

@flow(name="daily_feature_computation")
async def compute_features(trade_date: date):
    """每日特征计算流程"""

    # 1. 加载原始数据
    bars_store = BarsStore()
    bars = await bars_store.get(trade_date=trade_date)

    # 2. 获取活跃特征列表
    registry = FeatureRegistry()
    active_features = registry.get_active_features()

    # 3. 表达式引擎计算
    feature_engine = FeatureEngine()

    for feature_def in active_features:
        try:
            # 解析并计算特征
            feature_df = await feature_engine.evaluate(
                expression=feature_def['formula'],
                data=bars,
                context={
                    "trade_date": trade_date,
                    "parameters": feature_def['parameters']
                }
            )

            # 存储特征
            await feature_store.write(
                feature_id=feature_def['feature_id'],
                data=feature_df,
                version=feature_def['version']
            )

            logger.info(f"特征 {feature_def['feature_id']} 计算完成")

        except Exception as e:
            logger.error(f"特征 {feature_def['feature_id']} 计算失败: {e}")
            continue
```

### 15.4 阶段 3：因子计算（新增）

```python
from ditto_datahub.domains.factor.style import FactorEngine
from ditto_datahub.meta.factor_registry import FactorRegistry

@flow(name="daily_factor_computation")
async def compute_factors(trade_date: date):
    """每日因子计算流程"""

    # 1. 加载特征和原始数据
    feature_store = FeatureStore()
    features = await feature_store.get(trade_date=trade_date)

    raw_data = await bars_store.get(trade_date=trade_date)

    # 2. 获取活跃因子列表
    registry = FactorRegistry()
    active_factors = registry.get_active_factors()

    # 3. 因子计算引擎
    factor_engine = FactorEngine()

    for factor_def in active_factors:
        try:
            # 计算原始因子
            raw_factor = await factor_engine.compute_raw(
                factor_def=factor_def,
                features=features,
                raw_data=raw_data
            )

            # 后处理流程
            processed_factor = await factor_engine.post_process(
                raw_factor=raw_factor,
                methods=factor_def['post_processing']  # 去极值/标准化/中性化
            )

            # 存储因子（窄表）
            await factor_store.write_narrow(
                factor_id=factor_def['factor_id'],
                data=processed_factor,
                version=factor_def['version'],
                trade_date=trade_date
            )

            logger.info(f"因子 {factor_def['factor_id']} 计算完成")

        except Exception as e:
            logger.error(f"因子 {factor_def['factor_id']} 计算失败: {e}")
            continue

    # 4. 定期生成宽表（每周/每月）
    if is_widetable_generation_day(trade_date):
        await factor_store.generate_wide_table(trade_date)
```

### 15.5 因子后处理流程详解

```python
class FactorPostProcessor:
    """因子后处理：去极值 → 标准化 → 中性化"""

    async def process(
        self,
        raw_factor: pl.DataFrame,
        config: dict
    ) -> pl.DataFrame:
        """
        完整的后处理流程

        Args:
            raw_factor: 原始因子值，包含 (sid, trade_date, raw_value)
            config: 后处理配置
                {
                    "winsorization": {"method": "mad", "n": 3},
                    "standardization": {"method": "zscore"},
                    "neutralization": {"factors": ["industry", "market_cap"]}
                }
        """

        # 1. 去极值（Winsorization）
        if config.get('winsorization'):
            factor = self.winsorize(
                raw_factor,
                method=config['winsorization']['method'],
                **config['winsorization'].get('params', {})
            )
        else:
            factor = raw_factor

        # 2. 标准化（Standardization）
        if config.get('standardization'):
            factor = self.standardize(
                factor,
                method=config['standardization']['method']
            )

        # 3. 行业中性化（Neutralization）
        if config.get('neutralization'):
            factor = self.neutralize(
                factor,
                risk_factors=config['neutralization']['factors'],
                trade_date=factor['trade_date'][0]
            )

        return factor

    def winsorize(
        self,
        data: pl.DataFrame,
        method: str = 'mad',
        n: int = 3
    ) -> pl.DataFrame:
        """去极值"""

        if method == 'mad':
            # MAD（中位数绝对偏差）方法
            median = data['value'].median()
            mad = (data['value'] - median).abs().median()
            upper = median + n * mad
            lower = median - n * mad

        elif method == 'std':
            # 标准差方法（3σ）
            mean = data['value'].mean()
            std = data['value'].std()
            upper = mean + n * std
            lower = mean - n * std

        elif method == 'percentile':
            # 百分位方法
            lower = data['value'].quantile(n / 100)
            upper = data['value'].quantile(1 - n / 100)

        return data.with_columns(
            pl.col('value').clip(lower, upper)
        )

    def standardize(
        self,
        data: pl.DataFrame,
        method: str = 'zscore'
    ) -> pl.DataFrame:
        """标准化"""

        if method == 'zscore':
            # Z-score 标准化
            mean = data['value'].mean()
            std = data['value'].std()
            return data.with_columns(
                (pl.col('value') - mean) / std
            )

        elif method == 'minmax':
            # Min-Max 标准化
            min_val = data['value'].min()
            max_val = data['value'].max()
            return data.with_columns(
                (pl.col('value') - min_val) / (max_val - min_val)
            )

        elif method == 'robust':
            # 鲁棒标准化（基于中位数和四分位距）
            median = data['value'].median()
            q1 = data['value'].quantile(0.25)
            q3 = data['value'].quantile(0.75)
            iqr = q3 - q1
            return data.with_columns(
                (pl.col('value') - median) / iqr
            )

    def neutralize(
        self,
        data: pl.DataFrame,
        risk_factors: list[str],
        trade_date: date
    ) -> pl.DataFrame:
        """风险因子中性化（行业中性化/市值中性化）"""

        # 1. 构建风险因子矩阵
        X = self._build_risk_factor_matrix(
            sids=data['sid'].to_list(),
            risk_factors=risk_factors,
            trade_date=trade_date
        )

        # 2. 线性回归取残差
        from sklearn.linear_model import LinearRegression

        model = LinearRegression(fit_intercept=False)
        model.fit(X, data['value'].to_numpy())
        predicted = model.predict(X)

        # 3. 残差即中性化后的因子
        neutralized = data.with_columns(
            (pl.col('value') - predicted).alias('value')
        )

        return neutralized
```

### 15.6 每日 ETL 调度示例

```python
from prefect import flow
from prefect.task_runners import ConcurrentTaskRunner

@flow(name="daily_etl_pipeline", task_runner=ConcurrentTaskRunner())
async def daily_etl_pipeline(trade_date: date):
    """完整的每日 ETL 流程"""

    # 阶段 1：数据摄入（串行，确保数据完整性）
    await ingest_daily_data(trade_date)

    # 阶段 2 & 3：特征和因子计算（并行）
    await asyncio.gather(
        compute_features(trade_date),
        compute_factors(trade_date)
    )

    # 阶段 4：验证因子质量
    await validate_factors(trade_date)

    logger.info(f"ETL 流程完成: {trade_date}")

# Prefect 调度配置
from prefect.deployments import Deployment

Deployment.build_from_flow(
    flow=daily_etl_pipeline,
    name="daily-etl-prod",
    schedule=CronSchedule(cron="0 18 * * 1-5"),  # 每个工作日 18:00 执行
    parameters={"trade_date": "{{ date }}"}
)
```

---

## 十六、关键设计决策更新

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **DataHub 拆分** | 逻辑分域，物理统一 | 降低复杂度，保持统一入口 |
| **source 字段** | 多数据源数据必需，单数据源可选 | 支持质量校验和补充数据 |
| **因子存储格式** | **窄表分区为主，宽表为辅** | 灵活性 vs 性能的平衡，禁止单文件 |
| **因子分区策略** | **按 factor_category/factor_id/year 分区** | 支持分区剪裁，避免文件过大 |
| **版本管理** | 因子定义 + 数据双版本锁 | 确保可复现性 |
| **元数据存储** | SQLite（meta.sqlite） | 轻量级、事务支持、易于管理 |
| **特征元数据** | **独立的 feature_registry** | 与因子区分，简化管理 |
| **实时计算** | 日线策略不需要，可选风险监控 | 按需扩展 |
| **表达式引擎** | 支持 WorldQuant 风格算子 | 研究友好、灵活性高 |
| **ETL 流程** | **摄入 → 特征 → 因子 → 验证** | 清晰的数据血缘，易于调试 |

---

## 十七、参考资料更新

### 17.1 业界最佳实践调研

1. **WorldQuant 101 Alphas** - 表达式引擎设计
2. **Quantopian/Alphalens** - 因子分析框架
3. **DolphinDB** - 高频因子计算实践、窄表 vs 宽表
4. **AWS Feature Store** - 元数据管理、因子生命周期
5. **量化投顾高性能因子中间库设计与实践** - 完整的 Feature Store 架构
6. **Parquet Performance Best Practices** - 分区策略、文件大小优化
7. **Schema Registry Patterns** - 元数据版本管理

### 17.2 相关文档

- [02_data_design.md](./02_data_design.md) - 数据层设计文档
- [2026-01-23-dataset-field-mapping.md](../plans/2026-01-23-dataset-field-mapping.md) - 数据集字段映射
- [2026-01-23-datahub-storage-structure-analysis.md](../plans/2026-01-23-datahub-storage-structure-analysis.md) - 存储结构分析

---

## 十八、增强的数据质量验证架构（黄金数据集验证规范）

> **基于**: 《Ditto 黄金数据集验证规范 v1.2》
> **目的**: 设计工业级的数据质量保证体系，整合到现有 DataHub 架构中

### 18.1 架构概述

```
┌─────────────────────────────────────────────────────────────────────┐
│                    数据质量验证架构分层                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Port 层（应用层）                                            │   │
│  │                                                             │   │
│  │  ┌───────────────────────────────────────────────────────┐  │   │
│  │  │  QualityReconciliationService (质量对账服务)            │  │   │
│  │  │                                                         │  │   │
│  │  │  - 跨源对账协调                                         │  │   │
│  │  │  - 业务级质量报告                                       │  │   │
│  │  │  - 告警通知                                             │  │   │
│  │  │  - 质量趋势分析                                         │  │   │
│  │  └───────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                  │                                  │
│                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  DataHub 层（数据层）                                        │   │
│  │                                                             │   │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  │   │
│  │  │ Primary      │  │ Comparison       │  │ Golden       │  │   │
│  │  │ Source       │  │ Source           │  │ Dataset      │  │   │
│  │  │ (Tushare)    │  │ (TDX)            │  │ Freezer      │  │   │
│  │  │              │  │                  │  │              │  │   │
│  │  │ - 数据摄入    │  │ - 隔离区存储      │  │ - 版本冻结   │  │   │
│  │  │ - L1 质量检查 │  │ - 差异记录        │  │ - 指纹计算   │  │   │
│  │  │ - 落地主存储  │  │ - 30天自动清理    │  │ - 幂等性保证 │  │   │
│  │  └──────────────┘  └──────────────────┘  └──────────────┘  │   │
│  │                                                             │   │
│  │  ┌───────────────────────────────────────────────────────┐  │   │
│  │  │  Quality Validation Engine (P0/P1/P2 分级)             │  │   │
│  │  │                                                         │  │   │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │  │   │
│  │  │  │ P0 Rules │  │ P1 Rules │  │ P2 Rules │             │  │   │
│  │  │  │          │  │          │  │          │             │  │   │
│  │  │  │ 阻断级   │  │ 记录级   │  │ 仅记录   │             │  │   │
│  │  │  └──────────┘  └──────────┘  └──────────┘             │  │   │
│  │  │                                                         │  │   │
│  │  │  ┌─────────────────────────────────────────────────┐  │  │   │
│  │  │  │  Cross-Source Comparator (向量化比对引擎)         │  │  │   │
│  │  │  │  - Polars 向量化实现                              │  │  │   │
│  │  │  │  - 容差规则配置                                   │  │  │   │
│  │  │  │  - 差异样本记录                                   │  │  │   │
│  │  │  └─────────────────────────────────────────────────┘  │  │   │
│  │  └───────────────────────────────────────────────────────┘  │   │
│  │                                                             │   │
│  │  ┌───────────────────────────────────────────────────────┐  │   │
│  │  │  Metadata & Configuration                             │  │   │
│  │  │                                                         │  │   │
│  │  │  - InstrumentSpec (标的元数据)                        │  │   │
│  │  │  - LimitRuleTable (涨跌幅规则表)                       │  │   │
│  │  │  - UnitConverter (单位转换器)                          │  │   │
│  │  │  - ToleranceRules (容差规则)                           │  │   │
│  │  └───────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 18.2 P0/P1/P2 规则分级体系

#### P0 规则（阻断级）

任何一条失败都阻断发布：

| 规则名称 | 说明 | 实现要点 |
|---------|------|----------|
| **主键唯一性** | (sid, trade_date) 唯一且非空 | 检测重复和空值 |
| **OHLC 不变量** | low <= open/close <= high | 价格逻辑一致性 |
| **正值约束** | vol >= 0, adj_factor > 0 | 物理约束 |
| **VWAP 合理性** | low * 0.999 <= vwap <= high * 1.001 | 快速定位单位/错位问题 |
| **pre_close 连续性** | 非事件日 pre_close == lag(close) | 按tick_size对齐 |

#### P1 规则（需记录）

记录并告警，但不阻断：

| 规则名称 | 说明 | 实现要点 |
|---------|------|----------|
| **跨源价格对账** | Tushare vs TDX 价格对比 | 容差 0.1% |
| **涨跌停准确性** | up_limit/down_limit 计算正确性 | 使用 Decimal 避免浮点误差 |
| **pre_close 事件日** | 除权日跳变可被分红事件解释 | 与分红事件表关联 |

#### P2 规则（仅记录）

仅记录，不影响发布：

| 字段 | 模式 | 原因 | 处理 |
|------|------|------|------|
| amount | Tushare vs TDX 差异 | float32 精度问题 | 不对账此字段 |
| close | tick 舍入差异 <= 0.01 | 舍入方式差异 | 容差内忽略 |
| adj_factor | AkShare vs Tushare 差异 | 前复权基准日不同 | 仅用 Tushare 验证 |

### 18.3 目录结构设计

```
packages/
├── datahub/
│   └── src/ditto_datahub/
│       ├── sources/
│       │   ├── tushare/              # 主数据源
│       │   └── tdx/                 # 对账数据源（新增）
│       │       ├── source.py        # TDX 数据源
│       │       ├── reader.py        # 通达信 .day 文件读取器
│       │       └── quality.py       # 质量对比逻辑
│       │
│       ├── stores/
│       │   ├── quality/             # 质量隔离区（新增）
│       │   │   ├── comparison_store.py    # 差异记录存储
│       │   │   ├── metrics_store.py       # 质量指标存储
│       │   │   └── golden_dataset.py      # 黄金数据集冻结
│       │   └── ...
│       │
│       ├── quality/                 # 质量验证模块（新增）
│       │   ├── validators/          # 验证器
│       │   │   ├── p0_rules.py     # P0 阻断级规则
│       │   │   ├── p1_rules.py     # P1 记录级规则
│       │   │   └── p2_rules.py     # P2 仅记录规则
│       │   ├── comparator.py        # 向量化比对引擎
│       │   ├── config/              # 配置
│       │   │   ├── instrument_spec.py   # 标的元数据
│       │   │   ├── limit_rules.py       # 涨跌幅规则表
│       │   │   ├── tolerance_rules.py   # 容差规则
│       │   │   └── golden_instruments.py # 黄金数据集标的配置
│       │   └── unit_converter.py    # 单位转换器
│       │
│       └── runtime/
│           └── dq_rules.py          # 现有 DQ 规则（保留兼容）
│
└── port/
    └── src/ditto_port/
        └── services/                # 业务服务层
            └── quality/             # 质量对账服务（新增）
                ├── reconciliation.py  # 对账协调器
                ├── reporter.py        # 业务报告
                └── alerts.py          # 告警通知
```

### 18.4 核心组件设计

#### 18.4.1 标的元数据与涨跌幅规则表

```python
# 黄金数据集标的配置
GOLDEN_INSTRUMENTS: dict[str, InstrumentSpec] = {
    "510300.SH": InstrumentSpec(
        ts_code="510300.SH",
        name="沪深300ETF",
        market=Market.SH,
        board=Board.MAIN,
        asset_type=AssetType.ETF,
        tick_size=Decimal("0.001"),  # 上交所ETF是0.001
        lot_size=100,
        default_limit_ratio=Decimal("0.10"),
    ),
    # ... 其他标的配置
}

# 涨跌幅规则表
LIMIT_RULE_TABLE: dict[tuple, list[LimitRule]] = {
    ("main", False, None): [
        LimitRule(Decimal("0.10"), date(1996, 12, 16), None, "主板10%涨跌幅"),
    ],
    ("main", True, None): [
        LimitRule(Decimal("0.05"), date(1998, 4, 22), date(2025, 6, 26), "ST股票5%涨跌幅"),
    ],
    # ... 其他规则
}
```

#### 18.4.2 单位转换与规范化

```python
CANONICAL_UNITS = {
    # 价格类：元，保留到tick_size精度
    "open": "元", "high": "元", "low": "元", "close": "元",
    # 成交量：股（不是手）
    "vol": "股",
    # 成交额：元（不是千元）
    "amount": "元",
    # 比例类：小数（不是百分比）
    "pct_chg": "小数",
}

class UnitConverter:
    """数据源单位转换器"""

    @staticmethod
    def convert_tushare_to_canonical(df: pl.DataFrame) -> pl.DataFrame:
        """Tushare -> Canonical 单位转换"""
        return df.with_columns([
            (pl.col("vol") * 100).alias("vol"),      # 手 -> 股
            (pl.col("amount") * 1000).alias("amount"), # 千元 -> 元
            (pl.col("pct_chg") / 100).alias("pct_chg"), # 百分比 -> 小数
        ])
```

#### 18.4.3 向量化比对引擎

```python
class VectorizedComparator:
    """
    向量化比对器

    使用 Polars Expression 实现，比 Python 循环快 100 倍
    """

    def compare(
        self,
        df1: pl.DataFrame,
        df2: pl.DataFrame,
        key_cols: list[str],
        compare_cols: list[str],
    ) -> pl.DataFrame:
        """比对两个 DataFrame，返回差异记录"""
        # 向量化实现...
```

#### 18.4.4 黄金数据集冻结机制

```python
class GoldenDatasetFreezer:
    """黄金数据集冻结器"""

    def freeze(
        self,
        df: pl.DataFrame,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> FreezeMetadata:
        """
        冻结数据集

        保存:
        - 元数据 (JSON)
        - 数据指纹 (SHA256)
        - 统计摘要（不保存完整数据）
        """

    def verify(self, metadata: FreezeMetadata, current_df: pl.DataFrame) -> dict:
        """验证当前数据与冻结版本的一致性"""
```

### 18.5 关键设计决策（更新）

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **TDX 数据是否落地** | **落地到隔离区（30天清理）** | 质量趋势、异常样本、审计合规 |
| **验证规则分级** | **P0（阻断）/P1（记录）/P2（仅观察）** | 分层处理，平衡质量与可用性 |
| **对账功能位置** | **DataHub 对比 + Port 协调** | 清晰分层，DataHub 负责技术，Port 负责业务 |
| **TDX 是否走 DataHub** | **是，走隔离区** | 统一访问模式，避免 Port 直接依赖 |
| **单位转换策略** | **Canonical 强制归一** | 避免单位混淆，提高可维护性 |
| **比对引擎实现** | **Polars 向量化** | 性能优化，比循环快 100 倍 |
| **黄金数据集冻结** | **指纹存储 + 定期验证** | 幂等性保证，版本追溯 |

### 18.6 验证时间窗口规范

#### 全量验证窗口

```yaml
full_validation_window:
  start_date: "2020-01-01"
  end_date: "2024-12-31"
  trading_days: ~1215  # 约5年交易日
  rationale:
    - 覆盖完整牛熊周期
    - 覆盖多次分红周期
    - 覆盖疫情极端行情
```

#### 黄金数据集标的验证重点

| 标的 | 关键事件窗口 | 验证重点 |
|------|-------------|----------|
| **510300.SH** | 2020-03（疫情恐慌）、每年5-6月/11-12月（分红） | 复权因子、pre_close跳变 |
| **516010.SH** | 2021-07~08（游戏监管）、2023-12（版号政策） | 零成交、流动性枯竭 |
| **513100.SH** | 2020-03（美股熔断）、2022-03（中概暴跌） | 折溢价极端值、不与美股强对账 |
| **000300.SH** | 每年6月/12月（成分股调整） | 权重PIT正确性 |
| **000407.SZ** | ST加帽/摘帽日、停复牌日 | 涨跌停5%切换、停牌处理 |

### 18.7 跨境 ETF 特殊处理（513100）

```python
class CrossBorderETFValidator:
    """
    跨境 ETF 验证策略

    核心原则:
    - 不要用美股底层数据校验513100的走势（存在T+1错位和汇率影响）
    - 只验证 A股交易时段内的数据自身连续性和逻辑一致性
    """

    def validate_self_consistency(self, df: pl.DataFrame) -> dict:
        """自身一致性验证"""
        # 1. OHLC 不变量
        # 2. 价格连续性（跳变不应超过10%，极端行情除外）
        # 3. 成交量连续性（零成交需要确认是否停牌）
```

---

## 十九、参考资料更新（补充）

### 19.1 业界最佳实践调研（更新）

1. **WorldQuant 101 Alphas** - 表达式引擎设计
2. **Quantopian/Alphalens** - 因子分析框架
3. **DolphinDB** - 高频因子计算实践、窄表 vs 宽表
4. **AWS Feature Store** - 元数据管理、因子生命周期
5. **量化投顾高性能因子中间库设计与实践** - 完整的 Feature Store 架构
6. **Parquet Performance Best Practices** - 分区策略、文件大小优化
7. **Schema Registry Patterns** - 元数据版本管理
8. **Ditto 黄金数据集验证规范 v1.2** - 数据质量保证体系

### 19.2 相关文档（更新）

- [02_data_design.md](./02_data_design.md) - 数据层设计文档
- [2026-01-23-dataset-field-mapping.md](../plans/2026-01-23-dataset-field-mapping.md) - 数据集字段映射
- [2026-01-23-datahub-storage-structure-analysis.md](../plans/2026-01-23-datahub-storage-structure-analysis.md) - 存储结构分析
- **黄金数据集验证规范 v1.2** - 数据质量验证完整规范

### 19.3 实施路线图（最终更新）

| 阶段 | 任务 | 说明 | 优先级 |
|------|------|------|--------|
| **阶段 1** | 完善 source 字段支持 | 所有多数据源数据集的键列包含 source | P0 |
| **阶段 1** | 实现域内分层 | raw/feature/factor 逻辑分离 | P0 |
| **阶段 1** | P0 规则增强 | 主键、OHLC 不变量、VWAP 合理性 | P0 |
| **阶段 2** | 因子元数据管理 | factor_registry, factor_versions, factor_lineage | P1 |
| **阶段 2** | 窄表存储实现 | factors/narrow/{year}.parquet | P1 |
| **阶段 2** | 通达信对账模块 | TDX 数据源、隔离区存储、比对引擎 | P1 |
| **阶段 3** | 黄金数据集冻结 | 版本管理、指纹计算、幂等性验证 | P2 |
| **阶段 3** | 表达式引擎 | 支持常见算子的解析和计算 | P2 |
| **阶段 3** | 宽表生成 | 从窄表定期透视到宽表 | P2 |
| **阶段 4** | Port 层协调服务 | 质量对账服务、告警通知 | P3 |

---

**文档版本**: v1.1 (增强质量验证架构)
**最后更新**: 2026-01-24
**主要变更**:
- 新增第十八章：增强的数据质量验证架构（黄金数据集验证规范）
- 整合 P0/P1/P2 规则分级体系
- 新增多源对账模块设计
- 新增黄金数据集冻结机制
- 更新实施路线图
