# DataHub Port 层重构实施计划

> **注意:** 本阶段不在三域重构范围内。
>
> **三域重构范围:** Metadata、Market、Capital 三个域（DataHub 包内）。
>
> **最新实施计划:** 参见 [2026-01-29-datahub-three-domain-refactor-implementation.md](./2026-01-29-datahub-three-domain-refactor-implementation.md)
>
> **说明:** Port 层属于应用层（apps/port），不在 DataHub 三域重构范围内。本计划文档保留用于未来实施参考。

---

## 原始计划（保留用于参考）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 重构 Port 层，实现 SourceService、IngestionService、DataService、Writer、ReconciliationService

**架构:**
- 在 `apps/port/src/ditto_port/services/` 中实现服务编排
- Port 层负责 Identity 解析、跨域编排、业务流程组合
- 数据摄入、数据查询、质量对账等功能

**技术栈:** Python 3.12+, Polars, Pydantic, FastAPI, Prefect, Pyright Strict

**前置依赖:** Phase 0-8 所有域级重构

---

## 目录结构

```
apps/port/src/ditto_port/services/
├── __init__.py
├── source_service.py           # 编排 Source + Enrichment
├── ingestion_service.py         # 数据摄入流程
├── data_service.py              # 数据查询和编排
├── writer.py                    # 统一写入入口
├── reconciliation_service.py    # 质量对账
└── strategy_service.py          # 策略服务 (可选)
```

---

## 任务 1: 实现 SourceService

**职责:**
- 编排外部数据源 (Tushare、TDX 等)
- 编排数据增强 (Identity 解析、Symbol 添加)
- 统一的数据获取接口

**文件:**
- 新建: `apps/port/src/ditto_port/services/source_service.py`

**接口设计:**

```python
class SourceService:
    """数据源服务 - 统一数据获取和增强入口."""

    def fetch_stock_daily(
        self,
        src_codes: list[str],
        start_date: str,
        end_date: str,
        source: str = "tushare",
    ) -> pl.DataFrame:
        """
        获取股票日线数据并增强。

        自动解析 SID、添加 symbol 列。

        """

    def fetch_etf_daily(
        self,
        src_codes: list[str],
        start_date: str,
        end_date: str,
        source: str = "tushare",
    ) -> pl.DataFrame:
        """获取 ETF 日线数据并增强."""

    def fetch_index_daily(
        self,
        src_codes: list[str],
        start_date: str,
        end_date: str,
        source: str = "tushare",
    ) -> pl.DataFrame:
        """获取指数日线数据并增强."""
```

---

## 任务 2: 实现 Writer

**职责:**
- 统一的数据写入入口
- 自动路由到正确的域和 Store
- 支持批量写入和事务管理

**文件:**
- 新建: `apps/port/src/ditto_port/services/writer.py`

**接口设计:**

```python
class Writer:
    """统一写入入口."""

    def write_market_data(
        self,
        df: pl.DataFrame,
        dataset: str,
        source: str = "tushare",
    ) -> WriteResult:
        """
        写入市场数据。

        自动路由到正确的域和 Store。

        """

    def write_metadata(
        self,
        df: pl.DataFrame,
        dataset: str,
        source: str = "tushare",
    ) -> WriteResult:
        """写入元数据."""

    def write_fundamental_data(
        self,
        df: pl.DataFrame,
        dataset: str,
        source: str = "tushare",
    ) -> WriteResult:
        """写入基本面数据."""
```

---

## 任务 3: 实现 IngestionService

**职责:**
- 编排完整的数据摄入流程
- 数据质量检查
- 数据写入
- 摄入日志记录

**文件:**
- 新建: `apps/port/src/ditto_port/services/ingestion_service.py`

**接口设计:**

```python
class IngestionService:
    """数据摄入服务."""

    def ingest_stock_daily(
        self,
        trade_date: str,
        source: str = "tushare",
    ) -> IngestionResult:
        """
        摄入股票日线数据。

        流程:
        1. 获取活跃证券列表
        2. 调用 SourceService 获取数据
        3. DQ 检查
        4. 写入数据
        5. 记录摄入日志

        """

    def ingest_etf_daily(
        self,
        trade_date: str,
        source: str = "tushare",
    ) -> IngestionResult:
        """摄入 ETF 日线数据."""

    def ingest_index_daily(
        self,
        trade_date: str,
        source: str = "tushare",
    ) -> IngestionResult:
        """摄入指数日线数据."""
```

---

## 任务 4: 实现 DataService

**职责:**
- 编排跨域查询
- 提供 Port 层的便捷 API
- 支持复杂查询场景

**文件:**
- 新建: `apps/port/src/ditto_port/services/data_service.py`

**接口设计:**

```python
class DataService:
    """数据查询服务 - Port 层便捷 API."""

    def get_stock_bars_with_all(
        self,
        identifiers: list[str],
        start: str,
        end: str,
        adj: Literal["none", "qfq", "hfq"] = "none",
        with_status: bool = True,
        with_industry: bool = False,
    ) -> pl.DataFrame:
        """
        获取股票 K线，包含所有增强信息。

        编排:
        1. Metadata 域解析 SID
        2. Market 域获取 K线
        3. 合并状态、行业等信息

        """

    def get_stock_with_fundamental(
        self,
        identifiers: list[str],
        report_date: str,
    ) -> pl.DataFrame:
        """
        获取股票基本面数据.

        编排:
        1. Metadata 域解析 SID
        2. Fundamental 域获取财务数据
        3. 合并结果

        """
```

---

## 任务 5: 实现 ReconciliationService

**职责:**
- 跨源质量对账
- 数据一致性检查
- 对账报告生成

**文件:**
- 新建: `apps/port/src/ditto_port/services/reconciliation_service.py`

**接口设计:**

```python
class ReconciliationService:
    """质量对账服务."""

    def reconcile_sources(
        self,
        dataset: str,
        date: str,
        source_a: str = "tushare",
        source_b: str = "tdx",
    ) -> ReconciliationReport:
        """
        跨源对账。

        比较两个数据源的数据差异。

        """

    def check_data_completeness(
        self,
        dataset: str,
        date: str,
        expected_count: int,
    ) -> CompletenessReport:
        """
        检查数据完整性。

        """

    def generate_reconciliation_report(
        self,
        start_date: str,
        end_date: str,
    ) -> ReconciliationReport:
        """
        生成对账报告。

        """
```

---

## 任务 6: 更新 API 路由

**文件:**
- 修改: `apps/port/src/ditto_port/api/routes.py`

**变更:**
- 使用新的 Service 层
- 更新路由处理器

---

## 任务 7: 清理和文档更新

**文件:**
- 删除: `apps/port/src/ditto_port/services/` 中的旧服务
- 更新: `apps/port/README.md`

---

## 任务 8: 创建 Git Tag

```bash
git tag -a datahub-phase9-port-complete -m "完成 Port 层重构"
git push origin datahub-phase9-port-complete
```

---

## 验收标准

- [ ] SourceService 实现完整
- [ ] Writer 实现完整
- [ ] IngestionService 实现完整
- [ ] DataService 实现完整
- [ ] ReconciliationService 实现完整
- [ ] API 路由更新完成
- [ ] 测试覆盖率 ≥ 80%
- [ ] 所有代码检查通过

---

## 预计时间

- SourceService: 2 天
- Writer: 1 天
- IngestionService: 3 天
- DataService: 2 天
- ReconciliationService: 2 天
- API 更新 + 测试: 2 天

**总计: 约 12 个工作日**
