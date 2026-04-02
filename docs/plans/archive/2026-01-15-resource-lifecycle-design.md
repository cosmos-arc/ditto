# 资源生命周期管理设计

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


**设计日期**: 2026-01-15
**目标**: 解决 CLI 资源泄漏和 Observability 配置未生效问题

---

## 问题分析

### 1. CLI DataHub 资源泄漏

**文件**: `apps/port/src/ditto_port/cli/context.py:16-26`

**问题**:
- SQLite 连接池未关闭
- DuckDB 连接未关闭
- Store 的 SQLite 客户端未关闭

**影响**:
- Windows 上可能阻止进程退出
- 文件句柄泄漏

### 2. Observability 配置未生效

**文件**: `packages/foundation/src/ditto_foundation/app_initializer.py:84-96`

**问题**:
- `settings.observability.enabled` 未检查
- `settings.observability.mode` 未使用
- `settings.observability.vm_endpoint` 未传递

---

## 设计原则

### Python vs Java 模式差异

| 架构模式 | Java (Spring) | Python |
|---------|--------------|--------|
| 单例实现 | 类内部（`@Singleton`） | 应用入口管理 |
| 依赖注入 | 容器注入（IoC） | 函数参数/上下文传递 |
| 对象管理 | 框架控制 | 显式创建和传递 |

### 核心原则

1. **显式优于隐式**: DataHub 类不实现单例，应用侧保证单例
2. **依赖注入友好**: 测试可以注入独立实例
3. **职责分离**: 类负责功能，应用负责生命周期
4. **符合 Python 最佳实践**: 使用 `atexit` 而非 `__del__`

---

## 解决方案

### 1. DataHub: atexit 自动清理

**设计**: 每个实例注册自己的 `atexit` 处理器

```python
# packages/data/src/ditto_data/hub.py

import atexit

class DataHub:
    """DataHub 统一数据入口."""

    def __init__(self, data_root: str | None = None) -> None:
        self.data_root = data_root or str(get_settings().file_storage.data_root)
        self._closed = False
        # 注册进程退出清理
        atexit.register(self._cleanup_on_exit)

    def _cleanup_on_exit(self) -> None:
        """进程退出时清理（由 atexit 自动调用）."""
        if not self._closed:
            self.close()

    def close(self) -> None:
        """关闭资源."""
        if self._closed:
            return
        # ... 原有关闭逻辑 ...
        self._closed = True
```

**优点**:
- 简单，不需要类级别状态
- 符合 Python 最佳实践（参考 SQLAlchemy）

### 2. CLI: 应用侧单例 + 上下文管理器

**设计**: 模块级单例 + `with` 上下文管理器

```python
# apps/port/src/ditto_port/cli/context.py

import threading
from contextlib import contextmanager
from typing import Any

from ditto_data import DataHub

from ditto_port.cli.executor import CLIExecutor

# 模块级单例
_hub: DataHub | None = None
_hub_lock = threading.Lock()


def get_hub(data_root: str | None = None) -> DataHub:
    """
    获取应用级 DataHub 单例.

    Args:
        data_root: 数据根目录（首次调用时设置）

    Returns:
        DataHub 实例（同一进程内返回同一实例）
    """
    global _hub
    if _hub is None:
        with _hub_lock:
            if _hub is None:
                _hub = DataHub(data_root=data_root)
    return _hub


@contextmanager
def create_executor(data_root: str | None):
    """
    创建 CLI 执行器上下文管理器.

    自动管理 DataHub 生命周期，确保资源正确释放.

    Args:
        data_root: 数据根目录

    Yields:
        CLIExecutor: 可用的执行器实例
    """
    hub = get_hub(data_root)
    try:
        app_ctx = _AppContext(hub=hub, source=hub.sources)
        executor = CLIExecutor(app_ctx)
        yield executor
    finally:
        # hub 由 atexit 清理，这里不关闭
        pass
```

**命令使用**:
```python
# factory.py
def command(ctx: typer.Context, date: str, force: bool) -> None:
    with create_executor(ctx.obj.get("data_root")) as executor:
        result = executor.ingest_daily(dataset, date, force)
        print_ingestion_result(result, ctx.obj["verbose"])
```

### 3. Observability: 完整配置支持

**设计**: 检查 `enabled`，解析 `mode`，传递 `vm_endpoint`

```python
# packages/foundation/src/ditto_foundation/app_initializer.py

from ditto_foundation.observability import Mode, init

def _setup_observability(self, settings: Any) -> None:
    """Setup observability (logging, tracing, metrics)."""
    obs_settings = settings.observability

    # 检查是否启用
    if not obs_settings.enabled:
        logger.info("Observability disabled by configuration")
        return

    # 解析 mode
    mode_mapping: dict[str, Mode | None] = {
        "auto": None,
        "production": Mode.PRODUCTION,
        "development": Mode.DEVELOPMENT,
        "testing": Mode.TESTING,
    }

    configured_mode = mode_mapping.get(obs_settings.mode.lower(), None)
    actual_mode = configured_mode or (
        Mode.PRODUCTION if settings.is_production else Mode.DEVELOPMENT
    )

    # 初始化
    init(
        service_name="ditto",
        environment=settings.system.ditto_env,
        log_level=obs_settings.log_level,
        log_dir=str(settings.file_storage.log_root),
        vm_endpoint=obs_settings.vm_endpoint,
        mode=actual_mode,
    )
```

---

## 修改文件清单

| # | 文件 | 修改类型 | 描述 |
|---|------|----------|------|
| 1 | `packages/data/src/ditto_data/hub.py` | 修改 | 添加 atexit 清理 |
| 2 | `apps/port/src/ditto_port/cli/context.py` | 重写 | 删除 `ensure_executor`，添加 `create_executor` 和 `get_hub` |
| 3 | `apps/port/src/ditto_port/cli/commands/factory.py` | 更新 | 3 个工厂函数改用 `create_executor` |
| 4 | `apps/port/src/ditto_port/cli/commands/calendar.py` | 更新 | 命令改用 `create_executor` |
| 5 | `packages/foundation/src/ditto_foundation/app_initializer.py` | 修改 | Observability 配置完全支持 |
| 6 | `apps/port/tests/unit/cli/test_factory_unit.py` | 更新 | 测试改用上下文管理器 mock |

---

## 测试策略

### 单元测试

```python
# packages/data/tests/unit/test_hub_lifecycle.py

def test_atexit_registered_on_init():
    """验证 atexit 在初始化时注册."""
    hub = DataHub(data_root=tmp_path)
    # 验证 atexit 已注册

def test_close_is_idempotent():
    """验证 close() 可以多次调用."""
    hub = DataHub(data_root=tmp_path)
    hub.close()
    hub.close()  # 不应抛出异常
```

### 集成测试

```python
# packages/foundation/tests/integration/test_app_initializer.py

def test_observability_disabled():
    """验证 disabled=true 跳过初始化."""
    settings = ObservabilitySettings(enabled=False)
    # 验证 init() 不被调用

def test_observability_mode_respected():
    """验证 mode 配置生效."""
    settings = ObservabilitySettings(mode="testing")
    # 验证 Mode.TESTING 被传递

def test_observability_vm_endpoint():
    """验证 vm_endpoint 被传递."""
    settings = ObservabilitySettings(
        vm_endpoint="http://custom:8428"
    )
    # 验证 endpoint 被传递
```

---

## 配置说明

### Observability 环境变量

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ENABLED` | `true` | 是否启用可观测性 |
| `MODE` | `auto` | 运行模式：auto/production/development/testing |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `VM_ENDPOINT` | `http://localhost:8428/opentelemetry/v1/metrics` | VictoriaMetrics 端点 |
| `METRICS_INTERVAL_MS` | `15000` | 指标导出间隔（毫秒） |

---

## 参考资料

- [Python atexit Module](https://docs.python.org/3/library/atexit.html)
- [SQLAlchemy Engine Disposal](http://docs.sqlalchemy.org/en/latest/core/connections.html)
- [Python weakref.finalize](https://docs.python.org/3/library/weakref.html)

---

## 完成状态

| # | 任务 | 状态 | 提交 |
|---|------|------|------|
| 1 | `hub.py` - 添加 atexit 清理 | ✅ 完成 | cf3fa68 |
| 2 | `context.py` - 重写添加 `create_executor` 和 `get_hub` | ✅ 完成 | 待提交 |
| 3 | `factory.py` - 改用 `create_executor` | ✅ 完成 | 待提交 |
| 4 | `calendar.py` - 改用 `create_executor` | ✅ 完成 | 待提交 |
| 5 | `app_initializer.py` - Observability 配置完全支持 | ✅ 完成 | 待提交 |
| 6 | `test_factory_unit.py` - 测试改用上下文管理器 mock | ✅ 完成 | 待提交 |
