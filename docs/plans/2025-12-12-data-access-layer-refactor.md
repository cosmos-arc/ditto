# 数据访问层重构报告

## 概述
完成了数据访问层的重构，去掉了不必要的adapter抽象层，采用配置驱动的直接数据库管理方式。

## 主要改动

### 1. 新的DataReader实现
- 文件位置：`packages/core/src/ditto_core/data/services/new_data_reader.py`
- 直接管理DuckDB和SQLite连接
- 方法内部明确使用哪个数据库
- 提供`for_testing()`类方法用于测试

### 2. 新的DataWriter实现
- 文件位置：`packages/core/src/ditto_core/data/services/new_data_writer.py`
- 直接管理DuckDB和SQLite连接
- 支持DataFrame和字典列表两种输入格式
- 自动添加knowledge_date字段
- 提供`for_testing()`类方法用于测试

### 3. 向后兼容层
- 文件位置：`packages/core/src/ditto_core/data/adapters/compat.py`
- 提供旧的adapter接口的兼容性实现
- 包含简单的DuckDB和SQLite包装器
- 现有代码不会立即破坏

### 4. 旧文件处理
- 重命名旧的adapter文件，添加`_deprecated`后缀：
  - `duckdb_adapter.py` → `duckdb_adapter_deprecated.py`
  - `sqlite_adapter.py` → `sqlite_adapter_deprecated.py`
  - `base.py` → `base_deprecated.py`

### 5. 关键代码更新
- `apps/server/src/ditto_server/api/data.py`：更新为使用新的DataReader
- `apps/server/src/ditto_server/api/update.py`：更新为使用新的DataReader
- `packages/core/src/ditto_core/data/services/__init__.py`：导出新的类

## 优势

1. **更简单的架构**：去掉了中间层，代码更直观
2. **更好的性能**：减少了间接调用
3. **更容易理解**：业务方法明确知道使用哪个数据库
4. **更易于测试**：`for_testing()`方法简化了测试设置
5. **配置驱动**：通过配置文件决定数据库路径

## 数据存储策略

- **DuckDB**：市场数据（ETF信息、日线数据、复权因子、交易日历）
- **SQLite**：交易数据（订单、成交、持仓）

## 测试覆盖

- 单元测试：`packages/core/tests/unit/data/test_new_data_reader.py`
- 单元测试：`packages/core/tests/unit/data/test_new_data_writer.py`
- 集成测试：`packages/core/tests/integration/data/test_data_reader_integration.py`

## 迁移指南

### 新代码
```python
from ditto_core.data.services import DataReader, DataWriter

# 创建实例（自动使用配置的数据库路径）
reader = DataReader()
writer = DataWriter()

# 测试代码
test_reader = DataReader.for_testing()
test_writer = DataWriter.for_testing()
```

### 旧代码（仍然可用，但会显示弃用警告）
```python
from ditto_core.data.adapters import DuckDBAdapter, SQLiteAdapter
from ditto_core.data.services.data_reader import DataReader

# 这种方式仍然有效，但不推荐
adapter = DuckDBAdapter("path/to/db")
reader = DataReader(adapter)
```

## 后续建议

1. 逐步迁移剩余使用adapter的代码
2. 在1-2个版本后完全移除adapter相关代码
3. 考虑添加连接池功能以提高性能
4. 添加更多的集成测试覆盖完整数据流
