# ditto-platform

**版本**: v0.2.0
**最后更新**: 2026-04-27
**状态**: 稳定

## 概要

基础设施层（Platform Layer）是 Ditto 量化系统的横切层，提供跨所有层的基础设施服务。

## 架构定位

```
┌─────────────────────────────────────┐
│         interfaces                  │
│     (应用边界层)                     │
├─────────────────────────────────────┤
│      packages/app                   │
│     (应用编排层)                     │
├─────────────────────────────────────┤
│      packages/analytics             │
│     (表达式编译 + 因子 + 研究)       │
├─────────────────────────────────────┤
│      packages/engine                │
│     (核心业务层)                     │
├─────────────────────────────────────┤
│      packages/data                  │
│     (数据访问层)                     │
├─────────────────────────────────────┤
│      packages/kernel                │
│     (共享内核 — 零业务行为类型)       │
├─────────────────────────────────────┤
│      packages/platform (当前层)      │
│     (基础设施层)                     │
└─────────────────────────────────────┘
```

**依赖规则**: Platform 层零依赖其他层，可被所有层访问。

## 模块结构

```
ditto_platform/
├── foundation/                    # 基础模块（原 foundation 包）
│   ├── cache/                    # 通用缓存（DataCache）
│   ├── checksum/                 # 校验和计算
│   ├── concurrency/              # 并发控制（FileLockManager）
│   ├── config/                   # 配置管理（Settings、路径、环境）
│   │   └── providers/            # 配置提供者（校验、数据根路径）
│   ├── db/                       # 数据库连接（SQLitePool）
│   ├── observability/            # 可观测性（日志、追踪、指标、生命周期）
│   └── util/                     # 通用工具（日期、IO、校验和、Ticker）
└── services/                     # 基础服务
    └── notification/             # 通知服务（Telegram、Email、Webhook）
        ├── channels/             # 通知渠道实现
        └── templates/            # 通知模板
```

## 核心功能

| 模块 | 功能 |
|------|------|
| `cache` | 数据缓存、缓存统计 |
| `checksum` | 文件/数据校验和 |
| `concurrency` | 文件锁、并发控制 |
| `config` | 配置加载、环境管理、XDG 路径 |
| `config/providers` | 配置提供者（校验、数据根路径） |
| `db` | SQLite 连接池 |
| `observability` | 日志、追踪、指标、生命周期 |
| `notification` | Telegram、Email、Webhook 通知 |
| `notification/channels` | 通知渠道实现 |
| `notification/templates` | 通知模板 |

## 使用方式

```python
# 导入基础设施组件
from ditto_platform.foundation import (
    logger,
    SQLitePool,
    DataCache,
    FileLockManager,
)
from ditto_platform.foundation.config import get_environment, Settings
from ditto_platform.services.notification import NotificationManager
```

## 测试

```bash
pixi run -e dev pytest packages/platform/tests/
```

## 变更记录

### v0.2.0 (2026-04-27)
- 新增 config/providers/、notification/channels/、notification/templates/ 子目录
- 扩展 observability 细节（日志/追踪/指标/生命周期）

## 历史说明

> **2026-02-16 重构**: 原 `packages/foundation/` 合并到 `packages/platform/`，作为 `ditto_platform.foundation` 子模块存在。导入路径从 `ditto_foundation` 变更为 `ditto_platform.foundation`。
