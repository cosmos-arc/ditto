# Platform 测试

## 测试技术栈

pytest + polars.testing + pytest-mock + hypothesis（Property 测试）

## 测试标记

| 标记 | 描述 | 运行时机 |
|------|------|----------|
| `unit` | 单元测试（快速隔离） | 每次提交 |
| `integration` | 集成测试（多组件协作） | CI |

## 测试结构

```
tests/
├── unit/                # 单元测试
│   ├── cache/           # 缓存
│   ├── checksum/        # 校验和
│   ├── concurrency/     # 并发控制（文件锁）
│   ├── config/          # 配置管理（环境、路径、初始化）
│   ├── db/              # 数据库（SQLite 连接池）
│   ├── notification/    # 通知（Telegram、Webhook、模板）
│   ├── observability/   # 可观测性（日志、追踪、指标）
│   └── util/            # 工具函数（日期、IO、Ticker）
└── integration/         # 集成测试
    └── observability/   # 可观测性集成
```

## 运行测试

```bash
pixi run -e dev pytest packages/platform/tests/                 # 全部
pixi run -e dev pytest packages/platform/tests/unit -v          # 单元
pixi run -e dev pytest packages/platform/tests/integration -v   # 集成
pixi run -e dev pytest packages/platform/tests/ --cov           # 含覆盖率
```

## 覆盖率要求

分支覆盖率 >= 80%
