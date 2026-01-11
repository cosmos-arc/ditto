# Stores 单元测试

## 测试覆盖

Stores 单元测试覆盖存储抽象层的核心功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_adj_factor_store.py` | 复权因子 Store |
| `test_bars_store.py` | 行情 Store |
| `test_calendar_store.py` | 交易日历 Store |
| `test_index_weight_store.py` | 指数权重 Store |
| `test_security_store.py` | 证券 Store |
| `test_sqlite_client.py` | SQLite 客户端 |
| `test_stock_status_store.py` | 股票状态 Store |
| `test_universe_store.py` | 股票池 Store |

## 测试内容

### 复权因子 Store（test_adj_factor_store.py）

**测试内容**：
- 复权因子写入
- 复权因子读取
- 复权因子分区
- 复权因子验证

**测试场景**：
1. 写入复权因子数据
2. 读取复权因子数据
3. 按股票代码分区
4. 验证数据完整性

### 行情 Store（test_bars_store.py）

**测试内容**：
- 行情写入
- 行情读取
- 行情分区
- 行情聚合

**测试场景**：
1. 写入日行情数据
2. 读取日行情数据
3. 按日期/股票分区
4. 行情数据聚合

### 交易日历 Store（test_calendar_store.py）

**测试内容**：
- 交易日历写入
- 交易日历读取
- 交易日历缓存
- 交易日历查询

**测试场景**：
1. 写入交易日历
2. 读取交易日历
3. 查询交易日
4. 缓存验证

### 指数权重 Store（test_index_weight_store.py）

**测试内容**：
- 指数权重写入
- 指数权重读取
- 指数权重历史
- 指数权重查询

**测试场景**：
1. 写入指数权重
2. 读取指数权重
3. 查询历史权重
4. 查询特定日期权重

### 证券 Store（test_security_store.py）

**测试内容**：
- 证券信息写入
- 证券信息读取
- 证券信息更新
- 证券信息查询

**测试场景**：
1. 写入证券信息
2. 读取证券信息
3. 更新证券信息
4. 按类型查询证券

### SQLite 客户端（test_sqlite_client.py）

**测试内容**：
- 连接管理
- SQL 执行
- 事务处理
- 连接池

**测试场景**：
1. 创建连接
2. 执行 SQL
3. 事务提交/回滚
4. 连接池管理

### 股票状态 Store（test_stock_status_store.py）

**测试内容**：
- 股票状态写入
- 股票状态读取
- 股票状态查询
- 股票状态历史

**测试场景**：
1. 写入股票状态
2. 读取股票状态
3. 查询特定日期状态
4. 查询状态变更历史

### 股票池 Store（test_universe_store.py）

**测试内容**：
- 股票池写入
- 股票池读取
- 股票池历史
- 股票池查询

**测试场景**：
1. 写入股票池
2. 读取股票池
3. 查询历史股票池
4. 按日期查询股票池

## 运行测试

### 运行所有 Stores 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/stores -v
```

### 运行特定测试文件

```bash
# 复权因子
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_adj_factor_store.py -v

# 行情
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_bars_store.py -v

# 交易日历
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_calendar_store.py -v

# 指数权重
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_index_weight_store.py -v

# 证券
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_security_store.py -v

# SQLite 客户端
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_sqlite_client.py -v

# 股票状态
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_stock_status_store.py -v

# 股票池
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_universe_store.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/stores/test_calendar_store.py::test_write_calendar -v
```

## 临时目录使用

使用 `tmp_path` fixture 创建临时目录：

```python
def test_with_temp_store(tmp_path):
    """使用临时目录测试 Store"""
    store = CalendarStore(base_path=tmp_path / "calendar")

    # 写入数据
    store.save(data)

    # 数据写入到 tmp_path
    assert (tmp_path / "calendar").exists()

    # 测试结束后自动清理
```

## 预期结果

所有测试应该：

1. **数据正确写入**：Parquet 文件正确写入
2. **数据正确读取**：读取数据格式正确
3. **分区正确工作**：分区逻辑正确
4. **缓存正确工作**：缓存逻辑正确
5. **查询正确执行**：查询逻辑正确

## 相关文档

- [DataHub 单元测试总览](../README.md)
- [Stores 集成测试](../../integration/stores/README.md)
