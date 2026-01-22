# 架构问题详细修复方案

**日期**: 2026-01-21
**版本**: v1.0

---

## 问题 1：移除 datahub → core 反向依赖

### 问题分析

**当前状态**:
```python
# packages/datahub/src/ditto_datahub/models/__init__.py:3-28
# Re-export DQ models from Core Layer for backward compatibility
from ditto_core.quality.spec import (
    ColumnRule, CompletenessRule, ConsistencyRule,
    DatasetRules, DQIssue, DQLevel, DQResult, DQSeverity,
    DQSpec, ExpressionRule, ForeignKeyRule, ...
)
```

**问题**:
- datahub (数据层) 导入了 core (业务层) 的类型
- 注释说 "for backward compatibility"，但这是**架构违规**
- datahub 层**不需要** core 层的 DQ 类型

### 影响范围检查

经过代码搜索，`datahub` 层**没有实际使用**这些重导出的类型：

| datahub 层文件 | 使用类型 | 来源 |
|---------------|---------|------|
| `runtime/dq_rules.py` | `DQSeverity` | ✅ `models.common` (本层) |
| `models/common.py` | `DQSeverity` | ✅ 自定义 |
| 测试文件 | `OnDuplicate`, `Dataset` | ✅ `models.common` (本层) |
| Store 文件 | `OnDuplicate`, `WriteResult` | ✅ `models.storage` (本层) |

**结论**: datahub 层完全不使用 core 层的 DQ 类型，可以安全删除重导出。

### 修复方案

**步骤 1**: 删除 datahub/models/__init__.py 中的重导出

```python
# packages/datahub/src/ditto_datahub/models/__init__.py
"""DataHub models for data transfer objects."""

# ❌ 删除以下内容:
# from ditto_core.quality.spec import (...)

# ✅ 只保留本层定义的类型
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
    "FreezeManifest",
    "IngestionCursor",
    "IngestionLog",
    "IngestionStatus",
    "NotTradingDayError",
    "OnDuplicate",
    "Source",
    "WriteResult",
    "WriteResultStore",
]
```

**步骤 2**: 如果 core 层需要使用 datahub 的类型，通过接口隔离

```python
# 新建: packages/core/src/ditto_core/quality/types.py
"""Core 层使用的 DQ 类型定义."""

from ditto_datahub.models.common import DQSeverity

__all__ = ["DQSeverity"]
```

### 验证命令

```bash
# 1. 确认无 datahub → core 导入
grep -r "from ditto_core" packages/datahub/src --include="*.py"

# 2. 运行测试
pixi run -e dev test packages/datahub/tests

# 3. 类型检查
pixi run -e dev type
```

---

## 问题 2：Settings 单例 vs 依赖注入

### 业界最佳实践分析

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **全局单例** | 简单、全局访问 | 隐藏依赖、难测试 | 小型应用 |
| **依赖注入** | 显式依赖、易测试 | 初始化复杂 | 中大型应用 |
| **混合模式** | 兼顾两者 | 需要容器管理 | **推荐** |

### 当前实现分析

```python
# packages/foundation/src/ditto_foundation/config/settings.py:256-267
def get_settings() -> Settings:
    """获取全局配置实例 (单例模式)."""
    return SettingsManager.get()
```

**问题**:
- `core/quality/config.py:70` 使用延迟导入访问 `get_settings()`
- 这是**循环依赖**的征兆

### 业界最佳实践（推荐）

**方案 A: 容器管理的单例 + DI 注入**（推荐）

```python
# foundation 层: 保持单例，但通过容器暴露
class SettingsProvider(Provider):
    """Settings Provider (应用级单例)."""

    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        """提供 Settings 单例."""
        return get_settings()

# apps/port/src/ditto_port/registry/app.py
class AppProvider(Provider):
    """应用级 Provider."""

    @provide
    def observability(self, settings: Settings) -> Iterator[None]:
        """初始化 Observability (依赖注入 Settings)."""
        init(
            service_name="ditto-server",
            environment=settings.system.ditto_env.value,
            log_level="DEBUG" if settings.system.ditto_env.is_development else "INFO",
            # ...
        )
        yield
        shutdown()
```

**方案 B: 配置对象传递**（更简单）

```python
# core/quality/config.py
@dataclass(frozen=True)
class DQConfig:
    """DQ 配置 (POCO 对象)."""
    env: str
    rules_dir: str
    quarantine_enabled: bool = True
    # ...

class QualityEngine:
    """质量引擎 (依赖注入配置)."""

    def __init__(self, config: DQConfig) -> None:
        self._config = config

    def get_rules_paths(self, dataset: str) -> list[Path]:
        """获取规则路径 (无需 get_settings())."""
        env = self._config.env  # 直接使用，无循环依赖
        paths = [
            Path(f"config/{env}/dq_rules/{dataset}.yml"),
            self._config.rules_dir / f"{dataset}.yml",
        ]
        return [p for p in paths if p.exists()]
```

### 修复方案（推荐方案 B - 更简单）

**步骤 1**: 将 DQSettings 改为 POCO 配置对象

```python
# packages/core/src/ditto_core/quality/config.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class DQConfig:
    """
    DQ 配置 (纯配置对象，无隐藏依赖).

    通过构造函数注入，而非 get_settings()。
    """
    env: str  # 显式依赖，不再延迟导入
    rules_dir: str = "config/default/dq_rules"
    quarantine_enabled: bool = True
    quarantine_path: str = "data/quarantine"

    @property
    def rules_path(self) -> Path:
        """获取规则目录路径."""
        return Path(self.rules_dir)

    def get_rules_paths(self, dataset: str) -> list[Path]:
        """
        获取规则文件路径 (优先级顺序).

        无需 get_settings()，避免循环依赖。
        """
        paths: list[Path] = []

        # 1. 环境特定
        env_rules = Path(f"config/{self.env}/dq_rules/{dataset}.yml")
        if env_rules.exists():
            paths.append(env_rules)

        # 2. 默认
        default_rules = self.rules_path / f"{dataset}.yml"
        if default_rules.exists():
            paths.append(default_rules)

        # 3. 包内回退
        package_dir = Path(__file__).parent.parent.parent / "config" / "dq_rules"
        package_rules = package_dir / f"{dataset}.yml"
        if package_rules.exists():
            paths.append(package_rules)

        return paths
```

**步骤 2**: 在 DI 容器中配置

```python
# apps/port/src/ditto_port/registry/app.py
from dishka import Provider, provide
from ditto_core.quality.config import DQConfig
from ditto_foundation.config import get_settings

class AppProvider(Provider):
    """应用级 Provider."""

    @provide
    def dq_config(self) -> DQConfig:
        """创建 DQ 配置 (依赖注入)."""
        settings = get_settings()
        return DQConfig(
            env=settings.system.ditto_env.value,
            rules_dir=settings.system.data_root / "config" / "dq_rules",
        )
```

**步骤 3**: 在 core 层使用配置对象

```python
# packages/core/src/ditto_core/quality/engine.py
class QualityEngine:
    """质量引擎."""

    def __init__(self, config: DQConfig) -> None:
        """初始化 (依赖注入配置)."""
        self._config = config
```

### 对比总结

| 方案 | 循环依赖 | 隐藏依赖 | 易测试性 | 实现复杂度 |
|------|---------|---------|---------|-----------|
| 当前 (延迟导入) | ⚠️ 是 | ⚠️ 是 | ❌ 低 | 低 |
| 方案 A (DI 容器) | ✅ 否 | ✅ 否 | ✅ 高 | 中 |
| 方案 B (配置对象) | ✅ 否 | ✅ 否 | ✅ 高 | 低 |

**推荐**: 方案 B (配置对象) - 最简单，最符合 Python 风格

---

## 问题 3：暴露核心模块公共 API

### 当前状态

| 模块 | 状态 | 需要暴露 |
|------|------|----------|
| `ditto_core/__init__.py` | `__all__ = []` | ✅ QualityEngine |
| `ditto_core/quality/__init__.py` | ✅ 已暴露 | - |
| `ditto_core/engine/__init__.py` | 空 | ✅ RegimeEngine, FactorEngine |
| `ditto_core/strategy/__init__.py` | 空 | ✅ 策略基类 |
| `ditto_core/portfolio/__init__.py` | 空 | ✅ PortfolioManager |

### 修复方案

**步骤 1**: 暴露 core 主模块 API

```python
# packages/core/src/ditto_core/__init__.py
"""
Ditto 核心模块.

包含量化系统的核心业务逻辑:
- QualityEngine: 数据质量检查引擎
- 策略引擎: RegimeEngine, FactorEngine (规划中)
- 投资组合管理: PortfolioManager (规划中)
"""

from ditto_core.quality import (
    DQIssue,
    DQLevel,
    DQReportGenerator,
    DQResult,
    DQSeverity,
    DQSpec,
    DatasetRules,
    QualityEngine,
)

__all__ = [
    # Data Quality
    "DQIssue",
    "DQLevel",
    "DQReportGenerator",
    "DQResult",
    "DQSeverity",
    "DQSpec",
    "DatasetRules",
    "QualityEngine",
    # TODO: 添加其他核心模块
    # "RegimeEngine",
    # "FactorEngine",
    # "PortfolioManager",
]
```

**步骤 2**: 为其他模块添加占位符

```python
# packages/core/src/ditto_core/engine/__init__.py
"""
策略引擎模块.

TODO: 实现后更新此文件
"""

__all__: list[str] = []  # 占位符，表明模块存在但未实现
```

**步骤 3**: 更新文档

```markdown
# packages/core/README.md

## 公共 API

### 数据质量
```python
from ditto_core import QualityEngine, DQResult

engine = QualityEngine(config)
result: DQResult = engine.check(df, rules)
```

### 策略引擎 (规划中)
- RegimeEngine: 市场状态识别
- FactorEngine: 因子计算

### 投资组合 (规划中)
- PortfolioManager: 组合管理
```

---

## 问题 4：详细说明

### 修复优先级

| PR | 目标 | 工作量 | 风险 |
|----|------|--------|------|
| **PR-1** | 移除 datahub → core 反向依赖 | L (0.5天) | 低 |
| **PR-2** | 消除 core/quality 循环依赖 | M (1天) | 中 |
| **PR-3** | 暴露核心模块公共 API | L (0.5天) | 低 |

### PR-1 详细步骤

```bash
# 1. 修改 datahub/models/__init__.py
# 删除 from ditto_core.quality.spec 导入
# 删除相关 __all__ 导出

# 2. 运行验证
pixi run -e dev test packages/datahub/tests
pixi run -e dev type

# 3. 提交
git add packages/datahub/src/ditto_datahub/models/__init__.py
git commit -m "fix(datahub): remove reverse dependency on core layer

- Delete re-export of ditto_core.quality.types
- datahub layer only uses its own DQSeverity from models.common
- Fixes architecture violation: datahub → core

BREAKING_CHANGE: Import DQ types from ditto_core.quality instead"
```

### PR-2 详细步骤

```bash
# 1. 创建新的配置对象
# packages/core/src/ditto_core/quality/config.py
# 修改 DQSettings → DQConfig (POCO)

# 2. 更新 DI 容器配置
# apps/port/src/ditto_port/registry/app.py
# 添加 dq_config provider

# 3. 更新测试
# 修改测试中使用 DQConfig 的地方

# 4. 验证
pixi run -e dev test packages/core/tests
pixi run -e dev type

# 5. 提交
git commit -m "refactor(core): use POCO config instead of get_settings()

- Replace DQSettings with DQConfig (frozen dataclass)
- Inject config via DI container instead of lazy import
- Eliminates circular dependency between core and foundation

BREAKING_CHANGE: Use DQConfig injected via DI"
```

### PR-3 详细步骤

```bash
# 1. 更新 core/__init__.py
# 暴露 QualityEngine 等公共 API

# 2. 更新文档
# 添加 packages/core/README.md

# 3. 验证
pixi run -e dev type

# 4. 提交
git commit -m "docs(core): expose public APIs in __init__.py

- Add QualityEngine to ditto_core exports
- Add placeholder exports for engine/strategy/portfolio
- Update core package documentation"
```

---

## 验证清单

### 架构合规性

```bash
# 检查 datahub → core 依赖
! grep -r "from ditto_core" packages/datahub/src --include="*.py"

# 检查延迟导入
! grep -r "# noqa: PLC0415" packages/*/src --include="*.py"

# 检查空导出
! grep -r '__all__: list\[str\] = \[\]' packages/core/src/ditto_core --include="*.py"
```

### 完整 CI 检查

```bash
# 完整验证流程
pixi run -e dev ci

# 应该全部通过:
# - lint: All checks passed
# - type: 0 errors, 0 warnings
# - test: 所有测试通过
```

---

## 参考资料

### 业界最佳实践

1. **Settings 管理模式**:
   - [FastAPI Settings](https://fastapi.tiangolo.com/advanced/settings/)
   - [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
   - [Dishka Dependency Injection](https://github.com/reagento/dishka)

2. **分层架构**:
   - [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
   - [Domain-Driven Design](https://www.domainlanguage.com/ddd/)

3. **Python 包设计**:
   - [Python Packaging User Guide](https://packaging.python.org/)
   - [PEP 484 -- Type Hints](https://peps.python.org/pep-0484/)
