# DataHub 测试框架

## 测试框架

DataHub 测试使用以下技术栈：

- **pytest** - 测试运行器和测试组织
- **polars.testing** - DataFrame 断言和验证
- **hypothesis** - Property-based 测试（边界条件验证）
- **respx** - HTTP 请求 Mock（外部 API 测试）
- **inline-snapshot** - 快照测试（复杂数据结构验证）
- **time_machine** - 时间控制（确定性测试）

## 测试标记

DataHub 测试使用以下标记分类：

| 标记 | 描述 | 运行时机 |
|------|------|----------|
| `integration` | 集成测试（多组件协作） | CI |
| `pit` | PIT 数据验证（时间点数据正确性） | CI |
| `external` | 外部 API 调用（Tushare 等） | 手动 |
| `slow` | 耗时测试（>1 秒） | CI/手动 |
| `unit` | 单元测试（快速隔离） | 每次提交 |

## 测试结构

```
tests/
├── conftest.py              # 共享 fixtures
├── fixtures/                # 测试数据 fixtures
│   └── dq/                  # DQ 规则配置
├── unit/                    # 单元测试（70%）
│   ├── alerts/              # 告警系统
│   ├── datahub/             # DataHub 门面
│   ├── dq/                  # 数据质量引擎
│   ├── meta/                # 元数据验证
│   ├── accessors/           # Accessor 业务逻辑
│   ├── runtime/             # 运行时基础设施
│   ├── sources/             # 数据源客户端
│   ├── stores/              # 存储抽象
│   └── utils/               # 工具函数
└── integration/             # 集成测试（20%）
    ├── runtime/             # 运行时集成测试
    ├── sources/             # 数据源 E2E 测试
    └── stores/              # 存储并发测试
```

## 运行测试

### 本地开发（快速）

```bash
# 只运行单元测试（跳过慢速和外部测试）
pixi run -e dev pytest packages/datahub/tests/unit -m "not slow and not external"

# 运行特定标记
pixi run -e dev pytest packages/datahub/tests -m unit
pixi run -e dev pytest packages/datahub/tests -m integration
pixi run -e dev pytest packages/datahub/tests -m pit

# 运行特定目录
pixi run -e dev pytest packages/datahub/tests/unit/dq
pixi run -e dev pytest packages/datahub/tests/integration/runtime
```

### 完整测试（CI）

```bash
# 运行所有测试（跳过 external）
pixi run -e dev pytest packages/datahub/tests -m "not external" --cov

# 包含覆盖率报告
pixi run -e dev pytest packages/datahub/tests -m "not external" --cov-report=html
```

### 外部 API 测试（手动）

```bash
# 需要设置 TUSHARE_TOKEN
export TUSHARE_TOKEN="your_token"
pixi run -e dev pytest packages/datahub/tests/integration/sources/tushare -m external -v
```

### PIT 验证测试

```bash
# 验证时间点数据正确性
pixi run -e dev pytest packages/datahub/tests -m pit -v
```

## Fixtures

### 共享 Fixtures（conftest.py）

- `fake_time` - 可控的时间（跳过 sleep，加速测试）
- `init_observability()` - 自动初始化可观测性（autouse）

### 测试数据 Fixtures

- `sample_*` - 标准测试数据
- `empty_*` - 空数据/边界测试
- `duckdb_conn` / `sqlite_conn` - 内存数据库连接

## 测试规范

### AAA 模式

所有测试遵循 Arrange-Act-Assert 模式：

```python
def test_check_positive_values_fail():
    # Arrange - 准备测试数据
    df = pl.DataFrame({"open": [10.0, -5.0, 30.0]})

    # Act - 执行被测代码
    issues = checker.check(df, rules)

    # Assert - 验证结果
    assert len(issues) == 1
    assert issues[0].severity == DQSeverity.ERROR
```

### DataFrame 测试

使用 `polars.testing.assert_frame_equal` 进行 DataFrame 断言：

```python
from polars.testing import assert_frame_equal

assert_frame_equal(result, expected, atol=1e-4)  # 浮点容差
```

### Mock 选择

| 场景 | 工具 |
|------|------|
| 简单替换 | `monkeypatch.setattr()` |
| 验证调用 | `pytest-mock (mocker)` |
| HTTP 请求 | `respx` |

## 代码覆盖率要求

- **分支覆盖率**: >= 80%
- **单元测试占比**: 70%
- **集成测试占比**: 20%

## 相关文档

- [测试规范](../../../../../.claude/rules/python-test.md)
- [PIT 数据安全](../../../../../.claude/rules/pit.md)
- [DataHub 架构规范](../../../../../.claude/rules/datahub.md)
