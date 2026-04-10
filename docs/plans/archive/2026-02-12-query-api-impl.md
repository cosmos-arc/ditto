# Query API 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 5 域 19 个 REST API 端点 + 15 个 CLI 查询命令，共享 DataHub Service 层

**Architecture:**
- API 层定义独立的 Pydantic 请求/响应模型
- Convertor 层负责 Model ↔ Service Query 转换
- CLI 复用 API 模型和 Convertor，直接调用 Service

**Tech Stack:** FastAPI, Typer, Pydantic, Polars, orjson

---

## Phase 1: 基础设施

### Task 1: API 公共模型

**Files:**
- Create: `apps/port/src/ditto_port/api/models/__init__.py`
- Create: `apps/port/src/ditto_port/api/models/common.py`
- Test: `apps/port/tests/unit/api/models/test_common_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/models/test_common_unit.py
"""API 公共模型测试."""

from datetime import date

import pytest
from ditto_port.api.models.common import (
    PaginationRequest,
    PaginationResponse,
    APIResponse,
)


class TestPaginationRequest:
    """测试分页请求模型."""

    def test_default_limit(self) -> None:
        """默认 limit 为 100."""
        req = PaginationRequest()
        assert req.limit == 100

    def test_custom_limit(self) -> None:
        """自定义 limit."""
        req = PaginationRequest(limit=500)
        assert req.limit == 500

    def test_limit_min_value(self) -> None:
        """limit 最小值为 1."""
        with pytest.raises(ValueError):
            PaginationRequest(limit=0)

    def test_limit_max_value(self) -> None:
        """limit 最大值为 1000."""
        with pytest.raises(ValueError):
            PaginationRequest(limit=1001)


class TestPaginationResponse:
    """测试分页响应模型."""

    def test_basic_response(self) -> None:
        """基本响应."""
        resp = PaginationResponse(limit=100)
        assert resp.limit == 100


class TestAPIResponse:
    """测试统一 API 响应模型."""

    def test_single_data_response(self) -> None:
        """单数据响应."""
        resp = APIResponse[dict](data={"id": 1})
        assert resp.data == {"id": 1}
        assert resp.pagination is None

    def test_list_data_response(self) -> None:
        """列表数据响应."""
        resp = APIResponse[list](data=[1, 2, 3], pagination=PaginationResponse(limit=100))
        assert resp.data == [1, 2, 3]
        assert resp.pagination is not None
        assert resp.pagination.limit == 100

    def test_empty_data_response(self) -> None:
        """空数据响应."""
        resp = APIResponse[list](data=[])
        assert resp.data == []
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/models/test_common_unit.py -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'ditto_port.api.models'"

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/models/__init__.py
"""API 模型包."""

from ditto_port.api.models.common import (
    APIResponse,
    PaginationRequest,
    PaginationResponse,
)

__all__ = [
    "APIResponse",
    "PaginationRequest",
    "PaginationResponse",
]
```

```python
# apps/port/src/ditto_port/api/models/common.py
"""API 公共模型."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationRequest(BaseModel):
    """分页请求（简化版）."""

    limit: int = Field(default=100, ge=1, le=1000)


class PaginationResponse(BaseModel):
    """分页响应（简化版）."""

    limit: int
    # TODO: 后续迭代支持 cursor, has_more


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应."""

    data: T
    pagination: PaginationResponse | None = None
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/models/test_common_unit.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/models/
git add apps/port/tests/unit/api/models/
git commit -m "feat(api): add common API models (PaginationRequest/Response, APIResponse)"
```

---

### Task 2: API 异常体系

**Files:**
- Create: `apps/port/src/ditto_port/api/errors.py`
- Test: `apps/port/tests/unit/api/test_errors_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/test_errors_unit.py
"""API 异常测试."""

import pytest
from ditto_port.api.errors import (
    APIError,
    DateRangeError,
    RateLimitError,
)


class TestAPIError:
    """测试 API 错误基类."""

    def test_default_values(self) -> None:
        """默认值."""
        exc = APIError()
        assert exc.status_code == 500
        assert exc.code == "INTERNAL_ERROR"
        assert exc.message == "Internal server error"

    def test_custom_message(self) -> None:
        """自定义消息."""
        exc = APIError(message="Custom error")
        assert exc.message == "Custom error"


class TestDateRangeError:
    """测试日期范围错误."""

    def test_error_properties(self) -> None:
        """错误属性."""
        exc = DateRangeError(
            start_date="2024-12-01",
            end_date="2024-01-01",
        )
        assert exc.status_code == 400
        assert exc.code == "INVALID_DATE_RANGE"
        assert "2024-12-01" in exc.message
        assert "2024-01-01" in exc.message


class TestRateLimitError:
    """测试限流错误."""

    def test_error_properties(self) -> None:
        """错误属性."""
        exc = RateLimitError(retry_after=60)
        assert exc.status_code == 429
        assert exc.code == "RATE_LIMIT_EXCEEDED"
        assert exc.retry_after == 60
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/test_errors_unit.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/errors.py
"""API 异常定义."""

from ditto_port.exceptions import DittoException


class APIError(DittoException):
    """API 错误基类."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "Internal server error",
        error_code: str | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code or self.code)
        self.message = message


class DateRangeError(APIError):
    """日期范围错误."""

    status_code = 400
    code = "INVALID_DATE_RANGE"

    def __init__(self, start_date: str, end_date: str) -> None:
        message = f"start_date ({start_date}) cannot be greater than end_date ({end_date})"
        super().__init__(message=message)
        self.start_date = start_date
        self.end_date = end_date


class RateLimitError(APIError):
    """限流错误."""

    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, retry_after: int = 60) -> None:
        message = f"Rate limit exceeded. Retry after {retry_after} seconds."
        super().__init__(message=message)
        self.retry_after = retry_after
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/test_errors_unit.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/errors.py
git add apps/port/tests/unit/api/test_errors_unit.py
git commit -m "feat(api): add API error classes (APIError, DateRangeError, RateLimitError)"
```

---

## Phase 2: Metadata 域

### Task 3: Metadata 模型定义

**Files:**
- Create: `apps/port/src/ditto_port/api/models/metadata.py`
- Test: `apps/port/tests/unit/api/models/test_metadata_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/models/test_metadata_unit.py
"""Metadata 域模型测试."""

from datetime import date

import pytest
from ditto_port.api.models.metadata import (
    AssetClass,
    Instrument,
    InstrumentsRequest,
    InstrumentQueryRequest,
    Industry,
    Calendar,
)


class TestInstrument:
    """测试 Instrument 模型."""

    def test_basic_instrument(self) -> None:
        """基本标的."""
        inst = Instrument(
            instrument_id=1000001,
            ticker="600000",
            name="浦发银行",
            asset_class=AssetClass.stock,
            exchange="sh",
            list_date=date(1999, 11, 10),
            is_active=True,
        )
        assert inst.instrument_id == 1000001
        assert inst.ticker == "600000"
        assert inst.asset_class == AssetClass.stock


class TestAssetClass:
    """测试 AssetClass 枚举."""

    def test_values(self) -> None:
        """枚举值."""
        assert AssetClass.stock.value == "stock"
        assert AssetClass.etf.value == "etf"
        assert AssetClass.index.value == "index"


class TestInstrumentsRequest:
    """测试简单查询请求."""

    def test_get_request(self) -> None:
        """GET 请求参数."""
        req = InstrumentsRequest(
            asset_class=AssetClass.stock,
            exchange="sh",
        )
        assert req.asset_class == AssetClass.stock
        assert req.exchange == "sh"
        assert req.limit == 100


class TestInstrumentQueryRequest:
    """测试复杂查询请求."""

    def test_post_request(self) -> None:
        """POST 请求体."""
        req = InstrumentQueryRequest(
            asset_class=AssetClass.stock,
            exchanges=["sh", "sz"],
            is_active=True,
            asof="2024-06-01",
        )
        assert req.asset_class == AssetClass.stock
        assert req.exchanges == ["sh", "sz"]
        assert req.is_active is True
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/models/test_metadata_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/models/metadata.py
"""Metadata 域 API 模型."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

from ditto_port.api.models.common import PaginationRequest


class AssetClass(str, Enum):
    """资产类别."""

    stock = "stock"
    etf = "etf"
    index = "index"


class Instrument(BaseModel):
    """标的资源."""

    instrument_id: int
    ticker: str
    name: str
    asset_class: AssetClass
    exchange: str
    list_date: date | None = None
    is_active: bool = True


class InstrumentsRequest(PaginationRequest):
    """简单查询请求（GET 参数）."""

    asset_class: AssetClass | None = None
    exchange: str | None = None


class InstrumentQueryRequest(PaginationRequest):
    """复杂查询请求（POST body）."""

    asset_class: AssetClass | None = None
    exchanges: list[str] | None = None
    is_active: bool | None = None
    asof: str | None = None


class Industry(BaseModel):
    """行业资源."""

    industry_id: int
    name: str
    level: int
    parent_id: int | None = None
    is_active: bool = True


class Calendar(BaseModel):
    """交易日历资源."""

    year: int
    trading_days: list[str]
    holidays: list[str] = []
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/models/test_metadata_unit.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/models/metadata.py
git add apps/port/tests/unit/api/models/test_metadata_unit.py
git commit -m "feat(api): add Metadata domain models (Instrument, Industry, Calendar)"
```

---

### Task 4: Metadata Convertor

**Files:**
- Create: `apps/port/src/ditto_port/api/convertors/__init__.py`
- Create: `apps/port/src/ditto_port/api/convertors/metadata_convertor.py`
- Test: `apps/port/tests/unit/api/convertors/test_metadata_convertor_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/convertors/test_metadata_convertor_unit.py
"""Metadata Convertor 测试."""

import polars as pl
import pytest
from datetime import date

from ditto_port.api.models.metadata import (
    AssetClass,
    Instrument,
    InstrumentQueryRequest,
)
from ditto_port.api.convertors.metadata_convertor import MetadataConvertor


class TestMetadataConvertor:
    """测试 Metadata 转换器."""

    def test_to_instrument(self) -> None:
        """测试 DataFrame 行转 Instrument."""
        df = pl.DataFrame({
            "instrument_id": [1000001],
            "ticker": ["600000"],
            "name": ["浦发银行"],
            "asset_class": ["stock"],
            "exchange": ["sh"],
            "list_date": [date(1999, 11, 10)],
            "is_active": [True],
        })

        result = MetadataConvertor.to_instrument(df.row(0, named=True))
        assert result.instrument_id == 1000001
        assert result.ticker == "600000"
        assert result.asset_class == AssetClass.stock

    def test_to_instrument_list(self) -> None:
        """测试 DataFrame 转 Instrument 列表."""
        df = pl.DataFrame({
            "instrument_id": [1000001, 1000002],
            "ticker": ["600000", "600001"],
            "name": ["浦发银行", "邯郸钢铁"],
            "asset_class": ["stock", "stock"],
            "exchange": ["sh", "sh"],
            "list_date": [date(1999, 11, 10), date(1999, 12, 1)],
            "is_active": [True, True],
        })

        result = MetadataConvertor.to_instrument_list(df)
        assert len(result) == 2
        assert result[0].instrument_id == 1000001
        assert result[1].instrument_id == 1000002
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/convertors/test_metadata_convertor_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/convertors/__init__.py
"""Convertor 包."""

from ditto_port.api.convertors.metadata_convertor import MetadataConvertor

__all__ = ["MetadataConvertor"]
```

```python
# apps/port/src/ditto_port/api/convertors/metadata_convertor.py
"""Metadata 域转换器."""

from typing import Any

import polars as pl

from ditto_port.api.models.metadata import (
    AssetClass,
    Instrument,
)


class MetadataConvertor:
    """Metadata 域转换器."""

    @staticmethod
    def to_instrument(row: dict[str, Any]) -> Instrument:
        """将 DataFrame 行转换为 Instrument 模型."""
        return Instrument(
            instrument_id=row["instrument_id"],
            ticker=row["ticker"],
            name=row["name"],
            asset_class=AssetClass(row["asset_class"]),
            exchange=row["exchange"],
            list_date=row.get("list_date"),
            is_active=row.get("is_active", True),
        )

    @staticmethod
    def to_instrument_list(df: pl.DataFrame) -> list[Instrument]:
        """将 DataFrame 转换为 Instrument 列表."""
        if df.is_empty():
            return []
        return [MetadataConvertor.to_instrument(row) for row in df.to_dicts()]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/convertors/test_metadata_convertor_unit.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/convertors/
git add apps/port/tests/unit/api/convertors/
git commit -m "feat(api): add MetadataConvertor for DataFrame to Model conversion"
```

---

### Task 5: Metadata API Router - GET /instruments/{id}

**Files:**
- Modify: `apps/port/src/ditto_port/api/routes/metadata.py`
- Test: `apps/port/tests/integration/api/test_metadata_router_unit.py`

**Step 1: Write the failing test**

```python
# tests/integration/api/test_metadata_router_unit.py
"""Metadata Router 集成测试."""

from unittest.mock import MagicMock
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ditto_port.api.routes.metadata import router, get_metadata_service


@pytest.fixture
def mock_metadata_service() -> MagicMock:
    """Mock MetadataService."""
    return MagicMock()


@pytest.fixture
def client(mock_metadata_service: MagicMock) -> TestClient:
    """创建测试客户端."""
    app = FastAPI()
    app.dependency_overrides[get_metadata_service] = lambda: mock_metadata_service
    app.include_router(router, prefix="/api/v1/metadata")
    return TestClient(app)


class TestGetInstrumentById:
    """测试 GET /instruments/{id}."""

    def test_returns_instrument_when_found(
        self, client: TestClient, mock_metadata_service: MagicMock
    ) -> None:
        """找到标的时返回数据."""
        mock_metadata_service.get_instrument.return_value = {
            "instrument_id": 1000001,
            "ticker": "600000",
            "name": "浦发银行",
            "asset_class": "stock",
            "exchange": "sh",
            "list_date": date(1999, 11, 10),
            "is_active": True,
        }

        response = client.get("/api/v1/metadata/instruments/1000001")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["instrument_id"] == 1000001
        assert data["ticker"] == "600000"
        mock_metadata_service.get_instrument.assert_called_once_with(1000001)

    def test_returns_null_when_not_found(
        self, client: TestClient, mock_metadata_service: MagicMock
    ) -> None:
        """找不到标的时返回 null."""
        mock_metadata_service.get_instrument.return_value = None

        response = client.get("/api/v1/metadata/instruments/9999999")

        assert response.status_code == 200
        assert response.json()["data"] is None
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/integration/api/test_metadata_router_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/routes/metadata.py
"""元数据 API 路由."""

from typing import Any

from fastapi import APIRouter, Depends
from ditto_data.services.metadata_service import MetadataService

from ditto_port.api.models.common import APIResponse
from ditto_port.api.models.metadata import Instrument
from ditto_port.api.convertors.metadata_convertor import MetadataConvertor

router = APIRouter(prefix="/metadata", tags=["metadata"])


def get_metadata_service() -> MetadataService:
    """获取 MetadataService（由 DI 容器注入）."""
    # 实际实现由 dishka 提供
    raise NotImplementedError("DI container should provide MetadataService")


@router.get("/instruments/{instrument_id}", response_model=APIResponse[Instrument | None])
async def get_instrument(
    instrument_id: int,
    service: MetadataService = Depends(get_metadata_service),
) -> APIResponse[Instrument | None]:
    """获取单个标的."""
    result = service.get_instrument(instrument_id)
    if result is None:
        return APIResponse(data=None)

    instrument = MetadataConvertor.to_instrument(result)
    return APIResponse(data=instrument)
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/integration/api/test_metadata_router_unit.py::TestGetInstrumentById -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/routes/metadata.py
git add apps/port/tests/integration/api/test_metadata_router_unit.py
git commit -m "feat(api): implement GET /metadata/instruments/{id} endpoint"
```

---

### Task 6: Metadata API Router - GET /instruments

**Files:**
- Modify: `apps/port/src/ditto_port/api/routes/metadata.py`
- Test: `apps/port/tests/integration/api/test_metadata_router_unit.py`

**Step 1: Write the failing test**

```python
# 添加到 tests/integration/api/test_metadata_router_unit.py

class TestListInstruments:
    """测试 GET /instruments."""

    def test_returns_filtered_list(
        self, client: TestClient, mock_metadata_service: MagicMock
    ) -> None:
        """返回筛选后的列表."""
        import polars as pl
        mock_metadata_service.list_instruments.return_value = pl.DataFrame({
            "instrument_id": [1000001, 1000002],
            "ticker": ["600000", "600001"],
            "name": ["浦发银行", "邯郸钢铁"],
            "asset_class": ["stock", "stock"],
            "exchange": ["sh", "sh"],
            "list_date": [date(1999, 11, 10), date(1999, 12, 1)],
            "is_active": [True, True],
        })

        response = client.get("/api/v1/metadata/instruments?asset_class=stock&exchange=sh")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["ticker"] == "600000"

    def test_returns_empty_list_when_no_match(
        self, client: TestClient, mock_metadata_service: MagicMock
    ) -> None:
        """无匹配时返回空列表."""
        import polars as pl
        mock_metadata_service.list_instruments.return_value = pl.DataFrame()

        response = client.get("/api/v1/metadata/instruments?asset_class=stock")

        assert response.status_code == 200
        assert response.json()["data"] == []
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/integration/api/test_metadata_router_unit.py::TestListInstruments -v
```

**Step 3: Write minimal implementation**

```python
# 添加到 apps/port/src/ditto_port/api/routes/metadata.py

from ditto_port.api.models.metadata import InstrumentsRequest
from ditto_port.api.models.common import PaginationResponse


@router.get("/instruments")
async def list_instruments(
    asset_class: str | None = None,
    exchange: str | None = None,
    limit: int = 100,
    service: MetadataService = Depends(get_metadata_service),
) -> dict[str, Any]:
    """简单查询标的列表."""
    df = service.list_instruments(
        asset_class=asset_class,
        exchange=exchange,
        limit=limit,
    )

    instruments = MetadataConvertor.to_instrument_list(df)
    return {
        "data": [inst.model_dump(mode="json") for inst in instruments],
        "pagination": {"limit": limit},
    }
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/integration/api/test_metadata_router_unit.py::TestListInstruments -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/routes/metadata.py
git add apps/port/tests/integration/api/test_metadata_router_unit.py
git commit -m "feat(api): implement GET /metadata/instruments endpoint"
```

---

## Phase 3: Market 域

### Task 7: Market 模型定义

**Files:**
- Create: `apps/port/src/ditto_port/api/models/market.py`
- Test: `apps/port/tests/unit/api/models/test_market_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/models/test_market_unit.py
"""Market 域模型测试."""

from datetime import date

import pytest
from ditto_port.api.models.market import (
    Adjustment,
    Bar,
    BarsRequest,
    AdjFactor,
    Status,
)


class TestAdjustment:
    """测试复权类型枚举."""

    def test_values(self) -> None:
        """枚举值."""
        assert Adjustment.none.value == "none"
        assert Adjustment.qfq.value == "qfq"
        assert Adjustment.hfq.value == "hfq"


class TestBar:
    """测试 K 线模型."""

    def test_basic_bar(self) -> None:
        """基本 K 线."""
        bar = Bar(
            instrument_id=1000001,
            trade_date=date(2024, 6, 1),
            open=10.5,
            high=10.8,
            low=10.3,
            close=10.6,
            volume=12345678,
            amount=130567890.12,
        )
        assert bar.instrument_id == 1000001
        assert bar.close == 10.6


class TestBarsRequest:
    """测试 K 线查询请求."""

    def test_basic_request(self) -> None:
        """基本请求."""
        req = BarsRequest(
            instrument_ids=[1000001, 1000002],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert req.instrument_ids == [1000001, 1000002]
        assert req.adjustment == Adjustment.none
        assert req.limit == 1000

    def test_with_adjustment(self) -> None:
        """带复权参数."""
        req = BarsRequest(
            instrument_ids=[1000001],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            adjustment=Adjustment.qfq,
        )
        assert req.adjustment == Adjustment.qfq
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/models/test_market_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/models/market.py
"""Market 域 API 模型."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

from ditto_port.api.models.common import PaginationRequest


class Adjustment(str, Enum):
    """复权类型."""

    none = "none"
    qfq = "qfq"
    hfq = "hfq"


class Bar(BaseModel):
    """K 线资源."""

    instrument_id: int
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    turnover_rate: float | None = None


class BarsRequest(PaginationRequest):
    """K 线查询请求."""

    instrument_ids: list[int] = Field(..., min_length=1, max_length=100)
    start_date: date
    end_date: date
    adjustment: Adjustment = Adjustment.none
    limit: int = Field(default=1000, ge=1, le=5000)


class AdjFactor(BaseModel):
    """复权因子资源."""

    instrument_id: int
    trade_date: date
    adj_factor: float


class Status(BaseModel):
    """股票状态资源."""

    instrument_id: int
    trade_date: date
    is_suspended: bool
    is_st: bool
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/models/test_market_unit.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/models/market.py
git add apps/port/tests/unit/api/models/test_market_unit.py
git commit -m "feat(api): add Market domain models (Bar, BarsRequest, AdjFactor, Status)"
```

---

### Task 8: Market Convertor

**Files:**
- Create: `apps/port/src/ditto_port/api/convertors/market_convertor.py`
- Test: `apps/port/tests/unit/api/convertors/test_market_convertor_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/api/convertors/test_market_convertor_unit.py
"""Market Convertor 测试."""

from datetime import date

import polars as pl
import pytest

from ditto_port.api.models.market import Adjustment, BarsRequest, Bar
from ditto_port.api.convertors.market_convertor import MarketConvertor


class TestMarketConvertor:
    """测试 Market 转换器."""

    def test_to_bar(self) -> None:
        """测试 DataFrame 行转 Bar."""
        row = {
            "instrument_id": 1000001,
            "trade_date": date(2024, 6, 1),
            "open": 10.5,
            "high": 10.8,
            "low": 10.3,
            "close": 10.6,
            "volume": 12345678,
            "amount": 130567890.12,
        }

        result = MarketConvertor.to_bar(row)
        assert result.instrument_id == 1000001
        assert result.close == 10.6

    def test_to_bar_list(self) -> None:
        """测试 DataFrame 转 Bar 列表."""
        df = pl.DataFrame({
            "instrument_id": [1000001, 1000001],
            "trade_date": [date(2024, 6, 1), date(2024, 6, 2)],
            "open": [10.5, 10.6],
            "high": [10.8, 10.9],
            "low": [10.3, 10.4],
            "close": [10.6, 10.7],
            "volume": [12345678, 13456789],
            "amount": [130567890.12, 140567890.12],
        })

        result = MarketConvertor.to_bar_list(df)
        assert len(result) == 2
        assert result[0].trade_date == date(2024, 6, 1)
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/convertors/test_market_convertor_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/convertors/market_convertor.py
"""Market 域转换器."""

from typing import Any

import polars as pl

from ditto_port.api.models.market import Bar


class MarketConvertor:
    """Market 域转换器."""

    @staticmethod
    def to_bar(row: dict[str, Any]) -> Bar:
        """将 DataFrame 行转换为 Bar 模型."""
        return Bar(
            instrument_id=row["instrument_id"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            amount=row["amount"],
            turnover_rate=row.get("turnover_rate"),
        )

    @staticmethod
    def to_bar_list(df: pl.DataFrame) -> list[Bar]:
        """将 DataFrame 转换为 Bar 列表."""
        if df.is_empty():
            return []
        return [MarketConvertor.to_bar(row) for row in df.to_dicts()]
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/api/convertors/test_market_convertor_unit.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/convertors/market_convertor.py
git add apps/port/tests/unit/api/convertors/test_market_convertor_unit.py
git commit -m "feat(api): add MarketConvertor for DataFrame to Bar conversion"
```

---

### Task 9: Market API Router - POST /bars

**Files:**
- Modify: `apps/port/src/ditto_port/api/routes/market.py`
- Test: `apps/port/tests/integration/api/test_market_router_unit.py`

**Step 1: Write the failing test**

```python
# tests/integration/api/test_market_router_unit.py
"""Market Router 集成测试."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ditto_port.api.routes.market import router, get_market_service


@pytest.fixture
def mock_market_service() -> MagicMock:
    """Mock MarketService."""
    return MagicMock()


@pytest.fixture
def client(mock_market_service: MagicMock) -> TestClient:
    """创建测试客户端."""
    app = FastAPI()
    app.dependency_overrides[get_market_service] = lambda: mock_market_service
    app.include_router(router, prefix="/api/v1/market")
    return TestClient(app)


class TestQueryBars:
    """测试 POST /bars."""

    def test_returns_bars(
        self, client: TestClient, mock_market_service: MagicMock
    ) -> None:
        """返回 K 线数据."""
        mock_market_service.find_bars.return_value = pl.DataFrame({
            "instrument_id": [1000001],
            "trade_date": [date(2024, 6, 1)],
            "open": [10.5],
            "high": [10.8],
            "low": [10.3],
            "close": [10.6],
            "volume": [12345678],
            "amount": [130567890.12],
        })

        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1000001],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["instrument_id"] == 1000001

    def test_returns_empty_list_when_no_data(
        self, client: TestClient, mock_market_service: MagicMock
    ) -> None:
        """无数据时返回空列表."""
        mock_market_service.find_bars.return_value = pl.DataFrame()

        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [9999999],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_validates_date_range(
        self, client: TestClient, mock_market_service: MagicMock
    ) -> None:
        """验证日期范围."""
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1000001],
                "start_date": "2024-12-01",
                "end_date": "2024-01-01",  # start > end
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_DATE_RANGE"
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/integration/api/test_market_router_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/api/routes/market.py
"""行情数据 API 路由."""

from typing import Any

from fastapi import APIRouter, Depends
from ditto_data.services.market_service import MarketService

from ditto_port.api.errors import DateRangeError
from ditto_port.api.models.market import BarsRequest
from ditto_port.api.convertors.market_convertor import MarketConvertor

router = APIRouter(prefix="/market", tags=["market"])


def get_market_service() -> MarketService:
    """获取 MarketService（由 DI 容器注入）."""
    raise NotImplementedError("DI container should provide MarketService")


@router.post("/bars")
async def query_bars(
    request: BarsRequest,
    service: MarketService = Depends(get_market_service),
) -> dict[str, Any]:
    """查询 K 线数据."""
    # 日期校验
    if request.start_date > request.end_date:
        raise DateRangeError(
            start_date=request.start_date.isoformat(),
            end_date=request.end_date.isoformat(),
        )

    # 调用 Service（需要根据实际 Service 接口调整）
    df = service.find_bars(
        instrument_ids=request.instrument_ids,
        start_date=request.start_date.isoformat(),
        end_date=request.end_date.isoformat(),
        adjustment=request.adjustment.value,
        limit=request.limit,
    )

    bars = MarketConvertor.to_bar_list(df)
    return {
        "data": [bar.model_dump(mode="json") for bar in bars],
        "pagination": {"limit": request.limit},
    }
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/integration/api/test_market_router_unit.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/api/routes/market.py
git add apps/port/tests/integration/api/test_market_router_unit.py
git commit -m "feat(api): implement POST /market/bars endpoint with date validation"
```

---

## Phase 4-6: Fundamental, Capital, Macro 域

**注：** 由于篇幅限制，Fundamental、Capital、Macro 域遵循相同的模式：
1. 定义模型（`api/models/{domain}.py`）
2. 定义转换器（`api/convertors/{domain}_convertor.py`）
3. 实现路由（`api/routes/{domain}.py`）
4. 编写测试

每个域的任务结构相同，此处省略重复模式。

---

## Phase 7: CLI 查询命令

### Task 10: CLI Query 命令组注册

**Files:**
- Create: `apps/port/src/ditto_port/cli/commands/query/__init__.py`
- Modify: `apps/port/src/ditto_port/cli/main.py`
- Test: `apps/port/tests/unit/cli/commands/test_query_unit.py`

**Step 1: Write the failing test**

```python
# tests/unit/cli/commands/test_query_unit.py
"""CLI query 命令测试."""

from typer.testing import CliRunner
from ditto_port.cli.main import app

runner = CliRunner()


class TestQueryCommandGroup:
    """测试 query 命令组."""

    def test_query_help(self) -> None:
        """query 命令帮助信息."""
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "metadata" in result.output
        assert "market" in result.output

    def test_query_metadata_help(self) -> None:
        """query metadata 命令帮助."""
        result = runner.invoke(app, ["query", "metadata", "--help"])
        assert result.exit_code == 0
        assert "instruments" in result.output
```

**Step 2: Run test to verify it fails**

```bash
pixi run -e dev pytest apps/port/tests/unit/cli/commands/test_query_unit.py -v
```

**Step 3: Write minimal implementation**

```python
# apps/port/src/ditto_port/cli/commands/query/__init__.py
"""CLI query 命令组."""

import typer

from ditto_port.cli.commands.query import metadata, market

app = typer.Typer(
    name="query",
    help="数据查询命令",
    no_args_is_help=True,
)

app.add_typer(metadata.app, name="metadata")
app.add_typer(market.app, name="market")
```

```python
# apps/port/src/ditto_port/cli/commands/query/metadata.py
"""Metadata 查询命令."""

import typer

app = typer.Typer(
    name="metadata",
    help="元数据查询",
    no_args_is_help=True,
)


@app.command("instruments")
def query_instruments(
    id: int | None = typer.Option(None, "--id", help="标的ID"),
    asset_class: str | None = typer.Option(None, "--asset-class", help="资产类别"),
    exchange: str | None = typer.Option(None, "--exchange", help="交易所"),
    limit: int = typer.Option(100, "--limit"),
    compact: bool = typer.Option(False, "--compact", help="紧凑输出"),
) -> None:
    """查询标的信息."""
    # TODO: 实现查询逻辑
    typer.echo('{"data": [], "pagination": {"limit": 100}}')
```

```python
# apps/port/src/ditto_port/cli/commands/query/market.py
"""Market 查询命令."""

import typer

app = typer.Typer(
    name="market",
    help="行情数据查询",
    no_args_is_help=True,
)


@app.command("bars")
def query_bars(
    ids: str = typer.Option(..., "--ids", help="标的ID列表（逗号分隔）"),
    start: str = typer.Option(..., "--start", help="开始日期"),
    end: str = typer.Option(..., "--end", help="结束日期"),
    adj: str = typer.Option("none", "--adj", help="复权方式"),
    limit: int = typer.Option(1000, "--limit"),
    compact: bool = typer.Option(False, "--compact"),
) -> None:
    """查询 K 线数据."""
    # TODO: 实现查询逻辑
    typer.echo('{"data": [], "pagination": {"limit": 1000}}')
```

```python
# 修改 apps/port/src/ditto_port/cli/main.py
# 添加:
from ditto_port.cli.commands.query import app as query_app
# ...
app.add_typer(query_app, name="query")
```

**Step 4: Run test to verify it passes**

```bash
pixi run -e dev pytest apps/port/tests/unit/cli/commands/test_query_unit.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/cli/commands/query/
git add apps/port/src/ditto_port/cli/main.py
git add apps/port/tests/unit/cli/commands/test_query_unit.py
git commit -m "feat(cli): add query command group with metadata and market subcommands"
```

---

## 实施总结

### 文件清单

**新增文件（~25 个）：**
```
apps/port/src/ditto_port/api/
├── models/
│   ├── __init__.py
│   ├── common.py
│   ├── metadata.py
│   ├── market.py
│   ├── fundamental.py
│   ├── capital.py
│   └── macro.py
├── convertors/
│   ├── __init__.py
│   ├── metadata_convertor.py
│   ├── market_convertor.py
│   ├── fundamental_convertor.py
│   ├── capital_convertor.py
│   └── macro_convertor.py
└── errors.py

apps/port/src/ditto_port/cli/commands/query/
├── __init__.py
├── metadata.py
├── market.py
├── fundamental.py
├── capital.py
└── macro.py

apps/port/tests/unit/api/
├── models/test_*.py
├── convertors/test_*.py
└── test_errors_unit.py

apps/port/tests/integration/api/
├── test_metadata_router_unit.py
├── test_market_router_unit.py
├── test_fundamental_router_unit.py
├── test_capital_router_unit.py
└── test_macro_router_unit.py

apps/port/tests/unit/cli/commands/
└── test_query_unit.py
```

**修改文件（~5 个）：**
- `apps/port/src/ditto_port/api/routes/metadata.py`
- `apps/port/src/ditto_port/api/routes/market.py`
- `apps/port/src/ditto_port/api/routes/fundamental.py` (新增)
- `apps/port/src/ditto_port/api/routes/capital.py` (新增)
- `apps/port/src/ditto_port/api/routes/macro.py` (新增)
- `apps/port/src/ditto_port/cli/main.py`

### 估算工作量

| Phase | 任务数 | 估算时间 |
|-------|--------|----------|
| Phase 1: 基础设施 | 2 | 2h |
| Phase 2: Metadata | 4 | 4h |
| Phase 3: Market | 3 | 3h |
| Phase 4: Fundamental | 3 | 3h |
| Phase 5: Capital | 3 | 3h |
| Phase 6: Macro | 3 | 3h |
| Phase 7: CLI | 1+ | 2h |
| **总计** | ~19 | ~20h |

### 依赖关系

```
Task 1 (common models) ─┬─► Task 3 (metadata models)
                        │
Task 2 (errors) ────────┼─► Task 5 (metadata router) ─► Task 10 (CLI)
                        │
                        └─► Task 7 (market models) ─► Task 9 (market router)

Task 3 ─► Task 4 (metadata convertor) ─► Task 5
Task 7 ─► Task 8 (market convertor) ─► Task 9

# Fundamental/Capital/Macro 域遵循相同模式
```
