# 架构审计报告 2026-02-09

## 执行摘要

| 指标 | 数值 |
|------|------|
| **审计日期** | 2026-02-09 |
| **审计范围** | packages/ (foundation, datahub, core) + apps/port |
| **源代码文件** | ~300 个 .py 文件 |
| **Lint 检查** | ✅ 通过 (0 错误) |
| **类型检查** | ✅ 通过 (0 错误, 0 警告) |
| **单元测试** | ⚠️ 1950 通过, 1 失败, 5 跳过 |
| **测试覆盖率** | ✅ 82.45% (≥80%) |

### 问题统计

| 严重级别 | 数量 | 状态 |
|----------|------|------|
| **Blocker** | 0 | - |
| **High** | 3 | 需要关注 |
| **Medium** | 8 | 需要改进 |
| **Low** | 5 | 可选优化 |

---

## Top 5 高优先级问题

| 排名 | 问题编号 | 严重级别 | 描述 | 位置 |
|------|---------|----------|------|------|
| 1 | ARCH-001 | High | `CapitalTushareAdapter` 类规模过大 (1113行) | [capital.py:1](packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py) |
| 2 | ARCH-002 | High | Port 层违规导入 `QuarantineStore` | [service.py:7](apps/port/src/ditto_port/services/ingestion/quality/service.py) |
| 3 | TEST-001 | High | 单元测试失败 (InstrumentStore) | [test_security_store_unit.py](packages/datahub/tests/unit/stores/test_security_store_unit.py) |
| 4 | ARCH-003 | Medium | 多个类超过 600 行，维护风险 | 多个文件 |
| 5 | NAM-001 | Medium | Port 层使用技术术语 `DatabaseManager` | [testing.py](apps/port/src/ditto_port/testing.py) |

---

## 推断架构 (Inferred Architecture)

### 分层依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                    apps/port (应用层)                        │
│                         │                                    │
│                         ├──→ packages/datahub (数据层)       │
│                         │         │                          │
│                         │         └──→ packages/foundation   │
│                         │                                    │
│                         └──→ packages/core (核心层)          │
│                                   │                          │
│                                   └──→ packages/foundation   │
└─────────────────────────────────────────────────────────────┘
```

**依赖规则验证**：
- ✅ Foundation → 零依赖 (无违规)
- ✅ DataHub → Foundation (无违规)
- ✅ Core → Foundation + DataHub.models (无违规)
- ⚠️ Port → DataHub.runtime (1处违规)

### 统计数据

| 层级 | 文件数 | 主要类 | 职责 |
|------|--------|--------|------|
| **Foundation** | ~50 | SQLitePool, FileLockManager, DataCache | 基础设施 |
| **DataHub** | ~120 | MarketService, MetadataService, CapitalService | 数据访问 |
| **Core** | ~30 | QualityEngine, BusinessChecker | 业务逻辑 |
| **Port** | ~60 | IngestionCoordinator, DailyFlow | 应用编排 |

---

## 详细发现

### ARCH-001: 超大类文件 (High)

**问题描述**: `CapitalTushareAdapter` 类规模达到 1113 行，超出单文件推荐上限 (800行)。

**位置**: [capital.py](packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py)

**影响**:
- 维护困难
- 违反单一职责原则
- 增加修改风险

**建议**: 按数据类型拆分 Adapter
```
CapitalTushareAdapter (1113行)
├── ValuationAdapter
├── FundamentalAdapter (BalanceSheet, IncomeStatement, CashFlow)
├── CorporateActionAdapter (Dividend, PledgeRatio, MarginTrading)
└── IndexCompositionAdapter
```

---

### ARCH-002: Port 层违规导入 Runtime (High)

**问题描述**: Port 层业务代码 `QualityService` 直接导入 `QuarantineStore` (Runtime 层)。

**位置**: [service.py:7](apps/port/src/ditto_port/services/ingestion/quality/service.py)
```python
from ditto_datahub.runtime.quality.quarantine_store import QuarantineStore
```

**违反规则**: v5 强制边界 - Port 非 registry 模块禁止直接导入 Runtime。

**建议**: 通过 DataHub Service 访问或添加到 registry。

---

### TEST-001: 单元测试失败 (High)

**问题描述**: `test_register_logs_error_on_exception` 失败。

**错误信息**:
```
AttributeError: module 'ditto_datahub.domains' has no attribute 'metadata'
```

**位置**: [test_security_store_unit.py](packages/datahub/tests/unit/stores/test_security_store_unit.py)

**根因**: 测试使用已废弃的 `ditto_datahub.domains.metadata` 导入路径。

**建议**: 更新测试使用新的导入路径 `from ditto_datahub.stores.metadata import ...`。

---

### ARCH-003: 超大类文件 (Medium)

| 文件路径 | 行数 | 类名 | 问题 |
|---------|------|------|------|
| [capital.py](packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py) | 1113 | CapitalTushareAdapter | 单类超 1000 行 |
| [market_service.py](packages/datahub/src/ditto_datahub/services/market/market_service.py) | 754 | MarketService | 服务类过大 |
| [parquet_store.py](packages/datahub/src/ditto_datahub/stores/base/parquet_store.py) | 728 | ParquetStore | 通用类过大 |
| [metadata_service.py](packages/datahub/src/ditto_datahub/services/metadata/metadata_service.py) | 676 | MetadataService | 服务类过大 |
| [instrument_store.py](packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_store.py) | 622 | InstrumentStore | Store 类过大 |
| [sqlite_store.py](packages/datahub/src/ditto_datahub/stores/base/sqlite_store.py) | 622 | SQLiteStore | 通用类过大 |

**建议**: 作为长期重构计划，按优先级逐步拆分。

---

### NAM-001: Port 层技术术语混用 (Medium)

**问题描述**: Port 层使用 `DatabaseManager` 类名，包含技术术语 `Database`。

**位置**: [testing.py](apps/port/src/ditto_port/testing.py)

**建议**: 使用业务术语如 `TestingDataManager` 或 `TestDataManager`。

**其他发现**:
- `DatabaseManager` - testing.py (技术术语)
- `ORJSONResponse` - main.py (合理，FastAPI 集成)
- `ErrorResponse` - common.py (合理，API 响应)

---

### NAM-002: 泛化命名 (Low)

**问题描述**: Port 层存在多个使用 `Manager`/`Handler` 后缀的类。

**位置**: [apps/port/src](apps/port/src)
```python
class DatabaseManager: ...
class AlertManager: ...
class MetadataManager: ...
class BackfillManager: ...
class RetryManager: ...
class IngestionResultHandler: ...
```

**建议**: 审查这些类是否真正需要 `Manager`/`Handler` 后缀，或可使用更具体的业务名称。

---

### ENG-001: TYPE_CHECKING 使用 (Low)

**统计数据**: 源码中 6 处使用 `TYPE_CHECKING`。

**位置**:
- `packages/datahub/src/ditto_datahub/stores/fundamental/fundamental_ingestion.py`
- `packages/datahub/src/ditto_datahub/stores/capital/capital_ingestion.py`
- `packages/foundation/tests/integration/observability/conftest.py`

**状态**: 无空 TYPE_CHECKING 块，使用合理。

---

### ENG-002: type:ignore 使用 (Low)

**统计数据**: 源码中 31 处使用 `# type: ignore`。

**评估**: 根据 [core.md](.claude/rules/core.md) 规范，需要审查每个 ignore 是否有合理理由。

---

### ENG-003: Any 类型使用 (Medium)

**问题描述**: Quality checkers 中大量使用 `Any` 类型处理配置规则。

**位置**: [business.py](packages/core/src/ditto_core/quality/checkers/business.py), [technical.py](packages/core/src/ditto_core/quality/checkers/technical.py)

```python
rules: list[dict[str, Any]]
context: dict[str, Any] | None = None
```

**影响**: 配置规则使用 YAML 解析后进入系统，Any 类型降低了类型安全性。

**建议**: 考虑使用 `TypedDict` 定义规则类型结构。

---

### ARCH-004: domains 别名废弃 (Medium)

**问题描述**: `ditto_datahub.domains` 模块已标记为废弃，但测试中仍使用旧路径。

**位置**: [test_security_store_unit.py](packages/datahub/tests/unit/stores/test_security_store_unit.py)

**建议**: 全面迁移到新的导入路径 `ditto_datahub.stores.*`。

---

## 架构健康度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **分层清晰度** | 85/100 | 1 处 Port → Runtime 违规 |
| **模块内聚性** | 70/100 | 多个超大类文件 |
| **依赖方向** | 95/100 | 整体依赖关系健康 |
| **代码质量** | 90/100 | lint/type 全部通过 |
| **类型安全** | 85/100 | Any 类型在配置处理中使用 |
| **测试覆盖** | 85/100 | 82.45% 覆盖率, 1 个失败测试 |
| **命名一致性** | 80/100 | 存在技术术语泄漏 |
| **总分** | **86/100** | **良好** |

---

## 与上次审计对比 (2026-02-07 vs 2026-02-09)

| 指标 | 2026-02-07 | 2026-02-09 | 变化 |
|------|-----------|-----------|------|
| **总分** | 90/100 | 86/100 | -4 |
| **分层清晰度** | 90/100 | 85/100 | -5 (新增 1 处违规) |
| **模块内聚性** | 70/100 | 70/100 | 0 (持续问题) |
| **测试覆盖** | N/A | 85/100 | 新指标 |

**变化说明**:
- 发现 Port 层新增 1 处 Runtime 导入违规 (`QualityService`)
- 测试覆盖率首次纳入评估，达到 82.45%

---

## 修复计划 (按优先级)

### P0 - 立即修复 (本周)

1. **TEST-001**: 修复单元测试失败
   ```bash
   # 更新导入路径
   # from ditto_datahub.domains.metadata.instrument.instrument_store.logger
   # 改为
   # from ditto_datahub.stores.metadata.instrument.instrument_store.logger
   ```

2. **ARCH-002**: 修复 Port 层 Runtime 导入违规
   - 选项 A: 将 `QuarantineStore` 使用移至 registry
   - 选项 B: 通过 DataHub Service 访问

### P1 - 短期改进 (本月)

1. **ARCH-003**: 开始拆分超大类文件
   - 优先: `CapitalTushareAdapter` (1113行)
   - 按数据类型拆分为多个 Adapter

2. **ENG-003**: 改进 Quality checkers 类型安全
   - 使用 TypedDict 定义规则类型
   - 减少 Any 类型使用

### P2 - 长期规划 (季度)

1. **NAM-001**: 统一 Port 层命名规范
   - 建立命名术语表
   - 审查 `Manager`/`Handler` 后缀使用

2. **ARCH-004**: 完成废弃的 domains 别名迁移
   - 更新所有测试代码
   - 移除 `domains` 模块

---

## 验证命令

### 架构约束检查

```bash
# 检查 Port 层 Store/Source/Runtime 导入
grep -r "from ditto_datahub.stores" apps/port/src --include="*.py" | grep -v "registry"
grep -r "from ditto_datahub.sources" apps/port/src --include="*.py" | grep -v "registry"
grep -r "from ditto_datahub.runtime" apps/port/src --include="*.py" | grep -v "registry"

# 检查超大文件
find packages/datahub/src -name "*.py" -type f -exec sh -c 'lines=$(wc -l < "$1"); if [ "$lines" -gt 600 ]; then echo "$lines $1"; fi' _ {} \;
```

### 代码质量检查

```bash
# Lint
pixi run -e dev lint

# 类型检查
pixi run -e dev type

# 单元测试
pixi run -e dev test --unit
```

### LSP 语义分析

```bash
# 分析类结构
pixi run -e dev python .claude/scripts/lsp_pyright.py symbols <file>

# 查找引用
pixi run -e dev python .claude/scripts/lsp_pyright.py refs <file> <line> <col>
```

---

## 结论

Ditto 项目整体架构健康，v5 分层架构基本落地：

**优势**:
- ✅ Lint/Type 检查 100% 通过
- ✅ 测试覆盖率 82.45%，达到目标
- ✅ Foundation 层零依赖，设计优秀
- ✅ Core → DataHub 依赖关系正确

**需要改进**:
- ⚠️ 1 处 Port → Runtime 违规需修复
- ⚠️ 多个超大类文件 (600-1100行) 需要拆分
- ⚠️ 1 个单元测试失败需修复
- ⚠️ Quality checkers 类型安全可改进

**架构健康度: 86/100** (良好)

建议按 P0 → P1 → P2 优先级逐步处理发现的问题。
