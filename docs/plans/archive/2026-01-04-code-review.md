# 代码审查报告

**日期**: 2026-01-04
**范围**: 最近 5 次提交的全量代码审查
**基准 SHA**: e18818474e9be21421f556eef98b8ea2ad667782
**当前 SHA**: 694a4cfa9f422a3fedf6ae32b7d8e056a3f7dd5e
**审查维度**: PIT 安全、风控、代码质量、文档同步

---

## 变更概览

### 主要变更文件
1. **数据摄入层** (`apps/server/src/ditto_port/ingestion/`)
   - `services/backfill.py` - 回补管理器
   - `services/coordinator.py` - 摄取协调器
   - `tasks/dq_batch.py` - DQ 批量检查任务

2. **Tushare 数据源** (`packages/data/src/ditto_data/sources/tushare/`)
   - `client.py` - HTTP 客户端重构
   - `http_utils.py` - HTTP 工具函数
   - `source.py` - 数据源实现

3. **Repository 层** (`packages/data/src/ditto_data/repositories/`)
   - `security.py` - 证券仓库
   - `adj_factor.py` - **新增** 复权因子仓库

4. **测试**
   - `test_end_to_end.py` - **新增** 端到端集成测试
   - 单元测试更新

5. **文档**
   - `docs/plans/2026-01-03-tushare-http-refactor.md` - **新增** Tushare HTTP 重构计划
   - `docs/plans/2026-01-03-ingestion-crifixes.md` - **更新** 摄取系统修复计划

---

## 一、PIT 安全审查

### ✅ 通过项

1. **无 rolling_* 操作风险**
   - 代码库中没有发现 `rolling_mean()`, `rolling_std()`, `rolling_sum()` 等操作
   - 避免了 `closed="left"` 参数遗漏的 PIT 风险

2. **knowledge_date 正确使用**
   - [test_end_to_end.py:188](packages/data/tests/integration/sources/tushare/test_end_to_end.py#L188) 验证了 `knowledge_date == trade_date`（复权因子数据即日可用）
   - adj_factor schema 正确定义了 knowledge_date 字段

3. **游标管理改进**
   - [coordinator.py:190-196](apps/server/src/ditto_port/ingestion/services/coordinator.py#L190-L196) 正确处理游标更新逻辑
   - T0 数据集（stock_basic, etf_basic）在各自的 `_write_*` 方法中更新游标
   - T1/T2 数据集在 `ingest_date` 中统一更新游标

### ❌ 需修复问题

**Important**（建议修复）：

1. **knowledge_date 传递验证**
   - **位置**: 多个文件使用 knowledge_date
   - **问题**: 需要确保所有数据源正确设置 knowledge_date
   - **建议**: 在 DQ 检查中验证 knowledge_date <= 当前日期
   - **文件**:
     - [pit_helper.py](packages/data/src/ditto_data/runtime/pit_helper.py)
     - [bars.py](packages/data/src/ditto_data/repositories/bars.py)

### PIT 安全总体评级: 🟢 通过

---

## 二、风控审查

### ✅ 通过项

1. **认证错误处理** ✅
   - [http_utils.py:33-40](packages/data/src/ditto_data/sources/tushare/http_utils.py#L33-L40) 正确识别认证错误码（2002, 40101）
   - [client.py:66-80](packages/data/src/ditto_data/sources/tushare/client.py#L66-L80) 支持 keyring/secrets.toml/env 多源 token 获取

2. **限流机制** ✅
   - [client.py:152-155](packages/data/src/ditto_data/sources/tushare/client.py#L152-L155) 使用 TushareRateLimiter
   - [client.py:204-206](packages/data/src/ditto_data/sources/tushare/client.py#L204-L206) API 分组限流
   - 端到端测试验证限流机制 ([test_end_to_end.py:253-281](packages/data/tests/integration/sources/tushare/test_end_to_end.py#L253-L281))

3. **重试机制** ✅
   - [client.py:251-255](packages/data/src/ditto_data/sources/tushare/client.py#L251-L255) 使用 tenacity 重试
   - 指数退避：1-10 秒，最多 3 次重试

4. **并发写入保护** ✅
   - [adj_factor.py:81-86](packages/data/src/ditto_data/repositories/adj_factor.py#L81-L86) 使用文件锁保护
   - [coordinator.py:264](apps/server/src/ditto_port/ingestion/services/coordinator.py#L264) 使用 BarsRepository（带文件锁）

5. **错误分类处理** ✅
   - [http_utils.py:68-134](packages/data/src/ditto_data/sources/tushare/http_utils.py#L68-L134) 完整的错误映射
   - 区分认证错误、限流错误、网络错误、超时错误

6. **空数据处理** ✅
   - [coordinator.py:138-153](apps/server/src/ditto_port/ingestion/services/coordinator.py#L138-L153) 正确处理空数据
   - [source.py:99-107](packages/data/src/ditto_data/sources/tushare/source.py#L99-L107) 返回空 schema 而非错误

7. **降级策略** ✅
   - [coordinator.py:103-120](apps/server/src/ditto_port/ingestion/services/coordinator.py#L103-L120) 失败返回 IngestionResult 而非抛出异常
   - 支持跳过已摄取数据

### 风控总体评级: 🟢 通过

---

## 三、代码质量审查

### ✅ 通过项

1. **技术栈合规性** ✅
   - **无 pandas 导入**: 全部使用 polars
   - **HTTP 客户端**: 使用 httpx（符合规范）
   - **重试/限流**: 使用 tenacity/limits（符合规范）
   - **日志**: 使用 loguru（符合规范）
   - **指标**: 使用 M (metrics)（符合规范）

2. **类型注解** ✅
   - [client.py](packages/data/src/ditto_data/sources/tushare/client.py) 类型注解完整
   - [adj_factor.py](packages/data/src/ditto_data/repositories/adj_factor.py) 使用 TYPE_CHECKING 避免循环导入
   - [http_utils.py:68](packages/data/src/ditto_data/sources/tushare/http_utils.py#L68) 使用 NoReturn 类型标注

3. **错误处理** ✅
   - 自定义异常体系（SourceAuthenticationError, SourceRateLimitError, SourceFetchError）
   - 异常链保留（`raise ... from e`）
   - 详细错误信息（包含 API 名称、原始错误）

4. **代码结构** ✅
   - 职责分离：Client 负责 HTTP，Source 负责数据转换
   - 单一职责：BackfillManager 只管理回补，Coordinator 协调摄取
   - DRY 原则：_record_metrics 复用

5. **测试覆盖** ✅
   - [test_end_to_end.py](packages/data/tests/integration/sources/tushare/test_end_to_end.py) 330 行完整的端到端测试
   - 测试场景：认证、限流、数据一致性、OHLC 逻辑验证
   - 使用 @pytest.mark.external 标记需要真实 API 的测试

### ❌ 需修复问题

**Important**（建议修复）：

1. **ruff PLC0415 错误**（7 个）
   - **问题**: import 语句应放在文件顶层
   - **影响文件**:
     - [backfill.py:75, 149](apps/server/src/ditto_port/ingestion/flows/backfill.py#L75)
     - [repair.py:46, 116, 119](apps/server/src/ditto_port/ingestion/flows/repair.py#L46)
     - [t0_meta.py:85, 87](apps/server/src/ditto_port/ingestion/tasks/t0_meta.py#L85)
   - **建议**: 将这些 import 移至文件顶层，或添加 `# noqa: PLC0415` 注释（如果是有意延迟导入）

**Minor**（可选）：

2. **文档字符串**
   - [backfill.py](apps/server/src/ditto_port/ingestion/services/backfill.py) 的方法文档字符串完整
   - 建议为新增的 AdjFactorRepository 添加 README

3. **代码复杂度**
   - [coordinator.py](apps/server/src/ditto_port/ingestion/services/coordinator.py) 347 行，建议考虑拆分
   - 当前可接受，但未来可考虑按数据集拆分 Coordinator

### 代码质量总体评级: 🟡 需改进

---

## 四、文档同步审查

### ✅ 通过项

1. **计划文档** ✅
   - [2026-01-03-tushare-http-refactor.md](docs/plans/2026-01-03-tushare-http-refactor.md) 完整记录 Tushare HTTP 重构计划
   - [2026-01-03-ingestion-crifixes.md](docs/plans/2026-01-03-ingestion-crifixes.md) 显示所有 10 个任务已完成 ✅

2. **Sprint 状态** ✅
   - [sprint-02-data-quality.md](docs/sprints/sprint-02-data-quality.md) Phase 0 技术债务清理已完成
   - DQ 三层架构完整实现 ✅

3. **测试文档** ✅
   - [test_end_to_end.py](packages/data/tests/integration/sources/tushare/test_end_to_end.py) 包含完整的测试说明文档
   - [QUICK_REFERENCE.md](packages/data/tests/integration/sources/tushare/QUICK_REFERENCE.md) 测试快速参考（根据 git status）

### ❌ 需修复问题

**Important**（建议修复）：

1. **缺少 IMPLEMENTATION_SUMMARY.md**
   - **问题**: git status 显示 `IMPLEMENTATION_SUMMARY.md` 新增但未找到文件
   - **影响**: Tushare HTTP 重构的完成总结缺失
   - **建议**: 创建该文件记录：
     - 重构前后的差异
     - 测试覆盖率
     - 性能对比
     - 已知问题

2. **Sprint 2 任务状态更新**
   - [sprint-02-data-quality.md](docs/sprints/sprint-02-data-quality.md) 显示 Phase 0 已完成
   - 建议更新 Phase 1/2/3 的进度
   - 黄金数据集验证状态为 ⏳，需更新

3. **README 更新**
   - [packages/data/src/ditto_data/sources/tushare/](packages/data/src/ditto_data/sources/tushare/) 缺少 README
   - 建议添加：
     - Tushare 数据源使用说明
     - HTTP API 规范
     - 限流配置说明
     - Token 配置方法

**Minor**（可选）：

4. **ADR 更新**
   - Tushare HTTP 重构是重大架构变更
   - 建议创建 ADR 记录：
     - 为什么选择 httpx 而非 SDK
     - 为什么选择同步而非异步
     - 限流策略的选择

### 文档同步总体评级: 🟡 需改进

---

## 五、架构约束审查

### ✅ 通过项

1. **依赖方向** ✅
   - apps/server → packages/data → packages/foundation
   - Coordinator 依赖 DataHub（正确）
   - TushareSource 依赖 DataSource 基类（正确）

2. **分层职责** ✅
   - Foundation: 配置、日志、追踪
   - DataHub: Store/Repository/DQ
   - Server: FastAPI、Prefect 调度

3. **数据格式** ✅
   - 使用 polars DataFrame
   - 存储：parquet/duckdb/sqlite

### 架构约束总体评级: 🟢 通过

---

## 六、总体结论

### 汇总表

| 维度 | 评级 | Critical | Important | Minor |
|------|------|----------|-----------|-------|
| PIT 安全 | 🟢 通过 | 0 | 1 | 0 |
| 风控 | 🟢 通过 | 0 | 0 | 0 |
| 代码质量 | 🟡 需改进 | 0 | 1 | 3 |
| 文档同步 | 🟡 需改进 | 0 | 3 | 1 |
| 架构约束 | 🟢 通过 | 0 | 0 | 0 |

### 最终结论: 🟢 可合并

**理由**：
1. ✅ PIT 安全和风控审查全部通过
2. ✅ 技术栈完全符合项目规范
3. ⚠️ 代码质量有 7 个 ruff 错误（PLC0415），但不影响功能
4. ⚠️ 文档需要补充 IMPLEMENTATION_SUMMARY.md

### 建议行动

**合并前必须修复**（无）：

**合并后建议修复**（Important）：

1. **代码质量**: 修复 7 个 ruff PLC0415 错误
   - 将 import 移至顶层或添加 noqa 注释
   - 文件：backfill.py, repair.py, t0_meta.py

2. **文档同步**:
   - 创建 IMPLEMENTATION_SUMMARY.md
   - 更新 Sprint 2 进度
   - 添加 tushare/README.md

**可选改进**（Minor）：

3. 添加 Tushare HTTP 重构 ADR
4. 拆分 coordinator.py（当前 347 行）
5. 添加 AdjFactorRepository README

---

## 附录 A：关键文件路径

### 核心实现文件
- [apps/server/src/ditto_port/ingestion/services/backfill.py](apps/server/src/ditto_port/ingestion/services/backfill.py)
- [apps/server/src/ditto_port/ingestion/services/coordinator.py](apps/server/src/ditto_port/ingestion/services/coordinator.py)
- [apps/server/src/ditto_port/ingestion/tasks/dq_batch.py](apps/server/src/ditto_port/ingestion/tasks/dq_batch.py)
- [packages/data/src/ditto_data/sources/tushare/client.py](packages/data/src/ditto_data/sources/tushare/client.py)
- [packages/data/src/ditto_data/sources/tushare/http_utils.py](packages/data/src/ditto_data/sources/tushare/http_utils.py)
- [packages/data/src/ditto_data/repositories/adj_factor.py](packages/data/src/ditto_data/repositories/adj_factor.py)（新增）

### 测试文件
- [packages/data/tests/integration/sources/tushare/test_end_to_end.py](packages/data/tests/integration/sources/tushare/test_end_to_end.py)（新增）

### 文档文件
- [docs/plans/2026-01-03-tushare-http-refactor.md](docs/plans/2026-01-03-tushare-http-refactor.md)（新增）
- [docs/plans/2026-01-03-ingestion-crifixes.md](docs/plans/2026-01-03-ingestion-crifixes.md)（更新）

---

## 附录 B：测试覆盖率

| 组件 | 单元测试 | 集成测试 | 总计 |
|------|---------|---------|------|
| Tushare Client | - | ✅ (端到端) | 330 行 |
| Tushare Source | ✅ | ✅ (端到端) | 330 行 |
| Coordinator | ✅ | - | 现有测试 |
| Backfill | ✅ | - | 现有测试 |
| DQ Batch | ✅ | - | 现有测试 |
| AdjFactor Repository | ✅ | - | 新增测试 |

**注**: 端到端测试需要真实 Tushare Token，使用 @pytest.mark.external 标记，CI 默认跳过。

---

**审查完成时间**: 2026-01-04
**审查工具**: 人工代码审查 + ruff + grep
**审查方法**: 静态分析 + 文档对照
