# 项目测试时长分析与优化建议

## 一、核心问题：单元测试与集成测试混淆

**根本问题**: 项目中的单元测试目录下包含了实际是集成测试的代码，这些测试启动了真实的外部服务（Prefect 服务器），导致测试缓慢。

### 项目已有的测试 Marker 定义

`pyproject.toml` 中定义的 markers:
```toml
markers = [
    "integration: Mark test as an integration test",
    "e2e: Mark test as an end-to-end test",
    "slow: Mark test as slow running (skip with -m 'not slow')",
    "smoke: Mark test as a smoke test",
    "benchmark: Mark test as a performance benchmark test",
    "pit: Mark test for Point-in-Time data validation",
    "data: Mark test that requires data fixtures",
    "external: Mark test that calls external APIs (Tushare, etc.)",
]
```

### 测试分类原则

| 测试类型 | 定义 | 依赖 | 典型耗时 | 目录 |
|---------|------|------|---------|------|
| **单元测试** | 测试单个函数/类 | 全部 Mock，无外部依赖 | <0.1s | `tests/unit/` |
| **集成测试** | 测试组件间交互 | 可依赖真实服务（数据库、API等） | 0.1s-5s | `tests/integration/` |
| **端到端测试** | 完整业务流程 | 真实环境 + 外部服务 | >5s | `tests/integration/` |

---

## 二、测试时长分析

### 数据收集概况

| 目录/模块 | 测试数量 | 耗时 | 平均耗时/测试 | 类型判定 |
|----------|---------|------|--------------|---------|
| `packages/datahub/tests/unit/stores/` | 207 | 9.93s | 0.048s | ✅ 单元测试 |
| `packages/datahub/tests/unit/sources/tushare/` | 42 | 2.88s | 0.069s | ⚠️ 混合 (5个失败) |
| `apps/server/tests/unit/ingestion/test_coordinator.py` | 16 | ~1.5s | ~0.09s | ✅ 单元测试 |
| `apps/server/tests/unit/ingestion/test_backfill.py` | 9 | ~1s | ~0.11s | ✅ 单元测试 |
| `apps/server/tests/unit/ingestion/test_retry.py` | 12 | ~1.5s | ~0.12s | ✅ 单元测试 |
| **`apps/server/tests/unit/ingestion/flows/`** | **46** | **>120s** | **>2.6s** | 🔴 **应该是集成测试** |
| **总计** | **892** | **~137s+** | **~0.15s** | - |

### 🔴 关键问题：flows 测试被错误归类为单元测试

**位置**: `apps/server/tests/unit/ingestion/flows/`

**问题**:
- 这些测试启动了**真实的 Prefect 服务器**
- 每个测试需要 2-4 秒启动服务器
- 它们应该被标记为 `@pytest.mark.integration`
- 或者移到 `tests/integration/` 目录下

**日志证据**:
```
INFO     prefect:server.py:881 Starting temporary server on http://127.0.0.1:8800
INFO     httpx:_client.py:1025 HTTP Request: GET http://127.0.0.1:8800/api/health "HTTP/1.1 502 Bad Gateway"
... (5-10次健康检查重试)
INFO     httpx:_client.py:1025 HTTP Request: GET http://127.0.0.1:8800/api/health "HTTP/1.1 200 OK"
```

---

## 三、优化方案

### 优先级 1: 修复测试分类（立即）

#### 方案 A: 添加 integration marker（推荐）

**修改文件**:
- `apps/server/tests/unit/ingestion/flows/test_daily.py`
- `apps/server/tests/unit/ingestion/flows/test_backfill.py`
- `apps/server/tests/unit/ingestion/flows/test_repair.py`
- `apps/server/tests/unit/ingestion/flows/test_deploy.py`

为所有 flow 测试添加 `@pytest.mark.integration`:

```python
# apps/server/tests/unit/ingestion/flows/test_daily.py
import pytest

@pytest.mark.integration
class TestDailyIngestionFlow:
    """每日增量流程集成测试."""

    @pytest.mark.parametrize(
        ("trade_date", "is_trade_day"),
        [...]
    )
    def test_flow_skips_non_trading_days(self, trade_date, is_trade_day):
        ...
```

**收益**:
```bash
# 只运行单元测试（快速）
pytest -m "not integration"  # ~20 秒

# 只运行集成测试（慢速）
pytest -m integration       # ~120 秒

# CI 中可以分开运行，更快反馈
```

---

#### 方案 B: 移动到 integration 目录（更彻底）

**操作**:
```
apps/server/tests/unit/ingestion/flows/
  → apps/server/tests/integration/ingestion/flows/
```

**优点**: 目录结构清晰反映测试类型
**缺点**: 需要更新导入路径，可能影响其他代码

---

### 优先级 2: Mock Prefect 服务器（可选）

如果希望 flows 测试作为单元测试运行，可以使用 Mock:

**修改文件**: `apps/server/tests/unit/ingestion/flows/conftest.py` (新建)

```python
"""Prefect flow 测试配置。"""

from unittest.mock import patch, MagicMock
import pytest

@pytest.fixture
def mock_prefect_server():
    """模拟 Prefect 服务器，不启动真实服务。"""
    with patch("prefect.cli.dev.TemporaryServer") as mock_server:
        # 配置 mock 返回值
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_server.return_value = mock_instance

        yield mock_instance
```

**预期收益**: 120 秒 → ~5 秒

**缺点**: 无法测试真实的 Prefect 集成

---

### 优先级 3: 修复 tushare source 测试

**修改文件**: `packages/datahub/tests/unit/sources/tushare/test_source.py`

**问题**: 5 个测试失败，因为 `DataSource.ingest_date()` 已被移除

**操作**: 删除 `TestTushareSourceIngestDate` 类（对应废弃的方法）

---

### 优先级 4: 测试命令标准化

**CI/CD 脚本**:

```bash
# 快速单元测试（每次提交）
pytest -m "not integration and not slow" --maxfail=5

# 完整单元测试（PR 合并前）
pytest -m "not integration"

# 集成测试（每日/发布前）
pytest -m integration

# 全量测试
pytest
```

---

## 四、实施计划

### 阶段 1: 修复测试分类 (1小时)

1. **为 flows 测试添加 integration marker**
   - `test_daily.py` - 添加 `@pytest.mark.integration`
   - `test_backfill.py` - 添加 `@pytest.mark.integration`
   - `test_repair.py` - 添加 `@pytest.mark.integration`
   - `test_deploy.py` - 添加 `@pytest.mark.integration`

2. **验证命令**
   ```bash
   pytest -m "not integration" --collect-only  # 应该只显示单元测试
   pytest -m integration --collect-only       # 应该只显示 flows 测试
   ```

### 阶段 2: 修复失败的测试 (30分钟)

1. **删除 tushare source 中废弃的测试**
   - 删除 `TestTushareSourceIngestDate` 类

2. **运行验证**
   ```bash
   pytest packages/datahub/tests/unit/sources/tushare/
   ```

### 阶段 3: CI/CD 脚本更新 (30分钟)

1. **更新 `.github/workflows/test.yml`**

```yaml
- name: 快速单元测试
  run: pixi run -e dev pytest -m "not integration and not slow" --maxfail=5

- name: 完整单元测试 (PR 时)
  if: github.event_name == 'pull_request'
  run: pixi run -e dev pytest -m "not integration"

- name: 集成测试 (main 分支每日)
  if: github.ref == 'refs/heads/main' && github.event_name == 'schedule'
  run: pixi run -e dev pytest -m integration
```

---

## 五、实施状态

### ✅ 已完成 (2026-01-03)

#### 1. 测试目录规范化

**移动的文件**:
- `apps/server/tests/unit/ingestion/flows/*` → `apps/server/tests/integration/ingestion/flows/`
  - test_daily.py
  - test_backfill.py
  - test_repair.py
  - test_deploy.py

- `packages/datahub/tests/unit/stores/*` → `packages/datahub/tests/integration/stores/`
  - test_adj_factor_store.py
  - test_bars_store.py
  - test_calendar_store.py
  - test_calendar_store_concurrent.py
  - test_index_weight_store.py
  - test_ingestion_metadata_store.py
  - test_pipeline_store.py
  - test_quarantine_store.py
  - test_security_store.py
  - test_sqlite_client.py
  - test_stock_status_store.py
  - test_universe_store.py

- `packages/datahub/tests/unit/runtime/*` → `packages/datahub/tests/integration/runtime/`
  - test_freeze_manager.py
  - test_freeze_manager_checksum.py
  - test_sid_allocator.py
  - test_sql_engine.py
  - test_sql_engine_injection.py
  - test_sqlite_pool.py

#### 2. 自动标记集成测试

创建了 conftest.py 文件，为 `tests/integration/` 目录下的所有测试自动添加 `@pytest.mark.integration` marker：
- `apps/server/tests/integration/conftest.py`
- `packages/datahub/tests/integration/conftest.py`

#### 3. 删除废弃测试

- `packages/datahub/tests/unit/sources/tushare/test_source.py` 中的 `TestTushareSourceIngestDate` 类已删除

#### 4. 修复代码规范问题

- 为 flows 测试文件添加 `# ruff: noqa: PLC0415` 注释
- 修复 test_deploy.py 的行长度问题

---

## 六、实际结果

### 测试分类统计

| 指标 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| 总测试数 | 898 | 898 | - |
| 单元测试 | 841 | 571 | -270 |
| 集成测试 | 57 | 327 | +270 |
| 单元测试占比 | 93.7% | 63.6% | -30.1% |

### 测试时长对比

| 测试类型 | 测试数量 | 耗时 | 平均耗时/测试 |
|---------|---------|------|--------------|
| 单元测试（不含 integration） | 571 | ~21s | ~0.037s |
| 集成测试（含 integration 目录） | 327 | ~116s | ~0.355s |
| **总计** | **898** | **~137s** | **~0.153s** |

### CI/CD 改进

**优化前**:
```bash
# 所有测试混合运行
pytest  # ~137 秒
```

**优化后**:
```bash
# 快速单元测试（每次提交）
pytest -m "not integration"  # ~21 秒 (-85%)

# 完整测试套件（PR/发布前）
pytest  # ~137 秒

# 仅集成测试（单独运行）
pytest -m integration  # ~116 秒
```

**收益**:
- 开发时快速反馈：21 秒 vs 137 秒（**-85%**）
- PR 检查更快：21 秒即可验证核心逻辑
- 集成测试可按需运行

---

## 七、预期收益（原始）

### 开发体验改善

- **本地开发**: `pytest -m "not integration"` 快速验证逻辑
- **PR 检查**: 快速单元测试 < 20 秒反馈
- **发布前**: 运行完整测试套件

---

## 六、关键文件路径

### 需要添加 marker 的文件:
- `apps/server/tests/unit/ingestion/flows/test_daily.py`
- `apps/server/tests/unit/ingestion/flows/test_backfill.py`
- `apps/server/tests/unit/ingestion/flows/test_repair.py`
- `apps/server/tests/unit/ingestion/flows/test_deploy.py`

### 需要删除废弃测试的文件:
- `packages/datahub/tests/unit/sources/tushare/test_source.py`

### 配置文件:
- `pyproject.toml` - pytest markers (已配置，无需修改)
- `.github/workflows/test.yml` - CI 脚本

---

## 七、风险与注意事项

1. **测试隔离**: 确保 integration marker 不影响单元测试的隔离性
2. **CI 配置**: 确保 CI 脚本正确过滤测试类型
3. **开发习惯**: 团队需要适应使用 marker 区分测试类型

---

## 八、后续改进建议

1. **添加 pre-commit hook**: 检查单元测试是否依赖外部服务
2. **测试覆盖率监控**: 分别跟踪单元测试和集成测试的覆盖率
3. **性能回归测试**: 定期监控测试时长趋势
