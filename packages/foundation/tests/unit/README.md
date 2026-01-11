# Foundation 单元测试

## 测试覆盖范围

Foundation 单元测试覆盖基础设施的核心组件。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_app_initializer.py` | 应用初始化 |
| `test_observability.py` | 可观测性（日志、追踪、指标） |
| `util/test_dates.py` | 日期工具函数 |
| `util/test_dates_property.py` | 日期 Property 测试 |
| `util/test_io.py` | I/O 工具函数 |

## 测试内容

### 应用初始化（test_app_initializer.py）

**测试内容**：
- 应用初始化流程
- 配置加载
- 环境检测
- 初始化顺序

**测试场景**：
1. 初始化应用
2. 加载配置
3. 检测环境
4. 初始化可观测性

### 可观测性（test_observability.py）

**测试内容**：
- 运行模式检测
- 日志记录
- 追踪功能
- 指标记录
- Span 管理
- Trace ID 和 Span ID

**测试场景**：
1. **模式检测**
   - Production 模式
   - Development 模式
   - Testing 模式
   - Testing With Assertions 模式

2. **日志记录**
   - 不同级别日志
   - 日志格式
   - 日志上下文

3. **追踪功能**
   - Span 创建
   - Span 嵌套
   - Span 属性
   - Trace ID 和 Span ID

4. **指标记录**
   - Counter 指标
   - Gauge 指标
   - Histogram 指标

5. **装饰器**
   - @traced 装饰器
   - @span 上下文管理器

### 日期工具函数（util/test_dates.py）

**测试内容**：
- 日期范围生成
- 交易日计算
- 日期验证
- 日期转换

**测试场景**：
1. 生成日期范围
2. 计算工作日
3. 验证日期
4. 日期格式转换

### 日期 Property 测试（util/test_dates_property.py）

**测试内容**：
- 基于 Hypothesis 的 Property-based 测试
- 随机日期生成
- 边界条件覆盖

**测试场景**：
1. 随机日期范围生成
2. 边界日期验证
3. Property 验证

### I/O 工具函数（util/test_io.py）

**测试内容**：
- 文件读写
- 原子写入
- 路径处理
- 文件锁

**测试场景**：
1. 原子写入文件
2. 读取文件内容
3. 路径处理
4. 文件锁操作

## 运行测试

### 运行所有单元测试

```bash
pixi run -e dev pytest packages/foundation/tests/unit -v
```

### 运行特定测试文件

```bash
# 应用初始化
pixi run -e dev pytest packages/foundation/tests/unit/test_app_initializer.py -v

# 可观测性
pixi run -e dev pytest packages/foundation/tests/unit/test_observability.py -v

# 日期工具
pixi run -e dev pytest packages/foundation/tests/unit/util/test_dates.py -v

# 日期 Property 测试
pixi run -e dev pytest packages/foundation/tests/unit/util/test_dates_property.py -v

# I/O 工具
pixi run -e dev pytest packages/foundation/tests/unit/util/test_io.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/foundation/tests/unit/test_observability.py::test_mode_detection -v
```

### 运行 Property 测试

```bash
pixi run -e dev pytest packages/foundation/tests/unit/util/test_dates_property.py -v
```

## Mock 使用

### 环境变量 Mock

```python
def test_mode_detection(monkeypatch):
    """测试模式检测"""
    # 设置环境变量
    monkeypatch.setenv("DITTO_OBSERVABILITY_MODE", "production")

    config = ObservabilityConfig(environment="production")
    assert config.detect_mode() == Mode.PRODUCTION

    # 清理环境变量
    monkeypatch.delenv("DITTO_OBSERVABILITY_MODE")
```

### 文件系统 Mock

```python
def test_with_tmp_path(tmp_path):
    """使用临时目录"""
    test_file = tmp_path / "test.txt"
    atomic_write(test_file, "content")
    assert test_file.read_text() == "content"
```

### 函数 Mock

```python
def test_with_mocker(mocker):
    """验证函数调用"""
    spy = mocker.spy(logger, "info")
    logger.info("test message")
    spy.assert_called_once_with("test message")
```

## Property-based 测试

使用 Hypothesis 进行 Property-based 测试：

```python
from hypothesis import given, strategies as st

@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))
def test_date_range_property(start_date):
    """日期范围应该包含起始日期"""
    end_date = start_date + timedelta(days=10)
    result = generate_date_range(start_date, end_date)
    assert result[0] == start_date
```

## 预期结果

所有测试应该：

1. **功能正确**：功能实现正确
2. **边界条件处理**：边界条件正确处理
3. **错误处理**：错误情况正确处理
4. **Property 验证通过**：随机数据验证通过

## 相关文档

- [Foundation 测试框架总览](../README.md)
- [Foundation 规范](../../../../../.claude/rules/foundation.md)
