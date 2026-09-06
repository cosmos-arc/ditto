# Ditto Agent 指南

Ditto 是面向个人全栈量化投资者的本地优先 A 股与 ETF 量化决策、Paper Trading 和手工账户管理工作站，不连接券商下单。Python/Pixi 与 React/TypeScript/Bun 独立构建，以同一提交、跨栈契约和 release cohort 验收。

## 事实与阅读入口

机器约束、源码/测试、架构文档、本文件依次优先；改动位置的近端 AGENTS 补充局部约束。命令以根 `pixi.toml` 与 CI 为准，依赖边界以 `.importlinter` 和 Web dependency graph 为准。

- 涉及跨包、公共 API、DI 或目录归属：读 [架构快速参考](docs/architecture/agent-context-pack.md)；新增概念或调整抽象时读 [边界标准](docs/architecture/boundaries-and-abstraction-standards.md)。
- 涉及 HTTP DTO、OpenAPI 或 Web transport：读 [契约指南](contracts/AGENTS.md) 与 [兼容性](contracts/openapi/README.md)。
- 涉及 Bug、行为变化或验证安排：读 [测试指南](docs/engineering/testing.md)。
- 涉及宿主 hooks、scope、receipt 或共享写入：读 [Harness 说明](docs/engineering/agent-harness.md)。
- 处理 issue/spec/review 来源：使用 [GitHub Issues](docs/agents/issue-tracker.md)；状态标签见 [triage 配置](docs/agents/triage-labels.md)。
- 探索领域命名或 ADR：按 [领域文档布局](docs/agents/domain.md) 检索。

## 关键不变量

- 根 Pixi 是唯一跨栈任务 DAG；Web 使用 Bun，根保留唯一 `bun.lock`。不以 pip/poetry/conda 或 npm/yarn/pnpm 修改环境。
- 数据帧与表计算用 Polars；外部高性能序列化优先 orjson，现有 schema、SQLite、测试和规范化场景允许标准库 json。
- `application` 编排能力包，产品 `agent` 只经 application 使用业务能力，`apps/backend` 是唯一 Python composition root；kernel 零第三方依赖、零 I/O。
- 跨栈方向为 FastAPI → 本地 OpenAPI snapshot → generated types/runtime metadata → typed transport → feature adapter → UI。生成物通过生成器更新，组件使用 view model。
- 消费者从定义符号的源包/叶模块导入；循环依赖通过修正边界解决，不能用 re-export、TYPE_CHECKING 或延迟导入掩盖。
- 运行时 config/state/cache 显式定位；`workspace_root` 仅用于开发工具与测试。
- PIT 查询 fail closed，knowledge date、publication cutoff 和 source snapshot 必须传播。涉及查询、窗口、join、修订、因子或回测时间语义时使用 `ditto-pit-safety`。
- 不通过 type ignore、宽泛 noqa、跳过 hooks 或 no-verify 规避有效质量门；只报告实际运行结果。

## 工作与授权

局部可逆编辑、读取和非破坏性验证直接执行。通用规划、调试、审查由宿主和模型按任务选择；普通工作不要求固定角色、评分、重复确认或隐式 commit/tag。

新增/升级生产依赖、schema/数据迁移、架构边界、CI 权限/发布配置、生产或真实数据写入、真实券商操作及难以恢复的数据删除需明确授权；当前任务已明确要求的同类操作视为已授权，执行前核对精确目标。

日常调研、小修复和文档调整在当前目录处理；大型迭代用独立分支和 worktree。contract、lockfile、migration 和 generator 配置由 integrator 单写；各 worktree 隔离端口及 state/cache/log/browser 输出。

不在 main 直接 commit/push，不 force push，不提交 secrets。
