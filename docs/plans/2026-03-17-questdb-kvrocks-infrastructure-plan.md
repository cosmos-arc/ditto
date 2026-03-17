# QuestDB + Kvrocks 基础设施实施计划

**创建日期**: 2026-03-17
**前序**: ADR-011/023/027/028/029/030/031/040 设计文档已完成
**目标**: 从设计到落地，建立盘中热层数据基础设施

---

## 整改目标

| 维度 | 当前 | Phase 1 | Phase 2 | Phase 3 |
|------|------|---------|---------|---------|
| **部署环境** | 无 | Docker Compose 就绪 | DDL 自动创建 | 完整拓扑 |
| **依赖引入** | 无 | questdb + redis 客户端 | - | - |
| **连接基础设施** | 无 | infra 客户端 + 健康检查 | 生产实现 | - |
| **Protocol 实现** | Unavailable 占位 | InMemory/Fake | QuestDB/Kvrocks Real | - |
| **数据读写** | 无 | Fake 读写 | ILP 写入 + SQL 查询 | 集成到流水线 |
| **Pushdown** | 无 | - | - | 时间序列算子下推 |
| **测试** | - | Testcontainers 集成 | 协议实现测试 | 端到端测试 |

---

## 核心约束

| 约束项 | 内容 |
|--------|------|
| 分层 | `infra`（连接池）→ `datahub`（业务实现）→ `core`（语义定义） |
| 部署 | Docker Compose 开发/测试，Testcontainers 集成测试 |
| 测试 | Fake/InMemory 单元测试 + Testcontainers 真实实例集成测试 |
| 向后兼容 | 不需要，直接实现 |
| ADR 对齐 | 所有实现必须符合 ADR-028/031/040 的 DDL、Key 模式和 TTL 策略 |

---

## Phase 总览

| Phase | 名称 | 核心目标 | 依赖 | 预估 |
|-------|------|----------|------|------|
| **Phase 1** | 连接层 + 配置 + 部署 + Fake | 基础设施就绪，DI 可注入 | 无 | Week 1-2 |
| **Phase 2** | 协议实现 + 数据读写 | 3 个 Protocol 生产版本 | Phase 1 | Week 3-4 |
| **Phase 3** | 集成到流水线 + 盘中模式 | 端到端盘中因子计算 | Phase 2 | Week 5-7 |

---

## Phase 1: 连接层 + 配置 + 部署 + Fake

### 目标

建立基础设施骨架，不实现任何业务逻辑。开发环境一键启动，DI 可根据配置选择 Real 或 Fake 实现。

### 1.1 Docker Compose 服务定义

**文件**: `docker-compose.dev.yml`

```yaml
services:
  questdb:
    image: questdb/questdb:latest
    ports:
      - "9000:9000"   # HTTP/PG
      - "9009:9009"   # ILP
      - "8812:8812"   # PG Wire
    volumes:
      - questdb_data:/root/.questdb
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/status"]
      interval: 5s
      timeout: 3s
      retries: 10

  kvrocks:
    image: apache/kvrocks:latest
    ports:
      - "6666:6666"
    command: kvrocks --bind 0.0.0.0 --port 6666
    volumes:
      - kvrocks_data:/var/lib/kvrocks
    healthcheck:
      test: ["CMD", "redis-cli", "-p", "6666", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  questdb_data:
  kvrocks_data:
```

**配置文件**:

| 文件 | 内容 |
|------|------|
| `config/development/questdb.env` | `QUESTDB_HOST=localhost`, `QUESTDB_ILP_PORT=9009`, `QUESTDB_PG_PORT=8812` |
| `config/development/kvrocks.env` | `KVROCKS_HOST=localhost`, `KVROCKS_PORT=6666` |
| `config/testing/questdb.env` | Testcontainers 自动注入，无需配置文件 |
| `config/testing/kvrocks.env` | Testcontainers 自动注入，无需配置文件 |

### 1.2 pixi.toml 依赖

```toml
[pypi-dependencies]
# 新增
questdb = ">=3.0"
redis = { version = ">=5.0", extras = ["hiredis"] }

# 测试依赖
[feature.dev.dependencies]
testcontainers = ">=4.0"
```

**选型说明**:
- `questdb`: 官方 Python 客户端，提供 `ingress.Sender`（ILP 写入）和 HTTP/PG 查询
- `redis[hiredis]`: Kvrocks 兼容 Redis 协议，`redis.asyncio` 提供异步连接池
- `testcontainers`: 启动真实容器进行集成测试

### 1.3 Pydantic 配置模型

**文件**: `packages/datahub/src/ditto_datahub/settings.py`（扩展）

```python
@dataclass(frozen=True)
class QuestDBSettings:
    """QuestDB connection settings."""
    host: str = "localhost"
    ilp_port: int = 9009
    pg_port: int = 8812
    enabled: bool = False  # 是否启用真实连接（否则使用 Fake）

@dataclass(frozen=True)
class KvrocksSettings:
    """Kvrocks connection settings."""
    host: str = "localhost"
    port: int = 6666
    password: str | None = None
    db: int = 0
    enabled: bool = False  # 是否启用真实连接（否则使用 Fake）
```

**优先级**: 环境变量 > `.env` 文件 > 默认值（与现有 `DataSourceSettings` 一致）

### 1.4 infra 连接客户端

**文件**: `packages/infra/src/ditto_infra/clients/`

```
clients/
├── __init__.py
├── questdb.py      # QuestDBClient
└── kvrocks.py      # KvrocksClient
```

**QuestDBClient**:

```python
class QuestDBClient:
    """QuestDB 连接客户端。

    封装 ILP Sender（写入）和 HTTP/PG 连接（查询），
    提供统一的生命周期管理和健康检查。
    """

    def __init__(self, settings: QuestDBSettings) -> None: ...

    @property
    def is_available(self) -> bool: ...

    async def health_check(self) -> bool: ...

    async def flush(self) -> None:
        """刷新 ILP buffer。"""
        ...

    async def execute_query(self, sql: str, params: dict | None = None) -> pl.DataFrame:
        """执行查询并返回 Polars DataFrame。"""
        ...

    async def close(self) -> None: ...
```

**KvrocksClient**:

```python
class KvrocksClient:
    """Kvrocks 连接客户端（Redis 协议兼容）。

    封装 redis.asyncio 连接池，提供健康检查和生命周期管理。
    """

    def __init__(self, settings: KvrocksSettings) -> None: ...

    @property
    def is_available(self) -> bool: ...

    async def health_check(self) -> bool: ...

    @property
    def redis(self) -> redis.asyncio.Redis:
        """底层 Redis 客户端，供业务层使用。"""
        ...

    async def close(self) -> None: ...
```

### 1.5 Fake/InMemory 实现

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/`

```
hot_layer/
├── __init__.py           # Protocol 定义（已有）+ re-export
├── in_memory_reader.py   # InMemoryHotLayerReader
├── in_memory_writer.py   # InMemoryHotLayerWriter
└── in_memory_store.py    # InMemoryStateStore
```

**InMemoryHotLayerReader**:
- `is_available()` → 始终返回 `True`
- `read_latest()` → 从内存字典读取
- 支持写入（测试用）

**InMemoryStateStore**:
- `get()` / `set()` → 内存字典
- 支持 TTL 模拟（可选）

### 1.6 DI Provider 注册

**文件**: `apps/port/src/ditto_port/registry/datahub/hot_layer.py`（新增）

```python
class HotLayerProvider(SingletonScope):
    """热层基础设施 Provider。"""

    @provide
    def questdb_client(self, settings: QuestDBSettings) -> QuestDBClient: ...

    @provide
    def kvrocks_client(self, settings: KvrocksSettings) -> KvrocksClient: ...

    @provide
    def hot_layer_reader(self, ...) -> HotLayerReader:
        """根据 enabled 配置选择 Real 或 InMemory 实现。"""
        if settings.questdb.enabled:
            return QuestDBReader(questdb_client)
        return InMemoryHotLayerReader()

    @provide
    def hot_layer_writer(self, ...) -> HotLayerWriter: ...

    @provide
    def state_store(self, ...) -> StateStore:
        """根据 enabled 配置选择 Real 或 InMemory 实现。"""
        if settings.kvrocks.enabled:
            return KvrocksStore(kvrocks_client)
        return InMemoryStateStore()
```

### 1.7 Testcontainers 工具

**文件**: `packages/infra/tests/conftest.py`

```python
@pytest.fixture(scope="session")
def questdb_container():
    """启动 QuestDB 容器，返回连接参数。"""
    with QuestDBContainer("questdb/questdb:latest") as container:
        yield container

@pytest.fixture(scope="session")
def kvrocks_container():
    """启动 Kvrocks 容器，返回连接参数。"""
    with KvrocksContainer("apache/kvrocks:latest") as container:
        yield container
```

### Phase 1 验收标准

| 检查项 | 标准 |
|--------|------|
| Docker Compose | `docker compose -f docker-compose.dev.yml up` 两个服务健康检查通过 |
| 健康检查 | `QuestDBClient.health_check()` 和 `KvrocksClient.health_check()` 返回 True |
| DI 注入 | `HotLayerProvider` 根据 `enabled` 配置正确注入 Real/Fake |
| Fake 实现 | `InMemoryHotLayerReader`、`InMemoryStateStore` 通过单元测试 |
| Testcontainers | 集成测试可启动真实容器并执行健康检查 |
| 类型检查 | 0 errors |
| 测试 | 全部通过 |

---

## Phase 2: 协议实现 + 数据读写

### 目标

实现 3 个 Protocol 的 QuestDB/Kvrocks 生产版本，支持热表 DDL 自动创建和基础读写。

### 2.1 QuestDB DDL 管理

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/questdb_ddl.py`

```python
QUESTDB_DDL = [
    # bar_1m_hot（ADR-028）
    "CREATE TABLE IF NOT EXISTS bar_1m_hot (...)",
    "ALTER TABLE bar_1m_hot SET TTL 5 DAYS",
    # f_1m_hot（ADR-028）
    "CREATE TABLE IF NOT EXISTS f_1m_hot (...)",
    "ALTER TABLE f_1m_hot SET TTL 5 DAYS",
    # 物化视图
    "CREATE MATERIALIZED VIEW IF NOT EXISTS bar_5m_mv AS ...",
    "CREATE MATERIALIZED VIEW IF NOT EXISTS bar_15m_mv AS ...",
    "CREATE MATERIALIZED VIEW IF NOT EXISTS bar_60m_mv AS ...",
]

class QuestDBDDLManager:
    """管理 QuestDB 热表 DDL 创建。"""

    async def ensure_tables(self, client: QuestDBClient) -> None:
        """确保所有热表和物化视图已创建。"""
        ...

    async def verify_tables(self, client: QuestDBClient) -> list[str]:
        """验证表是否存在，返回缺失的表名。"""
        ...
```

### 2.2 QuestDBReader 实现

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/questdb_reader.py`

```python
class QuestDBReader:
    """HotLayerReader 的 QuestDB 实现（ADR-028/030）。"""

    def __init__(self, client: QuestDBClient) -> None:
        self._client = client

    def is_available(self) -> bool:
        return self._client.is_available

    def read_latest(
        self,
        *,
        derived_id: str,
        instrument_ids: tuple[int, ...] | None,
        as_of: str | None,
    ) -> pl.DataFrame:
        """从 QuestDB 查询最新因子值（f_1m_hot）。"""
        sql = """
            SELECT * FROM f_1m_hot
            WHERE factor_id = :factor_id
              AND ts <= :as_of
            ORDER BY ts DESC
            LIMIT 1
        """
        ...
```

### 2.3 QuestDBWriter 实现

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/questdb_writer.py`

```python
class QuestDBWriter:
    """HotLayerWriter 的 QuestDB 实现（ADR-028 ILP 写入）。"""

    def __init__(self, client: QuestDBClient) -> None:
        self._client = client

    def write_frame(
        self,
        *,
        derived_id: str,
        version: int,
        frame: pl.DataFrame,
    ) -> int:
        """通过 ILP 批量写入因子值到 f_1m_hot。"""
        # frame → ILP row 格式转换
        # 调用 client.sender.row()
        # 返回写入行数
        ...
```

### 2.4 KvrocksStore 实现

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/kvrocks_store.py`

```python
class KvrocksStore:
    """StateStore 的 Kvrocks 实现（ADR-031/040）。"""

    def __init__(self, client: KvrocksClient) -> None:
        self._client = client

    def get(self, key: str) -> bytes | None:
        raw = self._client.redis.get(key)
        return raw if raw else None

    def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: int | None = None,
    ) -> None:
        self._client.redis.set(key, value, ex=ttl_seconds)

    # --- ADR-031 专用方法 ---

    def write_hash_snapshot(
        self,
        *,
        factor_id: str,
        instrument_id: str,
        value: float,
        ts: datetime,
        trade_date: date,
        calc_ver: int,
    ) -> None:
        """写入 HASH 模式快照（ADR-031）。"""
        key = f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        self._client.redis.hset(key, mapping={
            "v": str(value),
            "ts": ts.isoformat(),
            "td": trade_date.isoformat(),
            "ver": str(calc_ver),
        })

    def read_hash_snapshot(
        self,
        *,
        factor_id: str,
        instrument_id: str,
    ) -> dict | None:
        """读取 HASH 模式快照。"""
        key = f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        data = self._client.redis.hgetall(key)
        if not data:
            return None
        return {
            "value": float(data[b"v"]),
            "ts": data[b"ts"].decode(),
            "trade_date": data[b"td"].decode(),
            "calc_ver": int(data[b"ver"]),
        }

    def write_blob_snapshot(
        self,
        *,
        factor_id: str,
        instrument_id: str,
        data: dict,
        ts: datetime,
        trade_date: date,
        calc_ver: int,
        schema_ver: int = 1,
    ) -> None:
        """写入 BLOB 模式快照（ADR-031）。"""
        key = f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        blob = orjson.dumps({
            "schema_ver": schema_ver,
            "factor_id": factor_id,
            "instrument_id": instrument_id,
            "serve_mode": "STATE",
            "ts": ts.isoformat(),
            "trade_date": trade_date.isoformat(),
            "calc_ver": calc_ver,
            "data": data,
        })
        self._client.redis.set(key, blob, ex=7 * 24 * 3600)  # 7 天 TTL

    def read_blob_snapshot(
        self,
        *,
        factor_id: str,
        instrument_id: str,
    ) -> dict | None:
        """读取 BLOB 模式快照。"""
        key = f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        raw = self._client.redis.get(key)
        if not raw:
            return None
        return orjson.loads(raw)

    def batch_read_snapshots(
        self,
        *,
        factor_id: str,
        instrument_ids: list[str],
    ) -> dict[str, dict | None]:
        """批量读取快照（Pipeline 优化）。"""
        pipe = self._client.redis.pipeline(transaction=False)
        for sid in instrument_ids:
            key = f"ditto:derived:state:factor:{factor_id}:snapshot:{sid}"
            pipe.hgetall(key)
        results = pipe.execute()
        return {
            sid: self._parse_hash(data) if data else None
            for sid, data in zip(instrument_ids, results)
        }

    def clear_factor_snapshots(self, factor_id: str) -> int:
        """清除某个因子的所有快照（SCAN + DELETE）。"""
        pattern = f"ditto:derived:state:factor:{factor_id}:snapshot:*"
        keys = list(self._client.redis.scan_iter(match=pattern))
        if keys:
            return self._client.redis.delete(*keys)
        return 0
```

### 2.5 命名空间与 TTL 策略

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/namespace.py`

```python
# ADR-040 统一命名空间

NAMESPACE_PREFIX = "ditto:derived"

def build_snapshot_key(
    *,
    entity_type: str,
    entity_id: str,
    instance_key: str,
) -> str:
    """构建 per-instance snapshot key。"""
    return f"{NAMESPACE_PREFIX}:state:{entity_type}:{entity_id}:snapshot:{instance_key}"

def build_control_state_key(
    *,
    entity_type: str,
    entity_id: str,
) -> str:
    """构建控制面 latest state key（无 TTL）。"""
    return f"{NAMESPACE_PREFIX}:state:{entity_type}:{entity_id}"

def build_checkpoint_key(
    *,
    entity_type: str,
    entity_id: str,
    partition_key: str,
) -> str:
    """构建 checkpoint key（7 天 TTL）。"""
    return f"{NAMESPACE_PREFIX}:checkpoint:{entity_type}:{entity_id}:{partition_key}"

# TTL 常量（ADR-040）
SNAPSHOT_TTL_SECONDS = 7 * 24 * 3600  # 7 天
CHECKPOINT_TTL_SECONDS = 7 * 24 * 3600  # 7 天
CONTROL_STATE_TTL_SECONDS = None  # 无 TTL
```

### Phase 2 验收标准

| 检查项 | 标准 |
|--------|------|
| DDL 管理 | `ensure_tables()` 创建所有热表，`verify_tables()` 确认无缺失 |
| QuestDBReader | `read_latest()` 从 `f_1m_hot` 查询返回 `pl.DataFrame` |
| QuestDBWriter | `write_frame()` 通过 ILP 写入数据，可被 Reader 读回 |
| KvrocksStore HASH | `write_hash_snapshot()` + `read_hash_snapshot()` 读写一致 |
| KvrocksStore BLOB | `write_blob_snapshot()` + `read_blob_snapshot()` 读写一致 |
| 命名空间 | 所有 key 符合 `ditto:derived:state:*` 规范 |
| TTL | snapshot 7 天、checkpoint 7 天、control state 无 TTL |
| Testcontainers | 集成测试使用真实容器验证读写 |
| 测试 | 全部通过，覆盖率 ≥ 80% |

---

## Phase 3: 集成到流水线 + 盘中模式

### 目标

将热层集成到物化/查询流水线，实现端到端盘中因子计算。

### 3.1 物化双写

**文件**: `apps/port/src/ditto_port/services/derived/materialization.py`（修改）

物化流程扩展：Parquet 写入完成后，同步写入 QuestDB。

```python
class DerivedMaterializationOrchestrator:
    def __init__(
        self,
        *,
        # ... 现有依赖 ...
        hot_layer_writer: HotLayerWriter,  # 新增
    ) -> None: ...

    def materialize(self, request: DerivedMaterializationRequest) -> DerivedMaterializationResult:
        # 1. 现有流程：编译 → 加载 → 计算 → 写入 Parquet → 更新 Catalog
        result = self._execute_materialization(request)

        # 2. 新增：如果 HotLayerWriter 可用，同步写入热层
        if self._hot_layer_available(request):
            self._write_to_hot_layer(result)

        return result
```

### 3.2 查询热层路由

**文件**: `apps/port/src/ditto_port/services/derived/query_facade.py`（修改）

扩展现有 `get_latest()` 的热层逻辑，从占位升级为完整实现。

```python
def get_latest(self, request: LatestDerivedRequest) -> DerivedLatestResult:
    mode = self._mode_resolver.resolve()

    # ONLINE 模式：热层优先
    if mode == RuntimeMode.ONLINE and self._hot_layer.is_available():
        try:
            data = self._hot_layer.read_latest(
                derived_id=request.derived_ids[0],
                instrument_ids=request.instrument_ids,
                as_of=_temporal_to_iso(request.as_of),
            )
            if not data.is_empty():
                logger.info("Hot layer hit", derived_id=request.derived_ids[0])
                return DerivedLatestResult(data=data)
        except Exception:
            logger.warning(
                "Hot layer read failed, falling back to cold layer",
                exc_info=True,
            )

    # 冷层回退
    return DerivedLatestResult(data=self._service.find_latest(query))
```

### 3.3 STATE 因子盘前初始化

**文件**: `packages/datahub/src/ditto_datahub/services/derived/state_initializer.py`（新增）

```python
class StateInitializer:
    """STATE 因子盘前状态初始化。"""

    def __init__(
        self,
        *,
        state_store: StateStore,
        catalog_service: DerivedCatalogService,
    ) -> None: ...

    async def initialize_factor(self, factor_id: str) -> int:
        """从 Parquet 计算初始快照并写入 Kvrocks。"""
        # 1. 获取 factor spec
        # 2. 从 Parquet 读取历史数据
        # 3. 计算状态快照
        # 4. 批量写入 Kvrocks
        # 返回初始化的 instrument 数量
        ...

    async def initialize_all_state_factors(self) -> dict[str, int]:
        """初始化所有 STATE 模式因子。"""
        ...
```

### 3.4 运行时模式持久化

**文件**: `packages/datahub/src/ditto_datahub/services/hot_layer/runtime_mode_manager.py`（新增）

```python
class RuntimeModeManager:
    """运行时模式管理（ADR-030）。"""

    def __init__(self, state_store: StateStore) -> None: ...

    def get_mode(self) -> RuntimeMode:
        """获取当前运行时模式。"""
        ...

    def set_mode(
        self,
        mode: RuntimeMode,
        *,
        reason: str,
        operator: str,
    ) -> None:
        """切换运行时模式（需显式触发，记录审计）。"""
        ...

    def get_mode_history(self, limit: int = 10) -> list[ModeChangeEvent]:
        """获取模式切换历史。"""
        ...
```

### 3.5 Pushdown Engine（可选）

**复杂度较高，建议作为 Phase 3 的增量迭代，不阻塞其他任务。**

```python
class PushdownEngine:
    """表达式下推引擎（ADR-027）。"""

    def can_pushdown(self, expression: str) -> bool:
        """检查表达式是否可以下推到 QuestDB。"""
        ...

    def to_questdb_sql(self, expression: str) -> str:
        """将表达式转换为 QuestDB SQL。"""
        ...

    def execute(
        self,
        expression: str,
        *,
        instrument_id: str,
        window: str,
    ) -> pl.DataFrame:
        """执行下推查询。"""
        ...
```

### 3.6 盘后回补 Flow

**文件**: `apps/port/src/ditto_port/jobs/flows/hot_layer_backfill.py`（新增）

```python
@flow(name="hot-layer-daily-backfill")
async def daily_backfill_flow() -> None:
    """每日盘后从 Parquet 回补 QuestDB 热层。"""
    # 1. 确定回补日期范围（最近 5 天）
    # 2. 读取 Parquet bar_1m 数据
    # 3. 通过 ILP 写入 QuestDB bar_1m_hot
    # 4. 验证写入行数
    ...
```

### Phase 3 验收标准

| 检查项 | 标准 |
|--------|------|
| 物化双写 | Parquet 写入后 QuestDB 可查到相同数据 |
| 查询路由 | ONLINE 模式优先读热层，DEGRADED 模式允许 Parquet |
| STATE 初始化 | 盘前从 Parquet 计算 Kvrocks 快照，盘中可读取 |
| 运行时模式 | 模式切换有审计记录，持久化到 Kvrocks |
| 盘后回补 | Prefect flow 成功回补 QuestDB |
| 端到端测试 | 物化 → QuestDB 写入 → 查询路由 → 降级回退 |
| 测试 | 全部通过，覆盖率 ≥ 80% |

---

## 文件变更总览

### 新增文件

```
# 基础设施
docker-compose.dev.yml
config/development/questdb.env
config/development/kvrocks.env

# infra 层 - 连接客户端
packages/infra/src/ditto_infra/clients/__init__.py
packages/infra/src/ditto_infra/clients/questdb.py
packages/infra/src/ditto_infra/clients/kvrocks.py

# datahub 层 - 协议实现
packages/datahub/src/ditto_datahub/services/hot_layer/in_memory_reader.py
packages/datahub/src/ditto_datahub/services/hot_layer/in_memory_writer.py
packages/datahub/src/ditto_datahub/services/hot_layer/in_memory_store.py
packages/datahub/src/ditto_datahub/services/hot_layer/questdb_reader.py
packages/datahub/src/ditto_datahub/services/hot_layer/questdb_writer.py
packages/datahub/src/ditto_datahub/services/hot_layer/questdb_ddl.py
packages/datahub/src/ditto_datahub/services/hot_layer/kvrocks_store.py
packages/datahub/src/ditto_datahub/services/hot_layer/namespace.py
packages/datahub/src/ditto_datahub/services/derived/state_initializer.py
packages/datahub/src/ditto_datahub/services/hot_layer/runtime_mode_manager.py

# Port 层 - DI + Flow
apps/port/src/ditto_port/registry/datahub/hot_layer.py
apps/port/src/ditto_port/jobs/flows/hot_layer_backfill.py

# 测试
packages/infra/tests/unit/clients/test_questdb_client_unit.py
packages/infra/tests/unit/clients/test_kvrocks_client_unit.py
packages/infra/tests/integration/test_containers_integration.py
packages/datahub/tests/unit/services/hot_layer/test_questdb_reader_unit.py
packages/datahub/tests/unit/services/hot_layer/test_questdb_writer_unit.py
packages/datahub/tests/unit/services/hot_layer/test_kvrocks_store_unit.py
packages/datahub/tests/unit/services/hot_layer/test_namespace_unit.py
packages/datahub/tests/integration/hot_layer/test_questdb_integration.py
packages/datahub/tests/integration/hot_layer/test_kvrocks_integration.py
```

### 修改文件

```
pixi.toml                                          # 添加依赖
packages/datahub/src/ditto_datahub/settings.py     # 添加配置模型
packages/datahub/src/ditto_datahub/services/__init__.py  # re-export
packages/datahub/src/ditto_datahub/services/hot_layer/__init__.py  # 添加 re-export
apps/port/src/ditto_port/services/derived/query_facade.py  # 热层路由
apps/port/src/ditto_port/services/derived/materialization.py  # 双写
apps/port/src/ditto_port/registry/datahub/__init__.py  # 注册 HotLayerProvider
```

---

## 不在本计划范围内

| 项目 | 原因 |
|------|------|
| Pushdown Engine 完整实现 | ADR-027 的表达式→SQL 映射复杂度高，建议独立计划 |
| LOB 热表（lob_5s_hot / lob_1s_hot） | 依赖实时行情数据源，非当前优先级 |
| 多实例 RuntimeMode 协调 | 需要分布式锁/选主，Phase 3 仅单实例持久化 |
| 生产部署（K8s / 监控 / 告警） | 属于运维阶段 |
| 灾备恢复脚本化 | ADR-023 恢复流程复杂度高，建议独立计划 |
| Kvrocks Streams | ADR 未定义消息 schema，建议独立计划 |

---

## 相关 ADR

| ADR | 内容 | Phase |
|-----|------|-------|
| [ADR-028](../design/unified-feature-factor-engine/decisions/storage/adr-028-questdb-hot-tables.md) | QuestDB 热表 DDL | Phase 2 |
| [ADR-031](../design/unified-feature-factor-engine/decisions/storage/adr-031-state-snapshot-abi.md) | State Snapshot ABI | Phase 2 |
| [ADR-040](../design/unified-feature-factor-engine/decisions/storage/adr-040-hot-cold-retention-state-namespace-policy.md) | 保留策略 + 命名空间 | Phase 2 |
| [ADR-027](../design/unified-feature-factor-engine/decisions/storage/adr-027-pushdown-strategy.md) | 表达式 Pushdown | Phase 3（可选） |
| [ADR-029](../design/unified-feature-factor-engine/decisions/adr-029-intraday-postmarket-paths.md) | 盘中/盘后路径 | Phase 3 |
| [ADR-030](../design/unified-feature-factor-engine/decisions/adr-030-online-data-access-boundary.md) | 在线查询边界 | Phase 3 |
| [ADR-011](../design/unified-feature-factor-engine/decisions/adr-011-streaming-mode.md) | 盘中微批量 | Phase 3 |
| [ADR-023](../design/unified-feature-factor-engine/decisions/adr-023-disaster-recovery.md) | 灾备恢复 | 不在本计划 |
