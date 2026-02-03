# PR-2：通过 DI 容器注入 DQSettings（保持全局配置规范一致）

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


**日期**: 2026-01-21
**目标**: 消除 core/quality 循环依赖，复用现有 DQSettings

---

## 问题分析

### 当前状态

```python
# packages/core/src/ditto_core/quality/config.py
class DQSettings(BaseSettings):
    """DQ configuration settings."""
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
    )
    rules_dir: str = "config/default/dq_rules"
    # ...

    def get_rules_paths(self, dataset: str, env: str | None = None) -> list[Path]:
        """❌ 问题：env=None 时需要延迟导入 get_settings()"""
        if env is None:
            from ditto_foundation.config import get_settings  # noqa: PLC0415
            settings = get_settings()
            env = settings.system.ditto_env.value  # 循环依赖！
        # ...
```

### 依赖链

```
core/quality/config.py
  → 延迟导入 → foundation/config (get_settings)
  → 正常导入 ← foundation (可能通过其他路径)
```

---

## 解决方案：DI 容器注入 DQSettings

### 架构设计

保持与全局配置规范一致：

```
┌─────────────────────────────────────────────────────────┐
│              DI 容器 (Dishka)                           │
│                                                         │
│  AppProvider.datahub_provider.dq_settings               │
│    ↓                                                    │
│  使用 get_settings() 获取环境                           │
│    ↓                                                    │
│  创建 DQSettings(env=...) 实例                          │
│    ↓                                                    │
│  注入到 QualityEngine                                   │
└─────────────────────────────────────────────────────────┘

保持一致性:
- Settings → SettingsManager → get_settings()
- DQSettings → DI Provider → 注入
```

---

## 修复步骤

### 步骤 1: 修改 DQSettings.get_rules_paths() 签名

```python
# packages/core/src/ditto_core/quality/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class DQSettings(BaseSettings):
    """
    DQ configuration settings.

    Environment variables:
        L1_ENABLED: Enable L1 technical checks
        RULES_DIR: DQ rules directory path
        ...
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Switches
    l1_enabled: bool = True
    l2_enabled: bool = True
    l3_enabled: bool = True

    # Rules directory
    rules_dir: str = "config/default/dq_rules"

    # Quarantine
    quarantine_enabled: bool = True
    quarantine_path: str = "data/quarantine"

    # Reports
    report_enabled: bool = True
    report_path: str = "data/reports/dq"

    @property
    def rules_path(self) -> Path:
        """Get rules directory path."""
        return Path(self.rules_dir)

    def get_rules_paths(
        self,
        dataset: str,
        env: str,  # ✅ 必需参数，不再使用 None 默认值
    ) -> list[Path]:
        """
        获取规则文件路径（优先级顺序）.

        Args:
            dataset: 数据集名称
            env: 环境名称 (development/testing/production)

        Returns:
            规则文件路径列表（按优先级排序）

        """
        paths: list[Path] = []

        # 1. 环境特定
        env_rules = Path(f"config/{env}/dq_rules/{dataset}.yml")
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

**变更说明**:
- ✅ 移除延迟导入 `# noqa: PLC0415`
- ✅ `env` 参数变为必需，不再使用 `None` 默认值
- ✅ 消除循环依赖

---

### 步骤 2: 在 DI 容器中提供 DQSettings

```python
# apps/port/src/ditto_port/registry/datahub.py
from pathlib import Path
from dishka import Provider, provide
from ditto_core.quality.config import DQSettings
from ditto_foundation.config import get_settings

class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    # ... 现有代码 ...

    @provide
    def dq_settings(self) -> DQSettings:
        """
        DQ 配置（应用级单例）.

        使用全局 Settings 获取环境，保持配置规范一致.
        """
        settings = get_settings()
        env = settings.system.ditto_env.value

        # 创建 DQSettings 并注入 env
        # DQSettings 会从环境变量加载，但我们需要显式传递 env
        return DQSettings(
            _env_file=f"config/{env}/dq.env",  # 使用环境特定的 env_file
        )
```

**关键点**:
- ✅ 使用 `get_settings()` 获取环境（与全局配置一致）
- ✅ 通过 `_env_file` 参数指定环境特定的配置文件
- ✅ 保持 `DQSettings` 作为 Pydantic BaseSettings 的特性

---

### 步骤 3: 更新 QualityEngine 接受 DQSettings 注入

```python
# packages/core/src/ditto_core/quality/engine.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Literal

import polars as pl

from ditto_core.quality.checkers.business import BusinessChecker
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.checkers.technical import TechnicalChecker
from ditto_core.quality.config import DQSettings
from ditto_core.quality.spec import DQIssue, DQResult, DQSeverity, DQSpec


class QualityEngine:
    """
    Quality execution engine.

    Orchestrates data quality checks across L1/L2/L3 levels.
    Core layer: Pure business logic, no data access dependencies.
    """

    def __init__(
        self,
        config: DQSpec | None = None,
        config_path: str | Path | None = None,
        data_root: str | Path | None = None,
        # ✅ 新增：接受 DQSettings 注入
        dq_settings: DQSettings | None = None,
    ) -> None:
        """
        Initialize Quality engine.

        Args:
            config: Pre-loaded DQ configuration
            config_path: Path to YAML configuration directory (legacy)
            data_root: Data root for user config override (new)
            dq_settings: DQ 配置对象（通过 DI 注入）
        """
        # 保存 DQSettings（如果有）
        self._dq_settings = dq_settings

        if config is not None:
            self.config = config
        elif data_root is not None:
            # New: Load with user override
            default_config_dir = (
                Path(__file__).parent.parent.parent / "config" / "dq_rules"
            )
            self.config = DQSpec.load_with_user_override(
                default_config_dir=default_config_dir, data_root=Path(data_root)
            )
        elif config_path is not None:
            # Legacy: Load from single path
            self.config = DQSpec.from_yaml_dir(config_path)
        else:
            self.config = DQSpec()

        # Initialize checkers
        self.technical_checker = TechnicalChecker()
        self.business_checker = BusinessChecker()
        self.statistical_checker = StatisticalChecker()

    @property
    def _config(self) -> DQSpec:
        """Backward compatibility for _config attribute."""
        return self.config

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[Literal["l1", "l2"]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """
        Execute DQ checks (write-time).

        Args:
            df: Data to check
            dataset: Dataset identifier
            levels: Check levels to run (default: ["l1", "l2"])
            context: Additional context

        Returns:
            DQResult with check results

        """
        if levels is None:
            levels = ["l1", "l2"]

        issues: list[DQIssue] = []

        # Get dataset rules
        dataset_rules = self.config.get_rules(dataset)
        if dataset_rules is None:
            return DQResult(dataset=dataset, passed=True, issues=[])

        # Run L1 technical checks
        if "l1" in levels and dataset_rules.l1_technical:
            # ✅ 使用注入的 DQSettings
            if self._dq_settings and not self._dq_settings.l1_enabled:
                pass  # 跳过 L1 检查
            else:
                l1_issues = self.technical_checker.check(
                    df=df,
                    rules=dataset_rules.l1_technical,
                    context=context,
                )
                issues.extend(l1_issues)

        # ... 其余代码保持不变 ...
```

---

### 步骤 4: 更新 DI 容器中的 QualityEngine 创建

```python
# apps/port/src/ditto_port/registry/datahub.py
class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    # ... 其他 provider 方法 ...

    @provide
    def dq_settings(self) -> DQSettings:
        """DQ 配置（应用级单例）."""
        settings = get_settings()
        env = settings.system.ditto_env.value
        return DQSettings(_env_file=f"config/{env}/dq.env")

    @provide
    def dq_engine(self, dq_settings: DQSettings) -> QualityEngine:
        """
        数据质量引擎（应用层 DQ 检查使用）.

        Args:
            dq_settings: 注入的 DQ 配置
        """
        # ✅ 注入 DQSettings
        return QualityEngine(dq_settings=dq_settings)
```

---

## 环境文件配置

### 环境文件结构

```
config/
├── development/
│   ├── dq.env           # DQ 开发环境配置
│   └── dq_rules/
│       └── stock_daily.yml
├── testing/
│   ├── dq.env           # DQ 测试环境配置
│   └── dq_rules/
└── production/
    ├── dq.env           # DQ 生产环境配置
    └── dq_rules/
```

### config/development/dq.env

```bash
# DQ 开发环境配置
L1_ENABLED=true
L2_ENABLED=true
L3_ENABLED=false
RULES_DIR=config/development/dq_rules
QUARANTINE_ENABLED=true
```

### config/testing/dq.env

```bash
# DQ 测试环境配置
L1_ENABLED=true
L2_ENABLED=true
L3_ENABLED=true
QUARANTINE_ENABLED=false
```

### config/production/dq.env

```bash
# DQ 生产环境配置
L1_ENABLED=true
L2_ENABLED=true
L3_ENABLED=true
RULES_DIR=config/production/dq_rules
QUARANTINE_ENABLED=true
```

---

## 验证命令

```bash
# 1. 检查循环依赖是否消除
! grep -r "# noqa: PLC0415" packages/core/src --include="*.py"

# 2. 类型检查
pixi run -e dev type packages/core/src

# 3. 运行测试
pixi run -e dev test packages/core/tests

# 4. 完整 CI
pixi run -e dev ci
```

---

## 回滚策略

```bash
# 如果出现问题，可以快速回滚
git revert <commit-hash>

# 或者手动恢复：
# 1. 恢复 DQSettings.get_rules_paths() 的 env: str | None = None 参数
# 2. 恢复延迟导入 # noqa: PLC0415
# 3. 移除 DI 容器中的 dq_settings provider
# 4. 恢复 QualityEngine 的原始签名
```

---

## 优势总结

| 方面 | 改进前 | 改进后 |
|------|--------|--------|
| **循环依赖** | ❌ 延迟导入 | ✅ 消除 |
| **配置规范** | ⚠️ 不一致 | ✅ 与 Settings 一致 |
| **可测试性** | ⚠️ 难以 Mock | ✅ DI 注入，易测试 |
| **环境隔离** | ⚠️ 手动管理 | ✅ 环境文件自动切换 |

---

## 提交信息

```bash
git add packages/core/src/ditto_core/quality/config.py
git add packages/core/src/ditto_core/quality/engine.py
git add apps/port/src/ditto_port/registry/datahub.py
git add config/development/dq.env
git add config/testing/dq.env
git add config/production/dq.env

git commit -m "refactor(core): inject DQSettings via DI container

- Remove lazy import in DQSettings.get_rules_paths()
- Add dq_settings provider in DataHubProvider
- Inject DQSettings into QualityEngine
- Add environment-specific dq.env files
- Maintain consistency with global Settings pattern

BREAKING_CHANGE: DQSettings.get_rules_paths() now requires env parameter"
```
