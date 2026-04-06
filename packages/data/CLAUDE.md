# Data 架构规范

## 目录结构

```
ditto_data/
├── config/              # 数据层配置（数据源/存储/存储路径）
├── di/                  # DI 注册（builders/sources/quality/runtime 等 Provider）
├── errors.py            # DataError 异常层级
├── events.py            # 数据事件定义
├── helpers/             # 辅助工具（复权调整/PIT 策略与 SQL/DataFrame）
│   └── pit/             # PIT（Point-in-Time）辅助
├── ingestion/           # 摄入服务（游标/日志/冻结/晚到数据/质量记录/发布安全）
├── models/              # 数据模型（枚举/市场/元数据/宏观/衍生/摄入/存储/策略等）
├── provider.py          # DataProvider Protocol 定义
├── quality/             # 数据质量引擎
│   └── checkers/        # L1-L4 检查器（技术/业务/统计/跨源）
├── query/               # 查询服务（市场/元数据查询 + Provider 路由）
├── runtime/             # 运行时基础设施（SQL 引擎/冻结管理/ID 分配）
├── scripts/             # 工具脚本
├── services/            # 域服务（Facade 模式）
│   ├── audit/           # 审计服务
│   ├── derived/         # 衍生数据服务（物化/查询/GC/并发）
│   ├── hot_layer/       # 热数据层
│   ├── metadata/        # 元数据子服务（日历/工具/Universe）
│   └── strategy/        # 策略数据服务（目录/运行/产物/规则）
├── sources/             # 外部数据源
│   ├── fred/            # FRED 数据源（宏观/商品适配器）
│   ├── schemas/         # 数据源 Schema 定义
│   ├── tdx/             # 通达信数据源
│   └── tushare/         # Tushare 数据源（适配器/处理器/映射）
│       ├── adapters/    # 数据适配器（ETF/股票/宏观/资金等）
│       ├── processors/  # 数据处理器（列映射/合并/转换）
│       └── utils/       # 工具（HTTP/限流）
├── storage/             # 存储引擎（Reader/Writer CQRS）
│   ├── base/            # 存储基类（Parquet/SQLite/分区策略）
│   ├── capital/         # 资本数据（估值/融资融券/质押/指数成分）
│   ├── factors/         # 因子存储
│   ├── features/        # 特征存储（技术指标）
│   ├── fundamental/     # 基本面存储（财报/预测/公司行为）
│   ├── macro/           # 宏观数据存储
│   ├── market/          # 市场数据存储（ETF/股票/指数/商品/外汇）
│   ├── metadata/        # 元数据存储（日历/工具/行业/Universe/策略）
│   ├── runtime/         # 运行时存储（摄入游标/日志/质量/衍生/研究/发布安全）
│   └── schemas/         # 存储层 Schema
├── stores/              # 高层 Store（基于 storage 构建）
│   ├── base/            # Store 基类
│   ├── capital/         # 资本 Store
│   ├── fundamental/     # 基本面 Store
│   ├── macro/           # 宏观 Store
│   ├── market/          # 市场 Store
│   ├── metadata/        # 元数据 Store
│   └── runtime/         # 运行时 Store
└── utils/               # 工具函数（时区等）
```

## 分层职责

| 层级 | 职责 | 禁止 | 必须 |
|------|------|------|------|
| storage (Reader/Writer) | 数据读写操作（CQRS 分离） | 包含业务逻辑 | 类型注解 |
| stores | 高层 Store 封装 | 跳过 storage 层 | 基于 storage Reader/Writer |
| services | 域服务（Facade 模式） | 直接访问文件系统 | 通过 stores/storage |
| sources | 外部数据源接入 | 包含业务逻辑 | 重试、限流、监控埋点 |
| query | 查询服务与 Provider 路由 | 包含写入逻辑 | 类型注解 |
| ingestion | 数据摄入编排 | 绕过质量检查 | 游标管理 |
| quality | 数据质量引擎 | 包含业务逻辑 | L1-L4 检查 |
| runtime | 运行时基础设施 | 包含业务逻辑 | SQL/PIT/Freeze |
| models | 数据模型定义 | 包含行为方法 | 纯数据类 |
| di | DI 注册 | 包含业务逻辑 | Provider 注册 |

## CQRS 模式（Command Query Responsibility Segregation）

`storage/` 层采用 CQRS 模式，将读写操作分离：

### Reader 组件（`storage/**/reader.py`）
- **职责**：数据查询（read/count/get_*）
- **特点**：无副作用，可并发执行
- **方法**：`read()`, `count()`, `get_*()`

### Writer 组件（`storage/**/writer.py`）
- **职责**：数据写入/删除（write/delete）
- **特点**：有副作用，需要并发控制
- **方法**：`write()`, `delete()`

### 命名约定
- 查询类：`*_reader.py`（如 `instrument_reader.py`）
- 写入类：`*_writer.py`（如 `instrument_writer.py`）
- 服务类：`*_service.py`（如 `metadata_service.py`）
- 存储基类：`storage/base/`（Parquet/SQLite/分区策略）

## 层级访问规则（2026-02-10 更新）

### Interfaces 层访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 | 说明 |
|---------|--------|--------|------|
| **通过 Domain Service** | `MetadataService`, `MarketService` 等 | - | **推荐方式**，通过 DI 容器注入 |
| **通过 Query Provider** | `QueryProvider` | - | 统一查询路由 |
| **直接导入** | `from ditto_data.sources.*` | `from ditto_data.storage.*` | Sources 可直接访问，Storage 禁止 |
| **Reader/Writer** | - | 直接实例化 | **禁止**直接访问 storage 层 |

### 正确示例

```python
# ✅ 推荐：通过 DI 容器注入 Domain Service
from dishka import Container
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.market_service import MarketService

container = Container()
metadata_service: MetadataService = container.get(MetadataService)
market_service: MarketService = container.get(MarketService)

# 使用 Service
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")
bars = market_service.query(query)

# ✅ 推荐：通过 Service 获取数据
provider = sources.get("tushare")
df = provider.fetch_stock_daily("2024-01-02")

# ❌ 禁止：直接访问 Reader/Writer（即使技术上可行）
from ditto_data.storage.metadata import InstrumentReader  # ❌
reader = InstrumentReader(...)  # ❌
```

**原则**：
- Sources 层（数据获取）可由 Interfaces 层直接访问
- Reader/Writer 层（数据存储）必须通过 Service 间接访问

## 数据质量（DQ）规范

| 类别 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| 技术类 | 非空、唯一、外键 | 写入时 | 阻断写入 |
| 业务类 | OHLC、涨跌幅 | 写入时 | 警告记录 |
| 统计类 | Z-score、完整性 | 定时批量 | 告警通知 |

| 配置文件位置 | 修改后必更新 |
|-------------|-------------|
| `config/default/dq_rules/*.yaml` | `docs/design/09_data_quality_design.md` |

## 数据摄入 T0/T1/T2/T3

| 层级 | 职责 | 调度时机 |
|------|------|----------|
| T0 | 元数据（calendar, basic） | 每日 8:00-9:00 |
| T1 | 增量数据（daily bars） | 交易日 18:00 |
| T2 | 空洞扫描 + 回填 | 每日凌晨 2:00 |
| T3 | 质量检查 | T1 完成后 |

## 游标管理

| 操作 | 说明 |
|------|------|
| 检查 last_attempted | 失败重试前 |
| 更新 last_success | 成功写入后 |

## 安全机制

| 禁止 | 替代 |
|------|------|
| Reader/Writer 直接写 Parquet | 通过对应的 Service |
| 绕过 DQ 检查写入 | Service.write() 自动触发 |
| 硬编码数据路径 | 使用 get_paths() |
| Parquet 写入不加锁 | FileLock (超时 30s) |
| 冻结数据无保护 | FreezeManager.acquirefreeze() |
| Interfaces 层直接访问 Reader/Writer | 通过 Service 间接访问 |
