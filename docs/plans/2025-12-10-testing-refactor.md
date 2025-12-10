# Testing Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构现有测试以符合Python测试规范v1.0，建立完整的测试基础设施和CI/CD流程

**Architecture:** 采用pytest生态，遵循AAA模式，建立单元测试、集成测试、端到端测试的完整分层体系，配置覆盖率监控和自动化CI检查

**Tech Stack:** pytest, pytest-cov, pytest-mock, GitHub Actions, mypy, ruff

---

### Task 1: 更新pyproject.toml配置pytest

**Files:**
- Modify: `pyproject.toml`

**Step 1: 添加pytest配置块**

在pyproject.toml中添加以下配置：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--cov=packages",
    "--cov=apps",
    "--cov-report=html:htmlcov",
    "--cov-report=term-missing",
    "--cov-report=xml",
    "--cov-branch",
    "--strict-markers",
    "--strict-config",
    "-v"
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "e2e: marks tests as end-to-end tests",
    "benchmark: marks performance benchmark tests",
    "unit: marks tests as unit tests",
]
filterwarnings = [
    "error",
    "ignore::UserWarning",
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
branch = true
source = ["packages", "apps"]
omit = [
    "*/tests/*",
    "*/test_*",
    "*/__pycache__/*",
    "*/site-packages/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "def __str__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "if 0:",
    "class .*\\bProtocol\\):",
    "@(abc\\.)?abstractmethod",
]
show_missing = true
precision = 2
fail_under = 80

[tool.coverage.html]
directory = "htmlcov"
```

**Step 2: 验证配置**

运行：`pixi run pytest --collect-only`
期望：成功收集所有测试

**Step 3: 提交配置**

```bash
git add pyproject.toml
git commit -m "test: 添加pytest配置和覆盖率设置 - P0-XXX"
```

### Task 2: 创建全局测试fixtures

**Files:**
- Create: `tests/conftest.py`

**Step 1: 创建conftest.py基础结构**

```python
"""全局pytest fixtures和配置."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Generator

import numpy as np
import pytest
import polars as pl
from pytest_mock import MockerFixture

# 设置测试数据目录
TEST_DATA_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def fixed_seed() -> None:
    """为所有测试固定随机种子，确保可重复性."""
    np.random.seed(42)


@pytest.fixture
def sample_price_data() -> pl.DataFrame:
    """标准日线价格数据fixture."""
    dates = pl.date_range(
        start=datetime.date(2024, 1, 1),
        end=datetime.date(2024, 1, 31),
        interval="1d",
        eager=True,
    )

    return pl.DataFrame({
        "date": dates,
        "open": [100.0 + i * 0.1 for i in range(len(dates))],
        "high": [101.0 + i * 0.1 for i in range(len(dates))],
        "low": [99.0 + i * 0.1 for i in range(len(dates))],
        "close": [100.5 + i * 0.1 for i in range(len(dates))],
        "volume": [1000000 + i * 1000 for i in range(len(dates))],
    })


@pytest.fixture
def sample_etf_data() -> pl.DataFrame:
    """标准ETF数据fixture."""
    return pl.DataFrame({
        "symbol": ["510300", "510500", "159915"],
        "name": ["沪深300ETF", "中证500ETF", "创业板ETF"],
        "market": ["SH", "SH", "SZ"],
        "category": ["index", "index", "index"],
        "launch_date": [
            datetime.date(2012, 5, 4),
            datetime.date(2013, 2, 25),
            datetime.date(2011, 9, 20),
        ],
    })


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """临时目录fixture."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_current_time(mocker: MockerFixture) -> None:
    """固定当前时间为2024-01-01."""
    fixed_time = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    mocker.patch("datetime.datetime.now", return_value=fixed_time)


@pytest.fixture
def mock_tushare_api(mocker: MockerFixture) -> Any:
    """Mock Tushare API."""
    mock_ts = mocker.MagicMock()
    mock_ts.pro_api = mocker.MagicMock()
    mock_ts.pro_api.daily = mocker.MagicMock()
    mock_ts.pro_api.trade_cal = mocker.MagicMock()
    return mock_ts


@pytest.fixture
def mock_akshare_api(mocker: MockerFixture) -> Any:
    """Mock AkShare API."""
    mock_ak = mocker.MagicMock()
    mock_ak.stock_zh_a_hist = mocker.MagicMock()
    mock_ak.tool_trade_date_hist_sina = mocker.MagicMock()
    return mock_ak


# 测试标记定义
def pytest_configure(config) -> None:
    """配置pytest标记."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "benchmark: marks tests as benchmark tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


# 测试收集钩子
def pytest_collection_modifyitems(config, items) -> None:
    """自动为测试添加标记."""
    for item in items:
        # 根据路径自动添加标记
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        elif "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        else:
            # 默认标记为unit测试
            item.add_marker(pytest.mark.unit)
```

**Step 2: 验证fixtures**

运行：`pixi run pytest --collect-only -q`
期望：成功收集fixtures

**Step 3: 提交**

```bash
git add tests/conftest.py
git commit -m "test: 创建全局测试fixtures - P0-XXX"
```

### Task 3: 重构数据层测试 - 异常处理

**Files:**
- Modify: `packages/core/tests/data/test_exceptions.py`

**Step 1: 重写测试遵循AAA模式**

```python
"""单元测试：数据源异常类."""

from __future__ import annotations

import pytest

from ditto_core.data.exceptions import (
    ConfigurationError,
    DataValidationError,
    DataSourceError,
    NetworkError,
    ParseError,
    ValidationError,
)


class TestDataSourceError:
    """测试DataSourceError基类."""

    def test_init_with_required_message(self) -> None:
        """测试必需参数message."""
        # Arrange
        message = "Test error message"

        # Act
        error = DataSourceError(message)

        # Assert
        assert error.message == message
        assert str(error) == message
        assert error.source is None
        assert error.symbol is None
        assert error.extra == {}

    def test_init_with_all_parameters(self) -> None:
        """测试所有参数."""
        # Arrange
        message = "Test error"
        source = "tushare"
        symbol = "000001"
        extra = {"code": 404}

        # Act
        error = DataSourceError(message, source=source, symbol=symbol, **extra)

        # Assert
        assert error.message == message
        assert error.source == source
        assert error.symbol == symbol
        assert error.extra == extra

    @pytest.mark.parametrize(
        "message,source,symbol,expected_str",
        [
            ("Simple error", None, None, "Simple error"),
            ("Error with source", "tushare", None, "Error with source"),
            ("Error with symbol", None, "000001", "Error with symbol"),
        ],
    )
    def test_string_representation(
        self, message: str, source: str | None, symbol: str | None, expected_str: str
    ) -> None:
        """测试字符串表示."""
        # Arrange & Act
        error = DataSourceError(message, source=source, symbol=symbol)

        # Assert
        assert str(error) == expected_str


class TestNetworkError:
    """测试NetworkError."""

    def test_inheritance(self) -> None:
        """测试继承关系."""
        # Arrange & Act
        error = NetworkError("Network timeout")

        # Assert
        assert isinstance(error, DataSourceError)
        assert error.message == "Network timeout"

    def test_with_retry_count(self) -> None:
        """测试带重试次数的错误."""
        # Arrange
        message = "Temporary failure"
        retry_count = 3

        # Act
        error = NetworkError(message, retry_count=retry_count)

        # Assert
        assert error.retry_count == retry_count


class TestValidationError:
    """测试ValidationError."""

    def test_with_field_info(self) -> None:
        """测试带字段信息的验证错误."""
        # Arrange
        message = "Invalid value"
        field = "price"
        value = -100

        # Act
        error = ValidationError(message, field=field, value=value)

        # Assert
        assert error.field == field
        assert error.value == value


class TestParseError:
    """测试ParseError."""

    def test_with_line_info(self) -> None:
        """测试带行信息的解析错误."""
        # Arrange
        message = "JSON parse error"
        line_number = 42
        line_content = '{"invalid": json}'

        # Act
        error = ParseError(message, line_number=line_number, line_content=line_content)

        # Assert
        assert error.line_number == line_number
        assert error.line_content == line_content


class TestConfigurationError:
    """测试ConfigurationError."""

    def test_with_config_key(self) -> None:
        """测试带配置键的错误."""
        # Arrange
        message = "Missing configuration"
        config_key = "tushare.token"

        # Act
        error = ConfigurationError(message, config_key=config_key)

        # Assert
        assert error.config_key == config_key


class TestDataValidationError:
    """ TestDataValidationError."""

    def test_with_validation_rules(self) -> None:
        """测试带验证规则的数据验证错误."""
        # Arrange
        message = "Data validation failed"
        rules = ["price > 0", "volume >= 0"]

        # Act
        error = DataValidationError(message, rules=rules)

        # Assert
        assert error.rules == rules
```

**Step 2: 验证测试**

运行：`pixi run pytest packages/core/tests/data/test_exceptions.py -v`
期望：所有测试通过

**Step 3: 提交**

```bash
git add packages/core/tests/data/test_exceptions.py
git commit -m "refactor(test): 重构异常测试遵循AAA模式 - P0-XXX"
```

### Task 4: 重构合约层测试 - Pydantic模型

**Files:**
- Modify: `packages/foundation/tests/contracts/test_etf.py`

**Step 1: 重写测试遵循AAA模式**

```python
"""单元测试：ETF信息模型."""

from __future__ import annotations

import datetime

import pytest
import pydantic

from ditto_foundation.contracts.market_data import ETFInfoModel


class TestETFInfoModel:
    """测试ETFInfoModel."""

    def test_valid_etf_info_creation(self) -> None:
        """测试创建有效的ETF信息."""
        # Arrange
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "SH",
            "category": "index",
            "launch_date": datetime.date(2012, 5, 4),
        }

        # Act
        etf = ETFInfoModel(**data)

        # Assert
        assert etf.symbol == "510300"
        assert etf.name == "沪深300ETF"
        assert etf.market == "SH"
        assert etf.category == "index"
        assert etf.launch_date == datetime.date(2012, 5, 4)

    @pytest.mark.parametrize(
        "field,invalid_value,expected_error",
        [
            ("symbol", "", "ensure this value has at least 1 characters"),
            ("symbol", "1234567", "ensure this value has at most 6 characters"),
            ("market", "NYSE", "value is not a valid enumeration member"),
            ("category", "invalid", "value is not a valid enumeration member"),
        ],
    )
    def test_invalid_field_raises_validation_error(
        self, field: str, invalid_value: Any, expected_error: str
    ) -> None:
        """测试无效字段抛出验证错误."""
        # Arrange
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "SH",
            "category": "index",
            "launch_date": datetime.date(2012, 5, 4),
        }
        data[field] = invalid_value

        # Act & Assert
        with pytest.raises(pydantic.ValidationError) as exc_info:
            ETFInfoModel(**data)

        assert expected_error in str(exc_info.value)

    def test_extra_fields_forbidden(self) -> None:
        """测试禁止额外字段."""
        # Arrange
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "SH",
            "category": "index",
            "launch_date": datetime.date(2012, 5, 4),
            "extra_field": "not allowed",
        }

        # Act & Assert
        with pytest.raises(pydantic.ValidationError) as exc_info:
            ETFInfoModel(**data)

        assert "Extra inputs are not permitted" in str(exc_info.value)

    def test_optional_fields_defaults(self) -> None:
        """测试可选字段的默认值."""
        # Arrange
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "SH",
            "category": "index",
            "launch_date": datetime.date(2012, 5, 4),
        }

        # Act
        etf = ETFInfoModel(**data)

        # Assert
        assert etf.description is None
        assert etf.manager is None
        assert etf.tracking_index is None
        assert etf.expense_ratio is None

    def test_to_dict_conversion(self) -> None:
        """测试转换为字典."""
        # Arrange
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "SH",
            "category": "index",
            "launch_date": datetime.date(2012, 5, 4),
        }
        etf = ETFInfoModel(**data)

        # Act
        result = etf.model_dump()

        # Assert
        assert result["symbol"] == "510300"
        assert result["launch_date"] == datetime.date(2012, 5, 4)

    def test_json_serialization(self) -> None:
        """测试JSON序列化."""
        # Arrange
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "SH",
            "category": "index",
            "launch_date": datetime.date(2012, 5, 4),
        }
        etf = ETFInfoModel(**data)

        # Act
        json_str = etf.model_dump_json()

        # Assert
        assert "510300" in json_str
        assert "沪深300ETF" in json_str
```

**Step 2: 验证测试**

运行：`pixi run pytest packages/foundation/tests/contracts/test_etf.py -v`
期望：所有测试通过

**Step 3: 提交**

```bash
git add packages/foundation/tests/contracts/test_etf.py
git commit -m "refactor(test): 重构ETF模型测试遵循AAA模式 - P0-XXX"
```

### Task 5: 创建GitHub Actions CI配置

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/coverage.yml`

**Step 1: 创建测试工作流**

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: ["3.11"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache Pixi dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/pixi
          key: ${{ runner.os }}-pixi-${{ hashFiles('**/pixi.lock') }}
          restore-keys: |
            ${{ runner.os }}-pixi-

      - name: Install Pixi
        uses: prefix-dev/setup-pixi@v0.8.1
        with:
          pixi-version: v0.17.0
          cache: true

      - name: Install dependencies
        run: pixi install

      - name: Run tests with pytest
        run: pixi run pytest --cov=packages --cov=apps --cov-report=xml --cov-report=html

      - name: Upload coverage reports to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          fail_ci_if_error: true
          flags: unittests
          name: codecov-umbrella
```

**Step 2: 创建覆盖率工作流**

```yaml
# .github/workflows/coverage.yml
name: Coverage Check

on:
  pull_request:
    branches: [master, main]

jobs:
  coverage:
    runs-on: windows-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install Pixi
        uses: prefix-dev/setup-pixi@v0.8.1

      - name: Install dependencies
        run: pixi install

      - name: Run coverage
        run: pixi run pytest --cov=packages --cov=apps --cov-fail-under=80

      - name: Coverage comment
        uses: py-cov-action/python-coverage-comment-action@v3
        if: github.event_name == 'pull_request'
        with:
          GITHUB_TOKEN: ${{ github.token }}
```

**Step 3: 验证配置**

本地测试：
```bash
# 安装act（本地GitHub Actions运行器）
brew install act  # macOS
# 或 choco install act  # Windows

# 测试工作流
act -j test
```

**Step 4: 提交**

```bash
git add .github/
git commit -m "ci: 添加GitHub Actions测试和覆盖率工作流 - P0-XXX"
```

### Task 6: 创建性能基准测试

**Files:**
- Create: `tests/benchmark/test_data_processing.py`

**Step 1: 创建基准测试**

```python
"""性能基准测试：数据处理."""

from __future__ import annotations

import pytest

from ditto_core.data.service import DataService


@pytest.mark.benchmark
class TestDataProcessingPerformance:
    """测试数据处理性能."""

    def test_large_dataset_processing(self, benchmark, sample_price_data) -> None:
        """测试大数据集处理性能."""
        # 使用pytest-benchmark测量执行时间
        result = benchmark(DataService.process_price_data, sample_price_data)

        # 基准：1万行数据应在1秒内处理完成
        assert len(result) > 0

    @pytest.mark.slow
    def test_factor_calculation_performance(self, benchmark) -> None:
        """测试因子计算性能."""
        # 创建测试数据
        import polars as pl
        large_data = pl.DataFrame({
            "date": pl.date_range(
                start=datetime.date(2020, 1, 1),
                end=datetime.date(2023, 12, 31),
                interval="1d",
                eager=True,
            ),
            "close": 100 + pl.Series(range(1460)).cast(pl.Float64) * 0.01,
        })

        # 基准测试因子计算
        result = benchmark(
            DataService.calculate_returns,
            large_data
        )

        assert len(result) == len(large_data)
```

**Step 2: 提交**

```bash
git add tests/benchmark/
git commit -m "test: 添加性能基准测试 - P0-XXX"
```

### Task 7: 优化测试覆盖率配置

**Files:**
- Create: `htmlcov/.gitignore`
- Modify: `.gitignore`

**Step 1: 添加覆盖率相关配置**

在`.gitignore`中添加：
```
# Coverage
htmlcov/
.coverage
.coverage.*
coverage.xml
*.cover
.hypothesis/
.pytest_cache/
```

**Step 2: 创建覆盖率报告忽略文件**

```bash
# .gitignore
htmlcov/
```

**Step 3: 提交**

```bash
git add .gitignore htmlcov/.gitignore
git commit -m "test: 添加覆盖率报告配置 - P0-XXX"
```

### Task 8: 运行完整测试套件验证

**Files:**
- 无文件修改

**Step 1: 运行所有测试**

```bash
# 运行完整测试套件
pixi run pytest --cov=packages --cov=apps --cov-report=html

# 检查覆盖率
pixi run pytest --cov=packages --cov=apps --cov-fail-under=80
```

**Step 2: 验证测试分布**

```bash
# 按标记运行测试
pixi run pytest -m unit -v
pixi run pytest -m integration -v
pixi run pytest -m slow -v
```

**Step 3: 最终提交**

```bash
git add -A
git commit -m "test: 完成测试重构和基础设施搭建 - P0-XXX

- 添加pytest配置和覆盖率要求
- 创建全局测试fixtures
- 重构现有测试遵循AAA模式
- 建立CI/CD自动化流程
- 添加性能基准测试框架

覆盖率目标：80%+
关键模块：90%+"
```

---

## 执行说明

此计划已保存到 `docs/plans/2025-12-10-testing-refactor.md`。

**执行选项：**

1. **Subagent驱动（当前会话）** - 我将逐个任务调度新的子代理，任务间进行代码审查，快速迭代

2. **并行会话（独立）** - 在新的worktree中开启新会话，使用executing-plans进行批量执行

选择哪种方式？
