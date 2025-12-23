# ditto-foundation

> 基础设施层 - 共享类型、配置管理与工具函数

## 一、核心功能

提供跨包共享的数据契约、系统配置管理、日志配置和通用工具函数，是系统的基础依赖层。

## 二、架构定位

```
┌─────────────────────────────────────┐
│         ditto-datahub               │
├─────────────────────────────────────┤
│      ditto-foundation               │  ← 当前层
│  ┌──────────┐  ┌──────────┐         │
│  │ Config   │  │ Contract │         │
│  │ Logging  │  │ Util     │         │
│  └──────────┘  └──────────┘         │
└─────────────────────────────────────┘
```

**依赖方向**: 零内部包依赖，仅依赖标准库和第三方库

## 三、目录结构

```
src/ditto_foundation/
├── config/            # 配置管理
│   └── settings.py         # Pydantic Settings (主配置)
├── contracts/         # 数据契约
│   ├── etf.py              # ETF Pydantic 模型
│   ├── market_data.py      # Market Data Pandera Schema
│   └── __init__.py
├── types/             # 共享类型
│   └── __init__.py
├── util/              # 工具函数
│   ├── io.py               # IO 工具 (atomic_write, file_md5)
│   └── __init__.py
├── logging_config.py  # 日志配置
└── app_initializer.py  # 应用初始化 (NEW)
```

## 四、关键模块说明

### app_initializer - 应用初始化 (NEW)
- `AppInitializer`: 应用初始化类
  - `initialize()`: 执行完整初始化（目录创建、日志设置、配置验证）
- `initialize_app()`: 快速初始化函数（单例模式）

**使用示例**:
```python
from ditto_foundation import initialize_app

result = initialize_app()
# 返回: {"status": "initialized", "log_initialized": True, ...}
```

### config/ - 配置管理
- `DatabaseSettings`: DuckDB/SQLite 配置
- `DataSourceSettings`: Tushare/AkShare 配置
- `TradingSettings`: 交易执行配置
- `RiskSettings`: 风险管理配置 (Kill Switch)
- `get_settings()`: 全局配置单例

### contracts/ - 数据契约
- `ETFInfoModel`: ETF 信息 Pydantic 模型
- `DailyPriceSchema`: 日线数据 Pandera Schema

### util/ - 工具函数
- `atomic_write()`: 原子写入 Parquet
- `file_md5()`: 文件 MD5 校验

## 五、注意事项

1. **零依赖原则**: 本包不依赖其他 ditto 包
2. **配置热加载**: 使用 `reload_settings()` 可重新加载配置
3. **环境变量**: 配置优先级: 环境变量 > .env 文件 > 默认值

## 六、使用示例

```python
from ditto_foundation.config.settings import get_settings
from ditto_foundation.util.io import atomic_write

# 获取配置
settings = get_settings()
print(settings.data_source.tushare_token)

# 原子写入
from pathlib import Path
atomic_write(df, Path("data/output.parquet"))
```
