# PR #62 Code Review 修复计划

## 概述
- Sprint: V1 Sprint | Phase: Code Review Fixes
- 创建: 2026-04-13
- PR: cosmos-arc/ditto#62
- 总计: 12 个问题 (评分 >= 25), 14 个任务

## 问题总览

| # | 问题 | 评分 | 复杂度 | 分组 |
|---|------|------|--------|------|
| 1 | `# noqa: S101` in frame.py | 75 | S | CLAUDE.md |
| 2 | `# noqa: RUF100` in trade.py | 100 | S | CLAUDE.md |
| 3 | `# noqa: S105` in signal_delivery.py | 50 | S | CLAUDE.md |
| 4 | `# type: ignore` in backtest route | 50 | S | CLAUDE.md |
| 5 | `# type: ignore` in command/backtest.py | 50 | S | CLAUDE.md |
| 6 | `# type: ignore` in signal_snapshot.py | 50 | S | CLAUDE.md |
| 7 | `TYPE_CHECKING` polars in contracts.py | 100 | S | CLAUDE.md |
| 8 | `types.py` 违反命名规范 | 100 | L | 结构 |
| 9 | barrel 超过 30 符号限制 | 75 | M | 结构 |
| 10 | `services/` 目录未在 CLAUDE.md 文档化 | 50 | S | 结构 |
| 11 | `_build_actual_navs` 占位逻辑 | 50 | L | 逻辑 |
| 12 | `list_runs` offset 无 limit 时忽略 | 25 | S | 逻辑 |
| 13 | 冗余 RUNNING 状态设置 | 50 | S | 逻辑 |
| 14 | 跟踪误差公式含无意义年化/去年化 | 50 | M | 逻辑 |

## 技术方案

### 跟踪误差 (Issue #14)

**业界标准** ([CFA Institute](https://analystprep.com/study-notes/cfa-level-iii/tracking-error/), [Quant.SE](https://quant.stackexchange.com/questions/63866)):
1. 计算日均超额收益: `excess_i = r_portfolio_i - r_benchmark_i`
2. 计算超额收益标准差: `TE_daily = std(excess)`
3. 年化跟踪误差: `TE_annual = TE_daily * sqrt(252)`

当前字段名 `avg_daily_tracking_error_bps` 语义为"日均 TE (基点)"，当前代码做了 `* sqrt(252) / sqrt(252)` 的无意义操作。

**修正**: 直接计算 `sqrt(te_var) * 10000.0`，移除虚假年化步骤。字段名与"日均"语义一致，无需修改字段名。

### NAV 重建 (Issue #11)

从 fills 重建 NAV 需要逐日盯市。`_build_actual_navs` 需要注入行情查询能力。

**方案**:
1. `ComparisonQueryFacade` 注入 `MarketQueryFacade` 获取日收盘价
2. 从 fills 重建持仓台账 (cash + positions)
3. 每个交易日: `NAV = cash + sum(position_qty * close_price)`
4. 无交易的日子继承前一日 NAV（使用最近已知收盘价）

## 任务清单

### Phase 1: CLAUDE.md 合规 (noqa / type:ignore / TYPE_CHECKING)

- [ ] T1: 替换 `assert` 为 `raise ValueError` 移除 noqa S101 `[S]`
  - 验收: `packages/engine/src/ditto_engine/alpha/frame.py:52` 无 noqa 注释
  - 文件: `packages/engine/src/ditto_engine/alpha/frame.py`
  - 方案: `if missing: raise ValueError(f"DecisionFrame missing required columns: {missing}")`
  - 测试: 现有 `test_validate_frame` 应覆盖

- [ ] T2: 移除未使用的 import + noqa RUF100 `[S]`
  - 验收: `interfaces/src/ditto_interfaces/api/routes/trade.py:19` 无 noqa，无未使用 import
  - 文件: `interfaces/src/ditto_interfaces/api/routes/trade.py`
  - 方案: 删除 `from ditto_app.query.signal import SignalQueryFacade  # noqa: RUF100`
  - 风险: 确认该 import 确实未使用

- [ ] T3: 处理 noqa S105 环境变量名常量 `[S]`
  - 验收: `interfaces/src/ditto_interfaces/registry/infra/signal_delivery.py` 无 noqa S105
  - 文件: `interfaces/src/ditto_interfaces/registry/infra/signal_delivery.py`
  - 方案: 在 `pyproject.toml` 的 ruff 配置中添加 `per-file-ignores` 或使用 `noqa: S105` 对应的正确处理。环境变量名（非实际密钥）是 Bandit 已知误报，最佳做法是在 ruff 配置中针对此模式添加允许规则: `extend-per-line-ignores = ["S105 *"]` 或重构为 `_BOT_TOKEN_ENV: str = "TELEGRAM_BOT_TOKEN"` 并在 ruff 配置 `lint.bandit.hardcoded-tmp-string.extend_checks` 中排除
  - 备选: 如果 S105 误报仅此一处，在 `pyproject.toml` 中 `extend-safe-globs` 或 `check-hardcoded-password-string` 配置

- [ ] T4: 消除 backtest route 的 type:ignore `[S]`
  - 验收: `interfaces/src/ditto_interfaces/api/routes/backtest.py` 无 `# type: ignore`
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py`
  - 方案: 用 `Callable[..., Any]` 显式类型包装 `_prefect_fn`，或提取类型化参数避免 `**dict[str, object]` 展开

- [ ] T5: 消除 command/backtest.py 的 type:ignore `[S]`
  - 验收: `packages/app/src/ditto_app/command/backtest.py` 无 `# type: ignore`
  - 文件: `packages/app/src/ditto_app/command/backtest.py`
  - 方案: 将 `spec_json.get()` 结果先赋值给 `list[object]` 类型变量再迭代，消除 pyright 的 `reportUnknownArgumentType`
  - 测试: 现有 `test_backtest_command` 应覆盖

- [ ] T6: 消除 signal_snapshot.py 的 type:ignore `[S]`
  - 验收: `packages/app/src/ditto_app/process/execution/signal_snapshot.py` 无 `# type: ignore`
  - 文件: `packages/app/src/ditto_app/process/execution/signal_snapshot.py`
  - 方案: 使用 `InstrumentId(int(iid))` 作为 dict key，而非 `int(iid)` 后裸用。或者修改 positions dict 的 key 类型为 `int`
  - 测试: 现有测试应覆盖

- [ ] T7: 移除 contracts.py 冗余 TYPE_CHECKING 守卫 `[S]`
  - 验收: `packages/app/src/ditto_app/contracts.py` 无 `TYPE_CHECKING` 相关代码
  - 文件: `packages/app/src/ditto_app/contracts.py`
  - 方案: 移除 `from typing import TYPE_CHECKING` 和 `if TYPE_CHECKING: import polars as pl`，将 `import polars as pl` 放到顶层 import 区
  - 测试: 现有测试应覆盖

### Phase 2: 结构/命名修复

- [ ] T8: 将 `types.py` 重命名为 `execution_dto.py` `[L]`
  - 验收: 不存在 `packages/app/src/ditto_app/types.py`；所有 import 路径更新
  - 文件: `packages/app/src/ditto_app/types.py` → `packages/app/src/ditto_app/execution_dto.py` + 17 个消费文件
  - 方案:
    1. `git mv packages/app/src/ditto_app/types.py packages/app/src/ditto_app/execution_dto.py`
    2. 全局替换 `from ditto_app.types` → `from ditto_app.execution_dto`
    3. 更新 `__init__.py` 如果有 re-export
  - 消费文件清单:
    - `packages/app/src/ditto_app/query/trade.py`
    - `packages/app/src/ditto_app/query/portfolio_actual.py`
    - `packages/app/src/ditto_app/query/comparison.py`
    - `packages/app/src/ditto_app/query/signal.py`
    - `packages/app/src/ditto_app/command/trade.py`
    - `packages/app/src/ditto_app/process/execution/comparison.py`
    - `packages/app/src/ditto_app/process/execution/delivery.py`
    - `packages/app/src/ditto_app/process/execution/signal_snapshot.py`
    - `packages/app/src/ditto_app/process/execution/ports.py`
    - `packages/app/src/ditto_app/process/execution/manual_tracker.py`
    - `interfaces/src/ditto_interfaces/api/routes/trade.py`
    - `interfaces/tests/integration/api/test_trade_api_integration.py`
    - `packages/app/tests/unit/query/test_comparison_unit.py`
    - `packages/app/tests/unit/command/test_trade_unit.py`
    - `packages/app/tests/unit/process/execution/test_manual_tracker_unit.py`
    - `packages/app/tests/unit/process/execution/test_comparison_unit.py`
    - `packages/app/tests/unit/process/execution/test_delivery_unit.py`
  - 测试: `pixi run -e dev test` 全量通过

- [ ] T9: 拆分 query/__init__.py barrel (31 → ≤30) `[M]`
  - 验收: `packages/app/src/ditto_app/query/__init__.py` 导出 <= 30 个符号
  - 文件: `packages/app/src/ditto_app/query/__init__.py`
  - 方案: 将 `TradeRecord` 移到 `backtest_trade.py` 模块直接导出（而非通过 barrel re-export），消费方直接 `from ditto_app.query.backtest_trade import TradeRecord`
  - 替选: 移除 `SignalQueryFacade`（已在 `signal.py` 直接导出）

- [ ] T10: 更新 interfaces/CLAUDE.md 文档化 services/ 目录 `[S]`
  - 验收: `interfaces/CLAUDE.md` 模块结构包含 `services/` 目录
  - 文件: `interfaces/CLAUDE.md`
  - 方案: 在模块结构树中添加 `├── services/  # Port 实现`，更新说明

### Phase 3: 逻辑/缺陷修复

- [ ] T11: 实现完整 NAV 重建 `_build_actual_navs` `[L]`
  - 验收: `_build_actual_navs` 从 fills 正确重建 NAV 序列（含持仓市值 + 现金）
  - 文件:
    - `packages/app/src/ditto_app/query/comparison.py`
    - `packages/app/src/ditto_app/query/portfolio_actual.py` (可能需新增价格查询方法)
  - 方案:
    1. `ComparisonQueryFacade.__init__` 注入 `MarketQueryFacade`
    2. `_build_actual_navs` 签名扩展: 接收 `fills` + `instrument_ids` + `date_range` + `price_query`
    3. 从 fills 逐日构建 cash/positions 台账
    4. 对交易日序列查询收盘价，计算 `NAV = cash + sum(qty * close)`
    5. 无交易的日子: `NAV = prev_cash + sum(qty * close)`
    6. 更新 `ComparisonQueryFacade.get_comparison` 传递价格查询
  - 测试: 新增单元测试 `test_build_actual_navs_from_fills` 覆盖:
    - 纯买入场景
    - 买卖混合场景
    - 多标的场景
    - 部分成交/T+1 冻结

- [ ] T12: 修复 `list_runs` offset 无 limit 时被忽略 `[S]`
  - 验收: `list_runs(offset=50)` 正确应用 OFFSET
  - 文件: `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`
  - 方案: 将 `if offset is not None and limit is not None:` 改为 `if offset is not None:`，OFFSET 独立于 LIMIT
  - 注意: SQLite 要求 OFFSET 必须有 LIMIT。需要添加默认 LIMIT (如 1000) 当只有 OFFSET 无 LIMIT 时
  - 测试: 新增或扩展测试验证 `offset` 单独使用

- [ ] T13: 移除 flow 中冗余 RUNNING 状态设置 `[S]`
  - 验收: `interfaces/src/ditto_interfaces/jobs/flows/backtest.py` 不再手动设置 RUNNING
  - 文件: `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`
  - 方案: 删除 `writer.update_status(run_id, _status_str(RunStatus.RUNNING))` 及关联的 `writer` 变量提取。BacktestService 内部已管理 PENDING → RUNNING 转换
  - 测试: 现有回测集成测试应覆盖

- [ ] T14: 修正跟踪误差公式，移除无意义年化 `[M]`
  - 验收: `_compute_tracking_error_bps` 直接计算日均 TE，无虚假年化步骤
  - 文件: `packages/app/src/ditto_app/query/comparison.py`
  - 方案:
    ```python
    # 修正前（无意义年化）:
    annualized_te = math.sqrt(te_var) * math.sqrt(_TRADING_DAYS_PER_YEAR)
    return annualized_te * 10_000.0 / math.sqrt(_TRADING_DAYS_PER_YEAR)

    # 修正后（直接日均）:
    return math.sqrt(te_var) * 10_000.0
    ```
  - 文档: 更新注释说明计算方法与 CFA/业界标准一致
  - 测试: 更新现有测试验证 TE 值的正确性

## 执行顺序

```
Phase 1 (T1-T7): CLAUDE.md 合规 — 可并行
  ├── T1, T2, T3: noqa 修复 (独立)
  ├── T4, T5, T6: type:ignore 修复 (独立)
  └── T7: TYPE_CHECKING 修复 (独立)

Phase 2 (T8-T10): 结构修复 — 串行
  ├── T8: types.py 重命名 (影响最广，先执行)
  ├── T9: barrel 拆分
  └── T10: CLAUDE.md 文档更新

Phase 3 (T11-T14): 逻辑修复 — 串行
  ├── T14: TE 公式修正 (简单，先执行)
  ├── T12: offset 修复 (简单)
  ├── T13: RUNNING 状态修复 (简单)
  └── T11: NAV 重建 (最复杂，最后执行)
```

## 验收标准

```bash
# 每个任务完成后
pixi run -e dev check

# 全部完成后
pixi run -e dev ci
```
