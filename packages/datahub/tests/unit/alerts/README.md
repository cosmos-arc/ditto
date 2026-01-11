# Alerts 单元测试

## 测试覆盖

Alerts 单元测试覆盖告警系统的核心功能。

| 测试文件 | 测试内容 |
|----------|----------|
| `test_base.py` | 告警基类 |
| `test_manager.py` | 告警管理器 |

## 测试内容

### 告警基类（test_base.py）

**测试内容**：
- 告警级别验证
- 告警严重程度
- 告警消息格式
- 告警元数据

**测试场景**：
1. INFO 级别告警
2. WARNING 级别告警
3. ERROR 级别告警
4. CRITICAL 级别告警
5. 告警消息格式化
6. 告警上下文信息

### 告警管理器（test_manager.py）

**测试内容**：
- 告警发送
- 告警聚合
- 告警过滤
- 告警历史记录

**测试场景**：
1. 发送单个告警
2. 批量发送告警
3. 告警聚合规则
4. 告警过滤条件
5. 告警历史查询
6. 告警统计

## 运行测试

### 运行所有 Alerts 单元测试

```bash
pixi run -e dev pytest packages/datahub/tests/unit/alerts -v
```

### 运行特定测试文件

```bash
# 告警基类
pixi run -e dev pytest packages/datahub/tests/unit/alerts/test_base.py -v

# 告警管理器
pixi run -e dev pytest packages/datahub/tests/unit/alerts/test_manager.py -v
```

### 运行特定测试函数

```bash
pixi run -e dev pytest packages/datahub/tests/unit/alerts/test_base.py::test_alert_info_level -v
```

## 测试模式

使用 `Mode.TESTING` 模式（在 `conftest.py` 中自动初始化）：

```python
@pytest.fixture(autouse=True)
def init_observability():
    init(mode=Mode.TESTING)
```

## Mock 使用

### Mock 告警发送

```python
def test_alert_send(mocker):
    """验证告警发送"""
    spy = mocker.spy(manager, "send")
    manager.send_alert("Test message")
    spy.assert_called_once()
```

### Mock 外部依赖

```python
def test_with_mock_notifier(monkeypatch):
    """Mock 外部通知服务"""
    def mock_send(alert):
        return True

    monkeypatch.setattr("ditto_datahub.alerts.notifier.send", mock_send)
```

## 预期结果

所有测试应该：

1. **告警正确创建**：级别、消息、上下文正确
2. **告警正确发送**：管理器正确发送告警
3. **告警正确聚合**：相似告警正确聚合
4. **告警正确过滤**：过滤规则正确工作

## 相关文档

- [DataHub 单元测试总览](../README.md)
