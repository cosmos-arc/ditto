> **Status**: Superseded by [2026-04-13-v1-review-fix-plan.md](./2026-04-13-v1-review-fix-plan.md)

# V1 Sprint Review Fixes — 修复设计

> 日期：2026-04-13
> 范围：Review Finding #1-#5 修复

## 修复清单

### F1 (Blocking): 测试类型检查失败

**问题**：`test_backtest_trigger_unit.py:206` 中 `params["cost_config"]` 类型为 `object`，
basedpyright 对 `:207-208` 的 dict 下标访问报 `reportIndexIssue`，导致 CI `type --all` 失败。

**修复**：在取值后加 `assert isinstance(cost_dict, dict)` 实现类型窄化。

**文件**：`interfaces/tests/unit/api/routes/test_backtest_trigger_unit.py`

---

### F2 (Blocking): `_run_in_process` 未真正绕过 Prefect engine

**问题**：`backtest.py:150` 用 `getattr(flow, "func", ...)` 但 Prefect 3.x Flow 属性是 `.fn`，
回退为直接调用 Flow 对象 → 触发 Prefect server → `ModuleNotFoundError: No module named 'lupa'`。

**修复**：`"func"` → `"fn"`。补单测验证调用的是 raw function 而非 Flow 对象。

**文件**：
- `interfaces/src/ditto_interfaces/api/routes/backtest.py` — 1 行改动
- `interfaces/tests/unit/api/routes/test_backtest_trigger_unit.py` — 新增 1 个测试

---

### F3 (Medium): FactorBridge lookback 硬编码

**问题**：`backtest_process.py:329` 固定 `lookback_days = 20`，但
`CompiledDerivedExpression.analysis.lookback` 已有编译器计算的准确值。
`ts_mean(close, 60)` 需要 61 天上下文，只给 20 天会算出 null。

**修复**：从 `compiled.expressions` 取 `max(analysis.lookback)`，默认兜底 20。

```python
lookback_days = max(
    (expr.analysis.lookback for expr in compiled.expressions),
    default=20,
)
```

**文件**：`packages/app/src/ditto_app/process/execution/backtest_process.py`

---

### F4 (Medium): cancel 后 flow 返回值语义误导

**问题**：`backtest_process.py:308` 正确标记 `cancelled`，但
`flows/backtest.py:96-101` 无条件返回 `"status": "completed"`。
SQLite guard 阻止了状态覆盖，但 flow 返回语义错误。

**修复**：Flow 执行完后通过 `run_service.get_run(run_id)` 读取 RunRecord 实际状态，
据此决定返回值中的 status 字段（completed/cancelled）。

**文件**：`interfaces/src/ditto_interfaces/jobs/flows/backtest.py`

---

### F5 (Process): 未跟踪文档文件

3 个 `docs/plans/2026-04-12-*.md` 保留并纳入本轮提交。

---

## 实施顺序

1. F1 — assert isinstance 类型窄化（1 行）
2. F2 — `.func` → `.fn` + 补单测
3. F3 — lookback 动态计算（2-3 行）
4. F4 — flow 读取 RunRecord 状态
5. F5 — 文档纳入提交

## 验证

- `pixi run -e dev type --tests` — 确认 F1 修复（0 errors, 0 warnings）
- `pixi run -e dev check` — 全量验证（lint/fmt/type/test/arch 全通过）

## 状态：已完成
