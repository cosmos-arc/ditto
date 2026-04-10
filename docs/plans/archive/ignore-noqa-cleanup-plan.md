# Ditto 项目 Ignore/Noqa 激进清理方案

## 目标

**核心源码零 ignore**：`packages/**/src` 和 `apps/port/**/src` 中不能有任何 `# noqa` 或 `# type: ignore`（除了 SQL 安全 `S608` 必须带详细注释）。

**测试代码灵活配置**：使用混合策略，固有模式配置文件豁免，特殊情况单行注释。

## 当前状况

### 核心源码统计

| 类型 | 数量 | 主要规则 |
|------|------|---------|
| `# noqa` | 43 处 | PLW0603 (9), PLC0415 (9), PLR0913 (5), PLR0911 (2), S608 (8) |
| `# type: ignore` | 3 处 | 第三方库限制、类型收窄 |

### 分布

- **Singleton 模式** (9 处): `app_initializer.py`, `settings.py`, `paths.py`, `observability/__init__.py`, `metrics.py`
- **延迟导入** (9 处): `settings.py`, `logging.py`, `adj_factor.py`, `bars.py`, `base.py`, `client.py`, `deploy.py`
- **复杂度** (7 处): `coordinator.py`, `datasets.py`, `backfill.py`, `pipeline_store.py`, `security.py`, `paths.py`
- **SQL 安全** (8 处): `sqlite_client.py`, `security_store.py`, `pipeline_store.py`, `technical.py`, `universe.py`, `pit_helper.py`, `sql_engine.py`

## 实施方案

### 阶段 1: Singleton 模式重构 (消除 PLW0603)

**策略**: 使用类属性 + `@cached_property` 消除 `global` 语句

**创建文件**: `packages/foundation/src/ditto_foundation/config/manager.py`

```python
from functools import cached_property

class SettingsManager:
    """配置管理器 - 单例模式（无 global）。"""

    _instance: SettingsManager | None = None

    def __new__(cls) -> SettingsManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @cached_property
    def settings(self) -> Settings:
        return Settings()

    def reload(self) -> Settings:
        if 'settings' in self.__dict__:
            del self.__dict__['settings']
        return self.settings

_settings_manager = SettingsManager()

def get_settings() -> Settings:
    return _settings_manager.settings
```

**修改文件**:
- `packages/foundation/src/ditto_foundation/config/settings.py` (移除 global)
- `packages/foundation/src/ditto_foundation/config/paths.py` (移除 global)
- `packages/foundation/src/ditto_foundation/observability/__init__.py` (使用状态管理类)
- `packages/foundation/src/ditto_foundation/observability/metrics.py` (使用状态管理类)
- `packages/foundation/src/ditto_foundation/app_initializer.py` (使用状态管理类)

**验证**: `pixi run -e dev test --unit packages/foundation`

---

### 阶段 2: 协议接口引入 (消除 PLC0415 - 循环依赖)

**策略**: 创建协议接口消除 Repository 循环依赖

**创建文件**: `packages/data/src/ditto_data/repositories/protocols.py`

```python
from typing import Protocol
import polars as pl

class BarsAccessor(Protocol):
    """行情数据访问器协议（消除循环依赖）。"""
    def get(self, sids: list[int] | None, start: str, end: str) -> pl.DataFrame: ...
```

**修改文件**:
- `packages/data/src/ditto_data/repositories/adj_factor.py` (使用协议)
- `packages/data/src/ditto_data/repositories/bars.py` (实现协议)
- `packages/data/src/ditto_data/hub.py` (注入依赖)
- `packages/data/src/ditto_data/sources/base.py` (移除延迟导入)

**验证**: `pixi run -e dev test --unit packages/data`

---

### 阶段 3: 配置重构 (消除 PLC0415 - computed_field)

**策略**: 将 `computed_field` 改为显式的 `resolve_paths()` 方法

**修改文件**:
- `packages/foundation/src/ditto_foundation/config/settings.py`
  - 移除 `DatabaseSettings` 和 `FileStorageSettings` 的 `computed_field`
  - 添加 `resolve_paths(paths: XDGPaths)` 方法
- `packages/foundation/src/ditto_foundation/app_initializer.py`
  - 在初始化时调用 `resolve_paths()`
- `packages/foundation/src/ditto_foundation/observability/logging.py` (移除延迟导入)

**验证**: `pixi run -e dev test --unit packages/foundation`

---

### 阶段 4: 复杂度控制 (消除 PLR0913/0911)

**策略**: 参数对象 + 函数拆分

**创建参数对象**:

```python
# packages/data/src/ditto_data/stores/pipeline_store.py
@dataclass(frozen=True)
class PipelineRunParams:
    """Pipeline 运行参数。"""
    run_id: str
    task_name: str
    dataset_id: str
    status: str = "running"
    # ... 其他字段
```

**修改文件**:
- `packages/data/src/ditto_data/stores/pipeline_store.py` (3 处)
- `packages/data/src/ditto_data/stores/security_store.py` (1 处)
- `packages/data/src/ditto_data/repositories/security.py` (1 处)
- `apps/port/src/ditto_port/services/ingestion/coordinator.py` (2 处 - 拆分函数)
- `apps/port/src/ditto_port/services/ingestion/config/datasets.py` (1 处 - Builder 模式)
- `apps/port/src/ditto_port/jobs/flows/backfill.py` (1 处)
- `packages/foundation/src/ditto_foundation/config/paths.py` (1 处)

**验证**: `pixi run -e dev test --unit packages/data apps/port`

---

### 阶段 5: 类型忽略清理 (消除 type: ignore)

**策略**: TypeGuard + stub + TYPE_CHECKING

**创建文件**: `typings/prefect/__init__.pyi` (Prefect 库类型存根)

**修改文件**:
- `packages/foundation/src/ditto_foundation/util/dates.py`
  - 使用 `TypeGuard` 替代 `unnecessary-isinstance`
- `packages/foundation/src/ditto_foundation/observability/testing.py`
  - 使用 `TYPE_CHECKING` 处理未使用导入
- `apps/port/src/ditto_port/jobs/flows/deploy.py`
  - 使用 Prefect stub

**验证**: `pixi run -e dev type --all`

---

### 阶段 6: SQL 安全注释 (规范化 S608)

**策略**: 保留 `# noqa: S608`，但必须带详细注释

**注释规范**:

```python
# SQL 注入防护：table 已通过 ALLOWED_TABLES 白名单验证
query = f"SELECT * FROM {table}"  # noqa: S608
```

**修改文件**:
- `packages/data/src/ditto_data/stores/sqlite_client.py`
- `packages/data/src/ditto_data/stores/security_store.py` (2 处)
- `packages/data/src/ditto_data/stores/pipeline_store.py`
- `packages/data/src/ditto_data/dq/checkers/technical.py`
- `packages/data/src/ditto_data/repositories/universe.py`
- `packages/data/src/ditto_data/runtime/pit_helper.py` (2 处)
- `packages/data/src/ditto_data/runtime/sql_engine.py`

**验证**: `pixi run -e dev lint packages/data/src`

---

### 阶段 7: 配置文件优化

**策略**: 移除核心源码的 `PLC0415` 豁免

**修改文件**: `pyproject.toml`

```toml
[tool.ruff.lint.per-file-ignores]
# 移除以下豁免（通过重构解决）:
# "packages/data/src/ditto_data/hub.py" = ["PLC0415"]
# "packages/foundation/src/ditto_foundation/config/settings.py" = ["PLC0415"]
# "apps/port/src/ditto_port/jobs/flows/deploy.py" = ["PLC0415"]

# 保留测试文件豁免
"tests/**/*.py" = ["PLR2004", "PLR0913", "S101", "ANN", "D", "PLC0415", "C901"]
"**/tests/**/*.py" = ["PLR2004", "PLR0913", "S101", "ANN", "D", "PLC0415", "C901"]
"**/conftest.py" = ["ANN", "D", "PLC0415"]

# 脚本文件豁免
"scripts/**/*.py" = ["T201", "S101", "S603", "S607", "D", "ANN"]
"**/cli.py" = ["T201"]
"**/cli/*.py" = ["T201"]

# __init__.py 豁免
"__init__.py" = ["D104"]
```

**验证**: `pixi run -e dev lint`

---

### 阶段 8: 最终验证

**完整检查清单**:

```bash
# 代码质量
pixi run -e dev lint
pixi run -e dev type --all
pixi run -e dev fmt --check

# 测试
pixi run -e dev test
pixi run -e dev test --coverage

# 统计验证
git grep "# noqa" packages/*/src apps/*/src | grep -v "S608"  # 应该为空
git grep "# type: ignore" packages/*/src apps/*/src  # 应该为空
git grep "global " packages/*/src apps/*/src  # 应该为空
```

**预期结果**:
- 核心源码无 PLW0603
- 核心源码无 PLC0415
- 核心源码无 PLR0913/0911
- SQL 安全 S608 都有详细注释

---

## 关键文件

**创建** (新文件):
1. `packages/foundation/src/ditto_foundation/config/manager.py`
2. `packages/data/src/ditto_data/repositories/protocols.py`
3. `typings/prefect/__init__.pyi`

**修改** (核心重构):
1. `packages/foundation/src/ditto_foundation/config/settings.py`
2. `packages/foundation/src/ditto_foundation/config/paths.py`
3. `packages/foundation/src/ditto_foundation/observability/metrics.py`
4. `packages/data/src/ditto_data/stores/pipeline_store.py`
5. `packages/data/src/ditto_data/hub.py`

**修改** (复杂度):
1. `apps/port/src/ditto_port/services/ingestion/coordinator.py`
2. `apps/port/src/ditto_port/services/ingestion/config/datasets.py`
3. `packages/data/src/ditto_data/repositories/security.py`

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 引入新的循环依赖 | 使用协议接口，严格检查依赖方向 |
| 测试覆盖不足 | 每个 PR 必须通过完整测试套件 |
| 性能回退 | 使用 `@cached_property` 确保懒加载 |

> **注意**: 项目处于开发阶段，无需考虑向后兼容性，可直接重构 API。

---

## 实施顺序

1. **阶段 1**: Singleton 重构 (1-2 天)
2. **阶段 2**: 协议接口 (1-2 天)
3. **阶段 3**: 配置重构 (1 天)
4. **阶段 4**: 复杂度控制 (1-2 天)
5. **阶段 5**: 类型清理 (0.5 天)
6. **阶段 6**: SQL 注释 (0.5 天)
7. **阶段 7**: 配置优化 (0.5 天)
8. **阶段 8**: 最终验证 (0.5 天)

**总计**: 约 6-9 天

每个阶段独立一个 PR，便于回滚和验证。
