# 多域标识符层统一改造计划

> **状态**: ✅ 全部完成
> **创建**: 2026-02-23
> **更新**: 2026-02-23
> **关联**: [标识符层重构实施计划](2026-02-20-identifier-layer-impl-plan.md)

---

## 当前进度

### Part 1: Exchange 层统一

| Task | 状态 | 完成时间 | 说明 |
|------|------|---------|------|
| 1.1 Exchange 枚举定义 | ✅ 已完成 | 2026-02-23 | 移除转换函数，只保留纯净枚举 |
| 1.2 Protocol + 工厂 | ✅ 已完成 | 2026-02-23 | ExchangeTransformer Protocol + ExchangeTransformers 工厂 |
| 1.3 TushareExchangeTransformer | ✅ 已完成 | 2026-02-23 | 16 个单元测试通过 |
| 1.4 TdxExchangeTransformer | ✅ 已完成 | 2026-02-23 | 16 个单元测试通过 |
| 1.5 DI 注册 | ✅ 已完成 | 2026-02-23 | SourcesProvider 添加 3 个 @provide 方法 |
| 1.6 MetadataService 重构 | ✅ 已完成 | 2026-02-23 | 通过 DI 注入 ExchangeTransformers |
| 1.7 清理旧代码 | ✅ 已完成 | 2026-02-23 | 移除 source_ticker_to_standard_ticker 引用 |

### Part 2: 多域改造

| Task | 状态 | 完成时间 | 说明 |
|------|------|---------|------|
| 2.1 ETF 域 | ✅ 已完成 | 2026-02-23 | 双模式查询支持 + Coordinator 集成 |
| 2.2 Index 域 | ✅ 已完成 | 2026-02-23 | 双模式查询支持 + Coordinator 集成 |
| 2.3 Fund 域 | ✅ 已完成 | 2026-02-23 | FUND_ADJ 双模式查询支持 + CLI 改造 |
| 2.4 Fundamental 域 | ✅ 已完成 | 2026-02-23 | Source 层双模式查询 + Coordinator 集成 |
| 2.5 Capital 域 | ✅ 已完成 | 2026-02-23 | Source 层双模式查询 + Coordinator 集成 |

---

## 已完成的文件变更

### 新建文件
| 文件路径 | 说明 |
|---------|------|
| `packages/datahub/src/ditto_datahub/sources/tushare/transformer.py` | TushareExchangeTransformer |
| `packages/datahub/src/ditto_datahub/sources/tdx/transformer.py` | TdxExchangeTransformer |
| `packages/datahub/tests/unit/models/test_exchange_unit.py` | Exchange 枚举测试 |
| `packages/datahub/tests/unit/sources/test_exchange_transformers_unit.py` | Protocol + 工厂测试 |
| `packages/datahub/tests/unit/sources/tushare/test_exchange_transformer_unit.py` | Tushare transformer 测试 |
| `packages/datahub/tests/unit/sources/tdx/test_transformer_unit.py` | TDX transformer 测试 |
| `apps/port/tests/registry/test_sources_provider_unit.py` | DI 注册测试 |

### 修改文件
| 文件路径 | 变更内容 |
|---------|---------|
| `packages/datahub/src/ditto_datahub/models/exchange.py` | 移除转换函数，只保留 Exchange 枚举 |
| `packages/datahub/src/ditto_datahub/models/__init__.py` | 更新导出 |
| `packages/datahub/src/ditto_datahub/sources/base.py` | 添加 Protocol + 工厂类 |
| `packages/datahub/src/ditto_datahub/sources/__init__.py` | 更新导出 |
| `packages/datahub/src/ditto_datahub/sources/tushare/__init__.py` | 添加 transformer 导出 |
| `packages/datahub/src/ditto_datahub/sources/tdx/__init__.py` | 添加 transformer 导出 |
| `apps/port/src/ditto_port/registry/datahub/sources.py` | 添加 DI 注册 |
| `packages/datahub/src/ditto_datahub/services/metadata_service.py` | 注入 ExchangeTransformers，移除映射 |
| `apps/port/src/ditto_port/registry/datahub/metadata.py` | 更新 DI 注册传递 transformer |
| `apps/port/src/ditto_port/registry/contexts/bundle.py` | 添加 exchange_transformers 到 IngestionBundle |
| `apps/port/src/ditto_port/registry/contexts/ingestion.py` | 提供 exchange_transformers |
| `apps/port/src/ditto_port/jobs/flows/backfill.py` | 使用 transformer 替换旧函数 |
| `packages/datahub/tests/unit/services/test_metadata_service_resolve.py` | 更新测试添加 transformer |

---

## 背景

标识符层重构（Phase 1）已完成 Stock 域改造，现需：
1. 统一 Exchange 层设计（枚举 + Source 抽象转换）
2. 扩展到 ETF/Index/Fund/Fundamental/Capital 等域

---

## Part 1: Exchange 层统一设计

### 现状问题

| 位置 | 内容 | 问题 |
|------|------|------|
| `models/exchange.py` | 转换函数 | tushare 特定逻辑放在 models 层 |
| `metadata_service.py` | `_DITTO_TO_SOURCE_EXCHANGE` | 映射重复定义 |
| Source Adapters | 无统一接口 | 各自处理 exchange |

### 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                     models/exchange.py                       │
│  Exchange 枚举 (XSHE, XSHG, XBSE) - 项目内统一标准           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   sources/base.py                            │
│  ExchangeTransformer Protocol:                              │
│    - to_standard(source_ticker) → standard_ticker           │
│    - from_standard(standard_ticker) → source_ticker         │
│  ExchangeTransformers 工厂（DI 注入）:                       │
│    - get(name) → ExchangeTransformer                        │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ TushareTransformer │ │   TdxTransformer   │ │  OtherTransformer  │
│  SZ → XSHE      │ │   (已有需求)    │ │   (未来)        │
│  SH → XSHG      │ │                 │ │                 │
│  BJ → XBSE      │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Task 1.1: Exchange 枚举定义

**文件**: `packages/datahub/src/ditto_datahub/models/exchange.py`

- 移除转换函数和映射
- 只保留纯净的 `Exchange` 枚举

### Task 1.2: ExchangeTransformer Protocol + ExchangeTransformers 工厂

**文件**: `packages/datahub/src/ditto_datahub/sources/base.py`

- `ExchangeTransformer` Protocol
- `ExchangeTransformers` 工厂类（通过 DI 注入）

### Task 1.3: TushareExchangeTransformer

**文件**: `packages/datahub/src/ditto_datahub/sources/tushare/exchange_transformer.py`

- 实现 `ExchangeTransformer` 协议
- 包含 tushare 特定的映射逻辑

### Task 1.4: TdxExchangeTransformer

**文件**: `packages/datahub/src/ditto_datahub/sources/tdx/exchange_transformer.py`

- 实现 `ExchangeTransformer` 协议
- 包含 tdx 特定的映射逻辑

### Task 1.5: DI 注册

**文件**: `apps/port/src/ditto_port/registry/datahub/sources.py`

- 添加 transformer 的 `@provide` 方法
- 创建 `ExchangeTransformers` 实例

### Task 1.6: MetadataService 重构

**文件**: `packages/datahub/src/ditto_datahub/services/metadata_service.py`

- 移除 `_DITTO_TO_SOURCE_EXCHANGE` 映射
- 通过 DI 获取 `ExchangeTransformers`
- `resolve_source_ticker()` 调用 transformer

### Task 1.7: 清理旧代码

- 更新所有引用 `source_ticker_to_standard_ticker` 的地方
- 更新 `sources/__init__.py` 导出

---

## Part 2: 多域改造计划

### 改造模式（以 Stock 为模板）

每个域的改造遵循相同模式：

```
1. Dataset.asset_class 扩展
2. CLI 命令增加 --ticker/--instrument-id 参数
3. Coordinator 增加按标的摄取方法
4. Source Adapter 支持按标的查询
```

### Task 2.1: ETF 域

| 组件 | 改造内容 |
|------|---------|
| Dataset | `ETF_DAILY.asset_class` → `AssetClass.ETF` |
| CLI | `ingest market etf --ticker 510300` |
| Coordinator | `ingest_by_instrument("etf_daily", params)` |
| Source | `fetch_etf_daily(ticker=, start=, end=)` |

**数据集**: `ETF_DAILY`, `ETF_BASIC`

### Task 2.2: Index 域

| 组件 | 改造内容 |
|------|---------|
| Dataset | `INDEX_DAILY.asset_class` → `AssetClass.INDEX` |
| CLI | `ingest market index --ticker 000001` |
| Coordinator | 复用 `ingest_by_instrument` |
| Source | `fetch_index_daily(ticker=, start=, end=)` |

**数据集**: `INDEX_DAILY`, `INDEX_BASIC`

### Task 2.3: Fund 域

| 组件 | 改造内容 |
|------|---------|
| Dataset | `FUND_ADJ.asset_class` → `AssetClass.FUND` |
| CLI | `ingest market fund-adj --ticker` |

**数据集**: `FUND_ADJ`

### Task 2.4: Fundamental 域

| 组件 | 改造内容 |
|------|---------|
| Dataset | `BALANCE_SHEET.asset_class` → `AssetClass.STOCK` |
| CLI | `ingest fundamental balance-sheet --ticker 000001` |

**数据集**:
- `BALANCE_SHEET`
- `INCOME_STATEMENT`
- `CASH_FLOW`
- `DIVIDEND`
- `VALUATION_METRICS`

### Task 2.5: Capital 域

| 组件 | 改造内容 |
|------|---------|
| Dataset | `MARGIN_TRADING.asset_class` → `AssetClass.STOCK` |
| CLI | `ingest capital margin --ticker 000001` |

**数据集**:
- `MARGIN_TRADING`
- `PLEDGE_RATIO`

---

## 实施顺序

```
Phase 1: Exchange 层统一 (Task 1.1 - 1.5)
         ↓
Phase 2: ETF 域 (Task 2.1)
         ↓
Phase 3: Index 域 (Task 2.2)
         ↓
Phase 4: Fundamental 域 (Task 2.4)
         ↓
Phase 5: Capital 域 (Task 2.5)
         ↓
Phase 6: Fund 域 (Task 2.3)
```

---

## 验收标准

| 检查项 | 标准 |
|--------|------|
| 类型检查 | 0 errors |
| 架构检查 | 6 kept, 0 broken |
| 单元测试 | 覆盖新增代码 |
| 集成测试 | 每域至少 1 个端到端测试 |

---

## CLI 用法示例

```bash
# Exchange 层使用
from ditto_datahub.models import Exchange
from ditto_datahub.sources import get_transformer

transformer = get_transformer("tushare")
standard = transformer.to_standard("000001.SZ")  # "000001.XSHE"

# ETF 按标的摄取
pixi run ingest market etf --ticker 510300 --start 2024-01-01 --end 2024-06-30

# Index 按标的摄取
pixi run ingest market index --ticker 000001 --start 2024-01-01 --end 2024-06-30

# Fundamental 按标的摄取
pixi run ingest fundamental balance-sheet --ticker 000001 --start 2024-01-01

# Capital 按标的摄取
pixi run ingest capital margin --ticker 000001 --start 2024-01-01
```
