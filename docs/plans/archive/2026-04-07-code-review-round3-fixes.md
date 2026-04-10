# Code Review Round 3 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PR #61 Code Review 发现的 3 个 25 分以上问题

**Architecture:** 问题分为两类——文档修正（Issue 2/3）和代码修复（Issue 1）。代码修复方案采用已有的 `QueryContext` 设计（见 `docs/plans/2026-04-04-fix-ingestion-bundle-leak.md`），创建专门的 query context manager 替代 CLI query 命令中对 `IngestionBundle` 废弃字段的引用。

**Tech Stack:** Python 3.12+, dataclasses, contextlib, dishka DI

---

## 任务清单

### Task 1: 创建 QueryContext + create_query_context `[M]`

**根因:** CLI query 命令直接引用 `bundle.capital_service` 等 7 个已从 `IngestionBundle` 移除的字段。Phase 4 将 bundle 精简为 5 个字段时遗漏了 CLI query 命令的更新。

**方案:** 新建 `QueryContext` dataclass 和 `create_query_context()` context manager，封装 5 个只读 query facade。此函数在 `registry/contexts/` 内（Composition Root），允许导入 data services。

**Files:**
- Create: `interfaces/src/ditto_interfaces/registry/contexts/query.py`
- Modify: `interfaces/src/ditto_interfaces/registry/contexts/__init__.py`

**Step 1: 创建 QueryContext**

```python
# interfaces/src/ditto_interfaces/registry/contexts/query.py
"""查询上下文组合包."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from ditto_app.query.capital import CapitalQueryFacade
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.macro import MacroQueryFacade
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

from ditto_interfaces.registry.container import make_app_container


@dataclass(frozen=True)
class QueryContext:
    """只读查询上下文 — 封装 app 层 query facades."""

    metadata: MetadataQueryFacade
    market: MarketQueryFacade
    capital: CapitalQueryFacade
    fundamental: FundamentalQueryFacade
    macro: MacroQueryFacade


@contextmanager
def create_query_context() -> Iterator[QueryContext]:
    """创建查询上下文（轻量级，不创建协调器等 process 组件）."""
    container = make_app_container()
    try:
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        capital_service = container.get(CapitalService)
        fundamental_service = container.get(FundamentalService)
        macro_service = container.get(MacroService)

        yield QueryContext(
            metadata=MetadataQueryFacade(metadata_service=metadata_service),
            market=MarketQueryFacade(market_service=market_service),
            capital=CapitalQueryFacade(capital_service=capital_service),
            fundamental=FundamentalQueryFacade(fundamental_service=fundamental_service),
            macro=MacroQueryFacade(macro_service=macro_service),
        )
    finally:
        container.close()
```

**Step 2: 更新 __init__.py 导出**

在 `interfaces/src/ditto_interfaces/registry/contexts/__init__.py` 中添加 `QueryContext` 和 `create_query_context` 的导入和导出。

**Step 3: 运行类型检查**

```bash
pixi run -e dev type
```

Expected: 通过

**Step 4: Commit**

```bash
git add interfaces/src/ditto_interfaces/registry/contexts/query.py
git add interfaces/src/ditto_interfaces/registry/contexts/__init__.py
git commit -m "feat: add QueryContext for CLI query commands"
```

---

### Task 2: 更新 5 个 CLI query 命令使用 QueryContext `[M]`

**根因:** 同 Task 1。5 个 query 命令仍在引用 `bundle.xxx_service` 等不存在的字段。

**Files:**
- Modify: `interfaces/src/ditto_interfaces/cli/commands/query/market.py:25-29`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/query/metadata.py:25-29`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/query/capital.py:28-37`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/query/fundamental.py:30-39`
- Modify: `interfaces/src/ditto_interfaces/cli/commands/query/macro.py:29-33`

**Step 1: 更新 market.py**

将 `_get_market_facade()` 从使用 `create_cli_host` + `bundle.market_service` 改为 `create_query_context` + `ctx.market`:

```python
# 旧代码 (line 25-29)
@contextmanager
def _get_market_facade() -> Generator[MarketQueryFacade, None, None]:
    with create_cli_host() as bundle:
        yield MarketQueryFacade(market_service=bundle.market_service)

# 新代码
@contextmanager
def _get_market_facade() -> Generator[MarketQueryFacade, None, None]:
    with create_query_context() as ctx:
        yield ctx.market
```

更新 import: 移除 `create_cli_host`，添加 `from ditto_interfaces.registry.contexts import create_query_context`。如果 `create_cli_host` 和 `MarketQueryFacade` 不再被其他地方使用则移除对应 import。

**Step 2: 更新 metadata.py**

同样模式，`_get_metadata_facade()` 使用 `create_query_context`:

```python
# 旧代码 (line 25-29)
@contextmanager
def _get_metadata_facade() -> Generator[MetadataQueryFacade, None, None]:
    with create_cli_host() as bundle:
        yield MetadataQueryFacade(metadata_service=bundle.metadata_service)

# 新代码
@contextmanager
def _get_metadata_facade() -> Generator[MetadataQueryFacade, None, None]:
    with create_query_context() as ctx:
        yield ctx.metadata
```

**Step 3: 更新 capital.py**

`_get_facades()` 需要两个 facade（capital + metadata）:

```python
# 旧代码 (line 28-37)
@contextmanager
def _get_facades() -> Generator[
    tuple[CapitalQueryFacade, MetadataQueryFacade], None, None
]:
    with create_cli_host() as bundle:
        yield (
            CapitalQueryFacade(capital_service=bundle.capital_service),
            MetadataQueryFacade(metadata_service=bundle.metadata_service),
        )

# 新代码
@contextmanager
def _get_facades() -> Generator[
    tuple[CapitalQueryFacade, MetadataQueryFacade], None, None
]:
    with create_query_context() as ctx:
        yield (ctx.capital, ctx.metadata)
```

**Step 4: 更新 fundamental.py**

同样模式，需要 fundamental + metadata:

```python
# 旧代码 (line 30-39)
@contextmanager
def _get_facades() -> Generator[
    tuple[FundamentalQueryFacade, MetadataQueryFacade], None, None
]:
    with create_cli_host() as bundle:
        yield (
            FundamentalQueryFacade(fundamental_service=bundle.fundamental_service),
            MetadataQueryFacade(metadata_service=bundle.metadata_service),
        )

# 新代码
@contextmanager
def _get_facades() -> Generator[
    tuple[FundamentalQueryFacade, MetadataQueryFacade], None, None
]:
    with create_query_context() as ctx:
        yield (ctx.fundamental, ctx.metadata)
```

**Step 5: 更新 macro.py**

```python
# 旧代码 (line 29-33)
@contextmanager
def _get_macro_facade() -> Generator[MacroQueryFacade, None, None]:
    with create_cli_host() as bundle:
        yield MacroQueryFacade(macro_service=bundle.macro_service)

# 新代码
@contextmanager
def _get_macro_facade() -> Generator[MacroQueryFacade, None, None]:
    with create_query_context() as ctx:
        yield ctx.macro
```

**Step 6: 检查 create_cli_host 是否还有其他 consumer**

```bash
grep -rn "create_cli_host" interfaces/src/ --include="*.py"
```

如果 `create_cli_host` 在 query 命令之外没有其他消费者，考虑标注 deprecated 或保留（ingest 命令通过 `create_executor` 走不同路径）。

**Step 7: 运行类型检查 + arch-check**

```bash
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: 全部通过。query 命令不再引用 `ditto_data.services`，全部通过 `QueryContext` facade 间接访问。

**Step 8: Commit**

```bash
git add interfaces/src/ditto_interfaces/cli/commands/query/
git commit -m "fix: CLI query commands use QueryContext instead of removed IngestionBundle fields"
```

---

### Task 3: 修复 CLAUDE.md analytics 依赖链 `[S]`

**根因:** Phase 3 将 analytics 确立为与 engine 平行的独立平面（互不依赖），但 CLAUDE.md line 68 的依赖链仍写成 `ditto_analytics → ditto_engine → ditto_kernel`，暗示 analytics 依赖 engine。

**验收:** CLAUDE.md 依赖层级准确反映 importlinter 合约和实际代码。

**Files:**
- Modify: `CLAUDE.md:66-74`

**Step 1: 修正依赖链 + 跨层依赖说明**

将 line 66-74 的架构原则部分从:

```
依赖层级（从高到低）:
  ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra
  ditto_interfaces → ditto_analytics → ditto_engine → ditto_kernel
  ditto_interfaces → ditto_data → ditto_kernel, ditto_infra

允许的跨层依赖:
  - interfaces 可以直接依赖 data.models/services/sources
  - interfaces 可以直接依赖 infra.foundation
  - interfaces 禁止直接依赖 data.storage/runtime（仅 registry 例外）
```

改为:

```
依赖层级（从高到低）:
  ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra
  ditto_interfaces → ditto_analytics → ditto_kernel
  ditto_interfaces → ditto_data → ditto_kernel, ditto_infra

允许的跨层依赖:
  - interfaces 可以直接依赖 data.sources（仅 registry 例外范围可依赖 data.services/models）
  - interfaces 可以直接依赖 infra.foundation
  - interfaces 禁止直接依赖 data.storage/runtime（仅 registry 例外）

详细约束见 .importlinter 配置
```

关键变更:
1. `ditto_analytics → ditto_engine → ditto_kernel` 改为 `ditto_analytics → ditto_kernel`（analytics 与 engine 是平行平面）
2. `data.models/services/sources` 改为 `data.sources`（importlinter `interfaces-service-isolation` 禁止非 registry 代码访问 data.services/data.models）

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: fix CLAUDE.md dependency chain for analytics and interfaces-data rules"
```

---

### Task 4: 运行完整验证 `[S]`

**验收:** 所有检查通过。

**Step 1: 运行完整 check**

```bash
pixi run -e dev check
```

Expected: lint + fmt + type + test --fast 全部通过。

**Step 2: 运行 arch-check**

```bash
pixi run -e dev arch-check
```

Expected: 所有 importlinter 合约通过。

**Step 3: 验证 query 命令不再引用 data services**

```bash
grep -rn "ditto_data\.services" interfaces/src/ditto_interfaces/cli/commands/query/ --include="*.py"
```

Expected: 无输出（所有 query 命令通过 QueryContext 访问）。

---

## 依赖关系

```
Task 1 (QueryContext) → Task 2 (CLI 命令更新) → Task 4 (验证)
Task 3 (CLAUDE.md) ─────────────────────────────→ Task 4 (验证)
```

Task 1 和 Task 3 可并行执行，Task 2 依赖 Task 1，Task 4 依赖所有。

## 验证汇总

```bash
pixi run -e dev check        # lint + fmt + type + test --fast
pixi run -e dev arch-check   # importlinter
grep -rn "ditto_data\.services" interfaces/src/ditto_interfaces/cli/commands/query/ --include="*.py"
# Expected: 无输出
```
