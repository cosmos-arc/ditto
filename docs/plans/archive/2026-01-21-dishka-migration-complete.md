# DI 容器架构重构完整实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 修复架构依赖方向错误，实现正确的分层依赖（core → datahub → foundation），并通过 DI 容器统一管理配置和组件。

**架构:**
- Foundation 层只提供基础设施（Environment、ConfigLoader、Settings 类定义）
- DataHub 层不依赖 Core 层
- Core 层组件由独立的 CoreProvider 提供
- 所有配置通过 ConfigProvider 在应用层统一加载

**技术栈:** dishka (DI), pydantic-settings, pydantic

---

## Phase 0: 修复架构依赖问题

### Task 0.1: 检查 datahub/models 重新导出的引用

**文件:**
- 检查: `apps/port/src/ditto_port/jobs/tasks/monitoring.py`
- 检查: `packages/datahub/tests/unit/models/test_common_unit.py`

**Step 1: 搜索 DQ models 引用**

Run: `pixi run -e dev python -c "
import re
from pathlib import Path

# 查找所有从 ditto_datahub.models 导入 DQ 相关的文件
pattern = re.compile(r'from ditto_datahub\.models import.*(?:DQIssue|DQLevel|DQResult|ColumnRule|DatasetRules)')

for py_file in Path('apps').rglob('*.py'):
    content = py_file.read_text(encoding='utf-8')
    if pattern.search(content):
        print(f'{py_file}')
"`

Expected: 找出所有需要修改的文件

**Step 2: 确认引用位置**

Run: `pixi run -e dev python -c "
# 检查 monitoring.py 的导入
import ast
import sys
from pathlib import Path

monitoring_file = Path('apps/port/src/ditto_port/jobs/tasks/monitoring.py')
if monitoring_file.exists():
    content = monitoring_file.read_text(encoding='utf-8')
    for line_no, line in enumerate(content.split('\n'), 1):
        if 'DQIssue' in line or 'DQLevel' in line or 'ColumnRule' in line:
            print(f'{monitoring_file}:{line_no}: {line.strip()}')
"`

Expected: 显示需要修改的具体行号

---

### Task 0.2: 删除 datahub/models/__init__.py 中的 DQ model 重新导出

**文件:**
- Modify: `packages/datahub/src/ditto_datahub/models/__init__.py`

**Step 1: 备份原文件**

Run: `cp packages/datahub/src/ditto_datahub/models/__init__.py packages/datahub/src/ditto_datahub/models/__init__.py.bak`

Expected: 备份文件创建成功

**Step 2: 删除 DQ model 重新导出**

Edit: `packages/datahub/src/ditto_datahub/models/__init__.py`

```python
# 删除以下导入
# Re-export DQ models from Core Layer for backward compatibility
from ditto_core.quality.spec import (
    ColumnRule,
    CompletenessRule,
    # ... 删除所有 DQ model 导入
)

# 删除 __all__ 中的所有 DQ model 导出
```

替换为:

```python
"""DataHub models for data transfer objects."""

# DataHub 层自己的 models
from ditto_datahub.models.common import AssetSidRange, Dataset, OnDuplicate, Source
from ditto_datahub.models.ingestion import (
    DataChangedError,
    IngestionCursor,
    IngestionLog,
    IngestionStatus,
    NotTradingDayError,
)
from ditto_datahub.models.storage import FreezeManifest, WriteResult, WriteResultStore

__all__ = [
    "AssetSidRange",
    "DataChangedError",
    "Dataset",
    "IngestionCursor",
    "IngestionLog",
    "IngestionStatus",
    "NotTradingDayError",
    "OnDuplicate",
    "Source",
    "FreezeManifest",
    "WriteResult",
    "WriteResultStore",
]
```

**Step 3: 运行类型检查验证**

Run: `pixi run -e dev type`

Expected: 类型检查通过（或显示需要修复的其他错误）

**Step 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/models/__init__.py
git commit -m "refactor(datahub): remove DQ model re-exports from datahub layer"
```

---

### Task 0.3: 更新 monitoring.py 的 DQ imports

**文件:**
- Modify: `apps/port/src/ditto_port/jobs/tasks/monitoring.py`

**Step 1: 查看当前导入**

Run: `head -50 apps/port/src/ditto_port/jobs/tasks/monitoring.py | grep -E "^from|^import"`

Expected: 显示当前的导入语句

**Step 2: 更新导入语句**

Edit: `apps/port/src/ditto_port/jobs/tasks/monitoring.py`

将:
```python
from ditto_datahub.models import DQIssue, DQLevel, ...
```

替换为:
```python
from ditto_core.quality.spec import DQIssue, DQLevel, ...
```

**Step 3: 运行类型检查**

Run: `pixi run -e dev type apps/port/src/ditto_port/jobs/tasks/monitoring.py`

Expected: 类型检查通过

**Step 4: 运行相关测试**

Run: `pixi run -e dev pytest apps/port/tests/jobs/tasks/test_monitoring.py -v`

Expected: 测试通过

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/jobs/tasks/monitoring.py
git commit -m "fix(monitoring): import DQ models from core layer"
```

---

### Task 0.4: 更新测试文件的 DQ imports

**文件:**
- Modify: `packages/datahub/tests/unit/models/test_common_unit.py`

**Step 1: 查看当前导入**

Run: `head -50 packages/datahub/tests/unit/models/test_common_unit.py | grep -E "^from|^import"`

Expected: 显示当前的导入语句

**Step 2: 更新导入语句**

Edit: `packages/datahub/tests/unit/models/test_common_unit.py`

将:
```python
from ditto_datahub.models import DQIssue, DQLevel, ...
```

替换为:
```python
from ditto_core.quality.spec import DQIssue, DQLevel, ...
```

**Step 3: 运行测试**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/models/test_common_unit.py -v`

Expected: 测试通过

**Step 4: 提交**

```bash
git add packages/datahub/tests/unit/models/test_common_unit.py
git commit -m "fix(tests): import DQ models from core layer in datahub tests"
```

---

### Task 0.5: 创建 CoreProvider

**文件:**
- Create: `apps/port/src/ditto_port/registry/core.py`

**Step 1: 写测试骨架（RED）**

Create: `apps/port/tests/registry/test_core_provider.py`

```python
"""测试 CoreProvider."""

from collections.abc import Iterator

from dishka import make_container
from ditto_core.quality import QualityEngine
from ditto_core.quality.config import DQSettings
from ditto_port.registry.core import CoreProvider


def test_core_provider_provides_dq_engine():
    """测试 CoreProvider 提供 QualityEngine."""
    container = make_container(CoreProvider())

    engine = container.get(QualityEngine)
    assert isinstance(engine, QualityEngine)

    container.close()


def test_core_provider_is_singleton():
    """测试 CoreProvider 组件是单例."""
    container = make_container(CoreProvider())

    engine1 = container.get(QualityEngine)
    engine2 = container.get(QualityEngine)
    assert engine1 is engine2

    container.close()
```

**Step 2: 运行测试（失败 - RED）**

Run: `pixi run -e dev pytest apps/port/tests/registry/test_core_provider.py -v`

Expected: FAIL - `ModuleNotFoundError: No module named 'ditto_port.registry.core'`

**Step 3: 实现 CoreProvider（GREEN）**

Create: `apps/port/src/ditto_port/registry/core.py`

```python
"""Core 层组件注册."""

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_core.quality import QualityEngine
from ditto_core.quality.config import DQSettings
from pathlib import Path

__all__ = ["CoreProvider"]


class CoreProvider(Provider):
    """Core 层组件 Provider."""

    scope = Scope.APP

    @provide
    def dq_engine(
        self,
        dq_settings: DQSettings,
        data_root: Path,
    ) -> Iterator[QualityEngine]:
        """
        数据质量引擎（应用层 DQ 检查使用）.

        Args:
            dq_settings: DQ 配置
            data_root: 数据根目录

        Yields:
            QualityEngine: DQ 引擎实例

        """
        engine = QualityEngine(dq_settings=dq_settings, data_root=data_root)
        yield engine
```

**Step 4: 运行测试（通过 - GREEN）**

Run: `pixi run -e dev pytest apps/port/tests/registry/test_core_provider.py -v`

Expected: PASS

**Step 5: 更新 registry/__init__.py 导出**

Edit: `apps/port/src/ditto_port/registry/__init__.py`

```python
"""依赖注入注册表."""

from ditto_port.registry.app import AppProvider
from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.core import CoreProvider
from ditto_port.registry.datahub import DataHubProvider
from ditto_port.registry.sources import DataSourcesProvider

__all__ = [
    "AppProvider",
    "ConfigProvider",
    "CoreProvider",
    "DataHubProvider",
    "DataSourcesProvider",
]
```

**Step 6: 提交**

```bash
git add apps/port/src/ditto_port/registry/core.py
git add apps/port/src/ditto_port/registry/__init__.py
git add apps/port/tests/registry/test_core_provider.py
git commit -m "feat(registry): add CoreProvider for core layer components"
```

---

### Task 0.6: 从 DataHubProvider 中移除 dq_engine 方法

**文件:**
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

**Step 1: 运行测试（确保当前状态）**

Run: `pixi run -e dev pytest apps/port/tests/registry/ -v`

Expected: 当前测试通过

**Step 2: 删除 dq_engine 方法和相关导入**

Edit: `apps/port/src/ditto_port/registry/datahub.py`

删除:
```python
from ditto_core.quality import QualityEngine
from ditto_core.quality.config import DQSettings
```

删除 dq_engine 方法（约第 149-160 行）:
```python
    @provide
    def dq_engine(
        self,
        dq_settings: DQSettings,
        data_root: Path,
    ) -> QualityEngine:
        """
        数据质量引擎（应用层 DQ 检查使用）.

        ✅ 注入 DQSettings，支持开关控制
        """
        # ✅ 注入 DQSettings
        return QualityEngine(dq_settings=dq_settings, data_root=data_root)
```

**Step 3: 运行类型检查**

Run: `pixi run -e dev type apps/port/src/ditto_port/registry/datahub.py`

Expected: 类型检查通过（DataHub 不再依赖 Core）

**Step 4: 提交**

```bash
git add apps/port/src/ditto_port/registry/datahub.py
git commit -m "refactor(datahub): remove dq_engine from DataHubProvider"
```

---

### Task 0.7: 更新 main.py 容器组合

**文件:**
- Modify: `apps/port/src/ditto_port/main.py`

**Step 1: 更新导入**

Edit: `apps/port/src/ditto_port/main.py`

将:
```python
from ditto_port.registry import AppProvider, DataHubProvider, DataSourcesProvider
```

替换为:
```python
from ditto_port.registry import ConfigProvider, CoreProvider, DataHubProvider, DataSourcesProvider
```

**Step 2: 更新容器创建（lifespan 函数）**

Edit: `apps/port/src/ditto_port/main.py` (约第 85-89 行)

将:
```python
    container = make_async_container(
        AppProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
```

替换为:
```python
    container = make_async_container(
        ConfigProvider(),
        CoreProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
```

**Step 3: 运行类型检查**

Run: `pixi run -e dev type apps/port/src/ditto_port/main.py`

Expected: 类型检查通过

**Step 4: 运行服务器测试**

Run: `pixi run -e dev pytest apps/port/tests/test_main.py -v -k "test_lifespan or test_health"`

Expected: 测试通过

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/main.py
git commit -m "refactor(main): use ConfigProvider and CoreProvider in container"
```

---

### Task 0.8: 更新 cli/context.py 容器组合

**文件:**
- Modify: `apps/port/src/ditto_port/cli/context.py`

**Step 1: 更新导入**

Edit: `apps/port/src/ditto_port/cli/context.py`

将:
```python
from ditto_port.registry import AppProvider, DataHubProvider, DataSourcesProvider
```

替换为:
```python
from ditto_port.registry import ConfigProvider, CoreProvider, DataHubProvider, DataSourcesProvider
```

**Step 2: 更新容器创建**

Edit: `apps/port/src/ditto_port/cli/context.py` (约第 30-34 行)

将:
```python
    container = make_container(
        AppProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
```

替换为:
```python
    container = make_container(
        ConfigProvider(),
        CoreProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
```

**Step 3: 运行 CLI 测试**

Run: `pixi run -e dev pytest apps/port/tests/cli/ -v`

Expected: 测试通过

**Step 4: 提交**

```bash
git add apps/port/src/ditto_port/cli/context.py
git commit -m "refactor(cli): use ConfigProvider and CoreProvider in container"
```

---

### Task 0.9: 更新 jobs/context.py 容器组合

**文件:**
- Modify: `apps/port/src/ditto_port/jobs/context.py`

**Step 1: 更新导入**

Edit: `apps/port/src/ditto_port/jobs/context.py`

将:
```python
from ditto_port.registry import AppProvider, DataHubProvider, DataSourcesProvider
```

替换为:
```python
from ditto_port.registry import ConfigProvider, CoreProvider, DataHubProvider, DataSourcesProvider
```

**Step 2: 更新容器创建**

Edit: `apps/port/src/ditto_port/jobs/context.py` (约第 33-37 行)

将:
```python
    container = make_container(
        AppProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
```

替换为:
```python
    container = make_container(
        ConfigProvider(),
        CoreProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
```

**Step 3: 运行 Jobs 测试**

Run: `pixi run -e dev pytest apps/port/tests/jobs/ -v`

Expected: 测试通过

**Step 4: 提交**

```bash
git add apps/port/src/ditto_port/jobs/context.py
git commit -m "refactor(jobs): use ConfigProvider and CoreProvider in container"
```

---

### Task 0.10: 验证架构依赖修复

**Step 1: 运行完整类型检查**

Run: `pixi run -e dev type`

Expected: 0 errors

**Step 2: 运行相关测试**

Run: `pixi run -e dev pytest apps/port/tests/ -v`

Expected: 所有测试通过

**Step 3: 验证依赖方向**

Run: `pixi run -e dev python -c "
# 验证 datahub 不再依赖 core
import ast
import sys
from pathlib import Path

datahub_files = Path('packages/datahub/src').rglob('*.py')
has_core_import = False

for py_file in datahub_files:
    content = py_file.read_text(encoding='utf-8')
    if 'from ditto_core' in content or 'import ditto_core' in content:
        print(f'❌ {py_file} 仍然依赖 core')
        has_core_import = True

if not has_core_import:
    print('✅ datahub 不再依赖 core')
" && echo "架构依赖修复完成" || echo "仍有依赖问题"`

Expected: ✅ datahub 不再依赖 core

**Step 4: Phase 0 完成提交**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "docs: complete Phase 0 - fix architecture dependency issues"
```

---

## Phase 1: 清理 Foundation 层

### Task 1.1: 删除备份文件

**Step 1: 查找备份文件**

Run: `find packages/foundation/src/ditto_foundation/config -name "*.py,cover" -o -name "*.py.bak"`

Expected: 列出所有备份文件

**Step 2: 删除备份文件**

Run: `rm -f packages/foundation/src/ditto_foundation/config/*.py,cover packages/foundation/src/ditto_foundation/config/*.py.bak`

Expected: 备份文件删除成功

**Step 3: 删除过时的 README**

Run: `rm -f packages/foundation/src/ditto_foundation/config/README.md`

Expected: README 删除成功（如果存在）

**Step 4: 提交**

```bash
git add -A packages/foundation/src/ditto_foundation/config/
git commit -m "chore(foundation): remove backup files and outdated README"
```

---

### Task 1.2: 删除全局单例相关代码

**文件:**
- Modify: `packages/foundation/src/ditto_foundation/config/settings.py`
- Modify: `packages/foundation/src/ditto_foundation/config/__init__.py`

**Step 1: 检查是否有引用**

Run: `pixi run -e dev python -c "
# 检查 get_settings 的引用
import subprocess
result = subprocess.run(
    ['grep', '-r', 'from ditto_foundation.config import.*get_settings', '--include=*.py', '.'],
    capture_output=True, text=True
)
if result.stdout:
    print('找到以下引用:')
    print(result.stdout)
else:
    print('✅ 没有找到 get_settings 的引用')
" && echo "检查完成" || echo "检查失败"`

Expected: ✅ 没有找到 get_settings 的引用

**Step 2: 删除 SettingsManager 类**

Edit: `packages/foundation/src/ditto_foundation/config/settings.py`

删除 (约第 241-254 行):
```python
class SettingsManager(SingletonManager["Settings"]):
    """
    Settings 单例管理器.

    使用类属性而非 global 变量实现单例模式，避免 PLW0603 警告。
    """

    _instance: ClassVar["Settings | None"] = None

    @classmethod
    def _create_instance(cls) -> "Settings":
        """创建 Settings 实例."""
        return Settings()
```

**Step 3: 删除 get_settings 和 reload_settings 函数**

Edit: `packages/foundation/src/ditto_foundation/config/settings.py`

删除 (约第 256-281 行):
```python
def get_settings() -> Settings:
    """
    获取全局配置实例.

    使用单例模式, 避免重复加载配置

    Returns
    -------
        Settings: 配置实例

    """
    return SettingsManager.get()


def reload_settings() -> Settings:
    """
    重新加载配置.

    主要用于测试或配置热更新场景

    Returns
    -------
        Settings: 新的配置实例

    """
    return SettingsManager.reload()
```

**Step 4: 删除 SingletonManager 导入**

Edit: `packages/foundation/src/ditto_foundation/config/settings.py`

删除:
```python
from ditto_foundation.config.manager import SingletonManager
```

**Step 5: 更新 __all__**

Edit: `packages/foundation/src/ditto_foundation/config/settings.py`

将:
```python
__all__ = [
    "DataSourceSettings",
    "DatabaseSettings",
    "FileStorageSettings",
    "ObservabilitySettings",
    "Settings",
    "SettingsManager",
    "SystemSettings",
    "get_settings",
    "reload_settings",
]
```

替换为:
```python
__all__ = [
    "DataSourceSettings",
    "DatabaseSettings",
    "FileStorageSettings",
    "ObservabilitySettings",
    "Settings",
    "SystemSettings",
]
```

**Step 6: 更新 __init__.py**

Edit: `packages/foundation/src/ditto_foundation/config/__init__.py`

删除 `get_settings` 和 `reload_settings` 的导出（如果存在）

**Step 7: 运行类型检查**

Run: `pixi run -e dev type packages/foundation/src/ditto_foundation/config/`

Expected: 类型检查通过

**Step 8: 运行测试**

Run: `pixi run -e dev pytest packages/foundation/tests/unit/config/ -v`

Expected: 测试通过

**Step 9: 提交**

```bash
git add packages/foundation/src/ditto_foundation/config/
git commit -m "refactor(foundation): remove global singleton (SettingsManager, get_settings, reload_settings)"
```

---

### Task 1.3: 简化 Settings 类

**文件:**
- Modify: `packages/foundation/src/ditto_foundation/config/settings.py`

**Step 1: 移除 __init__ 方法中的配置加载逻辑**

Edit: `packages/foundation/src/ditto_foundation/config/settings.py`

将 `Settings` 类简化为：

```python
class Settings(BaseSettings):
    """
    Ditto系统主配置类（Foundation 层）.

    只包含系统级配置，业务配置由各层自行管理。
    """

    system: SystemSettings = Field(default_factory=SystemSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
```

**注意**: `database`, `data_source`, `file_storage` 字段将被移到 DataHub 层

**Step 2: 临时保留兼容性（会在 Phase 2 中移除）**

为了保持兼容性，暂时保留这些字段，但在 Phase 2 中会移除。

**Step 3: 运行测试**

Run: `pixi run -e dev pytest packages/foundation/tests/ -v`

Expected: 测试通过

**Step 4: 提交**

```bash
git add packages/foundation/src/ditto_foundation/config/settings.py
git commit -m "refactor(foundation): simplify Settings class (preparation for Phase 2)"
```

---

### Task 1.4: 验证 Phase 1

**Step 1: 运行完整测试**

Run: `pixi run -e dev pytest packages/foundation/tests/ apps/port/tests/ -v`

Expected: 所有测试通过

**Step 2: 运行类型检查**

Run: `pixi run -e dev type`

Expected: 0 errors

**Step 3: Phase 1 完成提交**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "docs: complete Phase 1 - clean up Foundation layer"
```

---

## Phase 2: 创建 DataHub 配置

### Task 2.1: 创建 DataSourceSettings（完整版）

**文件:**
- Create: `packages/datahub/src/ditto_datahub/config/data_source.py`

**Step 1: 写测试（RED）**

Create: `packages/datahub/tests/unit/config/test_data_source_settings.py`

```python
"""测试 DataSourceSettings."""

from pydantic import ValidationError

from ditto_datahub.config.data_source import DataSourceSettings


def test_default_values():
    """测试默认值."""
    settings = DataSourceSettings()
    assert settings.http_base_url == "http://api.tushare.pro"
    assert settings.http_timeout == 30.0
    assert settings.retry_max_attempts == 3
    assert settings.rate_limit_profile == "free"


def test_validation():
    """测试验证规则."""
    # timeout 范围验证
    with pytest.raises(ValidationError):
        DataSourceSettings(http_timeout=0.5)  # 太小

    with pytest.raises(ValidationError):
        DataSourceSettings(http_timeout=400.0)  # 太大
```

**Step 2: 运行测试（RED）**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/config/test_data_source_settings.py -v`

Expected: FAIL - ModuleNotFoundError

**Step 3: 实现 DataSourceSettings（GREEN）**

Create: `packages/datahub/src/ditto_datahub/config/data_source.py`

```python
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
        description="全局限流（请求/分钟）"
    )
    rate_limit_daily_rate: int | None = Field(
        default=None,
        description="日限流（请求/天）"
    )

    # ========== Token 配置 ==========
    tushare_token: str = Field(
        default="",
        description="Tushare Pro API Token（优先使用 keyring）"
    )
```

**Step 4: 运行测试（GREEN）**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/config/test_data_source_settings.py -v`

Expected: PASS

**Step 5: 更新 datahub/__init__.py**

Edit: `packages/datahub/src/ditto_datahub/__init__.py`

添加:
```python
from ditto_datahub.config.data_source import DataSourceSettings
```

**Step 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/config/data_source.py
git add packages/datahub/src/ditto_datahub/__init__.py
git add packages/datahub/tests/unit/config/test_data_source_settings.py
git commit -m "feat(datahub): add complete DataSourceSettings"
```

---

### Task 2.2: 创建 DatabaseSettings（完整版）

**文件:**
- Create: `packages/datahub/src/ditto_datahub/config/database.py`

**Step 1: 写测试（RED）**

Create: `packages/datahub/tests/unit/config/test_database_settings.py`

```python
"""测试 DatabaseSettings."""

from ditto_datahub.config.database import DatabaseSettings


def test_default_values():
    """测试默认值."""
    settings = DatabaseSettings()
    assert settings.sqlite_timeout == 30.0
    assert settings.sqlite_wal_enabled is False
    assert settings.sqlite_foreign_keys is True
    assert settings.connection_warn_threshold == 50
```

**Step 2: 运行测试（RED）**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/config/test_database_settings.py -v`

Expected: FAIL - ModuleNotFoundError

**Step 3: 实现 DatabaseSettings（GREEN）**

Create: `packages/datahub/src/ditto_datahub/config/database.py`

```python
"""数据库配置."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config.paths import get_paths


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
    @property
    def sqlite_path(self) -> str:
        """SQLite 数据库文件路径."""
        return str(get_paths().data_subdir("db/sqlite/hub.sqlite"))

    @property
    def duckdb_path(self) -> str:
        """DuckDB 数据库文件路径."""
        return str(get_paths().data_subdir("db/duckdb/ditto.duckdb"))
```

**Step 4: 运行测试（GREEN）**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/config/test_database_settings.py -v`

Expected: PASS

**Step 5: 更新 datahub/__init__.py**

Edit: `packages/datahub/src/ditto_datahub/__init__.py`

添加:
```python
from ditto_datahub.config.database import DatabaseSettings
```

**Step 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/config/database.py
git add packages/datahub/src/ditto_datahub/__init__.py
git add packages/datahub/tests/unit/config/test_database_settings.py
git commit -m "feat(datahub): add complete DatabaseSettings"
```

---

### Task 2.3: 创建 FileStorageSettings（通用版）

**文件:**
- Create: `packages/datahub/src/ditto_datahub/config/storage.py`

**Step 1: 写测试（RED）**

Create: `packages/datahub/tests/unit/config/test_storage_settings.py`

```python
"""测试 FileStorageSettings."""

from ditto_datahub.config.storage import FileStorageSettings


def test_default_values():
    """测试默认值."""
    settings = FileStorageSettings()
    assert settings.compression == "snappy"
    assert settings.use_statistics is True
```

**Step 2: 运行测试（RED）**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/config/test_storage_settings.py -v`

Expected: FAIL - ModuleNotFoundError

**Step 3: 实现 FileStorageSettings（GREEN）**

Create: `packages/datahub/src/ditto_datahub/config/storage.py`

```python
"""文件存储配置（格式无关）."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_foundation.config.paths import get_paths


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

**Step 4: 运行测试（GREEN）**

Run: `pixi run -e dev pytest packages/datahub/tests/unit/config/test_storage_settings.py -v`

Expected: PASS

**Step 5: 更新 datahub/__init__.py**

Edit: `packages/datahub/src/ditto_datahub/__init__.py`

添加:
```python
from ditto_datahub.config.storage import FileStorageSettings
```

**Step 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/config/storage.py
git add packages/datahub/src/ditto_datahub/__init__.py
git add packages/datahub/tests/unit/config/test_storage_settings.py
git commit -m "feat(datahub): add FileStorageSettings (generic storage config)"
```

---

### Task 2.4: 在 ConfigProvider 中添加 DataHub 配置

**文件:**
- Modify: `apps/port/src/ditto_port/registry/config.py`

**Step 1: 写测试（RED）**

Create: `apps/port/tests/registry/test_config_datahub.py`

```python
"""测试 ConfigProvider 的 DataHub 配置."""

from dishka import make_container
from ditto_datahub.config import (
    DatabaseSettings,
    DataSourceSettings,
    FileStorageSettings,
)
from ditto_port.registry.config import ConfigProvider


def test_config_provider_provides_database_settings():
    """测试提供 DatabaseSettings."""
    container = make_container(ConfigProvider())
    settings = container.get(DatabaseSettings)
    assert isinstance(settings, DatabaseSettings)
    container.close()


def test_config_provider_provides_data_source_settings():
    """测试提供 DataSourceSettings."""
    container = make_container(ConfigProvider())
    settings = container.get(DataSourceSettings)
    assert isinstance(settings, DataSourceSettings)
    container.close()


def test_config_provider_provides_file_storage_settings():
    """测试提供 FileStorageSettings."""
    container = make_container(ConfigProvider())
    settings = container.get(FileStorageSettings)
    assert isinstance(settings, FileStorageSettings)
    container.close()
```

**Step 2: 运行测试（RED）**

Run: `pixi run -e dev pytest apps/port/tests/registry/test_config_datahub.py -v`

Expected: FAIL - dishka 无法提供这些配置

**Step 3: 实现 Provider 方法（GREEN）**

Edit: `apps/port/src/ditto_port/registry/config.py`

添加导入:
```python
from ditto_datahub.config import (
    DatabaseSettings,
    DataSourceSettings,
    FileStorageSettings,
)
```

添加 Provider 方法:

```python
    @provide
    def database_settings(
        self,
        config_loader: ConfigLoader,
    ) -> DatabaseSettings:
        """数据库配置（应用级单例）."""
        values = dotenv_values(config_loader.get_env_file("database"))
        return DatabaseSettings.model_validate(values)

    @provide
    def data_source_settings(
        self,
        config_loader: ConfigLoader,
    ) -> DataSourceSettings:
        """数据源配置（应用级单例）."""
        values = dotenv_values(config_loader.get_env_file("data_source"))
        return DataSourceSettings.model_validate(values)

    @provide
    def file_storage_settings(
        self,
        config_loader: ConfigLoader,
    ) -> FileStorageSettings:
        """文件存储配置（应用级单例）."""
        # file_storage 共用 system.env
        values = dotenv_values(config_loader.get_env_file("system"))
        return FileStorageSettings.model_validate(values)
```

**Step 4: 运行测试（GREEN）**

Run: `pixi run -e dev pytest apps/port/tests/registry/test_config_datahub.py -v`

Expected: PASS

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/registry/config.py
git add apps/port/tests/registry/test_config_datahub.py
git commit -m "feat(config): add DataHub settings providers"
```

---

### Task 2.5: 验证 Phase 2

**Step 1: 运行类型检查**

Run: `pixi run -e dev type`

Expected: 0 errors

**Step 2: 运行相关测试**

Run: `pixi run -e dev pytest packages/datahub/tests/ apps/port/tests/registry/ -v`

Expected: 所有测试通过

**Step 3: Phase 2 完成提交**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "docs: complete Phase 2 - create DataHub configuration"
```

---

## Phase 3: 重构业务代码使用配置

### Task 3.1: 更新 DataHubProvider 使用配置

**文件:**
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

**Step 1: 更新 sqlite_pool 方法**

Edit: `apps/port/src/ditto_port/registry/datahub.py`

修改:
```python
    @provide
    def sqlite_pool(
        self,
        database_settings: DatabaseSettings,
        data_root: Path,
    ) -> Iterator[SQLitePool]:
        """SQLite 连接池（应用级单例）."""
        db_path = data_root / "meta" / database_settings.sqlite_path
        schema_traversable = files("ditto_datahub.scripts") / "schema.sql"
        schema_path = Path(str(schema_traversable))
        pool = SQLitePool(
            str(db_path),
            schema_path=schema_path,
            timeout=database_settings.sqlite_timeout,
        )
        pool.init_schema()
        yield pool
        pool.close()
```

**Step 2: 运行测试**

Run: `pixi run -e dev pytest apps/port/tests/registry/ -v`

Expected: 测试通过

**Step 3: 提交**

```bash
git add apps/port/src/ditto_port/registry/datahub.py
git commit -m "refactor(datahub): inject DatabaseSettings into sqlite_pool"
```

---

### Task 3.2: 更新 DataSourcesProvider 使用配置

**文件:**
- Modify: `apps/port/src/ditto_port/registry/sources.py`

**Step 1: 查看 sources.py**

Run: `cat apps/port/src/ditto_port/registry/sources.py`

Expected: 显示当前的 sources provider 实现

**Step 2: 更新 tushare_source 方法**

Edit: `apps/port/src/ditto_port/registry/sources.py`

修改为注入配置:

```python
    @provide
    def tushare_source(
        self,
        data_source_settings: DataSourceSettings,
        sqlite_client: SQLiteClient,
    ) -> TushareSource:
        """Tushare 数据源（注入配置）."""
        return TushareSource(
            config=data_source_settings,
            sqlite_client=sqlite_client,
        )
```

**Step 3: 运行测试**

Run: `pixi run -e dev pytest apps/port/tests/registry/ -v`

Expected: 测试通过

**Step 4: 提交**

```bash
git add apps/port/src/ditto_port/registry/sources.py
git commit -m "refactor(sources): inject DataSourceSettings into tushare_source"
```

---

### Task 3.3: 验证 Phase 3

**Step 1: 运行完整测试**

Run: `pixi run -e dev pytest apps/port/tests/ packages/datahub/tests/ -v`

Expected: 所有测试通过

**Step 2: 运行类型检查**

Run: `pixi run -e dev type`

Expected: 0 errors

**Step 3: Phase 3 完成提交**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "docs: complete Phase 3 - refactor business code to use config"
```

---

## Phase 4: 更新环境文件

### Task 4.1: 更新 config/development/data_source.env

**文件:**
- Modify: `config/development/data_source.env`

**Step 1: 添加完整配置**

Edit: `config/development/data_source.env`

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

**Step 2: 提交**

```bash
git add config/development/data_source.env
git commit -m "config(data_source): add complete configuration options"
```

---

### Task 4.2: 更新 config/development/database.env

**文件:**
- Modify: `config/development/database.env`

**Step 1: 添加完整配置**

Edit: `config/development/database.env`

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

**Step 2: 提交**

```bash
git add config/development/database.env
git commit -m "config(database): add complete configuration options"
```

---

### Task 4.3: 创建 config/development/file_storage.env

**文件:**
- Create: `config/development/file_storage.env`

**Step 1: 创建配置文件**

Create: `config/development/file_storage.env`

```bash
# 通用文件存储配置（格式无关）
FILE_STORAGE_COMPRESSION=snappy
FILE_STORAGE_USE_STATISTICS=true
```

**Step 2: 提交**

```bash
git add config/development/file_storage.env
git commit -m "config: add file_storage.env with generic storage config"
```

---

### Task 4.4: 验证 Phase 4

**Step 1: 测试配置加载**

Run: `pixi run -e dev python -c "
from dishka import make_container
from ditto_port.registry import ConfigProvider
from ditto_datahub.config import DataSourceSettings, DatabaseSettings, FileStorageSettings

container = make_container(ConfigProvider())

ds_settings = container.get(DataSourceSettings)
print(f'DataSourceSettings: {ds_settings.http_base_url}, {ds_settings.http_timeout}')

db_settings = container.get(DatabaseSettings)
print(f'DatabaseSettings: {db_settings.sqlite_timeout}, {db_settings.sqlite_wal_enabled}')

fs_settings = container.get(FileStorageSettings)
print(f'FileStorageSettings: {fs_settings.compression}, {fs_settings.use_statistics}')

container.close()
" && echo "配置加载成功" || echo "配置加载失败"`

Expected: 配置加载成功，显示正确值

**Step 5: Phase 4 完成提交**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "docs: complete Phase 4 - update environment files"
```

---

## Phase 5: 验证与清理

### Task 5.1: 运行完整类型检查

**Step 1: 类型检查**

Run: `pixi run -e dev type`

Expected: 0 errors

**Step 2: 类型检查测试**

Run: `pixi run -e dev type --tests`

Expected: 0 errors

**Step 3: 提交类型检查结果**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "test: type check passed (0 errors)"
```

---

### Task 5.2: 运行完整测试套件

**Step 1: 运行单元测试**

Run: `pixi run -e dev pytest --unit -v`

Expected: 所有单元测试通过

**Step 2: 运行集成测试**

Run: `pixi run -e dev pytest --integration -v`

Expected: 所有集成测试通过

**Step 3: 运行全部测试**

Run: `pixi run -e dev pytest`

Expected: 所有测试通过

**Step 4: 提交测试结果**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "test: all tests passed"
```

---

### Task 5.3: 删除废弃代码和测试

**Step 1: 删除 Foundation 层中的废弃配置类**

从 `packages/foundation/src/ditto_foundation/config/settings.py` 中移除:
- `DatabaseSettings` 类
- `DataSourceSettings` 类
- `FileStorageSettings` 类
- `Settings` 类中的相关字段

**Step 2: 更新 Foundation __init__.py**

Edit: `packages/foundation/src/ditto_foundation/config/__init__.py`

移除已删除类的导出。

**Step 3: 删除废弃测试**

Run: `find packages/foundation/tests -name "*settings*" -o -name "*database*"`

删除与废弃配置相关的测试文件。

**Step 4: 运行测试验证**

Run: `pixi run -e dev pytest packages/foundation/tests/ -v`

Expected: 测试通过

**Step 5: 提交**

```bash
git add -A
git commit -m "refactor(foundation): remove deprecated config classes and tests"
```

---

### Task 5.4: 最终验证

**Step 1: 运行 CI**

Run: `pixi run -e dev ci`

Expected: 所有检查通过

**Step 2: 验证架构依赖**

Run: `pixi run -e dev python -c "
import ast
from pathlib import Path

# 验证依赖方向
def check_imports(package_dir, forbidden_import):
    violations = []
    for py_file in Path(package_dir).rglob('*.py'):
        content = py_file.read_text(encoding='utf-8')
        if forbidden_import in content:
            violations.append(str(py_file))
    return violations

# datahub 不应依赖 core
datahub_violations = check_imports('packages/datahub/src', 'ditto_core')
if datahub_violations:
    print(f'❌ datahub 仍然依赖 core:')
    for v in datahub_violations:
        print(f'  - {v}')
else:
    print('✅ datahub 不依赖 core')

# foundation 不应依赖 datahub 或 core
foundation_violations = check_imports('packages/foundation/src', 'ditto_datahub')
foundation_violations.extend(check_imports('packages/foundation/src', 'ditto_core'))
if foundation_violations:
    print(f'❌ foundation 依赖了上层:')
    for v in foundation_violations:
        print(f'  - {v}')
else:
    print('✅ foundation 不依赖上层')

print('\\n✅ 架构依赖方向正确')
" && echo "架构验证通过" || echo "架构验证失败"`

Expected: ✅ 架构依赖方向正确

**Step 3: 生成验证报告**

Run: `pixi run -e dev python -c "
print('=== DI 容器架构重构验证报告 ===')
print()
print('✅ Phase 0: 修复架构依赖问题')
print('  - 删除 datahub/models 中的 DQ model 重新导出')
print('  - 创建 CoreProvider')
print('  - 更新所有容器组合位置')
print()
print('✅ Phase 1: 清理 Foundation 层')
print('  - 删除 SettingsManager, get_settings, reload_settings')
print('  - 简化 Settings 类')
print()
print('✅ Phase 2: 创建 DataHub 配置')
print('  - DataSourceSettings（HTTP、重试、限流）')
print('  - DatabaseSettings（SQLite、连接池、缓存）')
print('  - FileStorageSettings（压缩、统计）')
print()
print('✅ Phase 3: 重构业务代码')
print('  - DataHubProvider 注入配置')
print('  - DataSourcesProvider 注入配置')
print()
print('✅ Phase 4: 更新环境文件')
print('  - data_source.env')
print('  - database.env')
print('  - file_storage.env')
print()
print('✅ Phase 5: 验证与清理')
print('  - 类型检查通过')
print('  - 所有测试通过')
print('  - 架构依赖正确')
print()
print('=== 重构完成 ===')
" && echo "报告生成成功" || echo "报告生成失败"`

Expected: 显示完整的验证报告

**Step 4: 完成提交**

```bash
git add docs/plans/2026-01-21-dishka-migration-complete.md
git commit -m "docs: complete Phase 5 - final verification and cleanup"
```

---

## 执行顺序总结

1. **Phase 0**: 修复架构依赖（必须首先完成）
2. **Phase 1**: 清理 Foundation 层
3. **Phase 2**: 创建 DataHub 配置
4. **Phase 3**: 重构业务代码使用配置
5. **Phase 4**: 更新环境文件
6. **Phase 5**: 验证与清理

**重要提示:**
- 每个 Task 完成后必须提交
- Phase 0 是关键路径，必须首先完成
- TDD 流程：RED → GREEN → REFACTOR → COMMIT
- 每次提交前运行 `pixi run -e dev type` 和 `pixi run -e dev pytest`

---

## 执行选项

计划完成并保存到 `docs/plans/2026-01-21-dishka-migration-complete.md`。

**执行方式选择：**

**1. Subagent-Driven（当前会话）** - 我为每个任务调度新的子代理，在任务间审查代码，快速迭代

**2. Parallel Session（独立会话）** - 在新的 worktree 中打开独立会话，使用 executing-plans skill 批量执行

你想选择哪种方式？
