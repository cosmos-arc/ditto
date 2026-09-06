# Ditto Agent 指南

Ditto 是面向个人全栈量化投资者的本地优先 A 股个股与 ETF 量化决策、Paper Trading 和手工账户管理工作站；宏观与全球核心市场数据用于解释 A 股环境，系统不连接券商下单。仓库是 Python/Pixi + React/TypeScript/Bun 的联邦式 monorepo；后端和 Web 独立构建，但由同一提交、契约和 release cohort 验收。

## 事实优先级

冲突时依次以机器约束、源码/测试、架构文档、本文件为准：

1. `.importlinter`、Web dependency graph 与 `contracts/openapi/v1.json` 是依赖和跨栈边界的机器事实源；根 `pixi.toml` 和 CI 是任务门事实源。
2. 源码、类型与测试定义当前行为；不要用旧计划覆盖现状。
3. [架构快速参考](docs/architecture/agent-context-pack.md) 说明当前能力平面与常用入口。
4. [边界与抽象标准](docs/architecture/boundaries-and-abstraction-standards.md) 说明命名、分层和新概念准入。
5. `apps/backend`、`apps/web`、`contracts` 与 capability package 的近端 `AGENTS.md` 补充局部约束，越接近改动位置的规则优先。

## Monorepo 地图与方向

- `apps/backend`：FastAPI、CLI、Jobs 与唯一 Python composition root；导入名仍为 `ditto_apps`。
- `apps/web`：React SPA；Bun 只拥有 Web workspace 依赖和叶子任务。
- `packages/*`：12 个后端 capability/application/agent package。
- `contracts/openapi`：FastAPI 导出的唯一跨语言契约。
- `tests/system`：production Web + 隔离 API 的跨栈 E2E。
- `tooling`：根 Harness、契约、质量与开发监督器。

根 Pixi 是唯一跨栈任务 DAG。依赖方向固定为：

```text
apps/backend -> contracts/openapi -> apps/web/src/api/generated
                                   -> typed transport -> feature adapters -> UI
```

Web 不导入 Python DTO/源码/存储模型；后端不读取 Web 状态或生成物。运行时不得依赖 Git checkout 推断 config/state/cache；`workspace_root` 只供开发工具和测试使用。

## 13 包架构地图

- `kernel`：共享原语与 Protocol；零第三方依赖、零 I/O。
- `platform`：横切技术基础设施；不得承载业务概念。
- `data`：数据源、摄取、存储、质量与 PIT 查询。
- `features`：表达式、因子、物化与评估。
- `strategy`：策略规格、Alpha pipeline 与信号。
- `portfolio`：会计、持仓、现金与调仓。
- `risk`：盘前/盘后风控、约束与暴露。
- `execution`：OMS、券商网关、成交、审计与对账。
- `backtest`：模拟运行时、回放、统计与报告。
- `analysis`：研究 control-plane 与独立研究存储。
- `application`：CQRS 用例和跨能力编排。
- `agent`：治理型 Agent 运行时、工具、模型端口、审计与 eval；只消费 application。
- `apps/backend`：API、CLI、Jobs 与唯一 composition root。

`application` 编排能力包，`agent` 只通过 application 使用业务能力，`apps/backend` 负责入口和装配；不要把 import-linter 的线性表达误读成业务层级。

## 项目 Skills 路由

只在命中触发条件时使用对应 skill；通用 planning、debugging、review、worktree 与 subagent 编排使用宿主原生能力。

- `ditto-architecture-change`：跨包、新模块、公共 API、DI、依赖方向、目录放置或架构重构。
- `ditto-pit-safety`：数据查询、rolling/shift/join、因子、回测、knowledge date、publication cutoff 或 source snapshot。
- `ditto-test-first`：Bug、行为变化、公共契约、PIT、风控、交易或回测语义。
- `ditto-api-contract-change`：FastAPI route/DTO、OpenAPI、generated types、typed transport 或兼容性变化。
- `ditto-change-review`：用户要求 review、PR 前审查，或高风险 diff 完成后的只读审查。
- `ditto-quality-eval`：仅当用户明确要求全库质量评估时使用。

## Agent skills

### Issue tracker

处理 issue、spec 或 review 的需求来源时，使用 GitHub Issues（`cosmos-arc/ditto`）；先读 [issue tracker 配置](docs/agents/issue-tracker.md)。

### Triage labels

执行 triage 或设置 ticket 状态时，使用五个默认标签；映射见 [triage labels 配置](docs/agents/triage-labels.md)。

### Domain docs

探索领域概念、命名或架构决策前，按 single-context 布局读取文档；规则见 [domain docs 配置](docs/agents/domain.md)。

## 风险与执行合同

- 普通：局部、可逆、不改变外部行为。完成目标测试与 changed-scope 门禁。
- 行为变更：Bug、新行为、公共契约。先观察能解释问题的 RED，再做最小实现、GREEN、重构。
- 高风险：PIT、交易、风控、回测、跨包边界、持久化语义。使用对应 skill，补未来哨兵/集成证据并运行专项门禁。
- 发布/真实数据：发布、生产配置、真实券商、真实数据写入或不可逆操作。执行前取得明确批准并保留可审计证据。

TDD 强制适用于 Bug、行为、公共契约、PIT、交易、风控和回测语义。纯文档、格式化、纯移动和机械重命名豁免，但仍须验证没有意外行为变化。

## 验证矩阵

- 文档/注释：目标文档检查；Harness/AGENTS/Skills 另跑 `pixi run -e dev harness-check`。
- 仅测试：变更测试 + `pixi run -e dev fmt-check` + `pixi run -e dev lint` + `pixi run -e dev type --tests`。
- 后端 Python：`pixi run -e dev check-backend`。
- Web TS/TSX/CSS：`pixi run -e dev check-web`。
- API/DTO/OpenAPI：`pixi run -e dev check-contract` + provider/adapter 目标测试。
- 跨栈行为：上述双栈门 + `pixi run -e dev test-system`。
- 根 lock、CI、Harness 或未知路径：`pixi run -e dev check`，未知分类 fail closed。
- PIT：目标测试 + `pixi run -e dev pytest -m pit`。
- 架构：上述验证 + `pixi run -e dev arch-check`。
- 提交/PR 前：`pixi run -e dev ci`、`git diff --check`；涉及 Harness 再跑 pre-commit。

只报告实际运行过的命令与结果；失败不得隐瞒。更细测试约定见 [测试指南](docs/engineering/testing.md)。

## Approval 边界

无需额外批准：读取、搜索、局部编辑、非破坏性测试与静态检查。

必须先批准：新增/升级生产依赖、数据库 schema 或数据迁移、架构边界变更、CI 权限/发布配置、生产/真实数据写入、真实券商操作、删除或覆盖难以恢复的数据。用户已明确要求的同类变更视为已授权，但仍先核对精确目标。

## 不可妥协项

- 数据帧与表计算使用 Polars，不引入 pandas。
- 依赖与任务使用 Pixi，不以 pip/poetry/conda 修改项目环境。
- Web 只使用 Bun；不引入 npm/yarn/pnpm lockfile。根保留唯一 `bun.lock`。
- generated OpenAPI 类型禁止手改；组件不得直接消费 generated DTO。
- 外部高性能序列化优先 `orjson`；现有 schema、SQLite、测试和规范化场景允许标准库 `json`。
- 消费者从定义符号的源包/叶模块导入；禁止用跨包 re-export 隐藏依赖。
- 不用 `TYPE_CHECKING` 或延迟导入掩盖循环依赖；修正边界或抽取契约。
- 不以 `# type: ignore`、宽泛 `# noqa`、跳过 hooks 或 `--no-verify` 规避质量门。
- PIT 查询 fail closed；rolling 窗口左闭，knowledge date、publication cutoff 与 source snapshot 必须传播。
- 日常调研、小修复和文档调整默认在当前工作目录处理；仅大型需求迭代使用独立分支和 worktree。
- contract、lockfile、migration 和 generator 配置只允许 integrator 同时写入。每个 worktree 使用独立端口、state/cache/log/browser 输出。
- 不在 `main` 直接 commit/push，不 force push，不提交 secrets。
