# Batch 1 代码审查修复计划

## 概述
- 来源: 6 维度并行代码审查（架构/PIT/规约/可维护/质量/文档）
- 创建: 2026-05-18
- 完成: 2026-05-18
- 范围: 8 项 Important + 14 项 Suggestion，共 22 项
- 状态: ✅ 全部完成（T1-T14），6729 测试通过，37/37 架构契约保持

## 技术方案

### 修复原则
1. **Protocol 化解耦**：application 层编排类应依赖 Protocol 而非具体实现
2. **严格防御**：from_row 工厂从外部源读取时应 fail-fast，不静默降级
3. **死代码清零**：无调用者的方法立即删除
4. **文档同步**：代码变更后 CLAUDE.md 必须同步

### 不做的事
- 不拆分 `dataset_registry.py`（465 行在可接受边界，内部结构清晰）
- 不新增 `_default_routes.py`（当前声明式注册同构且易审查）
- 不拆分 `data_writer.py`（计划内 Batch 3 遗留，不在本次范围）

---

## 任务清单

### T1: PaperTradingRuntime Protocol 化 `[M]`
- **验收**: `PaperTradingRuntime.__init__` 参数类型从 `PaperBrokerGateway` 改为 `BrokerGateway` Protocol；测试同步更新
- **文件**:
  - `packages/application/src/ditto_application/processes/execution/paper_trading_process.py`
  - `packages/application/tests/unit/process/execution/test_paper_trading_process_unit.py`
- **变更**: import `BrokerGateway` from `ditto_execution.broker.contracts`，替换类型标注

### T2: capital/fundamental 查询门面 Protocol 化 `[M]`
- **验收**: `CapitalQueryFacade` 和 `FundamentalQueryFacade` 构造函数接受 Protocol 而非具体 Store；DI provider 同步更新
- **文件**:
  - `packages/application/src/ditto_application/queries/capital.py`
  - `packages/application/src/ditto_application/queries/fundamental.py`
  - `packages/application/src/ditto_application/providers_market.py`
  - `packages/application/tests/unit/query/test_capital_query_facade_unit.py`
  - `packages/application/tests/unit/query/test_fundamental_query_facade_unit.py`
- **变更**: 定义 `CapitalDataPort` 和 `FundamentalDataPort` Protocol（仅声明 facade 使用的方法），替换构造函数参数类型

### T3: _lifecycle.py import 合并 + 死代码清理 `[S]`
- **验收**: 5 段重复 import 合并为 1 段；`Dataset.supports_instrument_ingestion()` 已删除且全库无残留引用
- **文件**:
  - `packages/platform/src/ditto_platform/foundation/observability/_lifecycle.py`
  - `packages/data/src/ditto_data/models/common.py`
- **变更**:
  1. `_lifecycle.py`: 合并 5 段 `from ._registry import ...` 为单段
  2. `common.py`: 删除 `supports_instrument_ingestion()` 方法（全库调用已迁移至 `DatasetRegistration.supports_instrument_ingestion`）

### T4: 类型安全修复 `[M]`
- **验收**: `SafeGauge._gauge` 类型为 `metrics.ObservableGauge | None`；`from_row()` 对无效类型 raise 而非静默降级
- **文件**:
  - `packages/platform/src/ditto_platform/foundation/observability/metrics/_types.py`
  - `packages/analysis/src/ditto_analysis/research/domain.py`
  - `packages/analysis/tests/unit/research/test_record_models_unit.py`
- **变更**:
  1. `_types.py:168`: `self._gauge: Any = None` → `self._gauge: metrics.ObservableGauge | None = None`
  2. `domain.py` 4 处 `from_row()` 中 `_version if isinstance(_version, int) else 1` → `raise ResearchDatasetError(...)` 当类型非 int 时（`_row_count` 同理 → raise 而非默认 0）
  3. `domain.py`: `_apply_late_arrival_policy` 参数 `policy: str` → `policy: LateArrivalPolicy`
  4. `domain.py:304,402,413`: `orjson.loads(orjson.dumps(x))` 往复 → 直接 `tuple(str(x) for x in raw)` / `dict(x for x in raw.items())`

### T5: Reconciler 命名 + 类型改进 `[S]`
- **验收**: `unmatched_count` 重命名为 `diff_count`；`ReconciliationReport.status` 使用 `Literal` 类型
- **文件**:
  - `packages/execution/src/ditto_execution/reconciliation/reconciler.py`
  - `packages/execution/src/ditto_execution/reconciliation/types.py`
  - `packages/execution/tests/unit/test_reconciliation_unit.py`
- **变更**:
  1. `reconciler.py`: 局部变量 `unmatched_count` → `diff_count`
  2. `types.py`: `status: str = "pending"` → `status: Literal["matched", "mismatch", "pending"] = "pending"`
  3. `types.py`: `ReconciliationReport.unmatched_count` → `ReconciliationReport.diff_count`
  4. 测试同步更新断言

### T6: PaperGateway fill price 注释 + 市价单防御 `[S]`
- **验收**: `paper.py` 中市价单 fill_price=0.0 的行为有明确注释说明
- **文件**:
  - `packages/execution/src/ditto_execution/broker/gateways/paper.py`
- **变更**: 在 `fill_price = order.price if order.price is not None else 0.0` 行上方添加注释，说明这是最小冒烟测试实现的简化，市价单应以 last close price 成交

### T7: _helpers.py 静默 catch 添加 DEBUG 日志 `[S]`
- **验收**: `compute_ic_decay_safe` 和 `estimate_avg_turnover` 的 except 块记录 DEBUG 级别日志
- **文件**:
  - `packages/features/src/ditto_features/evaluation/evaluator/_helpers.py`
- **变更**: 在两个 except 块中添加 `logger.debug(...)` 记录异常信息（使用 `from ditto_platform.foundation import get_logger`）

### T8: MomentumIndicator PIT 前置条件注释 `[S]`
- **验收**: `MomentumIndicator.compute()` 方法有 PIT 前置条件说明
- **文件**:
  - `packages/strategy/src/ditto_strategy/alpha/builtins/regime/regime_indicators.py`
- **变更**: 在 `compute()` 方法 docstring 中添加 "调用方须确保 frame.close 列仅含 T 时刻及之前数据"

### T9: metrics/__init__.py __getattr__ 注释 `[S]`
- **验收**: `__getattr__` 延迟导出有注释说明理由
- **文件**:
  - `packages/platform/src/ditto_platform/foundation/observability/metrics/__init__.py`
- **变更**: 在 `__getattr__` 函数上方添加注释说明这些符号仅供测试访问内部状态

### T10: protocol_adapters.py docstring 精确化 `[S]`
- **验收**: `source_data_port` 方法 docstring 准确描述 SourceAccessor.tushare → SourceDataPort 映射
- **文件**:
  - `packages/apps/src/ditto_apps/registry/infra/protocol_adapters.py`
- **变更**: `"TushareSource -> SourceDataPort."` → `"SourceAccessor.tushare -> SourceDataPort."`

### T11: ADR 格式补全 `[S]`
- **验收**: `adr-reconciliation-recovery.md` 包含背景/决策/后果/参考完整段落，与其他 ADR 格式一致
- **文件**:
  - `docs/architecture/adr-reconciliation-recovery.md`
- **变更**: 添加"背景"段落（为什么需要对账恢复策略）、"后果"段落（正面/负面/权衡）、"参考"段落

### T12: execution/CLAUDE.md 同步 `[M]`
- **验收**: Known Gaps 反映 PaperBrokerGateway 和 Reconciliation 已实现；目录结构包含新增文件
- **文件**:
  - `packages/execution/CLAUDE.md`
- **变更**:
  1. 更新 "Broker Gateways（EXEC-P1-02）" → 标记为已实现（PaperBrokerGateway）
  2. 更新 "Reconciliation（EXEC-P1-03）" → 标记为已实现（ExecutionReconciler + typed diffs）
  3. 目录结构 `reconciliation/` 注释从 "minimal dataclass only" 更新
  4. 目录结构 `broker/gateways/` 添加 `paper.py`

### T13: 其他包 CLAUDE.md 同步 `[M]`
- **验收**: apps/backtest/platform/strategy CLAUDE.md 反映本次变更
- **文件**:
  - `packages/apps/CLAUDE.md` — 添加 `protocol_adapters.py` 到 infra 目录
  - `packages/backtest/CLAUDE.md` — 反映 EngineResultBuilder 和 StepResult 扩展
  - `packages/platform/CLAUDE.md` — 反映 metrics 模块拆分
  - `packages/strategy/CLAUDE.md` — 反映 regime 模块重构为子包

### T14: Gateway conformance 测试扩展 `[S]`
- **验收**: `test_gateway_conformance_unit.py` 覆盖所有 Protocol 方法的返回值类型验证
- **文件**:
  - `packages/execution/tests/unit/broker/test_gateway_conformance_unit.py`
- **变更**: 扩展 Protocol 方法签名验证 + PaperBrokerGateway 实例行为验证

---

## 依赖关系与执行顺序

```
T1 (Protocol 化) ──┐
T2 (Protocol 化) ──┤── 无依赖，可并行
T3 (import + 死代码) ┤
T4 (类型安全) ──────┤
T5 (reconciler) ────┤
T6 (paper 注释) ────┤
T7 (helpers 日志) ──┤
T8 (PIT 注释) ──────┤
T9 (metrics 注释) ──┤
T10 (docstring) ────┤
T11 (ADR) ──────────┤
T14 (conformance) ──┘
                    │
T12 (execution doc) ├── 依赖 T5（字段重命名）
T13 (其他 doc) ─────┘
```

**建议并行组**:
- **组 A**: T1 + T2 + T3 + T4 + T5（核心代码修复，5 个 agent 并行）
- **组 B**: T6 + T7 + T8 + T9 + T10 + T14（小修复，可与组 A 并行）
- **组 C**: T11 + T12 + T13（文档，依赖 T5 完成后执行）

## 完成验证

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 36 contracts
```
