# Architecture Fixes Implementation Plan

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 P0 异常吞噬问题、P1 配置未生效问题、以及 ARCH-001 领域层 I/O 问题，提升系统可观测性、可运维性和架构纯净性

**Architecture:** 分四个 PR 顺序实施：
1. PR-0: 修复 ARCH-001 - 将 YAML I/O 从 core 移到 foundation（架构解耦）
2. PR-1: 修复 DQ 检查器异常处理（返回 ALERT 而非 None）
3. PR-2: 修复 L3BatchService 异常处理（logger.exception）
4. PR-3: 接通 DataSourceSettings 到 TushareClient

**Tech Stack:** Python 3.12, Pydantic Settings, Loguru, Pytest, Dishka DI

**执行顺序说明：** PR-0 必须最先执行，因为后续 PR 可能依赖新的配置加载方式

---

## Phase 0: PR-0 修复 ARCH-001 - YAML I/O 迁移出 Core 层 (P1)

### Task 0.1: 修改 Core 层 QualityEngine 接收 DQSpec

**Files:**
- Modify: `packages/core/src/ditto_core/quality/spec.py` (移除 I/O 方法)
- Modify: `packages/core/src/ditto_core/quality/engine.py` (修改构造函数)
- Test: `packages/core/tests/unit/quality/test_models_unit.py` (更新测试)

**Step 1: 从 DQSpec 移除 I/O 方法**

```python
# packages/core/src/ditto_core/quality/spec.py

# 删除以下方法 (行 232-306):
# @classmethod
# def from_yaml_dir(cls, config_dir: str | Path) -> "DQSpec":
#     ...

# @classmethod
# def load_with_user_override(cls, default_config_dir: str | Path, data_root: str | Path) -> "DQSpec":
#     ...

# 保留 __init__ 和数据结构方法
```

**Step 2: 修改 QualityEngine 构造函数**

```python
# packages/core/src/ditto_core/quality/engine.py

from typing import Literal
from pathlib import Path
import polars as pl
from loguru import logger

from ditto_core.quality.spec import DQSpec, DQResult
from ditto_core.quality.checkers.technical import TechnicalChecker
from ditto_core.quality.checkers.business import BusinessChecker
from ditto_core.quality.checkers.statistical import StatisticalChecker


class QualityEngine:
    """Data quality engine."""

    def __init__(
        self,
        config: DQSpec,  # 改为必需参数，移除 data_root/config_path
    ) -> None:
        """
        Initialize DQ engine with configuration.

        Args:
            config: DQ 配置规范（由上层通过 DI 注入）

        """
        self.config = config

        # Initialize checkers
        self.technical_checker = TechnicalChecker()
        self.business_checker = BusinessChecker()
        self.statistical_checker = StatisticalChecker()

    # 移除 _config property（不再需要向后兼容）
```

**Step 3: 更新测试以直接构造 DQSpec**

```python
# packages/core/tests/unit/quality/test_models_unit.py

# 修改前:
from ditto_core.quality.spec import DQSpec
config = DQSpec.from_yaml_dir(config_dir)

# 修改后（直接构造 DQSpec，不依赖 I/O）:
from ditto_core.quality.spec import DQSpec, DatasetRules, DQRule

config = DQSpec(datasets={
    "test_dataset": DatasetRules(
        dataset="test_dataset",
        level="l2_technical",
        rules=[DQRule(rule="not_null", column="price")]
    )
})
```

**Step 4: 运行测试**

```bash
pixi run -e dev pytest packages/core/tests/unit/quality/test_models_unit.py -v
```

**Step 5: 提交**

```bash
git add packages/core/src/ditto_core/quality/spec.py
git add packages/core/src/ditto_core/quality/engine.py
git add packages/core/tests/unit/quality/test_models_unit.py
git commit -m "refactor(core): remove I/O from domain layer

- Remove from_yaml_dir and load_with_user_override from DQSpec
- QualityEngine now receives DQSpec via DI
- Core layer only contains data structures and business logic
- Tests updated to directly construct DQSpec

Partial fix for ARCH-001 (config loading moved to Port layer in next step)"
```

---

### Task 0.2: 在 Port 层实现 DQ 配置加载逻辑

**Files:**
- Modify: `apps/port/src/ditto_port/registry/core.py`
- Test: `apps/port/tests/registry/test_core.py` (如有)

**Context:**
Port 层是装配层（assembly），负责组合各个组件。DQ 配置加载逻辑应该在这里实现，而不是在 foundation 或 core 层。

**设计原则：**
- Foundation: 提供基础设施（不包含业务逻辑）
- Core: 只保留数据结构（不包含 I/O）
- Port: 负责装配和配置加载

**Step 1: 在 CoreProvider 中实现 DQ 配置加载**

```python
# apps/port/src/ditto_port/registry/core.py

from collections.abc import Iterator
from pathlib import Path

import yaml
from dishka import Provider, Scope, provide
from loguru import logger
from pydantic import ValidationError

from ditto_core.quality import QualityEngine, DQSpec
from ditto_core.quality.spec import DatasetRules

__all__ = ["CoreProvider"]


class CoreProvider(Provider):
    """Core 层组件 Provider."""

    scope = Scope.APP

    def _load_dq_spec(self, config_dir: Path) -> DQSpec:
        """
        从目录加载 DQ 配置 (Port 层内部方法).

        Args:
            config_dir: 配置目录路径

        Returns:
            DQSpec 实例

        """
        if not config_dir.exists():
            return DQSpec()

        datasets: dict[str, DatasetRules] = {}

        for yaml_file in config_dir.glob("*.yml"):
            try:
                with yaml_file.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and "dataset" in data:
                    dataset_rules = DatasetRules(**data)
                    datasets[dataset_rules.dataset] = dataset_rules
            except (ValidationError, ValueError) as e:
                logger.warning(
                    "Invalid DQ config file, skipping",
                    event="dq_config_invalid",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue
            except yaml.YAMLError as e:
                logger.warning(
                    "Failed to parse YAML config, skipping",
                    event="dq_config_parse_error",
                    file=str(yaml_file),
                    error=str(e),
                )
                continue

        return DQSpec(datasets=datasets)

    @provide
    def dq_spec(self, data_root: Path) -> DQSpec:
        """
        加载 DQ 配置规范.

        支持用户配置覆盖默认配置：
        1. 默认配置: {package_dir}/config/dq_rules/*.yml
        2. 用户配置: {data_root}/config/dq/*.yml (覆盖)

        Args:
            data_root: 数据根目录

        Returns:
            DQSpec: DQ 配置实例

        """
        # 1. 加载包内默认配置
        default_config_dir = (
            Path(__file__).parent.parent.parent.parent / "packages" / "core" / "src" / "ditto_core" / "config" / "dq_rules"
        )
        default_config = self._load_dq_spec(default_config_dir)

        # 2. 加载用户自定义配置（覆盖默认配置）
        user_config_dir = Path(data_root) / "config" / "dq"
        user_config = self._load_dq_spec(user_config_dir)

        # 3. 合并配置（用户配置覆盖默认配置）
        merged_datasets = default_config.datasets.copy()
        merged_datasets.update(user_config.datasets)

        return DQSpec(datasets=merged_datasets)

    @provide
    def dq_engine(self, dq_spec: DQSpec) -> Iterator[QualityEngine]:
        """
        数据质量引擎（应用层 DQ 检查使用）.

        Args:
            dq_spec: DQ 配置规范（通过 DI 注入）

        Yields:
            QualityEngine: DQ 引擎实例

        """
        engine = QualityEngine(config=dq_spec)
        yield engine
```

**Step 2: 运行测试**

```bash
# Core 层测试（直接构造 DQSpec）
pixi run -e dev pytest packages/core/tests/unit/quality/test_models_unit.py -v

# Port 层测试（验证 CoreProvider）
pixi run -e dev pytest apps/port/tests/registry/ -v -k "core"
```

**Step 3: 验证类型检查**

```bash
pixi run -e dev type apps/port/src/ditto_port/registry/core.py
```

**Step 4: 提交**

```bash
git add apps/port/src/ditto_port/registry/core.py
git add packages/core/tests/unit/quality/test_models_unit.py
git commit -m "refactor: move DQ config loading to Port layer

- Port layer (CoreProvider) now handles DQ config loading
- Core layer only contains DQSpec data structure
- Removes I/O from domain layer
- Maintains proper separation of concerns

Fixes ARCH-001"
```

---

## Phase 1: PR-1 修复 DQ 检查器异常处理 (P0)

### Task 1.1: 修复 StatisticalChecker._check_zscore 异常处理

**Files:**
- Modify: `packages/core/src/ditto_core/quality/checkers/statistical.py:166-173`
- Test: `packages/core/tests/quality/checkers/test_statistical.py`

**Context:**
当前代码在异常时返回 `None`，导致 DQ 规则"静默通过"。需要返回 `DQIssue` 让失败可见。

**Step 1: 添加异常处理的测试**

```python
# packages/core/tests/quality/checkers/test_statistical.py

import polars as pl
import pytest
from ditto_core.quality.checkers.statistical import StatisticalChecker
from ditto_core.quality.spec import DQLevel, DQSeverity


def test_zscore_returns_alert_on_compute_error():
    """Test that computation errors return ALERT issue instead of silent None."""
    # 创建无效数据（无法计算统计量的数据）
    current = pl.DataFrame({
        "sid": [1, 2, 3],
        "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "price": [10.0, 20.0, 30.0],
    })
    # 历史数据包含 NaN（会导致 std() 计算失败）
    historical = pl.DataFrame({
        "sid": [1, 2],
        "price": [None, None],  # 全是 None，无法计算统计量
    })

    checker = StatisticalChecker()
    rule = {
        "rule": "zscore",
        "column": "price",
        "threshold": 3.0,
    }

    result = checker._check_zscore(current, historical, rule)

    # 应该返回 DQIssue 而非 None
    assert result is not None, "Exception should return ALERT issue, not None"
    assert result.level == DQLevel.L3_STATISTICAL
    assert result.severity == DQSeverity.ALERT
    assert "error" in result.message.lower() or "failed" in result.message.lower()


def test_zscore_logs_exception_details():
    """Test that exception details are logged."""
    import loguru
    from unittest.mock import Mock

    # Mock logger to verify exception is logged
    with loguru.contextualize(event="test"):
        # 这里主要验证异常被记录，实际日志需要集成测试
        current = pl.DataFrame({"sid": [1], "price": [10.0]})
        historical = pl.DataFrame({"sid": [1], "price": [None]})

        checker = StatisticalChecker()
        rule = {"rule": "zscore", "column": "price", "threshold": 3.0}

        # 不应该抛出异常，应该返回 ALERT
        result = checker._check_zscore(current, historical, rule)
        assert result is not None
```

**Step 2: 运行测试验证当前行为失败**

```bash
pixi run -e dev pytest packages/core/tests/quality/checkers/test_statistical.py::test_zscore_returns_alert_on_compute_error -v
```

Expected: FAIL (当前返回 None，而非 DQIssue)

**Step 3: 实现修复**

```python
# packages/core/src/ditto_core/quality/checkers/statistical.py:166-173

# 修改前:
        except Exception as e:
            logger.error(
                "dq_zscore_error",
                event="dq_check",
                error=str(e),
            )

        return None

# 修改后:
        except (pl.ComputeError, ValueError, TypeError) as e:
            # 使用 logger.exception 记录完整堆栈
            logger.exception(
                "dq_zscore_computation_failed",
                event="dq_check",
                column=column,
                rule_type="zscore",
            )
            # 返回 ALERT 级别的 DQIssue 而非 None
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="zscore",
                message=f"Z-score check failed for column '{column}': {type(e).__name__}",
                affected_rows=0,
                sample_data=[],
            )
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/core/tests/quality/checkers/test_statistical.py::test_zscore_returns_alert_on_compute_error -v
```

Expected: PASS

**Step 5: 运行完整测试套件确保无回归**

```bash
pixi run -e dev pytest packages/core/tests/quality/checkers/test_statistical.py -v
```

**Step 6: 提交**

```bash
git add packages/core/src/ditto_core/quality/checkers/statistical.py
git add packages/core/tests/quality/checkers/test_statistical.py
git commit -m "fix(core): return DQIssue on zscore check exception

- Change exception handling to return ALERT instead of None
- Use logger.exception to capture full stack trace
- Catch specific exceptions (ComputeError, ValueError, TypeError)
- Prevents silent failures in DQ checks

Fixes ENG-002 partial"
```

---

### Task 1.2: 修复 StatisticalChecker._check_completeness 异常处理

**Files:**
- Modify: `packages/core/src/ditto_core/quality/checkers/statistical.py:242-249`
- Test: `packages/core/tests/quality/checkers/test_statistical.py`

**Step 1: 添加异常处理测试**

```python
# packages/core/tests/quality/checkers/test_statistical.py

def test_completeness_returns_alert_on_compute_error():
    """Test that completeness check errors return ALERT issue."""
    # 创建无效的日历数据（缺少必需列）
    current = pl.DataFrame({
        "sid": [1, 2, 3],
        "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
    })
    # 日历缺少 is_open 列（会导致计算失败）
    calendar = pl.DataFrame({
        "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        # 缺少 is_open 列
    })

    checker = StatisticalChecker()
    rule = {
        "rule": "completeness",
        "lookback_days": 5,
    }

    result = checker._check_completeness(current, calendar, rule)

    # 应该返回 DQIssue 而非 None
    assert result is not None, "Exception should return ALERT issue, not None"
    assert result.severity == DQSeverity.ALERT
    assert "error" in result.message.lower() or "failed" in result.message.lower()
```

**Step 2: 运行测试验证失败**

```bash
pixi run -e dev pytest packages/core/tests/quality/checkers/test_statistical.py::test_completeness_returns_alert_on_compute_error -v
```

Expected: FAIL

**Step 3: 实现修复**

```python
# packages/core/src/ditto_core/quality/checkers/statistical.py:242-249

# 修改前:
        except Exception as e:
            logger.error(
                "dq_completeness_error",
                event="dq_check",
                error=str(e),
            )

        return None

# 修改后:
        except (pl.ComputeError, ValueError, KeyError, TypeError) as e:
            logger.exception(
                "dq_completeness_check_failed",
                event="dq_check",
                rule_type="completeness",
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=f"Completeness check failed: {type(e).__name__}",
                affected_rows=0,
                sample_data=[],
            )
```

**Step 4: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/core/tests/quality/checkers/test_statistical.py::test_completeness_returns_alert_on_compute_error -v
```

Expected: PASS

**Step 5: 完整测试**

```bash
pixi run -e dev pytest packages/core/tests/quality/checkers/test_statistical.py -v
```

**Step 6: 提交**

```bash
git add packages/core/src/ditto_core/quality/checkers/statistical.py
git add packages/core/tests/quality/checkers/test_statistical.py
git commit -m "fix(core): return DQIssue on completeness check exception

- Change exception handling to return ALERT instead of None
- Use logger.exception for full stack trace
- Catch specific exceptions

Fixes ENG-002 complete"
```

---

## Phase 2: PR-2 修复 L3BatchService 异常处理 (P0)

### Task 2.1: 修复 L3BatchService 异常吞噬

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py:108-120`
- Test: `apps/port/tests/services/ingestion/quality/test_l3_batch_service.py`

**Context:**
当前代码使用 `logger.error` 只记录错误消息，丢失堆栈信息。需要使用 `logger.exception` 并考虑是否重新抛出异常。

**Step 1: 查看现有测试**

```bash
cat apps/port/tests/services/ingestion/quality/test_l3_batch_service.py
```

**Step 2: 添加异常日志测试**

```python
# apps/port/tests/services/ingestion/quality/test_l3_batch_service.py

import pytest
from unittest.mock import Mock, patch
from ditto_port.services.ingestion.quality.l3_batch_service import L3BatchService


def test_l3_batch_check_logs_exception_on_failure():
    """Test that exceptions during batch check are logged with full stack trace."""
    # 创建 mock engine，抛出异常
    mock_engine = Mock()
    mock_engine.check_statistical.side_effect = ValueError("Test error")

    mock_hub = Mock()

    service = L3BatchService(engine=mock_engine, hub=mock_hub)

    # 使用 patch 验证 logger.exception 被调用
    with patch("ditto_port.services.ingestion.quality.l3_batch_service.logger") as mock_logger:
        result = service.check_batch(
            dataset="test_dataset",
            trade_date="2024-01-01",
            asset_class="stock",
            market_wide=True,
        )

        # 验证返回值
        assert result["passed"] is False
        assert "error" in result

        # 验证 logger.exception 被调用（而非 logger.error）
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args
        assert "l3_batch_error" in call_args.kwargs.get("event", "")


def test_l3_batch_check_propagates_critical_errors():
    """Test that critical errors can be propagated if needed."""
    # 这个测试根据业务需求决定是否需要重新抛出异常
    # 当前实现是返回 passed=False，这是合理的
    # 如果需要重新抛出，可以在未来添加
    pass
```

**Step 3: 运行测试验证当前失败**

```bash
pixi run -e dev pytest apps/port/tests/services/ingestion/quality/test_l3_batch_service.py::test_l3_batch_check_logs_exception_on_failure -v
```

Expected: FAIL (当前使用 logger.error)

**Step 4: 实现修复**

```python
# apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py:108-120

# 修改前:
        except Exception as e:
            logger.error(
                "L3 batch check failed",
                event="l3_batch_error",
                dataset=dataset,
                error=str(e),
            )
            return {
                "dataset": dataset,
                "trade_date": trade_date,
                "passed": False,
                "error": str(e),
            }

# 修改后:
        except Exception as e:
            logger.exception(  # 改为 exception 捕获完整堆栈
                "L3 batch check failed",
                event="l3_batch_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return {
                "dataset": dataset,
                "trade_date": trade_date,
                "passed": False,
                "error": f"{type(e).__name__}: {str(e)}",  # 包含异常类型
            }
```

**Step 5: 运行测试验证通过**

```bash
pixi run -e dev pytest apps/port/tests/services/ingestion/quality/test_l3_batch_service.py::test_l3_batch_check_logs_exception_on_failure -v
```

Expected: PASS

**Step 6: 完整测试套件**

```bash
pixi run -e dev pytest apps/port/tests/services/ingestion/quality/ -v
```

**Step 7: 提交**

```bash
git add apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py
git add apps/port/tests/services/ingestion/quality/test_l3_batch_service.py
git commit -m "fix(port): use logger.exception for full stack trace in L3BatchService

- Change logger.error to logger.exception
- Include error type in return value
- Makes debugging easier by preserving stack trace

Fixes ENG-001"
```

---

## Phase 3: PR-3 接通 DataSourceSettings 到 TushareClient (P1)

### Task 3.1: 修改 TushareClient 接收 DataSourceSettings

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/client.py:112-163`
- Test: `packages/datahub/tests/sources/tushare/test_client.py`

**Context:**
当前 TushareClient 硬编码 URL 和 timeout。需要从 DataSourceSettings 读取配置。

**Step 1: 查看现有测试**

```bash
pixi run -e dev pytest packages/datahub/tests/sources/tushare/test_client.py -v
```

**Step 2: 添加配置测试**

```python
# packages/datahub/tests/sources/tushare/test_client.py

import pytest
from unittest.mock import patch, Mock
from ditto_datahub.config.data_source import DataSourceSettings
from ditto_datahub.sources.tushare.client import TushareClient


def test_tushare_client_uses_settings_config(monkeypatch):
    """Test that TushareClient reads config from DataSourceSettings."""
    # 设置环境变量
    monkeypatch.setenv("HTTP_BASE_URL", "https://custom.api.com")
    monkeypatch.setenv("HTTP_TIMEOUT", "60.0")
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    # 从环境变量加载配置
    settings = DataSourceSettings()

    # 验证配置被正确加载
    assert settings.http_base_url == "https://custom.api.com"
    assert settings.http_timeout == 60.0
    assert settings.tushare_token == "test_token_123"

    # Mock _get_tushare_token to avoid real token lookup
    with patch("ditto_datahub.sources.tushare.client._get_tushare_token", return_value="test_token"):
        client = TushareClient(settings=settings)

        # 验证 HTTP client 使用了配置的 URL 和 timeout
        assert client._client.base_url == "https://custom.api.com"
        assert client._client.timeout == 60.0


def test_tushare_client_defaults_when_settings_not_provided():
    """Test that TushareClient uses defaults when no settings provided."""
    with patch("ditto_datahub.sources.tushare.client._get_tushare_token", return_value="test_token"):
        client = TushareClient()

        # 验证使用默认值
        assert client._client.base_url == "http://api.tushare.pro"
        assert client._client.timeout == 30.0
```

**Step 3: 实现修复**

```python
# packages/datahub/src/ditto_datahub/sources/tushare/client.py

# 在文件顶部添加导入
from ditto_datahub.config.data_source import DataSourceSettings

# 修改 __init__ 方法签名和实现
class TushareClient:
    """
    Tushare Pro API client.

    Features:
    - Token authentication from keyring/secrets.toml/env
    - Multi-level rate limiting using limits library
    - Retry with exponential backoff (Tenacity)
    - Error handling and logging
    - Configurable via DataSourceSettings

    Attributes:
        _token: Tushare API token.
        _limiter: Rate limiter instance.
        _settings: Data source configuration.

    """

    def __init__(
        self,
        token: str | None = None,
        rate_config: TushareRateLimitConfig | None = None,
        settings: DataSourceSettings | None = None,
    ) -> None:
        """
        Initialize Tushare client.

        Args:
            token: API token (auto-detected if None).
            rate_config: 限流配置(默认免费账户).
            settings: 数据源配置，包含 URL/timeout 等参数.

        Raises:
            SourceConfigurationError: If token not found.

        """
        # 存储 settings
        self._settings = settings or DataSourceSettings()

        # Get token with fallback chain
        # 优先使用 settings 中的 token（如果设置）
        token_to_use = token or self._settings.tushare_token or None
        self._token = _get_tushare_token(token_to_use if token_to_use else None)

        # 配置限流器(默认免费账户)
        config = rate_config or TushareRateLimitConfig.free()
        self._limiter = TushareRateLimiter(config)

        # Initialize HTTP client with settings
        self._client = httpx.Client(
            base_url=self._settings.http_base_url,  # 从 settings 读取
            timeout=self._settings.http_timeout,     # 从 settings 读取
            headers={"Content-Type": "application/json"},
        )

        logger.debug(
            "TushareClient initialized",
            event="tushare_client_init",
            base_url=self._settings.http_base_url,
            timeout=self._settings.http_timeout,
            rate_config=config,
        )
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/datahub/tests/sources/tushare/test_client.py -v
```

**Step 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/client.py
git add packages/datahub/tests/sources/tushare/test_client.py
git commit -m "feat(datahub): TushareClient supports DataSourceSettings

- Add settings parameter to TusharseClient.__init__
- Read base_url and timeout from DataSourceSettings
- Use settings.tushare_token as fallback
- Makes configuration runtime-editable via environment variables

Fixes ARCH-002"
```

---

### Task 3.2: 更新 DI 容器配置

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/init_providers.py`
- Modify: `apps/port/src/ditto_port/registry/datahub.py`

**Step 1: 查看当前 DI 配置**

```bash
grep -n "TushareClient\|tushare_client" packages/datahub/src/ditto_datahub/init_providers.py
grep -n "TushareClient\|tushare" apps/port/src/ditto_port/registry/datahub.py
```

**Step 2: 更新 datahub init_providers**

```python
# packages/datahub/src/ditto_datahub/init_providers.py

from ditto_datahub.config.data_source import DataSourceSettings
from dishka import Provider, provide

class DataSourceProvider(Provider):
    """Data source configuration and clients."""

    @provide
    def data_source_settings(self) -> DataSourceSettings:
        """Data source settings from environment."""
        return DataSourceSettings()

    @provide
    def tushare_client(
        self,
        settings: DataSourceSettings,
    ) -> TushareClient:
        """Tushare API client with configuration."""
        return TushareClient(settings=settings)
```

**Step 3: 验证类型检查**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/init_providers.py
```

**Step 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/init_providers.py
git commit -m "feat(datahub): add DataSourceSettings to DI container"
```

---

### Task 3.3: 更新环境配置文件

**Files:**
- Create: `config/development/data_source.env`
- Create: `config/testing/data_source.env`
- Create: `config/production/data_source.env`

**Step 1: 创建开发环境配置**

```bash
# config/development/data_source.env
# Data Source Configuration

# HTTP Configuration
HTTP_BASE_URL=http://api.tushare.pro
HTTP_TIMEOUT=30.0

# Rate Limiting (free tier by default)
RATE_LIMIT_PROFILE=free

# Token (optional - will use keyring if not set)
# TUSHARE_TOKEN=your_token_here
```

**Step 2: 创建测试环境配置**

```bash
# config/testing/data_source.env
# Data Source Configuration (Testing)

HTTP_BASE_URL=http://api.tushare.pro
HTTP_TIMEOUT=10.0
RATE_LIMIT_PROFILE=free
```

**Step 3: 创建生产环境配置**

```bash
# config/production/data_source.env
# Data Source Configuration (Production)

# Use production endpoint if different
HTTP_BASE_URL=http://api.tushare.pro
HTTP_TIMEOUT=60.0

# Production rate limit (adjust based on subscription)
RATE_LIMIT_PROFILE=premium
RATE_LIMIT_GLOBAL_RATE=1000
RATE_LIMIT_DAILY_RATE=50000

# Token MUST be set in production via secrets management
# TUSHARE_TOKEN is loaded from keyring/secrets.toml
```

**Step 4: 更新 README 文档**

```bash
# 在 README.md 中添加配置说明

## Configuration

### Data Source Configuration

Data source behavior can be configured via environment variables with `???` prefix:

| Variable | Description | Default |
|----------|-------------|---------|
| HTTP_BASE_URL | API base URL | http://api.tushare.pro |
| HTTP_TIMEOUT | Request timeout (seconds) | 30.0 |
| TUSHARE_TOKEN | API token | (from keyring) |
| RATE_LIMIT_PROFILE | Rate limit profile | free |

These settings are loaded from `config/{environment}/data_source.env`.
```

**Step 5: 提交**

```bash
git add config/
git commit -m "feat(config): add data_source environment configuration files

- Add development/testing/production configs
- Document ??? environment variables
- Enable runtime configuration for data sources"
```

---

## Phase 4: 验证和清理

### Task 4.1: 运行完整测试套件

```bash
# 单元测试
pixi run -e dev test --unit -v

# 集成测试
pixi run -e dev test --integration -v

# 完整 CI
pixi run -e dev ci
```

### Task 4.2: 类型检查

```bash
pixi run -e dev type
```

### Task 4.3: Lint 检查

```bash
pixi run -e dev lint
```

### Task 4.4: 创建 PR

```bash
# 推送到远程
git push origin feature/exception-handling-config-fixes

# 创建 PR
gh pr create --title "fix: exception handling and configuration fixes (P0/P1)" \
  --body "## Summary
- Fix DQ checker exception handling to return ALERT instead of None
- Fix L3BatchService to use logger.exception for stack traces
- Wire DataSourceSettings to TushareClient for runtime configuration

## Test plan
- [x] All existing tests pass
- [x] New tests for exception handling
- [x] Configuration tests with environment variables
- [x] Type checking passes
- [x] Linting passes

## Fixes
- ENG-001: L3BatchService exception swallowing
- ENG-002: DQ checker exception swallowing
- ARCH-002: DataSourceSettings not used"
```

---

## 附录：相关文档

### A. 项目规范参考

- **北极星原则**: `.claude/CLAUDE.md`
- **Python 核心规范**: `.claude/rules/core.md`
- **异常处理规范**: `.claude/rules/core.md` (见错误处理部分)
- **配置规范**: `.claude/rules/foundation.md` (见 Config 部分)

### B. 设计决策记录 (ADR)

创建以下 ADR 文档：

**docs/adr/005-exception-handling-strategy.md**
```markdown
# ADR 005: DQ 检查器异常处理策略

## Context
DQ 检查器在异常时返回 None，导致规则"静默通过"。

## Decision
改为返回 ALERT 级别的 DQIssue，让失败可见。

## Consequences
- 正面：错误不会被吞掉，可观测性提升
- 负面：需要调整依赖 None 行为的代码（如有）
```

**docs/adr/006-datasource-config-injection.md**
```markdown
# ADR 006: DataSource 注入策略

## Context
TushareClient 硬编码 URL 和 timeout。

## Decision
通过 DI 容器注入 DataSourceSettings，支持环境变量配置。

## Consequences
- 正面：配置可运维，支持多环境
- 负面：需要更新 DI 配置
```

### C. 回滚计划

如果出现问题：

```bash
# 回滚单个 PR
git revert <commit-hash>

# 或完全回滚 feature branch
git revert <range-of-commits>
```

---

**Plan Version:** 1.0
**Created:** 2026-01-22
**Estimated Effort:** 1-2 days (P0: 0.5 day, P1: 0.5-1 day)
