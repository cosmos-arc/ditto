# V1 Sprint 修复计划

## 概述

- **来源**: V1 Sprint 偏差分析（Phase 0-3 实现审查）
- **创建**: 2026-04-11
- **范围**: 8 项偏差修复 — 2 个 Bug + 3 个功能缺失 + 3 个增强
- **目标**: 将 V1 Sprint 完成度从 ~92% 提升到 100%

## 问题清单

| # | 问题 | 类型 | 优先级 | Phase |
|---|------|------|--------|-------|
| F1 | Position UPSERT 缺失 — 重复写入 UNIQUE 冲突 | Bug | P0 | Phase 2 |
| F2 | T+1 日历未注入 — ManualTracker 冻结逻辑不生效 | Bug | P1 | Phase 2 |
| F3 | 基准 NAV 未注入报告响应 | 缺失 | P1 | Phase 1 |
| F4 | Comparison API 缺失 — 计算逻辑无路由暴露 | 缺失 | P1 | Phase 2 |
| F5 | settlement_date 未计算 — fill record 始终为空 | 缺失 | P2 | Phase 2 |
| F6 | Signal API 缺失 — 信号快照未暴露 | 缺失 | P2 | Phase 2 |
| F7 | Run 分页未下沉 — 全量加载后截取 | 增强 | P2 | Phase 1 |
| F8 | Strategy Update 无乐观锁 — 并发更新冲突 | 增强 | P2 | Phase 1 |

## 技术方案

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Position 重复写入 | `INSERT OR REPLACE` | SQLite 原生支持，snapshot_id 是 PK，语义等价于"最新快照覆盖旧值" |
| T+1 日历注入方式 | DI Provider 加载 MetadataService → 传入交易日历 tuple | ManualTracker 构造函数已支持 trading_calendar 参数 |
| 基准 NAV 暴露 | 在 report 响应中增加 benchmark_nav_series 字段 | 数据已在 backtest_report.json（alpha_stats），只需 API 层透出 |
| Comparison API 位置 | app/query/comparison.py + interfaces routes/trade.py | 纯查询操作，归 query 层 |
| settlement_date | ManualExecutionFill DTO 增加 settlement_date 字段 | 保持 DTO/Record 对称，fill_to_record 直接传递 |
| Signal API | app/query/signal.py（新增 facade）+ interfaces routes/trade.py | 查询信号和意图，归 query 层 |
| Run 分页 | limit/offset 下沉到 strategy_run_store SQL | 数据层原生分页，避免全量加载 |
| 乐观锁 | UpdateStrategyHandler 检查 command.version == existing.version | 标准乐观锁模式 |

---

## Batch 1: 基础修复（无跨依赖）

### F1. Position UPSERT 修复 `[S]`

**问题**: `TradeService.save_position` 只有 INSERT。`RecordFillHandler._recompute_positions` 重复调用时，确定性 `snapshot_id` 导致 UNIQUE 约束冲突。

**方案**: 将 `_INSERT_POSITION` SQL 改为 `INSERT OR REPLACE`。snapshot_id 是确定性 UUID5（strategy_id:snapshot_date:instrument_id），语义上"同一策略+日期+标的的持仓取最新值"，INSERT OR REPLACE 完全匹配。

**验收**:
- `save_position` 使用 `INSERT OR REPLACE` 而非 `INSERT`
- 同一 snapshot_id 重复写入不报错，后写入覆盖先写入
- 现有单元测试全部通过
- 新增测试覆盖重复写入场景

**文件**:
- 修改: `packages/data/src/ditto_data/services/trade_service.py`（1 行 SQL）
- 修改: `packages/data/tests/unit/services/test_trade_service_unit.py`（新增测试）

---

### F7. Run 分页下沉 `[S]`

**问题**: `StrategyRunService.list_runs` 返回全量记录，API 层 Python 切片分页。数据量大时内存浪费。

**方案**: 在 `SQLiteStrategyRunStore` SQL 层支持 `LIMIT/OFFSET`，逐层传递。

**验收**:
- `strategy_run_store.list_runs` 支持 `limit`/`offset` 参数
- `StrategyRunService.list_runs` 透传 `limit`/`offset`
- `RunReadModel.list_runs` 透传 `limit`/`offset`
- `BacktestQueryFacade.list_runs` 透传 `limit`/`offset`
- API 路由不再做 Python 切片，直接传参
- 现有测试通过 + 新增分页测试

**文件**:
- 修改: `packages/data/src/ditto_data/storage/metadata/strategy_run_store.py`（SQL + 参数）
- 修改: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`（透传参数）
- 修改: `packages/app/src/ditto_app/query/run.py`（透传参数）
- 修改: `packages/app/src/ditto_app/query/backtest.py`（透传参数）
- 修改: `interfaces/src/ditto_interfaces/api/routes/backtest.py`（移除 Python 切片）
- 修改: `packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py`

---

### F8. Strategy Update 乐观锁 `[S]`

**问题**: `UpdateStrategyHandler` 接受 `command.version` 但仅用于 `version + 1`，不校验现有版本一致性。并发更新可能导致覆盖。

**方案**: Handler 先读取现有策略，检查 `existing.version == command.version`，不匹配则抛出 ValueError。

**验收**:
- UpdateStrategyHandler 在更新前校验版本号
- 版本冲突时抛出 ValueError（含清晰的冲突信息）
- 现有测试通过 + 新增版本冲突测试

**文件**:
- 修改: `packages/app/src/ditto_app/command/strategy.py`（增加版本校验）
- 修改: `packages/app/tests/unit/command/test_strategy_unit.py`（新增测试）

---

## Batch 2: T+1 交收链（F2 → F5 依赖）

### F2. T+1 日历注入 `[M]`

**问题**: `AppProcessProvider.manual_tracker()` 未传入 `trading_calendar`，ManualTracker 构造时默认空 tuple，导致 `compute_settlement_date` 直接返回 `trade_date`，T+1 冻结逻辑完全失效。

**方案**:
1. `AppProcessProvider` 注入 `MetadataService`
2. 在 `manual_tracker()` provider 方法中，加载一个足够大的交易日历范围（如 2020-01-01 到 2030-12-31）
3. 转为 tuple 传入 ManualTracker

**注意**: MetadataService 需要在 Data 层 DI 中已注册。交易日历加载是启动时一次性操作，不在请求热路径。

**验收**:
- ManualTracker 实例持有非空 trading_calendar
- `compute_settlement_date("2024-01-02", cycle=1)` 返回正确的 T+1 日期
- `_compute_single_instrument` 中 T+1 冻结逻辑正常工作
- 现有 ManualTracker 测试全部通过（测试构造时传入 calendar）
- DI 注册测试验证 calendar 非空

**文件**:
- 修改: `packages/app/src/ditto_app/providers.py`（manual_tracker provider 注入 MetadataService）
- 修改: `packages/app/tests/unit/process/execution/test_manual_tracker_unit.py`（已有测试应覆盖）

---

### F5. settlement_date 计算 `[M]`

**问题**: `ManualExecutionFill` DTO 缺少 `settlement_date` 字段，`fill_to_record` 映射后 record 的 `settlement_date` 始终为空字符串。

**方案**:
1. `ManualExecutionFill` DTO 增加 `settlement_date: str = ""` 字段
2. `fill_to_record` 映射时传递 `settlement_date`
3. `RecordFillHandler.handle()` 在构建 DTO 前，调用 `self._tracker.compute_settlement_date(command.trade_date)` 计算交收日期
4. 构建 DTO 时传入计算结果

**验收**:
- ManualExecutionFill DTO 包含 settlement_date 字段
- fill_to_record 映射传递 settlement_date
- RecordFillHandler 在录入成交时计算并设置 settlement_date
- 无交易日历时 settlement_date 回退为 trade_date
- 新增单元测试覆盖

**文件**:
- 修改: `packages/app/src/ditto_app/types.py`（DTO 增加字段 + 映射更新）
- 修改: `packages/app/src/ditto_app/command/trade.py`（Handler 计算 settlement_date）
- 修改: `packages/app/tests/unit/command/test_trade_unit.py`
- 修改: `interfaces/src/ditto_interfaces/models/trade.py`（Pydantic 模型增加字段）

---

## Batch 3: API 暴露（F3/F4/F6 无跨依赖）

### F3. 基准 NAV 注入 `[M]`

**问题**: `BacktestQueryFacade.get_report()` 返回原始 JSON dict，未提取基准相关数据。Sprint 计划要求基准 NAV 通过读模型路径注入报告。

**方案**:
1. 在 `BacktestQueryFacade` 增加依赖 `MarketQueryFacade`（或 `MetadataService`），用于获取基准指数 NAV
2. 在 `get_report()` 返回前，检查 report 中是否已有 benchmark 数据
3. 若无，从基准指数（如沪深 300 ETF）的历史 NAV 自动构建并注入
4. API 响应增加 `benchmark_nav_series` 字段

**简化方案**（推荐）: backtest_report.json 已包含 alpha_stats，alpha_stats 含 benchmark_total_return 等字段（如果回测时传了 benchmark_navs）。API 层只需：
1. 在 `RunResponse` 增加 `benchmark_return: float | None` 字段
2. `BacktestQueryFacade` 从报告 alpha_stats 中提取 benchmark 字段
3. 新增 `GET /api/v1/backtests/runs/{id}/benchmark` 端点返回基准 NAV 序列

**验收**:
- RunResponse 包含 benchmark_return 字段（从 alpha_stats 提取）
- 新增 benchmark NAV 序列查询端点
- 无基准数据时返回 None（不报错）
- 单元测试覆盖

**文件**:
- 修改: `interfaces/src/ditto_interfaces/models/backtest.py`（RunResponse 增加字段）
- 修改: `packages/app/src/ditto_app/query/backtest.py`（提取 benchmark 字段）
- 修改: `interfaces/src/ditto_interfaces/api/routes/backtest.py`（新增端点）
- 新增/修改测试

---

### F4. Comparison API `[M]`

**问题**: `compute_comparison` / `ComparisonMetrics` 已完整实现（11 个指标），但无 QueryFacade 封装、无 API 路由、无 DI 注册。用户无法通过 API 获取回测 vs 实际对比报告。

**方案**:
1. 新增 `ComparisonQueryFacade` 在 `app/query/comparison.py`（注意: query 层可导入 engine 类型 ✅，DTO 从 `ditto_app.types` 导入）
2. Facade 接受 `BacktestQueryFacade` + `PortfolioActualQueryFacade` + `ManualTracker` 依赖
3. 编排: 获取回测报告 → 获取实际持仓/成交 → 调用 compute_comparison
4. 新增 API 端点 `GET /api/v1/trade/comparison`
5. 新增 Pydantic 模型 `ComparisonResponse`
6. DI 注册

**验收**:
- `ComparisonQueryFacade` 封装完整对比流程
- `GET /api/v1/trade/comparison?strategy_id=...&run_id=...` 返回 ComparisonMetrics
- DI 注册完整
- 单元测试覆盖正常路径和空数据路径

**文件**:
- 新建: `packages/app/src/ditto_app/query/comparison.py`
- 修改: `interfaces/src/ditto_interfaces/api/routes/trade.py`（新增端点）
- 修改: `interfaces/src/ditto_interfaces/models/trade.py`（ComparisonResponse）
- 修改: `packages/app/src/ditto_app/providers.py`（DI 注册）
- 修改: `packages/app/src/ditto_app/query/__init__.py`（re-export）
- 新增: `packages/app/tests/unit/query/test_comparison_unit.py`

---

### F6. Signal API `[M]`

**问题**: `SignalSnapshotProcess` 未通过 API 暴露。Sprint 计划要求 `GET /api/v1/signals/latest` 和 `GET /api/v1/signals/{id}/intents`。

**方案**:
1. 新增 `SignalQueryFacade` 在 `app/query/signal.py`（查询已保存的 intents）
2. 利用现有 `TradeQueryFacade`/`TradeService` 查询 intents
3. 新增 API 端点：
   - `GET /api/v1/trade/signals/latest?strategy_id=...` — 返回最新信号日期的 intents
   - `GET /api/v1/trade/signals/{signal_date}/intents?strategy_id=...` — 返回指定日期的 intents
4. 路由注册在 trade.py（复用 prefix）

**注意**: Sprint 计划中的 `GET /api/v1/signals/latest` 路径调整为 `/api/v1/trade/signals/latest`，与现有 trade 路由一致。

**验收**:
- `SignalQueryFacade` 查询最新/指定日期的 intents
- 两个 API 端点可用
- DI 注册完整
- 单元测试覆盖

**文件**:
- 新建: `packages/app/src/ditto_app/query/signal.py`
- 修改: `interfaces/src/ditto_interfaces/api/routes/trade.py`（新增端点）
- 修改: `packages/app/src/ditto_app/providers.py`（DI 注册）
- 修改: `packages/app/src/ditto_app/query/__init__.py`（re-export）
- 新增: `packages/app/tests/unit/query/test_signal_unit.py`

---

## 依赖关系图

```
Batch 1（并行，无依赖）:
  F1 Position UPSERT ─────┐
  F7 Run 分页下沉 ────────┤
  F8 Strategy 乐观锁 ─────┤
                          │
Batch 2（F2 → F5 依赖）:  │
  F2 T+1 日历注入 ──→ F5 settlement_date
                          │
Batch 3（并行，无依赖）:  │
  F3 基准 NAV ────────────┤
  F4 Comparison API ──────┤  (依赖 F1: Position UPSERT 修复后才能可靠计算)
  F6 Signal API ──────────┘

F1 → F4: Comparison API 依赖正确的持仓数据（UPSERT 修复后）
F2 → F5: settlement_date 计算依赖日历注入
```

## 任务统计

| Batch | 任务数 | S | M | 新增文件 | 修改文件 |
|-------|--------|---|---|---------|---------|
| 1 | 3 | 3 | 0 | 0 | ~8 |
| 2 | 2 | 0 | 2 | 0 | ~5 |
| 3 | 3 | 0 | 3 | ~3 | ~6 |
| **合计** | **8** | **3** | **5** | **~3** | **~19** |

## 完成验证

```bash
pixi run -e dev check    # lint + fmt + type + test --fast  ✅ ALL PASSED
pixi run -e dev arch-check  # 23/24 contracts KEPT (1 pre-existing .process→.command cycle)
```

**验收 Gate**:
- [x] Position 重复写入不报错（F1）
- [x] ManualTracker T+1 冻结逻辑生效（F2）
- [x] fill record settlement_date 非空（F5）
- [x] Run 列表分页在 SQL 层完成（F7）
- [x] Strategy Update 版本冲突报错（F8）
- [x] 回测报告包含 benchmark 数据（F3）
- [x] Comparison API 返回 11 个指标（F4）
- [x] Signal API 返回最新/指定日期的 intents（F6）
- [x] 所有现有测试通过（无回归）

**实施备注**:
- F4 ComparisonMetrics + compute_comparison_from_raw 移至 query/comparison.py，消除 R8 query→process 违规
- process/execution/comparison.py 保留 compute_comparison（BacktestReport 版）并通过 re-export 保持兼容
- backtest.py get_benchmark_return 使用 try/except 替代 isinstance(dict) 缩窄，避免 pyright Unknown 类型问题
