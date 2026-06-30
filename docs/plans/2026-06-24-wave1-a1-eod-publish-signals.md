# A1 · EOD 自动 publish-signals 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** EOD pipeline 每日自动产出可交易信号包（持久化 `TradeIntent`），让 `/trade/signals/latest` 不再恒空。

**Architecture:** `eod_flow._run_strategies` 从 `RESEARCH` 改为 `RECOMMENDATION`，并对每个成功 run 调用 `SignalPackagePublisher.publish(target=run_result.target)`，镜像 [publish-signals CLI](../../packages/apps/src/ditto_apps/cli/commands/strategy.py) 范式。publisher 缺失或单策略 publish 失败不阻断 flow。

**Tech Stack:** Python / polars / prefect / pytest；无新依赖。

**战略索引:** [wave1 主计划](2026-06-24-wave1-implementation-plan.md) §0/§2；[战略定位](2026-06-24-strategic-positioning-and-functional-gap-analysis.md)。

> **⚠️ 分支基线注意：** `signal_package.py` 与相关 dev 工作仅在 `dev/architecture-remediation-batch2-6`，**main 落后 53 commit**。本工作流分支须基于含该代码的基线（dev 分支，或 main 合入 dev 后），不能直接从落后 main 拉。详见主计划 §0。

---

## 现状实证

- [eod.py](../../packages/apps/src/ditto_apps/jobs/flows/eod.py) `_run_strategies`（L75-138）：对每个 `published` spec 用 `StrategyRunMode.RESEARCH`（L111）调 `facade.run_strategy_for_date_from_catalog(...)`，**不调** `signal_package_publisher`。
- [publish-signals 命令](../../packages/apps/src/ditto_apps/cli/commands/strategy.py#L113) 正确范式：`RECOMMENDATION` 模式 + `bundle.signal_package_publisher.publish(target=result.target, dataset_snapshot_ids=..., factor_ids=..., threshold=...)`。
- [SignalPackagePublisher.publish](../../packages/application/src/ditto_application/processes/execution/signal_package.py#L65)：生成 `SignalPackage`、经 `intent_port.save_intent` 持久化 `TradeIntent`、返回含 `intents`/`checksum` 的包。
- bundle（`create_strategy_bundle()`）同时持有 `catalog_service`、`strategy_facade`、`signal_package_publisher`（后者可能为 None，CLI 已做 None 检查）。

**Files:**
- Modify: `packages/apps/src/ditto_apps/jobs/flows/eod.py`（`_run_strategies`）
- Verify: `packages/apps/src/ditto_apps/registry/contexts/strategy.py`（确认 `create_strategy_bundle` 暴露 `signal_package_publisher`）
- Test: `packages/apps/tests/integration/`（eod flow 测试；若无则新建）

---

## Task A1.0：理解现有测试与 bundle 结构（强制前置）

**Step 1：** `Grep "eod_flow\|_run_strategies" packages/apps/tests` 找到现有 eod flow 测试；Read 该测试 + 其 fixture，理解如何构造合成数据、published spec、assert flow 结果。
**Step 2：** Read `create_strategy_bundle` 返回类型，确认 `signal_package_publisher` 字段名与是否可注入测试替身（intent reader/writer）。
**Step 3：** 确认测试中如何读回已持久化 intent（`IntentDataPort` / 查询 facade），用于断言。

> 无代码改动。产出：测试 fixture 复用方案 + bundle publisher 注入点确认。

---

## Task A1.1：RED — eod 产出持久化 intents（失败测试）

**Step 1：** 在 eod flow 集成测试中加测试，断言 flow 跑完后存在该策略/该日的 `TradeIntent`：

```python
def test_eod_flow_publishes_trade_intents(eod_flow_fixture):
    # eod_flow_fixture: 合成数据 + 一个 published spec + intent reader 替身
    result = eod_flow(trade_date="2024-01-15", source="tushare")
    assert result["overall_status"] in {"success", "partial"}

    intents = eod_flow_fixture.intent_reader.list_intents(
        strategy_id=eod_flow_fixture.published_strategy_id,
        signal_date="2024-01-15",
    )
    assert len(intents) > 0  # 当前 RESEARCH 模式不 publish → 此处 FAIL
```

> fixture 名以 A1.0 调研结果为准；镜像现有 eod flow 测试的合成数据构造，勿新造。

**Step 2：** `pixi run -e dev pytest packages/apps/tests/integration -k eod -q`
**Expected：** FAIL（无 intent 持久化）。

---

## Task A1.2：GREEN — eod 切 RECOMMENDATION + publish

**Step 1：** 修改 `_run_strategies`（eod.py:75）：
- 在 `with create_strategy_bundle() as bundle:` 内取 `publisher = bundle.signal_package_publisher`。
- `StrategyRunMode.RESEARCH`（L111）→ `StrategyRunMode.RECOMMENDATION`。
- 每个 `run_result` 成功后，若 `publisher is not None`，调 `package = publisher.publish(target=run_result.target, threshold=0.01)`，把 `len(package.intents)` 与 `package.checksum` 并入 result dict（如 `"signals": {"intents": len(package.intents), "checksum": package.checksum}`）。
- 若 `publisher is None`，记 `logger.warning("signal_package_publisher 未配置，跳过 publish")`，不阻断。

**Step 2：** `pixi run -e dev pytest packages/apps/tests/integration -k eod -q`
**Expected：** PASS。

---

## Task A1.3：加固 — 单策略 publish 失败不阻断 flow

**Step 1：** 加测试：构造一个策略其 `publish` 抛异常，断言 flow 仍返回其他策略结果、`overall_status` 反映该策略失败、其他策略 intent 正常持久化。
**Step 2：** 确认 publish 调用被现有 `try/except`（eod.py:123）包裹；若未包裹则补上，publish 异常记入 result（`"status": "failed", "error": ...`）并 `all_success = False`，不向上抛。
**Step 3：** `pixi run -e dev pytest packages/apps/tests/integration -k eod -q` → PASS。

---

## Task A1.4：验证 + 提交

**Step 1：** `pixi run -e dev check`（lint + fmt + type + test --fast）。
**Step 2：** `pixi run -e dev arch-check`（确认未破坏 apps/application 边界）。
**Step 3：** Commit（独立分支）：
```bash
git add packages/apps/src/ditto_apps/jobs/flows/eod.py packages/apps/tests/integration/
git commit -m "feat(eod): publish trade signal packages in daily pipeline"
```

---

## DoD

- [ ] eod_flow 跑完后，`/trade/signals/latest`（或 intent reader）能查到当日信号。
- [ ] publisher 缺失只告警不阻断；单策略 publish 失败不影响其他策略。
- [ ] `check` + `arch-check` 全绿；新增/改动有单测覆盖。

## 风险

| 风险 | 缓解 |
|---|---|
| `create_strategy_bundle` 在 eod 上下文未注入 publisher | A1.0 先确认；若缺，在 `registry/contexts/strategy.py` 补 publisher 装配（复用 CLI 同一 provider） |
| RECOMMENDATION 模式对 experimental 数据 fail-closed 导致无信号 | publish 用已 published 策略 + initial-focus 数据；若触发 maturity gate，记录并降级为 RESEARCH（不 publish）而非硬失败 |
| 测试合成数据不产生 intent（target 为空） | fixture 确保 published spec 在合成数据上有非空 target positions |
