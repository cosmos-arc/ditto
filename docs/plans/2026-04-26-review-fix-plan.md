# V1 Sprint Code Review 全量修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 /ditto-review 6 维度审查发现的所有 54 项问题（8 P0 + 24 P1 + 22 P2）

**Architecture:** 按领域分 9 个 Phase，每个 Phase 内按依赖顺序执行。Phase 1-3 为合并门禁（P0），Phase 4-9 为质量提升。

**Tech Stack:** Python 3.12+, polars, basedpyright, ruff, pytest

---

## Phase 1: P0 代码缺陷（合并门禁）

### Task 1: 表达式编译器静默吞掉未知 AST 节点 `[S]`

**Files:**
- Modify: `packages/analytics/src/ditto_analytics/expression/codegen.py:169-187`
- Test: `packages/analytics/tests/unit/expression/test_codegen_unit.py`（已有测试文件）

**Step 1: 写失败测试**

在已有 codegen 测试中添加：
```python
def test_compile_unknown_literal_node_raises():
    """未知字面量 AST 节点应抛出编译错误，而非静默返回 None."""
    # 构造一个无法匹配的 AST 节点
    node = ExpressionNode(...)  # 使用一个非 IdentifierNode/ColumnRefNode/FeatureRefNode/NumberNode/StringNode 的类型
    with pytest.raises(ExpressionCompileError):
        _compile_literal_or_reference(node)
```

**Step 2: 运行测试确认失败**

Run: `pixi run -e dev pytest packages/analytics/tests/unit/expression/test_codegen_unit.py -k "unknown_literal" -v`

**Step 3: 修复实现**

在 `codegen.py:185` 将 `case _: pass` 改为抛出 `ExpressionCompileError`：
```python
from ditto_analytics.expression.diagnostics import make_compile_error

# 在 _compile_literal_or_reference 函数中：
case _:
    raise make_compile_error(
        source="",
        message=f"Unsupported literal or reference node: {type(node).__name__}",
        error_code="E0501",
        span=node.span if hasattr(node, "span") else Span(
            start=SourcePosition(0, 1, 1),
            end=SourcePosition(0, 1, 1),
        ),
    )
```

**Step 4: 运行测试确认通过**

Run: `pixi run -e dev pytest packages/analytics/tests/unit/expression/ -v`

**Step 5: Commit**

```bash
git commit -m "fix: 表达式编译器未知 AST 节点抛出错误而非静默返回 None (P0-2)"
```

---

### Task 2: Engine flush 静默吞掉异常 `[S]`

**Files:**
- Modify: `packages/engine/src/ditto_engine/backtest/engine.py:429-433`
- Test: `packages/engine/tests/unit/backtest/test_engine_loop_unit.py`（已有）

**Step 1: 写失败测试**

```python
def test_flush_delayed_signal_propagates_unexpected_error():
    """flush 延迟信号时，非 DataNotFoundError 应向上传播."""
    # mock data_feed.get_slice 抛出 RuntimeError
    # 验证 RuntimeError 被传播而非被吞掉
```

**Step 2: 运行测试确认失败**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/ -k "flush_propagates" -v`

**Step 3: 修复实现**

将 `engine.py:429-433` 的 `except Exception` 缩小为特定异常：
```python
try:
    ctx.slice_ = self._data_feed.get_slice(last_date)
except DataNotFoundError:
    logger.warning("Flush: no slice data for {}", last_date)
    return
except Exception:
    logger.exception("Flush: unexpected error getting slice for {}", last_date)
    raise
```

注意：需要确认 `DataNotFoundError` 的实际类名（可能在 `ditto_data.errors` 或 `ditto_kernel.exceptions`），通过 `grep -rn "class DataNotFoundError\|class.*NotFoundError" packages/` 确认。

**Step 4: 运行测试确认通过**

Run: `pixi run -e dev pytest packages/engine/tests/unit/backtest/ -v`

**Step 5: Commit**

```bash
git commit -m "fix: engine flush 延迟信号异常传播 — 非 DataNotFoundError 不再静默吞掉 (P0-5)"
```

---

### Task 3: Protocol 方法重复 — MacroFetcher / CommodityFetcher `[S]`

**Files:**
- Modify: `packages/data/src/ditto_data/sources/protocols.py:186-231`
- Test: `packages/data/tests/unit/sources/`（已有 Protocol 测试）

**Step 1: 写失败测试（确认行为不变）**

```python
def test_commodity_fetcher_protocol_compatible_with_macro_fetcher():
    """CommodityFetcher 应兼容 MacroFetcher 的 fetch_commodities 签名."""
    # 验证 StructuralSubtyping：任何 MacroFetcher 实现也满足 CommodityFetcher
```

**Step 2: 修复实现**

删除 `CommodityFetcher` Protocol，在注释中说明 `MacroFetcher.fetch_commodities` 已覆盖此能力：
```python
# 删除 L221-231 的 CommodityFetcher class
# 如果有消费者仅依赖 CommodityFetcher，改为依赖 MacroFetcher
```

先 grep 确认消费者：
```bash
grep -rn "CommodityFetcher" packages/ interfaces/ --include="*.py"
```

**Step 3: 更新消费者导入**

将所有 `from ... import CommodityFetcher` 改为 `from ... import MacroFetcher`。

**Step 4: 运行测试确认通过**

Run: `pixi run -e dev pytest packages/data/tests/ -v`

**Step 5: Commit**

```bash
git commit -m "refactor: 删除重复的 CommodityFetcher Protocol — 已由 MacroFetcher 覆盖 (P0-1)"
```

---

## Phase 2: P0 类型安全（合并门禁）

### Task 4: Command Handler 返回类型安全化 `[M]`

**Files:**
- Modify: `packages/app/src/ditto_app/command/universe.py:6,53,79`
- Modify: `packages/data/src/ditto_data/services/metadata_service.py`（get_universe_detail 返回类型）
- Test: `packages/app/tests/unit/command/test_universe_unit.py`（已有）

**Step 1: 写失败测试**

```python
def test_create_handler_returns_universe_detail():
    """CreateCustomUniverseHandler.handle 应返回 UniverseDetail."""
    # 验证返回类型为 dict 且包含必需字段
```

**Step 2: 修改 universe.py**

1. 移除 `from typing import Any`
2. 定义返回类型 TypedDict 或直接保持 `dict[str, str | None]`（如果 MetadataService 的 `get_universe_detail` 返回已类型化）：
```python
def handle(self, command: CreateCustomUniverseCommand) -> dict[str, str | None]:
```
3. 同理修改 `UpdateCustomUniverseHandler.handle`

**Step 3: 运行测试确认通过**

Run: `pixi run -e dev pytest packages/app/tests/unit/command/ -v`

**Step 4: Commit**

```bash
git commit -m "fix: universe command handler 移除 dict[str, Any]，收窄为 dict[str, str | None] (P0-3)"
```

---

### Task 5: CLI 工具函数类型安全化 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ops.py:102,113`

**Step 1: 修改返回类型**

```python
from ditto_interfaces.registry.container import AppContainer

def _fetch_status_facade() -> tuple[AppContainer, IngestionStatusQueryFacade]:
def _fetch_patrol_service() -> tuple[AppContainer, QualityPatrolService]:
```

**Step 2: 确认 `AppContainer` 是正确的类型名**

```bash
grep -n "class.*Container\|def make_app_container" interfaces/src/ditto_interfaces/registry/container.py | head -5
```

**Step 3: 运行类型检查**

Run: `pixi run -e dev type`

**Step 4: Commit**

```bash
git commit -m "fix: CLI 工具函数返回类型从 tuple[Any, ...] 收窄为具体容器类型 (P0-4)"
```

---

### Task 6: CLI `_CORE_DATASETS` 使用 Dataset 枚举 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ops.py:21`

**Step 1: 修改实现**

```python
_CORE_DATASETS: list[str] = [
    d.value for d in (
        Dataset.ETF_DAILY, Dataset.STOCK_DAILY,
        Dataset.INDEX_DAILY, Dataset.ADJ_FACTOR,
    )
]
```

**Step 2: 运行测试**

Run: `pixi run -e dev pytest interfaces/tests/unit/cli/ -v`

**Step 3: Commit**

```bash
git commit -m "fix: _CORE_DATASETS 改用 Dataset 枚举派生，避免硬编码字符串 (P1-16)"
```

---

## Phase 3: P0 文档修复（合并门禁）

### Task 7: CLAUDE.md 依赖方向声明修正 `[S]`

**Files:**
- Modify: `CLAUDE.md:66-70`

**Step 1: 修改内容**

将：
```
  ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra
```
改为：
```
  ditto_interfaces → ditto_app → ditto_engine → ditto_kernel
  ditto_interfaces → ditto_app → ditto_data → ditto_kernel, ditto_infra
  ditto_interfaces → ditto_data → ditto_kernel, ditto_infra
  ditto_app → ditto_analytics → ditto_kernel
```

**Step 2: Commit**

```bash
git commit -m "docs: CLAUDE.md 修正依赖方向 — engine 不依赖 data/infra (P0-7)"
```

---

### Task 8: README 依赖方向 + 模块计数修正 `[S]`

**Files:**
- Modify: `README.md:59-66,84,113,122-133`

**Step 1: 修改依赖方向图**

将 `engine → kernel, data.errors, data.provider (Protocol)` 改为 `engine → kernel`。

**Step 2: 修正模块计数**

- "查询编排（26 Facade）" → 重新计数并更新
- "数据模型（14 模块）" → "数据模型（13 模块）"
- kernel 模块列表：删除 `specs.py`、`types.py`，补充 `instrument.py`、`market.py`、`order.py`、`strategy.py`、`_version.py`

**Step 3: 修正 CLI 描述**

扩展 `ditto init/ingest/backfill/query` 为更详细的命令组描述。

**Step 4: 验证 Stage 计数**

```bash
grep -c "class.*Stage" packages/engine/src/ditto_engine/alpha/builtins/*.py
```

根据结果更新 "8 个内置 Stage" 描述。

**Step 5: Commit**

```bash
git commit -m "docs: README 修正依赖方向 + 模块计数 + CLI 描述 (P0-8, P1-18~21, P2-20)"
```

---

### Task 9: OpenAPI 规范补充 deviation 路由 `[S]`

**Files:**
- Modify: `docs/openapi/v1.json`

**Step 1: 从 FastAPI 应用导出更新**

```bash
# 在 dev 环境启动后，或通过脚本导出
pixi run -e dev python -c "
from ditto_interfaces.main import create_app
import orjson
app = create_app()
spec = app.openapi()
with open('docs/openapi/v1.json', 'wb') as f:
    f.write(orjson.dumps(spec, option=orjson.OPT_INDENT_2))
"
```

如果无法运行应用，则手动在 `docs/openapi/v1.json` 的 paths 中补充 `/api/v1/trade/deviation` 路由定义。

**Step 2: Commit**

```bash
git commit -m "docs: OpenAPI spec 补充 /trade/deviation 路由 (P0-6)"
```

---

## Phase 4: 异常处理改进（P1-13, P1-14, P1-15）

### Task 10: 47 处 raise 缺少 `from exc` 异常链 `[M]`

**Files:**
- Modify: `packages/data/src/ditto_data/services/metadata/instrument.py`（9 处）
- Modify: `packages/app/src/ditto_app/process/ingestion/coordinator.py`（4 处）
- Modify: `packages/app/src/ditto_app/builders/runtime_builder.py`（4 处）
- Modify: `packages/app/src/ditto_app/process/execution/factor_bridge.py`（3 处）
- Modify: `packages/app/src/ditto_app/process/materialization/orchestrator.py`（3 处）
- 以及其他文件中的剩余处

**Step 1: 批量定位所有缺失处**

```bash
grep -rn "except.*as exc:\|except.*as e:" packages/ interfaces/ --include="*.py" \
  | grep -v "/tests/" \
  | while read line; do
      file=$(echo "$line" | cut -d: -f1)
      lnum=$(echo "$line" | cut -d: -f2)
      # 检查后续的 raise 是否缺少 from
      next_raise=$(sed -n "$((lnum+1)),$((lnum+5))p" "$file" | grep "raise " | head -1)
      if echo "$next_raise" | grep -qv "from "; then
          echo "$file:$lnum -> $next_raise"
      fi
    done
```

**Step 2: 逐一添加 `from exc`**

模式：
```python
# Before:
except Exception as exc:
    raise SomeError("msg") from exc  # 添加 from exc

# Before:
except SomeSpecificError as exc:
    raise AnotherError("msg") from exc  # 添加 from exc
```

**Step 3: 运行测试确认无回归**

Run: `pixi run -e dev test --fast`

**Step 4: Commit**

```bash
git commit -m "fix: 47 处 raise 添加 from exc 异常链 — 防止调试上下文丢失 (P1-13)"
```

---

### Task 11: 4 处 bare `except Exception:` 添加变量绑定 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/jobs/flows/eod.py:72`
- Modify: `interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py`
- Modify: `packages/app/src/ditto_app/process/materialization/orchestrator.py:192`

**Step 1: 修改所有 bare except**

```python
# Before:
except Exception:
    logger.exception("...")
# After:
except Exception:
    logger.exception("...")  # 已有 logger.exception 的保持不变（已记录完整堆栈）
```

对于没有 `logger.exception` 的 bare except，添加 `as exc` 变量绑定。

**Step 2: Commit**

```bash
git commit -m "fix: bare except 添加变量绑定 (P1-14)"
```

---

### Task 12: CLI `except Exception` 缩小范围 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/cli/commands/ops.py:107`

**Step 1: 修改实现**

```python
from dishka.exceptions import RequestedScopeNotFoundError, MissingDependencyError

def _fetch_status_facade() -> tuple[AppContainer, IngestionStatusQueryFacade]:
    container = make_app_container()
    try:
        return container, container.get(IngestionStatusQueryFacade)
    except (RequestedScopeNotFoundError, MissingDependencyError) as exc:
        typer.secho(f"服务初始化失败: {exc}", fg=typer.colors.RED, err=True)
        container.close()
        raise typer.Exit(1) from exc
```

对 `_fetch_patrol_service` 同理修改。

**Step 2: 运行测试**

Run: `pixi run -e dev pytest interfaces/tests/unit/cli/ -v`

**Step 3: Commit**

```bash
git commit -m "fix: CLI 工具函数 except 范围缩小为 DI 特定异常 (P1-15)"
```

---

## Phase 5: 编码规约修复（P1-5, P1-6, P2-5, P2-6）

### Task 13: deps.py 8 个 dataclass 添加 `frozen=True` `[S]`

**Files:**
- Modify: `packages/data/src/ditto_data/services/deps.py:92,132,...`

**Step 1: 批量修改**

将所有 `@dataclass` 改为 `@dataclass(frozen=True)`：
- `MarketReaders` (L92)
- `MarketWriters` (L132)
- `FundamentalReaders`
- `FundamentalWriters`
- `CapitalReaders`
- `CapitalWriters`
- `ExecutionReaders`
- `ExecutionWriters`

**Step 2: 运行测试确认通过**

Run: `pixi run -e dev pytest packages/data/tests/ -v`

**Step 3: Commit**

```bash
git commit -m "fix: deps.py 8 个 DI 聚合 dataclass 添加 frozen=True (P1-5)"
```

---

### Task 14: `get_lineage` → `list_lineage` 重命名 `[S]`

**Files:**
- Modify: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py:179`
- Modify: 所有调用方（通过 grep 定位）

**Step 1: 定位调用方**

```bash
grep -rn "get_lineage\|\.get_lineage" packages/ interfaces/ --include="*.py"
```

**Step 2: 重命名方法**

```python
# Before:
def get_lineage(self, run_id: str) -> list[StrategyRunRecord]:
# After:
def list_lineage(self, run_id: str) -> list[StrategyRunRecord]:
```

**Step 3: 更新所有调用方**

**Step 4: 运行测试**

Run: `pixi run -e dev pytest packages/data/tests/ -v`

**Step 5: Commit**

```bash
git commit -m "fix: get_lineage → list_lineage — 返回 list 不符合 get_ 语义 (P1-6)"
```

---

### Task 15: kernel `__init__.py` 导出数降至 ≤30 `[S]`

**Files:**
- Modify: `packages/kernel/src/ditto_kernel/__init__.py`

**Step 1: 审查当前导出**

```bash
grep -c "__all__" packages/kernel/src/ditto_kernel/__init__.py
# 确认当前导出数量
```

**Step 2: 将 `__version__` 移出 `__all__`**（如果超标）

`__version__` 是元数据，消费者通常不直接导入，可从 `_version.py` 导入。

**Step 3: Commit**

```bash
git commit -m "refactor: kernel __init__.py 导出数降至 ≤30 (P2-5)"
```

---

### Task 16: 预存 dataclass 添加 frozen — StepContext 不可变化 `[M]`

**Files:**
- Modify: `packages/engine/src/ditto_engine/backtest/steps/types.py:74`
- Modify: `packages/engine/src/ditto_engine/accounting/account.py:50`
- Modify: `packages/engine/src/ditto_engine/execution/trade_builder.py:99,253`

**Step 1: 评估可变性需求**

`StepContext` 故意设计为可变共享状态。评估能否重构为 `dataclasses.replace` 模式。

如果重构成本过高（影响 engine 核心循环），则保留并添加注释说明原因。

**Step 2: 对于 `Account` 和 `_OpenEntry`/`_InstrumentAccumulator`**同理评估。

**Step 3: Commit（如有修改）**

```bash
git commit -m "refactor: 评估并修复预存 dataclass frozen 状态 (P2-6)"
```

---

## Phase 6: 架构改进（P1-1, P1-2, P2-21, P2-22）

### Task 17: Dataset 枚举提升到 kernel 或扩展 importlinter 豁免 `[M]`

**Files:**
- Option A: Move `Dataset` to `packages/kernel/src/ditto_kernel/enums.py`
- Option B: Extend `.importlinter` ignore_imports

**Step 1: 确认 Dataset 定义位置和消费者**

```bash
grep -rn "from.*import Dataset\|from.*models.common import" packages/ interfaces/ --include="*.py" | grep -v "/tests/"
```

**Step 2: 选择方案**

如果 `Dataset` 被多层使用（interfaces + app + data），推荐方案 A（提升到 kernel）。

**Step 3: 实施迁移**

方案 A：
1. 在 `ditto_kernel/enums.py` 中添加 `Dataset` StrEnum
2. 在 `ditto_data/models/common.py` 中改为 re-export（或直接引用 kernel）
3. 更新所有消费者导入路径
4. 更新 `.importlinter` ignore_imports

**Step 4: 运行 arch-check**

Run: `pixi run -e dev arch-check`

**Step 5: Commit**

```bash
git commit -m "refactor: Dataset 枚举提升到 kernel — 跨层共享系统级枚举 (P1-1)"
```

---

### Task 18: `DEFAULT_INITIAL_CASH` 提取到 kernel 或硬编码 `[S]`

**Files:**
- Modify: `packages/app/src/ditto_app/config.py`（当前定义位置）
- Modify: `interfaces/src/ditto_interfaces/models/backtest.py:8`

**Step 1: 确认当前位置**

```bash
grep -rn "DEFAULT_INITIAL_CASH" packages/ interfaces/ --include="*.py"
```

**Step 2: 选择方案**

- 方案 A：硬编码到 Pydantic 模型 `Field(default=1_000_000)`
- 方案 B：提取到 `ditto_kernel` 作为系统常量

推荐方案 A（简单，常量值不依赖任何配置）。

**Step 3: 实施 + Commit**

```bash
git commit -m "refactor: backtest 模型 DEFAULT_INITIAL_CASH 硬编码，移除跨层配置导入 (P1-2)"
```

---

### Task 19: `_artifact_utils.py` 去掉下划线前缀 `[S]`

**Files:**
- Rename: `packages/app/src/ditto_app/query/_artifact_utils.py` → `artifact_utils.py`
- Modify: 所有导入方

**Step 1: 确认消费者**

```bash
grep -rn "_artifact_utils" packages/ interfaces/ --include="*.py"
```

**Step 2: 重命名文件 + 更新导入**

**Step 3: Commit**

```bash
git commit -m "refactor: _artifact_utils.py → artifact_utils.py — 被跨 CQRS 子域消费 (P2-21)"
```

---

### Task 20: `data.services.__init__.py` 清理跨子包 re-export `[S]`

**Files:**
- Modify: `packages/data/src/ditto_data/services/__init__.py:8-14`

**Step 1: 确认消费者**

```bash
grep -rn "from ditto_data.services import FreezeService\|from ditto_data.services import IngestionCursorService" packages/ interfaces/ --include="*.py"
```

**Step 2: 更新消费者导入路径**

将 `from ditto_data.services import FreezeService` 改为 `from ditto_data.ingestion.freeze_service import FreezeService`。

**Step 3: 移除 `services/__init__.py` 中的交叉 re-export**

**Step 4: Commit**

```bash
git commit -m "refactor: data.services.__init__ 清理跨子包 re-export — 消费者直接引用叶模块 (P2-22)"
```

---

## Phase 7: PIT 改进（P1-3, P1-4, P2-1）

### Task 21: execution_delay flush 日志增强 `[S]`

**Files:**
- Modify: `packages/engine/src/ditto_engine/backtest/engine.py`（`_execute_delayed_signal` 方法）

**Step 1: 在 flush 方法中添加 WARNING 日志**

```python
def _execute_delayed_signal(self, signal: TargetPortfolioLike) -> None:
    last_date = self._trading_days[-1] if self._trading_days else ""
    logger.warning(
        "Flush: executing delayed signal on last_date={}, "
        "actual execution may differ from intended execution_delay",
        last_date,
    )
    # ... 现有逻辑
```

**Step 2: Commit**

```bash
git commit -m "fix: execution_delay flush 添加 WARNING 日志 — 标记非精确执行 (P1-3)"
```

---

### Task 22: execution_delay 语义文档补充 `[S]`

**Files:**
- Modify: `packages/engine/CLAUDE.md`（回测引擎段落）

**Step 1: 添加 execution_delay 语义说明**

在 Backtest 关键点段落中补充：
```markdown
### execution_delay 语义
- 基于调仓日（rebalance day）计数，非自然日
- daily rebalance 模式下 1 execution_delay = 1 交易日
- weekly/monthly rebalance 模式下延迟效果与自然日不对应
- 尾部 flush 使用 last_date，为"最佳努力"执行，非 PIT 精确
```

**Step 2: Commit**

```bash
git commit -m "docs: engine CLAUDE.md 补充 execution_delay 语义说明 (P1-4)"
```

---

### Task 23: SqliteTableReader pit_columns 断言 `[S]`

**Files:**
- Modify: `packages/data/src/ditto_data/storage/base/sqlite_table_reader.py:17-22`

**Step 1: 添加断言**

```python
def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
    self._spec = spec
    self._client = client
    assert len(spec.pit_columns) >= 2, (
        f"SqliteTableSpec.pit_columns must have >= 2 elements, got {len(spec.pit_columns)}"
    )
    pit_from = spec.pit_columns[-2]
    pit_to = spec.pit_columns[-1]
```

**Step 2: Commit**

```bash
git commit -m "fix: SqliteTableReader 添加 pit_columns 长度断言 (P2-1)"
```

---

## Phase 8: 可维护性改进（P1-7~12, P2-7~11）

### Task 24: 长函数重构 — Flow 函数拆分 `[L]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/jobs/flows/daily.py:80-212`（133 行）
- Modify: `interfaces/src/ditto_interfaces/jobs/flows/eod.py:146-269`（124 行）

**Step 1: daily_ingestion_flow 提取辅助函数**

将 T1 层级提交循环 (L153-179) 和 DQC 触发 (L186-190) 提取为：
```python
def _submit_t1_ingestion(container, trade_date, source) -> list[PrefectFuture]:
    """提交 T1 层级数据获取任务."""
    ...

def _trigger_dqc(container, trade_date, source) -> PrefectFuture | None:
    """触发数据质量检查."""
    ...
```

**Step 2: eod_flow 同理提取**

将结果收集和策略编排部分提取为辅助函数。

**Step 3: 运行测试**

Run: `pixi run -e dev pytest interfaces/tests/ -v`

**Step 4: Commit**

```bash
git commit -m "refactor: Flow 函数拆分 — daily_ingestion_flow + eod_flow 提取辅助函数 (P1-7)"
```

---

### Task 25: RuntimeProvider 按职责域拆分 `[L]`

**Files:**
- Modify: `packages/data/src/ditto_data/di/runtime.py`（474 行, 48 方法）
- Create: `packages/data/src/ditto_data/di/runtime_storage.py`
- Create: `packages/data/src/ditto_data/di/runtime_service.py`

**Step 1: 分析方法分类**

将 48 个方法分为：
- Infra 类（SQLitePool 等）：`RuntimeInfraProvider`
- Storage 类（Reader/Writer 装配）：`RuntimeStorageProvider`
- Service 类（Runtime Service 装配）：`RuntimeServiceProvider`

**Step 2: 拆分创建子 Provider**

**Step 3: 组合到 RuntimeProvider**

```python
class RuntimeProvider:
    """组合子 Provider."""
    infra = RuntimeInfraProvider()
    storage = RuntimeStorageProvider()
    service = RuntimeServiceProvider()
```

**Step 4: 运行 arch-check + test**

Run: `pixi run -e dev arch-check && pixi run -e dev pytest packages/data/tests/ -v`

**Step 5: Commit**

```bash
git commit -m "refactor: RuntimeProvider 按职责域拆分为 3 个子 Provider (P1-8)"
```

---

### Task 26: MetadataService 清理向后兼容属性 `[M]`

**Files:**
- Modify: `packages/data/src/ditto_data/services/metadata_service.py:67-160+`

**Step 1: 移除 L139-155 的冗余属性保留**

**Step 2: 更新 DI 注册和测试**

测试中直接 mock 子服务接口而非原始 reader/writer。

**Step 3: 运行测试**

Run: `pixi run -e dev pytest packages/data/tests/ -v`

**Step 4: Commit**

```bash
git commit -m "refactor: MetadataService 移除向后兼容属性 — 仅保留委托子服务 (P1-9)"
```

---

### Task 27: 测试 type: ignore 减少 `[L]`

**Files:**
- 67 个测试文件中的 155 处 `# type: ignore`

**Step 1: 分析高频模式**

```bash
grep -rn "# type: ignore" packages/app/tests/ interfaces/tests/ --include="*.py" \
  | sed 's/.*# type: ignore\[\([^]]*\)\].*/\1/' | sort | uniq -c | sort -rn
```

**Step 2: 针对高频模式创建工厂函数**

- `# type: ignore[arg-type]`：引入 `_create_*_defaults()` 工厂函数
- `# type: ignore[method-assign]`：用 `cast()` 替代 MagicMock 赋值
- `# type: ignore[misc]`：修复 dataclass frozen 属性赋值

**Step 3: 逐批替换（按包分组）**

**Step 4: 运行测试**

Run: `pixi run -e dev test`

**Step 5: Commit**

```bash
git commit -m "refactor: 测试 type: ignore 减少 — 引入工厂函数和 cast (P1-10)"
```

---

### Task 28: DataStoreSettings 路径属性分组 `[M]`

**Files:**
- Modify: `packages/data/src/ditto_data/config/data_store.py:32-286`

**Step 1: 定义嵌套模型**

```python
@dataclass(frozen=True)
class MarketPaths:
    data_root: Path
    @property
    def etf_bars(self) -> Path: return self.data_root / "market" / "etf" / "bars"
    # ... 其他 market 路径

@dataclass(frozen=True)
class DataStoreSettings:
    data_root: Path
    market: MarketPaths
    capital: CapitalPaths
    fundamental: FundamentalPaths
    # ... 5-6 个嵌套模型替代 33 个 property
```

**Step 2: 更新消费者**

**Step 3: 运行测试**

Run: `pixi run -e dev test`

**Step 4: Commit**

```bash
git commit -m "refactor: DataStoreSettings 33 个 property 按域分组为嵌套模型 (P1-12)"
```

---

### Task 29: analytics/factors re-export 优化 `[S]`

**Files:**
- Modify: `packages/analytics/src/ditto_analytics/factors/__init__.py`

**Step 1: 审查消费者**

```bash
grep -rn "from ditto_analytics.factors import" packages/ interfaces/ --include="*.py" | grep -v "/tests/"
```

**Step 2: 将低频使用的 re-export 移除，消费者直接从叶模块导入**

**Step 3: Commit**

```bash
git commit -m "refactor: analytics/factors __init__.py 精简 re-export (P1-11)"
```

---

### Task 30: 测试文件过大拆分 `[L]`

**Files（>1500 行）:**
- Split: `packages/engine/tests/unit/execution/test_planner_unit.py`（1712 行）
- Split: `packages/app/tests/unit/process/ingestion/test_coordinator_unit.py`（1660 行）

**Step 1: 按被测方法分组拆分**

例如 `test_planner_unit.py` → `test_planner_routing.py` + `test_planner_validation.py`

**Step 2: 运行测试确认**

Run: `pixi run -e dev test`

**Step 3: Commit**

```bash
git commit -m "refactor: 拆分超大测试文件 — planner + coordinator (P2-7)"
```

---

### Task 31: 超长私有函数重构 `[L]`

**Files（>90 行的私有函数）:**
- `app/process/ingestion/data_writer.py:124` `_build_dataset_handlers`
- `app/query/research.py:109` `build`
- `app/process/materialization/orchestrator.py:99` `materialize`
- `data/services/metadata/instrument.py:92` `resolve_or_create_instruments_batch`
- `data/models/common.py:93` `detect_asset_class`

**Step 1: 逐一分析并提取中间步骤函数**

**Step 2: 运行测试**

Run: `pixi run -e dev test`

**Step 3: Commit**

```bash
git commit -m "refactor: 超长私有函数拆分 — 5 个 >90 行函数 (P2-8)"
```

---

### Task 32: TODO 追踪 + 注释代码清理 `[S]`

**Files:**
- `interfaces/src/ditto_interfaces/api/deps.py:22`（TODO）
- 多个测试文件中的注释代码块

**Step 1: 将 TODO 转为 Issue**

**Step 2: 移除或保留有价值的测试注释**

**Step 3: Commit**

```bash
git commit -m "chore: TODO 追踪 + 测试注释清理 (P2-3, P2-4, P2-9)"
```

---

## Phase 9: 文档 + 质量打磨（P1-22~24, P2-12~15, P2-16~19）

### Task 33: 完成计划文档归档 `[S]`

**Files:**
- Move: `docs/plans/` 下 10 个已完成计划 → `docs/plans/archive/`
- Modify: 归档文档添加 `> **状态**: Done` 标记

**Step 1: 确认已完成状态**

以下文档需要归档：
- `2026-04-10-v1-sprint-plan.md`
- `2026-04-11-v1-enhancement-plan.md`
- `2026-04-17-full-architecture-audit.md`
- `2026-04-17-full-audit-fix-plan.md`
- `2026-04-18-phase2-data-protocol-parameterization-design.md`
- `2026-04-18-phase2-data-protocol-parameterization-plan.md`
- `2026-04-19-phase3-fetcher-protocol-design.md`
- `2026-04-22-audit-fix-missing-tests.md`
- `2026-04-26-pr62-review-fixes.md`
- `2026-04-26-v1-review-fixes.md`

**Step 2: 添加 Done 状态标记 + 移动**

**Step 3: Commit**

```bash
git commit -m "docs: 10 个已完成计划文档归档 (P1-22)"
```

---

### Task 34: ADR + 架构文档状态更新 `[S]`

**Files:**
- Modify: `docs/adr/README.md`（版本号 + 最后更新日期）
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`（Draft → Accepted）

**Step 1: 更新 ADR README**

版本号更新为 v0.14.0 或删除版本号字段。

**Step 2: 更新 boundaries 文档状态**

将 `> 状态：Draft` 改为 `> 状态：Accepted`

**Step 3: Commit**

```bash
git commit -m "docs: ADR 版本更新 + boundaries 文档状态 Accepted (P1-23, P1-24)"
```

---

### Task 35: 缺失 docstring 补充 `[S]`

**Files:**
- Modify: `packages/app/src/ditto_app/process/execution/strategy_run_process.py:269,277,290`

**Step 1: 为公共工厂函数补充 docstring**

**Step 2: Commit**

```bash
git commit -m "docs: 补充 strategy_run_process 工厂函数 docstring (P2-16)"
```

---

### Task 36: config.py 魔法数字命名 `[S]`

**Files:**
- Modify: `packages/app/src/ditto_app/config.py`

**Step 1: 提取关键数字为命名常量**

```python
# Before
time_limit = 900
# After
MAX_EXECUTION_TIMEOUT_SECONDS = 900  # 15 minutes
```

**Step 2: Commit**

```bash
git commit -m "refactor: config.py 魔法数字提取为命名常量 (P2-13)"
```

---

### Task 37: Facade dict[str, Any] 返回类型收窄 `[M]`

**Files:**
- Modify: `packages/data/src/ditto_data/services/metadata_service.py`（get_universe_detail, get_filtered_universe）
- Modify: `packages/app/src/ditto_app/query/research.py`（export, build）

**Step 1: 定义返回类型 dataclass/TypedDict**

```python
@dataclass(frozen=True)
class UniverseDetail:
    universe_id: str
    name: str
    universe_type: str
    description: str | None = None
```

**Step 2: 更新 Facade 返回类型**

**Step 3: 运行测试**

Run: `pixi run -e dev test`

**Step 4: Commit**

```bash
git commit -m "refactor: Facade 返回类型从 dict[str, Any] 收窄为 dataclass (P1-17)"
```

---

### Task 38: eod_flow 返回类型 dataclass `[S]`

**Files:**
- Create: `interfaces/src/ditto_interfaces/jobs/flows/eod_types.py`
- Modify: `interfaces/src/ditto_interfaces/jobs/flows/eod.py`

**Step 1: 定义 EODResult dataclass**

```python
@dataclass(frozen=True)
class EODResult:
    date: str
    skipped: bool
    overall_status: Literal["skipped", "success", "partial"]
    ingestion: dict[str, object] | None = None
    materialization: dict[str, object] | None = None
    strategies: list[dict[str, object]] | None = None
```

**Step 2: 更新 eod_flow 返回类型**

**Step 3: Commit**

```bash
git commit -m "refactor: eod_flow 返回 EODResult dataclass 替代 dict[str, object] (P2-15)"
```

---

## 最终验证

### Task 39: 全量检查 `[M]`

**Step 1: 运行完整检查**

```bash
pixi run -e dev check
pixi run -e dev arch-check
pixi run -e dev type
```

**Step 2: 确认所有 54 项问题已修复**

**Step 3: 最终 Commit（如有遗漏修复）**

---

## 执行统计

| Phase | 任务数 | 预估工作量 | 优先级 |
|-------|--------|-----------|--------|
| 1: P0 代码缺陷 | 3 | S+S+S | 合并门禁 |
| 2: P0 类型安全 | 3 | S+M+S | 合并门禁 |
| 3: P0 文档 | 3 | S+S+S | 合并门禁 |
| 4: 异常处理 | 3 | M+S+S | 高 |
| 5: 编码规约 | 4 | S+S+S+M | 中 |
| 6: 架构改进 | 4 | M+S+S+S | 中 |
| 7: PIT 改进 | 3 | S+S+S | 中 |
| 8: 可维护性 | 9 | L+L+M+L+M+S+L+L+S | 低 |
| 9: 文档+打磨 | 7 | S+S+S+S+S+S+M | 低 |
| **合计** | **39** | **8S + 14M + 5L** | - |
