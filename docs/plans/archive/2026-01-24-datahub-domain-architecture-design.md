# DataHub 域架构设计方案

> 创建日期: 2026-01-24
> 版本: v2.0
> 状态: 设计草案

> **目的**: 基于 Market/Metadata/Features/Factors 四域划分，设计清晰的数据访问架构，去除 Accessor 层，采用 QueryService 模式，禁止同层依赖，统一在应用层做 identity 解析。

---

## 一、设计背景

### 1.1 现有架构问题

| 问题 | 说明 | 影响 |
|------|------|------|
| **Accessor 层冗余** | Store → Accessor → Port 三层，职责重叠 | 维护成本高 |
| **子层级 Service 过多** | 每个子域都有独立的 Service | 层次过深，理解困难 |
| **共享能力分散** | Identity、复权等能力在各处重复实现 | 代码重复，不一致 |
| **依赖关系混乱** | 跨层级依赖，同层协作不明确 | 难以追踪调用链 |

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **域级唯一入口** | 每个域只有一个 QueryService |
| **子域能力模块化** | 子域提供能力模块，与 Store 同级 |
| **Store 纯数据访问** | Store 只负责数据读写 |
| **禁止同层依赖** | 域级服务之间禁止相互调用，保持完全独立 |
| **应用层编排** | Identity 解析、跨域编排统一在应用层（Port 层）完成 |
| **能力复用** | 子域能力模块可被多个服务调用 |

---

## 二、核心架构设计

### 2.1 域划分

```
packages/data/src/ditto_data/
├── domains/
│   ├── market/          # Market 域：市场原始数据
│   ├── metadata/        # Metadata 域：元数据（原 reference）
│   ├── features/        # Features 域：特征（原 signals）
│   └── factors/         # Factors 域：因子
```

**命名说明**：

| 域 | 原名称 | 新名称 | 原因 |
|---|--------|--------|------|
| 市场数据 | market | market | 保持不变 |
| 参考数据 | reference | **metadata** | 更符合业界习惯，语义清晰 |
| 信号/特征 | signals | **features** | 更符合业界习惯，与 ML 对齐 |
| 因子 | factors | factors | 保持不变 |

### 2.2 架构层次

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Port/App 层（应用编排）                        │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  应用层服务（Port 层）                                           │   │
│  │                                                                 │   │
│  │  - Identity 解析（ts_code/symbol → sid）                         │   │
│  │  - 跨域编排（Market → Features → Factors）                      │   │
│  │  - 业务流程组合                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         域级 QueryService（完全独立）                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  MarketQueryService  │  MetadataQueryService  │  FeaturesQueryService  │
│                                                                         │
│  特点：                                                                   │
│  - 只接收 sid（整数）                                                  │
│  - 无相互依赖                                                           │
│  - 完全独立，可并行部署                                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌─────────────────────────────┐     ┌─────────────────────────────────────┐
│      子域能力模块           │     │              Store 层               │
├─────────────────────────────┤     ├─────────────────────────────────────┤
│                             │     │                                     │
│  market/stock/adj_factor.py │     │  bars_store.py                      │
│  - 复权计算逻辑              │     │  status_store.py                   │
│  - 支持前复权/后复权         │     │  financial_store.py                │
│                             │     │                                     │
│  features/technical/        │     │  price_features_store.py            │
│    price/ma_feature.py      │     │  volume_features_store.py          │
│  - MA 特征计算              │     │                                     │
│  - 支持多周期               │     │  value_factor_store.py             │
│                             │     │                                     │
│  factors/style/value/       │     │  identity_store.py                  │
│    value_pe_factor.py       │     │  security_store.py                 │
│  - PE 价值因子计算          │     │  calendar_store.py                 │
│  - 去极值/标准化/中性化     │     │                                     │
│                             │     │  纯数据访问：Parquet/SQLite         │
└─────────────────────────────┘     └─────────────────────────────────────┘
```

### 2.3 架构对比

| 维度 | 旧架构（Accessor） | 新架构（QueryService） |
|------|-------------------|---------------------|
| **层次** | Store → Accessor → Port | Store → QueryService → Port（应用编排） |
| **Accessor 职责** | 纯数据访问，少量编排 | -（去除） |
| **QueryService 职责** | - | 数据访问 + 业务编排 |
| **子域 Service** | 每个子域独立 Service | -（去除） |
| **域级 Service** | 可选 | **必须**（唯一入口） |
| **子域能力** | 在 Accessor 中 | 独立能力模块（与 Store 同级） |
| **Identity 解析** | 分散在各 Accessor | **统一在应用层**（Port 层） |
| **同层依赖** | 不明确 | **禁止**（域级服务完全独立） |
| **数据转换** | 在 Accessor 中 | 子域能力模块或 Store 层 |
| **可部署性** | 耦合部署 | **独立部署**（各域互不影响） |

---

## 三、详细目录结构

```
packages/data/src/ditto_data/
├── domains/
│   ├── market/
│   │   ├── stock/
│   │   │   ├── bars/
│   │   │   │   └── bars_store.py          # 纯数据访问
│   │   │   ├── status/
│   │   │   │   └── status_store.py
│   │   │   ├── fundamental/
│   │   │   │   └── financial_store.py
│   │   │   ├── corporate/
│   │   │   │   └── dividend_store.py
│   │   │   ├── moneyflow/
│   │   │   │   └── moneyflow_store.py
│   │   │   │
│   │   │   ├── adj_factor.py              # ✅ 子域能力模块（复权逻辑）
│   │   │   ├── price_adjuster.py          # ✅ 子域能力模块（价格调整）
│   │   │   └── ...
│   │   │
│   │   ├── etf/
│   │   │   ├── bars/
│   │   │   │   └── bars_store.py
│   │   │   ├── constituent/
│   │   │   │   └── constituent_store.py
│   │   │   ├── scale/
│   │   │   │   └── scale_store.py
│   │   │   └── ...
│   │   │
│   │   ├── index/
│   │   │   ├── bars/
│   │   │   │   └── bars_store.py
│   │   │   ├── constituent/
│   │   │   │   └── constituent_store.py
│   │   │   └── ...
│   │   │
│   │   └── market_query_service.py       # ✅ Market 域唯一入口
│   │
│   ├── metadata/
│   │   ├── security/
│   │   │   └── security_store.py
│   │   ├── calendar/
│   │   │   └── calendar_store.py
│   │   ├── industry/
│   │   │   └── industry_store.py
│   │   ├── universe/
│   │   │   └── universe_store.py
│   │   ├── identity/
│   │   │   └── identity_store.py         # Identity 映射表存储
│   │   │
│   │   └── metadata_query_service.py     # ✅ Metadata 域唯一入口
│   │                                       # ✅ 可被同层其他服务依赖
│   │
│   ├── features/
│   │   ├── technical/
│   │   │   ├── price/
│   │   │   │   ├── price_features_store.py
│   │   │   │   ├── ma_feature.py          # ✅ 子域能力模块
│   │   │   │   ├── rsi_feature.py         # ✅ 子域能力模块
│   │   │   │   ├── macd_feature.py        # ✅ 子域能力模块
│   │   │   │   └── bollinger_feature.py   # ✅ 子域能力模块
│   │   │   ├── volume/
│   │   │   │   ├── volume_features_store.py
│   │   │   │   ├── obv_feature.py         # ✅ 子域能力模块
│   │   │   │   └── vol_ratio_feature.py   # ✅ 子域能力模块
│   │   │   ├── volatility/
│   │   │   │   ├── volatility_features_store.py
│   │   │   │   ├── atr_feature.py         # ✅ 子域能力模块
│   │   │   │   └── hist_vol_feature.py    # ✅ 子域能力模块
│   │   │   └── ...
│   │   ├── fundamental/
│   │   │   ├── valuation/
│   │   │   │   ├── valuation_features_store.py
│   │   │   │   ├── pe_ratio_feature.py    # ✅ 子域能力模块
│   │   │   │   └── pb_ratio_feature.py    # ✅ 子域能力模块
│   │   │   ├── profitability/
│   │   │   │   ├── profitability_features_store.py
│   │   │   │   ├── roe_feature.py         # ✅ 子域能力模块
│   │   │   │   └── roa_feature.py         # ✅ 子域能力模块
│   │   │   └── ...
│   │   ├── status/
│   │   │   ├── status_features_store.py
│   │   │   ├── trading_status_feature.py  # ✅ 子域能力模块
│   │   │   └── list_status_feature.py     # ✅ 子域能力模块
│   │   ├── macro/
│   │   │   ├── macro_features_store.py
│   │   │   └── ...
│   │   │
│   │   └── features_query_service.py     # ✅ Features 域唯一入口
│   │
│   └── factors/
│       ├── style/
│       │   ├── value/
│       │   │   ├── value_factor_store.py
│       │   │   ├── value_pe_factor.py     # ✅ 子域能力模块
│       │   │   ├── value_pb_factor.py     # ✅ 子域能力模块
│       │   │   └── value_composite.py     # ✅ 子域能力模块
│       │   ├── momentum/
│       │   │   ├── momentum_factor_store.py
│       │   │   ├── momentum_1m_factor.py  # ✅ 子域能力模块
│       │   │   └── momentum_12m_factor.py # ✅ 子域能力模块
│       │   ├── quality/
│       │   │   ├── quality_factor_store.py
│       │   │   ├── roe_quality_factor.py  # ✅ 子域能力模块
│       │   │   └── financial_health_factor.py # ✅ 子域能力模块
│       │   ├── volatility/
│       │   │   ├── volatility_factor_store.py
│       │   │   └── hist_vol_factor.py     # ✅ 子域能力模块
│       │   ├── size/
│       │   │   ├── size_factor_store.py
│       │   │   └── market_cap_factor.py   # ✅ 子域能力模块
│       │   └── ...
│       │
│       ├── industry/
│       │   ├── industry_factor_store.py
│       │   ├── industry_dummy_factor.py   # ✅ 子域能力模块
│       │   └── industry_neutral_factor.py # ✅ 子域能力模块
│       │
│       ├── risk/
│       │   ├── risk_factor_store.py
│       │   ├── beta_factor.py            # ✅ 子域能力模块
│       │   └── liquidity_risk_factor.py  # ✅ 子域能力模块
│       │
│       └── factors_query_service.py      # ✅ Factors 域唯一入口
│
├── stores/                               # 通用 Store（可选）
│   ├── base_store.py                     # Store 基类
│   └── cache_store.py                    # 缓存 Store（如果需要）
│
└── sources/                              # 数据源层（保持不变）
    ├── tushare/
    ├── tdx/
    └── ...
```

---

## 四、核心设计原则

### 4.1 设计原则总结

| 原则 | 说明 | 示例 |
|------|------|------|
| **域级唯一入口** | 每个域只有一个 QueryService | `MarketQueryService` |
| **子域能力模块化** | 子域提供能力模块，不是 Service | `adj_factor.py`, `ma_feature.py` |
| **Store 纯数据访问** | Store 只负责数据读写 | `bars_store.py` |
| **禁止同层依赖** | 域级服务之间完全独立，无相互调用 | 各域可独立部署 |
| **应用层编排** | Identity 解析、跨域编排统一在 Port 层 | Port 层服务 |
| **能力复用** | 子域能力模块可被多个服务调用 | `adj_factor.py` 被 Market/Features 调用 |

### 4.2 能力分层

| 能力类型 | 位置 | 原因 | 示例 |
|---------|------|------|------|
| **Identity 转换** | **应用层（Port 层）** | 统一处理，避免域间耦合 | `PortService.resolve_identity()` |
| **复权计算** | Market 子域能力模块 | 业务逻辑，不是纯数据转换 | `adj_factor.py` |
| **特征计算** | Features 子域能力模块 | 业务逻辑，可复用 | `ma_feature.py` |
| **因子计算** | Factors 子域能力模块 | 业务逻辑，标准化流程 | `value_pe_factor.py` |
| **数据读写** | Store 层 | 纯数据访问 | `bars_store.py` |
| **业务编排** | 应用层（Port 层） | 跨域编排、流程组合 | `PortService.get_features_with_bars()` |

---

## 五、域级 QueryService 设计

### 5.1 MarketQueryService

```python
# domains/market/market_query_service.py
"""
Market 域统一查询服务

职责：
- 统一 Market 域所有数据查询
- 编排子域 Store 和子域能力模块
- 依赖 MetadataQueryService（同层依赖）
"""

from typing import date, Literal
import polars as pl

from ditto_foundation import traced, logger

# Store 层
from ditto_data.domains.market.stock.bars.bars_store import BarsStore
from ditto_data.domains.market.stock.status.status_store import StatusStore
from ditto_data.domains.market.stock.fundamental.financial_store import FinancialStore
from ditto_data.domains.market.etf.bars.bars_store import EtfBarsStore
from ditto_data.domains.market.index.bars.bars_store import IndexBarsStore

# 子域能力模块
from ditto_data.domains.market.stock.adj_factor import AdjFactorCalculator

# 同层依赖
from ditto_data.domains.metadata.metadata_query_service import MetadataQueryService


class MarketQueryService:
    """
    Market 域统一查询服务

    特点：
    - 单一入口，统一 Market 域所有查询
    - 编排多个 Store 和能力模块
    - 依赖 MetadataQueryService 处理 identity
    """

    def __init__(
        self,
        # Store 层
        stock_bars_store: BarsStore,
        stock_status_store: StatusStore,
        stock_financial_store: FinancialStore,
        etf_bars_store: EtfBarsStore,
        index_bars_store: IndexBarsStore,

        # 同层依赖
        metadata_service: MetadataQueryService,
    ):
        # Store 层
        self.stock_bars_store = stock_bars_store
        self.stock_status_store = stock_status_store
        self.stock_financial_store = stock_financial_store
        self.etf_bars_store = etf_bars_store
        self.index_bars_store = index_bars_store

        # 子域能力模块（直接实例化）
        self.adj_factor_calculator = AdjFactorCalculator()

        # 同层依赖
        self.metadata_service = metadata_service

    @traced("market_service.get_stock_bars")
    async def get_stock_bars(
        self,
        identifiers: list[int] | list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        adjust_type: Literal["none", "qfq", "hfq"] = "none",
        with_status: bool = False,
    ) -> pl.DataFrame:
        """
        获取股票行情数据

        Args:
            identifiers: 标的标识符（支持 sid/ts_code/symbol）
            start_date: 起始日期
            end_date: 结束日期
            adjust_type: 复权类型
            with_status: 是否包含状态信息（可选）

        Returns:
            DataFrame with columns:
            - sid, trade_date, open, high, low, close, vol, amount
            - (可选) is_suspended, is_st, is_limit_up, is_limit_down
        """
        # 1. Identity 解析（调用同层依赖的 MetadataService）
        sids = await self.metadata_service.resolve_to_sids(identifiers)

        logger.info(
            "Fetching stock bars",
            event="market_stock_bars_start",
            sids_count=len(sids) if sids else "all",
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )

        # 2. 获取基础数据（Store 层）
        df = await self.stock_bars_store.get_bars(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
        )

        # 3. 复权处理（调用子域能力模块）
        if adjust_type != "none" and not df.is_empty():
            # 获取复权因子
            adj_factors = await self.stock_bars_store.get_adj_factors(
                sids=sids,
                start_date=start_date,
                end_date=end_date,
            )

            # 应用复权（子域能力模块）
            df = self.adj_factor_calculator.apply_adjustment(
                df=df,
                adj_factors=adj_factors,
                adjust_type=adjust_type,
            )

        # 4. 可选：添加状态信息
        if with_status and not df.is_empty():
            status_df = await self.stock_status_store.get_status(
                sids=sids,
                start_date=start_date,
                end_date=end_date,
            )
            df = df.join(status_df, on=["sid", "trade_date"], how="left")

        logger.info(
            "Stock bars fetched",
            event="market_stock_bars_complete",
            rows=len(df),
        )

        return df

    @traced("market_service.get_etf_bars")
    async def get_etf_bars(
        self,
        identifiers: list[int] | list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """获取 ETF 行情数据"""
        sids = await self.metadata_service.resolve_to_sids(identifiers)
        df = await self.etf_bars_store.get_bars(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
        )
        return df

    @traced("market_service.get_index_bars")
    async def get_index_bars(
        self,
        identifiers: list[int] | list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """获取指数行情数据"""
        sids = await self.metadata_service.resolve_to_sids(identifiers)
        df = await self.index_bars_store.get_bars(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
        )
        return df
```

### 5.2 MetadataQueryService

```python
# domains/metadata/metadata_query_service.py
"""
Metadata 域统一查询服务

职责：
- 统一 Metadata 域所有数据查询
- 提供 Identity 解析能力（供同层其他服务使用）
"""

from typing import Literal
import polars as pl

from ditto_foundation import traced

# Store 层
from ditto_data.domains.metadata.security.security_store import SecurityStore
from ditto_data.domains.metadata.calendar.calendar_store import CalendarStore
from ditto_data.domains.metadata.industry.industry_store import IndustryStore
from ditto_data.domains.metadata.identity.identity_store import IdentityStore


class MetadataQueryService:
    """
    Metadata 域统一查询服务

    特点：
    - 可被同层其他服务依赖（如 MarketService）
    - 提供 Identity 解析能力
    """

    def __init__(
        self,
        security_store: SecurityStore,
        calendar_store: CalendarStore,
        industry_store: IndustryStore,
        identity_store: IdentityStore,
    ):
        self.security_store = security_store
        self.calendar_store = calendar_store
        self.industry_store = industry_store
        self.identity_store = identity_store

    @traced("metadata_service.resolve_to_sids")
    async def resolve_to_sids(
        self,
        identifiers: list[int] | list[str] | None,
        input_type: Literal["auto", "sid", "ts_code", "symbol"] = "auto",
    ) -> list[int] | None:
        """
        解析为 SID 列表（供同层服务调用）

        Args:
            identifiers: 标的标识符列表
            input_type: 输入类型（auto 自动识别）

        Returns:
            SID 列表

        Examples:
            >>> service = MetadataQueryService(...)
            >>> sids = await service.resolve_to_sids(["000001.SZ", "600000.SH"])
            >>> [1000001, 1000002]
        """
        if identifiers is None:
            return None

        return await self.identity_store.resolve(
            identifiers=identifiers,
            input_type=input_type,
            output_type="sid",
        )

    @traced("metadata_service.get_security_info")
    async def get_security_info(
        self,
        sids: list[int],
    ) -> pl.DataFrame:
        """获取证券基本信息"""
        return await self.security_store.get_info(sids)

    @traced("metadata_service.get_trade_dates")
    async def get_trade_dates(
        self,
        exchange: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[str]:
        """获取交易日历"""
        return await self.calendar_store.get_trade_dates(
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
        )

    @traced("metadata_service.get_industry")
    async def get_industry(
        self,
        sids: list[int],
        trade_date: str | None = None,
    ) -> pl.DataFrame:
        """获取行业分类"""
        return await self.industry_store.get_industry(
            sids=sids,
            trade_date=trade_date,
        )
```

### 5.3 FeaturesQueryService

```python
# domains/features/features_query_service.py
"""
Features 域统一查询服务

职责：
- 统一 Features 域所有特征查询
- 编排子域 Store 和能力模块
- 依赖 MarketQueryService 和 MetadataQueryService（同层依赖）
"""

from typing import date
import polars as pl

from ditto_foundation import traced, logger

# Store 层
from ditto_data.domains.features.technical.price.price_features_store import PriceFeaturesStore
from ditto_data.domains.features.technical.volume.volume_features_store import VolumeFeaturesStore

# 子域能力模块
from ditto_data.domains.features.technical.price.ma_feature import MaFeatureCalculator
from ditto_data.domains.features.technical.price.rsi_feature import RsiFeatureCalculator

# 同层依赖
from ditto_data.domains.market.market_query_service import MarketQueryService
from ditto_data.domains.metadata.metadata_query_service import MetadataQueryService


class FeaturesQueryService:
    """
    Features 域统一查询服务

    特点：
    - 编排多个特征 Store 和能力模块
    - 依赖 MarketService 获取基础数据
    - 依赖 MetadataService 处理 identity
    """

    def __init__(
        self,
        # Store 层
        price_features_store: PriceFeaturesStore,
        volume_features_store: VolumeFeaturesStore,

        # 同层依赖
        market_service: MarketQueryService,
        metadata_service: MetadataQueryService,
    ):
        # Store 层
        self.price_features_store = price_features_store
        self.volume_features_store = volume_features_store

        # 子域能力模块
        self.ma_calculator = MaFeatureCalculator()
        self.rsi_calculator = RsiFeatureCalculator()

        # 同层依赖
        self.market_service = market_service
        self.metadata_service = metadata_service

    @traced("features_service.get_price_features")
    async def get_price_features(
        self,
        feature_ids: list[str],
        identifiers: list[int] | list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        version: str = "v1.0",
        compute_if_missing: bool = True,
    ) -> pl.DataFrame:
        """
        获取价格特征

        Args:
            feature_ids: 特征 ID 列表（如 ["ma_20", "rsi_14"]）
            identifiers: 标的标识符（自动转换）
            start_date: 起始日期
            end_date: 结束日期
            version: 特征版本
            compute_if_missing: 如果特征不存在，是否实时计算

        Returns:
            DataFrame with columns:
            - sid, trade_date, feature_id, value
        """
        # 1. Identity 解析（调用同层依赖）
        sids = await self.metadata_service.resolve_to_sids(identifiers)

        logger.info(
            "Fetching price features",
            event="features_price_start",
            feature_ids=feature_ids,
            sids_count=len(sids) if sids else "all",
            start_date=start_date,
            end_date=end_date,
        )

        # 2. 尝试从存储获取
        df = await self.price_features_store.get_features(
            feature_ids=feature_ids,
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            version=version,
        )

        # 3. 如果需要且允许，实时计算缺失特征
        if compute_if_missing and df.is_empty():
            df = await self._compute_price_features_realtime(
                feature_ids=feature_ids,
                sids=sids,
                start_date=start_date,
                end_date=end_date,
            )

        logger.info(
            "Price features fetched",
            event="features_price_complete",
            rows=len(df),
        )

        return df

    async def _compute_price_features_realtime(
        self,
        feature_ids: list[str],
        sids: list[int],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """
        实时计算价格特征

        编排：
        1. 调用 MarketService 获取基础数据
        2. 调用子域能力模块计算特征
        """
        # 1. 获取基础数据（调用同层依赖 MarketService）
        bars = await self.market_service.get_stock_bars(
            identifiers=sids,
            start_date=start_date,
            end_date=end_date,
            adjust_type="none",
        )

        # 2. 计算特征（调用子域能力模块）
        features_list = []
        for feature_id in feature_ids:
            if feature_id.startswith("ma_"):
                period = int(feature_id.split("_")[1])
                feature_df = self.ma_calculator.compute(bars, period)
            elif feature_id.startswith("rsi_"):
                period = int(feature_id.split("_")[1])
                feature_df = self.rsi_calculator.compute(bars, period)
            else:
                logger.warning(f"Unknown feature ID: {feature_id}")
                continue

            features_list.append(feature_df)

        # 3. 合并特征
        if features_list:
            df = pl.concat(features_list)
        else:
            df = pl.DataFrame(schema={
                "sid": pl.Int32,
                "trade_date": pl.Date,
                "feature_id": pl.String,
                "value": pl.Float64,
            })

        return df
```

### 5.4 FactorsQueryService

```python
# domains/factors/factors_query_service.py
"""
Factors 域统一查询服务

职责：
- 统一 Factors 域所有因子查询
- 编排子域 Store 和能力模块
- 依赖 FeaturesQueryService 和 MetadataQueryService（同层依赖）
"""

from typing import date
import polars as pl

from ditto_foundation import traced, logger

# Store 层
from ditto_data.domains.factors.style.value.value_factor_store import ValueFactorStore
from ditto_data.domains.factors.style.momentum.momentum_factor_store import MomentumFactorStore
from ditto_data.domains.factors.industry.industry_factor_store import IndustryFactorStore

# 子域能力模块
from ditto_data.domains.factors.style.value.value_pe_factor import ValuePeFactorCalculator
from ditto_data.domains.factors.style.momentum.momentum_12m_factor import Momentum12mFactorCalculator

# 同层依赖
from ditto_data.domains.features.features_query_service import FeaturesQueryService
from ditto_data.domains.metadata.metadata_query_service import MetadataQueryService


class FactorsQueryService:
    """
    Factors 域统一查询服务

    特点：
    - 编排多个因子 Store 和能力模块
    - 依赖 FeaturesService 获取特征数据
    - 依赖 MetadataService 处理 identity 和行业信息
    """

    def __init__(
        self,
        # Store 层
        value_factor_store: ValueFactorStore,
        momentum_factor_store: MomentumFactorStore,
        industry_factor_store: IndustryFactorStore,

        # 同层依赖
        features_service: FeaturesQueryService,
        metadata_service: MetadataQueryService,
    ):
        # Store 层
        self.value_factor_store = value_factor_store
        self.momentum_factor_store = momentum_factor_store
        self.industry_factor_store = industry_factor_store

        # 子域能力模块
        self.value_pe_calculator = ValuePeFactorCalculator()
        self.momentum_12m_calculator = Momentum12mFactorCalculator()

        # 同层依赖
        self.features_service = features_service
        self.metadata_service = metadata_service

    @traced("factors_service.get_style_factors")
    async def get_style_factors(
        self,
        factor_ids: list[str],
        identifiers: list[int] | list[str] | None = None,
        trade_date: date | None = None,
        version: str = "v1.0",
    ) -> pl.DataFrame:
        """
        获取风格因子

        Args:
            factor_ids: 因子 ID 列表（如 ["value_pe", "momentum_12m"]）
            identifiers: 标的标识符
            trade_date: 交易日期
            version: 因子版本

        Returns:
            DataFrame with columns:
            - sid, trade_date, factor_id, exposure
        """
        # 1. Identity 解析
        sids = await self.metadata_service.resolve_to_sids(identifiers)

        # 2. 尝试从存储获取
        df = await self.value_factor_store.get_factors(
            factor_ids=factor_ids,
            sids=sids,
            trade_date=trade_date,
            version=version,
        )

        # 3. 如果不存在，实时计算
        if df.is_empty():
            df = await self._compute_factors_realtime(
                factor_ids=factor_ids,
                sids=sids,
                trade_date=trade_date,
            )

        return df

    async def _compute_factors_realtime(
        self,
        factor_ids: list[str],
        sids: list[int],
        trade_date: date,
    ) -> pl.DataFrame:
        """实时计算因子"""
        # 1. 获取特征数据
        features = await self.features_service.get_features(
            identifiers=sids,
            end_date=trade_date,
        )

        # 2. 计算因子（调用子域能力模块）
        factors_list = []
        for factor_id in factor_ids:
            if factor_id == "value_pe":
                factor_df = self.value_pe_calculator.compute(
                    features=features,
                    trade_date=trade_date,
                )
            elif factor_id == "momentum_12m":
                factor_df = self.momentum_12m_calculator.compute(
                    features=features,
                    trade_date=trade_date,
                )
            else:
                logger.warning(f"Unknown factor ID: {factor_id}")
                continue

            factors_list.append(factor_df)

        # 3. 合并因子
        if factors_list:
            df = pl.concat(factors_list)
        else:
            df = pl.DataFrame(schema={
                "sid": pl.Int32,
                "trade_date": pl.Date,
                "factor_id": pl.String,
                "exposure": pl.Float64,
            })

        return df
```

---

## 六、子域能力模块设计

### 6.1 复权计算模块（Market 子域）

```python
# domains/market/stock/adj_factor.py
"""
股票复权计算模块（子域能力）

职责：
- 复权因子计算逻辑
- 前复权/后复权应用
- 可被多个服务调用（MarketService、FeaturesService）
"""

from typing import Literal
import polars as pl


class AdjFactorCalculator:
    """
    复权计算器

    注意：
    - 这是子域能力模块，不是 Service
    - 提供纯计算逻辑，无状态
    - 可被 MarketService、FeaturesService 等调用
    """

    def apply_adjustment(
        self,
        df: pl.DataFrame,
        adj_factors: pl.DataFrame,
        adjust_type: Literal["qfq", "hfq"],
    ) -> pl.DataFrame:
        """
        应用复权

        Args:
            df: 原始行情数据
            adj_factors: 复权因子数据
            adjust_type: 复权类型（qfq: 前复权, hfq: 后复权）

        Returns:
            复权后的行情数据
        """
        if adjust_type == "qfq":
            return self._apply_qfq(df, adj_factors)
        elif adjust_type == "hfq":
            return self._apply_hfq(df, adj_factors)
        else:
            return df

    def _apply_qfq(self, df: pl.DataFrame, adj_factors: pl.DataFrame) -> pl.DataFrame:
        """
        前复权计算

        逻辑：
        - 获取每个 sid 的最新复权因子
        - 所有历史价格乘以（最新复权因子 / 当日复权因子）
        """
        # 1. Join 复权因子
        df = df.join(
            adj_factors.select(["sid", "trade_date", "adj_factor"]),
            on=["sid", "trade_date"],
            how="left",
        )

        # 2. 获取每个 sid 的最新复权因子
        latest_adj = adj_factors.groupby("sid").agg(
            pl.col("adj_factor").last().alias("latest_adj_factor")
        )

        # 3. 应用前复权
        df = df.join(latest_adj, on="sid", how="left")

        price_columns = ["open", "high", "low", "close", "pre_close"]
        for col in price_columns:
            if col in df.columns:
                df = df.with_columns(
                    (pl.col(col) * pl.col("latest_adj_factor") / pl.col("adj_factor"))
                    .alias(col)
                )

        # 4. 清理临时列
        df = df.drop(["adj_factor", "latest_adj_factor"])

        return df

    def _apply_hfq(self, df: pl.DataFrame, adj_factors: pl.DataFrame) -> pl.DataFrame:
        """
        后复权计算

        逻辑：
        - 获取每个 sid 的首次复权因子
        - 所有历史价格乘以（当日复权因子 / 首次复权因子）
        """
        # 1. Join 复权因子
        df = df.join(
            adj_factors.select(["sid", "trade_date", "adj_factor"]),
            on=["sid", "trade_date"],
            how="left",
        )

        # 2. 获取每个 sid 的首次复权因子
        first_adj = adj_factors.groupby("sid").agg(
            pl.col("adj_factor").first().alias("first_adj_factor")
        )

        # 3. 应用后复权
        df = df.join(first_adj, on="sid", how="left")

        price_columns = ["open", "high", "low", "close", "pre_close"]
        for col in price_columns:
            if col in df.columns:
                df = df.with_columns(
                    (pl.col(col) * pl.col("adj_factor") / pl.col("first_adj_factor"))
                    .alias(col)
                )

        # 4. 清理临时列
        df = df.drop(["adj_factor", "first_adj_factor"])

        return df
```

### 6.2 MA 特征计算模块（Features 子域）

```python
# domains/features/technical/price/ma_feature.py
"""
MA 移动平均线特征计算模块（子域能力）

职责：
- MA 特征计算逻辑
- 支持多周期
- 可被多个服务调用
"""

import polars as pl


class MaFeatureCalculator:
    """
    MA 移动平均线计算器

    注意：
    - 这是子域能力模块，不是 Service
    - 提供纯计算逻辑，无状态
    - 可被 FeaturesService、FactorsService 等调用
    """

    def compute(
        self,
        bars: pl.DataFrame,
        period: int,
    ) -> pl.DataFrame:
        """
        计算 MA 特征

        Args:
            bars: 行情数据，需包含列
                - sid, trade_date, close
            period: 周期（如 20, 60）

        Returns:
            DataFrame with columns:
            - sid, trade_date, feature_id, value
        """
        # 1. 计算 MA
        df = bars.with_columns(
            pl.col("close")
            .rolling_mean(window_size=period, min_periods=period)
            .alias("ma_value")
        )

        # 2. 过滤空值
        df = df.filter(pl.col("ma_value").is_not_null())

        # 3. 格式化为特征格式
        feature_id = f"ma_{period}"
        df = df.select([
            pl.col("sid"),
            pl.col("trade_date"),
            pl.lit(feature_id).alias("feature_id"),
            pl.col("ma_value").alias("value"),
        ])

        return df
```

### 6.3 价值因子计算模块（Factors 子域）

```python
# domains/factors/style/value/value_pe_factor.py
"""
PE 价值因子计算模块（子域能力）

职责：
- PE 价值因子计算逻辑
- 去极值、标准化、中性化
- 可被多个服务调用
"""

from typing import date
import polars as pl


class ValuePeFactorCalculator:
    """
    PE 价值因子计算器

    注意：
    - 这是子域能力模块，不是 Service
    - 提供因子计算逻辑，无状态
    - 包含完整的因子处理流程
    """

    def compute(
        self,
        features: pl.DataFrame,
        trade_date: date,
    ) -> pl.DataFrame:
        """
        计算 PE 价值因子

        Args:
            features: 特征数据，需包含 pe_ratio 列
            trade_date: 交易日期

        Returns:
            DataFrame with columns:
            - sid, trade_date, factor_id, exposure
        """
        # 1. 提取 PE 特征
        df = features.filter(
            (pl.col("trade_date") == trade_date) &
            (pl.col("feature_id") == "pe_ratio")
        ).select([
            pl.col("sid"),
            pl.col("value").alias("pe_raw"),
        ])

        # 2. 转换为 PE 倒数（PE 越低，价值越高）
        df = df.with_columns(
            (1.0 / pl.col("pe_raw")).alias("pe_inv_raw")
        )

        # 3. 去极值（MAD 方法）
        df = self._winsorize_mad(df, "pe_inv_raw", n=3)

        # 4. 标准化（Z-score）
        df = self._standardize(df, "pe_inv_raw")

        # 5. 格式化为因子格式
        df = df.select([
            pl.col("sid"),
            pl.lit(trade_date).alias("trade_date"),
            pl.lit("value_pe").alias("factor_id"),
            pl.col("pe_inv_raw").alias("exposure"),
        ])

        return df

    def _winsorize_mad(
        self,
        df: pl.DataFrame,
        column: str,
        n: int = 3,
    ) -> pl.DataFrame:
        """去极值（MAD 方法）"""
        median = df[column].median()
        mad = (df[column] - median).abs().median()
        upper = median + n * mad
        lower = median - n * mad

        return df.with_columns(
            pl.col(column).clip(lower, upper).alias(column)
        )

    def _standardize(
        self,
        df: pl.DataFrame,
        column: str,
    ) -> pl.DataFrame:
        """标准化（Z-score）"""
        mean = df[column].mean()
        std = df[column].std()

        return df.with_columns(
            ((pl.col(column) - mean) / std).alias(column)
        )
```

---

## 七、Store 层设计

### 7.1 Store 基类

```python
# stores/base_store.py
"""
Store 基类

职责：
- 定义 Store 层统一接口
- 提供通用数据访问能力
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import polars as pl


class BaseStore(ABC):
    """
    Store 基类

    职责：
    - 纯数据访问
    - Parquet/SQLite 文件读写
    - 不包含业务编排
    """

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    @abstractmethod
    async def get_data(self, **kwargs) -> pl.DataFrame:
        """获取数据（子类实现）"""
        pass

    @abstractmethod
    async def write_data(self, data: pl.DataFrame) -> None:
        """写入数据（子类实现）"""
        pass
```

### 7.2 BarsStore 示例

```python
# domains/market/stock/bars/bars_store.py
"""
股票行情数据存储

职责：
- Parquet 文件读写
- 纯数据访问，无业务逻辑
"""

from pathlib import Path
from typing import date
import polars as pl

from ditto_data.stores.base_store import BaseStore


class BarsStore(BaseStore):
    """
    股票行情数据存储

    职责：
    - Parquet 文件读写
    - 数据过滤和投影
    - 不包含复权等业务逻辑
    """

    def __init__(self, base_path: Path = Path("data_root/market/stock/bars/daily")):
        super().__init__(base_path)

    async def get_bars(
        self,
        sids: list[int] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """
        获取行情数据

        Args:
            sids: 标的 ID 列表（必须是 sid）
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            DataFrame with columns:
            - sid, trade_date, open, high, low, close, vol, amount
        """
        # 1. 构建文件路径
        years = self._get_years(start_date, end_date)
        dfs = []

        for year in years:
            file_path = self.base_path / f"{year}.parquet"
            if not file_path.exists():
                continue

            # 2. 读取 Parquet
            df = pl.read_parquet(file_path)
            dfs.append(df)

        if not dfs:
            return pl.DataFrame()

        # 3. 合并
        df = pl.concat(dfs)

        # 4. 应用过滤条件
        if sids:
            df = df.filter(pl.col("sid").is_in(sids))

        if start_date:
            df = df.filter(pl.col("trade_date") >= start_date)

        if end_date:
            df = df.filter(pl.col("trade_date") <= end_date)

        return df

    async def get_adj_factors(
        self,
        sids: list[int] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """获取复权因子数据"""
        adj_path = self.base_path.parent / "adj"
        years = self._get_years(start_date, end_date)
        dfs = []

        for year in years:
            file_path = adj_path / f"{year}.parquet"
            if not file_path.exists():
                continue

            df = pl.read_parquet(file_path)
            dfs.append(df)

        if not dfs:
            return pl.DataFrame()

        df = pl.concat(dfs)

        # 应用过滤
        if sids:
            df = df.filter(pl.col("sid").is_in(sids))

        if start_date:
            df = df.filter(pl.col("trade_date") >= start_date)

        if end_date:
            df = df.filter(pl.col("trade_date") <= end_date)

        return df

    def _get_years(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> list[int]:
        """获取涉及的年份列表"""
        if start_date and end_date:
            return range(start_date.year, end_date.year + 1)
        elif start_date:
            return range(start_date.year, start_date.year + 1)
        elif end_date:
            return range(end_date.year, end_date.year + 1)
        else:
            return [2024]  # 默认当前年

    async def write_data(self, data: pl.DataFrame) -> None:
        """写入数据"""
        # 按年分区写入
        for year, df in data.groupby("trade_date").agg(pl.all()).iterrows():
            file_path = self.base_path / f"{year}.parquet"
            df.write_parquet(file_path)
```

---

## 八、同层依赖设计

### 8.1 依赖关系图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          同层依赖关系                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   MarketQueryService ──────────────────────────────────┐                │
│         │                                               │                │
│         │ 依赖                                           │                │
│         ▼                                               │                │
│   MetadataQueryService ◄────────────────────────────────┤                │
│         ▲                                               │                │
│         │ 被依赖                                        │                │
│         │                                               │                │
│   FeaturesQueryService ─────────────────────────────────┤                │
│         │                                               │                │
│         │ 依赖                                           │                │
│         ▼                                               │                │
│   MarketQueryService                                    │                │
│   MetadataQueryService                                  │                │
│                                                         │                │
│   FactorsQueryService ──────────────────────────────────┘                │
│         │                                                                │
│         │ 依赖                                                            │
│         ▼                                                                │
│   FeaturesQueryService                                                   │
│   MetadataQueryService                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 依赖规则

| 规则 | 说明 | 示例 |
|------|------|------|
| **允许域级服务依赖** | QueryService 可依赖其他域级 QueryService | MarketService → MetadataService |
| **禁止依赖下层** | QueryService 不直接依赖 Store | ❌ MarketService → IdentityStore |
| **禁止循环依赖** | 避免服务间循环依赖 | ❌ A → B → A |
| **单向依赖优先** | 优先使用单向依赖 | ✅ Factors → Features → Market |

---

## 九、数据集分类与映射

### 9.1 Market 域数据集

| 子域 | 数据集 | Tushare API | 存储格式 | 键列 |
|------|--------|-------------|----------|------|
| `stock/bars/daily` | `stock_daily` | `daily` | Parquet | `(sid, trade_date)` |
| `stock/bars/adj` | `adj_factor` | `adj_factor` | Parquet | `(sid, trade_date)` |
| `stock/status` | `stock_status` | `suspend/status_st` | Parquet | `(sid, trade_date)` |
| `stock/corporate/dividend` | `stock_dividend` | `dividend` | Parquet | `(sid, ex_date)` |
| `stock/fundamental/financial` | `stock_financial` | `balancesheet/income/cashflow` | Parquet | `(sid, report_date, report_type)` |
| `etf/bars/daily` | `etf_daily` | `daily` | Parquet | `(sid, trade_date)` |
| `etf/constituent` | `etf_constituent` | `index_weight` | SQLite | `(etf_id, sid, effective_from, effective_to)` |
| `index/bars/daily` | `index_daily` | `daily` | Parquet | `(sid, trade_date)` |
| `index/constituent` | `index_constituent` | `index_member` | SQLite | `(index_id, sid, effective_from, effective_to)` |

### 9.2 Metadata 域数据集

| 子域 | 数据集 | Tushare API | 存储格式 | 键列 |
|------|--------|-------------|----------|------|
| `security` | `securities` | `stock_basic/fund_basic` | SQLite | `(sid)` |
| `calendar` | `trade_calendar` | `trade_calendar` | SQLite | `(exchange, trade_date)` |
| `industry` | `industry_classification` | `index_classify` | SQLite | `(sid, effective_from, effective_to)` |
| `universe` | `universe_constituent` | - | SQLite | `(universe_id, sid, effective_from, effective_to)` |
| `identity` | `identity_mapping` | - | SQLite | `(sid, ts_code, symbol, effective_from, effective_to)` |

### 9.3 Features 域数据集

| 子域 | 特征类别 | 特征示例 | 存储路径 |
|------|---------|---------|---------|
| `technical/price` | 趋势 | `ma_20`, `ma_60`, `macd` | `price_features_{version}/{year}.parquet` |
| `technical/price` | 动量 | `rsi_14`, `cci_20` | `price_features_{version}/{year}.parquet` |
| `technical/volume` | 成交量 | `vol_ratio_5`, `obv` | `volume_features_{version}/{year}.parquet` |
| `technical/volatility` | 波动率 | `atr_14`, `hist_vol_20` | `volatility_features_{version}/{year}.parquet` |
| `fundamental/valuation` | 估值 | `pe_ratio`, `pb_ratio`, `ps_ratio` | `valuation_features_{version}/{year}.parquet` |
| `fundamental/profitability` | 盈利能力 | `roe`, `roa`, `roic` | `profitability_features_{version}/{year}.parquet` |
| `status` | 交易状态 | `is_suspended`, `is_st`, `is_limit_up` | `status_features_{version}/{year}.parquet` |

### 9.4 Factors 域数据集

| 子域 | 因子类别 | 因子示例 | 存储格式 |
|------|---------|---------|---------|
| `style/value` | 价值 | `value_pe`, `value_pb`, `value_composite` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |
| `style/momentum` | 动量 | `momentum_1m`, `momentum_12m` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |
| `style/quality` | 质量 | `quality_roe`, `quality_financial_health` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |
| `style/volatility` | 波动率 | `volatility_hist`, `volatility_idiosyncratic` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |
| `style/size` | 规模 | `size_market_cap`, `size_free_float` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |
| `industry` | 行业 | `industry_dummy`, `industry_neutral` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |
| `risk` | 风险 | `risk_beta`, `risk_liquidity` | 窄表：`(sid, trade_date, factor_id, exposure, version)` |

---

## 十、物理存储结构

```
data_root/
│
├── market/                      # Market 域存储
│   ├── stock/
│   │   ├── bars/daily/{year}.parquet
│   │   ├── bars/adj/{year}.parquet
│   │   ├── status/{year}.parquet
│   │   ├── corporate/dividend/{year}.parquet
│   │   └── fundamental/financial/{year}.parquet
│   ├── etf/
│   │   ├── bars/daily/{year}.parquet
│   │   ├── scale/{year}.parquet
│   │   └── basic/etf_basic.sqlite
│   └── index/
│       ├── bars/daily/{year}.parquet
│       ├── constituent/index_constituent.sqlite
│       └── weight/{year}.parquet
│
├── metadata/                    # Metadata 域存储
│   ├── security/securities.sqlite
│   ├── calendar/trade_calendar.sqlite
│   ├── industry/industry.sqlite
│   ├── universe/universe.sqlite
│   └── identity/identity_mapping.sqlite
│
├── features/                    # Features 域存储
│   ├── technical/price/price_features_{version}/{year}.parquet
│   ├── technical/volume/volume_features_{version}/{year}.parquet
│   ├── technical/volatility/volatility_features_{version}/{year}.parquet
│   ├── fundamental/valuation/valuation_features_{version}/{year}.parquet
│   ├── fundamental/profitability/profitability_features_{version}/{year}.parquet
│   └── status/status_features_{version}/{year}.parquet
│
├── factors/                     # Factors 域存储
│   ├── narrow/                  # 窄表主存储
│   │   ├── style/value/{year}.parquet
│   │   ├── style/momentum/{year}.parquet
│   │   ├── style/quality/{year}.parquet
│   │   ├── industry/industry_dummy/{year}.parquet
│   │   └── risk/market_beta/{year}.parquet
│   │
│   ├── wide/                    # 宽表辅助存储
│   │   ├── style/value_v1.0/{year}.parquet
│   │   └── snapshots/backtest_{date}/all_factors.parquet
│   │
│   └── meta/                   # 因子元数据
│       ├── factor_registry.sqlite
│       ├── factor_versions.sqlite
│       └── factor_lineage.sqlite
│
└── meta/                       # 全局元数据
    ├── feature_registry.sqlite
    └── quality/
        ├── quarantine/          # 质量隔离区
        ├── comparison/          # 跨源对比结果
        └── golden_dataset/      # 黄金数据集冻结
```

---

## 十一、使用示例

### 11.1 基础使用

```python
# 初始化服务
market_service = MarketQueryService(...)
metadata_service = MetadataQueryService(...)
features_service = FeaturesQueryService(..., market_service, metadata_service)
factors_service = FactorsQueryService(..., features_service, metadata_service)

# 1. 获取股票行情（支持多种标识符）
df = await market_service.get_stock_bars(
    identifiers=["000001.SZ", "600000.SH"],  # 支持 ts_code
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    adjust_type="qfq",  # 前复权
)

# 2. 获取价格特征
features = await features_service.get_price_features(
    feature_ids=["ma_20", "rsi_14", "macd"],
    identifiers=["000001.SZ", "600000.SH"],
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
)

# 3. 获取价值因子
factors = await factors_service.get_style_factors(
    factor_ids=["value_pe", "value_pb"],
    identifiers=["000001.SZ", "600000.SH"],
    trade_date=date(2024, 12, 31),
)
```

### 11.2 同层依赖示例

```python
# MarketService 依赖 MetadataService
class MarketQueryService:
    def __init__(self, ..., metadata_service: MetadataQueryService):
        self.metadata_service = metadata_service

    async def get_stock_bars(self, identifiers, ...):
        # 调用同层依赖解析 identity
        sids = await self.metadata_service.resolve_to_sids(identifiers)
        # ...

# FactorsService 依赖 FeaturesService 和 MetadataService
class FactorsQueryService:
    def __init__(
        self,
        ...,
        features_service: FeaturesQueryService,
        metadata_service: MetadataQueryService,
    ):
        self.features_service = features_service
        self.metadata_service = metadata_service

    async def get_style_factors(self, factor_ids, ...):
        # 调用同层依赖获取特征
        features = await self.features_service.get_features(...)
        # 调用同层依赖获取行业信息
        industry = await self.metadata_service.get_industry(...)
        # ...
```

---

## 十二、设计决策总结

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **域命名** | **Market/Metadata/Features/Factors** | 更符合业界习惯，语义清晰 |
| **Accessor 层** | **去除** | 职责与 QueryService 重叠 |
| **子域 Service** | **去除** | 层次过深，理解困难 |
| **域级 Service** | **必须（唯一入口）** | 清晰的域边界 |
| **子域能力模块** | **独立模块（与 Store 同级）** | 业务逻辑清晰，易于复用 |
| **复权逻辑** | **Market 子域能力模块** | 业务逻辑，不是纯数据转换 |
| **Identity 转换** | **应用层（Port 层）** | 统一处理，避免域间耦合 |
| **同层依赖** | **禁止** | 域级服务完全独立，可独立部署 |
| **Common 层** | **去除** | 无需通用层，各域独立 |
| **Store 层** | **纯数据访问** | Parquet/SQLite 读写，无业务逻辑 |
| **sid 参数** | **只接收整数 sid** | 类型明确，避免歧义 |

---

## 十三、应用层编排示例（Port 层）

```python
# apps/port/services/data_service.py
"""
应用层服务（Port 层）

职责：
- Identity 解析（ts_code/symbol → sid）
- 跨域编排（Market → Features → Factors）
- 业务流程组合
"""

from typing import date, list
import polars as pl

from ditto_foundation import traced, logger

# 域级服务（无同层依赖）
from ditto_data.domains.market.market_query_service import MarketQueryService
from ditto_data.domains.metadata.metadata_query_service import MetadataQueryService
from ditto_data.domains.features.features_query_service import FeaturesQueryService
from ditto_data.domains.factors.factors_query_service import FactorsQueryService


class DataService:
    """
    应用层数据服务

    特点：
    - 负责身份解析和跨域编排
    - 提供面向业务的高层接口
    """

    def __init__(
        self,
        market_service: MarketQueryService,
        metadata_service: MetadataQueryService,
        features_service: FeaturesQueryService,
        factors_service: FactorsQueryService,
    ):
        self.market_service = market_service
        self.metadata_service = metadata_service
        self.features_service = features_service
        self.factors_service = factors_service

    @traced("port_service.resolve_identity")
    async def resolve_identity(
        self,
        identifiers: list[int] | list[str],
        input_type: str = "auto",
    ) -> list[int]:
        """
        Identity 解析（应用层统一处理）

        Args:
            identifiers: 标的标识符（支持 sid/ts_code/symbol）
            input_type: 输入类型（auto 自动识别）

        Returns:
            sid 列表
        """
        # 调用 MetadataService 进行解析
        return await self.metadata_service.resolve_to_sids(
            identifiers=identifiers,
            input_type=input_type,
        )

    @traced("port_service.get_stock_bars_with_features")
    async def get_stock_bars_with_features(
        self,
        identifiers: list[int] | list[str],  # 支持多种格式
        start_date: date | None = None,
        end_date: date | None = None,
        feature_ids: list[str] | None = None,
        adjust_type: str = "none",
    ) -> pl.DataFrame:
        """
        获取行情数据和特征（跨域编排）

        流程：
        1. Identity 解析（ts_code/symbol → sid）
        2. 获取行情数据（MarketService）
        3. 获取特征数据（FeaturesService）
        4. 合并返回

        Args:
            identifiers: 标的标识符（支持 sid/ts_code/symbol）
            start_date: 起始日期
            end_date: 结束日期
            feature_ids: 特征 ID 列表
            adjust_type: 复权类型

        Returns:
            合并后的数据和特征
        """
        # 1. Identity 解析（应用层）
        sids = await self.resolve_identity(identifiers)

        # 2. 并行获取行情和特征（无依赖，可并行）
        import asyncio

        bars_task = self.market_service.get_stock_bars(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )

        features_task = None
        if feature_ids:
            features_task = self.features_service.get_price_features(
                feature_ids=feature_ids,
                sids=sids,
                start_date=start_date,
                end_date=end_date,
            )

        # 并行执行
        results = await asyncio.gather(
            bars_task,
            features_task,
            return_exceptions=True,
        )

        bars = results[0]
        features = results[1] if features_task else None

        # 3. 合并数据
        if features and not features.is_empty():
            # Pivot 特征数据
            features_wide = features.pivot(
                index=["sid", "trade_date"],
                columns="feature_id",
                values="value",
            )
            result = bars.join(features_wide, on=["sid", "trade_date"], how="left")
        else:
            result = bars

        return result

    @traced("port_service.compute_factors")
    async def compute_factors(
        self,
        identifiers: list[int] | list[str],
        trade_date: date,
        factor_ids: list[str],
    ) -> pl.DataFrame:
        """
        计算因子（跨域编排）

        流程：
        1. Identity 解析
        2. 获取特征数据
        3. 计算因子
        4. 返回结果

        Args:
            identifiers: 标的标识符
            trade_date: 交易日期
            factor_ids: 因子 ID 列表

        Returns:
            因子暴露度数据
        """
        # 1. Identity 解析
        sids = await self.resolve_identity(identifiers)

        # 2. 获取特征数据
        features = await self.features_service.get_features(
            sids=sids,
            end_date=trade_date,
        )

        # 3. 获取行业信息（用于中性化）
        industry = await self.metadata_service.get_industry(
            sids=sids,
            trade_date=str(trade_date),
        )

        # 4. 计算因子
        factors = await self.factors_service.compute_factors(
            sids=sids,
            trade_date=trade_date,
            factor_ids=factor_ids,
            features=features,
            industry=industry,
        )

        return factors
```

---

## 十四、实施路线图

| 阶段 | 任务 | 优先级 |
|------|------|--------|
| **阶段 1** | 创建域级 QueryService 骨架（只接收 sid） | P0 |
| **阶段 2** | 迁移现有 Accessor 逻辑到 QueryService | P0 |
| **阶段 3** | 提取子域能力模块（复权、特征计算等） | P1 |
| **阶段 4** | 实现 Port 层服务（Identity 解析 + 跨域编排） | P1 |
| **阶段 5** | 重构测试用例 | P2 |

---

**文档版本**: v2.1
**创建日期**: 2026-01-24
**最后更新**: 2026-01-24
**状态**: 设计草案

**主要变更**：
- 域命名更新：reference → metadata, signals → features
- 去除 Accessor 层
- 去除子域 Service，只保留域级 QueryService
- 子域能力模块与 Store 同级
- **禁止同层依赖**（域级服务完全独立）
- **Identity 解析统一在应用层**（Port 层）
- 域级服务只接收整数 sid
- **去除 Common 层**

**v2.1 更新**：
- 架构调整：禁止同层依赖
- Identity 解析移至应用层
- 域级服务接口简化（只接收 sid）
- 新增应用层编排示例
