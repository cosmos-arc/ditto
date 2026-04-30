# Platform 层架构规范

## 定位

Platform 层（原 Foundation）是**横切层**，提供跨所有层的基础设施服务，可被任何层访问。

**核心原则**：
- 零业务逻辑
- 零领域概念
- 可独立提取为通用包

## 模块结构

```
ditto_platform/
├── foundation/                    # 基础模块（原独立 foundation 包）
│   ├── cache/                    # 通用缓存（DataCache）
│   ├── checksum/                 # 校验和计算（file.py）
│   ├── concurrency/              # 并发控制（FileLockManager）
│   ├── config/                   # 配置管理（Settings、路径、环境）
│   │   └── providers/            # 配置提供者（校验、数据根路径）
│   ├── db/                       # 数据库连接（SQLitePool）
│   ├── observability/            # 可观测性（日志、追踪、指标、生命周期）
│   └── util/                     # 通用工具（日期、IO、校验和、Ticker）
└── services/                     # 基础服务
    └── notification/             # 通知服务（Telegram、Email、Webhook）
        ├── channels/             # 通知渠道实现（email、telegram、webhook）
        └── templates/            # 通知模板（alerts）
```

## 导入规范

```python
# ✅ 正确：从 foundation 子模块导入
from ditto_platform.foundation import get_logger, SQLitePool, DataCache
from ditto_platform.foundation.config import get_settings, get_environment
from ditto_platform.foundation.concurrency import FileLockManager

# ✅ 正确：从 services 子模块导入
from ditto_platform.services.notification import NotificationManager

# ❌ 错误：直接从 ditto_platform 导入内部模块
from ditto_platform.config import ...  # 应为 ditto_platform.foundation.config
```

## 模块职责

| 模块 | 职责 | 禁止 |
|------|------|------|
| `cache` | 数据缓存、缓存统计 | 包含业务逻辑 |
| `checksum` | 文件/数据校验和（纯工具，sort_keys 由调用方提供） | 领域知识（如数据集排序键映射） |
| `concurrency` | 文件锁、并发控制 | - |
| `config` | 配置加载、环境管理、XDG 路径 | 读取业务配置或数据源特定校验 |
| `db` | SQLite 连接池 | 包含 SQL 业务逻辑 |
| `observability` | 日志、追踪、指标 | - |
| `util` | 通用工具函数 | 领域特定工具 |
| `notification` | 通知发送 | 包含业务逻辑 |

## 依赖规则

```
┌─────────────────────────────────────┐
│  所有层都可以访问 Platform（foundation）│
│  interfaces → platform ✅             │
│  app → platform ✅                    │
│  engine → platform ❌                 │
│  analytics → platform ✅              │
│  data → platform ✅                   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Platform 禁止依赖其他层               │
│  platform → interfaces ❌             │
│  platform → app ❌                    │
│  platform → engine ❌                 │
│  platform → analytics ❌              │
│  platform → data ❌                   │
└─────────────────────────────────────┘
```

## 各层 Platform Scope 限制

| 层 | 允许范围 | 说明 |
|----|---------|------|
| interfaces | `foundation` + `services` | 完整访问（Composition Root） |
| app | `foundation` + `services` | 禁止 `config`（配置加载走 interfaces） |
| data | 仅 `foundation` | 存储通过 foundation.db / foundation.util |
| analytics | 仅 `foundation` | 配置、日志等基础能力 |
| engine | 禁止 | 不依赖 platform |

## 配置规范

详见 [config.md](/.claude/rules/config.md)

### 环境获取

```python
# ✅ 正确：使用统一入口
from ditto_platform.foundation.config import get_environment
env = get_environment()  # development | testing | production

# ❌ 错误：直接读取环境变量
import os
env = os.getenv("ENVIRONMENT")  # 绕过统一入口
```

### 配置加载位置

配置仅在 **Interfaces 层** 加载，其他层通过 DI 获取。详见 [config.md](/.claude/rules/config.md)。

## 测试规范

### 测试文件位置

```
packages/platform/
├── src/ditto_platform/
└── tests/
    ├── unit/           # 单元测试
    │   ├── cache/
    │   ├── checksum/
    │   ├── concurrency/
    │   ├── config/
    │   ├── db/
    │   ├── notification/
    │   ├── observability/
    │   └── util/
    └── integration/    # 集成测试
```

### 运行测试

```bash
pixi run -e dev pytest packages/platform/tests/
```

## 历史说明

> **2026-02-16 重构**：原 `packages/foundation/` 合并到 `packages/platform/`，作为 `ditto_platform.foundation` 子模块存在。导入路径从 `ditto_foundation` 变更为 `ditto_platform.foundation`。
