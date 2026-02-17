# 配置系统审计问题修复实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复配置系统审计发现的 4 个问题，消除 DQ 路径失效、Prefect I/O 错误、DI 重复依赖、运行时标志重复计算。

**Architecture:** 新增项目根目录发现能力到 foundation 层；删除 DI 重复 provider；注入 runtime_flags 替代重复计算；添加日志清理 fixture。

**Tech Stack:** Python 3.12+, dishka DI, pytest, pathlib

---

## Task 1: 新增项目根目录发现模块 (问题 1)

**Files:**
- Create: `packages/infra/src/ditto_infra/foundation/config/project_root.py`
- Test: `packages/infra/tests/unit/config/test_project_root_unit.py`

### Step 1.1: 写失败测试 - find_project_root

```python
# packages/infra/tests/unit/config/test_project_root_unit.py

from pathlib import Path

import pytest


class TestFindProjectRoot:
    """项目根目录发现测试。"""

    def test_find_project_root_from_current_file(self) -> None:
        """从当前文件向上查找应找到项目根目录。"""
        from ditto_infra.foundation.config.project_root import find_project_root

        root = find_project_root()
        # 验证根目录存在 pixi.toml
        assert (root / "pixi.toml").exists()

    def test_find_project_root_with_explicit_start(self) -> None:
        """从指定路径开始查找。"""
        from ditto_infra.foundation.config.project_root import find_project_root

        start_path = Path(__file__)
        root = find_project_root(start=start_path)
        assert (root / "pixi.toml").exists()

    def test_find_project_root_no_marker_raises(self, tmp_path: Path) -> None:
        """无 marker 文件时抛出 RuntimeError。"""
        from ditto_infra.foundation.config.project_root import find_project_root

        # tmp_path 下没有任何 marker 文件
        with pytest.raises(RuntimeError, match="Cannot find project root"):
            find_project_root(start=tmp_path / "nonexistent.py")

    def test_find_project_root_prefers_pixi_toml(self, tmp_path: Path) -> None:
        """优先选择 pixi.toml 所在目录。"""
        from ditto_infra.foundation.config.project_root import find_project_root

        # 创建嵌套结构：outer/ (pyproject.toml) / inner/ (pixi.toml)
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / "pyproject.toml").touch()

        inner = outer / "inner"
        inner.mkdir()
        (inner / "pixi.toml").touch()

        # 从 inner 的子目录开始查找
        start = inner / "src" / "module.py"
        start.parent.mkdir(parents=True, exist_ok=True)
        start.touch()

        root = find_project_root(start=start)
        # 应该找到 inner (pixi.toml)，而不是 outer (pyproject.toml)
        assert root == inner
```

### Step 1.2: 运行测试验证失败

```bash
pixi run -e dev pytest packages/infra/tests/unit/config/test_project_root_unit.py -v
```

Expected: FAIL - `ModuleNotFoundError: No module named 'ditto_infra.foundation.config.project_root'`

### Step 1.3: 实现 find_project_root

```python
# packages/infra/src/ditto_infra/foundation/config/project_root.py

"""项目根目录发现模块。

参考业界最佳实践:
- pyrootutils: https://pypi.org/project/pyrootutils/
- pyprojroot: https://github.com/chendaniely/pyprojroot
"""

from pathlib import Path
from typing import Final

__all__ = ["find_project_root", "get_default_dq_rules_dir"]

# 优先级：pixi.toml > pyproject.toml > .git
# pixi.toml 在 monorepo 根目录，优先级最高
_ROOT_MARKERS: Final = ("pixi.toml", "pyproject.toml", ".git")


def find_project_root(start: Path | None = None) -> Path:
    """
    从给定路径向上查找项目根目录。

    使用 pixi.toml / pyproject.toml / .git 作为根标记。
    优先级：pixi.toml > pyproject.toml > .git

    Args:
        start: 起始路径，默认为当前文件所在目录

    Returns:
        项目根目录路径

    Raises:
        RuntimeError: 找不到项目根目录

    Example:
        >>> root = find_project_root()
        >>> (root / "pixi.toml").exists()
        True
    """
    path = (start or Path(__file__)).resolve()

    for parent in path.parents:
        for marker in _ROOT_MARKERS:
            if (parent / marker).exists():
                return parent

    raise RuntimeError(f"Cannot find project root from {path}")


def get_default_dq_rules_dir() -> Path:
    """
    获取默认 DQ 规则目录。

    Returns:
        config/default/dq_rules 目录路径

    Raises:
        RuntimeError: 找不到项目根目录
    """
    return find_project_root() / "config" / "default" / "dq_rules"
```

### Step 1.4: 运行测试验证通过

```bash
pixi run -e dev pytest packages/infra/tests/unit/config/test_project_root_unit.py -v
```

Expected: PASS

### Step 1.5: 更新 __init__.py 导出

```python
# packages/infra/src/ditto_infra/foundation/config/__init__.py

"""Ditto 配置管理模块。"""

from ditto_infra.foundation.config.environment import Environment, get_environment
from ditto_infra.foundation.config.initializer import (
    ConfigInitCoordinator,
    ConfigInitProvider,
    InitResult,
    InitScope,
)
from ditto_infra.foundation.config.loader import ConfigLoader
from ditto_infra.foundation.config.paths import PathResolver, XDGPaths
from ditto_infra.foundation.config.project_root import (
    find_project_root,
    get_default_dq_rules_dir,
)
from ditto_infra.foundation.config.settings import (
    ObservabilitySettings,
    Settings,
    SystemSettings,
)

__all__ = [
    "ConfigInitCoordinator",
    "ConfigInitProvider",
    "ConfigLoader",
    "Environment",
    "InitResult",
    "InitScope",
    "ObservabilitySettings",
    "PathResolver",
    "Settings",
    "SystemSettings",
    "XDGPaths",
    "find_project_root",
    "get_default_dq_rules_dir",
    "get_environment",
]
```

### Step 1.6: 验证导出正确

```bash
pixi run -e dev python -c "from ditto_infra.foundation.config import find_project_root, get_default_dq_rules_dir; print(find_project_root())"
```

Expected: 打印项目根目录路径

### Step 1.7: 提交 Task 1

```bash
git add packages/infra/src/ditto_infra/foundation/config/project_root.py
git add packages/infra/src/ditto_infra/foundation/config/__init__.py
git add packages/infra/tests/unit/config/test_project_root_unit.py
git commit -m "$(cat <<'EOF'
feat(infra): 新增项目根目录发现能力

- 新增 find_project_root() 基于 marker 文件向上查找
- 新增 get_default_dq_rules_dir() 获取 DQ 规则目录
- 支持 pixi.toml / pyproject.toml / .git 三种 marker
- 参考 pyrootutils / pyprojroot 最佳实践

Refs: #1 (DQ 默认规则路径失效)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 修复 QualityProvider 使用新路径 (问题 1)

**Files:**
- Modify: `apps/port/src/ditto_port/registry/core/quality.py:81-90`
- Test: 运行现有测试验证

### Step 2.1: 写失败测试 - DQ 规则目录存在

```python
# apps/port/tests/unit/registry/core/test_quality_path_unit.py

from pathlib import Path


class TestDQRulesPath:
    """DQ 规则路径测试。"""

    def test_default_dq_rules_dir_exists(self) -> None:
        """默认 DQ 规则目录必须存在。"""
        from ditto_infra.foundation.config import get_default_dq_rules_dir

        dq_dir = get_default_dq_rules_dir()
        assert dq_dir.exists(), f"DQ rules directory not found: {dq_dir}"

    def test_default_dq_rules_dir_has_yaml_files(self) -> None:
        """默认 DQ 规则目录必须包含 yml 文件。"""
        from ditto_infra.foundation.config import get_default_dq_rules_dir

        dq_dir = get_default_dq_rules_dir()
        yaml_files = list(dq_dir.glob("*.yml"))
        assert yaml_files, f"No DQ rule files in: {dq_dir}"
        # 验证至少包含 stock_daily.yml
        assert any(f.name == "stock_daily.yml" for f in yaml_files)
```

### Step 2.2: 运行测试验证通过（路径已存在）

```bash
pixi run -e dev pytest apps/port/tests/unit/registry/core/test_quality_path_unit.py -v
```

Expected: PASS

### Step 2.3: 修改 QualityProvider 使用新路径

```python
# apps/port/src/ditto_port/registry/core/quality.py

# 在文件顶部添加导入
from ditto_infra.foundation.config import get_default_dq_rules_dir

# 修改 dq_spec 方法（约 line 81-90）
@provide
def dq_spec(self, data_root: Path) -> DQSpec:
    """
    加载 DQ 配置规范.

    支持用户配置覆盖默认配置：
    1. 默认配置: config/default/dq_rules/*.yml
    2. 用户配置: {data_root}/config/dq/*.yml (覆盖)

    Args:
        data_root: 数据根目录

    Returns:
        DQSpec: DQ 配置实例

    """
    # 1. 加载包内默认配置（使用标准路径发现）
    default_config_dir = get_default_dq_rules_dir()
    default_config = self._load_dq_spec(default_config_dir)

    # 2. 加载用户自定义配置（覆盖默认配置）
    user_config_dir = Path(data_root) / "config" / "dq"
    user_config = self._load_dq_spec(user_config_dir)

    # 3. 合并配置（用户配置覆盖默认配置）
    merged_datasets = default_config.datasets.copy()
    merged_datasets.update(user_config.datasets)

    return DQSpec(datasets=merged_datasets)
```

### Step 2.4: 运行相关测试验证

```bash
pixi run -e dev pytest apps/port/tests/unit/registry/core/ -v
```

Expected: PASS

### Step 2.5: 提交 Task 2

```bash
git add apps/port/src/ditto_port/registry/core/quality.py
git add apps/port/tests/unit/registry/core/test_quality_path_unit.py
git commit -m "$(cat <<'EOF'
fix(port): 修复 QualityProvider DQ 规则路径

- 使用 get_default_dq_rules_dir() 替代硬编码路径
- 添加单测验证 DQ 规则目录存在

Fixes: #1 (DQ 默认规则路径失效)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 删除 RuntimeProvider 重复的 data_root (问题 3)

**Files:**
- Modify: `apps/port/src/ditto_port/registry/datahub/runtime.py:44-46,76-84,159-164`

### Step 3.1: 写失败测试 - 验证 DI 无重复 provider

```python
# apps/port/tests/unit/registry/test_di_no_duplicate_path_unit.py

import pytest
from dishka import make_async_container


class TestDINoDuplicatePathProvider:
    """验证 DI 容器无重复 Path provider。"""

    def test_data_root_single_provider(self) -> None:
        """data_root 应只由 ConfigProvider 提供。"""
        from ditto_port.registry.container import create_app_container

        container = create_app_container()

        # 获取所有提供 Path 类型的 provider
        # 注入 Path 应该只返回一个实例（来自 ConfigProvider）
        from pathlib import Path
        from collections.abc import AsyncIterator

        # 检查容器状态
        providers = container.registry.providers
        path_providers = [p for p in providers if Path in p.type_hints.values()]

        # 应该只有一个 provider 提供 Path
        assert len(path_providers) <= 1, (
            f"Multiple providers for Path: {[p.cls.__name__ for p in path_providers]}"
        )
```

### Step 3.2: 修改 runtime.py - 删除 data_root，更新依赖方

```python
# apps/port/src/ditto_port/registry/datahub/runtime.py

# 删除以下方法（约 line 44-46）:
#     @provide
#     def data_root(self, config: DataRootConfig) -> Path:
#         """数据根目录."""
#         return config.data_root

# 修改 freeze_manager（约 line 76-78）:
@provide
def freeze_manager(self, config: DataRootConfig) -> FreezeManager:
    """数据版本管理."""
    return FreezeManager(data_root=str(config.data_root))

# 修改 file_lock（约 line 81-84）:
@provide
def file_lock(self, config: DataRootConfig) -> FileLockManager:
    """文件锁管理器."""
    lock_dir = config.data_root / "locks"
    return FileLockManager(lock_dir)

# 修改 sql_engine（约 line 159-164）:
@provide
def sql_engine(
    self,
    config: DataRootConfig,
) -> SqlEngine:
    """DuckDB SQL 引擎."""
    return SqlEngine(data_root=config.data_root)
```

### Step 3.3: 运行测试验证

```bash
pixi run -e dev pytest apps/port/tests/unit/registry/ -v -k "not slow"
```

Expected: PASS

### Step 3.4: 提交 Task 3

```bash
git add apps/port/src/ditto_port/registry/datahub/runtime.py
git add apps/port/tests/unit/registry/test_di_no_duplicate_path_unit.py
git commit -m "$(cat <<'EOF'
refactor(port): 删除 RuntimeProvider 重复的 data_root provider

- 删除 RuntimeProvider.data_root()，保留 ConfigProvider.data_root()
- 修改 freeze_manager/file_lock/sql_engine 直接使用 DataRootConfig
- 消除 DI 依赖顺序隐式耦合

Fixes: #3 (Path 依赖重复提供)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 修复 ObservabilityProvider 注入 runtime_flags (问题 4)

**Files:**
- Modify: `apps/port/src/ditto_port/registry/infra/observability.py:21-61`

### Step 4.1: 写失败测试 - 验证使用注入的 flags

```python
# apps/port/tests/unit/registry/infra/test_observability_flags_unit.py

import pytest
from dishka import make_async_container


class TestObservabilityUsesInjectedFlags:
    """验证 ObservabilityProvider 使用注入的 runtime_flags。"""

    def test_observability_config_uses_runtime_flags(self) -> None:
        """observability_config 应使用注入的 runtime_flags。"""
        # 检查 observability_config 方法的签名
        from ditto_port.registry.infra.observability import ObservabilityProvider
        import inspect

        sig = inspect.signature(ObservabilityProvider.observability_config)
        params = list(sig.parameters.keys())

        # 应该包含 runtime_flags 参数
        assert "runtime_flags" in params, (
            f"observability_config should have runtime_flags parameter, got: {params}"
        )
```

### Step 4.2: 修改 observability.py - 注入 runtime_flags

```python
# apps/port/src/ditto_port/registry/infra/observability.py

"""观测系统 Provider。"""

from __future__ import annotations

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_datahub.config import DataRootConfig
from ditto_infra.foundation.config.settings import Settings
from ditto_infra.foundation.observability import init, shutdown
from ditto_infra.foundation.observability.config import ObservabilityConfig

__all__ = ["ObservabilityProvider"]


class ObservabilityProvider(Provider):
    """观测系统 Provider。"""

    scope = Scope.APP

    @provide
    def observability_config(
        self,
        settings: Settings,
        data_root_config: DataRootConfig,
        runtime_flags: dict[str, bool],  # 注入 runtime_flags
    ) -> ObservabilityConfig:
        """构建观测配置对象。"""
        obs = settings.observability

        return ObservabilityConfig(
            service_name="ditto-server",
            environment=settings.system.environment,
            log_dir=str(data_root_config.logs_path),
            log_level=obs.log_level,
            log_format=obs.log_format,
            log_to_console=obs.log_to_console,
            log_to_file=obs.log_to_file,
            tracing_enabled=obs.tracing_enabled,
            tracing_exporter=obs.tracing_exporter,
            tracing_sample_rate=obs.tracing_sample_rate,
            metrics_enabled=obs.metrics_enabled,
            metrics_exporter=obs.metrics_exporter,
            vm_endpoint=obs.vm_endpoint,
            # 使用注入的 runtime_flags，替代重复计算
            pytest_running=runtime_flags["pytest_running"],
            assertions_enabled=runtime_flags["assertions_enabled"],
            verbose_logging=runtime_flags["verbose_logging"],
        )

    @provide
    def observability(self, config: ObservabilityConfig) -> Iterator[None]:
        """初始化并在生命周期结束时关闭观测系统。"""
        init(config)
        yield
        shutdown()
```

### Step 4.3: 运行测试验证

```bash
pixi run -e dev pytest apps/port/tests/unit/registry/infra/test_observability_flags_unit.py -v
```

Expected: PASS

### Step 4.4: 提交 Task 4

```bash
git add apps/port/src/ditto_port/registry/infra/observability.py
git add apps/port/tests/unit/registry/infra/test_observability_flags_unit.py
git commit -m "$(cat <<'EOF'
refactor(port): ObservabilityProvider 注入 runtime_flags

- 移除 observability_config 中的重复计算逻辑
- 直接注入 ConfigProvider 提供的 runtime_flags
- 消除配置漂移风险

Fixes: #4 (运行时标志重复计算)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 添加 flush_prefect_logs fixture (问题 2)

**Files:**
- Modify: `apps/port/tests/conftest.py`

### Step 5.1: 修改 conftest.py - 添加 fixture

```python
# apps/port/tests/conftest.py

# 在文件末尾添加:

# =============================================================================
# Prefect 日志清理
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def flush_prefect_logs():
    """确保所有 Prefect 日志在 teardown 前刷新。

    解决 pytest 关闭 stderr 后 Prefect 后台线程写入导致的 I/O 错误。

    参考: https://linen.prefect.io/t/23466101
    """
    yield

    # 清理所有 loggers 和 handlers
    loggers_to_cleanup = [
        logging.getLogger(),  # Root logger
        logging.getLogger("prefect"),
        logging.getLogger("prefect.client"),
    ]

    for lgr in loggers_to_cleanup:
        for handler in lgr.handlers[:]:
            try:
                handler.flush()
                handler.close()
            except (ValueError, OSError):
                pass  # 忽略已关闭的 handler
            lgr.removeHandler(handler)
```

### Step 5.2: 确保 logging 已导入

检查 `apps/port/tests/conftest.py` 文件顶部是否有 `import logging`，如果没有则添加。

### Step 5.3: 运行完整测试验证无 I/O 错误

```bash
pixi run -e dev pytest apps/port/tests/ -v --tb=short 2>&1 | grep -i "I/O operation" || echo "No I/O errors found"
```

Expected: "No I/O errors found"

### Step 5.4: 提交 Task 5

```bash
git add apps/port/tests/conftest.py
git commit -m "$(cat <<'EOF'
fix(test): 添加 flush_prefect_logs fixture 解决 teardown I/O 错误

- 在 session teardown 时显式 flush/close Prefect 日志 handlers
- 解决 "ValueError: I/O operation on closed file" 问题
- 参考 Prefect 社区最佳实践

Fixes: #2 (Prefect/Rich 关闭期 I/O 错误)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 最终验证

### Step 6.1: 运行完整检查

```bash
pixi run -e dev check
```

Expected: 全部通过 (lint + fmt + type + test --fast)

### Step 6.2: 验证 DQ 规则加载正常

```bash
pixi run -e dev python -c "
from ditto_infra.foundation.config import get_default_dq_rules_dir
from pathlib import Path

dq_dir = get_default_dq_rules_dir()
print(f'DQ rules dir: {dq_dir}')
print(f'Exists: {dq_dir.exists()}')
print(f'Files: {list(dq_dir.glob(\"*.yml\"))}')
"
```

Expected: 打印 DQ 规则目录和文件列表

### Step 6.3: 最终提交（如果有遗漏）

```bash
git status
# 如果有未提交的更改，在此提交
```

---

## 执行顺序总结

| Task | 问题 | 描述 | 预估时间 |
|------|------|------|----------|
| 1 | #1 | 新增 find_project_root 模块 | 10 min |
| 2 | #1 | 修复 QualityProvider 路径 | 5 min |
| 3 | #3 | 删除重复 data_root provider | 5 min |
| 4 | #4 | 注入 runtime_flags | 5 min |
| 5 | #2 | 添加 flush_prefect_logs fixture | 5 min |
| 6 | - | 最终验证 | 5 min |

**总计: ~35 min**

---

## 回滚计划

如果出现问题，按以下顺序回滚：

```bash
# 回滚最近一次提交
git revert HEAD

# 或回滚到特定 commit
git log --oneline -10
git revert <commit-hash>
```
