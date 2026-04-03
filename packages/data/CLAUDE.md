# DataHub 架构规范

## 分层职责

| 层级 | 职责 | 禁止 | 必须 |
|------|------|------|------|
| Reader | 数据查询操作 | 包含业务逻辑 | 类型注解 |
| Writer | 数据写入/删除操作 | 包含业务逻辑 | 类型注解 |
| Service | 业务逻辑封装 | 直接访问文件系统 | 通过 Reader/Writer |
| Runtime | 基础设施 | 包含业务逻辑 | - |
| Source | 外部数据源 | 包含业务逻辑 | 重试、限流、监控埋点 |

## CQRS 模式（Command Query Responsibility Segregation）

DataHub Store 层采用 CQRS 模式，将读写操作分离：

### Reader 组件
- **职责**：数据查询（read/count/get_*）
- **特点**：无副作用，可并发执行
- **方法**：`read()`, `count()`, `get_*()`

### Writer 组件
- **职责**：数据写入/删除（write/delete）
- **特点**：有副作用，需要并发控制
- **方法**：`write()`, `delete()`

### 命名约定
- 查询类：`*_reader.py`（如 `instrument_reader.py`）
- 写入类：`*_writer.py`（如 `instrument_writer.py`）
- 服务类：`*_service.py`（如 `metadata_service.py`）

## 层级访问规则（2026-02-10 更新）

### Port 层访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 | 说明 |
|---------|--------|--------|------|
| **通过 Domain Service** | `MetadataService`, `MarketService` 等 | - | **推荐方式**，通过 DI 容器注入 |
| **直接导入** | `from ditto_data.sources.*` | `from ditto_data.storage.*` | Sources 可直接访问，Storage 禁止 |
| **Reader/Writer** | - | 直接实例化 | **禁止**直接访问 Reader/Writer 层 |

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
- Sources 层（数据获取）可由 Port 层直接访问
- Reader/Writer 层（数据存储）必须通过 Service 间接访问

## 数据质量（DQ）规范

| 类别 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| 技术类 | 非空、唯一、外键 | 写入时 | 阻断写入 |
| 业务类 | OHLC、涨跌幅 | 写入时 | 警告记录 |
| 统计类 | Z-score、完整性 | 定时批量 | 告警通知 |

| 配置文件位置 | 修改后必更新 |
|-------------|-------------|
| `packages/data/config/dq/*.yaml` | `docs/design/09_data_quality_design.md` |

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
| Port 层直接访问 Reader/Writer | 通过 Service 间接访问 |
