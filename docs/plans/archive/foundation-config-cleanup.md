# Foundation 层配置代码清理 + 架构依赖修复计划

## 一、分析总结（基于 LSP + 代码探索）

### 1.1 LSP 分析结果

**全局单例函数使用情况**：
- `get_settings()` - **0 处实际使用**（只在导出中）
- `reload_settings()` - **0 处实际使用**
- `SettingsManager` - **0 处实际使用**

### 1.2 当前架构问题

**问题 1：配置类过于简单，实际价值不大**

当前 `DatabaseSettings`、`DataSourceSettings`、`FileStorageSettings` 只返回路径：

```python
# 当前：只有路径
class DatabaseSettings(BaseSettings):
    @computed_field
    def sqlite_path(self) -> Path:
        return get_paths().data_subdir("db/sqlite/hub.sqlite")
```

**实际需要**：配置应该包含真实可配置的参数

```python
# 期望：包含实际配置
class DatabaseSettings(BaseSettings):
    # SQLite 配置
    timeout: float = 30.0
    wal_enabled: bool = False
    foreign_keys_enabled: bool = True

    # 连接池配置
    connection_warn_threshold: int = 50

    # 路径仍然通过 computed_field
    @computed_field
    def sqlite_path(self) -> Path:
        return get_paths().data_subdir("db/sqlite/hub.sqlite")
```

**问题 2：业务代码直接注入底层资源**

```python
# 当前：直接注入底层资源
class TushareSource:
    def __init__(self, data_root: Path, sqlite_pool: SQLitePool):
        ...

# 期望：注入配置
class TushareSource:
    def __init__(self, config: DataSourceSettings):
        self.client = TushareClient(
            api_url=config.http_base_url,
            timeout=config.http_timeout,
            retry_config=config.retry_config,
        )
```

**问题 3：架构依赖方向错误**
- `datahub/models/__init__.py` 重新导出 `core.quality.spec`
- `DataHubProvider` 提供了 `dq_engine`（core 层组件）

---

## 二、重构目标

### 2.1 配置类应该包含真实配置

**DataSourceSettings** 应包含：
- HTTP 配置：`http_base_url`、`http_timeout`
- 重试配置：`retry_max_attempts`、`retry_delay`、`retry_multiplier`
- 限流配置：`rate_limit_profile`（free/paid/conservative）
- Token：`tushare_token`（可选，优先使用 keyring）

**DatabaseSettings** 应包含：
- 连接配置：`sqlite_timeout`、`wal_enabled`
- 连接池：`connection_warn_threshold`

**FileStorageSettings** 应包含：
- 压缩配置：`compression`（通用压缩配置）
- 统计配置：`use_statistics`（通用统计配置）
- 存储根目录：`data_root`

### 2.2 业务代码应该使用配置

重构后：
- `TushareClient` 接受 `DataSourceSettings`
- `SQLitePool` 接受 `DatabaseSettings`
- `ParquetStoreBase` 接受 `FileStorageSettings`（通用存储配置）

### 2.3 架构依赖方向修复

**修复前**：
- ❌ `datahub` → `core`（反向依赖）

**修复后**：
- ✅ `core` → `datahub` → `foundation`（单向依赖）
- ✅ `apps/port` 通过 `CoreProvider` 提供 Core 层组件

---

## 三、删除计划

### 3.1 立即删除的文件

```bash
# 备份文件
packages/foundation/src/ditto_foundation/config/__init__.py,cover
packages/foundation/src/ditto_foundation/config/paths.py,cover
packages/foundation/src/ditto_foundation/config/settings.py,cover

# 过时的 README
packages/foundation/src/ditto_foundation/config/README.md
```

### 3.2 删除的代码（foundation/settings.py）

**删除全局单例相关**：
- `SettingsManager` 类
- `get_settings()` 函数
- `reload_settings()` 函数

**从 Settings 类移除**：
- `database: DatabaseSettings` 字段（移至 DataHub，包含真实数据库配置）
- `data_source: DataSourceSettings` 字段（移至 DataHub，包含 HTTP/重试/限流配置）
- `file_storage: FileStorageSettings` 字段（移至 DataHub，改为通用存储配置）
- `__init__()` 方法（已由 ConfigProvider 接管）

---

## 四、架构依赖问题修复

### 4.1 问题 1：删除 datahub 对 core 的反向依赖

**当前问题**：`datahub/models/__init__.py` 重新导出 `core.quality.spec` 中的所有 DQ model

```python
# packages/datahub/src/ditto_datahub/models/__init__.py
# ❌ 违反依赖方向：datahub → core
from ditto_core.quality.spec import (
    ColumnRule, DatasetRules, DQIssue, DQLevel, ...
)
```

**解决方案**：
1. 删除 `datahub/models/__init__.py` 中所有 DQ model 的重新导出
2. 更新引用文件：
   - `apps/port/src/ditto_port/jobs/tasks/monitoring.py`
   - 测试文件：`packages/datahub/tests/unit/models/test_common_unit.py`

### 4.2 问题 2：创建 CoreProvider，移除 DataHubProvider 对 core 的依赖

**当前问题**：`DataHubProvider` 中提供了 `dq_engine` 方法，依赖 `core` 层

```python
# apps/port/src/ditto_port/registry/datahub.py
# ❌ DataHubProvider 依赖 core 层
from ditto_core.quality import QualityEngine
from ditto_core.quality.config import DQSettings

@provide
def dq_engine(self, dq_settings: DQSettings, data_root: Path) -> QualityEngine:
    return QualityEngine(dq_settings=dq_settings, data_root=data_root)
```

**解决方案**：创建独立的 `CoreProvider`

```python
# apps/port/src/ditto_port/registry/core.py
"""Core 层组件注册."""

from dishka import Provider, Scope, provide
from ditto_core.quality import QualityEngine
from ditto_core.quality.config import DQSettings

__all__ = ["CoreProvider"]


class CoreProvider(Provider):
    """Core 层组件 Provider."""

    scope = Scope.APP

    @provide
    def dq_engine(
        self,
        dq_settings: DQSettings,
        data_root: Path,
    ) -> QualityEngine:
        """数据质量引擎（应用层 DQ 检查使用）."""
        return QualityEngine(dq_settings=dq_settings, data_root=data_root)
```

### 4.3 更新容器组合

**需要更新的文件**：
1. `apps/port/src/ditto_port/main.py`
2. `apps/port/src/ditto_port/cli/context.py`
3. `apps/port/src/ditto_port/jobs/context.py`
4. `apps/port/src/ditto_port/registry/__init__.py`

**变更内容**：
- 添加 `ConfigProvider`（已存在，但未使用）
- 添加 `CoreProvider`（新建）
- 移除 `AppProvider`（已废弃）

```python
# 更新后
from ditto_port.registry import ConfigProvider, CoreProvider, DataHubProvider, DataSourcesProvider

container = make_async_container(
    ConfigProvider(),      # 配置
    CoreProvider(),        # Core 层（QualityEngine 等）
    DataHubProvider(),     # DataHub 层
    DataSourcesProvider(), # 数据源
)
```

---

## 五、DataHub 配置重构计划

### 5.1 创建完整的 DataSourceSettings

```python
# packages/datahub/src/ditto_datahub/config/data_source.py
"""数据源配置."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataSourceSettings(BaseSettings):
    """数据源配置."""

    model_config = SettingsConfigDict(
        env_prefix="DATASOURCE_",
        extra="ignore",
    )

    # ========== HTTP 配置 ==========
    http_base_url: str = Field(
        default="http://api.tushare.pro",
        description="Tushare API Base URL"
    )
    http_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="HTTP 请求超时（秒）"
    )

    # ========== 重试配置 ==========
    retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="最大重试次数"
    )
    retry_multiplier: float = Field(
        default=1.0,
        ge=0.1,
        description="重试延迟乘数"
    )
    retry_min_wait: float = Field(
        default=1.0,
        ge=0.1,
        description="最小等待时间（秒）"
    )
    retry_max_wait: float = Field(
        default=10.0,
        ge=1.0,
        description="最大等待时间（秒）"
    )

    # ========== 限流配置 ==========
    rate_limit_profile: str = Field(
        default="free",
        description="限流预设（free/paid/conservative）"
    )
    rate_limit_global_rate: int | None = Field(
        default=None,
        description="全局限流（请求/分钟），None 表示使用预设值"
    )
    rate_limit_daily_rate: int | None = Field(
        default=None,
        description="日限流（请求/天），None 表示使用预设值"
    )

    # ========== Token 配置 ==========
    tushare_token: str = Field(
        default="",
        description="Tushare Pro API Token（优先使用 keyring）"
    )
```

### 5.2 创建完整的 DatabaseSettings

```python
# packages/datahub/src/ditto_datahub/config/database.py
"""数据库配置."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config import get_paths


class DatabaseSettings(BaseSettings):
    """数据库配置."""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        extra="ignore",
    )

    # ========== SQLite 配置 ==========
    sqlite_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="SQLite 连接超时（秒）"
    )
    sqlite_wal_enabled: bool = Field(
        default=False,
        description="是否启用 WAL 模式"
    )
    sqlite_foreign_keys: bool = Field(
        default=True,
        description="是否启用外键约束"
    )

    # ========== 连接池配置 ==========
    connection_warn_threshold: int = Field(
        default=50,
        ge=1,
        description="连接数告警阈值"
    )

    # ========== 缓存配置 ==========
    calendar_cache_enabled: bool = Field(
        default=True,
        description="是否启用交易日历缓存"
    )
    calendar_cache_ttl: int = Field(
        default=3600,
        ge=60,
        description="缓存 TTL（秒）"
    )

    # ========== 路径（computed_field） ==========
    @computed_field
    @property
    def sqlite_path(self) -> str:
        """SQLite 数据库文件路径."""
        return str(get_paths().data_subdir("db/sqlite/hub.sqlite"))

    @computed_field
    @property
    def duckdb_path(self) -> str:
        """DuckDB 数据库文件路径."""
        return str(get_paths().data_subdir("db/duckdb/ditto.duckdb"))
```

### 5.3 创建完整的 FileStorageSettings

```python
# packages/datahub/src/ditto_datahub/config/storage.py
"""文件存储配置（格式无关）."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config import get_paths


class FileStorageSettings(BaseSettings):
    """文件存储配置（通用，不绑定具体存储格式）."""

    model_config = SettingsConfigDict(
        env_prefix="FILE_STORAGE_",
        extra="ignore",
    )

    # ========== 压缩配置 ==========
    compression: str = Field(
        default="snappy",
        description="压缩算法（snappy/gzip/brotli/zstd）"
    )

    # ========== 统计信息配置 ==========
    use_statistics: bool = Field(
        default=True,
        description="是否收集统计信息（加速查询）"
    )

    # ========== 路径（computed_field） ==========
    @property
    def data_root(self) -> str:
        """数据存储根目录."""
        return str(get_paths().data_home)
```

---

## 六、重构业务代码使用配置

### 6.1 重构 TushareClient

```python
# packages/datahub/src/ditto_datahub/sources/tushare/client.py

class TushareClient:
    def __init__(self, config: DataSourceSettings):
        self._config = config

        # 使用配置创建 HTTP 客户端
        self._http_client = httpx.Client(
            base_url=config.http_base_url,
            timeout=config.http_timeout,
        )

        # 使用配置创建限流器
        self._rate_limiter = TushareRateLimiter(
            config=TushareRateLimitConfig.from_profile(
                config.rate_limit_profile
            )
        )
```

### 6.2 重构 SQLitePool

```python
# packages/foundation/src/ditto_foundation/db/sqlite_pool.py

class SQLitePool:
    def __init__(self, db_path: str, config: DatabaseSettings):
        self._config = config

        # 使用配置连接
        self._pool = ThreadedConnectionPool(
            db_path,
            timeout=config.sqlite_timeout,
        )

        # 设置 PRAGMA
        self._setup_pragmas()
```

### 6.3 更新 Provider

```python
# apps/port/src/ditto_port/registry/datahub.py

@provide
def data_source_settings(config_loader: ConfigLoader) -> DataSourceSettings:
    """数据源配置."""
    values = dotenv_values(config_loader.get_env_file("data_source"))
    return DataSourceSettings.model_validate(values)

@provide
def database_settings(config_loader: ConfigLoader) -> DatabaseSettings:
    """数据库配置."""
    values = dotenv_values(config_loader.get_env_file("database"))
    return DatabaseSettings.model_validate(values)

@provide
def file_storage_settings(config_loader: ConfigLoader) -> FileStorageSettings:
    """文件存储配置（通用）."""
    values = dotenv_values(config_loader.get_env_file("file_storage"))
    return FileStorageSettings.model_validate(values)

@provide
def tushare_source(
    data_source_settings: DataSourceSettings,
    sqlite_client: SQLiteClient,
) -> TushareSource:
    """Tushare 数据源（注入配置）."""
    return TushareSource(
        config=data_source_settings,
        sqlite_client=sqlite_client,
    )
```

---

## 七、环境变量配置文件

### 7.1 更新 config/development/data_source.env

```bash
# HTTP 配置
DATASOURCE_HTTP_BASE_URL=http://api.tushare.pro
DATASOURCE_HTTP_TIMEOUT=30.0

# 重试配置
DATASOURCE_RETRY_MAX_ATTEMPTS=3
DATASOURCE_RETRY_MULTIPLIER=1.0
DATASOURCE_RETRY_MIN_WAIT=1.0
DATASOURCE_RETRY_MAX_WAIT=10.0

# 限流配置
DATASOURCE_RATE_LIMIT_PROFILE=free
# DATASOURCE_RATE_LIMIT_GLOBAL_RATE=200
# DATASOURCE_RATE_LIMIT_DAILY_RATE=1000

# Token（优先使用 keyring）
# DATASOURCE_TUSHARE_TOKEN=your_token_here
```

### 7.2 创建 config/development/file_storage.env

```bash
# 通用文件存储配置（格式无关）
FILE_STORAGE_COMPRESSION=snappy
FILE_STORAGE_USE_STATISTICS=true
```

### 7.3 更新 config/development/database.env

```bash
# SQLite 配置
DB_SQLITE_TIMEOUT=30.0
DB_SQLITE_WAL_ENABLED=false
DB_SQLITE_FOREIGN_KEYS=true

# 连接池配置
DB_CONNECTION_WARN_THRESHOLD=50

# 缓存配置
DB_CALENDAR_CACHE_ENABLED=true
DB_CALENDAR_CACHE_TTL=3600
```

---

## 八、Foundation 层简化

### 8.1 简化后的 settings.py

```python
"""Ditto 系统配置管理."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config.environment import Environment


class SystemSettings(BaseSettings):
    """系统基础配置（Foundation 层）."""

    ditto_env: Environment = Field(default=Environment.DEVELOPMENT)
    timezone: str = Field(default="Asia/Shanghai")
    debug: bool = Field(default=False)


class ObservabilitySettings(BaseSettings):
    """可观测性配置（Foundation 层）."""

    model_config = SettingsConfigDict(env_prefix="DITTO_OTEL_")

    log_level: str = Field(default="INFO")
    vm_endpoint: str = Field(
        default="http://localhost:8428/opentelemetry/v1/metrics"
    )
    # ... 其他配置


class Settings(BaseSettings):
    """Ditto系统主配置类（Foundation 层）."""

    system: SystemSettings = Field(default_factory=SystemSettings)
    observability: ObservabilitySettings = Field(
        default_factory=ObservabilitySettings
    )


__all__ = [
    "SystemSettings",
    "ObservabilitySettings",
    "Settings",
]
```

---

## 九、执行步骤

### Phase 0: 修复架构依赖问题（新增）
1. 删除 `datahub/models/__init__.py` 中的 DQ model 重新导出
2. 更新 `monitoring.py` 等文件的 import
3. 创建 `apps/port/src/ditto_port/registry/core.py`（CoreProvider）
4. 更新所有容器组合位置，添加 ConfigProvider 和 CoreProvider
5. 移除 AppProvider 引用
6. 从 DataHubProvider 中移除 dq_engine 方法

### Phase 1: 清理 Foundation 层
1. 删除备份文件
2. 删除 `get_settings()` 等全局单例
3. 简化 `Settings` 类

### Phase 2: 创建 DataHub 配置
1. 创建 `datahub/config/data_source.py`（DataSourceSettings）
2. 创建 `datahub/config/database.py`（DatabaseSettings）
3. 创建 `datahub/config/storage.py`（FileStorageSettings，通用存储配置）
4. 更新 `datahub/__init__.py`

### Phase 3: 重构业务代码
1. 重构 `TushareClient` 使用配置
2. 重构 `SQLitePool` 使用配置
3. 更新 `DataHubProvider`

### Phase 4: 更新环境文件
1. 更新 `config/development/data_source.env`
2. 更新 `config/development/database.env`
3. 创建 `config/development/file_storage.env`（通用文件存储配置）

### Phase 5: 验证
1. 类型检查
2. 运行测试
3. 删除废弃的测试文件

---

## 十、领域划分总结

| 层级 | 配置类 | 配置内容 |
|------|--------|---------|
| **Foundation** | `SystemSettings` | 时区、环境、调试模式 |
| **Foundation** | `ObservabilitySettings` | 日志、追踪、指标端点 |
| **DataHub** | `DataSourceSettings` | HTTP、重试、限流、Token |
| **DataHub** | `DatabaseSettings` | 超时、WAL、外键、缓存 |
| **DataHub** | `FileStorageSettings` | 压缩、统计（格式无关） |
| **Core** | `DQSettings` | L1/L2/L3 开关、规则目录 |

### 架构原则

> **配置应该包含实际可配置的参数**，而非简单的路径包装
>
> **业务代码应该注入配置类，而非直接注入底层资源**

### 依赖方向

**正确依赖链**：
```
apps/port (Composition Root)
    ├── ConfigProvider   (Foundation 配置)
    ├── CoreProvider     (Core 层组件)
    ├── DataHubProvider  (DataHub 层组件)
    └── DataSourcesProvider (数据源组件)

core → datahub → foundation
```

**修复前问题**：
- ❌ `datahub/models/__init__.py` 重新导出 `core.quality.spec`
- ❌ `DataHubProvider` 提供了 `dq_engine`（core 层组件）

**修复后**：
- ✅ `CoreProvider` 独立提供 Core 层组件
- ✅ `datahub` 不再依赖 `core`
- ✅ 所有层间依赖单向：`core → datahub → foundation`
