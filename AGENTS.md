# Ditto Agent 指南

Ditto 是面向 A 股 ETF 的 T1 全栈量化交易平台。后端是 13 包 Python 模块化单体；前端 `ditto-app` 是独立仓库，不在本仓库范围内。

## 事实优先级

冲突时依次以机器约束、源码/测试、架构文档、本文件为准：

1. `.importlinter` 是包依赖边界的机器事实源；`pixi.toml`、`pyproject.toml` 和 CI 是质量门事实源。
2. 源码、类型与测试定义当前行为；不要用旧计划覆盖现状。
3. [架构快速参考](docs/architecture/agent-context-pack.md) 说明当前能力平面与常用入口。
4. [边界与抽象标准](docs/architecture/boundaries-and-abstraction-standards.md) 说明命名、分层和新概念准入。
5. 包目录内的 `AGENTS.md` 补充该包约束，越接近改动位置的规则优先。

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
- `apps`：API、CLI、Jobs 与唯一 composition root。

`application` 编排能力包，`agent` 只通过 application 使用业务能力，`apps` 负责入口和装配；不要把 import-linter 的线性表达误读成业务层级。

## 项目 Skills 路由

只在命中触发条件时使用对应 skill；通用 planning、debugging、review、worktree 与 subagent 编排使用宿主原生能力。

- `ditto-architecture-change`：跨包、新模块、公共 API、DI、依赖方向、目录放置或架构重构。
- `ditto-pit-safety`：数据查询、rolling/shift/join、因子、回测、knowledge date、publication cutoff 或 source snapshot。
- `ditto-test-first`：Bug、行为变化、公共契约、PIT、风控、交易或回测语义。
- `ditto-change-review`：用户要求 review、PR 前审查，或高风险 diff 完成后的只读审查。
- `ditto-quality-eval`：仅当用户明确要求全库质量评估时使用。

## 风险与执行合同

- 普通：局部、可逆、不改变外部行为。完成目标测试与 changed-scope 门禁。
- 行为变更：Bug、新行为、公共契约。先观察能解释问题的 RED，再做最小实现、GREEN、重构。
- 高风险：PIT、交易、风控、回测、跨包边界、持久化语义。使用对应 skill，补未来哨兵/集成证据并运行专项门禁。
- 发布/真实数据：发布、生产配置、真实券商、真实数据写入或不可逆操作。执行前取得明确批准并保留可审计证据。

TDD 强制适用于 Bug、行为、公共契约、PIT、交易、风控和回测语义。纯文档、格式化、纯移动和机械重命名豁免，但仍须验证没有意外行为变化。

## 验证矩阵

- 文档/注释：目标文档检查；Harness 文档另跑 `pixi run -e dev harness-check`。
- 仅测试：变更测试 + `pixi run -e dev fmt-check` + `pixi run -e dev lint` + `pixi run -e dev type --tests`。
- 生产 Python/依赖/架构/配置：`pixi run -e dev check`。
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
- 外部高性能序列化优先 `orjson`；现有 schema、SQLite、测试和规范化场景允许标准库 `json`。
- 消费者从定义符号的源包/叶模块导入；禁止用跨包 re-export 隐藏依赖。
- 不用 `TYPE_CHECKING` 或延迟导入掩盖循环依赖；修正边界或抽取契约。
- 不以 `# type: ignore`、宽泛 `# noqa`、跳过 hooks 或 `--no-verify` 规避质量门。
- PIT 查询 fail closed；rolling 窗口左闭，knowledge date、publication cutoff 与 source snapshot 必须传播。
- 不在 `main` 直接 commit/push，不 force push，不提交 secrets。
