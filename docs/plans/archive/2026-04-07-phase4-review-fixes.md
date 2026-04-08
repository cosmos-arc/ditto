# Phase 4 代码审查修复计划

> **Status:** COMPLETED (2026-04-07)
>
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 Phase 4 代码审查发现的全部问题（archive 文档除外），使代码完全符合项目规范。

**Architecture:** 按影响范围分 6 个 Part：架构文档 → 生产 noqa 清零 → 架构代码修正 → 规约合规 → 文档路径更新 → 代码规模。每个 Part 内任务可并行。

**Tech Stack:** Python 3.13, basedpyright, ruff, importlinter

**完成验证:**
- `pixi run -e dev check` → lint clean, type 0 errors, 4379 passed, 0 failed
- `pixi run -e dev arch-check` → 23 contracts kept, 0 broken
- `# noqa` 仅剩 2 个合理使用 (UP047 TypeGuard, PLC0415 circular import)
- 所有源文件 < 1000 行

---

## Part 1: 架构文档修正（3 tasks，均为 S）

### Task 1: 修正 architecture.md 依赖方向图

**Files:**
- Modify: `.claude/rules/architecture.md:70-83`

**问题:**
1. 第 72 行 `ditto_interfaces → ditto_analytics → ditto_engine → ditto_kernel` 错误 — analytics 与 engine 互相隔离
2. 第 76 行遗漏 `analytics → infra (logger)` 合法依赖
3. 第 74 行 `ditto_app → ditto_infra` 需补充范围说明

**Step 1: 修改依赖规则块**

将第 70-83 行替换为：

```
ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra
ditto_interfaces → ditto_analytics → ditto_kernel
ditto_interfaces → ditto_data → ditto_kernel, ditto_infra
ditto_app → ditto_engine, ditto_data, ditto_analytics, ditto_kernel, ditto_infra
ditto_engine      → ditto_kernel                                            ✅
ditto_analytics   → ditto_kernel, ditto_data.errors, ditto_infra.foundation ✅
ditto_data        → ditto_kernel, ditto_infra                              ✅
ditto_kernel      → (无业务依赖)                                             ✅
ditto_infra       → (无业务依赖)                                             ✅
ditto_engine      → ditto_data (仅 errors/provider)                        ❌ (beyond)
ditto_data        → ditto_engine                                            ❌
ditto_data        → ditto_interfaces                                        ❌
ditto_infra       → 其他层                                                  ❌
```

**Step 2: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过

**Step 3: Commit**

```bash
git add .claude/rules/architecture.md
git commit -m "fix: 修正 architecture.md 依赖方向图 — analytics 与 engine 隔离，补充 infra 依赖"
```

---

### Task 2: 修正 noqa-ignore.md 旧路径

**Files:**
- Modify: `.claude/rules/noqa-ignore.md:10,213,216`

**问题:** 3 处引用已删除的 `interfaces/` 和 `apps/*/` 路径。

**Step 1: 替换旧路径**

第 10 行：
```
旧: packages/**/src 和 interfaces/**/src
新: packages/**/src 和 interfaces/**/src
```

第 213 行：
```
旧: git grep "# noqa" packages/*/src apps/*/src
新: git grep "# noqa" packages/*/src interfaces/*/src
```

第 216 行：
```
旧: git grep "# type: ignore" packages/*/src apps/*/src
新: git grep "# type: ignore" packages/*/src interfaces/*/src
```

第 219 行（如存在）：
```
旧: git grep "^global " packages/*/src apps/*/src
新: git grep "^global " packages/*/src interfaces/*/src
```

**Step 2: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过

**Step 3: Commit**

```bash
git add .claude/rules/noqa-ignore.md
git commit -m "fix: 更新 noqa-ignore.md 路径 — apps/port → interfaces"
```

---

### Task 3: 修正 kernel CLAUDE.md 枚举值描述

**Files:**
- Modify: `packages/kernel/CLAUDE.md:68-70`

**问题:** DerivedRole 文档写 `FACTOR/FEATURE/COMPOSITE`，实际为 `FEATURE/FACTOR/SIGNAL/LABEL`。MaterializationProfile 文档写 `SERIES/STATE`，实际为 `SERIES/STATE/DERIVE/OFFLINE`。

**Step 1: 修正枚举值**

第 68 行附近：
```
旧: StrEnum（FACTOR/FEATURE/COMPOSITE）
新: StrEnum（FEATURE/FACTOR/SIGNAL/LABEL）
```

第 70 行附近：
```
旧: StrEnum（SERIES/STATE）
新: StrEnum（SERIES/STATE/DERIVE/OFFLINE）
```

**Step 2: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过

**Step 3: Commit**

```bash
git add packages/kernel/CLAUDE.md
git commit -m "fix: 同步 kernel CLAUDE.md 枚举值与 specs.py 代码定义"
```

---

## Part 2: 生产代码 noqa 清零（5 tasks）

### Task 4: 消除 S101 assert — 改为显式检查

**Files:**
- Modify: `packages/app/src/ditto_app/process/quality.py:182`
- Modify: `packages/infra/src/ditto_infra/foundation/cache/core.py:139,140,204,205`

**问题:** 生产代码中使用 `assert` + `# noqa: S101`，assert 在 `-O` 模式下会被跳过。

**Step 1: 修复 quality.py:182**

```python
# 旧:
assert self._quarantine_writer is not None  # noqa: S101  # guarded by _quarantine_data

# 新:
if self._quarantine_writer is None:
    raise RuntimeError("quarantine_writer 未初始化，需先调用 _quarantine_data")
```

**Step 2: 修复 cache/core.py 的 4 处 assert**

读取文件确认上下文，将每处 `assert self._xxx is not None` 替换为：
```python
if self._xxx is None:
    raise RuntimeError("xxx 未初始化")
```

**Step 3: 更新对应测试**

如果测试中有 `with pytest.raises(AssertionError)` 的用例，需改为 `pytest.raises(RuntimeError)`。

**Step 4: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过，S101 noqa 数量为 0

**Step 5: Commit**

```bash
git add packages/app/src/ditto_app/process/quality.py packages/infra/src/ditto_infra/foundation/cache/core.py
git commit -m "fix: 消除生产代码 S101 assert — 改为显式 RuntimeError 检查"
```

---

### Task 5: 消除 PLC0415 — errors.py httpx 延迟导入

**Files:**
- Modify: `packages/data/src/ditto_data/errors.py:417,615`

**问题:** 2 处 `import httpx  # noqa: PLC0415` 缺少原因注释。PLC0415 不在 noqa-ignore.md 允许列表中。

**Step 1: 评估方案**

检查 `ditto_data` 的 `pyproject.toml` 确认 httpx 是否为必需依赖。如果是：
- **方案 A（推荐）**：将 httpx 移到模块顶层 import
- **方案 B**：如果 errors.py 有意保持零 import，则将 PLC0415 加入 noqa-ignore.md 允许列表并补充注释

**Step 2: 实施修复**

方案 A（httpx 是必需依赖时）：
```python
# 在 errors.py 顶部添加
import httpx

# 删除第 417 行和第 615 行的延迟导入
```

方案 B（需要保持零 import 时）：
```python
import httpx  # noqa: PLC0415  # 可选依赖延迟加载，避免模块加载时引入 httpx
```
并在 noqa-ignore.md 第 24 行添加 PLC0415 到允许列表（需注释原因）。

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/errors.py
git commit -m "fix: 消除 errors.py PLC0415 noqa — 将 httpx 移至顶层导入"
```

---

### Task 6: 消除 E501 — 行过长修复

**Files:**
- Modify: `packages/data/src/ditto_data/storage/metadata/instrument/instrument_reader.py:66`
- Modify: `packages/data/src/ditto_data/services/market_service.py:267,405`
- Modify: `interfaces/src/ditto_interfaces/jobs/context.py:58`

**问题:** 4 处 `# noqa: E501`，行长度超过 88 字符。E501 不在允许的 noqa 列表中。

**Step 1: 修复 instrument_reader.py:66**

将过长的 docstring 注释拆分为多行。

**Step 2: 修复 market_service.py:267**

```python
# 旧（单行）:
"IndexConstituentReader not configured. Please provide index_constituent when initializing MarketReadPorts.",

# 新（提取为变量）:
msg = (
    "IndexConstituentReader not configured. "
    "Please provide index_constituent when initializing MarketReadPorts."
)
raise ValueError(msg)
```

**Step 3: 修复 market_service.py:405**

```python
# 旧:
f"显式指定的资产类别 '{asset_class}' 与从 Instrument ID 检测出的类别 '{detected}' 不一致"

# 新:
f"显式指定的资产类别 '{asset_class}' 与从 Instrument ID 检测出的类别 '{detected}' 不一致"
# → 拆分为:
msg = (
    f"显式指定的资产类别 '{asset_class}' 与从 Instrument ID "
    f"检测出的类别 '{detected}' 不一致"
)
```

**Step 4: 修复 context.py:58**

将过长的 `with` 语句拆分。

**Step 5: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过

**Step 6: Commit**

```bash
git add packages/data/src/ditto_data/storage/metadata/instrument/instrument_reader.py packages/data/src/ditto_data/services/market_service.py interfaces/src/ditto_interfaces/jobs/context.py
git commit -m "fix: 消除生产代码 E501 noqa — 拆分过长行"
```

---

### Task 7: 消除 PLR0913 — app + data 层参数过多

**Files:**
- Modify: `packages/app/src/ditto_app/process/coordinator_factory.py:38`
- Modify: `packages/app/src/ditto_app/process/backfill_handler.py:17`
- Modify: `packages/data/src/ditto_data/di/market.py:190,220`
- Modify: `packages/data/src/ditto_data/di/metadata.py:190`
- Modify: `packages/data/src/ditto_data/services/metadata/instrument.py:46,149`

**问题:** 7 处函数参数 > 7 个，违反 core.md 参数个数 ≤ 7 规范。

**Step 1: 分析每处参数特征**

对每个函数，判断参数类型：
- **DI Provider 方法**（market.py, metadata.py）：参数是 Dishka 注入的依赖。→ 创建 `@dataclass(frozen=True)` 配置类聚合相关依赖
- **Service 方法**（instrument.py）：参数是查询/业务参数。→ 创建 `@dataclass(frozen=True)` 查询参数类
- **App 层函数**（coordinator_factory.py, backfill_handler.py）：混合依赖和业务参数。→ 拆分为配置对象 + 业务参数

**Step 2: 实施修复（每处独立 commit）**

对每个文件：
1. 读取函数签名和所有参数
2. 设计合适的 dataclass（放在同文件或 `models/` 中）
3. 修改函数签名使用 dataclass
4. 更新所有调用点
5. 运行测试确认无回归

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: PLR0913 noqa 在 packages/*/src 中为 0

**Step 4: Commit**

```bash
git add -u
git commit -m "refactor: 消除 app/data 层 PLR0913 noqa — 提取参数为 dataclass"
```

---

### Task 8: 消除 PLR0913 — interfaces 层参数过多

**Files:**
- Modify: `interfaces/src/ditto_interfaces/cli/commands/factory.py:25,73`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ingest/market.py:59`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ingest/_shared.py:11`
- Modify: `interfaces/src/ditto_interfaces/api/routes/source.py:38`

**问题:** 5 处函数参数 > 7 个。

**Step 1: 分析**

CLI 命令和 API 路由的参数通常是框架注入的选项/路径参数。对这类场景：
- CLI 命令（typer）：将相关选项分组为 `typer.Option` callback 或使用 `Annotated` 类型
- API 路由（FastAPI）：将查询参数分组为 Pydantic model（`Depends()` 注入）

**Step 2: 实施修复**

逐文件修改，使用框架推荐的参数分组模式。

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: PLR0913 noqa 在 interfaces/src 中为 0

**Step 4: Commit**

```bash
git add interfaces/
git commit -m "refactor: 消除 interfaces 层 PLR0913 noqa — 分组 CLI/API 参数"
```

---

### Task 9: 消除 C901/PLR0911/PLR0912 — 复杂度超标

**Files:**
- Modify: `packages/data/src/ditto_data/sources/tushare/adapters/macro.py:130` — C901 + PLR0912
- Modify: `packages/data/src/ditto_data/services/market_service.py:300` — PLR0911
- Modify: `interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py:22` — C901

**Step 1: 修复 macro.py fetch_indicators**

将长方法拆分为多个私有方法（如 `_fetch_gdp_indicators`、`_fetch_cpi_indicators` 等）。

**Step 2: 修复 market_service.py _load_bars_core**

将多个 return 语句重构为提前返回或策略模式。

**Step 3: 修复 dq_batch.py dq_batch_check**

将端到端流程拆分为 `_validate_config`、`_execute_checks`、`_report_results` 等子步骤。

**Step 4: 验证**

Run: `pixi run -e dev check`
Expected: C901/PLR0911/PLR0912 noqa 在生产代码中为 0

**Step 5: Commit**

```bash
git add -u
git commit -m "refactor: 消除生产代码 C901/PLR0911/PLR0912 noqa — 拆分复杂函数"
```

---

## Part 3: 架构代码修正（3 tasks）

### Task 10: App 层移除对 data.storage 的直接依赖

**Files:**
- Modify: `packages/app/src/ditto_app/providers.py:52`
- Modify: `packages/data/src/ditto_data/di/` (新增或修改 Provider)

**问题:** `providers.py:52` 直接导入 `ditto_data.storage.sqlite_client.SQLiteClient`，绕过 data 层封装。

**Step 1: 检查 SQLiteClient 在 providers.py 中的使用方式**

读取 `providers.py` 中所有使用 `SQLiteClient` 的位置，确认用途。

**Step 2: 在 data.di 中注册 SQLiteClient**

在 `packages/data/src/ditto_data/di/` 的适当 Provider 中注册 `SQLiteClient`。

**Step 3: 修改 providers.py**

将 `from ditto_data.storage.sqlite_client import SQLiteClient` 删除，改为通过 DI 容器注入。

**Step 4: 验证**

Run: `pixi run -e dev check && pixi run -e dev arch-check`
Expected: 全部通过

**Step 5: Commit**

```bash
git add packages/app/src/ditto_app/providers.py packages/data/src/ditto_data/di/
git commit -m "fix: app 层移除对 data.storage 的直接依赖 — 通过 DI 注入 SQLiteClient"
```

---

### Task 11: 补充 importlinter 合约约束

**Files:**
- Modify: `.importlinter`

**问题:** 缺少 `app → infra` 和 `app → analytics` 的范围约束合约。

**Step 1: 添加合约**

在 `.importlinter` 中添加：

```ini
[[contracts]]
name = "app-infra-scope"
type = "forbidden"
source_modules = ["ditto_app"]
forbidden_modules = ["ditto_infra.services", "ditto_infra.config"]
ignore_imports = [
    "ditto_app.** -> ditto_infra.foundation",
]
```

```ini
[[contracts]]
name = "app-analytics-scope"
type = "forbidden"
source_modules = ["ditto_app"]
forbidden_modules = []
# app → analytics 已被 app CLAUDE.md 认可，此处仅记录允许范围
# 如果未来需要收紧，在此添加 forbidden_modules
ignore_imports = []
```

**注意:** 第二个合约可能为空（因为 app → analytics 已被文档认可）。根据实际需求决定是否添加。

**Step 2: 验证**

Run: `pixi run -e dev arch-check`
Expected: 22+ kept, 0 broken

**Step 3: Commit**

```bash
git add .importlinter
git commit -m "feat: 补充 importlinter 合约 — app-infra-scope 范围约束"
```

---

### Task 12: 重命名 types.py → _reexports.py

**Files:**
- Rename: `packages/app/src/ditto_app/types.py` → `packages/app/src/ditto_app/_reexports.py`
- Modify: `packages/app/CLAUDE.md` (模块结构图)
- Modify: 12 个 import 站点

**问题:** core.md 第 187 行规定"取消顶层 types.py：避免与 Python 内置 types 模块混淆"。

**受影响的 import 站点（12 处）：**

| 文件 | 行号 |
|------|------|
| `interfaces/src/ditto_interfaces/models/__init__.py` | 26 |
| `interfaces/src/ditto_interfaces/models/macro.py` | 17 |
| `interfaces/src/ditto_interfaces/api/utils/identifier.py` | 8 |
| `interfaces/src/ditto_interfaces/jobs/tasks/t0_meta.py` | 13 |
| `interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py` | 8 |
| `interfaces/src/ditto_interfaces/jobs/tasks/monitoring.py` | 7 |
| `interfaces/src/ditto_interfaces/jobs/context.py` | 19 |
| `interfaces/src/ditto_interfaces/jobs/flows/daily.py` | 28 |
| `interfaces/src/ditto_interfaces/jobs/flows/backfill.py` | 14 |
| `interfaces/src/ditto_interfaces/cli/executor.py` | 18 |
| `interfaces/tests/unit/api/utils/test_identifier_unit.py` | 6 |
| `interfaces/tests/unit/api/routes/test_fundamental_identifier_query_unit.py` | 14 |
| `interfaces/tests/unit/api/routes/test_capital_identifier_query_unit.py` | 14 |

**Step 1: 执行批量替换**

```bash
# 重命名文件
git mv packages/app/src/ditto_app/types.py packages/app/src/ditto_app/_reexports.py

# 批量替换 import
find interfaces/ -name '*.py' -exec sed -i 's/from ditto_app\.types import/from ditto_app._reexports import/g' {} +
```

**Step 2: 更新 app/CLAUDE.md 模块结构**

将 `types.py` 改为 `_reexports.py`。

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: 全部通过

**Step 4: Commit**

```bash
git add -u
git commit -m "refactor: 重命名 app/types.py → _reexports.py — 避免与内置 types 模块混淆"
```

---

## Part 4: 规约合规（2 tasks）

### Task 13: 统一 docstring 语言为中文

**Files:**
- Modify: `packages/app/src/ditto_app/process/quality.py:73-92`
- Modify: `packages/app/src/ditto_app/providers.py:114`

**问题:** 部分函数 docstring 使用英文，与 core.md "中文 docstring" 规范不一致。

**Step 1: 修复 quality.py**

```python
# 旧:
"""Quality service for write-time DQ checks.

Application Layer: Orchestrates L1/L2 checks during data ingestion.
Handles quarantine logic and metrics/logging.
"""

# 新:
"""写入时数据质量检查服务.

应用层：在数据摄取过程中编排 L1/L2 检查。
处理隔离逻辑和指标/日志记录。
"""
```

```python
# 旧:
"""Initialize quality service.

Args:
    engine: Quality engine instance
    quarantine_writer: Optional quarantine writer for failed data
"""

# 新:
"""初始化质量检查服务.

Args:
    engine: 质量引擎实例
    quarantine_writer: 可选的隔离写入器，用于存储失败数据
"""
```

**Step 2: 修复 providers.py:114**

将英文 docstring 改为中文。

**Step 3: 验证**

Run: `pixi run -e dev check`

**Step 4: Commit**

```bash
git add packages/app/src/ditto_app/process/quality.py packages/app/src/ditto_app/providers.py
git commit -m "fix: 统一 docstring 语言为中文"
```

---

### Task 14: 补充 interfaces 层 __all__

**Files:**
- Modify: `interfaces/src/ditto_interfaces/__init__.py`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/backfill/__init__.py`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ingest/__init__.py`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/query/__init__.py`

**问题:** 4 个 `__init__.py` 有 import 但缺少 `__all__`。

**Step 1: 逐文件添加 `__all__`**

对每个文件，检查其 import 和导出，添加适当的 `__all__` 列表。

**Step 2: 验证**

Run: `pixi run -e dev check`

**Step 3: Commit**

```bash
git add interfaces/src/ditto_interfaces/__init__.py interfaces/src/ditto_interfaces/cli/commands/
git commit -m "fix: 补充 interfaces 层 __init__.py 的 __all__ 导出定义"
```

---

## Part 5: 文档路径更新（2 tasks）

### Task 15: 批量更新非 archive 文档中的旧路径

**Files:**
- Modify: ~32 个非 archive 文档文件

**问题:** 非 archive 文档中仍引用 `interfaces/`、`packages/core/`、`packages/data/` 旧路径。

**路径替换规则:**

| 旧路径 | 新路径 |
|--------|--------|
| `interfaces/src/ditto_interfaces/` | `interfaces/src/ditto_interfaces/` |
| `interfaces/` | `interfaces/` |
| `packages/engine/src/ditto_engine/` | `packages/engine/src/ditto_engine/` |
| `packages/core/` | `packages/engine/` (上下文为 engine 代码时) |
| `packages/core/` | `packages/app/` (上下文为 app 代码时) |
| `packages/core/` | `packages/kernel/` (上下文为 kernel 代码时) |
| `packages/data/src/ditto_data/` | `packages/data/src/ditto_data/` |
| `packages/data/` | `packages/data/` |
| `ditto_core` | `ditto_engine` 或 `ditto_app` 或 `ditto_kernel` (按上下文) |
| `ditto_data` | `ditto_data` |
| `ditto_interfaces` | `ditto_interfaces` |

**Step 1: 列出所有需修改的文件**

```bash
grep -rl 'interfaces/\|packages/core/\|packages/data/\|ditto_core\|ditto_data\|ditto_interfaces' docs/ --include='*.md' | grep -v archive
```

**Step 2: 逐文件替换**

对每个文件，根据上下文判断正确的新路径。**注意:** 同一文件中 `packages/core/` 可能需要替换为不同的新包名（engine/app/kernel），需人工判断上下文。

**Step 3: 重点文件**

以下文件优先处理（活跃文档）：
- `docs/operations/operations-manual.md` — 运维手册
- `docs/design/01_system_design.md` — 系统总体设计
- `docs/design/03_engine_design.md` — 引擎设计
- `docs/design/04_deployment_topology.md` — 部署拓扑
- `docs/sprints/sprint-03-core-engines.md` — Sprint 3
- `docs/sprints/sprint-04-backtest-risk.md` — Sprint 4

**Step 4: 验证**

确认无遗漏：
```bash
grep -r 'interfaces/\|packages/core/\|packages/data/' docs/ --include='*.md' | grep -v archive | wc -l
# Expected: 0
```

**Step 5: Commit**

```bash
git add docs/
git commit -m "docs: 更新非 archive 文档中的旧路径引用 — port/core/datahub → interfaces/engine/data"
```

---

### Task 16: 补充缺失的 README

**Files:**
- Create: `packages/app/README.md`
- Create: `packages/analytics/README.md`

**问题:** 其他 5 个包都有 README.md，app 和 analytics 缺失。

**Step 1: 创建 packages/app/README.md**

参考 `packages/engine/README.md` 和 `packages/app/CLAUDE.md` 的结构，编写：
- 包定位（应用编排层 CQRS）
- 模块结构（query/process/command/builders）
- 依赖关系
- 使用示例

**Step 2: 创建 packages/analytics/README.md**

参考 `packages/analytics/CLAUDE.md`，编写：
- 包定位（表达式编译 + 物化 + 因子 + 研究）
- 模块结构
- 依赖关系

**Step 3: 验证**

Run: `pixi run -e dev check`

**Step 4: Commit**

```bash
git add packages/app/README.md packages/analytics/README.md
git commit -m "docs: 补充 packages/app 和 packages/analytics 的 README.md"
```

---

## Part 6: 代码规模（1 task）

### Task 17: 拆分 market_service.py（1053 行 → ≤ 1000 行）

**Files:**
- Modify: `packages/data/src/ditto_data/services/market_service.py`
- Create: `packages/data/src/ditto_data/services/market_write_service.py`
- Modify: 所有引用 MarketService 写入方法的文件

**问题:** `market_service.py` 1053 行，超过 core.md 1000 行限制。

**Step 1: 分析拆分点**

文件结构分析：
- 第 31-107 行：查询 DTO（AdjType, MarketBarsQuery, MarketConstituentsQuery）
- 第 110-808 行：MarketService 查询方法（find_bars, list_bars, get_constituents 等）
- 第 822-1020 行：MarketService 写入方法（save_bars, save_adj_factor, save_stock_status）
- 第 1021-1053 行：静态工具方法（check_late_arrival_on_write）

**Step 2: 设计拆分方案**

方案：将写入方法提取到 `market_write_service.py`：
- `MarketWriteService` 包含 `save_bars`、`save_adj_factor`、`save_stock_status`、`check_late_arrival_on_write`
- DTO 类（AdjType, MarketBarsQuery, MarketConstituentsQuery）保留在 `market_service.py` 或提取到独立模块
- `MarketService` 保留查询方法

**Step 3: 更新 DI 注册**

在 `packages/data/src/ditto_data/di/market.py` 中注册 `MarketWriteService`。

**Step 4: 更新所有调用点**

```bash
grep -rn 'MarketService' packages/*/src interfaces/*/src --include='*.py' | grep -v test
```

**Step 5: 运行测试**

Run: `pixi run -e dev test`
Expected: 全部通过

**Step 6: 验证文件行数**

```bash
wc -l packages/data/src/ditto_data/services/market_service.py
wc -l packages/data/src/ditto_data/services/market_write_service.py
# Expected: 两个文件均 ≤ 1000 行
```

**Step 7: Commit**

```bash
git add packages/data/src/ditto_data/services/market_service.py packages/data/src/ditto_data/services/market_write_service.py packages/data/src/ditto_data/di/market.py
git commit -m "refactor: 拆分 market_service.py — 提取 MarketWriteService 降低文件规模"
```

---

## 执行顺序

```
Part 1 (架构文档) ─────┐
Part 2 (noqa 清零)  ───┤── 可并行
Part 3 (架构代码)  ───┤
Part 4 (规约合规)  ───┘
        │
        ▼
Part 5 (文档路径) ──── 依赖 Part 1 的路径规范确认
Part 6 (代码规模)  ──── 独立，可随时执行
```

**建议:** Part 1-4 可由 subagent 并行执行，Part 5-6 顺序执行。

---

## 验收标准

```bash
# 1. 生产代码 noqa 检查
git grep "# noqa" packages/*/src interfaces/*/src | grep -v "S608\|S108\|S110"
# Expected: 0 results

# 2. 类型检查
pixi run -e dev type
# Expected: 0 errors

# 3. Lint 检查
pixi run -e dev lint
# Expected: All checks passed

# 4. 测试
pixi run -e dev test
# Expected: 全部通过

# 5. 架构检查
pixi run -e dev arch-check
# Expected: 0 broken contracts

# 6. 文档路径检查
grep -r 'interfaces/\|packages/core/\|packages/data/' docs/ --include='*.md' | grep -v archive | wc -l
# Expected: 0

# 7. 文件规模检查
find packages/*/src -name '*.py' -exec wc -l {} + | sort -rn | head -5
# Expected: 无文件超过 1000 行
```
