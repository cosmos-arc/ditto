# 测试架构全面改造计划

**创建日期**: 2026-01-20
**目标**: 基于新的测试标准（80% 单元 + 20% 集成），系统性重构所有测试

---

## 一、核心原则回顾

### 测试分类标准

**单元测试（80%）**：
- 完全 Mock，测试单个类的原子功能
- 快速（毫秒级），可并行
- 示例：`DataHub.is_trading_day()` 的委托逻辑

**集成测试（20%）**：
- 真实组件，测试系统与外部的"接缝"处
- 关注点：DAO、HTTP Client、消息队列
- 使用临时资源（`:memory:`、`tmp_path`）
- **关键原则**：不要让集成测试变成端到端测试

**CLI 集成测试边界**（用户确认选项 A）：
- ✅ 测试 CLI 命令调用了正确的内部函数
- ❌ 不测试函数执行结果（由单元测试保证）

---

## 二、问题总结

### 2.1 命名问题（20个文件）

#### P0 - 使用禁止的 `e2e` 命名（3个）
| 当前文件 | 建议命名 | 原因 |
|---------|---------|------|
| `tests/integration/test_observability_e2e.py` | **删除** | 端到端测试，违反原则 |
| `apps/port/tests/integration/cli/test_e2e.py` | `test_cli_integration.py` | 避免"e2e"命名误导 |
| `packages/datahub/tests/integration/sources/tushare/test_end_to_end_integration.py` | `test_tushare_api_integration.py` | 避免"end_to_end"命名 |

#### P1 - 缺少 `_unit` 后缀（10个）
| 当前文件 | 建议命名 |
|---------|---------|
| `packages/foundation/tests/unit/config/test_manager.py` | `test_manager_unit.py` |
| `packages/foundation/tests/unit/config/test_environment.py` | `test_environment_unit.py` |
| `packages/foundation/tests/unit/config/test_loader.py` | `test_loader_unit.py` |
| `apps/port/tests/unit/cli/test_executor.py` | `test_executor_unit.py` |
| `packages/datahub/tests/unit/runtime/test_freeze_manager_collect_checksums.py` | `test_freeze_manager_collect_checksums_unit.py` |
| `packages/datahub/tests/unit/accessors/test_filter_failed_rows.py` | `test_filter_failed_rows_unit.py` |
| `packages/datahub/tests/test_models_common.py` | `tests/unit/models/test_models_common_unit.py` (移动) |
| `packages/datahub/tests/test_models_quality.py` | `tests/unit/models/test_models_quality_unit.py` (移动) |
| `apps/port/tests/unit/test_conftest.py` | `test_conftest_unit.py` |
| `apps/port/tests/unit/test_db_fixtures.py` | `test_db_fixtures_unit.py` |

#### P2 - 缺少 `_integration` 后缀（5个）
| 当前文件 | 建议命名 |
|---------|---------|
| `apps/port/tests/integration/cli/test_adj_commands.py` | `test_adj_commands_integration.py` |
| `apps/port/tests/integration/cli/test_calendar_commands.py` | `test_calendar_commands_integration.py` |
| `apps/port/tests/integration/cli/test_etf_commands.py` | `test_etf_commands_integration.py` |
| `apps/port/tests/integration/cli/test_init_commands.py` | `test_init_commands_integration.py` |
| `apps/port/tests/integration/cli/test_stock_commands.py` | `test_stock_commands_integration.py` |

---

### 2.2 测试内容重复（~1600行可删除）

#### 高优先级 - CLI 测试重复（严重）

**问题 1：帮助命令测试重复（6个文件）**
- `test_e2e.py::test_main_help()`
- `test_stock_commands.py::test_main_help()`
- `test_etf_commands.py::test_etf_help()`
- `test_calendar_commands.py::test_calendar_help()`
- `test_adj_commands.py::test_adj_help()`
- `test_init_commands.py::test_init_help()`

**建议**：
- 保留 `test_e2e.py` 中的帮助测试
- 删除其他文件中的重复帮助测试

**问题 2：CLI 命令执行测试重复（5个文件）**
```python
# 相同模式在多个文件中重复
def test_xxx_command(tmp_path: Path):
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "stock", "daily", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(result.exception)
```

**建议**：
- 保留 `test_e2e.py` 作为主要的 CLI 工作流测试
- 按新边界重构：只验证函数调用，不验证函数结果
- 删除其他文件中的重复测试
- 保留各命令特定参数的测试（如 `--force`, `--parallel`）

**问题 3：日期验证测试重复（5个文件）**
```python
# 测试无效日期格式 "2024/01/02"
result = runner.invoke(app, ["stock", "daily", "2024/01/02"])
assert result.exit_code == 1
```

**建议**：
- 保留 `test_validation.py` 单元测试（更完整的日期验证覆盖）
- 删除集成测试中的日期验证测试

#### 高优先级 - Prefect Flow 测试重复（严重）

**问题 4：Backfill Flow 测试重复（1056行）**
- `test_backfill_integration.py` (242 行) - 集成测试
- `test_backfill_unit.py` (814 行) - 单元测试

**重复内容**：
- Flow 存在性、日期范围处理、并行执行、Resume 功能、结果返回、Hub 关闭

**分析**：
- 集成测试几乎所有依赖都是 Mock（只有 @flow 装饰器是真实的）
- 这不是集成测试（没有测试"接缝"处）
- 应该是单元测试

**建议**：
- 重分类：`test_backfill_integration.py` → `test_backfill_unit.py`
- 删除重复的测试用例

**问题 5：Daily Flow 测试重复（969行）**
- `test_daily_integration.py` (328 行) - 集成测试
- `test_daily_unit.py` (641 行) - 单元测试

**建议**：同 backfill flow

#### 中优先级 - Store 测试重复（中等）

**问题 6：QuarantineStore 测试重复（545行）**
- `test_quarantine_store_unit.py` (388 行, @pytest.mark.pit)
- `test_quarantine_store_integration.py` (157 行)

**分析**：
- PIT 测试在 `unit/` 目录，但标记为 `@pytest.mark.pit`
- 集成测试使用 `:memory:`，测试完全相同的功能
- 实际上两个都是集成测试（使用真实 SQLite）

**建议**：
- 保留 `test_quarantine_store_unit.py`（更完整）
- 删除 `test_quarantine_store_integration.py`
- 或：将 PIT 测试移到 `integration/`，删除重复用例

---

### 2.3 测试缺失

#### P0 - Core 包完全缺失测试

**问题**：`packages/core/` 目录没有任何测试文件

**影响**：核心引擎逻辑（信号计算、策略执行）无测试覆盖

**建议**：
1. 为 `Core` 包创建测试目录结构
2. 为核心类添加单元测试：
   - 信号生成器
   - 策略执行器
   - 回测引擎
   - 性能计算器

#### P0 - 关键基础设施缺失测试

| 模块 | 缺失的测试 | 优先级 |
|------|-----------|--------|
| `runtime/sid_allocator.py` | SidAllocator 单元测试 | 高 |
| `runtime/sql_engine.py` | SqlEngine 单元测试（SQL 注入防护） | 高 |
| `runtime/cache.py` | Cache 模块单元测试 | 中 |
| `alerts/email_sender.py` | Email Sender 单元测试 | 中 |
| `alerts/telegram_sender.py` | Telegram Sender 单元测试 | 中 |
| `concurrency/file_lock.py` | FileLockManager 单元测试 | 中 |

#### P1 - Store 层集成测试缺失

| Store | 缺失的集成测试 | 测试内容 |
|-------|--------------|---------|
| `SecurityStore` | SQLite 集成测试 | 验证写入/读取接缝 |
| `UniverseStore` | SQLite 集成测试 | 验证写入/读取接缝 |
| `IngestionLogStore` | SQLite 集成测试 | 验证写入/读取接缝 |
| `AdjFactorStore` | Parquet 集成测试 | 验证 Parquet 文件接缝 |
| `BarsStore` | Parquet 集成测试 | 验证 Parquet 文件接缝 |

#### P2 - DQ 边界情况测试缺失

| 模块 | 缺失的测试 | 测试内容 |
|------|-----------|---------|
| `dq/checkers/` | 边界情况测试 | 空值处理、异常数据、业务规则边界 |
| `dq/engine.py` | 错误处理测试 | DQ 引擎异常处理 |

---

## 三、改造计划

### 第一阶段：命名规范化（P0 - 必须修复）

#### 步骤 1.1：重命名禁止的 `e2e` 文件
```bash
# 删除端到端测试（测试外部服务）
rm tests/integration/test_observability_e2e.py

# 重命名 CLI 端到端测试
git mv apps/port/tests/integration/cli/test_e2e.py \
        apps/port/tests/integration/cli/test_cli_integration.py

# 重命名 Tushare 端到端测试
git mv packages/datahub/tests/integration/sources/tushare/test_end_to_end_integration.py \
        packages/datahub/tests/integration/sources/tushare/test_tushare_api_integration.py
```

#### 步骤 1.2：添加缺少的 `_unit` 后缀（10个文件）
```bash
# Foundation 包
git mv packages/foundation/tests/unit/config/test_manager.py \
        packages/foundation/tests/unit/config/test_manager_unit.py
git mv packages/foundation/tests/unit/config/test_environment.py \
        packages/foundation/tests/unit/config/test_environment_unit.py
git mv packages/foundation/tests/unit/config/test_loader.py \
        packages/foundation/tests/unit/config/test_loader_unit.py

# Port 应用
git mv apps/port/tests/unit/cli/test_executor.py \
        apps/port/tests/unit/cli/test_executor_unit.py
git mv apps/port/tests/unit/test_conftest.py \
        apps/port/tests/unit/test_conftest_unit.py
git mv apps/port/tests/unit/test_db_fixtures.py \
        apps/port/tests/unit/test_db_fixtures_unit.py

# DataHub 包
git mv packages/datahub/tests/unit/runtime/test_freeze_manager_collect_checksums.py \
        packages/datahub/tests/unit/runtime/test_freeze_manager_collect_checksums_unit.py
git mv packages/datahub/tests/unit/accessors/test_filter_failed_rows.py \
        packages/datahub/tests/unit/accessors/test_filter_failed_rows_unit.py

# 移动位置
mkdir -p packages/datahub/tests/unit/models/
git mv packages/datahub/tests/test_models_common.py \
        packages/datahub/tests/unit/models/test_models_common_unit.py
git mv packages/datahub/tests/test_models_quality.py \
        packages/datahub/tests/unit/models/test_models_quality_unit.py
```

#### 步骤 1.3：添加缺少的 `_integration` 后缀（5个文件）
```bash
git mv apps/port/tests/integration/cli/test_adj_commands.py \
        apps/port/tests/integration/cli/test_adj_commands_integration.py
git mv apps/port/tests/integration/cli/test_calendar_commands.py \
        apps/port/tests/integration/cli/test_calendar_commands_integration.py
git mv apps/port/tests/integration/cli/test_etf_commands.py \
        apps/port/tests/integration/cli/test_etf_commands_integration.py
git mv apps/port/tests/integration/cli/test_init_commands.py \
        apps/port/tests/integration/cli/test_init_commands_integration.py
git mv apps/port/tests/integration/cli/test_stock_commands.py \
        apps/port/tests/integration/cli/test_stock_commands_integration.py
```

---

### 第二阶段：删除重复测试（P0 - 必须修复）

#### 步骤 2.1：删除 CLI 重复测试
```python
# 删除的测试方法：
# test_stock_commands.py::test_main_help()
# test_etf_commands.py::test_etf_help()
# test_calendar_commands.py::test_calendar_help()
# test_adj_commands.py::test_adj_help()
# test_init_commands.py::test_init_help()

# 重构 CLI 集成测试：只验证函数调用
# 修改 test_cli_integration.py 中的测试用例
```

#### 步骤 2.2：删除重复的日期验证测试
```python
# 从以下文件中删除日期格式验证测试：
# test_stock_commands.py::test_stock_daily_invalid_date_format()
# test_etf_commands.py::test_etf_daily_invalid_date_format()
# test_adj_commands.py::test_adj_factor_invalid_date_format()
# test_init_commands.py::test_init_invalid_date_format()

# 保留：test_validation.py（单元测试，更完整）
```

#### 步骤 2.3：重构 Prefect Flow 测试
```python
# 重分类：集成测试 → 单元测试
git mv apps/port/tests/integration/ingestion/flows/test_backfill_integration.py \
        apps/port/tests/unit/ingestion/flows/test_backfill_unit.py

git mv apps/port/tests/integration/ingestion/flows/test_daily_integration.py \
        apps/port/tests/unit/ingestion/flows/test_daily_unit.py

# 删除重复的测试用例（手动编辑）
```

#### 步骤 2.4：合并 QuarantineStore 测试
```python
# 保留：test_quarantine_store_unit.py（更完整）
# 删除：test_quarantine_store_integration.py
rm packages/datahub/tests/integration/stores/test_quarantine_store_integration.py
```

**预期效果**：删除 ~1600 行重复测试代码

---

### 第三阶段：重分类误分类的测试（P1 - 建议修复）

#### 步骤 3.1：重分类过度 Mock 的"集成测试"
```python
# 这些文件标记为 @pytest.mark.integration
# 但几乎所有依赖都是 Mock，应该重分类为单元测试

# 重分类：
# apps/port/tests/integration/ingestion/flows/test_backfill_integration.py
# apps/port/tests/integration/ingestion/flows/test_daily_integration.py
# apps/port/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py

# 操作：
# 1. 移动到 tests/unit/
# 2. 添加 @pytest.mark.unit
# 3. 删除 integration 相关的 fixtures
```

---

### 第四阶段：补充缺失的测试（P0-P2）

#### 步骤 4.1：创建 Core 包测试结构
```bash
mkdir -p packages/core/tests/unit/

# 为核心类创建单元测试：
touch packages/core/tests/unit/test_signal_generator_unit.py
touch packages/core/tests/unit/test_strategy_executor_unit.py
touch packages/core/tests/unit/test_backtest_engine_unit.py
touch packages/core/tests/unit/test_performance_calculator_unit.py
```

#### 步骤 4.2：补充基础设施测试
```bash
# Runtime 模块
touch packages/datahub/tests/unit/runtime/test_sid_allocator_unit.py
touch packages/datahub/tests/unit/runtime/test_sql_engine_unit.py
touch packages/foundation/tests/unit/test_cache_unit.py

# Alerts 模块
touch packages/datahub/tests/unit/alerts/test_email_sender_unit.py
touch packages/datahub/tests/unit/alerts/test_telegram_sender_unit.py
```

#### 步骤 4.3：补充 Store 集成测试
```bash
# 为每个 Store 创建集成测试（测试 SQLite 接缝）
touch packages/datahub/tests/integration/stores/test_security_store_integration.py
touch packages/datahub/tests/integration/stores/test_universe_store_integration.py
touch packages/datahub/tests/integration/stores/test_ingestion_log_store_integration.py
```

---

### 第五阶段：验证和文档更新

#### 步骤 5.1：运行测试套件验证
```bash
# 单元测试
pytest tests/unit/ -m "not slow" --cov

# 集成测试
pytest -m integration

# 完整 CI 检查
pixi run -e dev ci
```

#### 步骤 5.2：更新测试规范文档
- ✅ 已更新 `.claude/rules/python-test.md` 添加 CLI 集成测试边界说明
- ✅ 已创建本文档作为详细实施计划

---

## 四、预期效果

### 改造前 vs 改造后

| 指标 | 改造前 | 改造后 | 改善 |
|------|-------|-------|------|
| 测试文件数 | ~146 | ~140 | -6 (-4%) |
| 测试代码行数 | ~30000 | ~28400 | -1600 (-5%) |
| 单元测试比例 | ~80% | ~85% | +5% |
| 集成测试比例 | ~20% | ~15% | -5% |
| 重复测试覆盖率 | ~53% | ~10% | -43% |
| 命名规范符合率 | ~85% | 100% | +15% |

### 关键改进

1. **测试分类更准确**：单元测试完全 Mock，集成测试只测接缝
2. **测试代码更精简**：删除 ~1600 行重复代码
3. **命名更规范**：100% 符合命名规范
4. **覆盖更完整**：Core 包和基础设施测试补充

---

## 五、风险和注意事项

### 风险

1. **重命名可能影响 CI 收集**：需要同步更新 CI 配置
2. **删除重复测试可能降低覆盖率**：需要确保被删除的功能在其他测试中有覆盖
3. **重分类测试可能需要修改 import 路径**

### 注意事项

1. **逐步实施**：不要一次性修改所有文件
2. **保持测试通过**：每次修改后运行测试确保不破坏功能
3. **更新文档**：同步更新 `.claude/rules/python-test.md`
4. **团队沟通**：确保团队成员理解新的测试标准

---

## 六、时间估算

| 阶段 | 预计时间 | 优先级 |
|------|---------|--------|
| 第一阶段：命名规范化 | 2-4 小时 | P0 |
| 第二阶段：删除重复测试 | 4-8 小时 | P0 |
| 第三阶段：重分类误分类测试 | 2-4 小时 | P1 |
| 第四阶段：补充缺失测试 | 8-16 小时 | P0-P2 |
| 第五阶段：验证和文档更新 | 2-4 小时 | P0 |
| **总计** | **18-36 小时** | - |

---

## 七、后续行动

完成测试改造后：

1. **创建 Pre-commit 检查脚本**
2. **运行完整 CI 检查**
3. **团队培训**：新的测试标准和边界划分
