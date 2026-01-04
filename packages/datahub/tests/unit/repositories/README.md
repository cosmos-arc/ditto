# Repositories 单元测试

## 测试覆盖

Repositories 单元测试覆盖 Repository 业务逻辑封装。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_adj_factor_repository.py` | 复权因子 Repository |
| `test_bars_repository.py` | 行情 Repository |
| `test_calendar_repository.py` | 交易日历 Repository |
| `test_index_repository.py` | 指数 Repository |
| `test_security_repository.py` | 证券 Repository |
| `test_universe_repository.py` | 股票池 Repository |

## 测试内容

### 复权因子 Repository（test_adj_factor_repository.py）

**测试内容**：
- 复权因子查询
- 复权因子写入
- 复权因子缓存
- 复权因子验证

**测试场景**：
1. 查询单只股票复权因子
2. 查询多只股票复权因子
3. 查询日期范围复权因子
4. 写入复权因子数据
5. 验证复权因子逻辑

### 行情 Repository（test_bars_repository.py）

**测试内容**：
- 日行情查询
- 分钟行情查询
- 行情聚合
- 行情缓存

**测试场景**：
1. 查询单只股票行情
2. 查询多只股票行情
3. 查询日期范围行情
4. 行情 OHLC 验证
5. 行情涨跌幅计算

### 交易日历 Repository（test_calendar_repository.py）

**测试内容**：
- 交易日查询
- 交易日范围
- 交易日验证
- 交易日缓存

**测试场景**：
1. 查询特定交易日
2. 查询交易日范围
3. 验证是否交易日
4. 查询下一个交易日
5. 查询上一个交易日

### 指数 Repository（test_index_repository.py）

**测试内容**：
- 指数成分股查询
- 指数行情查询
- 指数权重查询
- 指数历史查询

**测试场景**：
1. 查询指数成分股
2. 查询指数行情
3. 查询指数权重
4. 查询指数历史变更

### 证券 Repository（test_security_repository.py）

**测试内容**：
- 证券信息查询
- 证券列表查询
- 证券分类查询
- 证券状态查询

**测试场景**：
1. 查询单只证券信息
2. 查询证券列表
3. 按类型查询证券
4. 查询证券状态

### 股票池 Repository（test_universe_repository.py）

**测试内容**：
- 股票池定义
- 股票池查询
- 股票池历史
- 股票池验证

**测试场景**：
1. 创建股票池
2. 查询股票池成分
3. 查询股票池历史
4. 验证股票池逻辑

## 运行测试

### 运行所有 Repositories 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/repositories -v
```

### 运行特定测试文件

```bash
# 复权因子
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_adj_factor_repository.py -v

# 行情
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_bars_repository.py -v

# 交易日历
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_calendar_repository.py -v

# 指数
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_index_repository.py -v

# 证券
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_security_repository.py -v

# 股票池
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_universe_repository.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_calendar_repository.py::test_is_trading_day -v
```

## Mock 使用

### Mock Store

```python
def test_repository_with_mock_store(mocker):
    """Mock Store 层"""
    mock_store = mocker.Mock()
    mock_store.read.return_value = sample_data

    repo = CalendarRepository(store=mock_store)
    result = repo.get_trading_days(start, end)

    mock_store.read.assert_called_once()
```

### Mock 缓存

```python
def test_repository_cache(mocker):
    """测试缓存逻辑"""
    mock_cache = mocker.Mock()
    mock_cache.get.return_value = None

    repo = CalendarRepository(cache=mock_cache)
    result = repo.get_trading_days(start, end)

    mock_cache.set.assert_called_once()
```

## 预期结果

所有测试应该：

1. **查询正确执行**：查询逻辑正确
2. **数据正确返回**：返回数据格式正确
3. **缓存正确工作**：缓存逻辑正确
4. **验证正确执行**：业务验证正确

## 相关文档

- [DataHub 单元测试总览](../README.md)
