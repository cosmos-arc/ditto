---
name: fastapi-guide
description: |
  【必读】FastAPI 开发指南。
  触发条件: FastAPI、Router、API、接口、endpoint、route、Pydantic、BaseModel、Depends、HTTPException、REST。
  核心规则: 三层架构 Router→Service→Engine、依赖注入、Pydantic 校验。
globs:
  - "**/api/**/*.py"
  - "**/routers/**/*.py"
---

# FastAPI 开发指南

## 分层架构

```
Router (api/)      ← 参数校验、路由
    ↓
Service (services/) ← 业务编排
    ↓
Engine/Repository  ← 核心计算、数据访问
```

---

## Router 模板

```python
router = APIRouter(prefix="/backtest", tags=["Backtest"])

@router.post("", response_model=BacktestResponse)
async def run_backtest(
    request: BacktestRequest,
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestResponse:
    result = await service.run(request.to_params())
    return BacktestResponse.from_result(result)
```

---

## Pydantic Models

```python
class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="策略名称")
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if v <= info.data.get("start_date"):
            raise ValueError("end_date must be after start_date")
        return v
```

---

## 依赖注入

```python
@lru_cache
def get_service() -> BacktestService:
    return BacktestService()

BacktestServiceDep = Annotated[BacktestService, Depends(get_service)]
```

---

## 错误处理

```python
class DittoError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

@app.exception_handler(DittoError)
async def handle_error(request, exc):
    return JSONResponse(
        status_code=400,
        content={"code": exc.code, "message": exc.message}
    )
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| Router 写业务逻辑 | 放 Service |
| 直接操作数据库 | 通过 Repository |
| 返回内部对象 | 定义 Response Model |
