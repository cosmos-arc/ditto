# Phase 1 代码审查修复设计

**日期**: 2026-03-20
**分支**: `feature/unified-feature-factor-engine-phase-1`
**变更规模**: 355 文件, +83,055 / -2,081 行
**审查维度**: 架构、PIT、规约、可维护、质量、文档

---

## 审查结果总览

| 维度 | ❌ Critical | ⚠️ Important | 💡 Suggestion |
|------|-----------|-------------|---------------|
| 架构 | 0 | 3 | 2 |
| PIT | 0 | 2 | 1 |
| 规约 | 2 | 3 | 0 |
| 可维护 | 1 | 5 | 0 |
| 质量 | 0 | 2 | 0 |
| 文档 | 4 | 8 | 0 |
| **合计** | **7** | **23** | **3** |

## 修复优先级

| 优先级 | 类别 | 问题数 | 说明 |
|--------|------|--------|------|
| **P0** | 合并门禁 | 10 | 架构合约、PIT 安全、关键文档 |
| **P1** | 本分支债务 | 7 | 文件拆分、重复代码、类型去重 |
| **P2** | 后续迭代 | 6 | 长函数、测试质量、noqa |
| **P3** | 文档 | 8 | README、ADR、规范示例 |
| **记录** | 偏离记录 | 1 | compile_cache I/O |

---

## P0: 合并门禁修复

### C1. Port → DataHub runtime 跨层访问

**现状**: `coordinator.py:27` 和 `factory.py:12` 直接导入 `ditto_datahub.runtime.freeze_manager`

**方案**: 在 `datahub.services` 中创建 `freeze` facade，Port 层通过 service 间接访问

**改动**:
1. 创建 `datahub/services/freeze_service.py`，封装 `FreezeManager` 调用
2. `coordinator.py` 和 `factory.py` 改为导入 `freeze_service`
3. DI 容器注册新 service

### C2. DataHub services 循环依赖

**现状**: `derived_catalog_service` ↔ `services.derived` 形成循环

**方案**: 将 `GcReport` 提取到 `datahub.models.derived`；`artifact_reader`/`query_service` 对 `DerivedCatalogService` 的导入改为 Protocol

**改动**:
1. `GcReport` 从 `garbage_collector.py` 移到 `datahub/models/derived.py`
2. `artifact_reader.py` 和 `query_service.py` 定义 `CatalogReader` Protocol
3. `derived_catalog_service.py` 实现该 Protocol

### C3. DataHub → Core 跨层依赖

**现状**:
- `artifact_persistence_service.py` 用 `TYPE_CHECKING` 导入 Core 类型
- `derived_artifact_writer.py` 用 `from __future__ import annotations` 隐藏 Core 导入

**方案**: Writer/Service 只接受 DataHub Record 类型，Port 层负责 Core → DataHub 类型转换

**改动**:
1. `derived_artifact_writer.py` 参数从 `DerivedSpec` 改为 record 类型字段
2. `artifact_persistence_service.py` 移除 `TYPE_CHECKING` 导入
3. Port 层编排代码中添加类型转换逻辑

### I1. lookback 日历日/交易日不匹配

**现状**: `planner.py:43-46` 用 `timedelta(days=lookback)` 减日历日

**方案**: 使用固定倍率 `math.ceil(lookback * 365 / 250)` 转换为日历日

**改动**:
1. `planner.py` 中添加 `_trading_days_to_calendar_days()` 转换函数
2. 替换 `timedelta(days=lookback)` 为 `timedelta(days=calendar_lookback)`

### I2. write_durable_partitions 未过滤预热行

**现状**: `derived_artifact_writer.py` 接收 `request_start` 但未用于过滤

**方案**: 在写入前按 `request_start` 过滤 frame（C3 修复后参数类型变化，此修复需适配）

**改动**:
1. 在 `write_durable_partitions` 的 Phase 1 之前添加 frame 过滤

### I3. 日志使用 logging 而非 loguru

**涉及文件**: `garbage_collector.py:5,15`、`derived_artifact_writer.py:5,25`

**方案**: 替换为 `from ditto_infra.foundation import logger`

**改动**: 2 处文件各替换 import 和 logger 调用

### C4. ADR 与代码不一致

**4a. ADR-034 REGISTERED 状态**: 代码无此状态 → 更新 ADR 移除或标注
**4b. ADR-035 InvalidationEvent 字段**: 与代码不匹配 → 更新字段定义
**4c. core/CLAUDE.md "待实现"**: engine 已实现 → 更新为 Phase 1 完成状态

---

## P1: 本分支债务修复

### C5. metrics.py 2140 行拆分

**方案**: 拆分为 `metrics/` 包

```
packages/core/src/ditto_core/engine/evaluation/metrics/
├── __init__.py          # re-export __all__
├── ic.py                # IC 相关函数 (8个)
├── portfolio.py         # 组合分析函数 (5个)
├── factor_analysis.py   # 因子分析函数 (3个)
├── tail_risk.py         # 尾部风险函数 (3个)
└── _math.py             # 数值辅助函数 (10个)
```

`__init__.py` 通过 `from .ic import *` 等 re-export，确保现有 import 路径不断。

### I4. metadata_service.py 1316 行拆分

**方案**: facade 模式拆分

```
packages/datahub/src/ditto_datahub/services/metadata/
├── __init__.py
├── calendar.py          # CalendarService (~200行)
├── instrument.py        # InstrumentService (~500行)
└── universe.py          # UniverseService (~200行)
```

保留 `metadata_service.py` 作为门面，`__init__` 有 15 个参数改为 3 个子服务。

### I5. 重复代码消除

**5a. baseline 解析**: 提取到 `DerivedCatalogService.get_primary_baseline_version()`
**5b. `_now_iso()`**: 统一到 `ditto_infra.foundation` 工具函数

### I7. materialization.py 629 行拆分

**方案**: 拆分为 `input_preparation.py` + `dq_summary.py` + `manifest_builder.py`

### I13+I14. 类型重复

**方案**: 提取到 `datahub/models/_json_types.py`，统一 `JsonPrimitive`/`JsonValue` 和 `_require_*` 工具函数

---

## P2: 后续迭代

### I6. coordinator.py noqa C901

评估函数复杂度来源，抽取子方法（可能在 C1 facade 上移时自然简化）。

### I11. metrics.py 长函数

`factor_exposure()` (215行) 和 `fama_macbeth()` (185行) 在 C5 拆分后归入 `factor_analysis.py`，进一步抽取子步骤。

### I12. 低断言密度测试

逐个审查 4 个文件：
- `test_derived_catalog_writer_unit.py` (3/10)
- `test_market_service_adj_status_unit.py` (2/6)
- `test_forward_return_service_unit.py` (3/9)
- `test_derived_catalog_service.py` (4/7)

补充缺失断言或确认 `mock.assert_*` 已覆盖验证需求。

---

## P3: 文档修复

### C6. docs/plans/README.md 过时

更新或标记为归档（最后更新 2026-01-23）。

### I7-I10. 文档不一致

- README 操作符数量 29→42: 更新
- 缺少 `factors/` 子包文档: 补充
- ADR-032 类型差异: 更新或添加注释说明设计演进

### S1. PIT 规范示例更新

在 `pit.md` 中添加 Polars 的 `shift(1) + rolling_*` 等价模式作为补充示例。

---

## 记录偏离

### S4. SQLiteCompileCache Core 层 I/O

`compile_cache.py` 中 `SQLiteCompileCache` 包含 SQL 操作，偏离 Core 层"无 I/O"原则。

**决策**: 记录为已知偏离（ADR）。理由：编译缓存与表达式编译器紧密耦合，放在 DataHub 会产生更严重的 Core → DataHub Service 依赖。I/O 通过 `SQLiteCompileCacheBackend` Protocol 注入（依赖倒置），具体实现由 DataHub 的 SQLiteClient 执行。暂不重构。

---

## 验证

所有修复完成后运行：
```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev lint-imports    # 6 个 contract 全部通过
```
