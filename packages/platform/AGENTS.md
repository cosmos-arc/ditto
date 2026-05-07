# Platform Agent 指南

## 定位

横切基础设施层 — 通用技术能力（缓存/日志/DB/存储基类/通知），零业务逻辑、零领域概念。

## 核心模块

| 模块 | 职责 |
|------|------|
| foundation/cache | 通用缓存（DataCache） |
| foundation/concurrency | 文件锁、并发控制 |
| foundation/config | 配置管理（Settings、路径、环境） |
| foundation/db | SQLite 连接池 |
| foundation/observability | 日志、追踪、指标、生命周期 |
| foundation/storage | 通用存储基类（ParquetStore、SQLiteClient） |
| services/notification | 通知服务（Telegram、Email、Webhook） |

## 依赖规则

### 允许

- platform → kernel ⚠️（仅 exceptions 继承 DittoError）

### 禁止

- platform → data/strategy/execution/backtest/application/apps ❌

## 关键约束

- 零业务逻辑、零领域概念、可独立提取为通用包
- 导入必须从 `ditto_platform.foundation` 或 `ditto_platform.services` 入口
- 配置仅在 Apps 层加载，Platform 只提供配置工具

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
