# ADR-017: 因子服务 API

**状态**: 已决策（2026-03-05）

---

## 背景

因子服务需要为多类调用方提供统一的 API：
- **Port Flow/Task** - 每日调度触发物化
- **CLI 命令** - 手动触发
- **研究环境** - Jupyter 交互式查询
- **外部系统** - 交易系统实时查询

---

## API 设计决策

| 决策点 | 选择 | 理由 |
|-------|------|------|
| **API 风格** | 声明式 | 更简洁，系统自动处理幂等/重试 |
| **物化执行** | 异步优先 | 物化耗时较长，立即返回 run_id |
| **执行后端** | Prefect | 复用现有依赖，生产就绪 |
| **查询格式** | 窄表优先（long） | 适合存储/传输，多因子可选宽表 |
| **认证** | 不需要 | 内网环境 |
| **API 版本** | 不版本化 | 保持与现有一致 |

---

## API 端点路径

```
/derived/
├── specs/                 # Spec 管理
│   ├── GET    /                      # 列出所有
│   ├── POST   /                      # 注册
│   ├── GET    /{entity_id}           # 详情
│   ├── GET    /{entity_id}/lineage   # 依赖
│   └── DELETE /{entity_id}           # 停用
│
├── runs/                  # 运行管理
│   ├── GET    /                      # 列出
│   ├── GET    /{run_id}              # 状态
│   ├── POST   /{run_id}/cancel       # 取消
│   └── GET    /{run_id}/wait         # 等待(SSE)
│
├── materialize/           # 物化操作
│   ├── POST   /                      # 单因子
│   └── POST   /batch                 # 批量
│
└── data/                  # 数据查询
    ├── POST   /query                 # 查询
    ├── GET    /watermark             # Watermark
    └── GET    /coverage              # 覆盖
```

---

## 目录结构

```
apps/port/src/ditto_port/
├── api/routes/derived.py      # 🆕 REST API 路由
├── models/derived.py          # 🆕 Pydantic 模型
└── cli/commands/materialize/  # 🆕 CLI 命令

packages/core/src/ditto_core/
└── derived/                   # 🆕 核心模块
    ├── service.py             # DerivedService
    ├── catalog/               # Catalog 存储
    ├── expression/            # 表达式引擎
    └── materialize/           # 物化逻辑（Prefect tasks）
```

---

## 核心 API 定义

### 管理 API

```python
class DerivedService:
    def register_spec(request: SpecRegisterRequest) -> SpecInfo
    def list_specs(entity_type, is_active) -> list[SpecInfo]
    def get_spec(entity_id) -> SpecInfo | None
    def get_lineage(entity_id) -> LineageInfo
    def deactivate_spec(entity_id) -> None
```

### 物化 API（异步优先）

```python
class DerivedService:
    def materialize(request: MaterializeRequest) -> MaterializeSubmitResult
    def materialize_batch(entity_ids, mode) -> list[MaterializeSubmitResult]
    def get_run(run_id) -> RunInfo | None
    def list_runs(entity_id, status, limit) -> list[RunInfo]
    def cancel_run(run_id) -> None
    def wait_for_run(run_id, timeout) -> RunInfo  # 阻塞等待
```

### 查询 API

```python
class DerivedService:
    def find(query: DerivedQuery) -> pl.DataFrame
    def get_watermark(entity_id) -> str | None
    def get_coverage(entity_id) -> CoverageInfo | None
```

---

## 请求/响应模型

```python
# Spec 注册
class SpecRegisterRequest(BaseModel):
    entity_type: Literal["feature", "factor"]
    entity_id: str
    expression: str
    description: str | None = None
    tags: list[str] | None = None

# 物化请求
class MaterializeRequest(BaseModel):
    entity_id: str
    mode: Literal["incremental", "full"] = "incremental"
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False
    force: bool = False
    callback_url: str | None = None

# 数据查询
class DataQueryRequest(BaseModel):
    entity_ids: list[str] | None = None
    start: str | None = None
    end: str | None = None
    as_of: str | None = None
    instruments: list[str] | None = None
    format: Literal["long", "wide"] = "long"  # 默认窄表
    limit: int = 10000
    offset: int = 0
```

---

## Prefect Flow 集成

```python
@flow(name="materialize_factor")
def materialize_flow(
    entity_id: str,
    mode: Literal["incremental", "full"] = "incremental",
    start_date: str | None = None,
    end_date: str | None = None,
) -> MaterializeResult:
    """物化 Flow（Prefect 编排）"""
    # 1. 验证依赖
    deps = validate_dependencies(entity_id)
    # 2. 计算范围
    compute_start, compute_end = compute_incremental_range(entity_id, mode)
    # 3. 加载数据
    df = load_source_data(deps, compute_start, compute_end)
    # 4. 执行计算
    result_df = execute_expression(df, spec.expression)
    # 5. 写入分区
    partitions = write_partitions(result_df, entity_id)
    # 6. 更新 Catalog
    update_catalog(entity_id, run_id, partitions, compute_end)
    return MaterializeResult(...)
```

---

## REST API 路由示例

```python
# apps/port/src/ditto_port/api/routes/derived.py

router = APIRouter(prefix="/derived", tags=["derived"])

@router.post("/materialize", response_model=MaterializeSubmitResponse, status_code=202)
@inject
async def materialize(
    request: MaterializeRequest,
    service: Annotated[DerivedService, FromComponent()],
):
    """提交物化任务（异步）"""
    return await asyncio.to_thread(service.materialize, request)

@router.get("/runs/{run_id}", response_model=RunResponse)
@inject
async def get_run(
    run_id: str,
    service: Annotated[DerivedService, FromComponent()],
):
    """查询任务状态"""
    run = await asyncio.to_thread(service.get_run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
```

---

## 盘中查询 API 路径

> 详见 [ADR-030: Online Data Access Boundary](adr-030-online-data-access-boundary.md)

### 在线因子查询服务

```python
class OnlineFactorQueryService:
    """盘中因子查询服务（Parquet 隔离）"""

    def __init__(self, runtime_mode: RuntimeMode = RuntimeMode.ONLINE):
        self.runtime_mode = runtime_mode

    async def get_latest_values(
        self,
        factor_id: str,
        instrument_ids: list[str],
    ) -> dict[str, float]:
        """获取最新因子值（只走热层）"""
        if self.runtime_mode == RuntimeMode.ONLINE:
            # ONLINE 模式：只从 Kvrocks 读取
            return await self._kvrocks_reader.get_latest_values(factor_id, instrument_ids)
        else:
            # DEGRADED/OFFLINE 模式：允许 Parquet 回退
            return await self._read_with_fallback(factor_id, instrument_ids)

    async def get_time_series(
        self,
        factor_id: str,
        instrument_id: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """获取时间序列"""
        if self.runtime_mode == RuntimeMode.ONLINE:
            # ONLINE 模式：只从 QuestDB 读取
            return await self._questdb_reader.read_factor_series(
                factor_id, instrument_id, start, end
            )
        else:
            # DEGRADED/OFFLINE 模式：允许 Parquet 回退
            return await self._read_with_fallback_series(factor_id, instrument_id, start, end)
```

### RuntimeMode 检查

```python
# API 路由中注入 RuntimeMode
@router.get("/data/query")
@inject
async def query_factor_data(
    request: DataQueryRequest,
    query_service: Annotated[OnlineFactorQueryService, FromComponent()],
):
    """查询因子数据（自动检查 RuntimeMode）"""
    # 服务内部会根据 RuntimeMode 决定是否允许 Parquet 访问
    return await query_service.get_time_series(
        request.factor_id,
        request.instrument_id,
        request.start,
        request.end,
    )
```

### 运行时模式管理 API

```python
@router.post("/runtime/degrade", dependencies=[Depends(require_admin)])
async def degrade_mode(reason: str) -> dict:
    """切换到降级模式（需管理员权限）"""
    manager = get_runtime_mode_manager()
    await manager.switch_mode(
        target_mode=RuntimeMode.DEGRADED,
        reason=reason,
        operator="api",
    )
    return {"status": "degraded", "reason": reason}

@router.post("/runtime/restore", dependencies=[Depends(require_admin)])
async def restore_mode() -> dict:
    """恢复到在线模式（需管理员权限）"""
    manager = get_runtime_mode_manager()
    await manager.switch_mode(
        target_mode=RuntimeMode.ONLINE,
        reason="Manual restore",
        operator="api",
    )
    return {"status": "online"}
```
