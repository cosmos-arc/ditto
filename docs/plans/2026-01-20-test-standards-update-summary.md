# 测试规范更新总结

**更新日期**: 2026-01-20
**更新范围**: 单元测试 vs 集成测试边界、可观测性测试最佳实践

---

## 核心原则更新

### 测试分类重新定义

| 测试类型 | 占比 | 目标 | Mock 策略 |
|---------|------|------|----------|
| **单元测试** | 80% | 单个类的原子功能 | **完全 Mock** |
| **集成测试** | 20% | 系统/外部的"接缝"处 | **真实组件** |
| ~~E2E 测试~~ | **暂不引入** | - | - |

### 核心判断标准

**是否测试系统与外部的"接缝"处？**

- **单元测试**: 测试单个类的逻辑功能，使用 **完全 Mock** 隔离依赖
- **集成测试**: 测试"接缝"处的契约和配置，使用 **真实组件** + **临时资源**

---

## 关键变化

### 1. 测试目标

| 测试维度 | 单元测试 ✅ | 集成测试 ✅ |
|---------|-----------|-------------|
| **测试目标** | 单个类的原子功能 | 系统/外部的"接缝"处 |
| **依赖策略** | **完全 Mock** | **真实组件** |
| **数据持久化** | 不关心 | 关键（验证写入/读取） |
| **外部调用** | Mock HTTP 调用 | 真实 Client + Mock 响应 |
| **典型场景** | 算法逻辑、状态机、数据转换 | DAO、HTTP Client、消息队列 |
| **速度** | 快（毫秒级） | 慢（秒级，有真实 IO） |
| **资源隔离** | Mock（无状态） | `:memory:` / `tmp_path` |

### 2. 测试分类决策树

```
开始
  ↓
测试目标是什么？
  ├─ 单个类的逻辑功能 → 单元测试 ✅（完全 Mock）
  └─ 系统/外部的接口 → 集成测试 ✅（真实组件）
      ↓
      接缝类型是什么？
      ├─ DAO/数据库 → 集成测试（验证写入/读取）
      ├─ HTTP Client/API → 集成测试（验证响应解析）
      └─ 消息队列/缓存 → 集成测试（验证序列化/网络）
```

### 3. 资源隔离策略

| 资源类型 | 单元测试 | 集成测试 |
|---------|---------|-------------|
| **SQLite** | `mocker.Mock()` | `:memory:`（内存数据库） |
| **Parquet** | `mocker.Mock()` | `tmp_path`（临时目录） |
| **HTTP** | `respx.mock()` | 真实 Client + Mock 响应 |
| **文件** | 不关心 | `tmp_path`（临时目录） |

---

## 可观测性测试最佳实践

### 核心原则

**测试你的代码是否正确"发射"了数据，不测试外部服务本身**

### 最佳实践

- ✅ 使用 In-Memory Registry（Prometheus `CollectorRegistry`）
- ✅ 验证关键指标的发射
- ❌ 不测试 VictoriaMetrics 服务
- ❌ 不过度测试（每个日志点都测）

### 测试覆盖策略

| 指标类型 | 测试策略 | 示例 |
|---------|---------|------|
| **关键指标** | 必须测试 | 摄入成功率、API 调用计数 |
| **诊断指标** | 可选测试 | 处理耗时、队列大小 |
| **调试日志** | 不测试 | 日志太多，成本高 |

### 示例代码

```python
# ✅ 正确：使用 In-Memory Registry

from prometheus_client import CollectorRegistry

@pytest.mark.integration
def test_data_ingestion_emits_metrics():
    """测试数据摄入正确发射指标"""
    registry = CollectorRegistry()

    # 执行业务操作
    records = ingest_stock_daily(
        symbol="000001.SZ",
        date="2024-01-02",
        registry=registry
    )

    # 验证关键指标
    success_count = registry.get_sample_value("ingestion_records_total", {
        "status": "success",
        "source": "tushare"
    })
    assert success_count == len(records)
```

---

## 常见误区澄清

### ❌ 误区 1: 多个组件协作 = 集成测试

**错误理解**: 使用了多个组件 = 集成测试
**正确理解**: 只要所有依赖都是 Mock = 单元测试

```python
# ✅ 正确：单元测试（Mock 所有依赖）
def test_facade_delegates_correctly(mocker):
    mock_dep1 = mocker.Mock()
    mock_dep2 = mocker.Mock()

    facade = Facade(dep1, dep2)
    facade.do_something()

    # 验证委托逻辑（单元测试）
    mock_dep1.method1.assert_called_once()
```

### ❌ 误区 2: 集成测试需要固定路径文件

**错误理解**: 集成测试必须使用固定路径的数据库文件
**正确理解**: 集成测试也使用临时资源（`:memory:`、`tmp_path`）隔离

```python
# ✅ 正确：集成测试（使用 :memory:）
@pytest.mark.integration
def test_security_store_can_write_sqlite():
    pool = SQLitePool(":memory:", schema_path=_SCHEMA_PATH)
    pool.init_schema()

    store = SecurityStore(SQLiteClient(pool))
    store.add_security(sid=1000001, symbol="000001.SZ")

    df = store.get_by_sid(1000001)
    assert df["symbol"][0] == "000001.SZ"
```

---

## 测试规范文档位置

完整测试规范: [`.claude/rules/python-test.md`](.claude/rules/python-test.md)

### 文档章节

1. **目录结构** - 80% 单元测试 + 20% 集成测试
2. **单元测试 vs 集成测试边界** - 核心判断标准
3. **可观测性测试** - In-Memory Registry 最佳实践
4. **Marker 规范** - 移除 E2E marker
5. **运行命令** - 单元测试和集成测试命令

---

## 后续行动

### P1: 创建 Pre-commit 检查脚本

- [ ] 创建 `scripts/check_pytest_markers.py`
- [ ] 更新 `.pre-commit-config.yaml`

### P2: 验证测试通过

- [ ] 运行 `pytest tests/unit/` 确保所有单元测试通过
- [ ] 运行 `pytest -m integration` 确保集成测试通过
- [ ] 运行 `pixi run -e dev ci` 完整 CI 检查

---

## 参考资料

- [Using DI container in unit tests - StackOverflow](https://stackoverflow.com/questions/32594803/using-di-container-in-unit-tests)
- [How not to do DI: configuring the IoC container in unit test projects - DevTrends](https://www.devtrends.co.uk/blog/how-not-to-do-dependency-injection-configuring-the-ioc-container-in-unit-test-projects)
- [Prometheus Python Client - CollectorRegistry](https://github.com/prometheus/client_python#custom-collector-registry-for-tests)
