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
| Source | 外部数据源 | 包含业务逻辑 | 重试、限流、监控埋点 |

## 数据质量（DQ）规范

| 层级 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| L1 | 非空、唯一、外键 | 写入时 | 阻断写入 |
| L2 | OHLC、涨跌幅 | 写入时 | 警告记录 |
| L3 | Z-score、完整性 | 定时批量 | 告警通知 |

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
