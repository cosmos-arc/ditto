# Code Review 修复计划

## 概述
- 创建: 2026-04-04
- 来源: PR #61 Code Review (7 个问题, 评分 >= 25)

## 问题清单

| # | 评分 | 问题 | 类别 |
|---|------|------|------|
| 1 | 100 | Engine 层执行 I/O 并依赖 Infra | 架构违规 |
| 2 | 100 | CI `--cov=apps` 引用已删除目录 | CI 陈旧路径 |
| 3 | 90 | E2E 报告路径不匹配 | CI 路径错误 |
| 4 | 90 | Data→Analytics 依赖违规 + importlinter 缺失 | 架构违规 |
| 5 | 75 | TYPE_CHECKING 使用（5 文件，均无循环依赖） | 代码风格 |
| 6 | 75 | App 测试导入 Interfaces 层 | 架构违规 |
| 7 | 25 | "Core 层" 陈旧 docstring（16 处） | 文档 |

## 任务清单

### Task 1: 修复 CI 陈旧路径 `[M]`

**问题**: ci.yml 多处引用已删除的 `apps/`、`packages/datahub/`、`packages/core/`、`packages/foundation/`

**修改文件**:
- `.github/workflows/ci.yml`
- `.github/workflows/e2e-validation.yml`
- `codecov.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`

**具体变更**:

ci.yml:
- L6: 注释 `apps/*` → `interfaces/*`
- L149: `packages/datahub/tests/unit/` → `packages/data/tests/unit/`，`--cov=packages` 不变
- L163: `--cov=apps` → `--cov=interfaces`
- L209-211: build step 重写为当前 6 个包 (`infra`, `kernel`, `data`, `analytics`, `engine`, `app`)

e2e-validation.yml:
- L62: `--junit-xml=interfaces/tests/reports/e2e-junit.xml` ✅ 已正确
- L70-71, L80: 路径已是 `interfaces/tests/reports/` ✅ 已正确

codecov.yml:
- L29: `packages/datahub/src/` → `packages/data/src/`，名称 `datahub:` → `data:`

PULL_REQUEST_TEMPLATE.md:
- L19: `packages/datahub` → `packages/data`

**验收**: `pixi run -e dev check` 通过，CI 配置无陈旧路径引用

---

### Task 2: 修复 E2E 报告路径不匹配 `[S]`

**问题**: conftest.py 写入 `tests/reports/`，CI 从 `interfaces/tests/reports/` 读取

**修改文件**:
- `interfaces/tests/e2e/conftest.py` L363

**具体变更**:
```python
# Before:
output_path = Path(f"tests/reports/e2e_validation_{date.today():%Y%m%d}.md")
# After:
output_path = Path(f"interfaces/tests/reports/e2e_validation_{date.today():%Y%m%d}.md")
```
同时更新 L353 的 docstring 描述。

**验收**: conftest 报告路径与 e2e-validation.yml 的 artifact 路径一致

---

### Task 3: 将 serialization.py 从 Engine 迁移到 App `[M]`

**问题**: Engine 层执行 I/O（文件写入）并依赖 `ditto_infra`，违反 "纯业务逻辑，无 I/O" 原则

**方案**: 移至 App 层（唯一生产消费者已在 App 层 `process/strategy.py`）

**具体步骤**:
1. 将 `packages/engine/src/ditto_engine/backtest/serialization.py` → `packages/app/src/ditto_app/process/backtest_serialization.py`
2. 更新 `packages/app/src/ditto_app/process/strategy.py` L53 的 import:
   `from ditto_engine.backtest.serialization` → `from ditto_app.process.backtest_serialization`
3. 移动测试: `packages/engine/tests/unit/backtest/test_serialization_unit.py` → `packages/app/tests/unit/process/test_backtest_serialization_unit.py`
4. 更新 Engine CLAUDE.md 和 AGENTS.md 中对 `BacktestReportSerializer` 的引用

**验收**: `ditto_engine` 不再 import `ditto_infra`，`arch-check` 通过

---

### Task 4: 解决 Data→Analytics 依赖违规 `[L]`（拆为 4 个子任务）

#### Task 4a: 将 research.py 迁移至 Kernel `[M]`

**前提验证**: `research.py` 满足 Kernel 准入 5 条标准:
1. ✅ 跨层使用: ditto_data + ditto_app + ditto_analytics (3 包)
2. ✅ 零业务行为: 4 个 frozen dataclass，无方法
3. ✅ 稳定性高: 研究记录结构不会频繁变更
4. ✅ 无外部依赖: 仅 `dataclasses` + `typing`
5. ✅ 纯值语义: 无序列化、持久化关注点

**具体步骤**:
1. 复制 `packages/analytics/src/ditto_analytics/models/research.py` → `packages/kernel/src/ditto_kernel/research.py`
2. 更新 `packages/kernel/src/ditto_kernel/__init__.py` 的 `__all__` 导出
3. 更新 `packages/analytics/src/ditto_analytics/models/__init__.py` 改为从 kernel re-export
4. 更新 Data 层消费者（改为从 kernel 导入）:
   - `packages/data/src/ditto_data/services/research_catalog_service.py`
   - `packages/data/src/ditto_data/storage/runtime/research_sqlite/reader.py`
   - `packages/data/src/ditto_data/storage/runtime/research_sqlite/writer.py`
5. 更新 App 层消费者:
   - `packages/app/src/ditto_app/query/research.py`
6. 更新测试文件的 import
7. 更新 Kernel CLAUDE.md 类型清单

**验收**: data 层不再直接 import ditto_analytics 的 research 模型

#### Task 4b: 删除 data/models 死代码 re-export `[S]`

**问题**: `ditto_data/models/__init__.py` re-export factors/features 但零消费者

**具体步骤**:
1. 从 `packages/data/src/ditto_data/models/__init__.py` 删除 L4-25 的 factors/features re-export
2. Grep 确认无消费者受影响

**验收**: `ditto_data.models` 不再 import `ditto_analytics.models.factors/features`

#### Task 4c: 迁移 compile_cache DI Provider 到 App `[S]`

**问题**: `packages/data/src/ditto_data/di/derived.py` 实例化 Analytics 层的 `SQLiteCompileCache`

**具体步骤**:
1. 从 `packages/data/src/ditto_data/di/derived.py` 删除 `compile_cache_service` 方法和 `SQLiteCompileCache` import
2. 确认 `packages/app/src/ditto_app/providers.py` 已有该注册（L19 已确认存在）

**验收**: ditto_data 不再 import ditto_analytics.compile_cache

#### Task 4d: 更新 importlinter 配置 `[S]`

**具体变更**:
`.importlinter` L76-84 `data-boundary` contract:
```ini
[importlinter:contract:data-boundary]
name = Data must not depend on Engine/Interfaces/App/Analytics
type = forbidden
source_modules =
    ditto_data.**
forbidden_modules =
    ditto_engine.**
    ditto_interfaces.**
    ditto_app.**
    ditto_analytics.**
```

**验收**: `pixi run -e dev arch-check` 通过

---

### Task 5: 移除 5 个文件中不必要的 TYPE_CHECKING `[M]`

**问题**: 5 个源文件使用 TYPE_CHECKING 但均无循环依赖（均为不必要的延迟导入）

**逐文件修复**:

| 文件 | 变更 |
|------|------|
| `packages/data/src/ditto_data/query/market.py` | 删 TYPE_CHECKING block，合并到已有 `MarketService` import |
| `packages/data/src/ditto_data/query/metadata.py` | 删 TYPE_CHECKING block，添加正常 `MetadataService` import |
| `packages/data/src/ditto_data/query/provider.py` | 删 TYPE_CHECKING block，添加 3 个正常 import |
| `packages/engine/src/ditto_engine/backtest/data_feed.py` | 删 TYPE_CHECKING block，合并到已有 `from ditto_data.provider` import |
| `packages/engine/src/ditto_engine/risk/post_trade.py` | 删 TYPE_CHECKING block，添加正常 `Slice` import |

**验收**: 5 个文件中无 `TYPE_CHECKING` 引用，所有 import 正常解析

---

### Task 6: 修复 App 测试→Interfaces 导入 `[S]`

**问题**: `packages/app/tests/unit/test_providers_unit.py` L43 导入 `ConfigProvider` from Interfaces

**方案**: 在测试文件中创建本地 mock Provider 替代（Option C — 最小侵入）

**具体步骤**:
1. 删除 `from ditto_interfaces.registry.infra import ConfigProvider`
2. 在测试文件中添加 `_TestConfigProvider` 类，提供 App Provider 所需的最小依赖集:
   - `Environment` → `TESTING`
   - `DataStoreSettings` / `DataSourceSettings` 等测试默认值
3. 替换 L158 的 `ConfigProvider()` 为 `_TestConfigProvider()`

**验收**: `ditto_app` 测试不再 import `ditto_interfaces`

---

### Task 7: 修复陈旧 "Core 层" docstring `[S]`

**问题**: 16 处 "Core 层" 应为 "Engine 层"（ditto_kernel → ditto_engine 重命名遗留）

**修改文件** (10 个):
- `packages/engine/src/ditto_engine/execution/rules.py` (2 处)
- `packages/engine/src/ditto_engine/alpha/README.md` (1 处)
- `packages/data/README.md` (1 处)
- `packages/data/src/ditto_data/models/ingestion.py` (1 处)
- `packages/data/src/ditto_data/quality/checkers/cross_source.py` (2 处)
- `packages/data/src/ditto_data/di/quality.py` (3 处)
- `packages/data/src/ditto_data/di/golden.py` (1 处)
- `packages/data/src/ditto_data/services/__init__.py` (1 处)
- `packages/data/src/ditto_data/storage/runtime/quality/comparison_reader.py` (1 处)
- `packages/data/src/ditto_data/storage/runtime/quality/comparison_writer.py` (1 处)
- `packages/app/src/ditto_app/process/quality.py` (2 处)

**验收**: `grep -r "Core 层" packages/` 返回 0 结果

---

## 完成状态

**全部完成** (2026-04-05)

- [x] Phase A: Task 1, 2, 5, 7
- [x] Phase B: Task 4a, 4b, 4c
- [x] Phase C: Task 3, 4d, 6
- [x] 最终验证: lint ✅ type ✅ test (4358 passed) ✅ arch-check (22/22) ✅

**注意事项**:
- Task 5: `post_trade.py` 的 `Slice` 导入保留 TYPE_CHECKING（移除会导致 engine 内部循环依赖 risk→backtest）
- Task 6: `_TestConfigProvider` 需提供 `DataCache[Any]`（非 `DataCache[object]`）以匹配 dishka 泛型解析
- Task 4d: importlinter 新增 `ditto_analytics.**` 到 data-boundary forbidden_modules

---

## 执行顺序

```
Phase A（独立并行）:
  Task 1: CI 陈旧路径修复
  Task 2: E2E 路径修复
  Task 5: TYPE_CHECKING 移除
  Task 7: "Core 层" docstring 修复

Phase B（依赖 Phase A 中 arch-check）:
  Task 4a: research.py → kernel
  Task 4b: 删除 data/models 死代码
  Task 4c: compile_cache DI → app

Phase C（依赖 Phase B）:
  Task 3: serialization.py → app
  Task 4d: 更新 importlinter
  Task 6: App 测试 mock provider

最终验证:
  pixi run -e dev check
  pixi run -e dev arch-check
```

## 风险评估

| 风险 | 缓解措施 |
|------|----------|
| Task 4a: research 迁移可能遗漏消费者 | 全局 grep 确认后再修改 |
| Task 6: mock provider 可能遗漏依赖 | 运行测试验证容器解析 |
| Task 3: 测试文件移动可能破坏测试路径 | 移动后立即运行 pytest 验证 |
