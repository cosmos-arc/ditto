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
