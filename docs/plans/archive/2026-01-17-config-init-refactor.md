# 配置初始化机制重构计划

## 概述

重构 ditto 项目的配置初始化机制，解决 `datahub/cli/` 目录违反分层架构的问题，建立统一的配置初始化协调框架。

## 问题分析

### 现有问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **分层违规** | `packages/data/src/ditto_data/cli/init_dq_config.py` 存在于数据层 | DataHub 不应包含 CLI 工具 |
| **职责混乱** | 配置初始化逻辑分散，缺乏统一协调 | 难以维护和扩展 |
| **依赖倒置** | 数据层提供"工具"而非"能力" | 违反 `port → datahub → foundation` 依赖原则 |

### 需要初始化的配置

1. **DQ 配置**：`packages/data/config/dq_rules/*.yml` → `{data_root}/config/dq/`
2. **数据库 Schema**：SQLite 表结构初始化
3. **数据集配置**：datasets.yaml（未来扩展）

## 架构设计

### 职责划分

| 层级 | 职责 | 提供 | 不提供 |
|------|------|------|--------|
| **Foundation** | 配置初始化协调框架 | `ConfigInitCoordinator`, `ConfigInitProvider` 接口 | 具体配置内容 |
| **DataHub** | 数据相关配置初始化 | DQ 配置、数据库 Schema 的提供者 | CLI 命令 |
| **Port** | 应用级协调 | CLI 命令、启动时自动初始化 | 配置实现细节 |

### 依赖关系

```
Port 应用
    ↓ 依赖
Foundation (ConfigInitCoordinator)
    ↓ 协调
DataHub (提供 ConfigInitProvider 实现)
```

## 核心组件

### 1. Foundation 框架（新建）

**文件**：`packages/foundation/src/ditto_foundation/config/initializer.py`

**核心类**：
- `InitScope` - 初始化作用域（STARTUP/MANUAL/ALWAYS）
- `InitResult` - 初始化结果数据类
- `ConfigInitProvider` - 提供者抽象基类
- `ConfigInitCoordinator` - 协调器（单例）

**关键方法**：
```python
class ConfigInitProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def scope(self) -> InitScope: ...

    @abstractmethod
    def check(self, data_root: Path) -> bool: ...

    @abstractmethod
    def initialize(self, data_root: Path) -> InitResult: ...

class ConfigInitCoordinator:
    def register(self, provider: ConfigInitProvider) -> None: ...
    def initialize(self, scope: InitScope, data_root, force) -> dict[str, InitResult]: ...
```

### 2. DataHub 提供者（新建）

**文件**：`packages/data/src/ditto_data/init_providers.py`

**实现类**：
- `DQConfigProvider` - DQ 配置初始化（复制 YAML 文件）
- `DatabaseSchemaProvider` - 数据库 Schema 初始化（调用 `SQLitePool.init_schema()`）

**注册函数**：
```python
def register_datahub_providers() -> None:
    coordinator = get_config_coordinator()
    coordinator.register(DQConfigProvider())
    coordinator.register(DatabaseSchemaProvider())
```

### 3. Port CLI 命令（新建）

**文件**：`apps/port/src/ditto_port/cli/commands/init.py`

**命令结构**：
```
ditto init
├── config      # 初始化所有配置
├── dq          # 仅初始化 DQ 配置
└── db          # 仅初始化数据库 Schema
```

### 4. 应用启动集成（修改）

**文件**：`apps/port/src/ditto_port/main.py` 的 `lifespan` 函数

**添加自动初始化**：
```python
from ditto_foundation.config.initializer import get_config_coordinator, InitScope
from ditto_data.init_providers import register_datahub_providers

register_datahub_providers()
coordinator = get_config_coordinator()
coordinator.initialize(scope=InitScope.STARTUP)  # 自动检测并初始化
```

## 关键文件

### 需要创建的文件

| 文件 | 用途 |
|------|------|
| `packages/foundation/src/ditto_foundation/config/initializer.py` | 配置初始化框架 |
| `packages/data/src/ditto_data/init_providers.py` | DataHub 配置提供者 |
| `apps/port/src/ditto_port/cli/commands/init.py` | CLI 命令实现 |

### 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `packages/foundation/src/ditto_foundation/config/__init__.py` | 导出 `initializer` 模块 |
| `packages/data/src/ditto_data/__init__.py` | 导出 `register_datahub_providers` |
| `apps/port/src/ditto_port/cli/main.py` | 添加 `init` 命令组 |
| `apps/port/src/ditto_port/main.py` | lifespan 中添加自动初始化 |

### 需要删除的文件

| 文件 | 原因 |
|------|------|
| `packages/data/src/ditto_data/cli/` | 违反分层架构 |

## 实现步骤

### 阶段 1：Foundation 框架 ✅

1. ✅ 创建 `packages/foundation/src/ditto_foundation/config/initializer.py`
2. ✅ 实现 `ConfigInitProvider` 抽象基类
3. ✅ 实现 `ConfigInitCoordinator` 协调器
4. ✅ 添加单元测试（60 个测试通过）
5. ✅ 更新 `__init__.py` 导出

### 阶段 2：DataHub 适配 ✅

1. ✅ 创建 `packages/data/src/ditto_data/init_providers.py`
2. ✅ 实现 `DQConfigProvider`（迁移 `init_dq_config.py` 逻辑）
3. ✅ 实现 `DatabaseSchemaProvider`（使用 `SQLitePool.init_schema()`）
4. ✅ 实现 `register_datahub_providers()` 函数
5. ✅ 删除 `packages/data/src/ditto_data/cli/` 目录
6. ✅ 添加单元测试（14 个测试通过）

### 阶段 3：Port 应用集成 ✅

1. ✅ 创建 `apps/port/src/ditto_port/cli/commands/init.py`
2. ✅ 实现 `init config`、`init dq`、`init db` 命令
3. ✅ 修改 `cli/main.py` 添加 `init` 命令组
4. ✅ 修改 `main.py` 的 `lifespan` 添加自动初始化
5. ✅ 添加集成测试（9 个测试通过）

### 阶段 4：文档与清理 ✅

1. ✅ 更新 README.md 添加 `ditto init` 使用说明
2. ✅ 更新架构文档
3. ✅ 运行 `pixi run -e dev ci` 确保所有检查通过

## CLI 使用示例

```bash
# 初始化所有配置
ditto init config

# 强制重新初始化
ditto init config --force

# 指定数据根目录
ditto init config --data-root /custom/path

# 仅初始化 DQ 配置
ditto init dq

# 仅初始化数据库
ditto init db
```

## 验收标准

- [x] `datahub/cli/` 目录已删除
- [x] Foundation 层提供 `ConfigInitCoordinator` 框架
- [x] DataHub 层实现 `DQConfigProvider` 和 `DatabaseSchemaProvider`
- [x] Port 层提供 `ditto init` CLI 命令
- [x] 应用启动时自动检测并初始化配置
- [x] 所有单元测试通过（74 个测试）
- [x] 所有集成测试通过（9 个测试）
- [x] pyright 类型检查通过（0 errors）
- [x] ruff 代码检查通过
- [x] 符合项目架构原则

## 可复用组件

- `SQLitePool.init_schema()` - 已存在，直接复用
- `XDGPaths` - Foundation 层路径管理
- `logger` - Foundation 层日志系统

## 参考资料

- [Best Practices for Working with Configuration in Python Applications](https://tech.preferred.jp/en/blog/working-with-configuration-in-python/)
- [Structuring Your Project — The Hitchhiker's Guide to Python](https://docs.python-guide.org/writing/structure/)
