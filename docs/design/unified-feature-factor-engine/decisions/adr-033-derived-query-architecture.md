# ADR-033: 派生查询架构与 Port/DataHub 层边界

**状态**: ✅ 已决策（2026-03-12）

---

## 背景

 `DerivedSpec` 定义了统一的派生语义模型，现在需要定义 Port Facade 和 DataHub Service 之间的精确边界，确保：
1. Port 层职责清晰（用例组装、参数整形、权限控制、返回模型转换)
2. DataHub 层职责清晰(source routing、版本/发布/as_of/source_scope、存储实现)
3. 层间依赖方向正确(Port → DataHub → Reader/Writer)

本 ADR 依赖 ADR-032 (DerivedSpec 语义模型) 和 ADR-030 (Online Data Access Boundary)。

---

## 决策记录

### D-1: Facade 模式与方法签名

| 属性 | 值 |
|------|------|
| **Facade 类** | 单一 `DerivedQueryFacade` |
| **公开方法** | 按用例拆分： `get_latest()`, `get_series()`, `compare_sources()` |
| **RuntimeMode** | 由 Facade 内部通过 `RuntimeModeResolver` 解析，不暴露给调用方 |
| **理由** | RuntimeMode 是运行边界策略而非业务参数； 三种独立 Facade 在返回模型/权限/SLA 未明显分叉时不增加复杂度 |

**代码示例**:
```python
@dataclass(frozen=True)
class LatestDerivedRequest:
    """Latest 埥询请求（服务场景）。"""
    derived_ids: list[str]
    instrument_ids: list[int]
    asof: datetime | None = None


@dataclass(frozen=True)
class SeriesDerivedRequest:
    """时间序列查询请求（研究/API 场景）。"""
    derived_ids: list[str]
    instrument_ids: list[int] | None = None
    start: date | datetime | None = None
    end: date | datetime | None = None
    asof: date | datetime | None = None
    universe_id: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class SourceCompareRequest:
    """多源对比请求（审计场景）。"""
    derived_ids: list[str]
    instrument_ids: list[int]
    start: date
    end: date
    compare_sources: tuple[str, ...] = ("serving", "offline")  # 默认对比热层与冷层


@dataclass(frozen=True)
class DerivedLatestResult:
    """Latest 查询结果。"""
    data: pl.DataFrame


@dataclass(frozen=True)
class DerivedSeriesResult:
    """时间序列查询结果。"""
    data: pl.DataFrame


@dataclass(frozen=True)
class DerivedCompareResult:
    """多源对比结果。"""
    data: pl.DataFrame


class DerivedQueryFacade:
    """派生查询 Facade - 按用例拆分公开方法。"""

    def __init__(
        self,
        service: DerivedQueryService,
        mode_resolver: RuntimeModeResolver,
    ):
        self._service = service
        self._mode_resolver = mode_resolver

    def get_latest(self, request: LatestDerivedRequest) -> DerivedLatestResult:
        """获取最新值 - 服务场景，ONLINE 模式强制走热层。"""
        mode = self._mode_resolver.resolve()
        # ONLINE 模式强制走 QuestDB/Kvrocks
        return DerivedLatestResult(
            data=self._service.find_latest(
                derived_ids=request.derived_ids,
                instrument_ids=request.instrument_ids,
                asof=request.asof,
            )
        )

    def get_series(self, request: SeriesDerivedRequest) -> DerivedSeriesResult:
        """获取时间序列 - 研究/API 场景。"""
        mode = self._mode_resolver.resolve()
        return DerivedSeriesResult(
            data=self._service.find_series(
                derived_ids=request.derived_ids,
                instrument_ids=request.instrument_ids,
                start=request.start,
                end=request.end,
                asof=request.asof,
            )
        )

    def compare_sources(
        self, request: SourceCompareRequest
    ) -> DerivedCompareResult:
        """多源对比 - 审计场景,DEGRADED 模式允许 Parquet。"""
        # 审计场景强制使用 DEGRADED 模式
        mode = RuntimeMode.DEGRADED
        return DerivedCompareResult(
            data=self._service.compare_sources(
                derived_ids=request.derived_ids,
                instrument_ids=request.instrument_ids,
                start=request.start,
                end=request.end,
                compare_sources=request.compare_sources,
            )
        )
```

**设计要点**:
1. **RuntimeMode 封装**: Facade 内部通过 `RuntimeModeResolver` 解析运行模式，API/CLI/jobs 不感知 RuntimeMode
2. **方法语义明确**: `get_latest()` 对应服务场景， `get_series()` 对应研究场景, `compare_sources()` 对应审计场景
3. **返回类型统一**: 所有数据查询方法返回 `pl.DataFrame`

---

### D-2: DataHub 返回类型

| 属性 | 值 |
|------|------|
| **查询类方法** | 统一返回 `pl.DataFrame` |
| **状态/治理类方法** | 返回标量或小型结构体 |
| **列模式固定** | 必须文档化，保证接口契约稳定性 |

**代码示例**:
```python
class DerivedQueryService:
    """派生查询服务 - DataHub 层实现。"""

    def find_series(
        self,
        derived_ids: list[str],
        instrument_ids: list[int] | None,
        start: date | datetime | None,
        end: date | datetime | None,
        asof: date | datetime | None,
    ) -> pl.DataFrame:
        """查询时间序列数据。

        返回列: derived_id, instrument_id, trade_date, bar_time?, value, asof_ts, version
        """
        ...

    def find_latest(
        self,
        derived_ids: list[str],
        instrument_ids: list[int],
        asof: datetime | None = None,
    ) -> pl.DataFrame:
        """查询最新数据。

        返回列: derived_id, instrument_id, value, trade_date, bar_time?, asof_ts, version
        """
        ...

    def compare_sources(
        self,
        derived_ids: list[str],
        instrument_ids: list[int],
        start: date,
        end: date,
        compare_sources: tuple[str, ...] = ("serving", "offline"),
    ) -> pl.DataFrame:
        """对比多个数据源。

        返回列: derived_id, instrument_id, trade_date, serving_value, offline_value, diff
        """
        ...

    def get_watermark(self, derived_id: str) -> str | None:
        """获取水位线 - 返回 ISO 格式日期字符串。"""
        ...

    def get_coverage(self, derived_id: str) -> CoverageInfo | None:
        """获取覆盖范围 - 返回小型结构体。 """
        ...

@dataclass(frozen=True)
class CoverageInfo:
    """覆盖范围信息。"""
    coverage_start: date
    coverage_end: date
    total_rows: int
    null_rate: float
```

**列模式规范**:

| 方法 | 返回列 |
|------|--------|
| `find_series` | `derived_id`, `instrument_id`, `trade_date`, `bar_time?`, `value`, `asof_ts`, `version` |
| `find_latest` | `derived_id`, `instrument_id`, `value`, `trade_date`, `bar_time?`, `asof_ts`, `version` |
| `compare_sources` | `derived_id`, `instrument_id`, `trade_date`, `serving_value`, `offline_value`, `diff` |

---

### D-3: Query DTO 归属

| 属性 | 值 |
|------|------|
| **位置** | DataHub 层定义 |
| **理由** | 与现有 `FeatureQuery`/`FactorQuery` 风格一致； Port 层通过请求模型传入参数 |
| **命名** | `DerivedSeriesQuery`, `DerivedLatestQuery`, `DerivedCompareQuery` |

---

### D-4: 同步/异步风格

| 属性 | 值 |
|------|------|
| **DataHub 服务** | 统一同步方法 |
| **Port Facade** | 同步接口 |
| **理由** | 与现有 DataHub 服务风格一致； 无明确异步需求时保持简单 |

**代码示例**:
```python
# DataHub 层 - 同步
class DerivedQueryService:
    def find_series(self, ...) -> pl.DataFrame:  # 同步
    def find_latest(self, ...) -> pl.DataFrame:  # 同步

# Port 层 - 同步
class DerivedQueryFacade:
    def get_series(self, ...) -> DerivedSeriesResult:  # 同步
    def get_latest(self, ...) -> DerivedLatestResult:  # 同步

# API 层 - 如需异步可用 asyncio 包装
@router.get("/derived/series")
async def get_series_endpoint(request: SeriesDerivedRequest):
    """API 端点可用 asyncio 包装同步方法。"""
    facade = get_facade()
    result = await asyncio.to_thread(
        lambda: facade.get_series(request)
    )
    return result
```

---

### D-5: 研究数据集构建不并入 `DerivedQueryFacade`

| 属性 | 值 |
|------|------|
| **是否纳入当前 Facade** | 否 |
| **原因** | 研究数据集构建需要 `SpineSpec`、`known_at`、`DatasetSnapshot`、coverage report 等额外契约，不是普通查询 |
| **边界** | `DerivedQueryFacade` 只承担 latest / series / compare 等查询能力；dataset build 走独立 facade/service |

**边界说明**：

1. `get_series()` 可用于研究时的单次 PIT 提取或分析查询，但不负责保存训练数据集快照。
2. 训练/回测数据集构建需要显式传入 `SpineSpec` / `ResearchDatasetSpec`，并产出 `DatasetSnapshot`。
3. 若后续需要 Port API，应新增 `ResearchDatasetFacade` 或同级入口，而不是继续膨胀 `DerivedQueryFacade`。

---

## 影响范围

| 层级 | 变更 |
|------|------|
| **DataHub** | 新增 `DerivedQueryService`；研究数据集后续新增独立 build service |
| **Port** | 新增 `DerivedQueryFacade`；研究数据集后续新增独立 facade |
| **API** | 无需变更，通过 Facade 暴露新方法 |
| **CLI** | 无需变更，通过 Facade 暴露新方法 |

---

## 文件结构
```
packages/data/src/ditto_data/
  services/
    derived/
      __init__.py
      query_service.py      # DerivedQueryService
      dtos/
        __init__.py
        queries.py              # DerivedSeriesQuery, etc.
        results.py              # CoverageInfo

apps/port/src/ditto_port/
  facades/
    derived/
      __init__.py
      query_facade.py          # DerivedQueryFacade
      dtos/
        __init__.py
        requests.py             # LatestDerivedRequest, etc.
        results.py             # DerivedLatestResult, etc.
```

---

## 与其他 ADR 的关系
- **依赖**: ADR-032 (DerivedSpec 语义模型)
- **依赖**: ADR-030 (Online Data Access Boundary)
- **相关**: ADR-017 (Service Layer API)
- **相关**: ADR-024 (Factor Versioning)
- **扩展**: ADR-041 (Research Dataset / Spine / Availability-Time)

---

## 更新记录

### 2026-03-12

- 创建 ADR
- 决策 D-1: Facade 模式 - 单一 Facade + 按用例拆分方法 + RuntimeMode 内部解析
- 决策 D-2: DataHub 返回类型 - 查询类统一 pl.DataFrame，状态/治理类返回标量或小型结构体
- 决策 D-3: Query DTO 归属 - 放在 DataHub 层
- 决策 D-4: 同步/异步风格 - 统一同步风格
- 决策 D-5: 研究数据集构建不并入 `DerivedQueryFacade`，后续独立建模
- **ADR 完成**: P0-2 Port/DataHub 接口契约已决策
