# DataHub Capital 域实施计划

> **状态:** ❌ 未实现
> **最新实施计划:** 参见 [2026-01-29-datahub-three-domain-refactor-implementation.md](./2026-01-29-datahub-three-domain-refactor-implementation.md)
>
> **重要说明:**
> - 本文档已完全重写，反映最新的三域架构设计
> - Capital 域定位：财务与公司基本面数据
> - 支持完整的 PIT（Point-in-Time）查询能力

---

## 域定位

### Capital 域 vs 原 Phase 3

| 项目 | 原 Phase 3 | 新 Capital 域 |
|------|-----------|--------------|
| 数据类型 | flow, margin, top_board, limit_board, chip | 财务报表、估值指标、衍生品等 |
| PIT 支持 | 无 | 完整支持 |
| 命名 | sid | instrument_id |
| 架构 | 独立 | 三域架构之一 |

### 三域关系

```
┌─────────────────────────────────────────────────────┐
│                    Application                      │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────┬─────────────┬─────────────────────────┐
│  Metadata   │   Market    │       Capital            │
│  (元数据)    │  (市场数据)   │      (财务数据)           │
│             │             │                         │
│ - instrument │ - bars      │ - balance_sheet         │
│ - industry  │ - status    │ - income_statement       │
│ - calendar  │ - adj_factor│ - cash_flow             │
│             │             │ - valuation_metrics      │
│             │             │ - derivatives            │
│             │             │ - index_composition      │
│             │             │ - corporate_actions      │
└─────────────┴─────────────┴─────────────────────────┘
```

---

## 数据类型清单

### 1. 财务报表数据 (PIT)

| 数据类型 | PIT 需求 | 优先级 | 说明 |
|---------|---------|-------|------|
| Balance Sheet | ✅ | P0 | 资产负债表 |
| Income Statement | ✅ | P0 | 利润表 |
| Cash Flow | ✅ | P0 | 现金流量表 |

### 2. 估值指标数据 (PIT)

| 数据类型 | PIT 需求 | 优先级 | 说明 |
|---------|---------|-------|------|
| Valuation Metrics | ✅ | P0 | PE、PB、PS、股息率等 |

### 3. 衍生品数据 (PIT)

| 数据类型 | PIT 需求 | 优先级 | 说明 |
|---------|---------|-------|------|
| Futures (期货) | ✅ | P0 | 股指期货数据 |
| Options (期权) | ✅ | P1 | 股票期权数据 |

### 4. 成分股数据 (PIT)

| 数据类型 | PIT 需求 | 优先级 | 说明 |
|---------|---------|-------|------|
| Index Composition | ✅ | P1 | 指数成分股及权重 |
| Dividend (股息分红) | ✅ | **P0 (新增)** | 分红数据 |
| Margin Trading (融资融券) | ✅ | **P0 (新增)** | 融资融券数据 |
| Pledge Ratio (股权质押) | ✅ | **P0 (新增)** | 股权质押数据 |

### 5. 公司行为 (非 PIT)

| 数据类型 | PIT 需求 | 优先级 | 说明 |
|---------|---------|-------|------|
| Corporate Actions | ❌ | P1 | 分红、拆股、并购等 |

**总计: 10 个数据类型**

---

## 目录结构

```
packages/datahub/src/ditto_datahub/domains/capital/
├── __init__.py
├── financial/
│   ├── balance_sheet_store.py       # 资产负债表
│   ├── income_statement_store.py    # 利润表
│   └── cash_flow_store.py           # 现金流量表
├── valuation/
│   └── valuation_metrics_store.py   # 估值指标
├── derivatives/
│   ├── futures_store.py             # 期货数据
│   └── options_store.py             # 期权数据
├── composition/
│   ├── index_member_store.py        # 指数成分股（PIT）
│   ├── dividend_store.py            # 股息分红（PIT）
│   ├── margin_trading_store.py      # 融资融券（PIT）
│   └── pledge_ratio_store.py        # 股权质押（PIT）
├── corporate_actions/
│   └── corporate_actions_store.py   # 公司行为
└── capital_query_service.py         # 域级查询服务
```

---

## SourceSchema 定义

### Balance Sheet SourceSchema

```python
BALANCE_SHEET_SOURCE_SCHEMA = SourceSchema(
    dataset="balance_sheet",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date | None,
        "total_assets": pl.Float64,
        "total_liabilities": pl.Float64,
        "net_assets": pl.Float64,
        "current_assets": pl.Float64,
        "current_liabilities": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to")
)
```

### Income Statement SourceSchema

```python
INCOME_STATEMENT_SOURCE_SCHEMA = SourceSchema(
    dataset="income_statement",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date | None,
        "revenue": pl.Float64,
        "operating_profit": pl.Float64,
        "net_profit": pl.Float64,
        "eps": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to")
)
```

### Valuation Metrics SourceSchema

```python
VALUATION_METRICS_SOURCE_SCHEMA = SourceSchema(
    dataset="valuation_metrics",
    key_columns=("instrument_id", "trade_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date | None,
        "pe_ratio": pl.Float64,
        "pb_ratio": pl.Float64,
        "ps_ratio": pl.Float64,
        "dividend_yield": pl.Float64,
        "market_cap": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to")
)
```

---

## PIT 实现模式

### Store 层 PIT 查询

```python
class CapitalStore(SQLiteStore):
    """Capital 域 Store 基类"""

    def _build_pit_query(
        self,
        table: str,
        instrument_id: str,
        as_of_date: date,
    ) -> tuple[str, list]:
        """构建 PIT 查询 SQL

        返回满足以下条件的记录：
        - effective_from <= as_of_date
        - (effective_to IS NULL OR effective_to > as_of_date)
        """
        sql = f"""
            SELECT * FROM {table}
            WHERE instrument_id = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY effective_from DESC
        """
        return sql, [instrument_id, as_of_date, as_of_date]

    def get_balance_sheet(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """查询指定日期的有效资产负债表"""
        sql, params = self._build_pit_query(
            "balance_sheet", instrument_id, as_of_date
        )
        rows = self.fetchall(sql, params)
        return pl.DataFrame(rows) if rows else pl.DataFrame()
```

### Source 层 PIT 处理

```python
class CapitalTushareAdapter(BaseTushareAdapter):
    """Capital 域 Tushare 适配器"""

    def fetch_balance_sheet(
        self,
        report_date: str,
    ) -> pl.DataFrame:
        """获取资产负债表数据

        Returns:
            DataFrame with PIT columns:
            - report_date: 报告期
            - knowledge_date: 数据可知日期
            - effective_from: 生效开始（默认为发布日期）
            - effective_to: 生效结束（默认为 NULL）
        """
        response = self._client.query(
            api_name="balancesheet",
            period=report_date,
        )

        # 转换为 SourceSchema 格式
        df = TushareDataTransformer.transform(
            response,
            "balance_sheet",
            BALANCE_SHEET_MAPPING,
        )

        # 添加 PIT 列
        df = df.with_columns([
            pl.lit(report_date).str.to_date().alias("report_date"),
            pl.lit(pl.Date.today()).alias("knowledge_date"),
            pl.col("ann_date").str.to_date().alias("effective_from"),
            pl.lit(None, dtype=pl.Date).alias("effective_to"),
        ])

        return df
```

---

## Ingestion 层

### CapitalIngestion

```python
class CapitalIngestion:
    """Capital 域数据摄入服务"""

    def __init__(
        self,
        source: CapitalSource,
        store: CapitalStore,
        writer: IngestionDataWriter,
    ) -> None:
        self._source = source
        self._store = store
        self._writer = writer

    async def ingest_balance_sheet(
        self,
        trade_date: str,
    ) -> IngestionResult:
        """摄入资产负债表数据"""
        # 1. 从 Source 获取数据（SourceSchema 格式）
        df = await self._source.fetch_balance_sheet(trade_date)

        # 2. 验证 SourceSchema
        BALANCE_SHEET_SOURCE_SCHEMA.validate(df)

        # 3. 转换为 StoreSchema
        store_df = self._transform_to_store_schema(df)

        # 4. 写入 Store（PIT 模式）
        return await self._writer.write_pit_data(
            store=self._store,
            table="balance_sheet",
            data=store_df,
        )
```

---

## 验收标准

### 功能验收

- [ ] 10 个数据类型全部实现
- [ ] PIT 查询功能正常
- [ ] SourceSchema 验证通过
- [ ] CapitalIngestion 完整实现
- [ ] CapitalQueryService 提供统一查询接口

### 测试验收

- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试覆盖 PIT 场景
- [ ] 真实 Tushare API 测试

### 文档验收

- [ ] API 文档完整
- [ ] PIT 查询示例
- [ ] 数据字典

---

## 预计时间

**总计: 约 2 周**

- Week 1: Source 层（SourceSchema + 10 个数据类型）
- Week 2: Store 层（PIT 支持）+ Ingestion 层

---

## 依赖关系

### 前置依赖

- Stage 0: SourceSchema 基础设施
- Phase 0: 基础层（SQLiteStore, DataRootConfig）
- Phase 1: Metadata 域（instrument 解析）

### 后续依赖

无（Capital 域是最后一个域）

---

## 原 Phase 3 文档（已废弃）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 实现完整的 Capital 域，支持资金流向、融资融券、龙虎榜、打板、筹码分布等数据

**架构:**
- 创建 `domains/capital/` 目录
- 按数据类型组织：flow、margin、top_board、limit_board、chip
- 实现 CapitalQueryService 作为域级统一入口

**技术栈:** Python 3.12+, Polars, Pydantic, Pyright Strict

**前置依赖:** Phase 0 - 基础层重构, Phase 2 - Market 域重构

**注意:** 原 Phase 3 的数据类型（flow, margin, top_board, limit_board, chip）已不在新 Capital 域范围内。如需这些数据，请单独规划。
