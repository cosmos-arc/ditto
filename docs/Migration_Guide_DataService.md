# DataService 迁移指南

## 概述

DataService 已被弃用，并将在未来版本中移除。请使用 DataReader 和 DataWriter 类代替，以实现更好的关注点分离。

## 迁移时间表

- **版本 0.5.0**: DataService 标记为弃用，开始显示警告
- **版本 1.0.0**: DataService 计划移除

## 迁移步骤

### 1. 读取数据迁移

#### 旧代码 (使用 DataService)
```python
from ditto_core.data import DataService

# 获取日线数据
with DataService(duckdb_path="data.duckdb") as service:
    adapter = service.get_duckdb()
    data = adapter.fetch_df(
        "SELECT * FROM daily_price_adjusted WHERE symbol = ?",
        {"symbol": "510300"}
    )
```

#### 新代码 (使用 DataReader)
```python
from ditto_core.data.adapters import DuckDBAdapter
from ditto_core.data.services.data_reader import DataReader

# 直接使用业务语义方法
adapter = DuckDBAdapter("data.duckdb")
reader = DataReader(adapter)

# 获取日线数据（已处理复权）
data = reader.get_daily_data(
    symbol="510300",
    start_date="2024-01-01",
    end_date="2024-12-31",
    adjusted=True
)

# 获取 ETF 列表
etf_list = reader.get_etf_list()

# 获取复权因子
adj_factors = reader.get_adjustment_factors("510300")

# 获取交易日历
calendar = reader.get_trading_calendar("2024-01-01", "2024-12-31")
```

### 2. 写入数据迁移

#### 旧代码 (使用 DataService)
```python
from ditto_core.data import DataService

# 存储日线数据
with DataService(duckdb_path="data.duckdb") as service:
    adapter = service.get_duckdb()
    adapter.execute_many(
        "INSERT INTO daily_price VALUES (?, ?, ?, ?, ?, ?)",
        daily_data.to_dicts()
    )
```

#### 新代码 (使用 DataWriter)
```python
from ditto_core.data.adapters import DuckDBAdapter
from ditto_core.data.services.data_writer import DataWriter

# 直接使用业务语义方法
adapter = DuckDBAdapter("data.duckdb")
writer = DataWriter(adapter)

# 存储日线数据
writer.store_daily_data(daily_data)

# 存储 ETF 基本信息
writer.store_etf_info(etf_data)

# 存储复权因子
writer.store_adjustment_factors(adj_data)

# 存储交易日历
writer.store_trading_calendar(calendar_data)
```

### 3. 数据库连接迁移

#### 旧代码 (使用 DataService)
```python
from ditto_core.data import DataService

# 初始化数据库
with DataService(
    duckdb_path="data/duckdb/ditto.duckdb",
    sqlite_path="data/sqlite/ditto.sqlite"
) as service:
    duckdb = service.get_duckdb()
    sqlite = service.get_sqlite()
    # 使用数据库...
```

#### 新代码 (直接使用适配器)
```python
from ditto_core.data.adapters import DuckDBAdapter, SQLiteAdapter

# 直接使用适配器
duckdb = DuckDBAdapter("data/duckdb/ditto.duckdb")
sqlite = SQLiteAdapter("data/sqlite/ditto.sqlite")

try:
    # 使用数据库...
    pass
finally:
    duckdb.close()
    sqlite.close()

# 或使用上下文管理器
with DuckDBAdapter("data/duckdb/ditto.duckdb") as duckdb, \
     SQLiteAdapter("data/sqlite/ditto.sqlite") as sqlite:
    # 使用数据库...
    pass
```

### 4. 特定场景迁移

#### 场景 1: 初始化数据库脚本

**旧代码:**
```python
# scripts/init_db.py
from ditto_core.data import DataService

with DataService(duckdb_path, sqlite_path) as service:
    service.initialize()  # 触发数据库连接
```

**新代码:**
```python
# scripts/init_db.py
from ditto_core.data.adapters import DuckDBAdapter, SQLiteAdapter

duckdb = DuckDBAdapter(duckdb_path)
sqlite = SQLiteAdapter(sqlite_path)

try:
    # 初始化操作
    duckdb.initialize_schema()
    sqlite.initialize_schema()
finally:
    duckdb.close()
    sqlite.close()
```

#### 场景 2: 数据服务类封装

**旧代码:**
```python
class MyDataService:
    def __init__(self):
        self.data_service = DataService(
            duckdb_path="data.duckdb",
            sqlite_path="data.sqlite"
        )

    def get_price(self, symbol):
        return self.data_service.get_duckdb().fetch_df(...)
```

**新代码:**
```python
from ditto_core.data.adapters import DuckDBAdapter
from ditto_core.data.services import DataReader, DataWriter

class MyDataService:
    def __init__(self):
        self.duckdb = DuckDBAdapter("data.duckdb")
        self.reader = DataReader(self.duckdb)
        self.writer = DataWriter(self.duckdb)

    def get_price(self, symbol):
        return self.reader.get_daily_data(symbol, ...)
```

## 新架构的优势

1. **更清晰的职责分离**
   - DataReader 专门处理数据读取
   - DataWriter 专门处理数据写入
   - Adapter 专门处理数据库连接

2. **更易测试**
   - 可以独立测试读取逻辑
   - 可以独立测试写入逻辑

3. **更灵活的组合**
   - 可以为不同的数据库使用不同的 reader/writer
   - 可以实现自定义的数据处理逻辑

4. **更好的错误处理**
   - 每个组件的错误更明确
   - 更容易定位问题

## 注意事项

1. **适配器生命周期管理**
   - 记得调用 `close()` 方法关闭连接
   - 推荐使用上下文管理器 (`with` 语句)

2. **事务处理**
   - DataWriter 的方法通常包含事务处理
   - 如需跨多个操作的事务，请直接使用 adapter

3. **性能考虑**
   - DataReader/DataWriter 使用批量操作优化性能
   - 避免频繁创建/销毁适配器实例

## 迁移检查清单

- [ ] 将所有 `from ditto_core.data import DataService` 替换为具体类导入
- [ ] 替换数据读取逻辑为 DataReader 方法
- [ ] 替换数据写入逻辑为 DataWriter 方法
- [ ] 添加适当的连接管理（close 或 with 语句）
- [ ] 更新相关测试
- [ ] 验证所有功能正常工作

## 获取帮助

如果在迁移过程中遇到问题，请：

1. 查看 DataReader 和 DataWriter 的文档
2. 参考项目中的示例代码
3. 在项目中搜索相关用例

---

*最后更新: 2024-12-11*
