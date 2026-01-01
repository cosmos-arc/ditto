# Ingestion 系统重构进度报告

> **更新时间**: 2025-01-01
> **计划文件**: [2025-12-30-ingestion-refactor.md](../plans/2025-12-30-ingestion-refactor.md)
> **分支**: `feat/ingestion-service-structure`

---

## 总体进度

| Phase | 任务数 | 已完成 | 进行中 | 待开始 | 完成率 |
|-------|--------|--------|--------|--------|--------|
| Phase 1 | 3 | 3 | 0 | 0 | 100% ✅ |
| Phase 2 | 2 | 2 | 0 | 0 | 100% ✅ |
| Phase 3 | 6 | 3 | 0 | 3 | 50% 🔄 |
| Phase 4 | 3 | 0 | 0 | 3 | 0% |
| Phase 5 | 3 | 0 | 0 | 3 | 0% |
| **总计** | **17** | **8** | **0** | **9** | **47%** |

---

## Phase 1: Ingestion Service 层 ✅ (100%)

### Task 1.1: 创建 Ingestion Service 目录结构 ✅

**状态**: 已完成
**提交**: `8388318` (初始), `5e9a5df` (规范修复)

**实现内容**:
- 创建 `apps/server/src/ditto_server/ingestion/services/` 目录
- 创建占位文件：`coordinator.py`, `metadata.py`, `backfill.py`, `retry.py`
- 每个文件包含清晰的中文 docstring

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过

---

### Task 1.2: 实现 MetadataManager ✅

**状态**: 已完成
**文件**: `apps/server/src/ditto_server/ingestion/services/metadata.py`
**测试**: `apps/server/tests/unit/ingestion/test_metadata.py`

**实现内容**:
- `compute_checksum(df: pl.DataFrame) -> str` - 计算数据 checksum
- `should_skip(dataset, trade_date, force) -> tuple[bool, str | None]` - 判断是否跳过
- `compare_data(new_df, existing_log) -> bool` - 比较新旧数据

**测试结果**:
- 14 个测试全部通过
- 覆盖率 **100%**

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过

---

### Task 1.3: 实现 IngestionCoordinator ✅

**状态**: 已完成
**文件**: `apps/server/src/ditto_server/ingestion/services/coordinator.py`
**测试**: `apps/server/tests/unit/ingestion/test_coordinator.py`

**实现内容**:
- `ingest_date(dataset, trade_date, force) -> IngestionResult` - 摄取单个交易日
- `ingest_range(dataset, start_date, end_date, force) -> list[IngestionResult]` - 摄取日期范围
- 支持 7 种数据集类型

**测试结果**:
- 16 个测试全部通过
- 覆盖率 **88.35%**

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过

---

## Phase 2: 全量回补和重试能力 ✅ (100%)

### Task 2.1: 实现 BackfillManager ✅

**状态**: 已完成
**文件**: `apps/server/src/ditto_server/ingestion/services/backfill.py`
**测试**: `apps/server/tests/unit/ingestion/test_backfill.py`

**实现内容**:
- `backfill_range(dataset, start_date, end_date, parallel) -> BackfillResult` - 按日期范围回补
- `backfill_missing(dataset, parallel) -> BackfillResult` - 回补缺失日期
- 支持并行回补（ThreadPoolExecutor）

**测试结果**:
- 9 个测试全部通过
- 覆盖率 **86.36%**

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过

---

### Task 2.2: 实现 RetryManager ✅

**状态**: 已完成
**文件**: `apps/server/src/ditto_server/ingestion/services/retry.py`
**测试**: `apps/server/tests/unit/ingestion/test_retry.py`

**实现内容**:
- `retry_failed(dataset, max_attempts, limit) -> RetryResult` - 重试失败任务
- `get_failed_dates(dataset, max_attempts) -> list[str]` - 获取失败日期

**测试结果**:
- 12 个测试全部通过
- 覆盖率 **100%**

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过（评分 A+ 95/100）

---

## Phase 3: Prefect 集成 🔄 (50%)

### Task 3.1: 创建 config/datasets.py ✅

**状态**: 已完成
**文件**: `apps/server/src/ditto_server/ingestion/config/datasets.py`
**测试**: `apps/server/tests/unit/ingestion/test_datasets.py`

**实现内容**:
- `Dataset` 枚举（7个数据集）
- `TaskTier` 枚举（T0/T1/T2/T3）
- `DatasetConfig` 模型（11个字段）
- `DATASET_REGISTRY` 注册表
- 辅助函数：`get_datasets_by_tier()`, `get_dataset_config()` 等

**测试结果**:
- 28 个测试全部通过
- 覆盖率 **88.61%**

**修复提交**:
- `d7bd0ad` - 修复 DatasetConfig 字段缺失
- `544e4df` - 修复 TaskTier 枚举规范合规性

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过

---

### Task 3.2: 创建 Tasks 层 ✅

**状态**: 已完成
**文件**:
- `apps/server/src/ditto_server/ingestion/tasks/t0_meta.py`
- `apps/server/src/ditto_server/ingestion/tasks/t1_bars.py`
- `apps/server/src/ditto_server/ingestion/tasks/t1_adj_factor.py`

**测试**: `apps/server/tests/unit/ingestion/tasks/test_task_factory.py`

**实现内容**:
- `create_ingest_task(dataset)` 工厂函数
- 配置驱动设计（从 DATASET_REGISTRY 读取）
- 轻量 wrapper，逻辑在 IngestionCoordinator
- try-finally 确保 DataHub 正确关闭

**测试结果**:
- 22 个测试全部通过
- 覆盖率 **100%**

**审查结果**:
- ✅ Spec 审查通过
- ✅ 代码质量审查通过（评分 9.8/10）

---

### Task 3.3: 创建 flows/daily.py ✅

**状态**: 已完成
**文件**: `apps/server/src/ditto_server/ingestion/flows/daily.py`
**测试**: `apps/server/tests/unit/ingestion/flows/test_daily.py`

**实现内容**:
- `daily_ingestion_flow(trade_date, source, data_root, force)` - 每日摄取 Flow
- T0 Meta 任务并行执行（calendar, stock_basic, etf_basic）
- T1 Incremental 任务并行执行，依赖 T0（etf_daily, stock_daily, adj_factor, fund_adj）
- 交易日验证（非交易日跳过）
- 使用 Prefect 原生依赖编排（`.submit()` + `wait_for`）

**测试结果**:
- 20 个测试全部通过

**修复提交**:
- `db2778d` - 修复依赖编排实现（使用 Prefect 声明式依赖）

---

### Task 3.4: 创建 flows/backfill.py ⏳

**状态**: 待开始

---

### Task 3.5: 创建 flows/repair.py ⏳

**状态**: 待开始

---

### Task 3.6: 创建 deploy.py ⏳

**状态**: 待开始

---

## Phase 4: Source 层简化 (0%)

### Task 4.1: 移除 DataSource.ingest_date() ⏳

**状态**: 待开始

---

### Task 4.2: 移除 TushareSource.ingest_date() ⏳

**状态**: 待开始

---

### Task 4.3: 废弃 fetch_etf_daily_incremental() ⏳

**状态**: 待开始

---

## Phase 5: 清理和文档 (0%)

### Task 5.1: 标记废弃组件 ⏳

**状态**: 待开始

---

### Task 5.2: 更新测试 ⏳

**状态**: 待开始

---

### Task 5.3: 更新文档 ⏳

**状态**: 待开始

---

## 技术债务与改进建议

### 已知问题

1. **my py 类型警告**：Prefect 任务工厂的类型推断限制（不影响功能）
2. **旧式任务测试失败**：4个使用废弃接口的测试失败（待 Phase 4 更新）

### 后续优化建议

1. **DQC 检查实现**：Task 3.3 中的 DQC 检查当前是 TODO 状态
2. **集成测试**：添加端到端的 flow 测试验证真实数据流
3. **性能测试**：验证并行执行的性能提升

---

## 下一步计划

1. **Task 3.4**: 创建 flows/backfill.py（全量回补 Flow）
2. **Task 3.5**: 创建 flows/repair.py（修补 Flow）
3. **Task 3.6**: 创建 deploy.py（部署脚本）
4. **Phase 4**: Source 层简化
5. **Phase 5**: 清理和文档

---

## 工作流程优化

为提高效率，后续任务将采用以下优化：

1. **合并审查步骤**：规范审查和代码质量审查合并为一次
2. **简化流程**：对于相似任务（如 3.4-3.6），可以批量实现后统一审查
3. **减少子代理调用**：使用更直接的实现方式
