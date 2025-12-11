# Data Module

该模块提供了 Ditto 量化交易系统的数据访问功能。

## 组件概述

### 核心组件

- **Adapters (适配器层)**
  - `DuckDBAdapter`: DuckDB 数据库适配器
  - `SQLiteAdapter`: SQLite 数据库适配器
  - `DatabaseAdapter`: 数据库适配器基类协议

- **Services (服务层)**
  - `DataReader`: 数据读取服务，提供业务语义的读取接口
  - `DataWriter`: 数据写入服务，提供业务语义的写入接口
  - `DataQualityService`: 数据质量验证服务

- **Data Sources (数据源层)**
  - `TushareDataSource`: Tushare 数据源
  - `AkShareDataSource`: AkShare 数据源
  - `DataSourceFactory`: 数据源工厂类
  - `DataCollector`: 数据收集器

### 弃用组件

- **`DataService`**: 已弃用，请使用 `DataReader` 和 `DataWriter` 代替
  - 迁移指南请参考: [../../../../../docs/Migration_Guide_DataService.md](../../../../../docs/Migration_Guide_DataService.md)

## 快速开始

### 读取数据

```python
from ditto_core.data.adapters import DuckDBAdapter
from ditto_core.data.services.data_reader import DataReader

# 创建适配器和读取器
adapter = DuckDBAdapter("path/to/database.duckdb")
reader = DataReader(adapter)

# 读取日线数据
daily_data = reader.get_daily_data(
    symbol="510300",
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# 读取 ETF 列表
etf_list = reader.get_etf_list()

# 读取复权因子
adj_factors = reader.get_adjustment_factors("510300")

# 读取交易日历
calendar = reader.get_trading_calendar("2024-01-01", "2024-12-31")
```

### 写入数据

```python
from ditto_core.data.adapters import DuckDBAdapter
from ditto_core.data.services.data_writer import DataWriter
import polars as pl

# 创建适配器和写入器
adapter = DuckDBAdapter("path/to/database.duckdb")
writer = DataWriter(adapter)

# 写入 ETF 信息
etf_data = pl.DataFrame({
    "symbol": ["510300", "159919"],
    "name": ["沪深300ETF", "沪深300ETF"],
    "list_date": ["2012-05-04", "2012-05-04"]
})
writer.store_etf_info(etf_data)

# 写入日线数据
daily_data = pl.DataFrame({
    "symbol": ["510300"],
    "date": ["2024-01-02"],
    "open": [4.0],
    "high": [4.1],
    "low": [3.9],
    "close": [4.05],
    "volume": [1000000]
})
writer.store_daily_data(daily_data)
```

### 数据收集

```python
from ditto_core.data.collector import DataCollector
from ditto_core.data.datasources import DataSourceFactory

# 创建数据源
tushare = DataSourceFactory.create_tushare(pro_token="your_token")

# 创建数据收集器
collector = DataCollector(sources=[tushare])

# 更新数据
collector.update_etf_list()
collector.update_daily_data(symbols=["510300"])
```

## 架构设计

### 分层架构

```
┌─────────────────────────────────────┐
│           应用层 (Application)        │
├─────────────────────────────────────┤
│         服务层 (Services)            │
│  ┌────────────┐  ┌────────────┐     │
│  │ DataReader │  │ DataWriter │     │
│  └────────────┘  └────────────┘     │
├─────────────────────────────────────┤
│         适配器层 (Adapters)          │
│  ┌────────────┐  ┌────────────┐     │
│  │ DuckDB     │  │ SQLite     │     │
│  │ Adapter    │  │ Adapter    │     │
│  └────────────┘  └────────────┘     │
├─────────────────────────────────────┤
│          数据源层 (DataSources)      │
│  ┌────────────┐  ┌────────────┐     │
│  │ Tushare    │  │ AkShare    │     │
│  └────────────┘  └────────────┘     │
└─────────────────────────────────────┘
```

### 设计原则

1. **单一职责原则**: 每个类只负责一个特定功能
2. **依赖倒置原则**: 依赖抽象而非具体实现
3. **开闭原则**: 对扩展开放，对修改关闭
4. **接口隔离原则**: 使用多个专门的接口

## 数据库模式

### DuckDB 表结构

主要存储：
- `etf_info`: ETF 基本信息
- `daily_price_raw`: 原始日线数据
- `daily_price_adjusted`: 复权后日线数据
- `adjustment_factors`: 复权因子
- `trading_calendar`: 交易日历

### SQLite 表结构

主要存储：
- 交易相关数据
- 用户配置
- 运行时状态

## 测试

### 运行单元测试

```bash
# 运行所有数据模块测试
pytest packages/core/tests/unit/data/

# 运行特定测试
pytest packages/core/tests/unit/data/test_service.py
```

### 运行集成测试

```bash
# 运行集成测试
pytest packages/core/tests/integration/data/
```

## 配置

数据源配置文件位于 `config/datasources.yaml`：

```yaml
tushare:
  pro_token: "your_tushare_token"
  timeout: 30

akshare:
  timeout: 30
  retry_count: 3
```

## 最佳实践

1. **连接管理**
   - 使用上下文管理器确保连接关闭
   - 避免频繁创建/销毁适配器实例

2. **批量操作**
   - DataWriter 自动使用批量操作
   - 尽量一次性写入多条数据

3. **错误处理**
   - 捕获并处理特定异常
   - 使用日志记录详细信息

4. **性能优化**
   - 使用适当的数据类型
   - 考虑使用索引优化查询

## 故障排除

### 常见问题

1. **导入错误**
   - 确保已安装所有依赖：`pixi install`
   - 检查 Python 路径配置

2. **连接错误**
   - 验证数据库文件路径
   - 检查文件权限

3. **数据质量问题**
   - 使用 DataQualityService 验证数据
   - 检查数据源配置

## 贡献指南

1. 遵循项目的代码风格规范
2. 为新功能添加测试
3. 更新相关文档
4. 使用 conventional commit 格式提交

## 版本历史

- v0.5.0: DataService 标记为弃用
- v0.4.0: 添加 DataReader/DataWriter
- v0.3.0: 重构适配器层
- v0.2.0: 添加数据源支持
- v0.1.0: 初始版本
