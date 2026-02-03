# Ditto 统一 DI 配置注入架构设计

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


**日期**: 2026-01-21
**目标**: 全部配置改为 DI 注入，同时保持 foundation 层统一框架

---

## 一、当前配置架构分析

### 1.1 双层环境架构

| 层级 | 变量 | 有效值 | 用途 |
|------|------|--------|------|
| Pixi 环境 | - | `default`, `dev` | 依赖管理层 |
| 运行时环境 | `DITTO_ENV` | `development`, `testing`, `production` | 行为控制层 |

### 1.2 配置文件结构

```
config/
├── development/
│   ├── api.env              # API_* 配置
│   ├── data_source.env      # HTTP_/RETRY_/RATE_LIMIT_/TUSHARE_TOKEN
│   ├── database.env         # SQLITE_PATH/DUCKDB_PATH
│   ├── dq.env               # 无前缀（直接字段名）✅ 新增
│   ├── observability.env    # 无前缀（直接字段名）
│   ├── performance.env      # 性能相关配置
│   └── system.env           # DITTO_ENV 等基础配置
├── testing/
├── production/
```

### 1.3 现有配置加载机制

```python
# packages/foundation/src/ditto_foundation/config/settings.py
class Settings(BaseSettings):
    def __init__(self, **kwargs: Any) -> None:
        env_str = os.getenv("DITTO_ENV", "development")
        environment = Environment.from_str(env_str)
        loader = ConfigLoader(environment)

        # 为每个配置子系统加载特定 env 文件
        self._init_config_subsystems(loader, kwargs)
        super().__init__(**kwargs)
```

### 1.4 当前问题

| 问题 | 影响 |
|------|------|
| 全局单例 `get_settings()` | 隐藏依赖，难测试 |
| 不同层直接调用 `get_settings()` | 依赖关系不清晰 |
| DQSettings 延迟导入 foundation | 循环依赖 |
| 配置加载逻辑分散在 `__init__` 中 | 难以扩展和测试 |

---

## 二、统一 DI 配置注入架构设计

### 2.1 核心原则

> **"配置即依赖"**：所有配置都是依赖，通过 DI 容器注入

**架构分层**：

```
┌─────────────────────────────────────────────────────────────┐
│              DI 容器                   │
│                                                         │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Foundation 配置层      │   │
│  │  - Settings (主配置)                    │   │
│  │  - ConfigLoader (环境感知加载)              │   │
│  │  - ConfigProvider (统一提供者)              │   │
│  └───────────────────────────────────────────────────────┘   │
│                         ↓                                   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  业务配置层 (core/datahub)        │   │
│  │  - DQSettings (env 注入)                 │   │
│  │  - 其他业务配置...                       │   │
│  └───────────────────────────────────────────────────────┘   │
│                         ↓                                   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  应用配置层              │   │
│  │  - ServerSettings (env 注入)               │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 Foundation 层：统一配置框架

#### 2.2.1 创建 ConfigProvider（统一配置提供者）

```python
# packages/foundation/src/ditto_foundation/config/provider.py
"""
统一配置提供者.

通过 DI 容器提供所有配置，保持配置加载逻辑统一。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from loguru import logger

from ditto_foundation.config.environment import Environment
from ditto_foundation.config.loader import ConfigLoader
from ditto_foundation.config.paths import get_paths


class ConfigProvider(Provider):
    """
    统一配置提供者.

    职责：
    1. 根据环境创建 ConfigLoader
    2. 加载所有配置子系统
    3. 提供配置给其他 Provider 使用
    """

    scope = Scope.APP  # 应用级单例

    @provide
    def environment(self) -> Environment:
        """运行时环境（应用级单例）."""
        import os
        env_str = os.getenv("DITTO_ENV", "development")
        return Environment.from_str(env_str)

    @provide
    def config_loader(self, environment: Environment) -> ConfigLoader:
        """配置加载器（应用级单例）."""
        return ConfigLoader(environment)

    @provide
    def data_root(self) -> Path:
        """数据根目录."""
        return get_paths().data_home

    @provide
    def settings(self, config_loader: ConfigLoader) -> Settings:
        """
        主配置 Settings（应用级单例）.

        由 ConfigLoader 负责加载所有子系统的配置.
        """
        # 从各个 env 文件加载配置
        database_values = dotenv_values(
            config_loader.get_env_file("database")
        )
        observability_values = dotenv_values(
            config_loader.get_env_file("observability")
        )
        # ... 其他配置

        return Settings(
            database=DatabaseSettings(**database_values),
            observability=ObservabilitySettings(**observability_values),
            # ...
        )
```

#### 2.2.2 保持 ConfigLoader 统一加载逻辑

```python
# packages/foundation/src/ditto_foundation/config/provider.py (续)

class ConfigProvider(Provider):
    # ... 现有方法 ...

    @provide
    def dq_settings(
        self,
        config_loader: ConfigLoader,
        environment: Environment,
    ) -> DQSettings:
        """
        DQ 配置（应用级单例）.

        ✅ 统一规则：从 config/{env}/dq.env 加载
        """
        dq_values = dotenv_values(
            config_loader.get_env_file("dq")
        )
        # 注入环境信息
        return DQSettings.model_validate({
            **dq_values,
            "env": environment.value,  # 注入环境
        })

    @provide
    def api_settings(
        self,
        config_loader: ConfigLoader,
    ) -> ApiSettings:
        """API 配置（应用级单例）."""
        api_values = dotenv_values(
            config_loader.get_env_file("api")
        )
        return ApiSettings(**api_values)
```

**关键设计**：
- ✅ 所有配置都在 ConfigProvider 中创建
- ✅ 统一使用 ConfigLoader 加载环境特定配置
- ✅ 环境信息通过 DI 注入到各个配置
- ✅ 保持与现有环境规范完全兼容

---

### 2.3 应用层：Dishka DI 容器

#### 2.3.1 更新 AppProvider

```python
# apps/port/src/ditto_port/registry/app.py
"""
基础设施组件注册（统一配置注入）.
"""

import os
from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_foundation.config import Settings
from ditto_foundation.observability import init, shutdown

class AppProvider(Provider):
    """基础设施组件 Provider（配置注入）."""

    scope = Scope.APP

    @provide
    def observability(self, settings: Settings) -> Iterator[None]:
        """
        初始化 Observability（注入 Settings）.

        ✅ 显式依赖：settings.observability.xxx
        """
        init(
            service_name="ditto-server",
            environment=settings.system.ditto_env.value,
            log_level=settings.observability.log_level,
            # ...
        )
        yield
        shutdown()
```

#### 2.3.2 创建统一的 FoundationProvider

```python
# apps/port/src/ditto_port/registry/foundation.py
"""
Foundation 层配置 Provider.

将 foundation 层的 ConfigProvider 暴露给应用层 DI 容器.
"""

from collections.abc import Iterator
from dishka import Provider, Scope, provide

from ditto_foundation.config.provider import ConfigProvider
from ditto_foundation.observability import init, shutdown


class FoundationProvider(Provider):
    """Foundation 层配置 Provider."""

    scope = Scope.APP

    @provide
    def config_provider(self) -> ConfigProvider:
        """✅ 暴露 Foundation 的 ConfigProvider."""
        return ConfigProvider()

    @provide
    def observability(
        self,
        config_provider: ConfigProvider,
    ) -> Iterator[None]:
        """
        初始化 Observability（通过 ConfigProvider）.

        ✅ 统一入口：所有配置都从 ConfigProvider 获取
        """
        settings = config_provider.settings  # ✅ 从 ConfigProvider 获取
        observability_config = settings.observability

        init(
            service_name="ditto-server",
            environment=settings.system.ditto_env.value,
            log_level=observability_config.log_level,
            tracing_enabled=observability_config.tracing_enabled,
            # ...
        )
        yield
        shutdown()
```

---

### 2.4 业务层：按统一规则接入配置

#### 2.4.1 DataHubProvider 使用配置

```python
# apps/port/src/ditto_port/registry/datahub.py
"""
DataHub 组件注册（配置注入）.
"""

from pathlib import Path
from dishka import Provider, Scope, provide

from ditto_foundation.config import Settings, ConfigProvider
from ditto_core.quality.config import DQSettings


class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    # ✅ 注入 ConfigProvider
    @provide
    def config_provider(self) -> ConfigProvider:
        """✅ 暴露 Foundation 的 ConfigProvider."""
        from ditto_port.registry.foundation import FoundationProvider
        return FoundationProvider().config_provider()

    # ✅ 注入主配置
    @provide
    def settings(self, config_provider: ConfigProvider) -> Settings:
        """✅ 主配置（从 ConfigProvider 获取）."""
        return config_provider.settings

    # ✅ 注入 DQ 配置
    @provide
    def dq_settings(
        self,
        config_provider: ConfigProvider,
    ) -> DQSettings:
        """✅ DQ 配置（从 ConfigProvider 统一加载）."""
        return config_provider.dq_settings

    @provide
    def dq_engine(
        self,
        dq_settings: DQSettings,
        data_root: Path,
    ) -> QualityEngine:
        """✅ 数据质量引擎（注入 DQ 配置）."""
        # 可以根据 dq_settings 的开关决定是否启用
        if not dq_settings.l1_enabled:
            # 返回一个禁用的引擎
            return QualityEngine(config=DQSpec())

        return QualityEngine(data_root=data_root)
```

---

### 2.5 配置层级的约束规则

#### 配置分层规则

| 层级 | 配置类 | 前缀规则 | Provider 位置 | 依赖 |
|------|--------|----------|-------------|------|
| **Foundation** | `Settings` | 混合 | `ConfigProvider` | 无 |
| **Foundation** | `ObservabilitySettings` | `???` | `ConfigProvider` | Settings |
| **Foundation** | `DatabaseSettings` | `DB_` | `ConfigProvider` | Settings |
| **DataHub** | `DQSettings` | `???` | `ConfigProvider` | Environment |
| **Port** | `ApiSettings` | `API_` | `ConfigProvider` | Environment |
| **Port** | `ServerSettings` | 无前缀 | `AppProvider` | Settings, Environment |

#### 配置接入规则

```python
# ✅ 规则 1：所有配置类必须通过 Provider 提供

# ❌ 错误：在业务层直接创建配置
class SomeService:
    def __init__(self):
        self.settings = Settings()  # ❌ 违背 DI 原则

# ✅ 正确：通过 DI 注入
class SomeService:
    def __init__(self, settings: Settings):
        self.settings = settings
```

```python
# ✅ 规则 2：配置加载统一由 ConfigProvider 负责

# ❌ 错误：在各个 Provider 中分散加载配置
class DataHubProvider(Provider):
    @provide
    def dq_settings(self) -> DQSettings:
        return DQSettings()  # ❌ 绕了默认 .env

# ✅ 正确：通过 ConfigProvider 统一加载
class DataHubProvider(Provider):
    @provide
    def dq_settings(self, config_provider: ConfigProvider) -> DQSettings:
        return config_provider.dq_settings  # ✅ 从 ConfigProvider 获取
```

```python
# ✅ 规则 3：环境信息通过 DI 传递，禁止内部读取环境变量

# ❌ 错误：配置类内部读取 DITTO_ENV
class DQSettings(BaseSettings):
    env: str = Field(
        default=os.getenv("DITTO_ENV", "development")  # ❌ 内部读取环境变量
    )

# ✅ 正确：通过 DI 注入环境
class DQSettings(BaseSettings):
    env: str = Field(default="development", exclude=True)  # ✅ 外部注入
```

---

## 三、改造实施计划

### Phase 1：Foundation 层改造（核心）

**目标**：创建统一的 ConfigProvider，支持所有配置的 DI 注入

#### 任务清单

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 创建 `ConfigProvider` | `foundation/config/provider.py` | M |
| 更新 `Settings.__init__` 为简单工厂 | `foundation/config/settings.py` | S |
| 添加 `ConfigProvider` 暴露到 `__init__.py` | `foundation/config/__init__.py` | S |

**代码示例**：

```python
# packages/foundation/src/ditto_foundation/config/provider.py
from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from dotenv import dotenv_values

from ditto_foundation.config.environment import Environment
from ditto_foundation.config.loader import ConfigLoader
from ditto_foundation.config.paths import get_paths
from ditto_foundation.config.settings import (
    DatabaseSettings,
    DataSourceSettings,
    FileStorageSettings,
    ObservabilitySettings,
    Settings,
    SystemSettings,
)


class ConfigProvider(Provider):
    """
    统一配置提供者.

    职责：
    - 根据 Environment 创建 ConfigLoader
    - 从 config/{env}/*.env 加载所有配置
    - 提供统一的配置访问接口
    """

    scope = Scope.APP

    @provide
    def environment(self) -> Environment:
        """运行时环境（应用级单例）."""
        import os
        env_str = os.getenv("DITTO_ENV", "development")
        return Environment.from_str(env_str)

    @provide
    def config_loader(self, environment: Environment) -> ConfigLoader:
        """配置加载器（应用级单例）."""
        return ConfigLoader(environment)

    @provide
    def data_root(self) -> Path:
        """数据根目录."""
        return get_paths().data_home

    @provide
    def settings(self, config_loader: ConfigLoader) -> Settings:
        """主配置 Settings（应用级单例）."""
        # ✅ 从各个 env 文件加载配置
        database_values = dotenv_values(
            config_loader.get_env_file("database")
        )
        observability_values = dotenv_values(
            config_loader.get_env_file("observability")
        )
        data_source_values = dotenv_values(
            config_loader.get_env_file("data_source")
        )
        system_values = dotenv_values(
            config_loader.get_env_file("system")
        )
        file_storage_values = dotenv_values(
            config_loader.get_env_file("file_storage")
        )

        return Settings(
            database=DatabaseSettings(**database_values),
            observability=ObservabilitySettings(**observability_values),
            data_source=DataSourceSettings(**data_source_values),
            system=SystemSettings(**system_values),
            file_storage=FileStorageSettings(**file_storage_values),
        )

    # ✅ 为 DQSettings 提供者
    @provide
    def dq_settings(
        self,
        config_loader: ConfigLoader,
        environment: Environment,
    ) -> DQSettings:
        """DQ 配置（应用级单例）."""
        # ✅ DQSettings 从 config/{env}/dq.env 加载
        dq_values = dotenv_values(
            config_loader.get_env_file("dq")
        )
        # ✅ 注入环境信息
        return DQSettings.model_validate({
            **dq_values,
            "env": environment.value,
        })

    @provide
    def api_settings(
        self,
        config_loader: ConfigLoader,
    ) -> ApiSettings:
        """API 配置（应用级单例）."""
        api_values = dotenv_values(
            config_loader.get_env_file("api")
        )
        return ApiSettings(**api_values)

    # ✅ 其他配置...
```

---

### Phase 2：应用层改造

**目标**：将 AppProvider 和 DataHubProvider 改为使用 ConfigProvider

#### 更新 AppProvider

```python
# apps/port/src/ditto_port/registry/app.py
"""
基础设施组件注册（配置注入）.
"""

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_foundation.config import Settings
from ditto_foundation.observability import init, shutdown


class AppProvider(Provider):
    """基础设施组件 Provider（配置注入）."""

    scope = Scope.APP

    @provide
    def observability(self, settings: Settings) -> Iterator[None]:
        """
        初始化 Observability（注入 Settings）.
        """
        config = settings.observability
        init(
            service_name="ditto-server",
            environment=settings.system.ditto_env.value,
            log_level=config.log_level,
            log_to_console=config.log_to_console,
            tracing_enabled=config.tracing_enabled,
            tracing_sample_rate=config.tracing_sample_rate,
            pytest_running=False,
            assertions_enabled=False,
            verbose_logging=(settings.system.ditto_env.is_development),
        )
        yield
        shutdown()

    @provide
    def sqlite_pool(
        self,
        settings: Settings,
        data_root: Path,
    ) -> Iterator[SQLitePool]:
        """SQLite 连接池（注入 Settings）."""
        db_path = settings.database.sqlite_path
        # ...
```

#### 更新 DataHubProvider

```python
# apps/port/src/ditto_port/registry/datahub.py
"""
DataHub 组件注册（配置注入）.
"""

from pathlib import Path
from dishka import Provider, Scope, provide
from ditto_foundation.config import ConfigProvider, Settings
from ditto_core.quality.config import DQSettings


class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    # ✅ 注入 ConfigProvider
    @provide
    def config_provider(self) -> ConfigProvider:
        """✅ 暴露 Foundation 的 ConfigProvider."""
        from ditto_port.registry.foundation import FoundationProvider
        return FoundationProvider().config_provider()

    # ✅ 注入主配置
    @provide
    def settings(self, config_provider: ConfigProvider) -> Settings:
        """✅ 主配置."""
        return config_provider.settings

    # ✅ 注入 DQ 配置
    @provide
    def dq_settings(
        self,
        config_provider: ConfigProvider,
    ) -> DQSettings:
        """✅ DQ 配置."""
        return config_provider.dq_settings

    @provide
    def dq_engine(
        self,
        dq_settings: DQSettings,
        data_root: Path,
    ) -> QualityEngine:
        """✅ 数据质量引擎（注入 DQ 配置）."""
        # 可以根据 dq_settings 的开关决定是否启用
        if not (dq_settings.l1_enabled or dq_settings.l2_enabled):
            return QualityEngine(config=DQSpec())

        return QualityEngine(data_root=str(data_root))
```

---

### Phase 3：移除全局单例访问（兼容层）

#### 标记 `get_settings()` 为废弃

```python
# packages/foundation/src/ditto_foundation/config/settings.py

from typing import warnings

# ... SettingsManager 现有代码 ...

def get_settings() -> Settings:
    """
    获取全局配置实例（兼容层）.

    .. deprecated::
        首选使用依赖注入获取 Settings。
        此函数将在未来版本中移除。
        迁移指南：在 __init__ 参数中声明 Settings 依赖。

    Returns
    -------
        Settings: 配置实例

    Examples
    --------
    ❌ 旧方式（全局单例）:
        settings = get_settings()

    ✅ 新方式（DI 注入）:
        class MyService:
            def __init__(self, settings: Settings):
                self._settings = settings
    """
    warnings.warn(
        "get_settings() is deprecated, use DI injection instead. "
        "See: docs/design/config-migration.md",
        DeprecationWarning,
        stacklevel=2
    )
    return SettingsManager.get()
```

#### 迁移脚本

```python
# scripts/migrate_to_di.py
"""
迁移指南：从全局单例迁移到 DI 注入.
"""

# 示例 1：基础设施组件
# Before:
from ditto_foundation.config import get_settings, init
settings = get_settings()
init(settings.observability.log_level)

# After:
from dishka import make_async_container
from ditto_port.registry import AppProvider
container = make_async_container(AppProvider())
settings = await container.get(Settings)
init(settings.observability.log_level)

# 示例 2：业务组件
# Before:
from ditto_foundation.config import get_settings
class MyService:
    def __init__(self):
        self.settings = get_settings()

# After:
class MyService:
    def __init__(self, settings: Settings):
        self._settings = settings
```

---

## 四、验证与测试

### 4.1 配置加载验证

```python
# tests/unit/config/test_di_config_migration.py
"""测试：DI 配置注入正确性."""

import pytest
from pathlib import Path
from ditto_port.registry import FoundationProvider

def test_config_provider_loads_correctly():
    """验证 ConfigProvider 正确加载配置."""
    # 创建容器
    container = make_container(FoundationProvider())

    # 获取配置
    settings = container.get(Settings)

    # 验证：从 development 环境加载
    assert settings.system.ditto_env.value == "development"

    # 验证：observability 配置
    assert settings.observability.log_level == "DEBUG"
    assert settings.observability.tracing_enabled is True

def test_dq_settings_has_env():
    """验证 DQSettings 包含环境信息."""
    container = make_container(FoundationProvider())
    dq_settings = container.get(DQSettings)

    # 验证：环境已注入
    assert dq_settings.env == "development"

def test_config_provider_isolation():
    """验证不同环境的配置隔离."""
    # Test 环境
    container = make_container(FoundationProvider())
    settings = container.get(Settings)

    # 修改环境测试（需 mock DITTO_ENV）
    with mock.patch.dict("os.environ", {"DITTO_ENV": "testing"}):
        container2 = make_container(FoundationProvider())
        settings2 = container2.get(Settings)
        assert settings2.system.ditto_env.is_testing
```

---

## 五、架构优势

### 5.1 配置加载统一

| 层级 | 改造前 | 改造后 |
|------|--------|--------|
| **加载位置** | `Settings.__init__` | `ConfigProvider.settings` |
| **环境感知** | 每个配置自己读取 | 统一由 ConfigProvider 管理 |
| **env 文件路径** | 硬编码或分散 | 统一通过 ConfigLoader |
| **扩展性** | 需修改多个地方 | 只需修改 ConfigProvider |

### 5.2 依赖关系清晰

```
Before (改造前):
Settings ←── 全局单例
  ↑              ↑
  │              │
Observability   SQLitePool
  (隐藏依赖)    (隐藏依赖)

After (改造后):
ConfigProvider
  ├─→ Settings
  ├─→ Observability ← 显式依赖
  └─→ SQLitePool       ← 显式依赖
```

### 5.3 测试简单化

```python
# ✅ 测试时直接创建配置
def test_my_service():
    mock_settings = Settings(
        system=SystemSettings(ditto_env=Environment.TESTING),
        observability=ObservabilitySettings(log_level="DEBUG"),
    )
    service = MyService(settings=mock_settings)

# ❌ 无需 Mock 全局函数
# with patch('ditto_foundation.config.get_settings') as mock:
#     ...
```

---

## 六、回滚策略

### 6.1 兼容层策略

```python
# packages/foundation/src/ditto_foundation/config/__init__.py

from ditto_foundation.config.provider import ConfigProvider
from ditto_foundation.config.settings import Settings, get_settings

__all__ = [
    "ConfigProvider",  # ✅ 新增
    "Settings",
    "get_settings",   # ⚠️ 标记为废弃
]

# 保留 get_settings() 作为兼容层
# 所有新代码必须使用 DI 注入
```

### 6.2 迁移检查清单

```bash
# 1. 确认无直接 get_settings() 调用（除测试）
! grep -r "get_settings()" packages/*/src --include="*.py" | grep -v test

# 2. 确认所有组件都通过 DI 注入配置
pixi run -e dev type

# 3. 运行完整测试
pixi run -e dev ci
```

---

## 七、实施步骤

### Week 1：Foundation 层改造
1. 创建 `ConfigProvider`
2. 修改 `Settings.__init__`
3. 更新 `__init__.py`
4. 添加单元测试

### Week 2：应用层改造
1. 更新 `AppProvider`
2. 更新 `DataHubProvider`
3. 更新其他 Provider
4. 更新集成测试

### Week 3：移除全局访问
1. 标记 `get_settings()` 废弃
2. 移除直接调用（除测试）
3. 添加迁移文档
4. 更新 README 和示例

---

## 八、总结

### 核心优势

| 方面 | 改进 |
|------|------|
| **统一性** | ✅ 所有配置通过 ConfigProvider 统一加载 |
| **一致性** | ✅ 遵循既定环境规范 |
| **可测试性** | ✅ 所有配置都可注入测试 |
| **可维护性** | ✅ 配置加载逻辑集中管理 |
| **扩展性** | ✅ 新增配置只需修改 ConfigProvider |

### 保持兼容

- ✅ 保留 `get_settings()` 作为兼容层（标记废弃）
- ✅ 环境文件结构完全不变
- ✅ 各个 Settings 类定义不变
- ✅ 支持渐进式迁移
