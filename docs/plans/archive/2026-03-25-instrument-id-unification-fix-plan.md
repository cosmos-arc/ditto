# Instrument ID Unification — 审计缺陷修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 Instrument ID 语义统一重构完成后的 5 项残留缺陷，确保计划可验收通过。

**前置审计**: `docs/reviews/2026-03-25-instrument-id-unification-post-audit.md`

**Tech Stack:** Python 3.13, dataclasses, pytest, basedpyright, ruff

---

## 1. 技术方案

### 1.1 修复范围

| # | 缺陷 | 优先级 | 复杂度 | 阻塞验收 |
|---|------|--------|--------|---------|
| 1 | benchmark_id 二次 resolve | P0 | S | 是 |
| 2 | PORTFOLIO_WIDE_ID 序列化语义断裂 | P0 | S | 视下游 |
| 3 | factory display_map 透传丢失 | P1 | S | 否 |
| 4 | 外部边界 instrument_id 命名歧义 | P1 | M | 否 |
| 5 | 文档和测试旧语义残留 | P2 | S | 否 |

### 1.2 关键决策

1. **#1 修复策略**: 直接使用 `self._config.benchmark_id`（已是 canonical `InstrumentId`），删除二次 `resolve_instrument_id()` 调用。`MarketServiceDataFeedConfig.benchmark_id` 的类型契约不变（`InstrumentId | None`），所有解析职责收归 `BacktestRuntimeBuilder._resolve_benchmark()`。

2. **#2 修复策略**: 短期在 Port 层 `_persist_audit()` 中引入统一转换函数 `_instrument_id_to_token()`，将 `PORTFOLIO_WIDE_ID` 映射为 `"*"`。不改动 Core 层和 DataHub DTO 层（DTO 字段类型保持 `str`）。

3. **#3 修复策略**: `_build_backtest_options()` 改用 `replace()` 补丁式合并，避免手动罗列字段再丢；`build_backtest_service_from_catalog()` 补充从 `runtime.data_feed.display_map` 注入 `display_map`。

4. **#4 暂不修复**: 当前重构范围是"策略/回测主链统一"。`CapitalService`、API 层等外部边界属于后续 Phase，本次不做命名变更，仅在计划文档中记录。

5. **#5 修复策略**: 更新 `pipeline.py` 模块文档中 `instrument_id` 的类型描述；统一测试 fixture 中 `benchmark_id` 为 `InstrumentId` 类型。

---

## 2. 任务清单

### Task 1: 修复 benchmark 二次 resolve `[S]`

- **描述**: `MarketServiceDataFeed._load_benchmark_close_map()` 直接使用 `self._config.benchmark_id`（已是 canonical `InstrumentId`），删除对 `resolve_instrument_id()` 的二次调用。
- **文件**:
  - 修改: `apps/port/src/ditto_port/services/strategy/market_data_feed.py`
- **变更细节**:
  - `_load_benchmark_close_map()` 第 208-212 行：删除 `resolve_instrument_id()` 调用，改为 `benchmark_instrument_id = int(self._config.benchmark_id)`
  - 删除第 213-214 行的 `None` 检查（canonical ID 不可能为 None，外层已有 guard）
- **验收标准**:
  - `MarketServiceDataFeedConfig.benchmark_id` 类型仍为 `InstrumentId | None`
  - `_load_benchmark_close_map()` 不再调用 `resolve_instrument_id()`
  - `pixi run -e dev check` 通过

---

### Task 2: 补 canonical InstrumentId benchmark 回归测试 `[S]`

- **描述**: 补充测试验证当 `benchmark_id` 为 canonical `InstrumentId` 时，`benchmark_close` 正确填充。
- **文件**:
  - 修改: `apps/port/tests/unit/services/strategy/test_market_service_data_feed_unit.py`
- **变更细节**:
  - 新增测试方法 `test_canonical_benchmark_id_skips_resolve()`:
    - 构造 `benchmark_id=InstrumentId(3_000_001)` 的 config
    - 验证 `metadata_service.resolve_instrument_id` **未被调用**（或仅被 universe 查询调用，不被 benchmark 查询调用）
    - 验证 `get_slice()` 返回正确的 `benchmark_close`
- **验收标准**:
  - 新测试通过
  - 现有 `test_trading_days_and_slice_use_prev_close_and_benchmark` 仍通过
  - `pixi run -e dev test --unit` 通过

---

### Task 3: 修复 PORTFOLIO_WIDE_ID 审计序列化 `[S]`

- **描述**: 在 `BacktestService._persist_audit()` 中引入统一转换函数，将 `PORTFOLIO_WIDE_ID` 映射为 `"*"`。
- **文件**:
  - 修改: `apps/port/src/ditto_port/services/strategy/backtest_service.py`
- **变更细节**:
  - 在模块顶部新增常量 `PORTFOLIO_WIDE_TOKEN = "*"` 和辅助函数 `_instrument_id_to_token()`
  - `_persist_audit()` 第 279 行和第 292 行：`str(r.instrument_id)` → `_instrument_id_to_token(r.instrument_id)`
- **代码示例**:
  ```python
  PORTFOLIO_WIDE_TOKEN = "*"

  def _instrument_id_to_token(instrument_id: InstrumentId) -> str:
      """Core InstrumentId → 持久化 token。全组合事件映射为 '*'。"""
      if instrument_id == PORTFOLIO_WIDE_ID:
          return PORTFOLIO_WIDE_TOKEN
      return str(instrument_id)
  ```
- **验收标准**:
  - `PORTFOLIO_WIDE_ID` → `str()` 输出 `"*"` 而非 `"0"`
  - 普通标的 ID → `str()` 输出不变
  - `pixi run -e dev check` 通过

---

### Task 4: 补 portfolio-wide 审计序列化回归测试 `[S]`

- **描述**: 补充测试验证全组合风控事件在持久化时被正确转换为 `"*"`。
- **文件**:
  - 修改: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`
- **变更细节**:
  - 在现有 audit 持久化相关测试中，新增或扩展测试用例：
    - 构造包含 `PORTFOLIO_WIDE_ID` 的 `RiskScanRecord`
    - 调用 `_persist_audit()`
    - 验证传递给 `audit_service.save_risk_log()` 的 payload 中 `instrument_id == "*"`
- **验收标准**:
  - 全组合事件 payload `instrument_id` 为 `"*"`
  - 普通标的事件 payload `instrument_id` 为其 canonical ID 字符串
  - `pixi run -e dev test --unit` 通过

---

### Task 5: 修复 factory display_map 透传 `[S]`

- **描述**: `_build_backtest_options()` 保留调用方传入的 `display_map`；`build_backtest_service_from_catalog()` 从 `runtime.data_feed.display_map` 注入。
- **文件**:
  - 修改: `apps/port/src/ditto_port/services/strategy/factory.py`
- **变更细节**:
  - `_build_backtest_options()` 第 184-192 行：在 `BacktestServiceOptions(...)` 构造中补上 `display_map=options.display_map`
  - `build_backtest_service_from_catalog()` 第 143-148 行：在 fee_model 注入后，补充 display_map 注入逻辑
- **代码示例**:
  ```python
  # _build_backtest_options 补充 display_map
  return BacktestServiceOptions(
      ...,
      display_map=options.display_map,  # ← 补上
      run_service=options.run_service or self._run_service,
  )

  # build_backtest_service_from_catalog 补充 display_map 注入
  if resolved_options.display_map is None:
      resolved_options = replace(
          resolved_options,
          display_map=runtime.data_feed.display_map,
      )
  ```
- **验收标准**:
  - 调用方传入 `display_map` 时，构建的 `BacktestService` options 中保留该值
  - catalog-backed 路径自动从 `runtime.data_feed` 注入 `display_map`
  - `pixi run -e dev check` 通过

---

### Task 6: 补 factory display_map 透传回归测试 `[S]`

- **描述**: 补充测试验证 factory 构建的 BacktestService 正确透传 display_map。
- **文件**:
  - 修改: `apps/port/tests/unit/services/strategy/test_strategy_service_factory_unit.py`
- **变更细节**:
  - 新增测试 `test_build_backtest_options_preserves_display_map()`:
    - 调用 `_build_backtest_options()` 传入带 `display_map` 的 options
    - 验证返回值中 `display_map` 被保留
  - 扩展 `test_build_backtest_service_from_catalog_uses_runtime_builder()`:
    - 在 mock runtime 的 `data_feed` 上设置 `display_map`
    - 验证构建的 service options 中包含该 display_map
- **验收标准**:
  - 新测试通过
  - `pixi run -e dev test --unit` 通过

---

### Task 7: 清理测试 fixture 中字符串 benchmark `[S]`

- **描述**: 将测试中仍使用字符串 `benchmark_id` 的 fixture 统一改为 `InstrumentId` 类型。
- **文件**:
  - 修改: `apps/port/tests/unit/services/strategy/test_backtest_service_unit.py`
  - 修改: `apps/port/tests/unit/services/strategy/test_strategy_service_factory_unit.py`
  - 修改: `apps/port/tests/unit/services/strategy/test_market_service_data_feed_unit.py`
- **变更细节**:
  - `test_backtest_service_unit.py`:
    - 第 119 行 `benchmark_id="CSI300"` → `benchmark_id=InstrumentId(3_000_001)`
    - 第 126 行断言同步更新
    - 第 250 行 `benchmark_id="CSI500"` → `benchmark_id=InstrumentId(3_000_002)`
  - `test_strategy_service_factory_unit.py`:
    - 第 64 行 `benchmark_id="000300.SH"` → `benchmark_id=InstrumentId(3_000_001)`
  - `test_market_service_data_feed_unit.py`:
    - 第 103 行 `benchmark_id="000300.SH"` → `benchmark_id=InstrumentId(3_000_001)`
    - mock 的 `resolve_instrument_id` 不再需要为 benchmark 路径返回值（因为 Task 1 已删除二次 resolve）
- **验收标准**:
  - 所有测试通过
  - grep 确认测试中不再有字符串 benchmark_id 赋值给 `InstrumentId` 类型字段
  - `pixi run -e dev test --unit` 通过

---

### Task 8: 更新 pipeline.py 模块文档 `[S]`

- **描述**: 更新 `StrategyPipeline` 模块文档中 `instrument_id` 的类型描述，与实际实现（`InstrumentId(int)`）对齐。
- **文件**:
  - 修改: `packages/core/src/ditto_core/strategy/pipeline.py`
- **变更细节**:
  - 第 10 行 `instrument_id: str    — 标的 ID` → `instrument_id: InstrumentId (int) — 标的 ID`
- **验收标准**:
  - 文档与 README 和实际代码一致
  - `pixi run -e dev check` 通过

---

## 3. 执行顺序

```
Task 1 (修 benchmark resolve) ──┐
Task 3 (修 portfolio-wide 序列化) ──┤── 并行安全（无文件交叉）
Task 5 (修 factory display_map) ────┤
Task 8 (更新 pipeline 文档) ────────┘
           │
           ▼
Task 2 (benchmark 回归测试) ──┐
Task 4 (portfolio-wide 回归测试) ──┤── 依赖对应修复完成
Task 6 (factory 回归测试) ────┤
Task 7 (清理测试 fixture) ────┘
           │
           ▼
    全量验证 pixi run -e dev check
```

**依赖关系**:
- Task 2 依赖 Task 1（测试验证修复）
- Task 4 依赖 Task 3（测试验证修复）
- Task 6 依赖 Task 5（测试验证修复）
- Task 7 依赖 Task 1（清理需要 benchmark 路径已修复）

---

## 4. 风险与控制

| 风险 | 控制 |
|------|------|
| Task 1 修改后 benchmark_close 在真实数据路径下行为变化 | Task 2 的回归测试覆盖 canonical ID 路径 |
| Task 3 的 `"*"` 映射与下游消费者不兼容 | 当前无下游消费此字段，属开发阶段 |
| Task 7 清理 fixture 时引入类型不匹配 | 逐文件修改，每文件改后跑测试 |
| Task 5 factory 改动影响 catalog-backed 路径 | Task 6 覆盖该路径回归 |

---

## 5. 验收标准

### 逐任务验收

- [x] Task 1-8 各自验收标准（见上文）

### 全量验收

```bash
# 单元测试
pixi run -e dev test --unit

# 完整检查
pixi run -e dev check

# 架构边界
pixi run -e dev arch-check
```

### 语义验证

```bash
# 确认 Core 层无 benchmark resolve_instrument_id 调用
grep -r "resolve_instrument_id" packages/core/  # 应无结果

# 确认 Port 层只有 BacktestRuntimeBuilder 调用 resolve_instrument_id
grep -rn "resolve_instrument_id" apps/port/src/  # 应仅在 backtest_runtime_builder.py
```

---

## 6. 完成记录

> 执行时在此处记录进度。

### Task 1 — benchmark 二次 resolve
- 状态: [x]
- 完成时间: 2026-03-25

### Task 2 — benchmark 回归测试
- 状态: [x]
- 完成时间: 2026-03-25

### Task 3 — PORTFOLIO_WIDE_ID 序列化
- 状态: [x]
- 完成时间: 2026-03-25

### Task 4 — portfolio-wide 回归测试
- 状态: [x]
- 完成时间: 2026-03-25

### Task 5 — factory display_map 透传
- 状态: [x]
- 完成时间: 2026-03-25

### Task 6 — factory display_map 回归测试
- 状态: [x]
- 完成时间: 2026-03-25

### Task 7 — 清理测试 fixture
- 状态: [x]
- 完成时间: 2026-03-25

### Task 8 — 更新 pipeline 文档
- 状态: [x]
- 完成时间: 2026-03-25
