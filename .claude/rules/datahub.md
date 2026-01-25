---
paths: packages/datahub/**/*.py
---

# DataHub 架构规范

## 分层职责

| 层级 | 职责 | 禁止 | 必须 |
|------|------|------|------|
| Store | 数据持久化 | 包含业务逻辑 | @traced 装饰器 |
| Accessor | 业务封装 | 直接访问文件系统 | 通过 Store 访问 |
| Runtime | 基础设施 | 包含业务逻辑 | - |
| Provider | 外部数据源 | 包含业务逻辑 | 重试、限流、监控埋点 |

## 层级访问规则（2026-01-19 更新）

### Apps 层访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 | 说明 |
|---------|--------|--------|------|
| **通过 DataHub** | `hub.sources` | - | **官方接口**，推荐使用 |
| **直接导入** | `from ditto_datahub.sources.*` | `from ditto_datahub.stores.*` | Providers 可直接访问，Stores 禁止 |
| **Accessor** | `hub.bars`, `hub.calendar` 等 | - | **数据查询**的推荐方式 |
| **Store** | - | `直接实例化 Store 类` | **禁止**直接访问 Store 层 |

### 正确示例

```python
# ✅ 推荐：通过 DataHub providers 获取数据
provider = hub.sources.get("tushare")
df = provider.fetch_stock_daily("2024-01-02")

# ✅ 推荐：通过 Accessor 查询数据
bars = hub.bars.get(...)
df = bars.query(...)

# ❌ 禁止：直接访问 Store（即使技术上可行）
from ditto_datahub.stores.bars_store import BarsStore  # ❌
store = BarsStore(...)  # ❌
```

**原则**：
- Providers 层（数据获取）可由 Apps 层直接访问
- Stores 层（数据存储）必须通过 Accessor 间接访问

## 数据质量（DQ）规范

| 类别 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| 技术类 | 非空、唯一、外键 | 写入时 | 阻断写入 |
| 业务类 | OHLC、涨跌幅 | 写入时 | 警告记录 |
| 统计类 | Z-score、完整性 | 定时批量 | 告警通知 |

| 配置文件位置 | 修改后必更新 |
|-------------|-------------|
| `packages/datahub/config/dq/*.yaml` | `docs/design/09_data_quality_design.md` |

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
| Accessor 直接写 Parquet | 通过对应的 Store |
| 绕过 DQ 检查写入 | hub.xxx.write() 自动触发 |
| 硬编码数据路径 | 使用 get_paths() |
| Parquet 写入不加锁 | FileLock (超时 30s) |
| 冻结数据无保护 | FreezeManager.acquirefreeze() |
