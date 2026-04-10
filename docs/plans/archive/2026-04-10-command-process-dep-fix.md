# Command → Process 依赖修正计划

> 日期：2026-04-10
> 状态：待实施
> 前置：`docs/plans/2026-04-10-app-layer-cqrs-redesign-impl.md`

## 问题

当前 `command → process` 存在 6 处反向依赖，违反 CQRS 互斥规则：

```
command/quality_check.py       → process.quality.quality_check       (TYPE_CHECKING)
command/quality_l3.py          → process.quality.l3_batch            (TYPE_CHECKING)
command/quality_l3.py          → process.quality.types               (运行时: L3CheckResult)
command/quality_reconciliation.py → process.quality.reconciliation  (TYPE_CHECKING)
command/quality_reconciliation.py → process.quality.protocols        (运行时: ReconciliationResult)
```

## 修正策略

三个质量服务的归属分析：

| 服务 | 功能 | 副作用 | 需要 Query | CQRS 归属 |
|------|------|--------|-----------|----------|
| `QualityService` | L1/L2 检查 + quarantine write | ✅ 写隔离数据 | ❌ 数据由调用方传入 | **Command** |
| `QualityReconciliationService` | 跨源对账 + 写对比结果 | ✅ 写对比数据 | ❌ 数据由调用方传入 | **Command** |
| `L3BatchService` | 统计异常巡检 | ❌ 仅日志/告警 | ✅ 主动查行情+日历 | **Process** |

修正后依赖方向：

```
command → ditto_data   ✅（app → data 允许）
command → ditto_kernel ✅（共享类型）
command → process      ❌ 禁止

process → command      ✅（Process 注入 Handler）
process → ditto_data   ✅
process → ditto_app.query ✅（process → query 允许）
```

---

## Phase A：类型下沉到 kernel `[S]`

**目标**：将纯值类型从 `process/quality/` 迁入 `ditto_kernel.quality`。

### 移动清单

| 类型 | 源 | 目标 | 依赖 |
|------|----|------|------|
| `L3CheckResult` | `process/quality/types.py` | `ditto_kernel.quality` | `DQIssue`（已在 kernel）✅ |
| `ReconciliationResult` | `process/quality/protocols.py` | `ditto_kernel.quality` | 无外部依赖 ✅ |

两个类型都是 frozen dataclass，无 polars 依赖，满足 kernel 准入 5 条标准。

### 导入更新（~15 文件）

**kernel**：
- `ditto_kernel/quality.py` — 新增 `L3CheckResult`、`ReconciliationResult` 到 `__all__`

**app（command handlers）**：
- `command/quality_l3.py` — `L3CheckResult` 改从 kernel 导入
- `command/quality_reconciliation.py` — `ReconciliationResult` 改从 kernel 导入

**app（process）**：
- `process/quality/quality_check.py` — 无变化（不直接用这两个类型）
- `process/quality/l3_batch.py` — `L3CheckResult` 改从 kernel 导入
- `process/quality/reconciliation.py` — `ReconciliationResult` 改从 kernel 导入
- `process/quality/__init__.py` — re-export 改从 kernel

**interfaces**：
- `interfaces/jobs/tasks/dq_batch.py` — `L3CheckResult` 可改从 kernel 导入
- `interfaces/jobs/context.py` — `QualityEngineProtocol` 不动（暂在 process/quality）
- `interfaces/tests/unit/jobs/tasks/test_dq_batch_unit.py` — 同上

**tests**：
- `tests/unit/process/quality/test_l3_batch_unit.py` — `L3CheckResult` 改从 kernel 导入
- `tests/unit/command/test_quality_handlers_unit.py` — `L3CheckResult`、`ReconciliationResult` 改从 kernel 导入

### 验收标准

- [ ] `L3CheckResult`、`ReconciliationResult` 在 `ditto_kernel.quality` 定义
- [ ] `ditto_kernel.quality.__all__` 更新
- [ ] 所有消费者导入更新
- [ ] `pixi run -e dev test --unit` 通过

---

## Phase B：L3BatchService → QualityPatrolService（归为 Process）`[M]`

**目标**：重命名 `L3BatchService` → `QualityPatrolService`，从 process/quality/ 移到 process/ 根目录，
删除对应的 Command Handler。

### 操作

1. **创建 `process/quality_patrol.py`**：
   - 将 `L3BatchService` 重命名为 `QualityPatrolService`
   - `L3CheckResult` 改从 kernel 导入
   - `QualityEngineProtocol` 暂从同目录导入（Phase D 清理）

2. **删除 `command/quality_l3.py`**（L3BatchCheckCommand + L3BatchCheckHandler）

3. **更新 `command/__init__.py`**：移除 `L3BatchCheckCommand`、`L3BatchCheckHandler`

4. **更新 `providers.py`**：
   - `AppCommandProvider` 移除 `l3_batch_check_handler`
   - `AppProcessProvider` 将 `l3_batch_service` 改为注册 `QualityPatrolService`
   - import 路径更新

5. **更新 `process/quality/__init__.py`**：移除 `L3BatchService` 的 re-export

6. **更新 interfaces 消费者**：
   - `interfaces/jobs/tasks/dq_batch.py` — `L3BatchService` → `QualityPatrolService`，import 路径更新
   - `interfaces/tests/unit/jobs/tasks/test_dq_batch_unit.py` — 测试更新

7. **测试迁移**：
   - `tests/unit/process/quality/test_l3_batch_unit.py` → `tests/unit/process/test_quality_patrol_unit.py`
   - 所有 `L3BatchService` → `QualityPatrolService` 重命名
   - 删除 `tests/unit/command/test_quality_handlers_unit.py` 中 `TestL3BatchCheckHandler` 类

8. **更新 `command/protocols.py`**：注释中移除 `L3BatchCheckHandler` 引用

### 验收标准

- [ ] `QualityPatrolService` 在 `process/quality_patrol.py`
- [ ] `command/quality_l3.py` 已删除
- [ ] 无 `L3BatchCheckHandler` 引用残留
- [ ] `pixi run -e dev test --unit` 通过

---

## Phase C：QualityService 逻辑吸收进 Command Handler `[L]`

**目标**：将 `QualityService.check_and_quarantine()` 逻辑直接写入 `CheckDataQualityHandler`，
Handler 直接依赖 `ditto_data` 层服务，消除对 `process.quality` 的依赖。

### 操作

1. **重写 `command/quality_check.py`**：
   ```python
   from ditto_data.quality import QualityEngine
   from ditto_data.services import QualityRecordService

   @dataclass(frozen=True)
   class CheckDataQualityCommand:
       df: pl.DataFrame
       dataset: str
       context: dict[str, Any] | None = None

   class CheckDataQualityHandler:
       """数据质量检查 — L1/L2 检查 + 隔离写入."""

       def __init__(self, engine: QualityEngine, writer: QualityRecordService) -> None:
           self._engine = engine
           self._writer = writer

       def handle(self, cmd: CheckDataQualityCommand) -> tuple[pl.DataFrame, bool]:
           # 原 QualityService.check_and_quarantine() 逻辑内联
           result = self._engine.check(df=cmd.df, dataset=cmd.dataset, levels=["l1", "l2"], context=cmd.context)
           self._log_check_result(result, cmd.dataset)
           if result.issues:
               self._quarantine_data(cmd.df, result, cmd.dataset)
           return cmd.df, result.has_errors
   ```

2. **更新 `providers.py`**：
   - `AppCommandProvider.check_data_quality_handler` 参数类型改为 `QualityEngine` + `QualityRecordService`
   - `AppProcessProvider` 移除 `quality_service()` 注册（逻辑已迁入 command）
   - `process/ingestion/config.py` 和 `coordinator_factory.py` 中的 `QualityService` 改为 `CheckDataQualityHandler`（或保留 Coordinator 自己构造）

3. **更新 `process/ingestion/` 消费者**：
   - `config.py` — `quality_service: QualityService` → `quality_service: CheckDataQualityHandler | None`
   - `coordinator_factory.py` — 同上
   - Coordinator 内部调用方式调整：`quality_service.handle(CheckDataQualityCommand(...))` 替代 `quality_service.check_and_quarantine(...)`

4. **更新 `interfaces/registry/contexts/ingestion.py`**：
   - `QualityService` → `CheckDataQualityHandler`，DI 注册路径更新

5. **更新测试**：
   - `tests/unit/command/test_quality_handlers_unit.py` — `TestCheckDataQualityHandler` 改用 `QualityEngine` + `QualityRecordService` mock
   - `tests/unit/process/quality/test_service_unit.py` — 迁移到 `tests/unit/command/` 或删除（逻辑已迁入 handler 测试）
   - 更新 ingestion 相关测试中 `QualityService` 的 mock

### 验收标准

- [ ] `CheckDataQualityHandler` 直接依赖 `ditto_data` 服务
- [ ] 无 `command → process.quality` 导入
- [ ] `process/quality/quality_check.py` 可删除（Phase E）
- [ ] `pixi run -e dev test --unit` 通过

---

## Phase D：QualityReconciliationService 逻辑吸收进 Command Handler `[L]`

**目标**：将 `QualityReconciliationService.daily_reconciliation()` 逻辑写入 `ReconcileSourcesHandler`，
Handler 直接依赖 data 层 Protocol 实现。

### 操作

1. **重写 `command/quality_reconciliation.py`**：
   - 将 `QualityReconciliationService` 的编排逻辑（~200 行）内联到 Handler
   - Handler 构造器直接接收各 Protocol 实现：
     ```python
     class ReconcileSourcesHandler:
         def __init__(
             self,
             engine: QualityEngine,
             tdx_source: TdxSourceProtocol,
             comparison_store: ComparisonStoreProtocol,
             instrument_store: InstrumentStoreProtocol,
             golden_dataset: GoldenDatasetSpec | None = None,
         ) -> None: ...
     ```
   - 各 Protocol 定义移入本文件或 `command/_quality_protocols.py`

2. **Protocol 归属**（消除对 `process/quality/protocols.py` 的依赖）：
   - `QualityEngineProtocol` → 使用 `ditto_data.quality.QualityEngine` 具体类型（只有一个实现）
   - `QuarantineWriterProtocol` → 使用 `ditto_data.services.QualityRecordService` 具体类型
   - `TdxSourceProtocol`、`ComparisonStoreProtocol`、`InstrumentStoreProtocol` → 移入 `command/_quality_protocols.py`
   - 这些 Protocol 被 command handler + QualityPatrolService（process）共用
   - `process → command` 方向 ✅ 允许

3. **更新 `providers.py`**：
   - `AppProcessProvider` 移除 reconciliation 相关注册
   - `AppCommandProvider` 新增 `ReconcileSourcesHandler` 注册

4. **更新测试**：
   - `tests/unit/command/test_quality_handlers_unit.py` — `TestReconcileSourcesHandler` 改用直接依赖
   - `tests/unit/process/quality/test_reconciliation_service_unit.py` — 迁移或删除

### 验收标准

- [ ] `ReconcileSourcesHandler` 直接依赖 data 层服务 + 本地 Protocol
- [ ] 无 `command → process.quality` 导入
- [ ] `process/quality/reconciliation.py` 可删除（Phase E）
- [ ] `pixi run -e dev test --unit` 通过

---

## Phase E：删除 process/quality/ + 全量验证 `[S]`

**目标**：删除 `process/quality/` 目录，清理残留引用。

### 操作

1. **删除目录**：
   - `process/quality/quality_check.py` — 已迁入 command（Phase C）
   - `process/quality/reconciliation.py` — 已迁入 command（Phase D）
   - `process/quality/l3_batch.py` — 已迁为 process/quality_patrol.py（Phase B）
   - `process/quality/types.py` — 已迁入 kernel（Phase A）
   - `process/quality/protocols.py` — 部分迁入 command/_quality_protocols.py（Phase D），部分用 data 具体类型替代
   - `process/quality/__init__.py` — 删除（re-export shim 不再需要）

2. **更新所有导入**：确认无 `from ditto_app.process.quality` 残留

3. **更新 `providers.py`**：
   - 移除 `from ditto_app.process.quality import ...`
   - `QualityService` 改为从 command 导入（或直接使用 Handler）

4. **更新文档**：
   - `packages/app/CLAUDE.md` — 移除 `quality/` 子目录描述
   - `.importlinter` — 移除/更新 quality 相关白名单

5. **全量验证**：
   - `pixi run -e dev check`
   - `pixi run -e dev arch-check`

### 验收标准

- [ ] `process/quality/` 目录已删除
- [ ] `process/` 子目录：`ingestion/`、`materialization/`、`execution/`（无 quality/）
- [ ] 无 `command → process` 依赖
- [ ] `pixi run -e dev check` 通过
- [ ] `pixi run -e dev arch-check` 通过

---

## 执行顺序

```
Phase A（类型下沉 kernel）──→ Phase B（L3 归为 Process + 重命名）
                         ──→ Phase C（QualityService → Handler）
                         ──→ Phase D（ReconciliationService → Handler）
                                                      ──→ Phase E（删除 quality/）
```

Phase A 必须最先（其他 Phase 依赖类型新位置）。
Phase B/C/D 可并行（互不依赖）。
Phase E 必须最后（等所有逻辑迁出）。

## 风险

| 风险 | 缓解 |
|------|------|
| ingestion coordinator 消费 QualityService 接口变化 | Coordinator 改用 Handler，或保留 thin wrapper |
| Protocol 从 process/quality 移出后 DI 注册路径变化 | providers.py 统一更新 |
| QualityReconciliationService 逻辑较大（~200 行），内联后 Handler 文件较长 | 可接受 — Handler 即 Service，符合 CQRS 设计 |
