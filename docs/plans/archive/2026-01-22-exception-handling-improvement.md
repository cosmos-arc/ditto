# 异常处理精确化改进设计

> **创建日期**: 2026-01-22
> **作者**: Claude Code
> **状态**: 设计中
> **关联**: [架构重构路线图](2026-01-22-architecture-refactor-roadmap.md) Phase 2 Task 2.2

---

## 执行摘要

**目标**: 将项目中 26 处宽泛的 `except Exception` 捕获改进为精确的异常处理，提升错误诊断能力和系统健壮性。

**核心策略**: **分类处理** - 根据不同场景采用不同的异常处理策略：
- **网络/数据处理异常** → 精确捕获 + 重新抛出
- **顶层异常处理** → 完整日志 + 重新抛出
- **通知发送异常** → 优雅降级 + 警告日志
- **资源清理异常** → 静默失败 + 警告日志

**预期成果**:
- 减少 80% 的宽泛异常捕获
- 所有异常都有完整的堆栈日志
- 提升错误诊断效率

---

## 现状分析

### 异常捕获分布统计

| 类别 | 文件数 | 典型位置 | 风险等级 |
|------|--------|----------|----------|
| **A: 网络请求** | 2 | `tushare/client.py` | 中 |
| **B: 顶层处理** | 6 | `main.py`, `coordinator.py`, `l3_batch_service.py`, `dq_batch.py`, `registry/notification.py` | 低 |
| **C: 数据处理** | 1 | `quality/checkers/statistical.py` | 中 |
| **D: 通知发送** | 4 | `notification.py`, `webhook.py`, `email.py`, `manager.py` | 低 |
| **E: 资源清理** | 3 | `sqlite_pool.py`, `observability/__init__.py`, 测试文件 | 低 |

**总计**: 约 16 个源文件，26 处异常捕获（不含测试）

---

## 异常处理策略设计

### 策略 1: 网络请求异常 - 精确捕获 + 重新抛出

**场景**: HTTP 请求、Token 加载

**目标**: 让调用者能够区分不同的错误原因并采取不同策略（重试、告警、降级）

**实现示例**:

```python
# packages/data/src/ditto_data/sources/tushare/client.py

# 修改前
try:
    keyring_token = keyring.get_password("ditto", "tushare")
    if keyring_token is not None:
        return keyring_token
except Exception as e:
    logger.debug("Keyring not available, skipping", error=str(e))

# 修改后
try:
    keyring_token = keyring.get_password("ditto", "tushare")
    if keyring_token is not None:
        return keyring_token
except (keyring.errors.KeyringError,
        keyring.errors.KeyringLocked,
        keyring.errors.PasswordSetError) as e:
    logger.debug(
        "Keyring not available, skipping",
        keyring_error=type(e).__name__,
    )
except OSError as e:
    # keyring 可能抛出的文件系统相关错误
    logger.debug(
        "Keyring OS error, skipping",
        os_error=str(e),
    )
```

**异常类型**:
- `keyring.errors.KeyringError` - Keyring 通用错误
- `keyring.errors.KeyringLocked` - Keyring 已锁定
- `OSError` - 文件系统错误
- `httpx.TimeoutException` - 请求超时
- `httpx.NetworkError` - 网络错误
- `httpx.HTTPStatusError` - HTTP 状态码错误

---

### 策略 2: 数据处理异常 - Polars 精确捕获

**场景**: Polars DataFrame 计算、Schema 验证

**目标**: 区分计算错误、Schema 错误、数据类型错误

**实现示例**:

```python
# packages/core/src/ditto_core/quality/checkers/statistical.py

# 修改前
try:
    df = df.with_columns(
        ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
    )
except Exception as e:
    logger.exception("dq_zscore_computation_failed")
    return DQIssue(...)

# 修改后
try:
    df = df.with_columns(
        ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
    )
except (pl.ComputeError, pl.SchemaError, pl.ColumnNotFoundError) as e:
    logger.exception(
        "dq_zscore_computation_failed",
        error_type=type(e).__name__,
        column=column,
    )
    return DQIssue(
        level=DQLevel.L3_STATISTICAL,
        severity=DQSeverity.ALERT,
        rule_name="zscore",
        message=f"Z-score check failed for column '{column}': {type(e).__name__}",
        affected_rows=0,
        sample_data=[],
    )
except ValueError as e:
    # 统计计算中的数值错误（如除零、无效统计量）
    logger.warning(
        "dq_zscore_invalid_value",
        error=str(e),
        column=column,
    )
    return DQIssue(
        level=DQLevel.L3_STATISTICAL,
        severity=DQSeverity.WARNING,  # 降低严重程度
        rule_name="zscore",
        message=f"Invalid statistical value for '{column}': {e}",
        affected_rows=0,
        sample_data=[],
    )
```

**异常类型**:
- `pl.ComputeError` - Polars 计算错误
- `pl.SchemaError` - Schema 不匹配
- `pl.ColumnNotFoundError` - 列不存在
- `ValueError` - 数值错误（除零、无效统计量）

---

### 策略 3: 顶层异常处理 - 完整日志 + 重新抛出

**场景**: Application 层的顶层异常捕获

**目标**: 确保异常堆栈完整记录，不丢失诊断信息

**实现示例**:

```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py

# 修改前
try:
    df = self._source.fetch(dataset, trade_date)
except SourceFetchError as e:
    return self._result_handler.handle_fetch_error(dataset, trade_date, e)
except Exception as e:
    return self._result_handler.handle_unknown_error(dataset, trade_date, e)

# 修改后
try:
    df = self._source.fetch(dataset, trade_date)
except SourceFetchError as e:
    # 已知的业务异常，直接处理
    return self._result_handler.handle_fetch_error(dataset, trade_date, e)
except (httpx.NetworkError, httpx.TimeoutException) as e:
    # 网络相关异常，转换为业务异常后处理
    logger.exception(
        "network_error_during_fetch",
        dataset=dataset,
        trade_date=trade_date,
    )
    fetch_error = SourceFetchError(
        message=f"Network error fetching {dataset}: {e}",
        source=type(e).__name__,
    )
    return self._result_handler.handle_fetch_error(dataset, trade_date, fetch_error)
except Exception as e:
    # 未知异常，记录完整堆栈后处理
    logger.exception(
        "unexpected_error_during_fetch",
        dataset=dataset,
        trade_date=trade_date,
        error_type=type(e).__name__,
    )
    return self._result_handler.handle_unknown_error(dataset, trade_date, e)
```

**关键改进**:
1. 使用 `logger.exception()` 记录完整堆栈
2. 添加 `error_type` 字段用于日志过滤
3. 保留兜底的 `except Exception` 但记录详细信息

---

### 策略 4: 通知发送异常 - 优雅降级

**场景**: 邮件、Webhook 通知发送

**目标**: 单个通知渠道失败不应影响其他渠道或主流程

**实现示例**:

```python
# apps/port/src/ditto_port/registry/notification.py

# 修改前
try:
    return NotificationSettings()
except Exception as e:
    logger.warning("Failed to load notification settings, using defaults")
    return NotificationSettings()

# 修改后
try:
    return NotificationSettings()
except (ValidationError, ValueError) as e:
    logger.warning(
        "notification_settings_validation_failed",
        error=str(e),
    )
    # 返回默认配置
    return NotificationSettings()
```

**异常类型**:
- `pydantic.ValidationError` - 配置验证失败
- `smtplib.SMTPException` - SMTP 错误
- `ConnectionError` - 连接失败
- `TimeoutError` - 发送超时

---

### 策略 5: 资源清理 - 静默失败 + 警告日志

**场景**: 数据库连接关闭、文件句柄释放

**目标**: 清理失败不应影响程序退出，但需要记录

**实现示例**:

```python
# packages/foundation/src/ditto_foundation/db/sqlite_pool.py

# 修改前
try:
    conn.close()
except Exception:
    pass

# 修改后
try:
    conn.close()
except sqlite3.Error as e:
    logger.warning(
        "failed_to_close_connection",
        error=str(e),
    )
finally:
    # 确保资源标记为已关闭
    self._closed = True
```

---

## TDD 实施流程

### RED 阶段：写失败测试

```python
# tests/datahub/sources/tushare/test_client_errors.py

def test_keyring_locked_falls_back_to_secrets(monkeypatch):
    """当 keyring 锁定时，应该降级到 secrets.toml"""
    import keyring.errors

    def mock_get_password(*args, **kwargs):
        raise keyring.errors.KeyringLocked("Keyring locked")

    monkeypatch.setattr("keyring.get_password", mock_get_password)

    # Mock secrets.toml
    def mock_read_toml(*args, **kwargs):
        return {"tushare": {"token": "test_token"}}

    monkeypatch.setattr("tomllib.loads", mock_read_toml)

    # 应该不抛出异常，而是返回 token
    token = _get_tushare_token()
    assert token == "test_token"


def test_http_timeout_propagates_as_fetch_error():
    """网络超时应该被转换为 SourceFetchError"""
    client = TushareClient(token="test_token")

    with mock.patch.object(client._client, 'post') as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Request timeout")

        with pytest.raises(SourceFetchError):
            client._query("daily", "ts_code,trade_date")


@pytest.mark.parametrize("exception_cls", [
    pl.ComputeError,
    pl.SchemaError,
    pl.ColumnNotFoundError,
])
def test_polars_errors_converted_to_dq_issue(exception_cls):
    """Polars 错误应该被转换为 DQIssue"""
    checker = StatisticalChecker()

    # Mock DataFrame that raises the exception
    with mock.patch.object(pl.DataFrame, 'with_columns') as mock_with_columns:
        mock_with_columns.side_effect = exception_cls("Test error")

    result = checker._check_zscore(
        current=pl.DataFrame({"a": [1, 2, 3]}),
        historical=pl.DataFrame({"a": [1, 2, 3]}),
        rule={"rule": "zscore", "column": "a", "threshold": 3.0},
    )

    assert result is not None
    assert result.severity == DQSeverity.ALERT
    assert "zscore" in result.message.lower()
```

### GREEN 阶段：最小实现

1. 修改异常捕获类型（如将 `except Exception` 改为 `except (TypeError, KeyError)`）
2. 添加必要的日志（使用结构化字段）
3. 运行测试验证通过

### REFACTOR 阶段：优化代码

1. 提取公共错误处理逻辑
2. 统一日志格式
3. 添加文档说明

---

## 实施计划

### 批次划分

| 批次 | 文件 | 依赖风险 | 可并行？ | 工作量 |
|------|------|----------|----------|--------|
| **Batch 1** | `statistical.py` | 被 `engine.py` 导入，但异常类型不改变接口 | ✅ 可独立 | 2-3h |
| **Batch 2** | `client.py` | 被 adapters 导入，但异常抛出行为不变 | ✅ 可独立 | 2-3h |
| **Batch 3** | `main.py`, `registry/notification.py`, `coordinator.py`, `l3_batch_service.py`, `dq_batch.py`, `manager.py` | 部分共享 `result_handler`，需注意顺序 | ⚠️ 部分可并行 | 3-4h |

### 实施顺序

```
Phase 1: Batch 1 (statistical.py)
    ↓
Phase 2: Batch 2 (client.py)
    ↓
Phase 3: Batch 3 (顶层处理，部分可并行)
    ↓
Phase 4: CI 验证 + 文档更新
```

---

## 风险和缓解措施

### 高风险变更

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 精确捕获遗漏异常类型 | 程序崩溃 | 1. 先写测试覆盖所有已知异常<br>2. 保留兜底 `except Exception` 作为最后一道防线<br>3. 添加 Sentry 告警监控新异常 |
| 异常传播链断裂 | 错误被吞掉 | 1. 测试验证异常确实被重新抛出<br>2. 使用 `pytest.raises()` 验证<br>3. Code Review 重点检查 |
| 日志格式不一致 | 难以诊断 | 1. 统一日志字段（error_type, error_msg）<br>2. 使用结构化日志<br>3. 添加日志格式测试 |

### 低风险变更

| 变更 | 风险等级 | 说明 |
|------|----------|------|
| 通知发送异常 | 低 | 已经有良好的降级逻辑，不修改核心行为 |
| 资源清理异常 | 低 | 程序退出时的清理，失败影响小 |

---

## 验收标准

### 代码质量

- [ ] pyright strict 模式通过
- [ ] ruff 检查无新增问题
- [ ] 测试覆盖率 >= 80%

### 功能验证

- [ ] 所有现有测试通过
- [ ] 新增异常处理测试通过
- [ ] 集成测试验证异常传播正确

### 日志规范

- [ ] 所有异常都有 `error_type` 字段
- [ ] 未知异常使用 `logger.exception()` 记录堆栈
- [ ] 日志级别使用正确（warning/error/exception）

---

## 相关文档

- [架构重构路线图](2026-01-22-architecture-refactor-roadmap.md)
- [Python 核心规范](../.claude/rules/core.md)
- [工作流规范](../.claude/rules/workflow.md)

---

**文档版本**: 1.0
**最后更新**: 2026-01-22
