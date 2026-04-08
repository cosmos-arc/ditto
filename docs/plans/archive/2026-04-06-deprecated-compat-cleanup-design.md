# 全面清理废弃与兼容代码

> 日期：2026-04-06
> 分支：`refactor/phase4-app-layer-extraction`
> 范围：全库（infra / kernel / data / analytics / app / engine / interfaces）

## 目标

项目处于开发期，无外部消费者。删除所有向后兼容 shim、废弃代码、legacy 迁移逻辑，
减少约 500-800 行死代码，消除架构噪声。

## 设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| FRED NotImplementedError stub | 保留 | Protocol 合规性设计 |
| Hot Layer stub 模块 | 保留 | Phase 5+ 预留接口 |
| S608 noqa（SQL format） | 保留 | 表名/列名无法参数化 |
| S101 noqa（assert） | 保留 | invariant check |

## Phase A：删除 Re-export Shim 文件（15 个）

### App 层（5 个）

| shim 文件 | 导入目标 | 导出符号数 |
|-----------|---------|-----------|
| `ditto_app/process/ingestion.py` | 子模块 | 18 |
| `ditto_app/process/coordinator.py` | 子模块 | 12 |
| `ditto_app/process/materialization.py` | 子模块 | 24 |
| `ditto_app/process/strategy.py` | 子模块 | 12 |
| `ditto_app/builders/strategy.py` | 子模块 | 6 |

### Data 层（6 个）

| shim 文件 | 导入目标 |
|-----------|---------|
| `ditto_data/services/ingestion_log_service.py` | `ditto_data.ingestion` |
| `ditto_data/services/publication_safety_record_service.py` | `ditto_data.ingestion` |
| `ditto_data/services/quality_record_service.py` | `ditto_data.ingestion` |
| `ditto_data/services/late_arrival.py` | `ditto_data.ingestion` |
| `ditto_data/services/ingestion_cursor_service.py` | `ditto_data.ingestion` |
| `ditto_data/services/freeze_service.py` | `ditto_data.ingestion` |

### Analytics 层（1 个）

| shim 文件 | 导入目标 |
|-----------|---------|
| `ditto_analytics/models/research.py` | `ditto_kernel` 直接导入 |

### Engine 层（3 个）

| shim 文件 | 导入目标 |
|-----------|---------|
| `ditto_engine/backtest/risk/__init__.py` | `ditto_engine.risk` |
| `ditto_engine/backtest/risk/pre_trade.py` | `ditto_engine.risk.pre_trade` |
| `ditto_engine/backtest/risk/post_trade.py` | `ditto_engine.risk.post_trade` |

### 实施步骤

1. 对每个 shim 文件，搜索所有引用该模块的 import 语句
2. 更新引用直接指向目标模块
3. 删除 shim 文件
4. 运行 `pixi run -e dev check` 验证

## Phase B：废弃代码清理

### B.1 删除 `SimpleGauge`（已废弃）

- 文件：`packages/infra/src/ditto_infra/foundation/observability/metrics.py`
- 操作：删除类定义，搜索所有引用并替换

### B.2 移除 `value_std` 兼容参数

- 文件：`packages/app/src/ditto_app/process/materialization_helpers.py`
- 操作：从 `_compute_value_jump_rate` 签名中删除 `value_std`，删除 `_ = value_std`
- 同步更新所有调用方

### B.3 移除 `ts_diff` 兼容别名

- 文件：`packages/analytics/src/ditto_analytics/expression/codegen.py`、`registry.py`
- 操作：删除 `ts_diff` 注册，全局替换 `ts_diff` → `ts_delta`

### B.4 移除私有符号重导出

- `_infer_exchange_suffix`：更新测试从 `ingestion_coordinator` 直接导入
- `_scalar_to_float` / `_two_sided_p_value`：更新测试从 `_math` 模块直接导入

## Phase C：Legacy 迁移代码 + 配置 + TYPE_CHECKING

### C.1 简化 SQLite Legacy Schema 处理

- `_handle_legacy_schema`：开发期可简化为直接重建
- `LegacySchemaError`：评估是否仍需要

### C.2 移除 execution_audit 列迁移

- `instrument_scope` 列迁移：开发期假设 schema 最新，删除运行时迁移

### C.3 删除 Vector 旧格式日志配置

- 移除 `legacy_logs` source 和 `legacy_logs_transform`

### C.4 修复 TYPE_CHECKING 块（4 个测试文件）

- `test_exchange_transformers_unit.py`：空块 → 删除
- `conftest.py`（infra observability）：直接导入
- `reporter.py` + `test_quality.py`（e2e）：直接导入

### C.5 删除废弃功能测试（8 个）

| 测试 | 文件 |
|------|------|
| `test_backward_compatibility_md5_raises_error` | data/tests |
| `test_backward_compatible` | analytics/tests |
| `test_sharpe_zero_rf_backward_compat` | analytics/tests |
| `TestMacroTushareAdapterLegacyMethod` | data/tests |
| `find_series() streaming=False backward compat` | data/tests |
| `test_migrates_legacy_table_missing_instrument_scope` | data/tests |
| `TestLegacySchemaProtection`（4 tests） | infra/tests |
| `test_compute_value_jump_rate_value_std_ignored` | app/tests |

## Phase D：代码质量优化

### D.1 消除 Triplicated CLI 代码

- `_run_instrument_ingest`（3 份相同代码）→ 提取到 `ingest/_shared.py`

### D.2 源码 noqa / type:ignore 优化

**消除（~10 处）**：
- `PLR0913`（参数过多）→ 重构为配置对象
- `PLC0415`（延迟导入 in errors）→ 正常 import
- `reportUnknownParameterType` → 改善类型标注

**保留（~10 处）**：
- `S608`（SQL format 用于表名/列名）
- `S101`（assert for invariant）
- `S108`（hardcoded /tmp in test config）

## 验证

每个 Phase 完成后运行：
```bash
pixi run -e dev check   # lint + fmt + type + test --fast
```

## 风险

| 风险 | 缓解 |
|------|------|
| 导入路径遗漏 | `check` 命令包含 pyright 类型检查 |
| 废弃测试依赖 | 每个 Phase 独立验证 |
| Legacy schema 回归 | 开发期无生产数据 |
