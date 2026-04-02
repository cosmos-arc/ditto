# 领域术语重构设计

## 概述

统一项目内证券标识相关术语，消除 `symbol`/`ticker`/`ts_code` 等术语的混用问题，建立清晰的术语体系。

## 目标术语体系

| 术语 | 含义 | 示例 | 存储位置 | 使用场景 |
|------|------|------|----------|----------|
| `instrument_id` | 系统内部唯一标识符 | `1000001` | SQLite 主键 | 精确查找、系统间引用 |
| `ticker` | 裸代码（纯编号） | `600000` | `instrument.ticker` | 条件查询匹配 |
| `source_ticker` | 数据源原始编码 | `600000.SH` | `instrument_mapping.source_ticker` | 数据源适配层 |
| `standard_ticker` | 标准可读编码 | `600000.SSE` | 动态计算 | 展示层 |
| `ts_code` | Tushare API 字段 | `600000.SH` | 仅 API 调用 | adapter 层内部 |

## 术语关系图

```
数据源 (Tushare)              系统内部                 展示层
┌─────────────────┐         ┌─────────────────┐     ┌─────────────────┐
│ ts_code         │  ──►    │ source_ticker   │     │                 │
│ "600000.SH"     │ adapter │ "600000.SH"     │     │                 │
└─────────────────┘         └────────┬────────┘     │                 │
                                     │              │ standard_ticker │
                                     ▼              │ "600000.SSE"    │
                            ┌─────────────────┐     │ (动态计算)       │
                            │ ticker + exchange│ ──►│                 │
                            │ "600000" + "SSE"│     │                 │
                            └─────────────────┘     └─────────────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ instrument_id   │
                            │ 1000001         │
                            └─────────────────┘
```

## 标准化规则

### 交易所映射
```python
# Tushare 后缀 → 项目标准枚举
"SH"  → Exchange.SSE   # 上海证券交易所
"SZ"  → Exchange.SZSE  # 深圳证券交易所
"BJ"  → Exchange.BSE   # 北京证券交易所
```

### standard_ticker 生成
```python
def get_standard_ticker(ticker: str, exchange: str) -> str:
    """生成标准可读编码（仅展示层使用）."""
    return f"{ticker}.{exchange}"
# 例如: get_standard_ticker("600000", "SSE") → "600000.SSE"
```

## 修改范围

### 数据库层

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/scripts/schema.sql` | `instrument.symbol` → `instrument.ticker`，索引重命名 |

### Models 层

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/models/metadata.py` | `InstrumentRegistration.symbol` → `ticker` |

### Store 层

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/stores/metadata/instrument/instrument_reader.py` | `get_symbol()` → `get_ticker()`，`enrich_with_symbol()` → `enrich_with_ticker()`，`get_instrument_id_symbol_map()` → `get_instrument_id_ticker_map()` |
| `packages/data/src/ditto_data/stores/metadata/instrument/instrument_writer.py` | 写入时使用 `ticker` |

### Service 层

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/services/metadata_service.py` | `get_symbol()` → `get_ticker()` |

### Source 层

| 文件 | 修改内容 |
|------|----------|
| `packages/data/src/ditto_data/sources/tushare/processors/transformer.py` | computed_columns 中 `symbol` → `ticker` |
| `packages/data/src/ditto_data/sources/schemas/metadata_schemas.py` | 移除模糊的 `ticker` 字段，保留 `source_ticker` |
| `packages/foundation/src/ditto_foundation/db/sqlite_pool.py` | schema 验证中 `symbol` → `ticker` |

### 展示层 - 新增

| 文件 | 修改内容 |
|------|----------|
| 新增工具函数 | `get_standard_ticker(ticker, exchange) -> str` |

### 测试文件（同步修改）

- `packages/data/tests/unit/models/test_security_unit.py`
- `packages/data/tests/unit/stores/test_security_store_unit.py`
- `packages/data/tests/unit/sources/tushare/test_transformer_unit.py`
- `packages/data/tests/integration/stores/test_security_store_integration.py`
- `packages/data/tests/integration/runtime/test_sql_engine_integration.py`
- `apps/port/tests/unit/services/ingestion/quality/test_reconciliation_service_unit.py`
- 其他涉及 symbol 的测试文件

## 实施顺序

采用**自底向上**的顺序，确保每层修改后上层编译通过：

### Phase 1: 数据库层
1. `schema.sql` - 字段重命名 symbol → ticker
2. `sqlite_pool.py` - schema 验证更新

### Phase 2: Models 层
3. `metadata.py` - InstrumentRegistration.symbol → ticker

### Phase 3: Store 层
4. `instrument_reader.py` - 方法重命名
5. `instrument_writer.py` - 写入字段更新

### Phase 4: Service 层
6. `metadata_service.py` - 方法重命名

### Phase 5: Source 层
7. `transformer.py` - computed_columns 更新
8. `schemas/metadata_schemas.py` - 移除模糊 ticker 字段

### Phase 6: 展示层 - 新增
9. 新增 `get_standard_ticker()` 工具函数

### Phase 7: 测试同步
10. 更新所有测试文件的断言和 mock 数据

### Phase 8: 验证
11. `pixi run -e dev check`

## 注意事项

1. **数据库迁移**：由于 SQLite 不支持 `ALTER COLUMN`，需要创建新表迁移数据
2. **向后兼容**：此重构涉及 API 变更，需要同步更新所有调用方
3. **测试覆盖**：确保所有测试在重构后通过，覆盖率不下降

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据库迁移失败 | 高 | 备份数据库，编写迁移脚本测试 |
| 遗漏 symbol 引用 | 中 | 使用全局搜索确认所有引用已更新 |
| 测试覆盖不足 | 低 | Phase 8 完整验证 |
