# Foundation 测试框架

## 测试框架

Foundation 测试使用以下技术栈：

- **pytest** - 测试运行器和测试组织
- **polars.testing** - DataFrame 断言和验证
- **pytest-mock** - Mock 框架
- **monkeypatch** - 简单替换和环境变量设置

## 测试标记

Foundation 测试使用以下标记分类：

| 标记 | 描述 | 运行时机 |
|------|------|----------|
| `integration` | 集成测试（多组件协作） | CI |
| `unit` | 单元测试（快速隔离） | 每次提交 |

## 测试结构

```
tests/
├── conftest.py              # 共享 fixtures（如果有）
├── integration/             # 集成测试
└── unit/                    # 单元测试
    ├── test_app_initializer.py   # 应用初始化
    ├── test_observability.py     # 可观测性
    └── util/                      # 工具函数
        ├── test_dates.py          # 日期工具
        ├── test_dates_property.py # 日期 Property 测试
        └── test_io.py             # I/O 工具
```

## 测试覆盖

### 集成测试

| 测试目录 | 测试内容 |
|----------|----------|
| `integration/` | 可观测性集成测试（如果有） |

### 单元测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_app_initializer.py` | 应用初始化 |
| `test_observability.py` | 可观测性（日志、追踪、指标） |
| `util/test_dates.py` | 日期工具函数 |
| `util/test_dates_property.py` | 日期 Property 测试 |
| `util/test_io.py` | I/O 工具函数 |

## 运行测试

### 本地开发（快速）

```bash
# 只运行单元测试
pixi run -e dev pytest packages/foundation/tests/unit -v

# 运行特定标记
pixi run -e dev pytest packages/foundation/tests -m unit
pixi run -e dev pytest packages/foundation/tests -m integration

# 运行特定目录
pixi run -e dev pytest packages/foundation/tests/unit/util -v
```

### 完整测试（CI）

```bash
# 运行所有测试
pixi run -e dev pytest packages/foundation/tests -v --cov

# 包含覆盖率报告
pixi run -e dev pytest packages/foundation/tests --cov-report=html
```

### 运行特定测试文件

```bash
# 可观测性测试
pixi run -e dev pytest packages/foundation/tests/unit/test_observability.py -v

# 日期工具测试
pixi run -e dev pytest packages/foundation/tests/unit/util/test_dates.py -v

# I/O 工具测试
pixi run -e dev pytest packages/foundation/tests/unit/util/test_io.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/foundation/tests/unit/test_observability.py::test_mode_detection -v
```

## 测试规范

### AAA 模式

所有测试遵循 Arrange-Act-Assert 模式：

```python
def test_mode_detection():
    # Arrange - 准备测试数据
    original_mode = os.environ.get("DITTO_OBSERVABILITY_MODE")

    try:
        # Act - 执行被测代码
        os.environ["DITTO_OBSERVABILITY_MODE"] = "production"
        config = ObservabilityConfig(environment="production")

        # Assert - 验证结果
        assert config.detect_mode() == Mode.PRODUCTION
    finally:
        # Cleanup - 清理
        if original_mode is None:
            os.environ.pop("DITTO_OBSERVABILITY_MODE", None)
```

### Mock 选择

| 场景 | 工具 |
|------|------|
| 简单替换 | `monkeypatch.setattr()` / `monkeypatch.setenv()` |
| 验证调用 | `pytest-mock (mocker)` |
| 环境变量 | `monkeypatch.setenv()` / `monkeypatch.delenv()` |

### 环境变量测试

使用 `monkeypatch` 修改环境变量：

```python
def test_with_env_var(monkeypatch):
    """测试环境变量处理"""
    monkeypatch.setenv("DITTO_ENV", "testing")
    settings = Settings()
    assert settings.mode == Mode.TESTING
```

## 代码覆盖率要求

- **分支覆盖率**: >= 80%
- **单元测试占比**: 70%
- **集成测试占比**: 20%

## 相关文档

- [Foundation 单元测试](unit/README.md)
- [Foundation 集成测试](integration/README.md)
- [Foundation 规范](../../../../../.claude/rules/foundation.md)
