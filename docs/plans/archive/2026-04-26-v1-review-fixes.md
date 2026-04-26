# V1 Sprint Code Review 全量修复计划

## 概述
- Sprint: V1 | Phase: Review Fix
- 创建: 2026-04-26
- 范围: 5 组审查 agent 发现的 27 项 confirmed issues（排除 2 项非问题）

## 技术方案
按包边界并行修复，每组内按依赖顺序执行。TYPE_CHECKING 消除为最高风险项，需逐个分析循环依赖根因。

## 任务清单

### Group 1: Kernel 修复 [S] — 4 files
- [x] Task 1.1: `math.py` pearson_correlation strict 修复 `[S]`
  - 验收: `zip(x, y, strict=False)` → `zip(x, y, strict=True)`；新增长度不等测试
  - 文件: `packages/kernel/src/ditto_kernel/math.py:46`, `packages/kernel/tests/unit/test_math.py`

- [x] Task 1.2: `__init__.py` 补充 MacroCategory 导出 `[S]`
  - 验收: `MacroCategory` 出现在 import 和 `__all__` 中；`from ditto_kernel import MacroCategory` 可用
  - 文件: `packages/kernel/src/ditto_kernel/__init__.py`

- [x] Task 1.3: CLAUDE.md 文档修正 `[S]`
  - 验收: ImpactModel 枚举值改为 `NONE/VOLUME_SHARE`；RunStatus 补充 `CANCELLED`
  - 文件: `packages/kernel/CLAUDE.md:91,93`

- [x] Task 1.4: DQSeverity docstring 增强 `[S]`
  - 验收: 补充各 severity level 含义说明（与 DQLevel docstring 风格一致）
  - 文件: `packages/kernel/src/ditto_kernel/quality.py:34`

### Group 2: Infra 修复 [S] — 3 files
- [x] Task 2.1: Webhook 模板 instrument_id JSON 引号 `[S]`
  - 验收: 使用 Jinja2 `tojson` filter 替代手动引号；5 个字段全部修复
  - 文件: `packages/infra/src/ditto_infra/services/notification/templates/signal_trading_webhook.j2:9`

- [x] Task 2.2: 测试中 stale ChecksumCompute API 调用修复 `[S]`
  - 验收: 3 处 `ChecksumCompute.from_dataframe(df, "stock_daily")` → `ChecksumCompute.from_dataframe(df)`
  - 文件: `packages/app/tests/unit/process/ingestion/test_metadata_unit.py:188,243,300`

### Group 3: Analytics 修复 [S-M] — 5 files
- [x] Task 3.1: 消除重复 obv factor spec `[S]`
  - 验收: 从 technical.py 移除重复 `"obv"` 条目，保留 `"obv_ma20"`
  - 文件: `packages/analytics/src/ditto_analytics/factors/technical.py`

- [x] Task 3.2: computation_type 改为 Literal 类型 `[S]`
  - 验收: `computation_type: str` → `computation_type: Literal["expression", "python"]`
  - 文件: `packages/analytics/src/ditto_analytics/factors/spec.py:65`

- [x] Task 3.3: evaluator.py O(n²) turnover 优化 `[M]`
  - 验收: 用 Polars `group_by + diff + mean` 替代逐行 filter，复杂度降到 O(n)
  - 文件: `packages/analytics/src/ditto_analytics/evaluation/evaluator.py:663-690`

- [x] Task 3.4: validate.py 数据前缀改为可扩展注册 `[S]`
  - 验收: 保留 `_KNOWN_DATA_PREFIXES` 常量并添加维护 comment
  - 文件: `packages/analytics/src/ditto_analytics/factors/validate.py:19`

### Group 4: Data 修复 [S-M] — 5 files
- [x] Task 4.1: FillWriter 添加幂等保护 `[S]`
  - 验收: `INSERT INTO` → `INSERT OR IGNORE INTO`
  - 文件: `packages/data/src/ditto_data/storage/execution/fill_writer.py:42`

- [x] Task 4.2: TradeProvider DDL 移至单次初始化 `[S]`
  - 验收: 提取 `init_schema` 方法 + `@provide` + `Scope.APP`；`trade_service` 用 `_schema_initialized: None` 排序
  - 文件: `packages/data/src/ditto_data/di/trade.py:48-62`

- [x] Task 4.3: SqliteTableWriter 错误信息增强 `[S]`
  - 验收: 在 try 块前预检查 non-nullable columns 存在性，提供描述性 ValueError
  - 文件: `packages/data/src/ditto_data/storage/base/sqlite_table_writer.py`

- [ ] Task 4.4: IndexConstituentReader/Writer 迁移至 SqliteTableSpec `[M]`
  - 验收: 使用 SqliteTableSpec + SqliteTableReader/Writer 模式，与 capital/fundamental 一致
  - 文件: `packages/data/src/ditto_data/storage/market/index/constituent/constituent_reader.py`, `constituent_writer.py`
  - **延期原因**: PIT 语义差异 — 当前用 `MAX(effective_date)` 取最新成分，SqliteTableSpec 用 `effective_from/effective_to` 区间模式，需架构决策
  - 文件: `packages/data/src/ditto_data/storage/market/index/constituent/constituent_reader.py`, `constituent_writer.py`

### Group 5: Engine 修复 [S-M] — 7 files
- [x] Task 5.1: brokerage.py AssertionError → 领域异常 `[S]`
  - 验收: `raise AssertionError(...)` → `raise EngineError(...)` + import
  - 文件: `packages/engine/src/ditto_engine/execution/brokerage.py:360`

- [x] Task 5.2: frame.py validate_frame 添加 __debug__ 守卫 `[S]`
  - 验收: 函数体包裹 `if __debug__:` 守卫；release 模式下 no-op
  - 文件: `packages/engine/src/ditto_engine/alpha/frame.py:33-49`

- [x] Task 5.3: _input_bundle.py 重命名为 input_bundle.py `[S]`
  - 验收: `git mv` 移除下划线前缀；更新 3 个 import 引用
  - 文件: `packages/engine/src/ditto_engine/backtest/steps/input_bundle.py`, `steps/__init__.py`, `engine.py`, `strategy.py`

- [x] Task 5.4: 测试 conftest helpers 类型修复 `[M]`
  - 验收: 修复 NewType 构造 (`InstrumentId(1)` 而非 `IID_1: InstrumentId = 1`)、参数类型注解、dict key 类型
  - 文件: `packages/engine/tests/unit/backtest/conftest.py`
  - **方案调整**: 保持 helpers 在 conftest.py 中（pytest 标准做法），不提取到独立 `_helpers.py`

### Group 6: App TYPE_CHECKING 消除 [M-L] — 4+ files
> 分析结论：5 个文件中仅 1 个存在真正循环依赖，其余 4 个可直接移除 TYPE_CHECKING

- [x] Task 6.1: 分析 TYPE_CHECKING 根因 `[S]`
  - 结论: `fetch_handlers.py ↔ coordinator.py` 存在真实循环依赖，通过提取 `SourceFetchers` 类型到 `types.py` 解决
  - 其余 4 文件均为假阳性，直接移除 TYPE_CHECKING guard

- [x] Task 6.2: 消除 app/query/source.py TYPE_CHECKING `[M]`
  - 已在未提交修改中完成

- [x] Task 6.3: 消除 app/process/ingestion/ 4 文件 TYPE_CHECKING `[M]`
  - 已在未提交修改中完成；`fetch_handlers.py ↔ coordinator.py` 通过 `types.py` 提取解决

- [x] Task 6.4: 消除 interfaces/api/routes/source.py TYPE_CHECKING `[M]`
  - 已在未提交修改中完成

### Group 7: App 其他修复 [S] — 2 files
- [x] Task 7.1: providers.py os.environ 改为 typed config `[S]`
  - 验收: 替换为 `TradingSettings` 参数注入；在 `infra.foundation.config.settings` 添加字段；在 registry DI 注册
  - 文件: `packages/app/src/ditto_app/providers.py`, `packages/infra/src/ditto_infra/foundation/config/settings.py`, `interfaces/src/ditto_interfaces/registry/infra/config.py`

- [x] Task 7.2: delivery.py 收窄异常捕获 `[S]`
  - 验收: `except Exception:` → `except (OSError, ConnectionError, TimeoutError):`；`logger.exception` → `logger.error`
  - 文件: `packages/app/src/ditto_app/process/execution/delivery.py:43`

### Group 8: Interfaces 修复 [S-M] — 5 files
- [x] Task 8.1: 偏差端点标记为 placeholder `[S]`
  - **无需修改**: 端点已完整实现，不是 placeholder

- [x] Task 8.2: backtest dict 返回改为 Pydantic model `[M]`
  - 验收: 新增 `BacktestReportResponse`, `NavPointResponse` 等 Pydantic model；替换 `dict[str, object]` 返回
  - 文件: `interfaces/src/ditto_interfaces/api/routes/backtest.py`, `interfaces/src/ditto_interfaces/models/backtest.py`

- [x] Task 8.3: 分页添加 TODO 注释 `[S]`
  - 验收: 在 `paginate` 函数添加注释说明当前为内存分页
  - 文件: `interfaces/src/ditto_interfaces/api/deps.py:22`

- [x] Task 8.4: 移除未使用的 RouteValidationError `[S]`
  - **无需修改**: 该类仍在测试中正确使用

## 执行记录

### Wave 1（并行）: Group 1 + Group 2 + Group 5 + Group 7
- 状态: ✅ 完成
- 备注: EngineError import 遗漏已在验证阶段修复

### Wave 2（并行）: Group 3 + Group 4
- 状态: ✅ 完成（Task 4.4 延期）
- 备注: Task 4.4 因 PIT 语义差异延期，需架构决策

### Wave 3（串行）: Group 6 — TYPE_CHECKING 消除
- 状态: ✅ 完成
- 备注: 所有 5 文件 TYPE_CHECKING 已在未提交修改中解决

### Wave 4（并行）: Group 8 — Interfaces 修复
- 状态: ✅ 完成
- 备注: Task 8.1 和 8.4 审查后发现无需修改

## 验证结果

```
pixi run -e dev check (2026-04-26)
├── lint:     All checks passed ✅
├── fmt:      1328 files unchanged ✅
├── type:     0 errors, 0 warnings ✅
└── test:     5852 passed, 25 skipped ✅

pixi run -e dev arch-check
└── 33 contracts kept, 0 broken ✅
```

## 延期任务

| 任务 | 原因 | 跟踪 |
|------|------|------|
| Task 4.4: IndexConstituentReader/Writer 迁移 | PIT 语义差异 (`MAX(effective_date)` vs `effective_from/effective_to`)，需架构决策 | 后续 Sprint |
