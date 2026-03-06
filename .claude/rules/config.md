---
paths:
  - ./**/*.py
---

# 配置系统规范

## 配置层次架构

### 双层环境架构

| 层级 | 变量/环境 | 有效值 | 说明 |
|------|----------|--------|------|
| Pixi 环境 | 选择环境 | `default`, `dev` | 依赖管理层（pixi.toml） |
| 运行时环境 | `ENVIRONMENT` | `development`, `testing`, `production` | 行为控制层 |

**核心原则**：Pixi 环境管理依赖，`ENVIRONMENT` 控制行为。

### 配置文件目录结构

```
config/
├── default/           # 环境无关的默认配置
│   └── dq_rules/      # DQ 规则 YAML
├── development/       # 开发环境
│   ├── system.env
│   ├── data_store.env
│   ├── data_source.env
│   ├── observability.env
│   ├── dq.env
│   └── notification.env
├── testing/           # 测试环境
└── production/        # 生产环境
```

### 配置加载优先级

1. **环境变量覆盖** - 最高优先级（如 `DITTO_DATA_ROOT`）
2. **配置文件** - `config/{environment}/*.env`
3. **模型默认值** - Settings 类中的默认值

---

## 配置模型规范

### 模型定义原则

| 原则 | 要求 | 示例 |
|------|------|------|
| **纯模型** | 不读取环境/文件，只定义结构 | `class DataStoreSettings(BaseModel)` |
| **extra="ignore"** | 忽略未知字段，兼容配置文件变化 | `model_config = ConfigDict(extra="ignore")` |
| **单一职责** | 每个 Settings 只管理一个领域 | `SystemSettings`, `DataSourceSettings` |

### 配置模型分层

```
┌─────────────────────────────────────────────────────┐
│  Settings（聚合配置）                                │
│  ├── SystemSettings（系统基础）                      │
│  └── ObservabilitySettings（可观测性）               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  DataStoreSettings（数据存储）                       │
│  └── SqlEngineConfig（引擎子配置）                   │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  DataSourceSettings（数据源）                        │
└─────────────────────────────────────────────────────┘
```

### 配置模型位置规范

| 包 | 位置 | 包含配置 |
|---|------|----------|
| `ditto_infra` | `foundation/config/settings.py` | `Settings`, `SystemSettings`, `ObservabilitySettings` |
| `ditto_datahub` | `config/data_store.py` | `DataStoreSettings`, `FileStorageSettings` |
| `ditto_datahub` | `config/data_source.py` | `DataSourceSettings` |
| `ditto_core` | `quality/config.py` | `DQSettings` |

### 禁止事项

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| 模型内直接读取 `os.environ` | 通过 `load_env_file()` 加载后传入 |
| 使用 `BaseSettings` 自动读取 | 使用纯 `BaseModel` + 手动加载 |
| 配置模型包含业务逻辑 | 配置模型只包含数据结构 |

---

## 配置加载规范

### 加载流程

```
启动 → get_environment() → ConfigLoader(environment)
     → load_env_file(loader, "xxx") → XxxSettings.model_validate(values)
     → DI 容器提供实例
```

### 加载职责划分

| 组件 | 职责 | 位置 |
|------|------|------|
| `get_environment()` | 获取运行时环境 | `infra/foundation/config/environment.py` |
| `ConfigLoader` | 定位配置文件路径 | `infra/foundation/config/loader.py` |
| `load_env_file()` | 加载 .env 文件 | `port/config/loader.py` |
| `ConfigProvider` | DI 装配 | `port/registry/infra/config.py` |

### 配置加载位置约束

**核心原则**：配置仅在 **Port 层** 加载，其他层通过 DI 获取。

```
┌────────────────────────────────────────────────────────────┐
│  apps/port/registry/infra/config.py（唯一加载点）          │
│                                                            │
│  @provide                                                  │
│  def settings(self, loader: ConfigLoader) -> Settings:    │
│      values = load_env_file(loader, "system")             │
│      return Settings.model_validate(values)               │
└────────────────────────────────────────────────────────────┘
          │
          │ DI 注入
          ▼
┌────────────────────────────────────────────────────────────┐
│  packages/datahub/   packages/core/   packages/infra/      │
│  （通过构造函数/方法参数获取配置，禁止自己加载）           │
└────────────────────────────────────────────────────────────┘
```

### 环境变量覆盖

**优先级**：环境变量 > 配置文件 > 默认值

```python
# ConfigProvider 中支持 CLI 透传
if override := os.getenv("DITTO_DATA_ROOT"):
    values["data_root"] = override
```

**允许的环境变量覆盖**：

| 环境变量 | 覆盖配置 | 用途 |
|---------|----------|------|
| `DITTO_DATA_ROOT` | `data_root` | CLI 临时指定数据目录 |
| `SQLITE_PATH` | `sqlite_path` | 覆盖 SQLite 路径 |
| `DUCKDB_PATH` | `duckdb_path` | 覆盖 DuckDB 路径 |

---

## 路径管理规范

### XDG 基础目录规范

`XDGPaths` 遵循 XDG Base Directory 规范，支持跨平台：

| 目录 | 环境变量 | 默认路径（Linux） | 用途 |
|------|---------|------------------|------|
| config_home | `DITTO_CONFIG_DIR` / `XDG_CONFIG_HOME` | `~/.config/ditto` | 用户配置 |
| data_home | `DITTO_DATA_DIR` / `XDG_DATA_HOME` | `~/.local/share/ditto` | 持久数据 |
| state_home | `DITTO_STATE_DIR` / `XDG_STATE_HOME` | `~/.local/state/ditto` | 状态日志 |
| cache_home | `DITTO_CACHE_DIR` / `XDG_CACHE_HOME` | `~/.cache/ditto` | 缓存 |
| runtime_dir | `DITTO_RUNTIME_DIR` / `XDG_RUNTIME_DIR` | `/tmp/ditto-{uid}` | PID/Socket |

### 路径解析优先级

```
1. DITTO_*_DIR（最高优先级，特定目录覆盖）
2. XDG_*_HOME（标准 XDG 变量）
3. DITTO_BASE_DIR（统一基础目录）
4. base_override（测试模式）
5. 平台默认值
```

### DataStoreSettings 路径派生

**核心原则**：所有数据路径从 `data_root` 派生，唯一真源。

```python
class DataStoreSettings(BaseModel):
    data_root: Path  # 唯一配置入口

    @property
    def resolved_sqlite_path(self) -> Path:
        return self.data_root / "metadata" / "metadata.sqlite"

    @property
    def market_stock_bars_path(self) -> Path:
        return self.data_root / "market" / "stock" / "bars" / "daily"
```

**禁止事项**：

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| 硬编码路径字符串 | 使用 `DataStoreSettings` 属性 |
| 多处定义相同路径 | 唯一真源 + 属性派生 |

---

## 配置初始化规范

### 初始化协调器

`ConfigInitCoordinator` 管理启动时的配置初始化：

```python
class InitScope(str, Enum):
    STARTUP = "startup"   # 启动时自动执行
    MANUAL = "manual"     # 手动触发
    ALWAYS = "always"     # 每次都执行
```

### 初始化提供者

| 提供者 | 作用域 | 职责 |
|--------|--------|------|
| `DataRootInitProvider` | STARTUP | 创建数据目录结构 |
| `MetadataDbInitProvider` | STARTUP | 初始化元数据库 |

### 初始化流程（main.py）

```python
coordinator: ConfigInitCoordinator = await container.get(ConfigInitCoordinator)
settings: DataStoreSettings = await container.get(DataStoreSettings)
coordinator.initialize(scope=InitScope.STARTUP, data_root=settings.data_root)
```

---

## 测试配置规范

### 测试环境隔离

```python
# conftest.py 或测试 fixture
monkeypatch.setenv("ENVIRONMENT", "testing")
```

**测试环境特性**：
- `DATA_ROOT=.tmp/ditto` - 隔离测试数据
- `DEBUG=true` - 启用调试
- `assertions_enabled=True` - 断言启用

### 测试中覆盖配置

```python
# ✅ 正确：通过 monkeypatch 覆盖环境变量
monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path))

# ✅ 正确：通过 DI 容器获取配置
container = make_container(ConfigProvider())
settings = container.get(DataStoreSettings)

# ❌ 错误：直接修改配置实例
settings.data_root = Path("/other")  # frozen dataclass 也不允许
```

### 测试配置文件

测试使用 `config/testing/*.env`，与开发/生产隔离。

---

## 配置变更规范

> **重要**：新增或修改配置后，必须同步更新 `docs/configuration.md` 操作手册。

### 变更检查清单

- [ ] 更新配置模型（`*Settings` 类）
- [ ] 更新配置文件（`config/{environment}/*.env`）
- [ ] 在 `ConfigProvider` 中添加加载逻辑（如需新配置文件）
- [ ] 更新 `docs/configuration.md` 操作手册
- [ ] 添加/更新相关测试

---

## 禁止事项清单

| ❌ 禁止 | ✅ 正确 | 原因 |
|---------|---------|------|
| 非 Port 层加载配置 | Port 层加载 + DI 注入 | 单一职责、可测试性 |
| 模型内读取 `os.environ` | 通过 `load_env_file()` 传入 | 配置来源可追溯 |
| 使用 `BaseSettings` | 使用纯 `BaseModel` | 显式加载、可控 |
| 硬编码路径 | 使用 `DataStoreSettings` 属性 | 唯一真源 |
| 直接访问 `os.getenv("ENVIRONMENT")` | 使用 `get_environment()` | 统一入口 |
| 使用废弃的 `DITTO_ENV` | 使用 `ENVIRONMENT` | 已弃用 |
| 使用全局单例 `get_paths()` | 通过 DI 注入 `XDGPaths` | 已移除 |

---

## 配置检查命令

```bash
# 验证配置加载
pixi run -e dev python -c "from ditto_infra.foundation.config import get_environment; print(get_environment())"

# 检查配置文件语法
cat config/development/system.env
```
