# V1 Sprint Review Fix Plan

## 概述
- Sprint: V1 Sprint | Phase: Review Fix
- 创建: 2026-04-13
- 来源: 6 维度并行审查 + 补充发现，共 16 项问题

## Context

对 `feat/v1-sprint` 分支（195+29 文件，+30,412/-780 行）执行 6 维度并行审查（架构/PIT/规约/可维护性/质量/文档），评分 A- ~ 7.5/10。补充发现 1 项功能缺陷（H1 warm-up）和 1 项契约治理问题（M1 impact_model）。本计划覆盖全部 20 项修复。

---

## 技术方案

### H1 — DataFeed 数据加载起点前扩 lookback

**问题**: `service_factory.py:151` 用 `config.start_date` 加载数据，`get_history()` 只能从已加载数据中过滤 `trade_date < as_of_date`。回测首 N 日 ts_mean/ts_std/ts_delay 等因子为 null。

**方案**: 在 `BacktestRuntimeBuilder.build_published_runtime()` 中：
1. 从 `compiled_expressions.analysis.lookback` 取最大值
2. 与 `REGIME_DEFAULT_LOOKBACK = 60`（覆盖 MomentumIndicator）取 max
3. DataFeed 的 `start_date` 向前扩展 `max_lookback` 个交易日
4. EngineConfig/trading_days 仍保持原始回测区间（仅数据加载起点提前）

**关键约束**: `ProviderBackedDataFeed.__init__` 的 `start_date` 参数控制数据加载范围，`EngineLoop` 的 `trading_days` 控制交易步进范围，两者天然解耦。

### M1 — impact_model 非法值拒绝

**问题**: 两处反序列化对非法值静默回退 `"none"`，测试夹具仍用废弃值。

**方案**: `_normalize_impact_model()` 和 `_get_impact_model()` 对非法值抛 `ValueError`。

### M2 — actual_return 返回 None

**方案**: 无 fills 时 actual_return 相关字段返回 `None`，docstring 标注为实验性功能。

---

## 任务清单

### Batch 1: 合并前必须修复 (8 项)

- [ ] Task 1: DataFeed 数据加载起点前扩 lookback `[L]`
  - 验收: 回测首日有 pre-start 历史，get_history() 返回 lookback 天数数据，trading_days 不变
  - 文件:
    - `packages/app/src/ditto_app/builders/service_factory.py`
    - `packages/app/src/ditto_app/process/execution/strategy_types.py`
    - `packages/app/src/ditto_app/process/execution/backtest_process.py`
    - `packages/app/tests/unit/builders/` (新增测试)

- [ ] Task 2: impact_model 非法值拒绝 + 测试修正 `[M]`
  - 验收: 非法值抛 ValueError，测试中无废弃值，设计文档同步
  - 文件:
    - `packages/app/src/ditto_app/builders/runtime_builder.py`
    - `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`
    - `packages/app/tests/unit/command/test_backtest_unit.py`
    - `packages/app/tests/unit/process/strategy/test_runtime_builder_unit.py`
    - `docs/plans/2026-04-11-v1-enhancement-design.md`

- [ ] Task 3: actual_return 无真实 NAV 时返回 None `[S]`
  - 验收: 无 fills 时返回 None，API model 允许 None
  - 文件:
    - `packages/app/src/ditto_app/query/comparison.py`
    - `interfaces/src/ditto_interfaces/models/trade.py`
    - `packages/app/tests/unit/query/test_comparison_unit.py`

- [ ] Task 4: except AttributeError → hasattr 前置检查 `[S]`
  - 验收: 不支持 get_history 时正常降级，不吞其他 AttributeError
  - 文件: `packages/app/src/ditto_app/process/execution/backtest_process.py`

- [ ] Task 5: pearson_correlation 从 `__all__` 移除 `[S]`
  - 验收: importlinter 无新增违规
  - 文件: `packages/engine/src/ditto_engine/backtest/replay.py`

- [ ] Task 6: 移除未使用 import 的 noqa `[S]`
  - 验收: lint 通过
  - 文件: `packages/app/src/ditto_app/providers.py`

- [ ] Task 7: TODO 从 docstring 移到函数上方 `[S]`
  - 验收: docstring 无 TODO
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py`

- [ ] Task 8: 未跟踪文档纳入提交 `[S]`
  - 验收: git status 无 untracked docs/plans/
  - 文件: `docs/plans/2026-04-12-*.md`, `docs/plans/2026-04-13-*.md`

### Batch 2: 合并后迭代修复 (11 项)

- [ ] Task 9: 跟踪误差单位修复 `[S]`
  - 验收: 单位为基点，数值合理
  - 文件: `packages/app/src/ditto_app/query/comparison.py`

- [ ] Task 10: comparison.py 重复代码提取 `_align_nav_series()` `[S]`
  - 验收: 3 处重复消除
  - 文件: `packages/app/src/ditto_app/query/comparison.py`

- [ ] Task 11: ImpactModel 归一化到 `ditto_kernel.enums` `[S]`
  - 验收: canonical source 唯一
  - 文件:
    - `packages/kernel/src/ditto_kernel/enums.py`
    - `packages/app/src/ditto_app/contracts.py`
    - `packages/engine/src/ditto_engine/alpha/specs.py`

- [ ] Task 12: 设计文档表达式示例同步 `[S]`
  - 验收: 示例可编译
  - 文件: `docs/plans/2026-04-11-v1-enhancement-design.md`

- [ ] Task 13: API Query 参数补 description `[S]`
  - 验收: Swagger UI 显示字段说明
  - 文件:
    - `interfaces/src/ditto_interfaces/api/routes/backtest.py`
    - `interfaces/src/ditto_interfaces/api/routes/strategy.py`

- [ ] Task 14: App 层文件 I/O 下沉到 Data 层 `[M]`
  - 验收: App 层无直接 Path I/O
  - 文件:
    - `packages/data/src/ditto_data/services/strategy/backtest_artifact_reader.py` (新增)
    - `packages/app/src/ditto_app/query/backtest.py`

- [ ] Task 15: Flow 对 Engine BacktestReport 依赖解耦 `[S]`
  - 验收: interfaces/jobs/ 无 ditto_engine 直接导入
  - 文件:
    - `packages/app/src/ditto_app/query/backtest.py`
    - `interfaces/src/ditto_interfaces/jobs/flows/backtest.py`

- [ ] Task 16: models/__init__.py barrel 拆分 `[M]`
  - 验收: barrel 符号数 ≤ 30
  - 文件: `interfaces/src/ditto_interfaces/models/__init__.py`

- [ ] Task 17: builtins/__init__.py barrel 拆分 `[S]`
  - 验收: barrel 符号数 ≤ 15
  - 文件: `packages/engine/src/ditto_engine/alpha/builtins/__init__.py`

- [ ] Task 18: get_history() 独立单元测试 `[S]`
  - 验收: 覆盖基本窗口、空数据、边界
  - 文件: `packages/engine/tests/unit/backtest/test_data_feed_history_unit.py` (新增)

- [ ] Task 19: ADR 补充 (架构维度扣分项) `[S]`
  - 验收: 至少 3 份核心 ADR
  - 文件: `docs/adr/` (ADR-0007 ~ ADR-0009)

### Batch 3: 后续迭代 (1 项)

- [ ] Task 20: C2C 执行模型增加 execution_delay 配置 `[L]`
  - 验收: execution_delay=1 时 T 日信号 T+1 执行
  - 文件:
    - `packages/engine/src/ditto_engine/backtest/engine.py`
    - `packages/app/src/ditto_app/process/execution/backtest_process.py`

---

## 执行顺序

```
Batch 1（合并前）
├── Task 5, 6, 7, 8  ← 独立小任务，可并行
├── Task 3            ← 独立
├── Task 4            ← 独立
├── Task 2            ← 独立
└── Task 1            ← 最复杂，需设计验证

Batch 2（合并后，可并行分组）
├── Group A: Task 9, 10, 12, 13, 17, 18  ← 独立小任务
├── Group B: Task 11                       ← ImpactModel 归一化
└── Group C: Task 14, 15, 16              ← 跨层变更

Batch 3（后续迭代）
└── Task 20
```

## 验证

```bash
# Batch 1 完成后
pixi run -e dev check           # lint + type + test --fast
pixi run -e dev arch-check      # importlinter

# Batch 2 完成后
pixi run -e dev check
pixi run -e dev arch-check
pixi run -e dev test            # 全量测试

# 最终
pixi run -e dev ci              # CI 完整检查
```
