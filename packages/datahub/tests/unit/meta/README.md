# Meta 单元测试

## 测试覆盖

Meta 单元测试覆盖元数据验证功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_schemas.py` | Schema 定义 |
| `test_schema_validator.py` | Schema 验证器 |

## 测试内容

### Schema 定义（test_schemas.py）

**测试内容**：
- Schema 模型定义
- Schema 字段类型
- Schema 约束条件
- Schema 序列化

**测试场景**：
1. 交易日历 Schema
2. 股票基础信息 Schema
3. 日行情 Schema
4. 复权因子 Schema
5. Schema 字段验证

### Schema 验证器（test_schema_validator.py）

**测试内容**：
- Schema 验证逻辑
- 错误消息生成
- 批量验证
- 自定义验证规则

**测试场景**：
1. 验证符合 Schema 的数据
2. 验证不符合 Schema 的数据
3. 生成详细的错误消息
4. 批量验证多个数据集
5. 自定义验证规则

## 运行测试

### 运行所有 Meta 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/meta -v
```

### 运行特定测试文件

```bash
# Schema 定义
pixi run -e dev pytest packages/datahub/tests/unit/meta/test_schemas.py -v

# Schema 验证器
pixi run -e dev pytest packages/datahub/tests/unit/meta/test_schema_validator.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/meta/test_schemas.py::test_calendar_schema -v
```

## 测试数据

使用 Polars 创建测试数据：

```python
def test_schema_validation():
    valid_data = pl.DataFrame({
        "date": [date(2024, 1, 1), date(2024, 1, 2)],
        "is_trading_day": [True, False],
        "knowledge_date": [date(2024, 1, 1), date(2024, 1, 1)],
    })

    is_valid, errors = validator.validate(valid_data, CalendarSchema)
    assert is_valid
    assert len(errors) == 0
```

## 预期结果

所有测试应该：

1. **Schema 正确定义**：Schema 模型符合预期
2. **验证正确执行**：验证逻辑正确
3. **错误正确报告**：错误消息清晰准确
4. **批量验证正确**：批量验证逻辑正确

## 相关文档

- [DataHub 单元测试总览](../README.md)
