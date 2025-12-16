---
paths: apps/server/**/*.py
---

# FastAPI 规范

> HTTP API 层，提供 RESTful 接口

## 项目结构

```
apps/server/src/ditto_server/
├── main.py              # 应用入口
├── api/                 # HTTP Routers（薄层）
│   ├── __init__.py
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── backtest.py
│   │   ├── portfolio.py
│   │   └── system.py
│   └── deps.py          # 依赖注入
├── services/            # 业务逻辑层
│   ├── __init__.py
│   ├── backtest_service.py
│   └── portfolio_service.py
├── models/              # Pydantic Models
│   ├── __init__.py
│   ├── requests.py
│   └── responses.py
└── scheduler/           # 定时任务
    ├── __init__.py
    └── jobs.py
```

## 分层职责

```
┌─────────────────────────────────────┐
│  Router (api/)                      │  ← 参数校验、路由、响应格式化
│  - 接收请求                          │     薄层，不包含业务逻辑
│  - 调用 Service                      │
│  - 返回响应                          │
├─────────────────────────────────────┤
│  Service (services/)                │  ← 业务编排
│  - 业务逻辑                          │     可被多个 Router 复用
│  - 调用 Engine/Repository           │     可独立测试
├─────────────────────────────────────┤
│  Engine/Repository (packages/core)  │  ← 核心计算、数据访问
│  - 纯业务计算                        │     与 HTTP 无关
│  - 数据库操作                        │
└─────────────────────────────────────┘
```

## Router 规范

### 基本结构

```python
# api/v1/backtest.py
from fastapi import APIRouter, Depends, HTTPException, status

from ditto_server.models.requests import BacktestRequest
from ditto_server.models.responses import BacktestResponse
from ditto_server.services.backtest_service import BacktestService
from ditto_server.api.deps import get_backtest_service

router = APIRouter(prefix="/backtest", tags=["Backtest"])


@router.post(
    "",
    response_model=BacktestResponse,
    summary="运行回测",
    description="根据指定参数运行策略回测",
)
async def run_backtest(
    request: BacktestRequest,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestResponse:
    """
    运行回测任务。

    - **strategy**: 策略名称
    - **start_date**: 回测开始日期
    - **end_date**: 回测结束日期
    """
    result = await service.run(request.to_params())
    return BacktestResponse.from_result(result)


@router.get(
    "/{backtest_id}",
    response_model=BacktestResponse,
)
async def get_backtest(
    backtest_id: int,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestResponse:
    result = await service.get(backtest_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest {backtest_id} not found",
        )
    return BacktestResponse.from_result(result)
```

### Router 注册

```python
# api/v1/__init__.py
from fastapi import APIRouter

from .backtest import router as backtest_router
from .portfolio import router as portfolio_router
from .system import router as system_router

router = APIRouter(prefix="/api/v1")
router.include_router(backtest_router)
router.include_router(portfolio_router)
router.include_router(system_router)


# main.py
from fastapi import FastAPI
from ditto_server.api.v1 import router as v1_router

app = FastAPI(
    title="Ditto Trading API",
    version="0.1.0",
)
app.include_router(v1_router)
```

## Pydantic Models

### Request Models

```python
# models/requests.py
from datetime import date
from pydantic import BaseModel, Field, field_validator


class BacktestRequest(BaseModel):
    """回测请求参数"""

    strategy: str = Field(..., description="策略名称", examples=["etf_rotation"])
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    initial_capital: float = Field(
        default=1_000_000,
        ge=10_000,
        description="初始资金",
    )

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v

    def to_params(self) -> "BacktestParams":
        """转换为内部参数对象"""
        from ditto_core.backtest import BacktestParams
        return BacktestParams(
            strategy=self.strategy,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
        )


class PaginationParams(BaseModel):
    """分页参数"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
```

### Response Models

```python
# models/responses.py
from datetime import date, datetime
from pydantic import BaseModel, Field


class BacktestResult(BaseModel):
    """回测结果明细"""

    date: date
    portfolio_value: float
    daily_return: float
    cumulative_return: float
    drawdown: float


class BacktestResponse(BaseModel):
    """回测响应"""

    id: int
    strategy: str
    start_date: date
    end_date: date
    total_return: float = Field(..., description="总收益率")
    annual_return: float = Field(..., description="年化收益率")
    max_drawdown: float = Field(..., description="最大回撤")
    sharpe_ratio: float = Field(..., description="夏普比率")
    results: list[BacktestResult]
    created_at: datetime

    @classmethod
    def from_result(cls, result: "InternalBacktestResult") -> "BacktestResponse":
        """从内部结果对象构造响应"""
        return cls(
            id=result.id,
            strategy=result.strategy,
            start_date=result.start_date,
            end_date=result.end_date,
            total_return=result.total_return,
            annual_return=result.annual_return,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
            results=[
                BacktestResult(
                    date=r.date,
                    portfolio_value=r.portfolio_value,
                    daily_return=r.daily_return,
                    cumulative_return=r.cumulative_return,
                    drawdown=r.drawdown,
                )
                for r in result.daily_results
            ],
            created_at=result.created_at,
        )


class ErrorResponse(BaseModel):
    """错误响应"""

    code: str
    message: str
    details: dict | None = None


class PaginatedResponse(BaseModel):
    """分页响应基类"""

    total: int
    page: int
    page_size: int
    items: list
```

## 依赖注入

```python
# api/deps.py
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from ditto_server.services.backtest_service import BacktestService
from ditto_server.services.portfolio_service import PortfolioService
from ditto_core.data import DataService


@lru_cache
def get_data_service() -> DataService:
    """数据服务单例"""
    return DataService()


@lru_cache
def get_backtest_service() -> BacktestService:
    """回测服务单例"""
    return BacktestService(data_service=get_data_service())


@lru_cache
def get_portfolio_service() -> PortfolioService:
    """组合服务单例"""
    return PortfolioService(data_service=get_data_service())


# 类型别名，简化注入
BacktestServiceDep = Annotated[BacktestService, Depends(get_backtest_service)]
PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]


# Router 中使用
@router.post("")
async def run_backtest(
    request: BacktestRequest,
    service: BacktestServiceDep,
) -> BacktestResponse:
    ...
```

## 错误处理

### 自定义异常

```python
# exceptions.py
class DittoError(Exception):
    """基础异常"""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(DittoError):
    """资源未找到"""

    def __init__(self, resource: str, id: int | str):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} with id {id} not found",
            details={"resource": resource, "id": id},
        )


class ValidationError(DittoError):
    """验证错误"""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details={"field": field} if field else None,
        )


class KillSwitchError(DittoError):
    """Kill Switch 触发"""

    def __init__(self, level: int, reason: str):
        super().__init__(
            code="KILL_SWITCH_ACTIVE",
            message=f"Kill switch level {level} is active: {reason}",
            details={"level": level, "reason": reason},
        )
```

### 异常处理器

```python
# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ditto_server.exceptions import DittoError, NotFoundError, KillSwitchError

app = FastAPI()


@app.exception_handler(DittoError)
async def handle_ditto_error(request: Request, exc: DittoError) -> JSONResponse:
    status_code = 400
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, KillSwitchError):
        status_code = 503  # Service Unavailable

    return JSONResponse(
        status_code=status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # 生产环境不暴露内部错误
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
        },
    )
```

## Service 规范

```python
# services/backtest_service.py
from datetime import date

from ditto_core.backtest import BacktestEngine, BacktestParams, BacktestResult
from ditto_core.data import DataService


class BacktestService:
    """回测服务：编排回测流程"""

    def __init__(self, data_service: DataService):
        self._data_service = data_service
        self._engine = BacktestEngine()

    async def run(self, params: BacktestParams) -> BacktestResult:
        """运行回测"""
        # 1. 获取数据
        prices = await self._data_service.get_prices(
            start_date=params.start_date,
            end_date=params.end_date,
        )

        # 2. 执行回测
        result = self._engine.run(prices, params)

        # 3. 保存结果
        result_id = await self._save_result(result)
        result.id = result_id

        return result

    async def get(self, backtest_id: int) -> BacktestResult | None:
        """获取回测结果"""
        return await self._data_service.get_backtest_result(backtest_id)

    async def _save_result(self, result: BacktestResult) -> int:
        """保存回测结果到数据库"""
        return await self._data_service.save_backtest_result(result)
```

## 中间件

```python
# middleware.py
import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start_time
        logger.info(
            "%s %s %d %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )

        return response


# main.py
app.add_middleware(RequestLoggingMiddleware)
```

## API 版本控制

```python
# 当前版本
/api/v1/backtest

# 破坏性变更时创建新版本
/api/v2/backtest

# Router 组织
api/
├── v1/
│   ├── __init__.py
│   └── backtest.py
└── v2/
    ├── __init__.py
    └── backtest.py  # 新版本
```

## 测试

```python
# tests/api/test_backtest.py
import pytest
from fastapi.testclient import TestClient

from ditto_server.main import app
from ditto_server.api.deps import get_backtest_service


class MockBacktestService:
    async def run(self, params):
        return MockResult(...)


@pytest.fixture
def client():
    app.dependency_overrides[get_backtest_service] = lambda: MockBacktestService()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_run_backtest(client):
    response = client.post(
        "/api/v1/backtest",
        json={
            "strategy": "etf_rotation",
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "total_return" in data
    assert "max_drawdown" in data


def test_backtest_validation_error(client):
    response = client.post(
        "/api/v1/backtest",
        json={
            "strategy": "etf_rotation",
            "start_date": "2024-06-30",
            "end_date": "2024-01-01",  # end < start
        },
    )

    assert response.status_code == 422  # Validation error
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| Router 中写业务逻辑 | 职责不清 | 放到 Service |
| 直接操作数据库 | 耦合 | 通过 Service/Repository |
| 硬编码配置 | 不可配置 | 环境变量或配置文件 |
| 忽略异常处理 | 用户体验差 | 统一异常处理器 |
| 返回内部对象 | 泄露实现 | 定义 Response Model |
| 同步阻塞操作 | 性能差 | 用 async 或后台任务 |
