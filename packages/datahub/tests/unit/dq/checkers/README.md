# DQ Checkers 单元测试

## 测试覆盖

DQ Checkers 单元测试覆盖数据质量检查器的各种规则类型。

| 测试文件 | 测试内容 | 规则类型 |
|----------|----------|----------|
| `test_business.py` | 业务规则检查器 | positive, unique, not_null, range |
| `test_statistical.py` | 统计规则检查器 | zscore, iqr, outlier |
| `test_technical.py` | 技术规则检查器 | ohlc, volume, percentage |
| `test_statistical_property.py` | 统计规则 Property 测试 | 基于 Hypothesis |

## 测试内容

### 业务规则检查器（test_business.py）

**测试内容**：
- 正值检查
- 唯一性检查
- 非空检查
- 范围检查

**测试场景**：
1. positive 规则：价格、数量必须为正
2. unique 规则：股票代码唯一性
3. not_null 规则：关键字段非空
4. range 规则：日期范围、数值范围

### 统计规则检查器（test_statistical.py）

**测试内容**：
- Z-score 异常检测
- IQR 异常检测
- 离群值检测

**测试场景**：
1. zscore 规则：检测 3-sigma 异常值
2. iqr 规则：检测 IQR 范围外异常值
3. outlier 规则：综合异常检测

### 技术规则检查器（test_technical.py）

**测试内容**：
- OHLC 逻辑检查
- 成交量检查
- 百分比检查

**测试场景**：
1. ohlc 规则：High >= Low, High >= Open/Close
2. volume 规则：成交量非负
3. percentage 规则：涨跌幅在合理范围

### 统计规则 Property 测试（test_statistical_property.py）

**测试内容**：
- 基于 Hypothesis 的 Property-based 测试
- 随机数据生成
- 边界条件覆盖

**测试场景**：
1. 随机数据 zscore 检查
2. 随机数据 iqr 检查
3. 边界值验证

## 运行测试

### 运行所有 DQ Checkers 测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers -v
```

### 运行特定测试文件

```bash
# 业务规则
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_business.py -v

# 统计规则
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical.py -v

# 技术规则
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_technical.py -v

# Property 测试
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical_property.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_business.py::TestBusinessChecker::test_check_positive_values_pass -v
```

## Property-based 测试

使用 Hypothesis 进行 Property-based 测试：

```python
from hypothesis import given, strategies as st

@given(st.lists(st.floats(min_value=0, max_value=1000), min_size=10))
def test_positive_property(values):
    """所有正数都应该通过 positive 规则"""
    df = pl.DataFrame({"price": values})
    issues = checker.check(df, [{"rule": "positive", "columns": ["price"]}])
    assert len(issues) == 0
```

## 测试数据

使用 Polars 创建测试数据：

```python
def test_with_polars():
    df = pl.DataFrame({
        "sid": [1, 2, 3],
        "open": [10.0, 20.0, 30.0],
        "close": [10.5, 20.5, 30.5],
    })
    issues = checker.check(df, rules)
```

## 预期结果

所有测试应该：

1. **规则正确执行**：规则检查逻辑正确
2. **异常正确检测**：异常值正确识别
3. **边界条件处理**：边界值正确处理
4. **Property 验证通过**：随机数据验证通过

## 故障排查

### 测试失败：规则不匹配

```
AssertionError: Expected 1 issue, but got 0
```

**解决方案**：
1. 检查规则配置
2. 验证测试数据
3. 确认规则参数

### Property 测试失败

```
Falsified: input=[...]
```

**解决方案**：
1. 检查反例数据
2. 修复规则逻辑
3. 调整测试策略

## 相关文档

- [DataHub 单元测试总览](../../README.md)
- [DQ 单元测试总览](../README.md)
