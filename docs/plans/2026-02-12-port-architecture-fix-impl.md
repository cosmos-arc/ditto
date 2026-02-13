# ditto-port 架构修复实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 4 个 P1 运行时 Bug 和 1 个架构债务，统一 DI 为单一组合根。

**Architecture:** 采用激进方案 - 完全移除 DomainServiceProvider，合并所有 Store 绑定到 DataHubProvider。执行顺序：P1 Bug 修复 → 架构整理 → P2 可观测性。

**Tech Stack:** Python 3.12, dishka (DI), FastAPI, Prefect, pytest

**设计文档:** [2026-02-12-port-architecture-fix.md](./2026-02-12-port-architecture-fix.md)

---

## 执行顺序

```
阶段 1：P1 运行时 Bug 修复（必须先完成）
├── Task 1: Foundation 层新增 get_environment()
├── Task 2: 修复 backfill 参数名
├── Task 3: 修复 DQ 返回契约
└── Task 4: CLI --data-root 透传

阶段 2：P1 架构整理（依赖阶段 1）
├── Task 5: 删除 DomainServiceProvider
├── Task 6: DataHubProvider 吸收 Store 绑定
└── Task 7: 更新入口点 Provider 注册

阶段 3：P2 可观测性与语义修正
├── Task 8: request_id 全链路闭环
└── Task 9: 修正 backfill 并发注释
```

---

## 阶段 1：P1 运行时 Bug 修复

### Task 1: Foundation 层新增 get_environment()

**复杂度:** S（单文件 + 测试）

**Files:**
- Modify: `packages/foundation/src/ditto_foundation/config/environment.py`
- Modify: `packages/foundation/src/ditto_foundation/config/__init__.py`
- Create: `packages/foundation/tests/unit/test_environment.py`

**Step 1: 编写单元测试**

Create: `packages/foundation/tests/unit/test_environment.py`

```python
"""测试 get_environment() 函数."""

import os
from unittest.mock import patch

import pytest

from ditto_foundation.config.environment import Environment, get_environment


class TestGetEnvironment:
    """get_environment() 测试."""

    def test_default_is_development(self) -> None:
        """默认返回 development."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENVIRONMENT", None)
            result = get_environment()
            assert result == Environment.DEVELOPMENT

    def test_reads_environment_variable(self) -> None:
        """从 ENVIRONMENT 环境变量读取."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            result = get_environment()
            assert result == Environment.PRODUCTION

    def test_case_insensitive(self) -> None:
        """大小写不敏感."""
        with patch.dict(os.environ, {"ENVIRONMENT": "TESTING"}):
            result = get_environment()
            assert result == Environment.TESTING

    def test_invalid_value_raises(self) -> None:
        """无效值抛出 ValueError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "invalid"}):
            with pytest.raises(ValueError, match="Invalid environment"):
                get_environment()
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/test_environment.py -v
```

Expected: FAIL - `ImportError: cannot import name 'get_environment'`

**Step 3: 实现 get_environment()**

Modify: `packages/foundation/src/ditto_foundation/config/environment.py`

在 `Environment` 类后添加：

```python
import os


def get_environment() -> Environment:
    """
    获取当前运行环境（统一入口）。

    读取顺序：
    1. 环境变量 ENVIRONMENT
    2. 默认值 development

    Returns:
        Environment 枚举值

    Raises:
        ValueError: 环境变量值无效时

    """
    env_str = os.getenv("ENVIRONMENT", "development")
    return Environment.from_str(env_str)
```

**Step 4: 更新 __init__.py 导出**

Modify: `packages/foundation/src/ditto_foundation/config/__init__.py`

添加 `get_environment` 到导出。

**Step 5: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/test_environment.py -v
```

Expected: PASS

**Step 6: 更新 ConfigProvider 使用统一方法**

Modify: `apps/port/src/ditto_port/registry/config.py`

```python
# 修改导入
from ditto_foundation.config import ConfigInitCoordinator, ConfigLoader, Environment, get_environment

# 修改方法
@provide
def environment(self) -> Environment:
    """提供运行环境枚举。"""
    return get_environment()
```

**Step 7: Commit**

```bash
git add packages/foundation/src/ditto_foundation/config/environment.py \
        packages/foundation/src/ditto_foundation/config/__init__.py \
        packages/foundation/tests/unit/test_environment.py \
        apps/port/src/ditto_port/registry/config.py
git commit -m "feat(foundation): 新增 get_environment() 统一环境变量读取"
```

---

### Task 2: 修复 backfill 参数名不一致

**复杂度:** S（单行修改 + 测试）

**Files:**
- Modify: `apps/port/src/ditto_port/jobs/flows/deploy.py:123`
- Create: `packages/foundation/tests/unit/jobs/test_deploy_unit.py`

**Step 1: 编写参数契约测试**

Create: `packages/foundation/tests/unit/jobs/test_deploy_unit.py`

```python
"""部署配置参数契约测试."""

import pytest

from ditto_port.jobs.flows.deploy import _get_flow_configs


class TestFlowDeploymentContracts:
    """Flow 部署参数契约测试."""

    def test_backfill_uses_config_not_backfill_config(self) -> None:
        """backfill_flow 参数名应为 config，而非 backfill_config."""
        configs = _get_flow_configs()

        backfill_config = next(
            (c for c in configs if c.deployment_name == "backfill-prod"),
            None,
        )
        assert backfill_config is not None

        # 参数名必须是 "config"，匹配 backfill_flow 签名
        assert "config" in backfill_config.parameters
        assert "backfill_config" not in backfill_config.parameters
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/jobs/test_deploy_unit.py -v
```

Expected: FAIL

**Step 3: 修复参数名**

Modify: `apps/port/src/ditto_port/jobs/flows/deploy.py:123`

```python
# 修改前
"backfill_config": {

# 修改后
"config": {
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/jobs/test_deploy_unit.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/jobs/flows/deploy.py \
        packages/foundation/tests/unit/jobs/test_deploy_unit.py
git commit -m "fix(port): 修复 backfill_flow 参数名 backfill_config → config"
```

---

### Task 3: 修复 DQ 返回契约（添加 issues 字段）

**复杂度:** S（单行修改 + 测试）

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py:106-112`
- Create: `packages/foundation/tests/unit/services/test_l3_batch_unit.py`

**Step 1: 编写返回契约测试**

Create: `packages/foundation/tests/unit/services/test_l3_batch_unit.py`

```python
"""L3 Batch Service 返回契约测试."""

from unittest.mock import MagicMock

import polars as pl
import pytest

from ditto_port.services.ingestion.quality.l3_batch_service import L3BatchService


class TestL3BatchServiceContract:
    """L3BatchService 返回契约测试."""

    @pytest.fixture
    def mock_engine(self) -> MagicMock:
        """创建 mock DQ 引擎."""
        engine = MagicMock()
        result = MagicMock()
        result.passed = True
        result.issues = []
        result.alert_count = 0
        result.has_alerts = False
        engine.check_statistical.return_value = result
        return engine

    @pytest.fixture
    def mock_market_service(self) -> MagicMock:
        """创建 mock MarketService."""
        service = MagicMock()
        service.find_bars.return_value = pl.DataFrame()
        return service

    @pytest.fixture
    def mock_metadata_service(self) -> MagicMock:
        """创建 mock MetadataService."""
        service = MagicMock()
        service.list_calendar_range.return_value = pl.DataFrame()
        return service

    def test_check_dataset_returns_issues_field(
        self,
        mock_engine: MagicMock,
        mock_market_service: MagicMock,
        mock_metadata_service: MagicMock,
    ) -> None:
        """check_dataset 返回必须包含 issues 字段."""
        service = L3BatchService(
            engine=mock_engine,
            market_service=mock_market_service,
            metadata_service=mock_metadata_service,
        )

        result = service.check_dataset(
            dataset="stock_daily",
            trade_date="2024-01-15",
        )

        assert "issues" in result
        assert isinstance(result["issues"], list)
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/services/test_l3_batch_unit.py -v
```

Expected: FAIL

**Step 3: 添加 issues 字段到返回值**

Modify: `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py:106-112`

```python
return {
    "dataset": dataset,
    "trade_date": trade_date,
    "passed": result.passed,
    "issue_count": len(result.issues),
    "alert_count": result.alert_count,
    "issues": result.issues,  # 新增
}
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/services/test_l3_batch_unit.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py \
        packages/foundation/tests/unit/services/test_l3_batch_unit.py
git commit -m "fix(port): L3BatchService 返回添加 issues 字段修复 DQ 告警失效"
```

---

### Task 4: CLI --data-root 透传支持

**复杂度:** M（涉及 CLI 和 DI 配置）

**Files:**
- Modify: `apps/port/src/ditto_port/cli/main.py:26-37`
- Modify: `apps/port/src/ditto_port/registry/config.py:94-97`
- Create: `packages/foundation/tests/integration/cli/test_cli_data_root.py`

**Step 1: 编写集成测试**

Create: `packages/foundation/tests/integration/cli/test_cli_data_root.py`

```python
"""CLI --data-root 参数透传测试."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ditto_port.cli.main import app


runner = CliRunner()


class TestCLIDataRootPassthrough:
    """CLI --data-root 参数透传测试."""

    def test_data_root_sets_environment_variable(self, tmp_path: Path) -> None:
        """--data-root 参数应设置 DITTO_DATA_ROOT 环境变量."""
        custom_root = str(tmp_path / "custom_data")

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

            assert result.exit_code == 0
            assert os.getenv("DITTO_DATA_ROOT") == custom_root
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/foundation/tests/integration/cli/test_cli_data_root.py -v
```

Expected: FAIL

**Step 3: CLI main.py 设置环境变量**

Modify: `apps/port/src/ditto_port/cli/main.py:26-37`

```python
import os

@app.callback()
def main(
    ctx: typer.Context,
    data_root: str = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出模式"),
) -> None:
    """初始化 CLI 上下文."""
    ctx.ensure_object(dict)

    # 透传 data_root 到环境变量
    if data_root:
        os.environ["DITTO_DATA_ROOT"] = data_root

    ctx.obj["data_root"] = data_root
    ctx.obj["verbose"] = verbose
```

**Step 4: ConfigProvider 支持环境变量覆盖**

Modify: `apps/port/src/ditto_port/registry/config.py:94-97`

```python
@provide
def data_root_config(self, config_loader: ConfigLoader) -> DataRootConfig:
    """加载数据根目录配置。"""
    data_store_values = load_env_file(config_loader, "data_store")

    # 支持 CLI 透传的环境变量覆盖
    if override := os.getenv("DITTO_DATA_ROOT"):
        data_store_values["data_root"] = override

    return DataRootConfig.model_validate(data_store_values)
```

**Step 5: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/foundation/tests/integration/cli/test_cli_data_root.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add apps/port/src/ditto_port/cli/main.py \
        apps/port/src/ditto_port/registry/config.py \
        packages/foundation/tests/integration/cli/test_cli_data_root.py
git commit -m "feat(port): CLI --data-root 参数透传到 DITTO_DATA_ROOT 环境变量"
```

---

## 阶段 2：P1 架构整理

### Task 5: DataHubProvider 吸收 Store 绑定

**复杂度:** L（大量代码迁移，需谨慎）

**Files:**
- Modify: `apps/port/src/ditto_port/registry/datahub.py`
- Read: `apps/port/src/ditto_port/registry/domain.py`（源文件）

**Step 1: 分析迁移范围**

需要从 `domain.py` 迁移到 `datahub.py` 的方法：

| 类别 | 方法 | domain.py 行号 |
|------|------|----------------|
| Runtime | `sqlite_client`, `instrument_id_allocator`, `freeze_manager` | 129-142 |
| Metadata | `instrument/reader/writer`, `calendar_reader/writer`, `industry_*`, `universe_*` | 148-237 |
| Runtime | `ingestion_log_*`, `comparison_*`, `quarantine_*` | 242-270 |
| Market | `stock_bars_*`, `stock_status_*`, `stock_adj_*`, `etf_bars_*`, `etf_status_*` | 280-328 |
| Fundamental | `balance_sheet_*`, `income_statement_*`, `cash_flow_*`, `dividend_*`, etc. | 335-481 |

**Step 2: 合并导入**

将 `domain.py` 中所有 Store 导入合并到 `datahub.py`。

**Step 3: 迁移方法**

将所有 `@provide` 方法从 `domain.py` 复制到 `datahub.py`。

**Step 4: 删除 DataHubProvider 中重复的方法**

删除 `fundamental_query_service` 等直接在方法内创建 Store 的方法。

**Step 5: 运行检查**

```bash
pixi run -e dev check
```

**Step 6: Commit**

```bash
git add apps/port/src/ditto_port/registry/datahub.py
git commit -m "refactor(port): DataHubProvider 吸收 DomainServiceProvider 所有 Store 绑定"
```

---

### Task 6: 删除 DomainServiceProvider 文件

**复杂度:** S（删除文件）

**Files:**
- Delete: `apps/port/src/ditto_port/registry/domain.py`
- Modify: `apps/port/src/ditto_port/registry/__init__.py`

**Step 1: 更新 __init__.py**

Modify: `apps/port/src/ditto_port/registry/__init__.py`

```python
"""依赖注入注册表."""

from ditto_port.registry.app import AppProvider
from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.core import CoreProvider
from ditto_port.registry.datahub import DataHubProvider
from ditto_port.registry.notification import NotificationProvider
from ditto_port.registry.sources import DataSourcesProvider

__all__ = [
    "AppProvider",
    "ConfigProvider",
    "CoreProvider",
    "DataHubProvider",
    "DataSourcesProvider",
    "NotificationProvider",
]
```

**Step 2: 删除 domain.py**

```bash
rm apps/port/src/ditto_port/registry/domain.py
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(port): 删除 DomainServiceProvider"
```

---

### Task 7: 更新入口点 Provider 注册

**复杂度:** S（删除导入和参数）

**Files:**
- Modify: `apps/port/src/ditto_port/main.py:40-46, 105-111`
- Modify: `apps/port/src/ditto_port/cli/context.py:18-24, 42-48`

**Step 1: 更新 main.py**

Modify: `apps/port/src/ditto_port/main.py`

```python
# 修改导入
from ditto_port.registry import (
    ConfigProvider,
    CoreProvider,
    DataHubProvider,
    DataSourcesProvider,
)

# 修改容器创建
container = make_async_container(
    ConfigProvider(),
    CoreProvider(),
    DataHubProvider(),
    DataSourcesProvider(),
)
```

**Step 2: 更新 cli/context.py**

Modify: `apps/port/src/ditto_port/cli/context.py`

```python
# 修改导入
from ditto_port.registry import (
    ConfigProvider,
    CoreProvider,
    DataHubProvider,
    DataSourcesProvider,
)

# 修改容器创建
container = make_container(
    ConfigProvider(),
    CoreProvider(),
    DataHubProvider(),
    DataSourcesProvider(),
)
```

**Step 3: 运行完整检查**

```bash
pixi run -e dev check
```

**Step 4: Commit**

```bash
git add apps/port/src/ditto_port/main.py \
        apps/port/src/ditto_port/cli/context.py \
        apps/port/src/ditto_port/registry/__init__.py
git commit -m "refactor(port): 移除 DomainServiceProvider 注册，统一单一组合根"
```

---

## 阶段 3：P2 可观测性与语义修正

### Task 8: request_id 全链路闭环

**复杂度:** M（涉及 middleware 和异常处理器）

**Files:**
- Modify: `apps/port/src/ditto_port/main.py:179-186`
- Modify: `apps/port/src/ditto_port/middleware.py`
- Create: `packages/foundation/tests/unit/test_request_id_propagation.py`

**Step 1: 编写测试**

Create: `packages/foundation/tests/unit/test_request_id_propagation.py`

```python
"""request_id 传播测试."""

import pytest
from fastapi.testclient import TestClient

from ditto_port.main import app


class TestRequestIdPropagation:
    """request_id 传播测试."""

    def test_request_id_in_response_header(self) -> None:
        """响应头应包含 X-Request-ID."""
        client = TestClient(app)

        response = client.get("/healthz")

        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36  # UUID 格式
```

**Step 2: 存储到 request.state**

Modify: `apps/port/src/ditto_port/main.py:179-186`

```python
@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log incoming requests and outgoing responses."""
    request_id = str(uuid.uuid4())

    # 新增：存储到 request.state
    request.state.request_id = request_id

    # ... 其余代码不变
```

**Step 3: 更新异常处理器**

Modify: `apps/port/src/ditto_port/middleware.py`

在异常处理器中使用 `getattr(request.state, "request_id", "unknown")`。

**Step 4: 运行测试**

```bash
pixi run -e dev pytest packages/foundation/tests/unit/test_request_id_propagation.py -v
```

**Step 5: Commit**

```bash
git add apps/port/src/ditto_port/main.py \
        apps/port/src/ditto_port/middleware.py \
        packages/foundation/tests/unit/test_request_id_propagation.py
git commit -m "fix(port): request_id 存储到 request.state 实现全链路闭环"
```

---

### Task 9: 修正 backfill 并发注释

**复杂度:** S（单行注释修改）

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/backfill.py:81-82`

**Step 1: 修正注释**

```python
# 修改前
# 年份级并行，年内串行（避免文件锁冲突）

# 修改后
# 按年份分组，并发度上限为 min(parallel, 年份数)
# 注意：同一年内的日期仍会并行执行，依赖 FileLockManager 避免冲突
```

**Step 2: Commit**

```bash
git add apps/port/src/ditto_port/services/ingestion/backfill.py
git commit -m "docs(port): 修正 backfill 并发注释，说明实际并发语义"
```

---

## 验收检查清单

完成所有任务后运行：

```bash
pixi run -e dev check
```

**验收标准：**
- [ ] 所有测试通过
- [ ] 类型检查通过
- [ ] `DomainServiceProvider` 已删除
- [ ] `DataHubProvider` 是唯一提供 Store 的 Provider
- [ ] `ENVIRONMENT` 环境变量统一使用
- [ ] backfill 参数名正确
- [ ] DQ issues 字段返回
- [ ] CLI `--data-root` 透传生效

---

## 风险与回滚

**风险点：**
1. Task 5-7 涉及大量代码迁移，可能影响 DI 解析
2. 测试目录结构需根据实际项目调整

**回滚方案：**
```bash
git revert HEAD  # 回滚单个 commit
```
