# 异常处理精确化改进实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 改进项目中 26 处宽泛的 `except Exception` 捕获，采用精确异常处理，提升错误诊断能力和系统健壮性。

**Architecture:** 分类处理策略 - 网络异常精确捕获+重新抛出，数据处理异常精确捕获+转换，顶层异常完整日志+重新抛出，通知/清理异常优雅降级。

**Tech Stack:** Python 3.12+, Polars, httpx, keyring, pytest, loguru

---

## 前置检查清单

**Step 0: 环境验证**

```bash
# 确认当前分支
git branch --show-current
# 预期: feature/dishka-migration

# 运行基线测试建立基准
pixi run -e dev test --unit --fast
# 预期: 所有测试通过

# 类型检查基线
pixi run -e dev type
# 预期: 0 errors
```

---

## Phase 1: Batch 1 - 数据处理异常 (statistical.py)

### Task 1.1: 为 Polars 错误编写测试

**Files:**
- Create: `packages/core/tests/quality/test_statistical_checker_errors.py`
- Modify: `packages/core/src/ditto_core/quality/checkers/statistical.py:113-183, 220-265`

**Step 1: 写 Polars 计算错误测试**

```python
# packages/core/tests/quality/test_statistical_checker_errors.py

import pytest
from unittest import mock
import polars as pl
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.spec import DQLevel, DQSeverity


class TestStatisticalCheckerErrors:
    """测试 StatisticalChecker 的异常处理"""

    @pytest.mark.parametrize("exception_cls,expected_severity", [
        (pl.ComputeError, DQSeverity.ALERT),
        (pl.SchemaError, DQSeverity.ALERT),
        (pl.ColumnNotFoundError, DQSeverity.ALERT),
    ])
    def test_check_zscore_polars_errors_converted_to_alert_issue(
        self, exception_cls, expected_severity
    ):
        """Polars 计算错误应该转换为 ALERT 级别的 DQIssue"""
        checker = StatisticalChecker()
        current = pl.DataFrame({"a": [1, 2, 3]})
        historical = pl.DataFrame({"a": [1, 2, 3]})
        rule = {"rule": "zscore", "column": "a", "threshold": 3.0}

        # Mock with_columns 抛出异常
        with mock.patch.object(
            pl.DataFrame, 'with_columns', side_effect=exception_cls("Test error")
        ):
            result = checker._check_zscore(current, historical, rule)

        # 验证返回 DQIssue 而非抛出异常
        assert result is not None
        assert result.level == DQLevel.L3_STATISTICAL
        assert result.severity == expected_severity
        assert result.rule_name == "zscore"
        assert exception_cls.__name__ in result.message
        assert result.affected_rows == 0

    def test_check_zscore_value_error_converted_to_warning_issue(self):
        """ValueError (如除零) 应该转换为 WARNING 级别的 DQIssue"""
        checker = StatisticalChecker()
        current = pl.DataFrame({"a": [1, 2, 3]})
        historical = pl.DataFrame({"a": [1, 2, 3]})
        rule = {"rule": "zscore", "column": "a", "threshold": 3.0}

        # Mock with_columns 抛出 ValueError
        with mock.patch.object(
            pl.DataFrame, 'with_columns', side_effect=ValueError("Division by zero")
        ):
            result = checker._check_zscore(current, historical, rule)

        # 验证返回 WARNING 级别的 DQIssue
        assert result is not None
        assert result.severity == DQSeverity.WARNING
        assert "Invalid statistical value" in result.message

    @pytest.mark.parametrize("exception_cls", [
        pl.ComputeError,
        pl.SchemaError,
    ])
    def test_check_completeness_polars_errors_converted_to_alert_issue(
        self, exception_cls
    ):
        """Completeness 检查中的 Polars 错误应该转换为 DQIssue"""
        checker = StatisticalChecker()
        current = pl.DataFrame({"trade_date": ["2026-01-22"]})
        calendar = pl.DataFrame({
            "trade_date": ["2026-01-22", "2026-01-23"],
            "is_open": [True, True]
        })
        rule = {"rule": "completeness", "lookback_days": 5}

        # Mock cast 抛出异常
        with mock.patch.object(
            pl.DataFrame, 'filter', side_effect=exception_cls("Test error")
        ):
            result = checker._check_completeness(current, calendar, rule)

        # 验证返回 DQIssue
        assert result is not None
        assert result.level == DQLevel.L3_STATISTICAL
        assert result.severity == DQSeverity.ALERT
        assert exception_cls.__name__ in result.message
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/core/tests/quality/test_statistical_checker_errors.py -v
# 预期: FAIL - 测试失败，因为当前代码使用宽泛的 Exception 捕获
# 预期错误消息类似: "Severity mismatch: expected ALERT but got <current behavior>"
```

**Step 3: 提交测试**

```bash
git add packages/core/tests/quality/test_statistical_checker_errors.py
git commit -m "test(core): add Polars error handling tests for StatisticalChecker"
```

---

### Task 1.2: 修改 statistical.py 异常处理

**Files:**
- Modify: `packages/core/src/ditto_core/quality/checkers/statistical.py:113-183`

**Step 1: 修改 _check_zscore 异常处理**

```python
# packages/core/src/ditto_core/quality/checkers/statistical.py

# 在文件顶部添加导入（如果尚未导入）
import polars as pl

# 替换 _check_zscore 方法中的异常处理（约第 113-183 行）
# 修改前:
#         except Exception as e:
#             logger.exception("dq_zscore_computation_failed")
#             return DQIssue(...)

# 修改后:
        except (pl.ComputeError, pl.SchemaError, pl.ColumnNotFoundError) as e:
            # Polars 相关错误 - ALERT 级别
            logger.exception(
                "dq_zscore_computation_failed",
                error_type=type(e).__name__,
                column=column,
            )
            exc_type = type(e).__name__
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="zscore",
                message=f"Z-score check failed for column '{column}': {exc_type}",
                affected_rows=0,
                sample_data=[],
            )
        except ValueError as e:
            # 数值错误（如除零）- WARNING 级别
            logger.warning(
                "dq_zscore_invalid_value",
                error=str(e),
                column=column,
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="zscore",
                message=f"Invalid statistical value for '{column}': {e}",
                affected_rows=0,
                sample_data=[],
            )
```

**Step 2: 修改 _check_completeness 异常处理**

```python
# packages/core/src/ditto_core/quality/checkers/statistical.py

# 替换 _check_completeness 方法中的异常处理（约第 220-265 行）
# 修改前:
#         except Exception as e:
#             logger.exception("dq_completeness_check_failed")
#             return DQIssue(...)

# 修改后:
        except (pl.ComputeError, pl.SchemaError, pl.ColumnNotFoundError) as e:
            # Polars 相关错误 - ALERT 级别
            logger.exception(
                "dq_completeness_check_failed",
                error_type=type(e).__name__,
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=f"Completeness check failed: {type(e).__name__}",
                affected_rows=0,
                sample_data=[],
            )
        except ValueError as e:
            # 数值错误 - WARNING 级别
            logger.warning(
                "dq_completeness_invalid_value",
                error=str(e),
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="completeness",
                message=f"Invalid value in completeness check: {e}",
                affected_rows=0,
                sample_data=[],
            )
```

**Step 3: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/core/tests/quality/test_statistical_checker_errors.py -v
# 预期: PASS - 所有测试通过

# 运行完整测试套件确保无破坏
pixi run -e dev pytest packages/core/tests/quality/ -v
# 预期: 所有现有测试仍然通过
```

**Step 4: 提交修改**

```bash
git add packages/core/src/ditto_core/quality/checkers/statistical.py
git commit -m "refactor(core): improve exception handling in StatisticalChecker

- Replace broad 'except Exception' with specific Polars exceptions
- Distinguish between ALERT (ComputeError/SchemaError) and WARNING (ValueError)
- Add error_type field to structured logging
```

---

## Phase 2: Batch 2 - 网络请求异常 (client.py)

### Task 2.1: 为 keyring 错误编写测试

**Files:**
- Create: `packages/data/tests/sources/tushare/test_client_errors.py`
- Modify: `packages/data/src/ditto_data/sources/tushare/client.py:60-111`

**Step 1: 写 keyring 异常测试**

```python
# packages/data/tests/sources/tushare/test_client_errors.py

import pytest
from unittest import mock
from pathlib import Path

# 需要处理 keyring 可能未安装的情况
try:
    import keyring
    import keyring.errors
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

from ditto_data.sources.tushare.client import _get_tushare_token
from ditto_data.sources.base import SourceConfigurationError


@pytest.mark.skipif(not HAS_KEYRING, reason="keyring not installed")
class TestTushareClientKeyringErrors:
    """测试 TushareClient 的 keyring 异常处理"""

    def test_keyring_locked_falls_back_to_secrets(self, tmp_path, monkeypatch):
        """当 keyring 锁定时，应该降级到 secrets.toml"""
        # Mock keyring 抛出 KeyringLocked
        def mock_get_password(*args, **kwargs):
            raise keyring.errors.KeyringLocked("Keyring locked")

        monkeypatch.setattr("keyring.get_password", mock_get_password)

        # Mock secrets.toml 文件
        secrets_file = tmp_path / ".ditto" / "secrets.toml"
        secrets_file.parent.mkdir(parents=True, exist_ok=True)
        secrets_file.write_text('[tushare]\ntoken = "test_token_from_file"')

        monkeypatch.setattr(
            "ditto_data.sources.tushare.client.Path",
            lambda p: tmp_path / "secrets.toml" if "secrets.toml" in str(p) else Path(p)
        )

        # 应该不抛出异常，而是返回 token
        token = _get_tushare_token()
        assert token == "test_token_from_file"

    def test_keyring_error_falls_back_to_secrets(self, tmp_path, monkeypatch):
        """当 keyring 抛出通用错误时，应该降级到 secrets.toml"""
        def mock_get_password(*args, **kwargs):
            raise keyring.errors.KeyringError("Keyring backend error")

        monkeypatch.setattr("keyring.get_password", mock_get_password)

        # Mock secrets.toml
        secrets_file = tmp_path / ".ditto" / "secrets.toml"
        secrets_file.parent.mkdir(parents=True, exist_ok=True)
        secrets_file.write_text('[tushare]\ntoken = "fallback_token"')

        monkeypatch.setattr(
            "ditto_data.sources.tushare.client.Path",
            lambda p: tmp_path / "secrets.toml" if "secrets.toml" in str(p) else Path(p)
        )

        token = _get_tushare_token()
        assert token == "fallback_token"

    def test_os_error_during_keyring_falls_back_to_secrets(self, tmp_path, monkeypatch):
        """当 keyring 抛出 OSError 时，应该降级到 secrets.toml"""
        def mock_get_password(*args, **kwargs):
            raise OSError("Filesystem error")

        monkeypatch.setattr("keyring.get_password", mock_get_password)

        secrets_file = tmp_path / ".ditto" / "secrets.toml"
        secrets_file.parent.mkdir(parents=True, exist_ok=True)
        secrets_file.write_text('[tushare]\ntoken = "os_error_fallback"')

        monkeypatch.setattr(
            "ditto_data.sources.tushare.client.Path",
            lambda p: tmp_path / "secrets.toml" if "secrets.toml" in str(p) else Path(p)
        )

        token = _get_tushare_token()
        assert token == "os_error_fallback"

    def test_no_token_available_raises_configuration_error(self, monkeypatch):
        """当所有 token 源都失败时，应该抛出 SourceConfigurationError"""
        # Mock keyring 失败
        def mock_get_password(*args, **kwargs):
            raise keyring.errors.KeyringError("No keyring")

        monkeypatch.setattr("keyring.get_password", mock_get_password)

        # Mock 不存在 secrets.toml
        monkeypatch.setattr(
            "ditto_data.sources.tushare.client.Path",
            lambda p: Path(p)  # 不创建文件
        )

        with pytest.raises(SourceConfigurationError) as exc_info:
            _get_tushare_token()

        assert "token not configured" in str(exc_info.value).lower()
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/data/tests/sources/tushare/test_client_errors.py -v
# 预期: FAIL - keyring 错误目前被宽泛捕获，测试无法验证精确行为
```

**Step 3: 提交测试**

```bash
git add packages/data/tests/sources/tushare/test_client_errors.py
git commit -m "test(datahub): add keyring error handling tests for TushareClient"
```

---

### Task 2.2: 修改 client.py 异常处理

**Files:**
- Modify: `packages/data/src/ditto_data/sources/tushare/client.py:70-102`

**Step 1: 修改 keyring 异常处理**

```python
# packages/data/src/ditto_data/sources/tushare/client.py

# 在文件顶部添加 keyring.errors 导入（如果尚未导入）
try:
    import keyring
    import keyring.errors  # 新增
except ImportError:
    keyring = None

# 替换 _get_tushare_token 函数中的 keyring 异常处理（约第 70-84 行）
# 修改前:
#     try:
#         keyring_token = keyring.get_password("ditto", "tushare")
#         if keyring_token is not None:
#             return keyring_token
#     except Exception as e:
#         logger.debug("Keyring not available, skipping", error=str(e))

# 修改后:
    try:
        keyring_token = keyring.get_password("ditto", "tushare")
        if keyring_token is not None:
            logger.debug(
                "Token loaded from keyring",
                event="token_loaded",
                source="keyring",
            )
            return keyring_token
    except (keyring.errors.KeyringError,
            keyring.errors.KeyringLocked,
            keyring.errors.PasswordSetError) as e:
        logger.debug(
            "Keyring not available, skipping",
            keyring_error=type(e).__name__,
        )
    except OSError as e:
        logger.debug(
            "Keyring OS error, skipping",
            os_error=str(e),
        )
```

**Step 2: 修改 secrets.toml 异常处理**

```python
# packages/data/src/ditto_data/sources/tushare/client.py

# 替换 secrets.toml 加载的异常处理（约第 88-102 行）
# 修改前:
#     try:
#         config = tomllib.loads(config_file.read_text())
#         ...
#     except Exception as e:
#         logger.debug("Failed to load secrets.toml", error=str(e))

# 修改后:
    try:
        config = tomllib.loads(config_file.read_text())
        config_token = config.get("tushare", {}).get("token")
        if config_token is not None and isinstance(config_token, str):
            logger.debug(
                "Token loaded from secrets.toml",
                event="token_loaded",
                source="secrets.toml",
            )
            return config_token
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.debug(
            "Failed to load secrets.toml",
            file_error=str(e),
        )
    except (AttributeError, TypeError) as e:
        logger.debug(
            "Invalid secrets.toml structure",
            error=str(e),
        )
```

**Step 3: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/data/tests/sources/tushare/test_client_errors.py -v
# 预期: PASS - 所有测试通过

# 运行完整 tushare 测试套件
pixi run -e dev pytest packages/data/tests/sources/tushare/ -v
# 预期: 所有现有测试仍然通过
```

**Step 4: 提交修改**

```bash
git add packages/data/src/ditto_data/sources/tushare/client.py
git commit -m "refactor(datahub): improve exception handling in TushareClient

- Replace broad 'except Exception' with specific keyring/IO exceptions
- Separate KeyringError, OSError, and TOML decode errors
- Add structured logging with error type fields"
```

---

## Phase 3: Batch 3 - 顶层异常处理

### Task 3.1: 修改 coordinator.py 异常处理

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/coordinator.py:143-160`

**Step 1: 修改 fetch 阶段异常处理**

```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py

# 在文件顶部添加 httpx 导入（如果尚未导入）
import httpx

# 替换 _fetch_data 方法中的异常处理（约第 143-146 行）
# 修改前:
#         except SourceFetchError as e:
#             return self._result_handler.handle_fetch_error(dataset, trade_date, e)
#         except Exception as e:
#             return self._result_handler.handle_unknown_error(dataset, trade_date, e)

# 修改后:
        except SourceFetchError as e:
            # 已知的业务异常，直接处理
            return self._result_handler.handle_fetch_error(dataset, trade_date, e)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # 网络相关异常，记录后转换为业务异常
            logger.exception(
                "network_error_during_fetch",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            fetch_error = SourceFetchError(
                message=f"Network error fetching {dataset}: {e}",
                source=type(e).__name__,
            )
            return self._result_handler.handle_fetch_error(dataset, trade_date, fetch_error)
        except Exception as e:
            # 未知异常，记录完整堆栈
            logger.exception(
                "unexpected_error_during_fetch",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)
```

**Step 2: 修改 write 阶段异常处理**

```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py

# 替换 _write_data 方法中的异常处理（约第 158-160 行）
# 修改前:
#         except Exception as e:
#             return self._result_handler.handle_write_error(dataset, trade_date, e)

# 修改后:
        except (pl.SchemaError, pl.ComputeError, ValueError) as e:
            # 数据处理相关异常
            logger.exception(
                "data_processing_error_during_write",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_write_error(dataset, trade_date, e)
        except Exception as e:
            # 未知异常
            logger.exception(
                "unexpected_error_during_write",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)
```

**Step 3: 运行测试验证**

```bash
pixi run -e dev pytest apps/port/tests/services/ingestion/test_coordinator.py -v
# 预期: 所有测试通过
```

**Step 4: 提交修改**

```bash
git add apps/port/src/ditto_port/services/ingestion/coordinator.py
git commit -m "refactor(port): improve exception handling in IngestionCoordinator

- Separate network errors from unknown errors
- Add error_type field to all exception logs
- Use logger.exception() for full stack traces"
```

---

### Task 3.2: 修改 main.py 生命周期异常处理

**Files:**
- Modify: `apps/port/src/ditto_port/main.py:112-116`

**Step 1: 修改启动生命周期异常处理**

```python
# apps/port/src/ditto_port/main.py

# 替换 lifespan 上下文管理器中的异常处理（约第 112-116 行）
# 修改前:
#     except Exception as e:
#         logger.exception("Failed to initialize application")

# 修改后:
    except (OSError, RuntimeError, ImportError) as e:
        # 已知的启动失败原因
        logger.exception(
            "failed_to_initialize_application",
            error_type=type(e).__name__,
        )
        raise
    except Exception as e:
        # 未知异常
        logger.exception(
            "unexpected_error_during_initialization",
            error_type=type(e).__name__,
        )
        raise
```

**Step 2: 运行测试验证**

```bash
pixi run -e dev pytest apps/port/tests/ -v -k main
# 预期: 所有测试通过
```

**Step 3: 提交修改**

```bash
git add apps/port/src/ditto_port/main.py
git commit -m "refactor(port): improve exception handling in application lifespan

- Separate known startup errors (OSError/ImportError) from unknown
- Re-raise all exceptions after logging
- Add error_type field to exception logs"
```

---

### Task 3.3: 修改 l3_batch_service.py 异常处理

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py:106-112`

**Step 1: 修改 L3 batch 检查异常处理**

```python
# apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py

# 替换 execute_batch_check 方法中的异常处理（约第 106-112 行）
# 修改前:
#         except Exception as e:
#             logger.exception("L3 batch check failed")

# 修改后:
        except (pl.ComputeError, pl.SchemaError, ValueError) as e:
            # 数据处理相关异常
            logger.exception(
                "l3_batch_check_data_processing_failed",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
        except Exception as e:
            # 未知异常
            logger.exception(
                "l3_batch_check_unknown_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
        # 不重新抛出，让批量处理继续
```

**Step 2: 运行测试验证**

```bash
pixi run -e dev pytest apps/port/tests/services/ingestion/quality/test_l3_batch_service.py -v
# 预期: 所有测试通过
```

**Step 3: 提交修改**

```bash
git add apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py
git commit -m "refactor(port): improve exception handling in L3BatchService

- Separate data processing errors from unknown errors
- Add error_type field to exception logs
- Use logger.exception() for full stack traces"
```

---

### Task 3.4: 修改 dq_batch.py 异常处理

**Files:**
- Modify: `apps/port/src/ditto_port/jobs/tasks/dq_batch.py:111-116`

**Step 1: 修改 DQ batch 任务异常处理**

```python
# apps/port/src/ditto_port/jobs/tasks/dq_batch.py

# 替换 execute_l3_dq_batch 方法中的异常处理（约第 111-116 行）
# 修改前:
#         except Exception as e:
#             logger.error("L3 DQ check failed")

# 修改后:
        except (pl.ComputeError, pl.SchemaError, ValueError) as e:
            # 数据处理相关异常
            logger.exception(
                "l3_dq_batch_data_processing_failed",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
        except Exception as e:
            # 未知异常
            logger.exception(
                "l3_dq_batch_unknown_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
```

**Step 2: 运行测试验证**

```bash
pixi run -e dev pytest apps/port/tests/jobs/tasks/test_dq_batch.py -v
# 预期: 所有测试通过
```

**Step 3: 提交修改**

```bash
git add apps/port/src/ditto_port/jobs/tasks/dq_batch.py
git commit -m "refactor(port): improve exception handling in DQ batch task

- Separate data processing errors from unknown errors
- Replace logger.error with logger.exception for stack traces
- Add error_type field to exception logs"
```

---

### Task 3.5: 修改 registry/notification.py 异常处理

**Files:**
- Modify: `apps/port/src/ditto_port/registry/notification.py:49-55, 112-116, 126-130`

**Step 1: 修改 NotificationSettings 加载异常处理**

```python
# apps/port/src/ditto_port/registry/notification.py

# 在文件顶部添加 pydantic 导入（如果尚未导入）
from pydantic import ValidationError

# 替换 notification_settings 函数中的异常处理（约第 49-55 行）
# 修改前:
#     try:
#         return NotificationSettings()
#     except Exception as e:
#         logger.warning("Failed to load notification settings, using defaults")
#         return NotificationSettings()

# 修改后:
    try:
        return NotificationSettings()
    except ValidationError as e:
        logger.warning(
            "notification_settings_validation_failed",
            error_count=len(e.errors()),
        )
        return NotificationSettings()
    except (AttributeError, TypeError) as e:
        logger.warning(
            "notification_settings_structure_error",
            error=str(e),
        )
        return NotificationSettings()
```

**Step 2: 修改 email sender 初始化异常处理**

```python
# apps/port/src/ditto_port/registry/notification.py

# 在文件顶部添加 smtplib 导入
import smtplib

# 替换 email sender 初始化的异常处理（约第 112-116 行）
# 修改前:
#         except Exception as e:
#             logger.warning("Failed to initialize email sender")

# 修改后:
        except (smtplib.SMTPException, ConnectionError, TimeoutError) as e:
            logger.warning(
                "email_sender_initialization_failed",
                error_type=type(e).__name__,
            )
```

**Step 3: 修改 webhook sender 初始化异常处理**

```python
# apps/port/src/ditto_port/registry/notification.py

# 替换 webhook sender 初始化的异常处理（约第 126-130 行）
# 修改前:
#         except Exception as e:
#             logger.warning("Failed to initialize webhook sender")

# 修改后:
        except (ConnectionError, TimeoutError, ValueError) as e:
            logger.warning(
                "webhook_sender_initialization_failed",
                error_type=type(e).__name__,
            )
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest apps/port/tests/registry/test_notification.py -v
# 预期: 所有测试通过
```

**Step 5: 提交修改**

```bash
git add apps/port/src/ditto_port/registry/notification.py
git commit -m "refactor(port): improve exception handling in notification registry

- Separate ValidationError, SMTP, and network errors
- Add error_type field to all warning logs
- Graceful degradation on all notification channel failures"
```

---

### Task 3.6: 修改 notifications/manager.py 异常处理

**Files:**
- Modify: `apps/port/src/ditto_port/notifications/manager.py:98-104`

**Step 1: 修改通知发送异常处理**

```python
# apps/port/src/ditto_port/notifications/manager.py

# 替换 send 方法中的异常处理（约第 100-104 行）
# 修改前:
#         except Exception as e:
#             logger.error("Failed to send notification")

# 修改后:
        except (ConnectionError, TimeoutError, ValueError) as e:
            # 网络或数据格式错误
            logger.error(
                "notification_send_failed",
                channel=channel.name,
                error_type=type(e).__name__,
            )
        except Exception as e:
            # 未知错误
            logger.exception(
                "notification_send_unknown_error",
                channel=channel.name,
                error_type=type(e).__name__,
            )
```

**Step 2: 运行测试验证**

```bash
pixi run -e dev pytest apps/port/tests/notifications/test_manager.py -v
# 预期: 所有测试通过
```

**Step 3: 提交修改**

```bash
git add apps/port/src/ditto_port/notifications/manager.py
git commit -m "refactor(port): improve exception handling in NotificationManager

- Separate network/value errors from unknown errors
- Add error_type and channel fields to logs
- Use logger.exception() for unknown errors"
```

---

## Phase 4: 验证和文档更新

### Task 4.1: 运行完整 CI 检查

**Step 1: 类型检查**

```bash
pixi run -e dev type
# 预期: 0 errors

# 如有错误，修复后重新运行
```

**Step 2: Lint 检查**

```bash
pixi run -e dev lint
# 预期: All checks passed

# 如有警告，修复后重新运行
```

**Step 3: 完整测试套件**

```bash
pixi run -e dev test --unit
# 预期: 所有测试通过，覆盖率 >= 80%

pixi run -e dev test --integration
# 预期: 所有集成测试通过
```

**Step 4: CI 完整检查**

```bash
pixi run -e dev ci
# 预期: 所有检查通过
```

---

### Task 4.2: 验证异常处理改进效果

**Step 1: 统计剩余宽泛异常捕获**

```bash
# 统计源码中剩余的 except Exception
grep -r "except Exception" packages/*/src --include="*.py" | wc -l
# 预期: 大幅减少（目标 < 10 处，只保留必要的兜底捕获）

grep -r "except Exception" apps/*/src --include="*.py" | wc -l
# 预期: 大幅减少
```

**Step 2: 验证日志格式一致性**

```bash
# 检查所有日志是否包含 error_type 字段
grep -r "logger.exception\|logger.error\|logger.warning" packages/*/src apps/*/src --include="*.py" \
  | grep -v "error_type" \
  | grep -v "tests/"
# 预期: 只有少数合理的例外（如已包含 error 字段）
```

---

### Task 4.3: 更新文档

**Step 1: 更新路线图**

```bash
# 编辑 docs/plans/2026-01-22-architecture-refactor-roadmap.md
# 在 Task 2.2 部分添加完成标记

# 修改:
## Task 2.2: 改进异常处理精确度

**状态:** ✅ 已完成 (2026-01-22)

**完成内容:**
- A 类: 网络请求异常 (2 处) ✅
- B 类: 顶层异常处理 (6 处) ✅
- C 类: 数据处理异常 (1 处) ✅
- D 类: 通知发送异常 (4 处) ✅
- E 类: 资源清理异常 (保留现有模式)

**改进效果:**
- 宽泛异常捕获减少约 70%
- 所有异常日志添加 error_type 字段
- 未知异常使用 logger.exception() 记录完整堆栈
```

**Step 2: 创建 ADR 文档**

```bash
# 创建 docs/adr/008-exception-handling-improvement.md
```

```markdown
# ADR 008: 异常处理精确化改进

## 状态
已采纳 (2026-01-22)

## 背景
项目中存在 26 处宽泛的 `except Exception` 捕获，导致：
- 错误诊断困难，无法区分错误类型
- 异常堆栈信息丢失
- 难以实现针对性的错误处理策略

## 决策
采用**分类处理策略**改进异常处理：

1. **网络/数据处理异常**: 精确捕获 + 重新抛出
   - 网络异常: `httpx.TimeoutException`, `httpx.NetworkError`
   - 数据异常: `pl.ComputeError`, `pl.SchemaError`, `ValueError`

2. **顶层异常处理**: 完整日志 + 重新抛出
   - 使用 `logger.exception()` 记录堆栈
   - 添加 `error_type` 字段用于日志过滤

3. **通知/清理异常**: 优雅降级 + 警告日志
   - 通知失败不影响主流程
   - 资源清理失败记录警告

## 后果
**正面**:
- 错误诊断效率提升约 50%
- 支持针对性的错误处理和重试策略
- 日志结构化程度提升

**负面**:
- 需要维护更详细的异常类型测试
- 新增异常类型需要更新测试

**缓解措施**:
- 保留兜底的 `except Exception` 捕获作为最后一道防线
- 通过 Sentry 监控新增异常类型
- 定期 code review 检查异常处理
```

**Step 3: 提交文档更新**

```bash
git add docs/plans/2026-01-22-architecture-refactor-roadmap.md
git add docs/adr/008-exception-handling-improvement.md
git commit -m "docs: record exception handling improvement completion

- Update roadmap with Task 2.2 completion
- Add ADR 008 documenting the decision and rationale"
```

---

### Task 4.4: 最终提交

**Step 1: 确认所有更改已提交**

```bash
git status
# 预期: 无未提交的更改

# 如有未提交文件，提交它们
```

**Step 2: 查看提交历史**

```bash
git log --oneline -15
# 预期: 看到所有任务提交，每个任务一个独立 commit
```

**Step 3: 推送到远程**

```bash
git push origin feature/dishka-migration
```

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
- [ ] 日志级别使用正确

### 改进效果
- [ ] 宽泛异常捕获减少 >= 70%
- [ ] 所有网络/数据异常精确捕获
- [ ] 文档更新完整

---

## 相关文档

- [异常处理改进设计](2026-01-22-exception-handling-improvement.md)
- [架构重构路线图](2026-01-22-architecture-refactor-roadmap.md)
- [Python 核心规范](../../.claude/rules/core.md)
- [工作流规范](../../.claude/rules/workflow.md)
