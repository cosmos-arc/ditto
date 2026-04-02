# DataHub 单元测试

## 测试覆盖范围

单元测试覆盖 DataHub 的核心组件，测试隔离、快速（<100ms）。

| 模块 | 测试文件 | 覆盖内容 |
|------|----------|----------|
| **Alerts** | `test_base.py`, `test_manager.py` | 告警基类和告警管理器 |
| **DataHub** | `test_datahub_observability.py` | DataHub 门面可观测性 |
| **DQ** | `test_engine.py`, `test_models.py`, `test_report.py`, `test_result.py` | 数据质量引擎、模型、报告和结果 |
| **DQ Checkers** | `test_business.py`, `test_statistical.py`, `test_technical.py` | 业务规则、统计规则、技术规则检查器 |
| **Meta** | `test_schemas.py`, `test_schema_validator.py` | Schema 定义和验证器 |
| **Repositories** | `test_*.py` | Repository 业务逻辑封装 |
| **Runtime** | `test_*.py` | 运行时基础设施（缓存、文件锁、PIT 辅助） |
| **Sources** | `test_*.py` | 数据源客户端（Tushare HTTP 工具、限流器） |
| **Stores** | `test_*.py` | 存储抽象（Parquet Store、SQLite Client） |
| **Utils** | `test_date_utils.py` | 工具函数 |

## Mock 使用方式

### 简单替换（monkeypatch）

```python
def test_with_fake_time(monkeypatch):
    """使用 fake_time fixture 替换时间函数"""
    # 在 conftest.py 中已定义 autouse fixture
    # time.sleep 和 time.time 已被替换
    ...
```

### 验证调用（mocker）

```python
def test_cache_invalidate(mocker):
    """验证 invalidate 方法被正确调用"""
    spy = mocker.spy(cache, "invalidate")
    # ... 执行代码 ...
    spy.assert_called_once_with("key1")
```

### HTTP Mock（respx）

```python
import respx

def test_tushare_client(respx_mock):
    """Mock Tushare API 响应"""
    respx_mock.post("https://api.tushare.pro").mock(
        return_value=httpx.Response(200, json={"data": {"items": [...]}})
    )
    # ... 执行测试 ...
```

## 运行测试

### 运行所有单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit -v
```

### 运行特定模块

```bash
# DQ 模块
pixi run -e dev pytest packages/datahub/tests/unit/dq -v

# DQ Checkers
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers -v

# Runtime
pixi run -e dev pytest packages/datahub/tests/unit/runtime -v
```

### 运行特定测试文件

```bash
# 特定文件
pixi run -e dev pytest packages/datahub/tests/unit/dq/test_engine.py -v

# 特定测试函数
pixi run -e dev pytest packages/datahub/tests/unit/dq/test_engine.py::test_check_positive -v
```

### 带覆盖率

```bash
pixi run -e dev pytest packages/datahub/tests/unit --cov=packages/datahub/src --cov-report=term-missing
```

## 测试模式

单元测试默认使用 `Mode.TESTING` 模式，在 `conftest.py` 中自动初始化：

```python
@pytest.fixture(autouse=True)
def init_observability():
    """Initialize observability in testing mode for all tests."""
    init(mode=Mode.TESTING)
```

## 边界测试

单元测试重点覆盖边界条件：

- 空数据集
- 单行数据
- 负值、零值
- None/Null 值
- 极端数值（inf, -inf）

## 相关文档

- [DataHub 测试框架总览](../README.md)
- [DQ Checker 测试](dq/checkers/README.md)
- [Runtime 测试](runtime/README.md)
