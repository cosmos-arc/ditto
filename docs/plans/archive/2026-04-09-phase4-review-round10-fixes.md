# Phase 4 Code Review Round 10 修复计划

## 概述

- **Sprint**: Phase 4 App Layer Extraction
- **创建**: 2026-04-09
- **来源**: Round 7-9 并行审查（6 维度），共发现 2 严重 + 5 中等 + 7 轻微问题
- **状态**: ✅ 已完成（2026-04-09）
- **创建**: 2026-04-09
- **来源**: Round 7-9 并行审查（6 维度），共发现 2 严重 + 5 中等 + 7 轻微问题

## 技术方案

### 关键决策

**#1 DQResult property 处理策略** — 更新准入标准而非移除 property

理由：`DQResult.has_errors` 等 7 个 `@property` 被 17 个文件（data/app/interfaces 三层 + 测试）广泛使用，移除会导致大规模重构且无实际收益。这些 property 是纯计算型（`any()`/`sum()`/`len()`），无副作用、无 I/O、无外部依赖。选择更新 kernel/CLAUDE.md 准入标准，明确豁免 frozen dataclass 上的纯计算型 `@property`。

**#2 QualityRecordService Protocol 抽象** — 在 quality_protocols.py 中定义 `QuarantineWriterProtocol`

与现有的 `QualityEngineProtocol`、`ComparisonStoreProtocol` 等保持一致的设计风格，避免 App 层直接耦合 Data 层具体实现类。

**#3 now_iso 归属** — 移至 `ditto_app.config` 模块

`now_iso()` 被 query 和 process 两个 CQRS 子模块使用，属于通用工具函数，不适合放在 `query._utils`（私有模块）中。`ditto_app.config` 已是 App 层的共享配置模块，放置时间戳工具函数合理。

---

## 任务清单

### Task 1: 更新 Kernel 准入标准 + 类型清单 `[M]`

- 验收: kernel/CLAUDE.md 准入标准明确豁免纯计算型 property；模块结构和类型清单更新
- 文件:
  - `packages/kernel/CLAUDE.md`
- 步骤:
  1. 值对象准入标准第 2 条修改为："零业务行为：纯值对象 / 枚举 / NewType。frozen dataclass 允许纯计算型 `@property`（无副作用、无 I/O、仅基于自身字段）"
  2. 模块结构中新增 `quality.py`、`exceptions.py`、`types.py`
  3. 当前类型清单新增 DQLevel/DQSeverity/DQIssue/DQResult、DataError/IdentifierError/NoIdentifierProvidedError/AmbiguousTickerError、InstrumentIngestParams

### Task 2: 修复 quality_reconciliation.py 冗余 except `[S]`

- 验收: 冗余的 `except Exception` 块被合并
- 文件:
  - `packages/app/src/ditto_app/process/quality_reconciliation.py`
- 步骤:
  1. 将第 113-121 行的两个 except 块合并为单个 `except Exception`
  2. 保留 `logger.exception` 调用（记录完整堆栈）

### Task 3: 定义 QuarantineWriterProtocol `[S]`

- 验收: `QualityService` 构造函数使用 Protocol 类型而非具体类
- 文件:
  - `packages/app/src/ditto_app/process/quality_protocols.py`
  - `packages/app/src/ditto_app/process/quality_check.py`
- 步骤:
  1. 在 `quality_protocols.py` 中定义 `QuarantineWriterProtocol`，包含 `save_failed_data` 方法签名
  2. 修改 `quality_check.py` 导入和类型注解：`QualityRecordService | None` → `QuarantineWriterProtocol | None`
  3. 验证现有 mock 测试无需修改（MagicMock 自动满足 Protocol）

### Task 4: 迁移 now_iso 至公共模块 `[S]`

- 验收: `_publication_helpers.py` 不再导入私有模块 `query._utils`
- 文件:
  - `packages/app/src/ditto_app/config.py`（新增 `now_iso`）
  - `packages/app/src/ditto_app/query/_utils.py`（删除 `now_iso`）
  - `packages/app/src/ditto_app/process/_publication_helpers.py`（更新导入）
  - `packages/app/src/ditto_app/process/materialization_orchestrator.py`（更新导入）
  - `packages/app/src/ditto_app/process/publication_facade.py`（更新导入）
  - `packages/app/src/ditto_app/process/materialization_helpers.py`（更新导入）
  - `packages/app/src/ditto_app/query/research.py`（更新导入）
- 步骤:
  1. 将 `now_iso` 函数移至 `ditto_app.config`
  2. 从 `query/_utils.py` 中删除 `now_iso`（无需向后兼容）
  3. 更新所有消费方的导入路径

### Task 5: 提取 AmbiguousTickerError 嵌套函数 `[S]`

- 验收: `format_match` 为模块级私有函数 `_format_match`
- 文件:
  - `packages/kernel/src/ditto_kernel/exceptions.py`
- 步骤:
  1. 提取 `format_match` 为 `_format_match`（模块级）
  2. 更新 `__init__` 中的调用

### Task 6: 测试质量修复 — async 误用 + fixture 重复 `[M]`

- 验收: 测试无不必要的 async 标记；fixture 复用 conftest
- 文件:
  - `packages/app/tests/unit/process/quality/test_reconciliation_service_unit.py`
  - `packages/app/tests/unit/process/quality/test_l3_batch_unit.py`
  - `packages/app/tests/unit/process/quality/conftest.py`
- 步骤:
  1. 修复 `sync_comparison_writer`：将 `async def write_comparison_impl` 改为 `def write_comparison_impl`（同步函数）
  2. 同时修复 `conftest.py` 中 `mock_comparison_writer` 的默认 side_effect（同样改为同步）
  3. 移除 `test_reconciliation_service_unit.py` 中所有不必要的 `@pytest.mark.asyncio` 和 `async` 关键字
  4. 将 `test_l3_batch_unit.py` 中的 `mock_engine`、`mock_market_service`、`mock_metadata_service` fixture 迁移至 `conftest.py`（与现有 `mock_quality_engine` 合并或独立定义）

### Task 7: runtime_builder.py 硬编码常量提取 `[S]`

- 验收: 金融默认值提取为模块级命名常量
- 文件:
  - `packages/app/src/ditto_app/builders/runtime_builder.py`
- 步骤:
  1. 在模块顶部定义常量：
     ```python
     _DEFAULT_COMMISSION_RATE = 0.0003
     _DEFAULT_SLIPPAGE_BPS = 5.0
     _DEFAULT_TRAILING_STOP_PCT = 0.08
     _DEFAULT_MAX_WEIGHT = 0.15
     _DEFAULT_TOP_K = 10
     ```
  2. 替换所有内联硬编码引用

### Task 8: quality_l3.py 神秘乘数命名 `[S]`

- 验收: `window * 2` 和 `lookback_days * 2` 使用命名常量
- 文件:
  - `packages/app/src/ditto_app/process/quality_l3.py`
- 步骤:
  1. 定义 `_CALENDAR_BUFFER_MULTIPLIER = 2`（周末/假日缓冲系数）
  2. 替换第 195 行 `window * 2` 和第 232 行 `lookback_days * 2`

### Task 9: 补充 _spec_deserializer.py 单元测试 `[M]`

- 验收: 12 个公共函数有基础参数校验测试
- 文件:
  - `packages/app/tests/unit/builders/test_spec_deserializer_unit.py`（新增）
- 步骤:
  1. 测试 `read_int`/`read_float`/`read_optional_int`/`read_optional_float` 的正常值和类型错误
  2. 测试 `read_bool` 的 bool 排除逻辑（`isinstance(True, int)` 边界）
  3. 测试 `read_required_str` 的 None 和空字符串错误
  4. 测试 `as_sequence`/`as_str_tuple`/`as_float_tuple`/`as_object_dict` 的类型转换

### Task 10: 补充 _commodity_fetcher.py 单元测试 `[M]`

- 验收: 双源获取逻辑有测试覆盖
- 文件:
  - `packages/app/tests/unit/process/test_commodity_fetcher_unit.py`（新增）
- 步骤:
  1. 测试正常双源合并
  2. 测试 FRED 失败降级（仅 Tushare 数据）
  3. 测试 Tushare 失败降级（仅 FRED 数据）
  4. 测试双源均失败（返回空 DataFrame）
  5. 测试 FRED 未配置（fred_source=None）

### Task 11: 文档一致性修复 `[M]`

- 验收: 所有文档描述与实际代码结构一致
- 文件:
  - `.claude/rules/architecture.md`（合约数量 22 → 24）
  - `AGENTS.md`（跨层依赖描述与 CLAUDE.md 对齐）
  - `packages/kernel/CLAUDE.md`（Task 1 已覆盖模块结构/类型清单）
- 步骤:
  1. `architecture.md` 第 85 行：`共 22 条合约` → `共 24 条合约`
  2. `AGENTS.md` 第 73 行：`interfaces 可以直接依赖 data.models/services/sources` → `interfaces 可以直接依赖 data.sources（仅 registry 例外范围可依赖 data.services/models）`

---

## 执行顺序

```
Task 1 (Kernel 准入标准)
  ↓
Task 2 (冗余 except) ─── Task 3 (Protocol 抽象) ─── Task 4 (now_iso 迁移)
  ↓                           ↓                         ↓
Task 5 (嵌套函数)         Task 6 (测试质量)         Task 7 (硬编码常量)
                                                      ↓
                                              Task 8 (神秘乘数)
  ↓
Task 9 (deserializer 测试) ─── Task 10 (fetcher 测试)
  ↓
Task 11 (文档修复)
```

独立任务可并行：Task 2/3/4/5/7/8 互相独立。
Task 6 依赖 Task 2/3 完成（避免测试冲突）。
Task 9/10 独立于其他任务。
Task 11 最后执行（汇总所有变更）。

## 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| Task 3 Protocol 变更影响 DI 注入 | 低 | MagicMock 自动满足 Protocol，无需修改 Provider |
| Task 4 now_iso 迁移影响范围 | 低 | _utils.py 保留 re-export，向后兼容 |
| Task 6 async→sync 测试变更 | 低 | 被测代码是同步的，移除 async 不影响行为 |
