# Foundation 基础设施规范

## 可观测性

| 操作 | 必须使用 | 命名规范 |
|------|----------|----------|
| 数据读写 | @traced 装饰器 | data.read/write.{dataset} |
| 复杂操作 | with span() | compute.{operation} |
| 指标记录 | M.{metric}.add() | - |
| 应用启动 | init(name, mode) | - |

| Mode | 适用场景 |
|------|----------|
| PRODUCTION | 生产环境 |
| DEVELOPMENT | 本地开发 |
| TESTING | 单元测试 |
| TESTING_WITH_ASSERTIONS | 测试+断言 |

## 配置管理

| 禁止 | 替代 |
|------|------|
| 硬编码路径 | get_settings() |
| 直接访问环境变量 | Settings 模型 |
| 绕过 AppInitializer | init() 函数 |

## I/O 操作

| 禁止 | 替代 |
|------|------|
| open() + write() | atomic_write() |
| 直接 pathlib | get_paths() |

## 导入规范

Foundation 层是最底层，禁止依赖 Ditto 内部其他模块（如 datahub、core）。

允许的外部依赖：
- 标准库
- 第三方库（polars、fastapi、loguru、httpx 等）

详见项目根目录的 CLAUDE.md 中的依赖规范。
