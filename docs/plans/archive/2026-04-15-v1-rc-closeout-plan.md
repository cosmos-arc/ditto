# V1 RC Closeout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 关闭 V1 RC 发布闸门 — 提交 Sprint 6 代码、修复 3 类实现缺口（StrategySpec 校验、API 错误统一、波动率因子补齐）。

**Architecture:** 4 个独立修复任务，无跨任务依赖，可并行执行。Task 1（Sprint 6 提交）是独立收尾；Task 2-4 是代码修复。全部完成后运行 `pixi run -e dev check` 验收。

**Tech Stack:** Python 3.12+, pydantic/dataclass, polars, FastAPI, pytest, inline-snapshot

**前置参考:** `docs/plans/2026-04-14-v1-final-enhancement-design.md`

---

## Task 1: Sprint 6 代码提交验收 `[S]`

提交 EOD Flow、CLI ops 命令、信号推送模板及其测试。

**Files:**
- Add (untracked): `interfaces/src/ditto_interfaces/jobs/flows/eod.py`
- Add (untracked): `interfaces/src/ditto_interfaces/cli/commands/ops.py`
- Add (untracked): `interfaces/tests/unit/jobs/flows/test_eod_flow_unit.py`
- Add (untracked): `interfaces/tests/unit/cli/commands/test_ops_unit.py`
- Add (untracked): `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_email.j2`
- Add (untracked): `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_telegram.j2`
- Add (untracked): `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_webhook.j2`

**Step 1: 运行测试验证未提交代码正确性**

```bash
pixi run -e dev pytest interfaces/tests/unit/jobs/flows/test_eod_flow_unit.py -v
pixi run -e dev pytest interfaces/tests/unit/cli/commands/test_ops_unit.py -v
```

Expected: 全部 PASS

**Step 2: 运行全量检查**

```bash
pixi run -e dev check
```

Expected: lint/type/test 全通过

**Step 3: 提交 Sprint 6 代码**

```bash
git add interfaces/src/ditto_interfaces/jobs/flows/eod.py \
        interfaces/src/ditto_interfaces/cli/commands/ops.py \
        interfaces/tests/unit/jobs/flows/test_eod_flow_unit.py \
        interfaces/tests/unit/cli/commands/test_ops_unit.py \
        packages/infra/src/ditto_infra/services/notification/templates/signal_trading_email.j2 \
        packages/infra/src/ditto_infra/services/notification/templates/signal_trading_telegram.j2 \
        packages/infra/src/ditto_infra/services/notification/templates/signal_trading_webhook.j2

git commit -m "$(cat <<'EOF'
feat: Sprint 6 — EOD 编排 Flow + CLI ops 命令 + 信号推送模板

- EOD pipeline: 摄取→物化→策略全链路编排，含失败处理和告警
- ops status: 数据集摄取状态查询（表格/JSON）
- ops dq: 数据质量检查（支持指定数据集或核心数据集）
- signal_trading 模板: telegram/webhook/email 三通道信号推送
EOF
)"
```

---

## Task 2: F0.4 — StrategySpec benchmark-in-universe 校验 `[M]`

当前 `StrategySpec.__post_init__` 验证了 benchmark 格式（`NNNNNN.SH|SZ`）但未校验 benchmark 是否在 universe 内。

**设计决策:** StrategySpec 的 `universe` 字段是 string（如 `"etf_core"`），不是 instruments 列表，因此无法直接做 `benchmark in universe` 交叉验证。正确做法是：对 benchmark 添加已知指数白名单校验，拒绝不在白名单中的代码。

**Files:**
- Modify: `packages/engine/src/ditto_engine/alpha/specs.py:175-198`
- Modify: `packages/engine/tests/unit/alpha/test_specs_unit.py:190+`

**Step 1: 写失败测试**

在 `packages/engine/tests/unit/alpha/test_specs_unit.py` 的 `TestStrategySpecValidation` 类中追加测试：

```python
def test_benchmark_known_index_ok(self) -> None:
    """已知指数代码应通过校验。"""
    from ditto_engine.alpha.specs import StrategySpec

    spec = StrategySpec(
        strategy_id="test",
        name="Test",
        template="etf_rotation",
        universe="etf_core",
        asset_class="etf",
        benchmark="000300.SH",  # 沪深300
        execution=ExecutionSpec(frequency="M"),
    )
    assert spec.benchmark == "000300.SH"

@pytest.mark.parametrize(
    "bad",
    ["999999.SH", "000001.SZ", "399001.SZ"],
)
def test_benchmark_unknown_index_raises(self, bad: str) -> None:
    """非已知指数代码应抛出 ValueError。"""
    import pytest
    from ditto_engine.alpha.specs import StrategySpec

    with pytest.raises(ValueError, match="benchmark.*not a known index"):
        StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="etf_core",
            asset_class="etf",
            benchmark=bad,
            execution=ExecutionSpec(frequency="M"),
        )
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/engine/tests/unit/alpha/test_specs_unit.py::TestStrategySpecValidation::test_benchmark_known_index_ok -v
pixi run -e dev pytest packages/engine/tests/unit/alpha/test_specs_unit.py::TestStrategySpecValidation::test_benchmark_unknown_index_raises -v
```

Expected: `test_benchmark_known_index_ok` PASS（000300.SH 在白名单中）；`test_benchmark_unknown_index_raises` FAIL（当前无白名单校验）

**Step 3: 实现白名单校验**

在 `packages/engine/src/ditto_engine/alpha/specs.py` 的 `StrategySpec` 类中添加已知指数白名单，并在 `__post_init__` 中校验：

在 `_BENCHMARK_RE` 定义后添加：

```python
_KNOWN_BENCHMARKS: frozenset[str] = frozenset(
    {
        # 主要宽基指数
        "000300.SH",  # 沪深300
        "000905.SH",  # 中证500
        "000852.SH",  # 中证1000
        "000016.SH",  # 上证50
        "399006.SZ",  # 创业板指
        "399673.SZ",  # 创业板50
        "000688.SH",  # 科创50
        # 行业指数
        "399986.SZ",  # 中证医疗
        "399971.SZ",  # 中证传媒
        "000932.SH",  # 中证消费
        # 策略基准
        "000001.SH",  # 上证综指
        "399001.SZ",  # 深证成指
    }
)
```

在 `__post_init__` 中 benchmark 格式校验通过后追加：

```python
# benchmark 必须是已知指数（如果非 None）
if self.benchmark is not None and self.benchmark not in self._KNOWN_BENCHMARKS:
    raise ValueError(
        f"StrategySpec.benchmark '{self.benchmark}' is not a known index. "
        + f"Known: {sorted(self._KNOWN_BENCHMARKS)}"
    )
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/engine/tests/unit/alpha/test_specs_unit.py::TestStrategySpecValidation -v
```

Expected: 全部 PASS

**Step 5: 全量验证 + 提交**

```bash
pixi run -e dev check
```

Expected: 全通过

```bash
git add packages/engine/src/ditto_engine/alpha/specs.py \
        packages/engine/tests/unit/alpha/test_specs_unit.py
git commit -m "$(cat <<'EOF'
fix: StrategySpec benchmark 校验 — 已知指数白名单

F0.4: benchmark 字段必须匹配已知指数白名单，
拒绝格式正确但不在白名单中的代码。
EOF
)"
```

---

## Task 3: F6 — 数据查询路由统一 APIError `[M]`

4 个数据查询路由文件共 10 处 `raise HTTPException`，需替换为 `APIError` 子类。

**映射规则:**

| 原始 | 替换为 |
|------|--------|
| `HTTPException(status_code=400, detail=...)` | `BadRequestError(...)` |
| `HTTPException(status_code=500, detail=...)` | `APIError(...)` |

### Task 3a: fx.py — 1 处 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/api/routes/fx.py:12,46-53`

**Step 1: 替换 import**

```python
# 删除
from fastapi import APIRouter, HTTPException

# 替换为
from fastapi import APIRouter

from ditto_interfaces.api.errors import BadRequestError
```

**Step 2: 替换异常**

```python
# 原 (L46-53)
raise HTTPException(
    status_code=400,
    detail={
        "error": "invalid_currency_pairs",
        "message": f"Invalid currency pairs: {invalid_pairs}",
        "valid_pairs": list(valid_pairs),
    },
)

# 替换为
raise BadRequestError(
    f"Invalid currency pairs: {invalid_pairs}. "
    + f"Valid pairs: {sorted(valid_pairs)}"
)
```

### Task 3b: commodity.py — 1 处 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/api/routes/commodity.py:12,50-57`

**Step 1: 替换 import**

```python
# 删除
from fastapi import APIRouter, HTTPException

# 替换为
from fastapi import APIRouter

from ditto_interfaces.api.errors import BadRequestError
```

**Step 2: 替换异常**

```python
# 原 (L50-57)
raise HTTPException(
    status_code=400,
    detail={
        "error": "invalid_commodity_codes",
        "message": f"Invalid commodity codes: {invalid_codes}",
        "valid_codes": list(valid_codes),
    },
)

# 替换为
raise BadRequestError(
    f"Invalid commodity codes: {invalid_codes}. "
    + f"Valid codes: {sorted(valid_codes)}"
)
```

### Task 3c: fundamental.py — 1 处 `[S]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/api/routes/fundamental.py:13,163-170`

**Step 1: 替换 import**

```python
# 删除
from fastapi import APIRouter, HTTPException, Query

# 替换为
from fastapi import APIRouter, Query

from ditto_interfaces.api.errors import DateRangeError
```

**Step 2: 替换异常**

```python
# 原 (L163-170)
if start_date > end_date:
    raise HTTPException(
        status_code=400,
        detail=(
            f"start_date ({start_date}) cannot be greater than "
            f"end_date ({end_date})"
        ),
    )

# 替换为
if start_date > end_date:
    raise DateRangeError(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
```

### Task 3d: source.py — 6 处 `[M]`

**Files:**
- Modify: `interfaces/src/ditto_interfaces/api/routes/source.py:15,99-150`

**Step 1: 替换 import**

```python
# 删除
from fastapi import APIRouter, Depends, HTTPException, Path

# 替换为
from fastapi import APIRouter, Depends, Path

from ditto_interfaces.api.errors import APIError, BadRequestError
```

**Step 2: 逐一替换 6 处异常**

```python
# 原 L99-102
raise HTTPException(
    status_code=400,
    detail="必须提供 ticker、standard_ticker 或 instrument_id 之一",
)
# 替换为
raise BadRequestError("必须提供 ticker、standard_ticker 或 instrument_id 之一")

# 原 L108
raise HTTPException(status_code=400, detail=str(exc)) from exc
# 替换为
raise BadRequestError(str(exc)) from exc

# 原 L111-113
raise HTTPException(
    status_code=400, detail=f"数据集 {dataset} 不支持按标的查询"
)
# 替换为
raise BadRequestError(f"数据集 {dataset} 不支持按标的查询")

# 原 L128
raise HTTPException(status_code=400, detail=str(exc)) from exc
# 替换为
raise BadRequestError(str(exc)) from exc

# 原 L131
raise HTTPException(status_code=500, detail="Failed to resolve ticker") from exc
# 替换为
raise APIError("Failed to resolve ticker") from exc

# 原 L137
raise HTTPException(status_code=400, detail=str(exc)) from exc
# 替换为
raise BadRequestError(str(exc)) from exc

# 原 L150
raise HTTPException(status_code=400, detail=str(exc)) from exc
# 替换为
raise BadRequestError(str(exc)) from exc
```

### Task 3e: 验证 + 提交 `[S]`

**Step 1: 确认无残留 HTTPException**

```bash
grep -rn "raise HTTPException" interfaces/src/ditto_interfaces/api/routes/
```

Expected: 0 匹配

**Step 2: 运行全量检查**

```bash
pixi run -e dev check
```

Expected: 全通过

**Step 3: 提交**

```bash
git add interfaces/src/ditto_interfaces/api/routes/fx.py \
        interfaces/src/ditto_interfaces/api/routes/commodity.py \
        interfaces/src/ditto_interfaces/api/routes/fundamental.py \
        interfaces/src/ditto_interfaces/api/routes/source.py
git commit -m "$(cat <<'EOF'
refactor: 数据查询路由 HTTPException → APIError 统一

F6: fx/commodity/fundamental/source 4 个路由文件共 10 处
HTTPException 替换为 BadRequestError/DateRangeError/APIError。
全库 API 路由已无裸 HTTPException 残留。
EOF
)"
```

---

## Task 4: F1 — 波动率因子补齐（+6 因子） `[M]`

当前 6 个波动率因子，设计目标 12 个。补充 6 个缺失因子。

**新增因子清单:**

| 因子 ID | 表达式逻辑 | 类型 | 说明 |
|---------|-----------|------|------|
| `volatility_60` | `ts_std(returns_1, 60) * sqrt(252)` | expression | 60 日年化波动率 |
| `volatility_120` | `ts_std(returns_1, 120) * sqrt(252)` | expression | 120 日年化波动率 |
| `parkinson_vol` | `ts_mean(log(high/low)^2, 20) * sqrt(252/4ln2)` | python | Parkinson 波动率（高低价） |
| `garman_klass_vol` | Python | python | Garman-Klass 波动率 |
| `overnight_vol` | `ts_std(open/close - 1, 20) * sqrt(252)` | expression | 隔夜波动率 |
| `intraday_vol` | `ts_std(high/low - 1, 20) * sqrt(252)` | expression | 日内波动率 |

**Files:**
- Modify: `packages/analytics/src/ditto_analytics/factors/volatility.py`
- Modify: `packages/analytics/tests/unit/factors/test_factor_definitions.py`

**Step 1: 写失败测试**

在 `packages/analytics/tests/unit/factors/test_factor_definitions.py` 的 `TestFactorCategoryCoverage` 类中修改波动率测试：

```python
def test_has_volatility_factors(self) -> None:
    """Volatility category should have at least 10 factors."""
    vol_ids = [
        k for k in ALL_FACTOR_SPECS
        if k.startswith(("vol_", "volatility_", "realized_", "beta_", "cmra", "downside_", "idio_", "parkinson_", "garman_", "overnight_", "intraday_"))
    ]
    assert len(vol_ids) >= 10, f"Expected >= 10 volatility factors, got {len(vol_ids)}: {vol_ids}"
```

同时更新 `TestTopologicalOrder.test_minimum_spec_count` 的断言：

```python
def test_minimum_spec_count(self) -> None:
    """There should be at least 119 factor specs defined (V1 RC target: 113 + 6 volatility)."""
    assert len(ALL_FACTOR_SPECS) >= 119, (
        f"Expected >= 119 factor specs, got {len(ALL_FACTOR_SPECS)}"
    )
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/analytics/tests/unit/factors/test_factor_definitions.py::TestFactorCategoryCoverage::test_has_volatility_factors -v
```

Expected: FAIL — 当前只有 6 个波动率因子

**Step 3: 实现新因子**

在 `packages/analytics/src/ditto_analytics/factors/volatility.py` 的 `VOLATILITIES` dict 中追加：

```python
"volatility_60": FactorSpec(
    id="volatility_60",
    expression="ts_std(returns_1, 60) * sqrt(252)",
    dependencies=("returns_1",),
    description="60-day annualized return volatility",
    computation_type="expression",
),
"volatility_120": FactorSpec(
    id="volatility_120",
    expression="ts_std(returns_1, 120) * sqrt(252)",
    dependencies=("returns_1",),
    description="120-day annualized return volatility",
    computation_type="expression",
),
"parkinson_vol": FactorSpec(
    id="parkinson_vol",
    expression="",
    dependencies=("high", "low"),
    description="Parkinson volatility: high-low range based estimator",
    computation_type="python",
),
"garman_klass_vol": FactorSpec(
    id="garman_klass_vol",
    expression="",
    dependencies=("open", "high", "low", "close"),
    description="Garman-Klass volatility: OHLC based estimator",
    computation_type="python",
),
"overnight_vol": FactorSpec(
    id="overnight_vol",
    expression="ts_std(open / close - 1, 20) * sqrt(252)",
    dependencies=("open", "close"),
    description="Overnight return volatility (close-to-open gap)",
    computation_type="expression",
),
"intraday_vol": FactorSpec(
    id="intraday_vol",
    expression="ts_std(high / low - 1, 20) * sqrt(252)",
    dependencies=("high", "low"),
    description="Intraday range volatility (high-low spread)",
    computation_type="expression",
),
```

**Step 4: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/analytics/tests/unit/factors/test_factor_definitions.py -v
```

Expected: 全部 PASS，波动率因子 >= 10，总因子 >= 119

**Step 5: 运行 validate_factor_specs CI gate**

```bash
pixi run -e dev pytest packages/analytics/tests/unit/factors/test_factor_definitions.py::TestFactorDefinitionsCompile -v
```

Expected: PASS — 所有 expression 因子编译成功

**Step 6: 全量验证 + 提交**

```bash
pixi run -e dev check
```

Expected: 全通过

```bash
git add packages/analytics/src/ditto_analytics/factors/volatility.py \
        packages/analytics/tests/unit/factors/test_factor_definitions.py
git commit -m "$(cat <<'EOF'
feat: 补齐波动率因子至 12 个（+6 expression/python）

F1: 新增 volatility_60/120、parkinson_vol、garman_klass_vol、
overnight_vol、intraday_vol。波动率因子覆盖 119 个，CI gate 通过。
EOF
)"
```

---

## Task 5: V1 RC 发布门禁验收 `[S]`

全部修复完成后，运行发布门禁检查。

**Step 1: 完整 CI 检查**

```bash
pixi run -e dev check
```

Expected: lint + type + test 全通过

**Step 2: 架构约束检查**

```bash
pixi run -e dev arch-check
```

Expected: 24 contracts, 0 broken, 0 warnings

**Step 3: API 一致性验证**

```bash
grep -rn "raise HTTPException" interfaces/src/ditto_interfaces/api/routes/
grep -rn "coming soon" interfaces/src/ditto_interfaces/api/routes/
```

Expected: 0 匹配（HTTPException 和 coming soon 占位均已消除）

**Step 4: 因子规格验证**

```bash
pixi run -e dev pytest packages/analytics/tests/unit/factors/test_factor_definitions.py -v
```

Expected: 全通过，>= 119 因子，9 大类覆盖

**Step 5: 更新设计文档状态**

将 `docs/plans/2026-04-14-v1-final-enhancement-design.md` 中 Sprint 6 状态更新为 Done：

```markdown
Sprint 6: EOD 运营闭环（F12 + F13 + F11）✅ Done
```

并追加：

```markdown
## 17. Closeout 修复（2026-04-15）

| 修复项 | 内容 | 状态 |
|--------|------|------|
| F0.4 补充 | benchmark 已知指数白名单校验 | Done |
| F6 补充 | 数据查询路由 HTTPException → APIError（10 处） | Done |
| F1 补充 | 波动率因子 6→12 | Done |
```

**Step 6: 提交设计文档更新**

```bash
git add docs/plans/2026-04-14-v1-final-enhancement-design.md
git commit -m "$(cat <<'EOF'
docs: V1 RC closeout — Sprint 6 Done + 缺口修复记录
EOF
)"
```

---

## 任务依赖图

```
Task 1 (Sprint 6 提交)    ─┐
Task 2 (benchmark 校验)   ─┤──→ Task 5 (发布门禁验收)
Task 3 (APIError 统一)    ─┤
Task 4 (波动率因子补齐)   ─┘
```

Task 1-4 相互独立，可并行执行。Task 5 在所有 Task 完成后执行。

## 工作量估算

| Task | 复杂度 | 新代码 | 测试 |
|------|--------|--------|------|
| Task 1 | S | 0（已实现） | 验收 |
| Task 2 | M | ~20 行 | ~15 行 |
| Task 3 | M | ~30 行 | 验收（已有集成测试覆盖） |
| Task 4 | M | ~50 行 | ~10 行 |
| Task 5 | S | 0 | 验收 |
| **合计** | | **~100 行** | |
