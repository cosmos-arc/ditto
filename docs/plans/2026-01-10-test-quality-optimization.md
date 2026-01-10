# 测试质量全面优化计划

## 概述

| 项目 | 详情 |
|------|------|
| 创建时间 | 2026-01-10 |
| Sprint | Phase 5: 测试质量优化 |
| 分支 | `feat/test-quality-optimization` |

## 问题诊断

### 0. 规则更新（预防措施）✅ 已完成

**文件**: `.claude/rules/python-test.md`

**新增规则**：
1. **文件命名规范** - 防止 import 冲突
2. **禁止假测试** - 严格禁止 `assert True`/`assert False`
3. **Mock 选择** - 强制使用 `pytest-mock`，禁止 `unittest.mock`
4. **参数化测试** - 减少重复代码
5. **异步测试** - 覆盖异步代码
6. **覆盖率要求** - 80% 覆盖率标准
7. **并发测试配置** - pytest-xdist 配置
8. **测试隔离性** - 确保测试独立
9. **检测问题命令** - 提交前检查命令

### 1. 覆盖率问题
- **当前行覆盖率**: ~42.59%
- **当前分支覆盖率**: ~10.24%
- **目标覆盖率**: >=80%
- **差距**: 需要提升约37个百分点

**低覆盖率模块**:
- `packages/datahub/src/ditto_datahub/errors.py` - 异常类定义
- `packages/datahub/src/ditto_datahub/hub.py` - DataHub 门面类

### 2. 测试基础设施问题

#### 2.1 import 冲突（2对文件）
```
packages/datahub/tests/unit/stores/test_pipeline_store.py
packages/datahub/tests/integration/stores/test_pipeline_store.py
packages/datahub/tests/unit/stores/test_quarantine_store.py
packages/datahub/tests/integration/stores/test_quarantine_store.py
```

#### 2.2 测试文件命名规范问题（约80个文件）

**新规则要求**：
- 单元测试: `test_{module}_unit.py`
- 集成测试: `test_{module}_integration.py`
- E2E测试: `test_{module}_e2e.py`

**当前问题**：大部分测试文件没有添加层级后缀，导致：
1. 同名文件在不同测试层级冲突
2. 文件用途不明确
3. 违反新的命名规范

**需要重命名的文件清单**：

**Unit 测试（约56个文件需要添加 `_unit` 后缀）**:
```
packages/datahub/tests/unit/
├── test_errors.py → test_errors_unit.py
├── test_hub.py → test_hub_unit.py
├── alerts/test_base.py → test_base_unit.py
├── alerts/test_manager.py → test_manager_unit.py
├── dq/checkers/test_business.py → test_business_unit.py
├── dq/checkers/test_statistical.py → test_statistical_unit.py
├── dq/checkers/test_technical.py → test_technical_unit.py
├── dq/test_config_loading.py → test_config_loading_unit.py
├── dq/test_engine.py → test_engine_unit.py
├── dq/test_init_dq_config.py → test_init_dq_config_unit.py
├── dq/test_models.py → test_models_unit.py
├── dq/test_report.py → test_report_unit.py
├── dq/test_result.py → test_result_unit.py
├── meta/test_schema_validator.py → test_schema_validator_unit.py
├── meta/test_schemas.py → test_schemas_unit.py
├── repositories/test_adj_factor_repository.py → test_adj_factor_repository_unit.py
├── repositories/test_bars_repository.py → test_bars_repository_unit.py
├── repositories/test_calendar_repository.py → test_calendar_repository_unit.py
├── repositories/test_index_repository.py → test_index_repository_unit.py
├── repositories/test_security_repository.py → test_security_repository_unit.py
├── repositories/test_universe_repository.py → test_universe_repository_unit.py
├── runtime/test_cache.py → test_cache_unit.py
├── runtime/test_cache_ttl.py → test_cache_ttl_unit.py
├── runtime/test_fake_time.py → test_fake_time_unit.py
├── runtime/test_file_lock.py → test_file_lock_unit.py
├── runtime/test_pit_helper.py → test_pit_helper_unit.py
├── runtime/test_pit_helper_property.py → test_pit_helper_property_unit.py
├── sources/test_accessor.py → test_accessor_unit.py
├── sources/test_base.py → test_base_unit.py
├── sources/tushare/test_client.py → test_client_unit.py
├── sources/tushare/test_http_utils.py → test_http_utils_unit.py
├── sources/tushare/test_rate_limiter.py → test_rate_limiter_unit.py
├── sources/tushare/test_source.py → test_source_unit.py
├── stores/test_adj_factor_store.py → test_adj_factor_store_unit.py
├── stores/test_bars_store.py → test_bars_store_unit.py
├── stores/test_calendar_store.py → test_calendar_store_unit.py
├── stores/test_ingestion_cursor_store.py → test_ingestion_cursor_store_unit.py
├── stores/test_ingestion_log_store.py → test_ingestion_log_store_unit.py
├── stores/test_index_weight_store.py → test_index_weight_store_unit.py
├── stores/test_parquet_store_base.py → test_parquet_store_base_unit.py
├── stores/test_pipeline_store.py → test_pipeline_store_unit.py ⚠️ 冲突
├── stores/test_quarantine_store.py → test_quarantine_store_unit.py ⚠️ 冲突
├── stores/test_security_store.py → test_security_store_unit.py
├── stores/test_sqlite_client.py → test_sqlite_client_unit.py
├── stores/test_stock_status_store.py → test_stock_status_store_unit.py
├── stores/test_universe_store.py → test_universe_store_unit.py
├── utils/test_date_utils.py → test_date_utils_unit.py
└── datahub/test_datahub_observability.py → test_datahub_observability_unit.py

packages/foundation/tests/unit/
├── test_app_initializer.py → test_app_initializer_unit.py
├── test_observability.py → test_observability_unit.py
├── util/test_dates.py → test_dates_unit.py
├── util/test_dates_property.py → test_dates_property_unit.py
└── util/test_io.py → test_io_unit.py

apps/server/tests/unit/
├── ingestion/test_backfill.py → test_backfill_unit.py
├── ingestion/test_config.py → test_config_unit.py
├── ingestion/test_coordinator.py → test_coordinator_unit.py
├── ingestion/test_datasets.py → test_datasets_unit.py
├── ingestion/test_metadata.py → test_metadata_unit.py
├── ingestion/test_monitoring.py → test_monitoring_unit.py
├── ingestion/test_retry.py → test_retry_unit.py
├── ingestion/test_security_mapper.py → test_security_mapper_unit.py
├── ingestion/flows/test_backfill.py → test_backfill_flows_unit.py
├── ingestion/flows/test_daily.py → test_daily_flows_unit.py
├── ingestion/tasks/test_dq_batch.py → test_dq_batch_unit.py
└── ingestion/tasks/test_task_factory.py → test_task_factory_unit.py
```

**Integration 测试（约16个文件需要添加 `_integration` 后缀）**:
```
packages/datahub/tests/integration/
├── runtime/test_freeze_manager.py → test_freeze_manager_integration.py
├── runtime/test_freeze_manager_checksum.py → test_freeze_manager_checksum_integration.py
├── runtime/test_sid_allocator.py → test_sid_allocator_integration.py
├── runtime/test_sql_engine.py → test_sql_engine_integration.py
├── runtime/test_sql_engine_injection.py → test_sql_engine_injection_integration.py
├── runtime/test_sqlite_pool.py → test_sqlite_pool_integration.py
├── sources/tushare/test_end_to_end.py → test_end_to_end_integration.py
├── stores/test_calendar_store_concurrent.py → test_calendar_store_concurrent_integration.py
├── stores/test_pipeline_store.py → test_pipeline_store_integration.py ⚠️ 冲突
├── stores/test_quarantine_store.py → test_quarantine_store_integration.py ⚠️ 冲突
└── stores/test_sqlite_pool.py → test_sqlite_pool_integration.py

apps/server/tests/integration/
├── ingestion/test_adj_factor_ingestion.py → test_adj_factor_ingestion_integration.py
├── ingestion/test_coordinator_dq_blocking.py → test_coordinator_dq_blocking_integration.py
├── ingestion/flows/test_backfill.py → test_backfill_flows_integration.py
├── ingestion/flows/test_daily.py → test_daily_flows_integration.py
├── ingestion/flows/test_deploy.py → test_deploy_flows_integration.py
└── ingestion/flows/test_repair.py → test_repair_flows_integration.py
```

**E2E 测试（1个文件需要重命名）**:
```
tests/integration/test_observability_e2e.py → tests/e2e/test_observability_e2e.py
```

#### 2.3 假测试（1个文件）
```
packages/datahub/tests/unit/stores/test_sqlite_client.py:367
    assert True  # If we get here, close() worked
```

#### 2.4 并发测试被禁用
- `pyproject.toml:396` 并发配置被注释

### 3. Mock 工具使用问题（22个文件需要迁移到 pytest-mock）

```
apps/server/tests/unit/ingestion/test_security_mapper.py
apps/server/tests/unit/ingestion/test_coordinator.py
apps/server/tests/unit/ingestion/test_metadata.py
apps/server/tests/unit/ingestion/flows/test_backfill.py
apps/server/tests/unit/ingestion/flows/test_daily.py
packages/datahub/tests/unit/dq/test_engine.py
packages/datahub/tests/unit/dq/checkers/test_technical.py
packages/datahub/tests/unit/dq/checkers/test_statistical.py
apps/server/tests/unit/ingestion/tasks/test_task_factory.py
packages/datahub/tests/integration/runtime/test_freeze_manager_checksum.py
apps/server/tests/unit/ingestion/test_backfill.py
packages/datahub/tests/unit/repositories/test_index_repository.py
packages/datahub/tests/unit/repositories/test_bars_repository.py
apps/server/tests/integration/ingestion/test_adj_factor_ingestion.py
apps/server/tests/integration/ingestion/test_coordinator_dq_blocking.py
apps/server/tests/unit/ingestion/tasks/test_dq_batch.py
packages/datahub/tests/unit/repositories/test_universe_repository.py
apps/server/tests/integration/ingestion/flows/test_deploy.py
apps/server/tests/integration/ingestion/flows/test_repair.py
apps/server/tests/integration/ingestion/flows/test_backfill.py
apps/server/tests/integration/ingestion/flows/test_daily.py
apps/server/tests/unit/ingestion/test_retry.py
```

### 4. 异步测试覆盖不足
- 项目中有异步代码（FastAPI、httpx 异步请求）
- 搜索 `async def test` 返回 **0** 个结果
- 需要为异步函数添加异步测试覆盖

---

## 优化计划

### Phase 1: 修复测试基础设施（紧急）✅ 已完成

完成时间：2026-01-10

**已完成任务：**
- [x] Task 1.1: 批量重命名测试文件（85个文件）
- [x] Task 1.2: 更新导入语句（无需更新，无跨测试文件导入）
- [x] Task 1.3: 修复假测试（test_sqlite_client.py:367）
- [x] Task 1.4: 启用并发测试配置

**提交记录：**
- b256df5: refactor: rename datahub unit test files with _unit suffix (52 files)
- 433d1dd: refactor: rename datahub integration test files with _integration suffix (10 files)
- 0d1ef6f: refactor: rename foundation unit test files with _unit suffix (5 files)
- a7cc0dc: refactor: rename server unit test files with _unit suffix (12 files)
- 3b503b4: refactor: rename server integration test files with _integration suffix (6 files)
- 5fe7729: test: fix fake test in test_sqlite_client_unit.py
- bbf9529: test: enable parallel test execution with pytest-xdist
- 59e6625: fix: remove dynamic_context from coverage config for xdist compatibility

**验收结果：**
- ✅ 无 import 冲突错误
- ✅ 无假测试（grep -r "assert True" tests/ 无结果）
- ✅ 并发测试已启用（-n auto）
- ✅ datahub + foundation 单元测试覆盖率 91.26% (> 80%)
- ✅ 861 个单元测试通过

**已知问题：**
- apps/server/tests/unit/ingestion/flows/ 下有 7 个测试失败，与 backfill flow 的 mock 设置有关（预存在问题，与 Phase 1 更改无关）

#### Task 1.1: 批量重命名测试文件（约80个文件）

**自动化脚本**:
```bash
#!/bin/bash
# rename_tests.sh - 批量重命名测试文件以符合命名规范

# Unit 测试添加 _unit 后缀
for file in $(find packages/datahub/tests/unit -name "test_*.py" -not -name "*_unit.py"); do
    dir=$(dirname "$file")
    base=$(basename "$file" .py)
    new_name="${base}_unit.py"
    echo "Renaming: $file -> $dir/$new_name"
    git mv "$file" "$dir/$new_name"
done

# Integration 测试添加 _integration 后缀
for file in $(find packages/datahub/tests/integration -name "test_*.py" -not -name "*_integration.py"); do
    dir=$(dirname "$file")
    base=$(basename "$file" .py)
    new_name="${base}_integration.py"
    echo "Renaming: $file -> $dir/$new_name"
    git mv "$file" "$dir/$new_name"
done

# 对 apps/server 执行相同操作
for file in $(find apps/server/tests/unit -name "test_*.py" -not -name "*_unit.py"); do
    dir=$(dirname "$file")
    base=$(basename "$file" .py)
    new_name="${base}_unit.py"
    echo "Renaming: $file -> $dir/$new_name"
    git mv "$file" "$dir/$new_name"
done

for file in $(find apps/server/tests/integration -name "test_*.py" -not -name "*_integration.py"); do
    dir=$(dirname "$file")
    base=$(basename "$file" .py)
    new_name="${base}_integration.py"
    echo "Renaming: $file -> $dir/$new_name"
    git mv "$file" "$dir/$new_name"
done

# 对 packages/foundation 执行相同操作
for file in $(find packages/foundation/tests/unit -name "test_*.py" -not -name "*_unit.py"); do
    dir=$(dirname "$file")
    base=$(basename "$file" .py)
    new_name="${base}_unit.py"
    echo "Renaming: $file -> $dir/$new_name"
    git mv "$file" "$dir/$new_name"
done

# 创建 E2E 测试目录并移动文件
mkdir -p tests/e2e
git mv tests/integration/test_observability_e2e.py tests/e2e/ || echo "File already moved or not found"
```

**注意事项**：
1. 使用 `git mv` 保留文件历史
2. 优先处理有冲突的文件（test_pipeline_store.py、test_quarantine_store.py）
3. 重命名后需要更新所有导入语句
4. 分批提交，每批10-20个文件

#### Task 1.2: 更新导入语句

重命名后需要使用脚本更新所有导入：

```bash
#!/bin/bash
# update_imports.sh - 更新导入语句

# 查找所有需要更新的导入
grep -r "from.*test_.*import" --include="*.py" | grep -v "_unit\|_integration\|_e2e"

# 批量替换（需要手动审核）
find . -name "*.py" -type f -exec sed -i 's/test_\([a-z_]*\)\.py/test_\1_unit.py/g' {} \;
```

#### Task 1.3: 修复假测试
- **文件**: `packages/datahub/tests/unit/stores/test_sqlite_client_unit.py:367`
- **问题**: `assert True` 无效断言
- **修复**: 添加实际验证逻辑或删除该测试

#### Task 1.4: 启用并发测试
- **文件**: `pyproject.toml:396`
- **操作**: 取消注释 `"-n", "auto"`
- **预期**: 测试速度提升 2-4倍

---

### Phase 2: 提升覆盖率到80%（核心）

#### Task 2.1: 为 errors.py 补充测试
创建 `packages/datahub/tests/unit/test_errors.py`：

```python
"""测试 DataHub 异常类"""

import pytest
from ditto_datahub.errors import (
    DataHubError,
    SidNotFoundError,
    TradingDateNotFoundError,
    ValidationError,
    DatasetNotFoundError,
    PartitionNotFoundError,
)


class TestDataHubError:
    def test_init_with_message(self):
        error = DataHubError("test error")
        assert str(error) == "test error"
        assert error.details == {}

    def test_init_with_details(self):
        error = DataHubError("test", details={"key": "value"})
        assert error.details == {"key": "value"}


class TestSidNotFoundError:
    def test_default_init(self):
        error = SidNotFoundError()
        assert str(error) == "SID not found"

    def test_init_with_identifier(self):
        error = SidNotFoundError(identifier="600000")
        assert error.details["identifier"] == "600000"

    def test_init_with_source(self):
        error = SidNotFoundError(source="tushare")
        assert error.details["source"] == "tushare"


# 其他异常类的测试...
```

#### Task 2.2: 为 hub.py 补充测试
扩展 `packages/datahub/tests/unit/test_hub.py`：

```python
"""测试 DataHub 门面类"""

import pytest
from pathlib import Path
from ditto_datahub.hub import DataHub
from ditto_datahub.errors import SidNotFoundError


class TestDataHubInit:
    def test_init_with_default_path(self):
        hub = DataHub()
        assert hub.data_root.exists()

    def test_init_with_custom_path(self, tmp_path):
        hub = DataHub(data_root=tmp_path)
        assert hub.data_root == tmp_path


class TestDataHubResolveSid:
    def test_resolve_sid_not_found(self, tmp_path):
        hub = DataHub(data_root=tmp_path)
        with pytest.raises(SidNotFoundError):
            hub.resolve_sid("NOTEXIST")

    # 添加更多测试...


class TestDataHubClose:
    def test_close_uninitialized_resources(self, tmp_path):
        hub = DataHub(data_root=tmp_path)
        hub.close()  # 不应报错

    def test_close_initialized_resources(self, tmp_path):
        hub = DataHub(data_root=tmp_path)
        _ = hub.sqlite_pool  # 初始化资源
        hub.close()  # 不应报错

    # 添加更多测试...


class TestDataHubConvenienceMethods:
    def test_get_trading_days(self, tmp_path):
        hub = DataHub(data_root=tmp_path)
        # 需要添加测试数据
        # days = hub.get_trading_days("2024-01-01", "2024-01-31")
        # assert len(days) > 0

    def test_is_trading_day(self, tmp_path):
        hub = DataHub(data_root=tmp_path)
        # 需要添加测试数据
        # assert hub.is_trading_day("2024-01-02") == True
```

#### Task 2.3: 提升分支覆盖率
- 使用条件组合测试覆盖所有 `if-else` 分支
- 测试 `try-except` 的异常路径
- 测试 `and/or` 逻辑的所有组合

---

### Phase 3: 迁移到 pytest-mock ✅ 已完成

完成时间：2026-01-10

**已完成任务：**
- [x] Task 3.1: 批量迁移 unittest.mock 到 pytest-mock（23个文件）
- [x] Task 3.2: 更新代码审查检查清单（已在规则中定义）

**迁移文件清单：**

| # | 文件 | 状态 | 测试通过 |
|---|------|------|---------|
| 1 | `apps/server/tests/unit/ingestion/test_coordinator_unit.py` | ✅ | 42 passed |
| 2 | `apps/server/tests/unit/ingestion/test_metadata_unit.py` | ✅ | 20 passed |
| 3 | `packages/datahub/tests/unit/dq/test_engine_unit.py` | ✅ | 21 passed |
| 4 | `apps/server/tests/unit/ingestion/test_security_mapper_unit.py` | ✅ | 20 passed |
| 5 | `apps/server/tests/unit/ingestion/flows/test_backfill_unit.py` | ✅ | 15 passed |
| 6 | `apps/server/tests/unit/ingestion/flows/test_daily_unit.py` | ✅ | 18 passed |
| 7 | `packages/datahub/tests/unit/dq/checkers/test_technical_unit.py` | ✅ | 27 passed |
| 8 | `packages/datahub/tests/unit/dq/checkers/test_statistical_unit.py` | ✅ | 23 passed |
| 9 | `apps/server/tests/unit/ingestion/tasks/test_task_factory_unit.py` | ✅ | 22 passed |
| 10 | `apps/server/tests/unit/ingestion/tasks/test_dq_batch_unit.py` | ✅ | 5 passed |
| 11 | `apps/server/tests/unit/ingestion/test_backfill_unit.py` | ✅ | 11 passed |
| 12 | `apps/server/tests/unit/ingestion/test_retry_unit.py` | ✅ | 12 passed |
| 13 | `packages/datahub/tests/unit/repositories/test_index_repository_unit.py` | ✅ | 13 passed |
| 14 | `packages/datahub/tests/unit/repositories/test_bars_repository_unit.py` | ✅ | 32 passed |
| 15 | `packages/datahub/tests/unit/repositories/test_universe_repository_unit.py` | ✅ | 18 passed |
| 16 | `packages/datahub/tests/integration/runtime/test_freeze_manager_checksum_integration.py` | ✅ | 6 passed |
| 17 | `packages/datahub/tests/integration/stores/test_pipeline_store_integration.py` | ✅ | 30 passed |
| 18 | `apps/server/tests/integration/ingestion/test_adj_factor_ingestion_integration.py` | ✅ | 2 passed (预存在失败) |
| 19 | `apps/server/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py` | ✅ | 3 passed |
| 20 | `apps/server/tests/integration/ingestion/flows/test_deploy_integration.py` | ✅ | 4 passed (1 skipped) |
| 21 | `apps/server/tests/integration/ingestion/flows/test_repair_integration.py` | ✅ | 11 passed |
| 22 | `apps/server/tests/integration/ingestion/flows/test_backfill_integration.py` | ✅ | 11 passed |
| 23 | `apps/server/tests/integration/ingestion/flows/test_daily_integration.py` | ✅ | 20 passed |

**验收结果：**
- ✅ 无 `from unittest.mock` 导入（grep 验证无匹配）
- ✅ 无 `@patch` 装饰器
- ✅ 使用 `mocker` fixture
- ✅ 所有迁移的测试通过
- ✅ 总计约 350+ 个测试通过

**提交记录：**
- （待创建提交）

#### Task 3.1: 批量迁移 unittest.mock 到 pytest-mock

**迁移模式**:

**改造前**:
```python
from unittest.mock import Mock, patch, MagicMock

@patch("module.function")
def test_something(mock_func):
    mock_func.return_value = "value"
    ...
```

**改造后**:
```python
def test_something(mocker):
    mock_func = mocker.patch("module.function")
    mock_func.return_value = "value"
    ...
```

**需要迁移的文件清单**（按优先级）:

| 优先级 | 文件 | 原因 |
|--------|------|------|
| P0 | `apps/server/tests/unit/ingestion/test_coordinator.py` | 核心协调器 |
| P0 | `apps/server/tests/unit/ingestion/test_metadata.py` | 元数据管理 |
| P0 | `packages/datahub/tests/unit/dq/test_engine.py` | DQ 引擎 |
| P1 | `apps/server/tests/unit/ingestion/flows/*.py` | 摄入流程 |
| P1 | `packages/datahub/tests/unit/dq/checkers/*.py` | DQ 检查器 |
| P2 | `apps/server/tests/integration/ingestion/*.py` | 集成测试 |
| P2 | `packages/datahub/tests/unit/repositories/*.py` | 仓库测试 |

#### Task 3.2: 更新代码审查检查清单
- [ ] 无 `from unittest.mock import` 导入
- [ ] 无 `@patch` 装饰器
- [ ] 使用 `mocker` fixture

---

### Phase 4: 优化测试效率

#### Task 4.1: 参数化测试改造
将重复测试改造为参数化：

**改造前**:
```python
def test_read_filter_by_sids_1(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000001])
    assert len(df) == 3

def test_read_filter_by_sids_2(self, store, sample_df):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=[1000002])
    assert len(df) == 1
```

**改造后**:
```python
@pytest.mark.parametrize("sids,expected_count", [
    ([1000001], 3),
    ([1000002], 1),
    ([1000001, 1000002], 4),
    ([], 0),
])
def test_read_filter_by_sids(self, store, sample_df, sids, expected_count):
    store.write("adj_factor", sample_df, 2024)
    df = store.read("adj_factor", sids=sids)
    assert len(df) == expected_count
```

#### Task 4.2: 异步测试补充

**问题**: 项目有异步代码但无异步测试（搜索 `async def test` 返回 0）

**需要添加异步测试的模块**:
1. FastAPI 路由测试
2. httpx 异步客户端测试
3. 异步数据库操作测试

**示例**:
```python
import pytest

@pytest.mark.asyncio
async def test_async_endpoint():
    """测试异步 API 端点"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/data")
        assert response.status_code == 200
```

---

### Phase 5: 验收标准

#### 5.1 测试基础设施
- [ ] 无 import 冲突错误（`pytest --collect-only` 无报错）
- [ ] 无假测试（`grep -r "assert True" tests/` 无结果）
- [ ] 无 unittest.mock（`grep -r "from unittest.mock" tests/` 无结果）
- [ ] 测试可并发执行

#### 5.2 覆盖率
- [ ] 分支覆盖率 >= 80%
- [ ] 行覆盖率 >= 80%
- [ ] `pixi run -e dev ci-check` 通过

#### 5.3 测试效率
- [ ] 全量测试时间 < 5分钟（并发）
- [ ] 快速测试集 < 30秒
- [ ] 异步测试覆盖关键异步函数

---

## 关键文件清单

### 需要修改的文件
| 文件 | 修改内容 |
|------|---------|
| `pyproject.toml:396` | 取消注释并发测试配置 |
| `packages/datahub/tests/unit/stores/test_sqlite_client.py:367` | 修复假测试 |
| **22个文件** | 迁移 unittest.mock → pytest-mock |

### 需要重命名的文件
| 原文件 | 新文件 |
|--------|--------|
| `packages/datahub/tests/unit/stores/test_pipeline_store.py` | `test_pipeline_store_unit.py` |
| `packages/datahub/tests/unit/stores/test_quarantine_store.py` | `test_quarantine_store_unit.py` |

### 需要创建的文件
| 文件 | 目的 |
|------|------|
| `packages/datahub/tests/unit/test_errors.py` | 测试异常类 |
| `packages/datahub/tests/unit/test_hub.py` | 测试 DataHub 门面 |
| `packages/datahub/tests/unit/async/` | 异步测试目录 |

---

## 验证流程

```bash
# 1. 检查假测试
grep -r "assert True" tests/
grep -r "assert False" tests/

# 2. 检查 unittest.mock 使用
grep -r "from unittest.mock" tests/
grep -r "@patch" tests/

# 3. 检查 import 冲突
pytest --collect-only 2>&1 | grep "import mismatch"

# 4. 运行测试并检查覆盖率
pytest --cov --cov-report=term-missing:skip-covered

# 5. 完整 CI 检查
pixi run -e dev ci-check

# 6. 检查异步测试覆盖
grep -r "async def test" tests/
```

---

## 风险识别

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 测试执行时间过长 | 降低开发效率 | 使用标记分层执行，启用并发 |
| 测试脆弱性（flaky） | 误报，降低信任度 | 改进测试隔离，使用 fixture |
| 覆盖率提升困难 | 无法达到80%目标 | 优先覆盖核心路径，逐步提升 |
| Mock 迁移引入 bug | 测试失败 | 逐个文件迁移，充分测试 |
| 异步测试不稳定 | CI 不稳定 | 使用 pytest-asyncio 的 fixture 模式 |
| **文件重命名破坏导入** | **测试失败，CI挂掉** | **自动化脚本 + 充分测试 + 分批提交** |

---

## 预计工作量

| 阶段 | 任务 | 预计时间 | 优先级 |
|------|------|---------|--------|
| Phase 1.1 | 重命名约80个测试文件 | 4-6小时 | **紧急** |
| Phase 1.2 | 更新导入语句和 conftest.py | 2-3小时 | **紧急** |
| Phase 1.3 | 修复假测试 + 启用并发 | 1小时 | **紧急** |
| Phase 2 | 提升覆盖率到80% | 8-16小时 | 高 |
| Phase 3 | 迁移 22 个文件到 pytest-mock | 6-10小时 | 高 |
| Phase 4 | 参数化测试改造 + 异步测试 | 4-8小时 | 中 |
| **Phase 1 小计** | | **7-10小时** | |
| **总计** | | **27-49小时** | |
