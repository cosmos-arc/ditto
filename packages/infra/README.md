# ditto-infra

**版本**: v0.1.1
**最后更新**: 2026-03-24
**状态**: ✅ 稳定

## 概要

基础设施层（Infra Layer）是 Ditto 量化系统的横切层，提供跨所有层的基础设施服务。

## 架构定位

```
┌─────────────────────────────────────┐
│         apps/port                 │
│     (FastAPI 服务层)                  │
├─────────────────────────────────────┤
│      packages/datahub              │
│     (数据访问层)                      │
├─────────────────────────────────────┤
│      packages/core                 │
│     (核心业务层)                      │
├─────────────────────────────────────┤
│      packages/infra (当前层)        │
│     (基础设施层)                      │
└─────────────────────────────────────┘
```

**依赖规则**: Infra 层零依赖其他层，可被所有层访问。

## 模块结构

```
ditto_infra/
├── foundation/           # 基础模块（原 foundation 包）
│   ├── cache/           # 通用缓存
│   ├── checksum/        # 校验和计算
│   ├── concurrency/     # 并发控制
│   ├── config/          # 配置管理
│   ├── db/              # 数据库连接
│   ├── observability/   # 可观测性
│   └── util/            # 通用工具
│       ├── dates.py         # 日期工具
│       ├── io.py            # IO 工具
│       ├── ticker_utils.py  # Ticker 工具
│       └── checksum.py      # 校验和计算
└── services/            # 基础服务
    └── notification/    # 通知服务
```

## 核心功能

| 模块 | 功能 |
|------|------|
| `cache` | 数据缓存、缓存统计 |
| `checksum` | 文件/数据校验和 |
| `concurrency` | 文件锁、并发控制 |
| `config` | 配置加载、环境管理、XDG 路径 |
| `db` | SQLite 连接池 |
| `observability` | 日志、追踪、指标 |
| `notification` | Telegram、Email、Webhook 通知 |

## 使用方式

```python
# 导入基础设施组件
from ditto_infra.foundation import (
    logger,
    SQLitePool,
    DataCache,
    FileLockManager,
)
from ditto_infra.foundation.config import get_environment, Settings
from ditto_infra.services.notification import NotificationManager
```

## 测试

```bash
pixi run -e dev pytest packages/infra/tests/
```

## 历史说明

> **2026-02-16 重构**: 原 `packages/foundation/` 合并到 `packages/infra/`，作为 `ditto_infra.foundation` 子模块存在。导入路径从 `ditto_foundation` 变更为 `ditto_infra.foundation`。
