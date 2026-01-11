# Utils 单元测试

## 测试覆盖

Utils 单元测试覆盖工具函数的核心功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_date_utils.py` | 日期工具函数 |

## 测试内容

### 日期工具函数（test_date_utils.py）

**测试内容**：
- 日期范围生成
- 交易日计算
- 日期验证
- 日期转换

**测试场景**：
1. 生成日期范围
2. 计算下一个交易日
3. 计算上一个交易日
4. 验证日期格式
5. 日期字符串转换
6. Knowledge Date 计算
7. 工作日计算

## 运行测试

### 运行所有 Utils 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/utils -v
```

### 运行特定测试文件

```bash
pixi run -e dev pytest packages/datahub/tests/unit/utils/test_date_utils.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/utils/test_date_utils.py::test_generate_date_range -v
```

## 测试数据

使用标准日期进行测试：

```python
def test_date_utils():
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 31)

    result = generate_date_range(start_date, end_date)
    assert len(result) == 31
    assert result[0] == start_date
    assert result[-1] == end_date
```

## 边界测试

重点测试边界条件：

```python
def test_boundary_cases():
    # 单日范围
    result = generate_date_range(date(2024, 1, 1), date(2024, 1, 1))
    assert len(result) == 1

    # 反向范围
    result = generate_date_range(date(2024, 1, 31), date(2024, 1, 1))
    assert len(result) == 0

    # 月末
    end_date = date(2024, 1, 31)
    assert is_month_end(end_date)

    # 年末
    end_date = date(2024, 12, 31)
    assert is_year_end(end_date)
```

## PIT 相关测试

测试 Knowledge Date 计算：

```python
def test_knowledge_date_calculation():
    """Knowledge Date 应该是 Trade Date + 1"""
    trade_date = date(2024, 1, 15)
    knowledge_date = calculate_knowledge_date(trade_date)
    expected = date(2024, 1, 16)
    assert knowledge_date == expected
```

## 预期结果

所有测试应该：

1. **日期范围正确**：生成的日期范围正确
2. **交易日计算正确**：交易日计算逻辑正确
3. **日期验证正确**：日期验证逻辑正确
4. **日期转换正确**：日期字符串转换正确
5. **Knowledge Date 正确**：Knowledge Date 计算正确

## 相关文档

- [DataHub 单元测试总览](../README.md)
- [PIT 数据安全](../../../../../.claude/rules/pit.md)
