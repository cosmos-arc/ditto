# 测试架构全面改造实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 基于新的测试标准（80% 单元 + 20% 集成），系统性重构所有测试文件，规范命名、删除重复、补充缺失。

**架构:** 分 4 个 Commit 执行：Commit 1（命名规范化 + 删除重复）、Commit 2（重分类）、Commit 3（补充测试）、Commit 4（验证）。

**技术栈:** pytest、pytest-mock、git、pixi

---

## Commit 1: 命名规范化 + 文件夹整理 + 删除重复测试

**目标:** 重命名 20+ 个测试文件、重分类 Flow 测试、删除 ~1600 行重复测试代码

### Task 1.1: 删除 observability e2e 测试

**问题:** `tests/integration/test_observability_e2e.py` 测试外部服务，违反"不测试外部服务"原则

**Files:**
- Delete: `tests/integration/test_observability_e2e.py`

**Step 1: 检查文件是否存在**

Run: `ls tests/integration/test_observability_e2e.py`
Expected: 文件存在

**Step 2: 删除文件**

Run: `rm tests/integration/test_observability_e2e.py`
Expected: 文件已删除

**Step 3: 验证删除**

Run: `ls tests/integration/test_observability_e2e.py 2>&1`
Expected: "No such file or directory"

---

### Task 1.2: 重命名 CLI e2e 测试

**问题:** `test_e2e.py` 命名误导，应为 `test_cli_integration.py`

**Files:**
- Rename: `apps/port/tests/integration/cli/test_e2e.py` → `apps/port/tests/integration/cli/test_cli_integration.py`

**Step 1: 检查源文件存在**

Run: `ls apps/port/tests/integration/cli/test_e2e.py`
Expected: 文件存在

**Step 2: 读取文件内容**

Run: `Read apps/port/tests/integration/cli/test_e2e.py`
Expected: 读取文件内容，确认是否需要修改 import

**Step 3: 使用 git mv 重命名**

Run: `git mv apps/port/tests/integration/cli/test_e2e.py apps/port/tests/integration/cli/test_cli_integration.py`
Expected: 文件已重命名

**Step 4: 验证重命名**

Run: `ls apps/port/tests/integration/cli/test_cli_integration.py`
Expected: 新文件存在

---

### Task 1.3: 重命名 Tushare e2e 测试

**问题:** `test_end_to_end_integration.py` 应为 `test_tushare_api_integration.py`

**Files:**
- Rename: `packages/datahub/tests/integration/sources/tushare/test_end_to_end_integration.py` → `packages/datahub/tests/integration/sources/tushare/test_tushare_api_integration.py`

**Step 1: 检查源文件存在**

Run: `ls packages/datahub/tests/integration/sources/tushare/test_end_to_end_integration.py`
Expected: 文件存在

**Step 2: 使用 git mv 重命名**

Run: `git mv packages/datahub/tests/integration/sources/tushare/test_end_to_end_integration.py packages/datahub/tests/integration/sources/tushare/test_tushare_api_integration.py`
Expected: 文件已重命名

**Step 3: 验证重命名**

Run: `ls packages/datahub/tests/integration/sources/tushare/test_tushare_api_integration.py`
Expected: 新文件存在

---

### Task 1.4: 重命名 Foundation config 测试文件（3个）

**问题:** Foundation config 测试文件缺少 `_unit` 后缀

**Files:**
- Rename: `packages/foundation/tests/unit/config/test_manager.py` → `test_manager_unit.py`
- Rename: `packages/foundation/tests/unit/config/test_environment.py` → `test_environment_unit.py`
- Rename: `packages/foundation/tests/unit/config/test_loader.py` → `test_loader_unit.py`

**Step 1: 重命名 test_manager.py**

Run: `git mv packages/foundation/tests/unit/config/test_manager.py packages/foundation/tests/unit/config/test_manager_unit.py`
Expected: 文件已重命名

**Step 2: 重命名 test_environment.py**

Run: `git mv packages/foundation/tests/unit/config/test_environment.py packages/foundation/tests/unit/config/test_environment_unit.py`
Expected: 文件已重命名

**Step 3: 重命名 test_loader.py**

Run: `git mv packages/foundation/tests/unit/config/test_loader.py packages/foundation/tests/unit/config/test_loader_unit.py`
Expected: 文件已重命名

**Step 4: 验证所有重命名**

Run: `ls packages/foundation/tests/unit/config/`
Expected: 所有文件已重命名

---

### Task 1.5: 重命名 Port CLI 测试文件（5个）

**问题:** Port CLI 测试文件缺少 `_unit` 后缀

**Files:**
- Rename: `apps/port/tests/unit/cli/test_executor.py` → `test_executor_unit.py`
- Rename: `apps/port/tests/unit/cli/test_output.py` → `test_output_unit.py`
- Rename: `apps/port/tests/unit/cli/test_validation.py` → `test_validation_unit.py`
- Rename: `apps/port/tests/unit/test_conftest.py` → `test_conftest_unit.py`
- Rename: `apps/port/tests/unit/test_db_fixtures.py` → `test_db_fixtures_unit.py`

**Step 1: 重命名 test_executor.py**

Run: `git mv apps/port/tests/unit/cli/test_executor.py apps/port/tests/unit/cli/test_executor_unit.py`
Expected: 文件已重命名

**Step 2: 重命名 test_output.py**

Run: `git mv apps/port/tests/unit/cli/test_output.py apps/port/tests/unit/cli/test_output_unit.py`
Expected: 文件已重命名

**Step 3: 重命名 test_validation.py**

Run: `git mv apps/port/tests/unit/cli/test_validation.py apps/port/tests/unit/cli/test_validation_unit.py`
Expected: 文件已重命名

**Step 4: 重命名 test_conftest.py**

Run: `git mv apps/port/tests/unit/test_conftest.py apps/port/tests/unit/test_conftest_unit.py`
Expected: 文件已重命名

**Step 5: 重命名 test_db_fixtures.py**

Run: `git mv apps/port/tests/unit/test_db_fixtures.py apps/port/tests/unit/test_db_fixtures_unit.py`
Expected: 文件已重命名

**Step 6: 验证所有重命名**

Run: `ls apps/port/tests/unit/cli/ && ls apps/port/tests/unit/*.py`
Expected: 所有文件已重命名

---

### Task 1.6: 重命名 DataHub 测试文件（4个）

**问题:** DataHub 测试文件缺少 `_unit` 后缀或位置不对

**Files:**
- Rename: `packages/datahub/tests/unit/runtime/test_freeze_manager_collect_checksums.py` → `test_freeze_manager_collect_checksums_unit.py`
- Rename: `packages/datahub/tests/unit/accessors/test_filter_failed_rows.py` → `test_filter_failed_rows_unit.py`
- Move+Rename: `packages/datahub/tests/test_models_common.py` → `packages/datahub/tests/unit/models/test_models_common_unit.py`
- Move+Rename: `packages/datahub/tests/test_models_quality.py` → `packages/datahub/tests/unit/models/test_models_quality_unit.py`

**Step 1: 创建 models 测试目录**

Run: `mkdir -p packages/datahub/tests/unit/models/`
Expected: 目录已创建

**Step 2: 重命名 test_freeze_manager_collect_checksums.py**

Run: `git mv packages/datahub/tests/unit/runtime/test_freeze_manager_collect_checksums.py packages/datahub/tests/unit/runtime/test_freeze_manager_collect_checksums_unit.py`
Expected: 文件已重命名

**Step 3: 重命名 test_filter_failed_rows.py**

Run: `git mv packages/datahub/tests/unit/accessors/test_filter_failed_rows.py packages/datahub/tests/unit/accessors/test_filter_failed_rows_unit.py`
Expected: 文件已重命名

**Step 4: 移动并重命名 test_models_common.py**

Run: `git mv packages/datahub/tests/test_models_common.py packages/datahub/tests/unit/models/test_models_common_unit.py`
Expected: 文件已移动并重命名

**Step 5: 移动并重命名 test_models_quality.py**

Run: `git mv packages/datahub/tests/test_models_quality.py packages/datahub/tests/unit/models/test_models_quality_unit.py`
Expected: 文件已移动并重命名

**Step 6: 验证所有重命名**

Run: `ls packages/datahub/tests/unit/runtime/ && ls packages/datahub/tests/unit/accessors/ && ls packages/datahub/tests/unit/models/`
Expected: 所有文件已正确重命名

---

### Task 1.7: 重命名 Port CLI 集成测试文件（5个）

**问题:** Port CLI 集成测试文件缺少 `_integration` 后缀

**Files:**
- Rename: `apps/port/tests/integration/cli/test_adj_commands.py` → `test_adj_commands_integration.py`
- Rename: `apps/port/tests/integration/cli/test_calendar_commands.py` → `test_calendar_commands_integration.py`
- Rename: `apps/port/tests/integration/cli/test_etf_commands.py` → `test_etf_commands_integration.py`
- Rename: `apps/port/tests/integration/cli/test_init_commands.py` → `test_init_commands_integration.py`
- Rename: `apps/port/tests/integration/cli/test_stock_commands.py` → `test_stock_commands_integration.py`

**Step 1: 重命名 test_adj_commands.py**

Run: `git mv apps/port/tests/integration/cli/test_adj_commands.py apps/port/tests/integration/cli/test_adj_commands_integration.py`
Expected: 文件已重命名

**Step 2: 重命名 test_calendar_commands.py**

Run: `git mv apps/port/tests/integration/cli/test_calendar_commands.py apps/port/tests/integration/cli/test_calendar_commands_integration.py`
Expected: 文件已重命名

**Step 3: 重命名 test_etf_commands.py**

Run: `git mv apps/port/tests/integration/cli/test_etf_commands.py apps/port/tests/integration/cli/test_etf_commands_integration.py`
Expected: 文件已重命名

**Step 4: 重命名 test_init_commands.py**

Run: `git mv apps/port/tests/integration/cli/test_init_commands.py apps/port/tests/integration/cli/test_init_commands_integration.py`
Expected: 文件已重命名

**Step 5: 重命名 test_stock_commands.py**

Run: `git mv apps/port/tests/integration/cli/test_stock_commands.py apps/port/tests/integration/cli/test_stock_commands_integration.py`
Expected: 文件已重命名

**Step 6: 验证所有重命名**

Run: `ls apps/port/tests/integration/cli/`
Expected: 所有文件已重命名

---

### Task 1.8: 重分类 Flow 测试（Integration → Unit）

**问题:** Flow 测试几乎完全 Mock，应该归类为单元测试

**Files:**
- Move+Rename: `apps/port/tests/integration/ingestion/flows/test_backfill_integration.py` → `apps/port/tests/unit/ingestion/flows/test_backfill_unit.py`
- Move+Rename: `apps/port/tests/integration/ingestion/flows/test_daily_integration.py` → `apps/port/tests/unit/ingestion/flows/test_daily_unit.py`

**Step 1: 检查源文件存在**

Run: `ls apps/port/tests/integration/ingestion/flows/test_backfill_integration.py && ls apps/port/tests/integration/ingestion/flows/test_daily_integration.py`
Expected: 两个文件都存在

**Step 2: 读取 test_backfill_integration.py 内容**

Run: `Read apps/port/tests/integration/ingestion/flows/test_backfill_integration.py`
Expected: 读取文件内容，确认是否需要修改 mark

**Step 3: 移动 test_backfill_integration.py**

Run: `git mv apps/port/tests/integration/ingestion/flows/test_backfill_integration.py apps/port/tests/unit/ingestion/flows/test_backfill_unit.py`
Expected: 文件已移动并重命名

**Step 4: 读取新位置文件，修改 mark**

Run: `Read apps/port/tests/unit/ingestion/flows/test_backfill_unit.py`
Expected: 读取文件内容

**Step 5: 修改 pytest.mark**

Edit: `apps/port/tests/unit/ingestion/flows/test_backfill_unit.py`
Change: `@pytest.mark.integration` → `@pytest.mark.unit`
Expected: mark 已修改

**Step 6: 移动 test_daily_integration.py**

Run: `git mv apps/port/tests/integration/ingestion/flows/test_daily_integration.py apps/port/tests/unit/ingestion/flows/test_daily_unit.py`
Expected: 文件已移动并重命名

**Step 7: 读取新位置文件，修改 mark**

Run: `Read apps/port/tests/unit/ingestion/flows/test_daily_unit.py`
Expected: 读取文件内容

**Step 8: 修改 pytest.mark**

Edit: `apps/port/tests/unit/ingestion/flows/test_daily_unit.py`
Change: `@pytest.mark.integration` → `@pytest.mark.unit`
Expected: mark 已修改

**Step 9: 验证移动和修改**

Run: `ls apps/port/tests/unit/ingestion/flows/ && grep -l "@pytest.mark.unit" apps/port/tests/unit/ingestion/flows/test_*.py`
Expected: 文件已移动，mark 已修改

---

### Task 1.9: 删除 QuarantineStore 重复集成测试

**问题:** QuarantineStore 有两个测试文件测试相同功能

**Files:**
- Delete: `packages/datahub/tests/integration/stores/test_quarantine_store_integration.py`
- Keep: `packages/datahub/tests/unit/stores/test_quarantine_store_unit.py`

**Step 1: 检查两个文件是否存在**

Run: `ls packages/datahub/tests/integration/stores/test_quarantine_store_integration.py && ls packages/datahub/tests/unit/stores/test_quarantine_store_unit.py`
Expected: 两个文件都存在

**Step 2: 读取集成测试文件内容**

Run: `Read packages/datahub/tests/integration/stores/test_quarantine_store_integration.py`
Expected: 读取文件内容，确认测试内容

**Step 3: 删除集成测试文件**

Run: `rm packages/datahub/tests/integration/stores/test_quarantine_store_integration.py`
Expected: 文件已删除

**Step 4: 验证删除**

Run: `ls packages/datahub/tests/integration/stores/test_quarantine_store_integration.py 2>&1`
Expected: "No such file or directory"

---

### Task 1.10: 删除 models/common 重复测试

**问题:** `test_models_common_unit.py` 和 `test_common_unit.py` 测试同一个模块

**Files:**
- Delete: `packages/datahub/tests/unit/models/test_models_common_unit.py`
- Keep: `packages/datahub/tests/unit/models/test_common_unit.py`

**Step 1: 检查两个文件是否存在**

Run: `ls packages/datahub/tests/unit/models/test_models_common_unit.py && ls packages/datahub/tests/unit/models/test_common_unit.py`
Expected: 两个文件都存在

**Step 2: 读取 test_models_common_unit.py 内容**

Run: `Read packages/datahub/tests/unit/models/test_models_common_unit.py`
Expected: 读取文件内容，确认测试内容

**Step 3: 读取 test_common_unit.py 内容**

Run: `Read packages/datahub/tests/unit/models/test_common_unit.py`
Expected: 读取文件内容

**Step 4: 合并测试内容（如果需要）**

如果 `test_models_common_unit.py` 有独特测试内容，需要合并到 `test_common_unit.py`

**Step 5: 删除重复文件**

Run: `rm packages/datahub/tests/unit/models/test_models_common_unit.py`
Expected: 文件已删除

**Step 6: 验证删除**

Run: `ls packages/datahub/tests/unit/models/test_models_common_unit.py 2>&1`
Expected: "No such file or directory"

---

### Task 1.11: 删除 CLI 帮助命令重复测试

**问题:** 多个 CLI 测试文件都测试帮助命令

**Files:**
- Modify: `apps/port/tests/integration/cli/test_stock_commands_integration.py` - 删除 `test_main_help()`
- Modify: `apps/port/tests/integration/cli/test_etf_commands_integration.py` - 删除 `test_etf_help()`
- Modify: `apps/port/tests/integration/cli/test_calendar_commands_integration.py` - 删除 `test_calendar_help()`
- Modify: `apps/port/tests/integration/cli/test_adj_commands_integration.py` - 删除 `test_adj_help()`
- Modify: `apps/port/tests/integration/cli/test_init_commands_integration.py` - 删除 `test_init_help()`
- Keep: `apps/port/tests/integration/cli/test_cli_integration.py` - 保留帮助测试

**Step 1: 读取 test_stock_commands_integration.py**

Run: `Read apps/port/tests/integration/cli/test_stock_commands_integration.py`
Expected: 读取文件内容，找到 `test_main_help()` 方法

**Step 2: 删除 test_main_help() 方法**

Edit: `apps/port/tests/integration/cli/test_stock_commands_integration.py`
Delete: 删除 `test_main_help()` 及相关代码
Expected: 方法已删除

**Step 3: 读取 test_etf_commands_integration.py**

Run: `Read apps/port/tests/integration/cli/test_etf_commands_integration.py`
Expected: 读取文件内容

**Step 4: 删除 test_etf_help() 方法**

Edit: `apps/port/tests/integration/cli/test_etf_commands_integration.py`
Delete: 删除 `test_etf_help()` 及相关代码
Expected: 方法已删除

**Step 5: 读取 test_calendar_commands_integration.py**

Run: `Read apps/port/tests/integration/cli/test_calendar_commands_integration.py`
Expected: 读取文件内容

**Step 6: 删除 test_calendar_help() 方法**

Edit: `apps/port/tests/integration/cli/test_calendar_commands_integration.py`
Delete: 删除 `test_calendar_help()` 及相关代码
Expected: 方法已删除

**Step 7: 读取 test_adj_commands_integration.py**

Run: `Read apps/port/tests/integration/cli/test_adj_commands_integration.py`
Expected: 读取文件内容

**Step 8: 删除 test_adj_help() 方法**

Edit: `apps/port/tests/integration/cli/test_adj_commands_integration.py`
Delete: 删除 `test_adj_help()` 及相关代码
Expected: 方法已删除

**Step 9: 读取 test_init_commands_integration.py**

Run: `Read apps/port/tests/integration/cli/test_init_commands_integration.py`
Expected: 读取文件内容

**Step 10: 删除 test_init_help() 方法**

Edit: `apps/port/tests/integration/cli/test_init_commands_integration.py`
Delete: 删除 `test_init_help()` 及相关代码
Expected: 方法已删除

**Step 11: 验证所有帮助测试已删除**

Run: `grep -r "test_main_help\|test_etf_help\|test_calendar_help\|test_adj_help\|test_init_help" apps/port/tests/integration/cli/ 2>&1 || echo "All help tests removed"`
Expected: 所有帮助测试已删除

---

### Task 1.12: 运行测试验证 Commit 1

**Step 1: 运行单元测试**

Run: `pixi run -e dev test --unit`
Expected: 单元测试通过

**Step 2: 运行集成测试**

Run: `pixi run -e dev test --integration`
Expected: 集成测试通过

**Step 3: 运行类型检查**

Run: `pixi run -e dev type`
Expected: 类型检查通过

**Step 4: 运行代码检查**

Run: `pixi run -e dev lint`
Expected: 代码检查通过

**Step 5: 提交 Commit 1**

Run: `git add -A && git commit -m "test: 命名规范化 + 文件夹整理 + 删除重复测试

- 重命名 20+ 个测试文件，添加 _unit/_integration 后缀
- 重分类 Flow 测试（integration → unit）
- 删除 observability e2e 测试（测试外部服务）
- 删除 QuarantineStore 重复集成测试
- 删除 models/common 重复测试
- 删除 CLI 帮助命令重复测试

预期效果: 删除 ~1600 行重复测试代码"`
Expected: Commit 已创建

---

## Commit 2: 重分类误分类的测试

**目标:** 将过度 Mock 的"集成测试"重分类为单元测试

### Task 2.1: 检查 coordinator_dq_blocking_integration 是否需要重分类

**Files:**
- Check: `apps/port/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py`

**Step 1: 读取文件内容**

Run: `Read apps/port/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py`
Expected: 读取文件内容

**Step 2: 检查 Mock 比例**

检查文件中 Mock 依赖的比例。如果 >80% 依赖都是 Mock，应该重分类为单元测试。

**Step 3: 根据分析结果决定是否重分类**

如果过度 Mock，执行重分类；否则保持不变。

---

### Task 2.2: 运行测试验证 Commit 2

**Step 1: 运行单元测试**

Run: `pixi run -e dev test --unit`
Expected: 单元测试通过

**Step 2: 运行集成测试**

Run: `pixi run -e dev test --integration`
Expected: 集成测试通过

**Step 3: 提交 Commit 2（如果有修改）**

Run: `git add -A && git commit -m "test: 重分类误分类的测试

- 将过度 Mock 的集成测试重分类为单元测试
- 更新 pytest.mark"
Expected: Commit 已创建（如果有修改）

---

## Commit 3: 补充缺失的测试

**目标:** 为无测试覆盖的源码添加测试

### Task 3.1: 创建 Core 包测试结构

**Files:**
- Create: `packages/core/tests/unit/__init__.py`

**Step 1: 创建测试目录**

Run: `mkdir -p packages/core/tests/unit/`
Expected: 目录已创建

**Step 2: 创建 __init__.py**

Run: `touch packages/core/tests/unit/__init__.py`
Expected: 文件已创建

**Step 3: 验证创建**

Run: `ls packages/core/tests/unit/`
Expected: 目录和文件已创建

---

### Task 3.2: 补充 DataHub Bars 测试

**Files:**
- Create: `packages/datahub/tests/unit/accessors/bars/test_accessor_unit.py`
- Create: `packages/datahub/tests/unit/accessors/bars/test_dq_filters_unit.py`

**Step 1: 读取 accessor.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/accessors/bars/accessor.py`
Expected: 读取源码，理解需要测试的功能

**Step 2: 创建 test_accessor_unit.py**

Run: `Write packages/datahub/tests/unit/accessors/bars/test_accessor_unit.py`
Content: 添加单元测试，使用 Mock 所有依赖
Expected: 文件已创建

**Step 3: 读取 dq_filters.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/accessors/bars/dq_filters.py`
Expected: 读取源码

**Step 4: 创建 test_dq_filters_unit.py**

Run: `Write packages/datahub/tests/unit/accessors/bars/test_dq_filters_unit.py`
Content: 添加单元测试
Expected: 文件已创建

---

### Task 3.3: 补充 DataHub Alerts 测试

**Files:**
- Create: `packages/datahub/tests/unit/alerts/test_email_unit.py`
- Create: `packages/datahub/tests/unit/alerts/test_telegram_unit.py`

**Step 1: 读取 email.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/alerts/email.py`
Expected: 读取源码

**Step 2: 创建 test_email_unit.py**

Run: `Write packages/datahub/tests/unit/alerts/test_email_unit.py`
Content: 添加单元测试，Mock HTTP 客户端
Expected: 文件已创建

**Step 3: 读取 telegram.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/alerts/telegram.py`
Expected: 读取源码

**Step 4: 创建 test_telegram_unit.py**

Run: `Write packages/datahub/tests/unit/alerts/test_telegram_unit.py`
Content: 添加单元测试
Expected: 文件已创建

---

### Task 3.4: 补充 DataHub Models 测试

**Files:**
- Create: `packages/datahub/tests/unit/models/test_ingestion_unit.py`
- Create: `packages/datahub/tests/unit/models/test_security_unit.py`
- Create: `packages/datahub/tests/unit/models/test_storage_unit.py`

**Step 1: 读取 ingestion.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/models/ingestion.py`
Expected: 读取源码

**Step 2: 创建 test_ingestion_unit.py**

Run: `Write packages/datahub/tests/unit/models/test_ingestion_unit.py`
Content: 添加单元测试
Expected: 文件已创建

**Step 3: 读取 security.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/models/security.py`
Expected: 读取源码

**Step 4: 创建 test_security_unit.py**

Run: `Write packages/datahub/tests/unit/models/test_security_unit.py`
Content: 添加单元测试
Expected: 文件已创建

**Step 5: 读取 storage.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/models/storage.py`
Expected: 读取源码

**Step 6: 创建 test_storage_unit.py**

Run: `Write packages/datahub/tests/unit/models/test_storage_unit.py`
Content: 添加单元测试
Expected: 文件已创建

---

### Task 3.5: 补充 DataHub Runtime 测试

**Files:**
- Create: `packages/datahub/tests/unit/runtime/test_sid_allocator_unit.py`
- Create: `packages/datahub/tests/unit/runtime/test_sql_engine_unit.py`

**Step 1: 读取 sid_allocator.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/runtime/sid_allocator.py`
Expected: 读取源码

**Step 2: 创建 test_sid_allocator_unit.py**

Run: `Write packages/datahub/tests/unit/runtime/test_sid_allocator_unit.py`
Content: 添加单元测试，包含 SQL 注入防护测试
Expected: 文件已创建

**Step 3: 读取 sql_engine.py 源码**

Run: `Read packages/datahub/src/ditto_datahub/runtime/sql_engine.py`
Expected: 读取源码

**Step 4: 创建 test_sql_engine_unit.py**

Run: `Write packages/datahub/tests/unit/runtime/test_sql_engine_unit.py`
Content: 添加单元测试
Expected: 文件已创建

---

### Task 3.6: 运行测试验证 Commit 3

**Step 1: 运行新增测试**

Run: `pixi run -e dev pytest packages/core/tests/unit/ packages/datahub/tests/unit/ -v`
Expected: 新增测试通过

**Step 2: 运行完整测试套件**

Run: `pixi run -e dev test --unit`
Expected: 单元测试通过

**Step 3: 检查测试覆盖率**

Run: `pixi run -e dev pytest --cov --cov-report=term-missing`
Expected: 覆盖率 >= 80%

**Step 4: 提交 Commit 3**

Run: `git add -A && git commit -m "test: 补充缺失的测试

- 创建 Core 包测试结构
- 补充 DataHub Bars 模块测试（accessor, dq_filters）
- 补充 DataHub Alerts 模块测试（email, telegram）
- 补充 DataHub Models 模块测试（ingestion, security, storage）
- 补充 DataHub Runtime 模块测试（sid_allocator, sql_engine）"
Expected: Commit 已创建

---

## Commit 4: 验证和文档更新

**目标:** 运行完整 CI 检查，确认测试改造成功

### Task 4.1: 运行完整 CI 检查

**Step 1: 运行 lint 检查**

Run: `pixi run -e dev lint`
Expected: 所有检查通过

**Step 2: 运行格式化检查**

Run: `pixi run -e dev fmt --check`
Expected: 格式化检查通过

**Step 3: 运行类型检查**

Run: `pixi run -e dev type --all`
Expected: 类型检查通过

**Step 4: 运行单元测试**

Run: `pixi run -e dev test --unit`
Expected: 单元测试通过

**Step 5: 运行集成测试**

Run: `pixi run -e dev test --integration`
Expected: 集成测试通过

**Step 6: 运行完整 CI**

Run: `pixi run -e dev ci`
Expected: CI 完整通过

---

### Task 4.2: 生成测试报告

**Step 1: 生成覆盖率报告**

Run: `pixi run -e dev pytest --cov --cov-report=html --cov-report=term-missing`
Expected: 覆盖率报告已生成

**Step 2: 查看覆盖率指标**

Run: `cat htmlcov/index.html | grep -o ".*" | head -1`
Expected: 覆盖率 >= 80%

---

### Task 4.3: 更新文档

**Step 1: 检查文档是否需要更新**

Run: `Read .claude/rules/python-test.md`
Expected: 文档已是最新的

**Step 2: 验证实施计划文档已创建**

Run: `ls docs/plans/2026-01-20-test-refactoring-implementation.md`
Expected: 实施计划文档已存在

---

### Task 4.4: 提交 Commit 4

**Step 1: 提交最终验证**

Run: `git add -A && git commit -m "docs: 验证测试改造并更新文档

- 运行完整 CI 检查通过
- 确认测试覆盖率 >= 80%
- 测试架构改造完成

改造效果:
- 测试文件数: ~146 → ~140 (-4%)
- 测试代码行数: ~30000 → ~28400 (-5%)
- 单元测试比例: ~80% → ~85%
- 命名规范符合率: ~85% → 100%"
Expected: Commit 已创建

---

## 回滚计划

如果遇到问题，可以回滚到改造前状态：

```bash
# 回滚单个 commit
git revert HEAD

# 回滚所有测试改造 commits
git revert HEAD~3..HEAD

# 或直接重置到改造前
git reset --hard <commit-hash-before-refactoring>
```

---

## 验证清单

完成测试改造后，确认：

- [ ] 所有测试文件命名符合规范（`_unit` 或 `_integration` 后缀）
- [ ] 无同名测试文件存在于不同测试层级
- [ ] 单元测试完全 Mock，集成测试只测接缝
- [ ] 测试覆盖率 >= 80%
- [ ] 所有测试通过（`pixi run -e dev ci`）
- [ ] 无假测试（assert True、assert False、空 pass）
- [ ] CLI 集成测试只验证函数调用，不验证结果
- [ ] 文件夹结构与源码目录对应
