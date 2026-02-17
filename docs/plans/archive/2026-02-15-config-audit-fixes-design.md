# 配置系统审计问题修复设计

> 日期: 2026-02-15
> 状态: 设计完成，待实施

## 概述

基于代码审计发现的 4 个配置系统问题，本文档描述修复方案。

| # | 严重度 | 问题 | 状态 |
|---|--------|------|------|
| 1 | High | DQ 默认规则路径失效 | 待修复 |
| 2 | Medium | Prefect/Rich 关闭期 I/O 错误 | 待修复 |
| 3 | Medium | Path 依赖重复提供 | 待修复 |
| 4 | Low | 运行时标志重复计算 | 待修复 |

---

## 问题 1 [High] DQ 默认规则路径失效

### 问题分析

**当前代码** ([quality.py:81-89](apps/port/src/ditto_port/registry/core/quality.py#L81-L89)):

```python
default_config_dir = (
    Path(__file__).parent.parent.parent.parent.parent
    / "packages"
    / "core"
    / "src"
    / "ditto_core"
    / "config"
    / "dq_rules"
)
```

**问题**：路径 `packages/core/src/ditto_core/config/dq_rules` 不存在。

**实际路径**：
- `config/default/dq_rules/` ✅
- `packages/datahub/config/dq_rules/` ✅

**影响**：DQ 规则完全不加载，数据质量检查退化为空校验。

### 解决方案

在 `ditto_infra.foundation.config` 中新增项目根目录发现能力。

#### 新增模块

```python
# ditto_infra/foundation/config/project_root.py

from pathlib import Path
from typing import Final

# 优先级：pixi.toml > pyproject.toml > .git
# pixi.toml 在 monorepo 根目录，优先级最高
_ROOT_MARKERS: Final = ("pixi.toml", "pyproject.toml", ".git")


def find_project_root(start: Path | None = None) -> Path:
    """
    从给定路径向上查找项目根目录。

    使用 pixi.toml / pyproject.toml / .git 作为根标记。

    Args:
        start: 起始路径，默认为调用者文件所在目录

    Returns:
        项目根目录路径

    Raises:
        RuntimeError: 找不到项目根目录
    """
    path = (start or Path(__file__)).resolve()

    for parent in path.parents:
        for marker in _ROOT_MARKERS:
            if (parent / marker).exists():
                return parent

    raise RuntimeError(f"Cannot find project root from {path}")


def get_default_dq_rules_dir() -> Path:
    """获取默认 DQ 规则目录。"""
    return find_project_root() / "config" / "default" / "dq_rules"
```

#### 修改 QualityProvider

```python
# quality.py
from ditto_infra.foundation.config.project_root import get_default_dq_rules_dir

@provide
def dq_spec(self, data_root: Path) -> DQSpec:
    # 1. 加载包内默认配置
    default_config_dir = get_default_dq_rules_dir()
    default_config = self._load_dq_spec(default_config_dir)

    # 2. 加载用户自定义配置（覆盖默认配置）
    user_config_dir = Path(data_root) / "config" / "dq"
    user_config = self._load_dq_spec(user_config_dir)

    # 3. 合并配置
    merged_datasets = default_config.datasets.copy()
    merged_datasets.update(user_config.datasets)

    return DQSpec(datasets=merged_datasets)
```

#### 增强保护

```python
# 非 testing 环境下，若合并后规则为空 → fail-fast
if not merged_datasets and environment != Environment.TESTING:
    raise ConfigurationError("DQ rules empty after merge - check config paths")
```

### 单测覆盖

```python
def test_default_dq_rules_dir_exists():
    """默认规则目录必须存在。"""
    from ditto_infra.foundation.config.project_root import get_default_dq_rules_dir

    dq_dir = get_default_dq_rules_dir()
    assert dq_dir.exists(), f"DQ rules directory not found: {dq_dir}"
    assert list(dq_dir.glob("*.yml")), f"No DQ rule files in: {dq_dir}"
```

---

## 问题 2 [Medium] Prefect/Rich 关闭期 I/O 错误

### 问题分析

**错误信息**:

```
--- Logging error ---
ValueError: I/O operation on closed file.
Message: 'Stopping temporary server on http://127.0.0.1:8211'
```

**根因**：
- Prefect 使用后台线程处理日志
- pytest teardown 时先关闭了 stderr
- Prefect 日志线程尝试向已关闭的文件写入

### 解决方案

基于 [Prefect 社区最佳实践](https://linen.prefect.io/t/23466101)，在 teardown 阶段显式清理日志 handlers。

#### 修改 conftest.py

```python
# apps/port/tests/conftest.py

import logging


@pytest.fixture(scope="session", autouse=True)
def flush_prefect_logs():
    """确保所有 Prefect 日志在 teardown 前刷新。"""
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

### 为什么有效

| 步骤 | 作用 |
|------|------|
| `handler.flush()` | 强制写入缓冲区内容 |
| `handler.close()` | 关闭文件句柄 |
| `lgr.removeHandler()` | 移除引用，防止后续写入 |

---

## 问题 3 [Medium] Path 依赖重复提供

### 问题分析

| 文件 | 方法 | 提供 |
|------|------|------|
| [config.py:111](apps/port/src/ditto_port/registry/infra/config.py#L111) | `data_root(data_root_config)` | `Path` |
| [runtime.py:44](apps/port/src/ditto_port/registry/datahub/runtime.py#L44) | `data_root(config)` | `Path` |

**影响**：依赖解析受 provider 注册顺序影响，重排容易引入隐性回归。

### 解决方案

保留 `ConfigProvider`，删除 `RuntimeProvider` 的 `data_root` 方法。

#### 删除 runtime.py 中的重复定义

```python
# runtime.py - 删除此方法
# @provide
# def data_root(self, config: DataRootConfig) -> Path:
#     """数据根目录."""
#     return config.data_root
```

#### 修改依赖方

```python
# runtime.py - 修改后

@provide
def freeze_manager(self, config: DataRootConfig) -> FreezeManager:
    """数据版本管理."""
    return FreezeManager(data_root=str(config.data_root))

@provide
def file_lock(self, config: DataRootConfig) -> FileLockManager:
    """文件锁管理器."""
    lock_dir = config.data_root / "locks"
    return FileLockManager(lock_dir)

@provide
def sql_engine(self, config: DataRootConfig) -> SqlEngine:
    """DuckDB SQL 引擎."""
    return SqlEngine(data_root=config.data_root)
```

---

## 问题 4 [Low] 运行时标志重复计算

### 问题分析

| 文件 | 代码 | 问题 |
|------|------|------|
| [config.py:175](apps/port/src/ditto_port/registry/infra/config.py#L175) | `runtime_flags(environment)` | 正确实现 |
| [observability.py:32](apps/port/src/ditto_port/registry/infra/observability.py#L32) | `__import__("os").environ` | 重复计算 |

**影响**：配置漂移风险，测试行为难统一。

### 解决方案

`ObservabilityProvider` 直接注入 `runtime_flags`。

#### 修改 observability.py

```python
# 修改前
@provide
def observability_config(
    self,
    settings: Settings,
    data_root_config: DataRootConfig,
) -> ObservabilityConfig:
    obs = settings.observability
    env = settings.system.environment

    # 重复计算
    pytest_running = "PYTEST_CURRENT_TEST" in __import__("os").environ

    if env.value == "testing":
        assertions_enabled = True
        verbose_logging = False
    elif env.value == "production":
        assertions_enabled = False
        verbose_logging = False
    else:
        assertions_enabled = True
        verbose_logging = True
    ...

# 修改后
@provide
def observability_config(
    self,
    settings: Settings,
    data_root_config: DataRootConfig,
    runtime_flags: dict[str, bool],  # ← 注入
) -> ObservabilityConfig:
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
        pytest_running=runtime_flags["pytest_running"],
        assertions_enabled=runtime_flags["assertions_enabled"],
        verbose_logging=runtime_flags["verbose_logging"],
    )
```

---

## 实施计划

### Phase 1: 基础设施（问题 1）

1. 新增 `ditto_infra/foundation/config/project_root.py`
2. 更新 `ditto_infra/foundation/config/__init__.py` 导出
3. 添加单测 `test_default_dq_rules_dir_exists`

### Phase 2: 配置修复（问题 3、4）

1. 修改 `runtime.py` 删除 `data_root` provider
2. 修改 `observability.py` 注入 `runtime_flags`

### Phase 3: 测试稳定性（问题 2）

1. 修改 `conftest.py` 添加 `flush_prefect_logs` fixture
2. 验证测试无 I/O 错误

### 验证命令

```bash
pixi run -e dev check  # lint + fmt + type + test --fast
```

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 项目根目录查找失败 | 低 | 高 | 支持 3 种 marker，单元测试覆盖 |
| DI 依赖注入顺序变化 | 低 | 中 | 删除重复 provider 消除隐式依赖 |
| Prefect 日志清理不完整 | 低 | 低 | try-except 兜底 |

---

## 参考资料

- [pyrootutils - PyPI](https://pypi.org/project/pyrootutils/) - 项目根目录发现最佳实践
- [pyprojroot - GitHub](https://github.com/chendaniely/pyprojroot) - R here 包的 Python 实现
- [Prefect Issue #16626](https://github.com/PrefectHQ/prefect/issues/16626) - I/O operation on closed file 问题
- [Prefect Community Solution](https://linen.prefect.io/t/23466101) - flush_prefect_logs fixture
