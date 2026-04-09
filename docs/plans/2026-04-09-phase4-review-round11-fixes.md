# Phase 4 Code Review Round 11 — 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复代码审查发现的 3 个违规 + 33 个建议项，涵盖文档一致性、代码质量、可维护性、类型安全。

**Architecture:** 分 9 个 Task，按风险递增排序：文档修复 → 代码卫生 → DRY 重构 → 类型安全强化。每个 Task 独立提交，可并行。

**Tech Stack:** Python 3.12+ / basedpyright / ruff / pytest

---

## Task 1: AGENTS.md + 设计文档违规修复 `[S]`

**Files:**
- Modify: `AGENTS.md:137-147,225-234`
- Modify: `docs/plans/2026-04-09-re-export-governance-design.md:73,102-103`

**Step 1: AGENTS.md 禁止事项表补充 3 条 re-export 规则**

在 `AGENTS.md` 禁止事项表（line 147 之后）添加：
```markdown
| 跨包 re-export | 隐藏真实依赖（详见 python.md Re-export 规范） |
| `__init__.py` 混合 re-export + 内联定义 | 分离到独立模块 |
| re-export 链深度 > 2 层 | 消费者直接引用叶模块 |
```

**Step 2: AGENTS.md Never do 列表补充 3 条 re-export 规则**

在 `AGENTS.md` Never do 列表（line 234 之后）添加：
```markdown
- 跨包 re-export（隐藏真实依赖，详见 [python.md](.claude/rules/python.md) Re-export 规范）
- `__init__.py` 中混合 re-export 与内联定义（必须分离到独立模块）
- re-export 链深度超过 2 层（消费者必须直接引用叶模块）
```

**Step 3: 设计文档 P0 测试迁移数量修正**

`docs/plans/2026-04-09-re-export-governance-design.md` line 73，将 "3 个测试文件已迁移" 修正为 "4 个测试文件已迁移"（包括 `test_factor_definitions.py`）。

**Step 4: 设计文档 P3 文件名修正**

`docs/plans/2026-04-09-re-export-governance-design.md` line 102，将 `_registry.py` 修正为 `factor_specs.py`。

**Step 5: 设计文档 P3 BrokerageModel 描述修正**

`docs/plans/2026-04-09-re-export-governance-design.md` line 103，将描述修正为：删除（`BrokerageModel` 已在 `brokerage.py` 中定义，barrel 中的重复定义被删除）。

**Step 6: Commit**

```bash
git add AGENTS.md docs/plans/2026-04-09-re-export-governance-design.md
git commit -m "docs: Phase 4 Review R11 — AGENTS.md 同步 re-export 规则 + 设计文档修正"
```

---

## Task 2: architecture.md + .importlinter 文档更新 `[S]`

**Files:**
- Modify: `.claude/rules/architecture.md:92,94`
- Modify: `.importlinter:163-169`

**Step 1: architecture.md 第 5 项补充 App**

将 line 92:
```
5. **Analytics 隔离** (`forbidden`): Analytics 禁止依赖 Data（除 errors）/Engine
```
改为:
```
5. **Analytics 隔离** (`forbidden`): Analytics 禁止依赖 Data（除 errors）/Engine/App
```

**Step 2: architecture.md 第 7 项补充 services/models**

将 line 94:
```
7. **Interfaces 边界** (`forbidden`): Interfaces 非 registry 禁止依赖 storage/runtime
```
改为:
```
7. **Interfaces 边界** (`forbidden`): Interfaces 非 registry 禁止依赖 storage/runtime/services/models/errors/quality/config
```

**Step 3: .importlinter 注释补充隐式依赖说明**

在 `analytics-no-app-dependency` 合约注释中补充：
```
注意：App → Analytics 方向由分层架构隐式允许（无对应 forbidden 合约）。
```

**Step 4: Commit**

```bash
git add .claude/rules/architecture.md .importlinter
git commit -m "docs: Phase 4 Review R11 — architecture.md 检查类型描述补全"
```

---

## Task 3: 代码卫生 — Unused Import + 注释 + 文档路径 `[S]`

**Files:**
- Modify: `packages/app/src/ditto_app/process/quality_protocols.py:15`
- Modify: `packages/app/src/ditto_app/process/quality_l3.py:195`
- Modify: `packages/app/src/ditto_app/process/quality.py:1`
- Modify: `docs/plans/2026-04-09-any-usage-audit-and-rules.md`

**Step 1: 移除 quality_protocols.py 未使用的 Literal 导入**

`quality_protocols.py` line 15，将：
```python
from typing import Any, Literal, Protocol
```
改为：
```python
from typing import Any, Protocol
```

**Step 2: quality_l3.py 英文注释改中文**

`quality_l3.py` line 195，将：
```python
        # Calculate start date with buffer for weekends
```
改为：
```python
        # 计算包含周末/假日缓冲的起始日期
```

**Step 3: quality.py shim 添加迁移计划注释**

`quality.py` line 1，将 docstring 改为：
```python
"""质量服务 — re-export shim（向后兼容，计划下一迭代迁移消费者后删除）.

当前消费者（10 处）：
- 生产代码：providers.py, ingestion_config.py, coordinator_factory.py, interfaces/registry
- 测试代码：test_providers_unit.py, test_service_unit.py, test_l3_batch_unit.py,
  test_golden_unit.py, test_reconciliation_service_unit.py
"""
```

**Step 4: any-usage-audit-and-rules.md 路径改为完整路径**

检查 B 类列表中的相对路径（如 `infra/.../tracing.py:65`），改为完整路径。

**Step 5: 验证**

```bash
pixi run -e dev lint
pixi run -e dev type --tests
```

**Step 6: Commit**

```bash
git add packages/app/src/ditto_app/process/quality_protocols.py \
       packages/app/src/ditto_app/process/quality_l3.py \
       packages/app/src/ditto_app/process/quality.py \
       docs/plans/2026-04-09-any-usage-audit-and-rules.md
git commit -m "fix: Phase 4 Review R11 — 代码卫生清理（unused import + 注释统一 + shim 迁移计划）"
```

---

## Task 4: _spec_deserializer DRY 消除 + field_name 补全 + 测试补全 `[M]`

**Files:**
- Modify: `packages/app/src/ditto_app/builders/_spec_deserializer.py`
- Modify: `packages/app/src/ditto_app/builders/runtime_builder.py`（调用方适配）
- Test: `packages/app/tests/unit/builders/test_spec_deserializer_unit.py`

**Step 1: read_str_value 委托到 read_required_str 消除重复**

`_spec_deserializer.py` line 111-116，将 `read_str_value` 改为委托：
```python
def read_str_value(raw_value: object, *, field_name: str) -> str:
    """读取字符串值（委托 read_required_str，入参形式不同）."""
    return read_required_str({field_name: raw_value}, field_name)
```

**Step 2: read_optional_str 增加 field_name 参数**

`_spec_deserializer.py` line 101-108，修改签名：
```python
def read_optional_str(raw_value: object, *, field_name: str = "字段") -> str | None:
    """读取可选字符串字段."""
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        msg = f"{field_name} 必须是字符串"
        raise ValueError(msg)
    return raw_value
```

同步更新 `__all__` 和 runtime_builder.py 中 `read_optional_str` 的调用点（如有传 field_name）。

**Step 3: as_object_dict 补充 docstring 说明 None value**

在 `as_object_dict` docstring 中补充：
```python
"""校验对象形态并返回 ``dict[str, object]``。

允许 value 为 ``None``（下游通过 ``read_optional_*`` 处理）。
"""
```

**Step 4: 补充测试 — read_optional_str**

在 `test_spec_deserializer_unit.py` 中添加：
```python
class TestReadOptionalStr:
    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert read_optional_str(None, field_name="x") is None

    @pytest.mark.unit
    def test_valid_string(self) -> None:
        assert read_optional_str("hello", field_name="x") == "hello"

    @pytest.mark.unit
    def test_empty_string_returns_value(self) -> None:
        assert read_optional_str("", field_name="x") == ""

    @pytest.mark.unit
    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是字符串"):
            read_optional_str(42, field_name="x")
```

**Step 5: 补充测试 — read_str_value**

```python
class TestReadStrValue:
    @pytest.mark.unit
    def test_valid_string(self) -> None:
        assert read_str_value("hello", field_name="x") == "hello"

    @pytest.mark.unit
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是非空字符串"):
            read_str_value("", field_name="x")

    @pytest.mark.unit
    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是非空字符串"):
            read_str_value(42, field_name="x")
```

**Step 6: 更新 test imports**

在 test 文件 import 中添加 `read_optional_str` 和 `read_str_value`。

**Step 7: 验证**

```bash
pixi run -e dev test packages/app/tests/unit/builders/test_spec_deserializer_unit.py -v
pixi run -e dev lint
pixi run -e dev type
```

**Step 8: Commit**

```bash
git add packages/app/src/ditto_app/builders/_spec_deserializer.py \
       packages/app/tests/unit/builders/test_spec_deserializer_unit.py
git commit -m "refactor: Phase 4 Review R11 — spec_deserializer DRY 消除 + 测试补全"
```

---

## Task 5: _write_capital Dict 映射模式重构 `[S]`

**Files:**
- Modify: `packages/app/src/ditto_app/process/data_writer.py:490-515`

**Step 1: 重构 _write_capital 为 dict 映射**

将 `data_writer.py` 中的 `_write_capital` 方法里的 if-elif 链替换为 dict 映射，与 `_write_fundamental` 保持风格一致：
```python
        capital_methods = {
            "valuation_metrics": self._capital_service.save_valuation_metrics,
            "margin_trading": self._capital_service.save_margin_trading,
            "pledge_ratio": self._capital_service.save_pledge_ratio,
        }
        save_method = capital_methods.get(capital_dataset)
        if save_method is None:
            valid = ", ".join(capital_methods)
            raise ValueError(
                f"Unknown capital_dataset: {capital_dataset}. Expected: {valid}"
            )
        records_written = save_method(enriched_df)
```

**Step 2: 验证**

```bash
pixi run -e dev test packages/app/tests/unit/process/ -k "capital" -v
pixi run -e dev lint
```

**Step 3: Commit**

```bash
git add packages/app/src/ditto_app/process/data_writer.py
git commit -m "refactor: Phase 4 Review R11 — _write_capital 统一 dict 映射模式"
```

---

## Task 6: quality_reconciliation 类型收窄 `[M]`

**Files:**
- Modify: `packages/app/src/ditto_app/process/quality_reconciliation.py:179,282-298`

**Step 1: 修复 unique().to_list() 返回类型**

`quality_reconciliation.py` line 179，将：
```python
        tickers = primary_df["ticker"].unique().to_list()
```
改为：
```python
        tickers = primary_df["ticker"].unique().cast(pl.String).to_list()
```

注意：需要确认 pyright 对 `to_list()` 的推断。如果 `.cast(pl.String)` 仍不解决问题，改用 `cast("list[str]", ...)`.

**Step 2: _convert_result_to_df 使用 dict[str, object] 替代 dict[str, Any]**

`quality_reconciliation.py` line 282-298，将：
```python
        rows: list[dict[str, Any]] = []
        ...
            row: dict[str, Any] = {
```
改为：
```python
        rows: list[dict[str, object]] = []
        ...
            row: dict[str, object] = {
```

这样与 D1 类 Any 收敛方向一致，且所有值（str, int）都是 object 的子类型。

**Step 3: 验证**

```bash
pixi run -e dev type
pixi run -e dev test packages/app/tests/unit/process/quality/test_reconciliation_service_unit.py -v
```

**Step 4: Commit**

```bash
git add packages/app/src/ditto_app/process/quality_reconciliation.py
git commit -m "fix: Phase 4 Review R11 — quality_reconciliation 类型收窄（Any → object）"
```

---

## Task 7: L3CheckResult Dataclass 定义 + 历史窗口注释 `[M]`

**Files:**
- Create: `packages/app/src/ditto_app/process/quality_types.py`
- Modify: `packages/app/src/ditto_app/process/quality_l3.py`
- Modify: `packages/app/src/ditto_app/process/quality.py`（re-export shim）
- Test: `packages/app/tests/unit/process/quality/test_l3_batch_unit.py`

**Step 1: 定义 L3CheckResult dataclass**

创建 `quality_types.py`：
```python
"""L3 检查结果类型."""

from __future__ import annotations

__all__ = ["L3CheckResult"]

from dataclasses import dataclass, field

from ditto_kernel.quality import DQIssue


@dataclass(frozen=True)
class L3CheckResult:
    """L3 批量检查结果（强类型）."""

    dataset: str
    trade_date: str
    passed: bool
    issue_count: int
    alert_count: int = 0
    issues: tuple[DQIssue, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None
```

**Step 2: quality_l3.py 使用 L3CheckResult**

更新 `check_dataset` 和 `_format_check_result` 返回类型为 `L3CheckResult`。

`_handle_check_error` 返回：
```python
    return L3CheckResult(
        dataset=dataset,
        trade_date=trade_date,
        passed=False,
        issue_count=0,
        error=f"{type(error).__name__}: {error!s}",
    )
```

`_format_check_result` 返回：
```python
    return L3CheckResult(
        dataset=dataset,
        trade_date=trade_date,
        passed=result.passed,
        issue_count=len(result.issues),
        alert_count=result.alert_count,
        issues=tuple(result.issues),
    )
```

**Step 3: quality_l3.py _fetch_data 添加历史窗口注释**

在 `_fetch_data` 的 `end=trade_date` 处添加注释：
```python
        # end=trade_date 包含当日数据（与 current 重叠），这是预存行为。
        # 引擎内部使用 historical 构建参考分布时需排除 current 行。
        # TODO: 考虑 end=trade_date 前一天以避免参考分布污染。
```

**Step 4: quality.py shim 添加 L3CheckResult re-export**

在 `quality.py` 的 `__all__` 和 import 中添加 `L3CheckResult`。

**Step 5: 更新测试**

更新 `test_l3_batch_unit.py` 中的断言，使用 `L3CheckResult` 属性替代 dict key 访问。同时更新 `conftest.py` 中的 mock 返回值。

**Step 6: 验证**

```bash
pixi run -e dev test packages/app/tests/unit/process/quality/ -v
pixi run -e dev type
pixi run -e dev lint
```

**Step 7: Commit**

```bash
git add packages/app/src/ditto_app/process/quality_types.py \
       packages/app/src/ditto_app/process/quality_l3.py \
       packages/app/src/ditto_app/process/quality.py \
       packages/app/tests/unit/process/quality/
git commit -m "refactor: Phase 4 Review R11 — L3CheckResult dataclass + 历史窗口注释"
```

---

## Task 8: test_commodity_fetcher @patch 合并 + type:ignore 消除 `[S]`

**Files:**
- Modify: `packages/app/tests/unit/process/test_commodity_fetcher_unit.py`

**Step 1: 将 @patch 提取到类级别 autouse fixture**

将 5 个测试方法中重复的 `@patch(METAL_CODE_ALIASES)` 和 `@patch(VIX_CODE_TO_INSTRUMENT_ID)` 提取为 `autouse=True` 的 fixture：

```python
@pytest.fixture(autouse=True)
def _patch_code_mappings(self) -> None:
    with (
        patch(
            "ditto_app.process._commodity_fetcher.METAL_CODE_ALIASES",
            {"COMMOD_GOLD": "XAUUSD.FXCM", "COMMOD_SILVER": "XAGUSD.FXCM"},
        ),
        patch(
            "ditto_app.process._commodity_fetcher.VIX_CODE_TO_INSTRUMENT_ID",
            {"VIX_30D": 5_100_001},
        ),
    ):
        yield
```

删除所有测试方法上的 `@patch` 装饰器（每个方法减少 ~12 行）。

**Step 2: 消除 type:ignore — 优化 _make_sources 签名**

将 `_make_sources` 参数类型改为更精确的联合类型，消除 `_UNSET` sentinel 带来的 type:ignore：
```python
_UNSET: object = object()

def _make_sources(
    *,
    fred_df: pl.DataFrame | Exception | None | object = _UNSET,
    metal_df: pl.DataFrame | Exception | None | object = _UNSET,
) -> tuple[MagicMock, MagicMock | None]:
```

在赋值处使用 `cast` 替代 `# type: ignore`：
```python
    _metal: pl.DataFrame | Exception = cast(
        "pl.DataFrame | Exception",
        _make_metal_df() if metal_df is _UNSET else metal_df,
    )
```

如果 cast 仍不够精确，可保留 `# type: ignore[arg-type]` 但在注释中说明原因。

**Step 3: 验证**

```bash
pixi run -e dev test packages/app/tests/unit/process/test_commodity_fetcher_unit.py -v
pixi run -e dev type --tests
```

**Step 4: Commit**

```bash
git add packages/app/tests/unit/process/test_commodity_fetcher_unit.py
git commit -m "refactor: Phase 4 Review R11 — commodity_fetcher 测试 @patch 合并 + type:ignore 消除"
```

---

## Task 9: CommandHandler Protocol @runtime_checkable 注释 `[S]`

**Files:**
- Modify: `packages/app/src/ditto_app/command/protocols.py:12`

**Step 1: 添加 @runtime_checkable 选择理由注释**

在 `protocols.py` 的 `@runtime_checkable` 装饰器前添加注释：
```python
# runtime_checkable 允许 isinstance() 检查，用于 DI 容器路由。
# 注意：泛型 Protocol 的 runtime_checkable 仅检查方法是否存在，不检查参数类型。
```

**Step 2: 验证**

```bash
pixi run -e dev lint
```

**Step 3: Commit**

```bash
git add packages/app/src/ditto_app/command/protocols.py
git commit -m "docs: Phase 4 Review R11 — CommandHandler @runtime_checkable 注释"
```

---

## 完成验证

所有 Task 完成后运行完整验证：

```bash
pixi run -e dev check
```

**分支门禁：**
- [ ] basedpyright 0 errors
- [ ] ruff All checks passed
- [ ] tests passed
- [ ] 覆盖率 ≥ 80%

---

## 任务汇总

| Task | 类型 | 复杂度 | 文件数 | 涉及项 |
|------|------|--------|--------|--------|
| 1 | 文档违规 | S | 2 | V1, V2, V3, D6 |
| 2 | 文档建议 | S | 2 | D1, D2, D4 |
| 3 | 代码卫生 | S | 4 | C1, C5, M4, D5 |
| 4 | DRY + 测试 | M | 3 | M1, C7, C8, T1 |
| 5 | 风格统一 | S | 1 | M2 |
| 6 | 类型收窄 | M | 1 | C3, C4 |
| 7 | 类型强化 | M | 4 | C2, P1 |
| 8 | 测试重构 | S | 1 | M3, T2 |
| 9 | 文档注释 | S | 1 | C6 |

**依赖关系：** 所有 Task 独立，可并行执行。Task 7 依赖 Task 3（quality.py shim 需先添加 L3CheckResult re-export）。

**执行建议：** Task 1-3 为文档/卫生修复，可快速完成；Task 4-9 涉及代码变更，需要测试验证。
