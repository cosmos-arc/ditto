# Instrument ID Semantics Unification — Phase 完成后审计

**日期**: 2026-03-25
**计划文档**: `docs/plans/2026-03-24-instrument-id-semantics-unification-implementation-plan.md`
**计划状态**: 标记 COMPLETED (Phase 0-4 全部完成)
**审计结论**: 主链方向正确，Core 迁移基本成功，**但不建议完全验收通过**

---

## 1. 计划完成状态

计划文档自身标记 **COMPLETED (2026-03-25)**，Phase 0-4 全部标绿。实际审计发现存在"标记完成但残留缺陷"的情况，其中 #1 为 P0 阻塞项。

| Phase | 声明状态 | 审计结论 |
|-------|---------|---------|
| Phase 0 — 引入 InstrumentId NewType | COMPLETED | 确认无问题 |
| Phase 1 — Port 层切换输入语义 | COMPLETED | 存在残留（见 #1） |
| Phase 2 — Core 运行时主键切换 | COMPLETED | Core 层迁移正确 |
| Phase 3 — DataHub 规则子域收敛 | COMPLETED | 确认无问题 |
| Phase 4 — 清理桥接与语义债务 | COMPLETED | 存在残留（见 #3, #5） |

---

## 2. 发现详情

### #1 — benchmark_id 在 DataFeed 边界被二次 resolve（P0，阻塞验收）

**严重度**: 高
**阻塞验收**: 是

**问题**: `BacktestRuntimeBuilder` 已将 benchmark 解析为 canonical `InstrumentId` 并塞进配置，但 `MarketServiceDataFeed._load_benchmark_close_map()` 又对它执行了一次 `resolve_instrument_id(str(self._config.benchmark_id), ...)`。

**证据链**:

| 步骤 | 文件 | 行号 | 行为 |
|------|------|------|------|
| 1 | `backtest_runtime_builder.py` | 88-98 | `_resolve_benchmark()` 返回 `InstrumentId \| None` |
| 2 | `backtest_runtime_builder.py` | 116 | 将已解析的 `InstrumentId` 传给 `MarketServiceDataFeedConfig.benchmark_id` |
| 3 | `market_data_feed.py` | 27 | config 类型声明 `benchmark_id: InstrumentId \| None` — 类型正确 |
| 4 | `market_data_feed.py` | 208-211 | **`str(self._config.benchmark_id)` → `resolve_instrument_id()`** — 违反契约 |

**影响分析**:

`resolve_instrument_id()` 的契约是"接收 source ticker（如 `000300.SH`）→ 返回 canonical int"。但此处传入的是 canonical ID 的字符串形式（如 `"3000001"`），导致：

- **路径 A**: resolver 无法匹配 → `benchmark_instrument_id = None` → `benchmark_close` 全部为空 → 回测报告没有基准收益（基准线消失）
- **路径 B**: 碰巧匹配到错误标的 → 静默产出错误基准数据（更危险）

**测试缺陷**:

现有测试未覆盖真实路径。`test_market_service_data_feed_unit.py:103` 传入 `benchmark_id="000300.SH"`（字符串 ticker），既绕过了类型检查也绕过了 canonical ID 路径。同样 `test_backtest_service_unit.py:114` 和 `test_strategy_service_factory_unit.py:58` 也在用字符串 benchmark。

**修复建议**:

`_load_benchmark_close_map()` 应直接使用 `self._config.benchmark_id`（已是 `InstrumentId`），删除二次 resolve。若需支持"未解析 benchmark"输入场景，应单独引入 `benchmark_identifier: str | None` 字段，不要一个字段混两种语义。

```python
# 修复前 (market_data_feed.py:199-213)
def _load_benchmark_close_map(self, start_date, *, trading_days) -> dict[str, float]:
    if self._config.benchmark_id is None:
        return {}
    benchmark_instrument_id = self._metadata_service.resolve_instrument_id(
        str(self._config.benchmark_id),  # ← BUG: str(InstrumentId(3000001)) = "3000001"
        self._config.source,
        self._config.start_date,
    )
    ...

# 修复后
def _load_benchmark_close_map(self, start_date, *, trading_days) -> dict[str, float]:
    if self._config.benchmark_id is None:
        return {}
    benchmark_instrument_id = int(self._config.benchmark_id)  # ← 直接使用 canonical ID
    ...
```

**回归测试**:

补一个测试用 `benchmark_id=InstrumentId(3_000_001)` 走完整路径，验证 `benchmark_close` 正确填充。

---

### #2 — PORTFOLIO_WIDE_ID 序列化语义断裂（P0）

**严重度**: 中高
**阻塞验收**: 视下游消费者而定（当前为语义债务）

**问题**: Core 用 `InstrumentId(0)` 表示"全组合"风控事件，DataHub DTO 文档声明 `"*"` 表示全组合，但 Port 持久化时做 `str(r.instrument_id)` 把全组合事件写成 `"0"`，三处语义不一致。

**证据链**:

| 层 | 文件 | 行号 | 语义 |
|----|------|------|------|
| Core | `post_trade.py` | 68 | `PORTFOLIO_WIDE_ID = InstrumentId(0)` → 全组合 |
| DataHub DTO | `strategy_audit.py` | 30 | 文档声明 `"*"` 表示全组合 |
| Port 持久化 | `backtest_service.py` | 279 | `str(r.instrument_id)` → 写入 `"0"` |

**影响**: 下游展示/筛选按 `"*"` 过滤全组合事件会完全命中不了，按 `"0"` 过滤则会意外匹配到一个不存在的标的 ID。

**修复建议**:

短期（P0）— 在 Port 层转换时收口映射规则：

```python
# backtest_service.py _persist_audit()
PORTFOLIO_WIDE_TOKEN = "*"

def _instrument_id_to_token(instrument_id: InstrumentId) -> str:
    if instrument_id == PORTFOLIO_WIDE_ID:
        return PORTFOLIO_WIDE_TOKEN
    return str(instrument_id)
```

长期 — DTO 显式拆分，消灭魔法值：

```python
@dataclass(frozen=True)
class RiskScanPayload:
    instrument_id: int | None      # None = 全组合
    scope: Literal["instrument", "portfolio"]
    ...
```

**回归测试**: 补一个 portfolio-wide 风控事件的序列化测试，验证输出为 `"*"` 而非 `"0"`。

---

### #3 — display_map 在 factory 主链丢失（P1）

**严重度**: 中
**阻塞验收**: 否（功能形同虚设但不影响正确性）

**问题**: `ArtifactWriter` 已支持 display_map 注入，`BacktestServiceOptions` 已声明 `display_map` 字段，但 `StrategyServiceFactory._build_backtest_options()` 手动重建 options 时漏掉了该字段。同时 catalog-backed 路径也没有把 `runtime.data_feed.display_map` 接入。

**证据链**:

| 文件 | 行号 | 行为 |
|------|------|------|
| `backtest_service.py` | 120 | `display_map: dict[InstrumentId, str] \| None = None` — 字段已定义 |
| `factory.py` | 184-192 | `_build_backtest_options()` 手动罗列字段，**漏掉 `display_map`** |
| `factory.py` | 143-148 | `build_backtest_service_from_catalog()` 未从 `runtime.data_feed.display_map` 接入 |
| `artifact_writer.py` | 55 | `write_backtest_artifacts()` 已接受 `display_map` 参数 |
| `test_artifact_writer_unit.py` | 234 | 单测验证了 enrichment，但主链无对应回归 |

**修复建议**:

1. `_build_backtest_options()` 改用 `replace()` 补丁式合并，避免再丢字段：

```python
def _build_backtest_options(self, options):
    base = options or BacktestServiceOptions()
    defaults = BacktestServiceOptions(
        audit_service=self._audit_service,
        artifact_service=self._artifact_service,
        run_service=self._run_service,
    )
    merged = {
        "fee_model": base.fee_model or defaults.fee_model,
        "rule_provider": base.rule_provider,
        "post_trade_guard": base.post_trade_guard,
        "audit_service": base.audit_service or defaults.audit_service,
        "artifact_service": base.artifact_service or defaults.artifact_service,
        "artifact_dir": base.artifact_dir,
        "display_map": base.display_map,  # ← 保留调用方传入的 display_map
        "run_service": base.run_service or defaults.run_service,
    }
    return replace(defaults, **merged)
```

2. `build_backtest_service_from_catalog()` 补充 display_map 注入：

```python
# 从 runtime.data_feed 读取 display_map
if resolved_options.display_map is None and hasattr(runtime.data_feed, "display_map"):
    resolved_options = replace(
        resolved_options,
        display_map=runtime.data_feed.display_map,
    )
```

**回归测试**: 补一个 factory 构建 + artifact 写出的集成测试，验证 `instrument_symbol` 字段出现在输出中。

---

### #4 — 外部边界 instrument_id 命名歧义（P1）

**严重度**: 中
**阻塞验收**: 否

**问题**: 本次重构范围是"策略/回测主链统一"，不是"全仓语义统一"。以下位置仍把 `instrument_id` 定义为 `str`：

| 文件 | 行号 | 说明 |
|------|------|------|
| `capital_service.py` | 44 | `instrument_id: str` |
| `capital.py` | 25 | `instrument_id: str` |
| `strategy_audit.py` | 39 | `instrument_id: str`（DTO） |
| `test_execution_audit_service_unit.py` | 36 | 测试用 `str` |

如果这是刻意保留的外部边界，不算 bug；但命名应改为 `identifier` / `source_ticker`，否则团队会继续误以为此处也是 canonical ID。

**建议**: 明确裁剪边界 — 内部一律 `InstrumentId`；外部若保留字符串输入，将字段重命名为 `identifier` 或 `source_ticker`。

---

### #5 — 文档和测试旧语义残留（P2）

**严重度**: 低
**阻塞验收**: 否

**残留位置**:

| 文件 | 行号 | 残留内容 |
|------|------|---------|
| `pipeline.py` | 9-10 | DecisionFrame 文档仍写 `instrument_id: str` |
| `test_market_service_data_feed_unit.py` | 98 | benchmark 仍用字符串 `"000300.SH"` |
| `test_backtest_service_unit.py` | 114 | benchmark 仍用字符串 |
| `test_strategy_service_factory_unit.py` | 58 | benchmark 仍用字符串 |

**影响**: 文档残留会误导开发者；测试残留会让 #1 的 bug 长期潜伏（测试永远走字符串路径，不经过 canonical ID 路径）。

**建议**: 清理文档 + 统一测试 fixture 使用 `InstrumentId`。

---

## 3. 修复优先级

| 优先级 | 发现 | 工作量 | 说明 |
|--------|------|--------|------|
| **P0** | #1 benchmark 二次 resolve | 小 | 删除 3 行 + 补 1 个测试 |
| **P0** | #2 PORTFOLIO_WIDE_ID 映射 | 小 | 加 1 个转换函数 + 补 1 个测试 |
| **P1** | #3 factory display_map 透传 | 小 | 改 `_build_backtest_options` + 补接入逻辑 |
| **P1** | #4 外部边界命名清理 | 中 | 重命名 + 类型标注调整 |
| **P2** | #5 文档/测试残留清理 | 小 | 文档更新 + fixture 统一 |

**必须补的 3 个回归测试**:

1. canonical `InstrumentId` benchmark 路径 — 验证 `benchmark_close` 正确填充
2. portfolio-wide risk 审计序列化 — 验证输出为 `"*"` 而非 `"0"`
3. factory/display_map 透传 — 验证 `instrument_symbol` 出现在 artifact 输出

---

## 4. 总结

本次重构的 Core 层迁移方向正确、深度到位（~29 个业务文件），`InstrumentId` NewType 已成功成为运行时主键。但在 Port 层装配和边界转换环节存在 3 个实质性 bug（#1-#3），其中 #1 直接阻塞验收。

修复总工作量较小（预计 1-2 个 session），修复后建议重新跑 `pixi run -e dev check` + `pixi run -e dev arch-check` 确认全绿。
