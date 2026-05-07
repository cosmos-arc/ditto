# Platform 单元测试

## 测试分类

| 目录 | 测试内容 |
|------|----------|
| `cache/` | DataCache 缓存读写与统计 |
| `checksum/` | 文件/数据校验和 |
| `concurrency/` | FileLockManager 并发控制 |
| `config/` | 配置加载、环境检测、路径、初始化、交易设置 |
| `db/` | SQLitePool 连接管理与多线程 |
| `notification/` | 消息构造、模板渲染、Telegram/Webhook 发送 |
| `observability/` | 日志格式、追踪装饰器、指标注册、测试辅助 |
| `util/` | 日期工具、Property 测试、IO 工具、Ticker 工具 |

## 运行测试

```bash
pixi run -e dev pytest packages/platform/tests/unit -v                          # 全部
pixi run -e dev pytest packages/platform/tests/unit/observability -v            # 可观测性
pixi run -e dev pytest packages/platform/tests/unit/util -v                     # 工具函数
pixi run -e dev pytest packages/platform/tests/unit/config -v                   # 配置
```

## 覆盖率要求

分支覆盖率 >= 80%
