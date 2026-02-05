# DataHub 三域协调重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 引入 SourceSchema 层作为数据源接入标准协议，协调重构 Metadata、Market、Capital 三域

**架构:** 3 层架构（Source → SourceSchema → StoreSchema → Store），支持多数据源接入

**技术栈:** Python 3.12+, Polars, Pydantic, Pyright Strict

**前置依赖:** Source 层改造（引入 SourceSchema），Metadata 域（SecurityStore.sid 解析）

---

## 重构范围

| 域 | 状态 | 工作内容 | 优先级 |
|----|------|---------|--------|
| **Metadata** | ⚠️ 需重构 | 引入 SourceSchema，统一基类使用，补充缺失 Adapter | **P0** |
| **Market** | ✅ 无需重构 | 已完全符合目标架构（测试覆盖率 93.48%+） | - |
| **Capital** | ❌ 未实现 | 按 SourceSchema 模式实现全新域 | **P0** |

**重构原则**：
- ✅ **向后兼容**：不破坏现有功能，渐进式迁移
- ✅ **增量演进**：先引入 SourceSchema，再逐个 Adapter 迁移
- ✅ **协调一致**：三域使用统一的 SourceSchema 标准

---

## 目录结构

### sources/ 目录结构（独立组织）

```
packages/datahub/src/ditto_datahub/sources/
├── source_schemas.py              # SourceSchema 定义（新增）
├── base.py                         # DataSource 基类
└── tushare/
    ├── tushare_source.py          # 主入口（组合模式）
    ├── adapters/
    │   ├── base.py                # BaseTushareAdapter（共享客户端）
    │   ├── calendar.py            # 交易日历（Metadata 域）
    │   ├── stock.py               # 股票数据（Market + Metadata 域）
    │   ├── etf.py                 # ETF 数据（Market 域）
    │   ├── industry.py            # 行业分类（Metadata 域，新增）
    │   └── capital.py             # Capital 域 Adapter（新增）
    └── processors/
        ├── transformer.py         # 现有 ColumnMapping（扩展 validate()）
        ├── industry_transformer.py # Industry 域转换器（新增）
        └── capital_transformer.py # Capital 域转换器（新增）
```

**说明**：
- Adapters 按功能/数据类型组织，不按主域组织
- 一个 Adapter 可能跨域（如 StockTushareAdapter 覆盖 Market + Metadata）
- 新增 Industry 和 Capital Adapters

### domains/ 目录结构（三域并存）

```
packages/datahub/src/ditto_datahub/domains/
├── metadata/                      # Metadata 域（已存在，需重构）
│   ├── calendar/
│   ├── security/
│   ├── identity/
│   ├── industry/
│   └── metadata_query_service.py
├── market/                        # Market 域（已存在，无需重构）
│   ├── stock/
│   ├── etf/
│   ├── index/
│   ├── base/
│   └── market_query_service.py
└── capital/                       # Capital 域（新增）
    ├── flow/
    │   ├── __init__.py
    │   ├── market_flow_store.py   # 市场资金流
    │   ├── industry_flow_store.py # 行业资金流
    │   └── stock_flow_store.py    # 个股资金流
    ├── margin/
    │   ├── __init__.py
    │   ├── margin_detail_store.py # 融资融券明细
    │   └── margin_summary_store.py# 融资融券汇总
    ├── top_board/
    │   ├── __init__.py
    │   └── top_board_store.py     # 龙虎榜
    ├── limit_board/
    │   ├── __init__.py
    │   └── limit_board_store.py   # 涨跌停
    ├── chip/
    │   ├── __init__.py
    │   └── chip_distribution_store.py # 筹码分布
    └── capital_query_service.py   # Capital 域统一入口
```

**说明**：
- Metadata 和 Market 域已存在
- Capital 域新增，采用扁平设计（与 Market 一致）

---

## 数据类型分类（SourceSchema）

SourceSchema 按数据类型分类，不按 Domain 分类。完整分类如下：

### Market 数据类型（已实现，需形式化）

| 数据类型 | SourceSchema | 覆盖范围 | Tushare API | 状态 |
|---------|-------------|---------|-------------|------|
| BAR_DAILY | BarSourceSchema | stock/etf/index | daily | ✅ 已实现 |
| ADJ_FACTOR | AdjFactorSourceSchema | stock/etf 复权因子 | adj_factor / fund_adj | ✅ 已实现 |
| STOCK_STATUS | StockStatusSourceSchema | 股票状态 | suspend/st/list_status | ✅ 已实现 |

### Metadata 数据类型（需引入）

| 数据类型 | SourceSchema | 覆盖范围 | Tushare API | 状态 |
|---------|-------------|---------|-------------|------|
| CALENDAR | CalendarSourceSchema | 交易日历 | trade_cal | ✅ 已实现 |
| SECURITY_BASIC | SecurityBasicSourceSchema | 证券基础信息 | stock_basic | ✅ 已实现 |
| INDUSTRY_BASIC | IndustryBasicSourceSchema | 行业主数据 | index_classify (申万) | ❌ 缺失 |
| INDUSTRY_MAPPING | IndustryMappingSourceSchema | 股票-行业映射 | index_member (申万) | ❌ 缺失 |

### Capital 数据类型（待实现）

| 数据类型 | SourceSchema | 覆盖范围 | Tushare API | 状态 |
|---------|-------------|---------|-------------|------|
| FLOW_MARKET | FlowMarketSourceSchema | 市场资金流 | moneyflow_hsgt | ❌ 待实现 |
| FLOW_STOCK | FlowStockSourceSchema | 个股资金流 | moneyflow | ❌ 待实现 |
| MARGIN_DETAIL | MarginDetailSourceSchema | 融资融券明细 | margin_detail | ❌ 待实现 |
| MARGIN_SUMMARY | MarginSummarySourceSchema | 市场汇总 | mtsk_sec | ❌ 待实现 |
| TOP_LIST | TopListSourceSchema | 龙虎榜 | top_list | ❌ 待实现 |
| LIMIT_BOARD | LimitBoardSourceSchema | 涨跌停 | limit_list_d | ❌ 待实现 |
| CHIP_DISTRIBUTION | ChipDistributionSourceSchema | 筹码分布 | cyq_chips | ❌ 待实现 |

**设计原则：**
- ✅ 多源映射成本最小化：不同数据源实现相同 SourceSchema
- ✅ 复用性最大化：SourceSchema 可被多个 Domain 共享
- ✅ 与现有架构对齐：复用 ColumnMapping、Transformer 模式
- ✅ PIT 支持：SecurityBasic、IndustryMapping 需支持时点查询

---

## 实施步骤

### 阶段 0：SourceSchema 基础设施（三域共享）

| 任务 | 文件 | 说明 |
|------|------|------|
| 定义 SourceSchema 基类 | `sources/source_schemas.py` | 新增：SourceSchema + Schema 验证 |
| 扩展 TushareDataTransformer | `sources/tushare/processors/transformer.py` | 添加 validate() 方法 |
| 更新 BaseTushareAdapter | `sources/tushare/adapters/base.py` | 添加可选 Schema 验证 |
| 单元测试 | `tests/unit/sources/test_source_schemas.py` | 测试 Schema 定义和验证 |

### 阶段 1：Metadata 域重构（优先级 P0）

#### 1.1 引入 SourceSchema（形式化现有实现）

| 任务 | 文件 | 说明 |
|------|------|------|
| 定义 CalendarSourceSchema | `sources/source_schemas.py` | 形式化现有实现 |
| 定义 SecurityBasicSourceSchema | `sources/source_schemas.py` | 支持 PIT 查询 |
| 更新 CalendarTushareAdapter | `sources/tushare/adapters/calendar.py` | 添加 SourceSchema |
| 更新 StockTushareAdapter | `sources/tushare/adapters/stock.py` | 为 fetch_stock_basic() 添加 SourceSchema |
| 单元测试 | `tests/unit/sources/tushare/test_metadata_adapters.py` | 验证 Schema 兼容性 |

#### 1.2 补充缺失的 Industry Adapter

| 任务 | 文件 | 说明 |
|------|------|------|
| 定义 IndustryBasicSourceSchema | `sources/source_schemas.py` | 申万行业主数据 |
| 定义 IndustryMappingSourceSchema | `sources/source_schemas.py` | 股票-行业映射（PIT） |
| 实现 IndustryTushareAdapter | `sources/tushare/adapters/industry.py` | 新增 Adapter |
| 实现 IndustryTransformer | `sources/tushare/processors/industry_transformer.py` | 定义 ColumnMapping |
| 扩展 TushareSource | `sources/tushare/tushare_source.py` | 添加 Industry 域方法 |
| 单元测试 | `tests/unit/sources/tushare/test_industry_adapter.py` | 测试 Industry 数据获取 |

#### 1.3 统一 Metadata Store 基类

| 任务 | 文件 | 说明 |
|------|------|------|
| 重构 CalendarStore | `domains/metadata/calendar/calendar_store.py` | 考虑继承 SQLiteStore |
| 重构 SecurityStore | `domains/metadata/security/security_store.py` | 保持功能，优化结构 |
| 单元测试 | `tests/unit/domains/metadata/` | 验证重构后兼容性 |

### 阶段 2：Capital 域实现（优先级 P0）

#### 2.1 Source 层实现

| 任务 | 文件 | 说明 |
|------|------|------|
| 定义 Capital SourceSchemas | `sources/source_schemas.py` | 7 个数据类型 |
| 实现 CapitalTushareAdapter | `sources/tushare/adapters/capital.py` | 新增 Adapter（按子域拆分方法） |
| 实现 CapitalTransformer | `sources/tushare/processors/capital_transformer.py` | 定义 ColumnMapping |
| 扩展 TushareSource | `sources/tushare/tushare_source.py` | 添加 Capital 域方法 |
| 单元测试 | `tests/unit/sources/tushare/test_capital_adapter.py` | 测试数据获取和转换 |

#### 2.2 Store 层实现

| 任务 | 文件 | 说明 |
|------|------|------|
| 定义 Parquet Schema | `meta/schemas.py` | 扩展 FLOW_STOCK_SCHEMA 等 |
| 实现 StockFlowStore | `domains/capital/flow/stock_flow_store.py` | 继承 ParquetStoreBase |
| 实现 MarketFlowStore | `domains/capital/flow/market_flow_store.py` | 无 sid（市场级数据）|
| 实现 IndustryFlowStore | `domains/capital/flow/industry_flow_store.py` | 行业资金流 |
| 实现 MarginDetailStore | `domains/capital/margin/margin_detail_store.py` | 继承 ParquetStoreBase |
| 实现 MarginSummaryStore | `domains/capital/margin/margin_summary_store.py` | 市场汇总数据 |
| 实现 TopBoardStore | `domains/capital/top_board/top_board_store.py` | 龙虎榜数据 |
| 实现 LimitBoardStore | `domains/capital/limit_board/limit_board_store.py` | 涨跌停数据 |
| 实现 ChipDistributionStore | `domains/capital/chip/chip_distribution_store.py` | 筹码分布 |
| 单元测试 | `tests/unit/domains/capital/` | 测试 Store 读写 |

### 阶段 3：Ingestion 层扩展（Port 层）

| 任务 | 文件 | 说明 |
|------|------|------|
| 扩展 Dataset 枚举 | `apps/port/src/ditto_port/models/config.py` | 添加 INDUSTRY_BASIC、FLOW_STOCK 等 |
| 扩展 DATASET_REGISTRY | `apps/port/src/ditto_port/models/config.py` | 注册 Metadata/Capital 域数据集 |
| 扩展 IngestionCoordinator | `apps/port/src/ditto_port/services/ingestion/coordinator.py` | 添加 Industry/Capital 域处理 |
| 扩展 IngestionDataWriter | `apps/port/src/ditto_port/services/ingestion/data_writer.py` | 实现 Industry/Capital 的 src_code → sid 转换 |
| 集成测试 | `tests/integration/ingestion/test_industry_capital_ingestion.py` | 端到端测试 |

### 阶段 4：QueryService 实现

| 任务 | 文件 | 说明 |
|------|------|------|
| 更新 MetadataQueryService | `domains/metadata/metadata_query_service.py` | 集成 Industry 相关查询 |
| 实现 CapitalQueryService | `domains/capital/capital_query_service.py` | 统一查询入口 |
| 注册到 DataHub | `hub.py` | 确保 Metadata、Capital 访问点正常 |
| 单元测试 | `tests/unit/domains/capital/test_capital_query_service.py` | 测试查询逻辑 |

### 阶段 5：Market 域验证（无需重构，仅验证）

| 任务 | 文件 | 说明 |
|------|------|------|
| 验证 Market 域兼容性 | `domains/market/` | 确保重构不影响 Market 域 |
| 回归测试 | `tests/unit/domains/market/` | 运行完整测试套件 |
| 性能测试 | `tests/integration/market_benchmark.py` | 确保无性能退化 |

---

## 关键技术决策

### 1. SourceSchema 定义策略

**决策**：按数据类型分类，不按 Domain 分类

**示例**：
```python
# ✅ 正确：按数据类型
class FlowStockSourceSchema: ...
# AkShare 也实现 FlowStockSourceSchema
class AkShareAdapter:
    def fetch_flow_stock() -> FlowStockSourceSchema: ...
```

### 2. Metadata 域重构策略

**决策**：渐进式重构，向后兼容

| 改造项 | 策略 | 风险 |
|--------|------|------|
| SourceSchema 引入 | 形式化现有实现，添加可选验证 | 低（现有代码不变） |
| Industry Adapter | 新增 Adapter，补充缺失功能 | 低（不影响现有代码） |
| Store 基类统一 | 可选重构，优化结构 | 中（需验证兼容性） |

**PIT 支持**：SecurityBasicSourceSchema、IndustryMappingSourceSchema 需支持时点查询

```python
@dataclass(frozen=True)
class SourceSchema:
    dataset: str
    key_columns: list[str]
    schema: dict[str, type[pl.DataType]]
    pit_columns: list[str] = field(default_factory=list)  # PIT 支持
```

### 3. Market 域保持不变

**决策**：Market 域无需重构，仅验证兼容性

**理由**：
- ✅ 架构设计优秀（测试覆盖率 93.48%+）
- ✅ 已完全符合目标架构
- ✅ 继承模式清晰（MarketBarsStoreBase → ParquetStoreBase）
- ⚠️ 重构风险 > 收益

### 4. src_code → sid 转换位置

**决策**：Port 层 IngestionDataWriter 统一处理

**三域统一**：
- Metadata: `stock_basic` (src_code) → SecurityStore (sid)
- Market: `daily` (src_code) → StockBarsStore (sid)
- Capital: `moneyflow` (src_code) → StockFlowStore (sid)

### 5. 多数据源支持

**决策**：先实现 Tushare，预留扩展点

**数据源优先级**：
1. Tushare（主力数据源）
2. AkShare（补充数据源，如行业分类）
3. 米筐 RQData（机构数据源）
4. 通达信 TDX（本地数据源）
5. 迅投 QMT（实时数据流）

**SourceSchema 作为集成协议**：
```python
# 多数据源实现相同 SourceSchema
TushareAdapter.fetch_flow_stock() -> FlowStockSourceSchema
AkShareAdapter.fetch_flow_stock() -> FlowStockSourceSchema
```

### 6. 测试策略

**决策**：三域独立测试 + 集成验证

| 测试类型 | 覆盖范围 | 目标覆盖率 |
|---------|---------|-----------|
| 单元测试 | SourceSchema、Adapters、Stores | ≥ 80% |
| 集成测试 | Ingestion 端到端流程 | 关键路径 100% |
| 回归测试 | Market 域现有功能 | 确保无破坏 |
| 性能测试 | Metadata 域 PIT 查询 | 无退化 |

---

## 关键文件清单

### 新增文件

#### SourceSchema 基础设施
- `packages/datahub/src/ditto_datahub/sources/source_schemas.py`

#### Metadata 域新增
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/industry.py`
- `packages/datahub/src/ditto_datahub/sources/tushare/processors/industry_transformer.py`
- `packages/datahub/src/ditto_datahub/scripts/schema/industry_tables.sql`（补充 schema）

#### Capital 域新增
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py`
- `packages/datahub/src/ditto_datahub/sources/tushare/processors/capital_transformer.py`
- `packages/datahub/src/ditto_datahub/domains/capital/flow/market_flow_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/flow/stock_flow_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/flow/industry_flow_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/margin/margin_detail_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/margin/margin_summary_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/top_board/top_board_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/limit_board/limit_board_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/chip/chip_distribution_store.py`
- `packages/datahub/src/ditto_datahub/domains/capital/capital_query_service.py`

### 修改文件

#### Source 层
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/base.py` - 添加可选 Schema 验证
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/calendar.py` - 添加 SourceSchema
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/stock.py` - 为 fetch_stock_basic() 添加 SourceSchema
- `packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py` - 添加 Industry/Capital 域方法
- `packages/datahub/src/ditto_datahub/sources/tushare/processors/transformer.py` - 添加 validate() 方法

#### Metadata 域
- `packages/datahub/src/ditto_datahub/domains/metadata/calendar/calendar_store.py` - 可选：考虑继承 SQLiteStore
- `packages/datahub/src/ditto_datahub/domains/metadata/security/security_store.py` - 可选：优化结构
- `packages/datahub/src/ditto_datahub/domains/metadata/metadata_query_service.py` - 集成 Industry 相关查询

#### Capital 域
- `packages/datahub/src/ditto_datahub/meta/schemas.py` - 扩展 Capital 域 Schema

#### Ingestion 层（Port 应用）
- `apps/port/src/ditto_port/models/config.py` - 扩展 Dataset 枚举和注册表
- `apps/port/src/ditto_port/services/ingestion/coordinator.py` - 扩展 Industry/Capital 域处理
- `apps/port/src/ditto_port/services/ingestion/data_writer.py` - 扩展 Industry/Capital 的 src_code → sid 转换

### 测试文件

#### 单元测试
- `packages/datahub/tests/unit/sources/test_source_schemas.py`
- `packages/datahub/tests/unit/sources/tushare/test_metadata_adapters.py`
- `packages/datahub/tests/unit/sources/tushare/test_industry_adapter.py`
- `packages/datahub/tests/unit/sources/tushare/test_capital_adapter.py`
- `packages/datahub/tests/unit/domains/metadata/` - 更新现有测试
- `packages/datahub/tests/unit/domains/capital/` - 新增 Capital 域测试

#### 集成测试
- `packages/datahub/tests/integration/ingestion/test_industry_capital_ingestion.py`

---

## 验收标准

### SourceSchema 基础设施
- [ ] SourceSchema 基类定义完整，支持 Schema 验证和 PIT
- [ ] TushareDataTransformer.validate() 方法实现
- [ ] BaseTushareAdapter 可选 Schema 验证（通过配置开关）

### Metadata 域
- [ ] CalendarSourceSchema、SecurityBasicSourceSchema 定义
- [ ] IndustryBasicSourceSchema、IndustryMappingSourceSchema 定义
- [ ] IndustryTushareAdapter 实现完整（申万行业分类）
- [ ] Industry 相关数据在 MetadataQueryService 中可查询
- [ ] CalendarStore、SecurityStore 重构后兼容性验证通过
- [ ] 测试覆盖率 ≥ 80%

### Capital 域
- [ ] 7 个 SourceSchema 定义完整（FLOW_MARKET、FLOW_STOCK、MARGIN_DETAIL 等）
- [ ] CapitalTushareAdapter 实现完整，通过单元测试
- [ ] Capital 域所有 Store 实现完整（Flow、Margin、TopBoard、LimitBoard、Chip）
- [ ] Port 层摄入流程集成测试通过
- [ ] CapitalQueryService 提供统一查询接口
- [ ] 测试覆盖率 ≥ 80%

### Market 域
- [ ] 现有测试全部通过（无回归）
- [ ] 性能测试通过（无退化）
- [ ] 测试覆盖率保持 93%+

### 代码质量
- [ ] basedpyright 类型检查通过（strict 模式）
- [ ] ruff lint 检查通过
- [ ] pre-commit hooks 通过
- [ ] 所有测试通过（pytest）

---

## 预计时间

**总计: 约 5 周**

| 阶段 | 工作内容 | 预计时间 | 依赖 |
|------|---------|---------|------|
| **阶段 0** | SourceSchema 基础设施 | **3 天** | 无 |
| **阶段 1** | Metadata 域重构 | **1 周** | 阶段 0 |
| **阶段 2** | Capital 域实现 | **1.5 周** | 阶段 0 |
| **阶段 3** | Ingestion 层扩展 | **1 周** | 阶段 1, 2 |
| **阶段 4** | QueryService 实现 | **3 天** | 阶段 3 |
| **阶段 5** | Market 域验证 | **2 天** | 阶段 0-4 |

### 风险与缓冲

| 风险项 | 影响 | 缓解措施 |
|--------|------|---------|
| Metadata Store 基类重构引入兼容性问题 | +3 天 | 可选重构，通过特性开关控制 |
| Industry Adapter 数据格式不兼容 | +2 天 | 先验证 Tushare API，再实现 |
| Capital 域 PIT 需求超出预期 | +3 天 | 先实现简单版本，PIT 后续迭代 |

**建议缓冲时间：+1 周**

**总时间范围：5-6 周**

---
