# Infra 与 Foundation 合并设计

> 日期：2026-02-12
> 状态：✅ 已完成
> 完成日期：2026-02-13
> 实施计划：[2026-02-12-infra-foundation-merge-impl.md](2026-02-12-infra-foundation-merge-impl.md)

## 背景

### 当前问题

1. **Foundation 层**包含业务无关的基础能力，但也包含了 `notification` 模块
2. **Port 层**有 `notifications/` 目录，是对 Foundation 通知能力的业务适配
3. 未来会有更多应用级基础设施服务（埋点 Catalog、限流等）
4. 需要明确"技术基础设施"与"应用基础设施"的边界

### 术语定义

| 术语 | 定义 | 示例 |
|------|------|------|
| **技术基础设施** | 完全业务无关的底层能力 | DB连接池、通用日志、缓存 |
| **应用基础设施** | 可含业务上下文的基础服务 | 业务告警、埋点 Catalog、限流规则 |
| **业务服务** | 业务领域编排 | IngestionService, OrderService |

## 设计方案

### 目标结构

```
packages/
├── infra/                       # 统一的基础设施层
│   ├── foundation/              # 【纯技术基础设施】
│   │   ├── db/                  # SQLitePool
│   │   ├── observability/       # 通用 logger, tracer, metrics
│   │   ├── cache/               # DataCache
│   │   ├── concurrency/         # FileLockManager
│   │   ├── checksum/            # 校验和
│   │   ├── quality/             # DQSeverity
│   │   ├── pit/                 # PitConfig
│   │   ├── config/              # 环境配置
│   │   └── util/                # 工具函数
│   │
│   └── services/                # 【应用级基础设施服务】
│       ├── notification/        # 通知服务
│       │   ├── sender.py        # 通用发送能力
│       │   ├── channels/        # EmailSender, WebhookSender
│       │   ├── template.py      # TemplateEngine
│       │   ├── manager.py       # AlertManager
│       │   ├── alerts.py        # 业务告警函数
│       │   └── templates/       # 业务模板目录
│       │
│       ├── telemetry/           # 【未来】埋点服务
│       └── rate_limit/          # 【未来】限流服务
│
├── datahub/                     # 数据访问层（保持不变）
└── core/                        # 核心引擎（保持不变）

apps/port/
├── services/                    # 业务服务（保持不变）
└── registry/                    # DI Provider（调整导入路径）
```

### 依赖关系

```
apps/port/services/ingestion/
         │
         ▼
packages/infra/services/notification/
         │
         ▼
packages/infra/foundation/
```

## 迁移计划

### Phase 1: 创建 infra 包结构

1. 创建 `packages/infra/` 目录
2. 创建 `packages/infra/foundation/` 子包
3. 创建 `packages/infra/services/` 子包

### Phase 2: 迁移 foundation 内容

1. 将 `packages/foundation/` 内容移至 `packages/infra/foundation/`
2. 更新所有导入路径

### Phase 3: 迁移 notification 服务

1. 将 `packages/foundation/notification/` 移至 `packages/infra/services/notification/`
2. 将 `apps/port/notifications/` 业务适配合并到 `packages/infra/services/notification/`
3. 更新 `apps/port/registry/notification.py` 导入路径
4. 删除 `apps/port/notifications/` 目录

### Phase 4: 清理与验证

1. 删除旧的 `packages/foundation/` 目录
2. 运行完整测试套件

## 导入路径变更

### 变更前

```python
from ditto_foundation.notification.sender import NotificationSender
from ditto_foundation.db.sqlite_pool import SQLitePool
from ditto_port.notifications import AlertManager
```

### 变更后

```python
from ditto_infra.foundation.db import SQLitePool
from ditto_infra.services.notification import AlertManager, alert_dq_failure
```

## 决策记录

### Q: 为什么 notification 放在 packages/infra/services/ 而不是 apps/port/services/？

**A:** 通知是横切关注点，多个 apps 可能需要共享。

### Q: 为什么需要 foundation 子包？

**A:** 明确区分"技术基础设施"与"应用基础设施服务"，便于理解依赖方向。

## 参考资料

- [Platform Specification - The Four Layers](https://platformspec.io/docs/types/infrastructure/the-four-layers.html)
- [Domain-Application-Infrastructure Services Pattern](https://badia-kharroubi.gitbooks.io/microservices-architecture/content/patterns/tactical-patterns/domain-application-infrastructure-services-pattern.html)
