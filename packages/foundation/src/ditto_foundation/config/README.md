# config

> 使用 Pydantic Settings 进行系统配置管理，支持环境变量、类型验证和配置热加载

## 一、核心功能

### 1.1 配置管理

- **环境变量自动加载**：从 `.env` 文件和环境变量读取配置
- **类型验证**：基于 Pydantic 的自动类型检查和转换
- **分层配置**：按功能模块分组管理配置项
- **默认值**：为所有配置提供合理的默认值

### 1.2 配置子模块

| 模块 | 文件 | 职责 |
|------|------|------|
| `DatabaseSettings` | settings.py | 数据库配置（DuckDB + SQLite）|
| `DataSourceSettings` | settings.py | 数据源配置（Tushare + AkShare）|
| `APISettings` | settings.py | FastAPI 服务配置 |
| `SystemSettings` | settings.py | 系统基础配置 |
| `FileStorageSettings` | settings.py | 文件存储配置 |
| `ObservabilitySettings` | settings.py | 可观测性配置 |

## 二、架构定位

```
ditto-foundation/config
    ↓ 被所有模块引用
ditto-datahub, ditto-core, apps/port
```

- **层级**：基础设施层
- **依赖**：仅依赖外部库（pydantic-settings）
- **被依赖**：系统所有模块

## 三、目录结构

```
config/
├── __init__.py      # 导出 get_settings, Settings
└── settings.py      # 所有配置类定义
```

## 四、关键模块说明

### 4.1 Settings（主配置类）

集成所有配置子模块的统一入口：

```python
from ditto_foundation.config import get_settings

settings = get_settings()

# 访问配置
db_path = settings.database.sqlite_path
token = settings.data_source.tushare_token
```

### 4.2 环境变量前缀

每个子模块支持独立的环境变量前缀：

```bash
# DatabaseSettings 使用 DB_ 前缀
DB_SQLITE_PATH=./data/sqlite/ditto.sqlite

# 其他模块使用无前缀的全局变量
TUSHARE_TOKEN=your_token
LOG_LEVEL=INFO
```

### 4.3 配置验证

`validate_settings()` 函数检查配置有效性：

- 必要的 API 密钥是否存在
- 生产环境的安全配置是否正确
- 交易配置的完整性
- 通知配置的完整性

## 五、注意事项

### 5.1 环境变量优先级

1. 代码中的默认值（最低）
2. `.env` 文件中的值
3. 系统环境变量（最高）

### 5.2 单例模式

`get_settings()` 返回全局单例，避免重复加载：

```python
# 推荐
settings = get_settings()

# 不推荐：每次创建新实例
settings = Settings()
```

### 5.3 配置热加载

使用 `reload_settings()` 可重新加载配置（主要用于测试）：

```python
new_settings = reload_settings()
```

### 5.4 敏感信息

- **SECRET_KEY**：生产环境必须修改
- **API Token**：不要提交到代码仓库
- 使用 `.env.example` 作为配置模板

## 六、使用示例

### 6.1 基本使用

```python
from ditto_foundation.config import get_settings

settings = get_settings()

# 访问数据库配置
db_path = settings.database.duckdb_path
pool_size = settings.database.pool_size

# 访问数据源配置
token = settings.data_source.tushare_token
rate_limit = settings.data_source.tushare_rate_limit

# 环境判断
if settings.is_production:
    # 生产环境逻辑
    pass
```

### 6.2 配置验证

```python
from ditto_foundation.config import get_settings, validate_settings

settings = get_settings()
errors = validate_settings(settings)

if errors:
    for error in errors:
        print(f"配置错误: {error}")
else:
    print("配置验证通过")
```

### 6.3 自定义日志配置

```python
from ditto_foundation.config import get_settings

settings = get_settings()
log_config = settings.get_log_config()

# log_config = {
#     "level": "INFO",
#     "timezone": "Asia/Shanghai",
#     "log_root": "./logs",
#     "retention_days": 30,
#     "debug": False
# }
```
