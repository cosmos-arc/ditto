# 能力包架构完善计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 补齐能力包架构重构的所有差距，使审计评分从 7/10 达到 10/10。

**状态:** ✅ 已完成（2026-05-02）

**基线问题:**
1. strategy→execution 依赖违规（`DEFAULT_COMMISSION_RATE`）
2. 三个旧包空壳未删（engine / app / analytics）
3. 5 个陈旧 egg-info 残留
4. analysis 测试覆盖率 39%（目标 80%+）
5. risk 测试覆盖率 50%（目标 80%+）
6. 12 个包中仅 3 个有导入边界测试
7. BrokerGateway 空壳 Protocol 无 TODO 标注

**技术栈:** Python 3.13, pixi, ruff, basedpyright, pytest, import-linter, polars

---

## Execution Rules

1. 每个 task 单独提交，提交前运行 task 内指定验证命令。
2. TDD 流程：RED → GREEN → REFACTOR。
3. 不引入长期 backward compatibility。
4. 不用 `TYPE_CHECKING` 延迟导入解决循环依赖。
5. 每次改 import 先用 `rg` 定位引用，再改，再跑 type + arch-check。

---

## Task 1: 移动交易常量到 Kernel `[M]`

**解决:** strategy→execution 依赖违规

**文件:**
- Create: `packages/kernel/src/ditto_kernel/trading.py`
- Modify: `packages/kernel/src/ditto_kernel/__init__.py`
- Modify: `packages/execution/src/ditto_execution/reality/constants.py`（改为从 kernel re-export）
- Modify: `packages/strategy/src/ditto_strategy/alpha/specs.py`
- Modify: `packages/risk/src/ditto_risk/pre_trade.py`
- Modify: `packages/application/src/ditto_application/contracts.py`
- Modify: `packages/application/src/ditto_application/builders/runtime_builder.py`
- Modify: `packages/strategy/pyproject.toml`（移除 ditto-execution 依赖）
- Modify: `.importlinter`（移除 strategy→execution ignore）

**Step 1: 创建 kernel trading 常量模块**

在 `packages/kernel/src/ditto_kernel/trading.py`:

```python
"""A 股交易领域常量。"""

__all__ = [
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
]

DEFAULT_COMMISSION_RATE: float = 0.0003
"""默认佣金费率(万分之三)。"""

DEFAULT_MIN_COMMISSION: float = 5.0
"""最低佣金(元)。"""

DEFAULT_LOT_SIZE: int = 100
"""默认最小交易单位(A股一手 = 100 股)。"""
```

在 `packages/kernel/src/ditto_kernel/__init__.py` 中添加 re-export。

**Step 2: 改写 execution constants 为 re-export**

`packages/execution/src/ditto_execution/reality/constants.py` 改为:

```python
"""执行层默认常量（从 kernel re-export）。"""

from ditto_kernel.trading import (  # noqa: F401
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)

__all__ = [
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
]
```

**Step 3: 重写所有外部导入**

```bash
rg -n "from ditto_execution.reality.constants import" packages/strategy packages/risk packages/application --type py
```

替换为:
```python
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE
```

`apps/models/backtest.py` 中的本地 `_DEFAULT_COMMISSION_RATE = 0.0003` 改为从 kernel 导入。

**Step 4: 移除 strategy 对 execution 的 pyproject 依赖**

从 `packages/strategy/pyproject.toml` 的 dependencies 中移除 `"ditto-execution"`。

**Step 5: 更新 import-linter**

移除 `.importlinter` 中 strategy-boundary 里 `ditto_strategy.alpha.specs -> ditto_execution.reality.constants` 的 ignore 条目。

**Step 6: 验证**

```bash
pixi run -e dev pytest packages/strategy/tests/unit packages/risk/tests/unit packages/kernel/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**验收标准:**
- `rg "from ditto_execution" packages/strategy/src --type py` 返回空
- `pixi run -e dev arch-check` 0 broken contracts（无 ignore 条目）
- 所有现有测试通过

---

## Task 2: 删除旧包空壳和陈旧 egg-info `[S]`

**文件:**
- Delete: `packages/engine/`（整个目录）
- Delete: `packages/app/`（整个目录）
- Delete: `packages/analytics/`（整个目录）
- Delete: `packages/platform/src/ditto_infra.egg-info/`
- Delete: `packages/application/src/ditto_app.egg-info/`

**Step 1: 确认旧包无活跃源码**

```bash
find packages/engine packages/app packages/analytics -name "*.py" -not -path "*/egg-info/*" -not -path "*/__pycache__/*"
```

预期: 无输出（或仅有空的 `__init__.py`）。

**Step 2: 删除旧包**

```bash
git rm -r packages/engine packages/app packages/analytics
```

**Step 3: 删除陈旧 egg-info**

```bash
git rm -r packages/platform/src/ditto_infra.egg-info packages/application/src/ditto_app.egg-info
```

**Step 4: 清理 __pycache__**

```bash
find packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```

**Step 5: 验证**

```bash
pixi run -e dev type
pixi run -e dev arch-check
pixi run -e dev test --fast
```

**验收标准:**
- `ls packages/engine packages/app packages/analytics 2>&1` 返回 "No such file or directory"
- `find packages -name "ditto_infra.egg-info" -o -name "ditto_app.egg-info"` 返回空
- 所有测试通过

---

## Task 3: 补充全包导入边界测试 `[M]`

**文件:**
- Create: `packages/kernel/tests/unit/test_import_boundary_unit.py`
- Create: `packages/platform/tests/unit/test_import_boundary_unit.py`
- Create: `packages/data/tests/unit/test_import_boundary_unit.py`
- Create: `packages/features/tests/unit/test_import_boundary_unit.py`
- Create: `packages/analysis/tests/unit/test_import_boundary_unit.py`
- Create: `packages/execution/tests/unit/test_import_boundary_unit.py`
- Create: `packages/backtest/tests/unit/test_import_boundary_unit.py`
- Create: `packages/application/tests/unit/test_import_boundary_unit.py`
- Create: `packages/apps/tests/unit/test_import_boundary_unit.py`
- （portfolio 和 risk 已有，跳过）

**Step 1: 编写通用模板**

每个包的边界测试包含:
1. 包可导入且 `__version__` 正确
2. 包不导入禁止依赖（用 `importlib.util.find_spec` 检测模块级隔离）

示例（kernel）:

```python
import importlib


def test_kernel_imports_successfully() -> None:
    import ditto_kernel

    assert ditto_kernel.__version__ == "0.1.0"


def test_kernel_does_not_import_platform() -> None:
    """kernel 是最底层，不应依赖任何上层包。"""
    assert importlib.util.find_spec("ditto_platform") is not None  # 平台存在
    # kernel 模块加载后不应触发 platform 的导入
    import ditto_kernel

    assert "ditto_platform" not in set(ditto_kernel.__dict__.keys())
```

示例（data）:

```python
def test_data_does_not_import_upper_packages() -> None:
    """data 是数据平面，不应导入能力包。"""
    import sys

    import ditto_data

    loaded = set(sys.modules.keys())
    forbidden = {"ditto_strategy", "ditto_portfolio", "ditto_risk", "ditto_execution", "ditto_backtest", "ditto_analysis", "ditto_application", "ditto_apps"}
    assert not (loaded & forbidden)
```

**Step 2: 为每个包创建测试**

按包的 CLAUDE.md 禁止依赖列表编写对应断言。

**Step 3: 验证**

```bash
pixi run -e dev pytest packages/*/tests/unit/test_import_boundary_unit.py -q
```

**验收标准:**
- 12 个包全部有 `test_import_boundary_unit.py`
- 所有测试通过
- 每个测试验证了该包的禁止依赖列表

---

## Task 4: Analysis 测试覆盖 — Domain + ArtifactService `[L]`

**目标:** analysis 覆盖率 39% → 65%+

**文件:**
- Modify: `packages/analysis/tests/unit/test_research_unit.py`（补齐 5 个缺失分支）
- Create: `packages/analysis/tests/unit/test_artifact_service_unit.py`

**Step 1: 补齐 domain.py 缺失分支（~6 个测试）**

在 `test_research_unit.py` 中添加:

| 测试 | 覆盖分支 |
|------|---------|
| `test_spine_spec_validate_grain_not_1d` | `grain != "1d"` → `DerivedNotImplementedError` |
| `test_spine_spec_validate_entity_key_not_instrument_id` | `entity_key != "instrument_id"` → `DerivedNotImplementedError` |
| `test_dataset_spec_validate_empty_derived_ids` | `derived_ids=()` → `DerivedValidationError` |
| `test_dataset_spec_validate_join_policy_not_left_preserving_pit` | `join_policy="inner"` → `DerivedNotImplementedError` |
| `test_dataset_spec_validate_all_valid_derived_ids` | `derived_ids=("factor.alpha",)` → 通过 |
| `test_apply_late_arrival_policy_unknown` | `policy="unknown"` → `ValueError` |

**Step 2: 编写 artifact_service 测试（~15 个测试）**

`test_artifact_service_unit.py` 使用 `tmp_path` fixture:

| 测试 | 场景 |
|------|------|
| `test_read_parquet_exists` | 文件存在，返回 DataFrame |
| `test_read_parquet_not_found` | 文件不存在，抛 FileNotFoundError |
| `test_write_parquet` | 写入文件，可被读回 |
| `test_write_parquet_creates_dirs` | 中间目录不存在时自动创建 |
| `test_export_dataset_parquet` | parquet 格式导出 |
| `test_export_dataset_csv` | csv 格式导出 |
| `test_export_dataset_feather` | feather 格式导出 |
| `test_export_dataset_unsupported` | 不支持格式 → ValueError |
| `test_read_json_valid` | 有效 JSON → dict |
| `test_read_json_not_found` | 文件不存在 → FileNotFoundError |
| `test_read_json_not_dict` | JSON 是 list → ValueError |
| `test_write_json` | 写入后验证内容和缩进 |
| `test_resolve_artifact_relative_path_found` | 匹配返回路径 |
| `test_resolve_artifact_relative_path_not_found` | 无匹配返回 None |
| `test_read_source_snapshot_ids_valid` | 正确返回 snapshot ID 列表 |

**Step 3: 验证**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/test_research_unit.py packages/analysis/tests/unit/test_artifact_service_unit.py -q
pixi run -e dev pytest packages/analysis/tests --cov=ditto_analysis --cov-report=term-missing -q
```

**验收标准:**
- artifact_service.py 覆盖率 ≥ 85%
- domain.py 覆盖率 ≥ 95%
- 全包覆盖率 ≥ 65%

---

## Task 5: Analysis 测试覆盖 — CatalogService + Storage `[L]`

**目标:** analysis 覆盖率 65% → 80%+

**文件:**
- Create: `packages/analysis/tests/unit/test_catalog_service_unit.py`
- Create: `packages/analysis/tests/unit/test_sqlite_research_reader_unit.py`
- Create: `packages/analysis/tests/unit/test_sqlite_research_writer_unit.py`

**Step 1: 编写 catalog_service 测试（~10 个测试）**

使用 `MagicMock` mock Reader/Writer Protocol:

| 测试 | 场景 |
|------|------|
| `test_constructor_stores_reader_writer` | 验证引用保存 |
| `test_save_spine_spec` | 调用 `writer.write_spine_spec` |
| `test_save_dataset_spec` | 调用 `writer.write_dataset_spec` |
| `test_save_spine_snapshot` | 调用 `writer.write_spine_snapshot` |
| `test_save_dataset_snapshot` | 调用 `writer.write_dataset_snapshot` |
| `test_get_spine_spec_found` | reader 返回记录 → 转发 |
| `test_get_spine_spec_not_found` | reader 返回 None → 转发 |
| `test_get_dataset_spec_found` | reader 返回记录 → 转发 |
| `test_get_latest_spine_snapshot` | reader 返回记录 → 转发 |
| `test_get_latest_dataset_snapshot` | reader 返回记录 → 转发 |

**Step 2: 编写 sqlite research reader 测试（~10 个测试）**

Mock `SQLiteClient.fetchone()` 返回 dict-like Row:

| 测试 | 场景 |
|------|------|
| `test_read_spine_spec_found` | Row 存在 → `ResearchSpineSpecRecord` |
| `test_read_spine_spec_not_found` | Row None → None |
| `test_read_dataset_spec_found` | Row 存在，`derived_ids` JSON 反序列化 |
| `test_read_dataset_spec_not_found` | Row None → None |
| `test_read_spine_snapshot_found` | Row 存在 → Record |
| `test_read_spine_snapshot_not_found` | Row None → None |
| `test_read_dataset_snapshot_found` | Row 存在，版本/输入反序列化 |
| `test_read_dataset_snapshot_not_found` | Row None → None |
| `test_get_latest_spine_snapshot` | ORDER BY DESC 验证 |
| `test_get_latest_dataset_snapshot` | ORDER BY DESC 验证 |

**Step 3: 编写 sqlite research writer 测试（~10 个测试）**

Mock `SQLiteClient.execute/commit/rollback`:

| 测试 | 场景 |
|------|------|
| `test_commit` | 调用 `sqlite_client.commit()` |
| `test_rollback` | 调用 `sqlite_client.rollback()` |
| `test_execute_spine_spec` | SQL + 8 元素参数正确 |
| `test_execute_dataset_spec` | SQL 正确，`derived_ids` 序列化为 JSON |
| `test_execute_spine_snapshot` | SQL + 9 元素参数正确 |
| `test_execute_dataset_snapshot` | SQL 正确，版本/输入/快照序列化 |
| `test_write_spine_spec` | execute + commit |
| `test_write_dataset_spec` | execute + commit |
| `test_write_spine_snapshot` | execute + commit |
| `test_write_dataset_snapshot` | execute + commit |

**Step 4: 验证**

```bash
pixi run -e dev pytest packages/analysis/tests --cov=ditto_analysis --cov-report=term-missing -q
```

**验收标准:**
- analysis 全包覆盖率 ≥ 80%
- 所有新测试通过
- 无 `# noqa` 或 `# type: ignore` 在测试文件中

---

## Task 6: Risk 测试覆盖 — Validation + PreTrade Context `[L]`

**目标:** risk 覆盖率 50% → 65%+

**文件:**
- Create: `packages/risk/tests/unit/test_validation_unit.py`
- Create: `packages/risk/tests/unit/test_pre_trade_context_unit.py`
- Create: `packages/risk/tests/unit/test_no_short_sell_check_unit.py`
- Create: `packages/risk/tests/unit/test_price_validity_check_unit.py`
- Create: `packages/risk/tests/unit/test_lot_size_check_unit.py`
- Create: `packages/risk/tests/unit/test_buying_power_check_unit.py`

**Step 1: 编写 _validation 测试（~6 个测试）**

| 测试 | 场景 |
|------|------|
| `test_valid_weight` | 0.5 通过 |
| `test_weight_one` | 1.0 通过（上界） |
| `test_weight_zero` | 0.0 → ValueError |
| `test_weight_negative` | -0.1 → ValueError |
| `test_weight_over_one` | 1.5 → ValueError |
| `test_custom_name_in_error` | 错误消息包含自定义 name |

**Step 2: 编写 PreTradeContext 测试（~12 个测试）**

构造最小化的 frozen dataclass fixtures:

| 测试 | 场景 |
|------|------|
| `test_price_for_found` | 有 snapshot → close |
| `test_price_for_not_found` | 无 snapshot → None |
| `test_lot_size_for_found` | 有 rules → lot_size |
| `test_lot_size_for_default` | 无 rules → DEFAULT_LOT_SIZE |
| `test_fee_schedule_for_found` | 有 rules → schedule |
| `test_fee_schedule_for_default` | 无 rules → 默认 |
| `test_estimate_order_cost` | quantity * price + fee |
| `test_with_order_accepted_buy` | BUY: 扣 cash, 增 pending_buy_value |
| `test_with_order_accepted_sell` | SELL: 减 available_quantity |
| `test_with_order_accepted_sell_insufficient` | SELL 超量仍创建上下文 |
| `test_total_value_calculation` | cash + sum(position market_value) |
| `test_nav_equals_total_value` | nav = total_value |

**Step 3: 编写各 PreTradeChecker 测试（~22 个测试）**

每个 Checker 独立测试文件，覆盖正常/边界/拒绝路径。

**NoShortSellCheck:**
| 测试 | 场景 |
|------|------|
| `test_buy_accepted` | BUY 始终接受 |
| `test_sell_no_position_rejected` | 无持仓 → REJECT |
| `test_sell_insufficient_rejected` | 持仓不足 → REJECT |
| `test_sell_sufficient_accepted` | 持仓充足 → ACCEPT |

**PriceValidityCheck:**
| 测试 | 场景 |
|------|------|
| `test_market_order_accepted` | MARKET → ACCEPT |
| `test_no_snapshot_accepted` | 无行情 → ACCEPT |
| `test_no_limits_accepted` | 无涨跌停 → ACCEPT |
| `test_price_within_range` | 价格合理 → ACCEPT |
| `test_price_above_limit_rejected` | 超涨停 → REJECT |

**LotSizeCheck:**
| 测试 | 场景 |
|------|------|
| `test_sell_accepted` | SELL → ACCEPT |
| `test_zero_lot_size_accepted` | lot_size <= 0 → ACCEPT |
| `test_valid_lot_multiple` | 整数倍 → ACCEPT |
| `test_invalid_lot_resized` | 非整数倍 → RESIZE |
| `test_resize_rounds_up` | 向上取整到下一手 |

**BuyingPowerCheck:**
| 测试 | 场景 |
|------|------|
| `test_sell_accepted` | SELL → ACCEPT |
| `test_sufficient_power` | 资金充足 → ACCEPT |
| `test_insufficient_power` | 资金不足 → REJECT |
| `test_exact_power` | 刚好够 → ACCEPT |

**Step 4: 验证**

```bash
pixi run -e dev pytest packages/risk/tests/unit -q
pixi run -e dev pytest packages/risk/tests --cov=ditto_risk --cov-report=term-missing -q
```

**验收标准:**
- risk 覆盖率 ≥ 65%
- 所有新测试通过
- PreTradeContext 所有分支覆盖

---

## Task 7: Risk 测试覆盖 — PostTrade + Composite `[L]`

**目标:** risk 覆盖率 65% → 80%+

**文件:**
- Create: `packages/risk/tests/unit/test_concentration_pre_check_unit.py`
- Create: `packages/risk/tests/unit/test_daily_turnover_pre_check_unit.py`
- Create: `packages/risk/tests/unit/test_composite_pre_trade_check_unit.py`
- Create: `packages/risk/tests/unit/test_max_drawdown_rule_unit.py`
- Create: `packages/risk/tests/unit/test_single_loss_limit_rule_unit.py`
- Create: `packages/risk/tests/unit/test_concentration_limit_rule_unit.py`
- Create: `packages/risk/tests/unit/test_market_anomaly_rule_unit.py`
- Create: `packages/risk/tests/unit/test_composite_post_trade_guard_unit.py`

**Step 1: PreTrade 补充（~16 个测试）**

**ConcentrationPreCheck:**
| 测试 | 场景 |
|------|------|
| `test_sell_accepted` | SELL → ACCEPT |
| `test_nav_zero_accepted` | nav <= 0 → ACCEPT |
| `test_no_price_accepted` | 无价格 → ACCEPT |
| `test_over_limit_rejected` | 超权重 → REJECT |
| `test_within_limit_accepted` | 权重内 → ACCEPT |

**DailyTurnoverPreCheck:**
| 测试 | 场景 |
|------|------|
| `test_sell_accepted` | SELL → ACCEPT |
| `test_nav_zero_accepted` | nav <= 0 → ACCEPT |
| `test_over_limit_rejected` | 超换手率 → REJECT |
| `test_within_limit_accepted` | 换手率内 → ACCEPT |
| `test_pending_tickets_included` | pending 金额计入 |

**CompositePreTradeCheck:**
| 测试 | 场景 |
|------|------|
| `test_all_pass` | 全部通过 → ACCEPT |
| `test_reject_short_circuits` | REJECT 立即返回 |
| `test_resize_rechecks` | RESIZE 触发重新检查 |
| `test_resize_loop_detected` | 超过 3 次 RESIZE → REJECT |
| `test_multiple_resizes` | 连续 RESIZE 最终 ACCEPT |
| `test_accept_with_resize_quantity` | RESIZE 后 ACCEPT 携带新数量 |

**Step 2: PostTrade 测试（~27 个测试）**

**MaxDrawdownRule:**
| 测试 | 场景 |
|------|------|
| `test_no_drawdown` | 持续上涨 → 无动作 |
| `test_warning_threshold` | 达到 warning → ALERT |
| `test_emergency_threshold` | 达到 emergency → LIQUIDATE |
| `test_reset_clears_peak` | reset 后 peak 清零 |
| `test_peak_updates_only_on_new_high` | peak 只在新高时更新 |
| `test_zero_nav_returns_empty` | nav = 0 → 空列表 |
| `test_invalid_thresholds_rejected` | warning >= emergency → ValueError |

**SingleLossLimitRule:**
| 测试 | 场景 |
|------|------|
| `test_no_loss` | 无亏损 → 空列表 |
| `test_loss_below_threshold` | 亏损超限 → REDUCE_POSITION |
| `test_no_bar_data_skipped` | 无行情跳过 |
| `test_threshold_zero_rejected` | threshold <= 0 → ValueError |

**ConcentrationLimitRule:**
| 测试 | 场景 |
|------|------|
| `test_within_limit` | 权重内 → 空列表 |
| `test_over_limit` | 超限 → ALERT |
| `test_zero_nav` | nav = 0 → 空列表 |

**MarketAnomalyRule:**
| 测试 | 场景 |
|------|------|
| `test_no_anomaly` | 正常波动 → 空列表 |
| `test_anomaly_detected` | 异常波动 → ALERT |
| `test_zero_prev_close_skipped` | prev_close = 0 跳过 |
| `test_threshold_zero_rejected` | threshold <= 0 → ValueError |

**CompositePostTradeGuard:**
| 测试 | 场景 |
|------|------|
| `test_no_actions` | 所有规则无动作 → 空列表 |
| `test_collects_all_actions` | 多规则触发 → 合并 |
| `test_fires_callbacks` | callback 被调用 |
| `test_reset_resets_all` | reset 传播到所有子规则 |

**Step 3: 验证**

```bash
pixi run -e dev pytest packages/risk/tests --cov=ditto_risk --cov-report=term-missing -q
```

**验收标准:**
- risk 覆盖率 ≥ 80%
- pre_trade.py 覆盖率 ≥ 85%
- post_trade.py 覆盖率 ≥ 85%
- 所有新测试通过

---

## Task 8: BrokerGateway TODO 标注 + 文档更新 `[S]`

**文件:**
- Modify: `packages/execution/src/ditto_execution/broker/contracts.py`
- Modify: `packages/strategy/pyproject.toml`（确认 strategy→portfolio 合法）
- Modify: `.importlinter`（显式声明 strategy→portfolio 合法依赖）
- Modify: `packages/strategy/CLAUDE.md`

**Step 1: 添加 BrokerGateway TODO**

在 `packages/execution/src/ditto_execution/broker/contracts.py`:

```python
"""券商网关契约。"""

from __future__ import annotations

from typing import Protocol


class BrokerGateway(Protocol):
    """Boundary for real and simulated broker implementations.

    TODO: 在对接真实券商时 flesh out 方法签名（submit_order, cancel_order, query_fills 等）。
    当前为占位 Protocol，等 execution 包订单模型稳定后再设计完整接口。
    """
```

**Step 2: 确认 strategy→portfolio 合法依赖**

在 `packages/strategy/CLAUDE.md` 的"允许依赖"中显式列出 `ditto-portfolio`，并添加注释:

```markdown
## 允许依赖

ditto_strategy → ditto_kernel ✅
ditto_strategy → ditto_data ✅
ditto_strategy → ditto_features ✅
ditto_strategy → ditto_portfolio ✅ （策略模板作为完整交易配方，需要引用分配器和约束类型）

## 技术债务

strategy 模板当前直接引用 portfolio 的 allocation/constraints 类型。
长期演进方向：策略只产信号，分配方案由 application 层独立配置。
参见 LEAN 架构的 AlphaModel → PortfolioConstructionModel 解耦模式。
```

**Step 3: 更新 import-linter**

在 `.importlinter` 的 `strategy-boundary` contract 中，确保 `ditto_portfolio` 不在 forbidden 列表中。

**Step 4: 验证**

```bash
pixi run -e dev arch-check
pixi run -e dev type
```

**验收标准:**
- BrokerGateway 有 TODO 注释
- strategy CLAUDE.md 明确记录 strategy→portfolio 依赖及演进方向
- arch-check 通过

---

## Task 9: 最终验证和提交 `[S]`

**Step 1: 运行完整 CI 门禁**

```bash
pixi run -e dev check
```

预期:
```
ruff check . -> All checks passed
ruff format . -> files unchanged
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all pass
import-linter -> all contracts kept
architecture smell check passed
```

**Step 2: 运行覆盖率检查**

```bash
pixi run -e dev pytest packages/analysis/tests --cov=ditto_analysis --cov-fail-under=80 -q
pixi run -e dev pytest packages/risk/tests --cov=ditto_risk --cov-fail-under=80 -q
```

预期: 两个包均 ≥ 80%。

**Step 3: 确认所有差距已补齐**

```bash
# 无旧包残留
ls packages/engine packages/app packages/analytics 2>&1 | grep "No such"

# 无陈旧 egg-info
find packages -name "ditto_infra.egg-info" -o -name "ditto_app.egg-info"

# 无 strategy→execution 违规
rg "from ditto_execution" packages/strategy/src --type py

# 导入边界测试完整
ls packages/*/tests/unit/test_import_boundary_unit.py | wc -l  # 预期 12
```

**Step 4: 提交**

```bash
git add -A
git commit -m "refactor: complete capability package architecture — fill all audit gaps"
```

**验收标准:**
- `pixi run -e dev check` 全部通过
- analysis 覆盖率 ≥ 80%
- risk 覆盖率 ≥ 80%
- 0 个旧包残留
- 0 个陈旧 egg-info
- 0 个 strategy→execution 违规
- 12 个导入边界测试全部存在且通过
- arch-check 0 broken contracts

---

## 实施注意事项

### 执行顺序
1. **Task 1**（常量移动）必须在其他测试任务之前，因为它改变了 kernel 包
2. **Task 2**（删除旧包）可以与 Task 1 并行，但建议在 Task 1 之后做以保持干净状态
3. **Task 3**（边界测试）可以在任何时间点做，不依赖其他任务
4. **Task 4-5**（analysis 测试）可以与 Task 6-7（risk 测试）并行
5. **Task 8**（文档更新）可以在任何时间点做
6. **Task 9**（最终验证）必须最后

### 覆盖率策略
- 优先覆盖有业务逻辑的模块（pre_trade.py, post_trade.py, artifact_service.py）
- 纯 re-export 的 `__init__.py` 和空 `contracts.py` 通过导入边界测试间接覆盖
- 测试中使用 frozen dataclass fixtures，避免 mock 过度

### 已知技术债务（记录但不在本计划解决）
1. **strategy→portfolio 耦合**: 策略模板直接引用 portfolio 类型，长期应演进为 LEAN 式解耦架构
2. **BrokerGateway 空壳**: 等真实券商对接时 flesh out
3. **runtime/ 空目录**: application/runtime/ 为预留目录，等运行时抽象需求明确后再填充
