# Ditto

Ditto 是面向个人全栈量化投资者的本地优先 A 股个股与 ETF 决策工作站，
覆盖研究、回测、Paper Trading 与手工账户管理；系统不连接券商自动下单。

本仓库是联邦式 polyglot monorepo：Python 后端与 TypeScript Web 保留各自原生
生态，由根 Pixi 任务图、同一 OpenAPI 契约、同一 Git 提交和同一 release cohort
统一治理。

## 技术栈

下表由 `tooling/quality/stack_inventory.py` 从 manifests 生成并做 zero-diff 校验。

<!-- stack-inventory:start -->
| 范围 | 事实源 | 声明 |
| --- | --- | --- |
| 产品版本 | `pyproject.toml` | `0.1.0` |
| Python | `pixi.toml` | `3.13.*` |
| Pixi | `pixi.toml` | `>=0.73,<0.74` |
| Bun | `package.json` | `1.3.14` |
| FastAPI | `pixi.toml` | `>=0.115,<0.137` |
| Polars | `pixi.toml` | `>=1.9,<2` |
| React | `apps/web/package.json` | `^19.2.4` |
| TypeScript | `apps/web/package.json` | `~6.0.2` |
| Vite | `apps/web/package.json` | `^8.0.2` |
<!-- stack-inventory:end -->

根 `pixi.toml` 是唯一跨栈任务编排事实源。Pixi 管理 Python、质量工具和任务 DAG；
Bun 只管理 Web workspace 依赖及 lint/type/test/build/codegen 叶子任务。

## 仓库地图

```text
ditto/
├── apps/
│   ├── backend/                 # FastAPI / CLI / Jobs / composition root
│   └── web/                     # React SPA
├── packages/
│   ├── kernel/                  # 零第三方依赖共享原语和 Protocol
│   ├── platform/                # 横切技术基础设施
│   ├── data/                    # 数据源、存储、质量和 PIT 查询
│   ├── features/                # 表达式、因子、物化与评估
│   ├── strategy/                # 策略、Alpha pipeline 与信号
│   ├── portfolio/               # 会计、持仓、现金与调仓
│   ├── risk/                    # 盘前/盘后风控
│   ├── execution/               # OMS、成交、审计与对账
│   ├── backtest/                # 回放、模拟、统计与报告
│   ├── analysis/                # 研究 control-plane
│   ├── application/             # CQRS 与跨能力编排
│   └── agent/                   # 只消费 application 的治理 Agent
├── contracts/openapi/v1.json   # 跨语言 API 语义快照
├── tests/system/                # production Web + real API E2E
├── tooling/                     # contracts / harness / quality / dev / release
├── deploy/                      # 独立制品定义
└── docs/                        # 当前架构、ADR、runbook 与迁移证据
```

Python 的 13 个 distribution 使用同一产品版本但不独立发布。包依赖方向由
`.importlinter` 机器强制；目录合并没有放宽 `kernel`、`platform`、`application`、
`agent` 或 composition root 的边界。

Web 依赖方向由 alias-aware dependency graph 强制：

```text
app/routes → workflows → feature public APIs → shared → ui/lib
feature api adapters → typed src/api → contracts/openapi/v1.json
```

## 快速开始

需要 Pixi `>=0.73,<0.74`。Bun 版本由根 `packageManager` 固定；不要使用 pip、
Poetry、Conda、pnpm 或 npm 修改项目环境。

```bash
pixi run -e dev bootstrap
pixi run -e dev dev
```

`dev` 会为当前 worktree 分配隔离端口、state/cache/log 目录，等待 API/Web
readiness，并在 Ctrl-C、异常退出或超时后回收子进程。默认 profile 不读取真实用户
数据库、市场数据或凭证。

## 根任务接口

| 命令 | 作用 |
| --- | --- |
| `pixi run -e dev bootstrap` | 校验工具链并执行冻结锁文件安装 |
| `pixi run -e dev dev` | 受监督地启动 API 与 Web |
| `pixi run -e dev check-backend` | Python lint、format、type、architecture、fast tests |
| `pixi run -e dev check-web` | Web lint、全部 TS project、unit、graph 与产品合同 |
| `pixi run -e dev check-contract` | OpenAPI export/lint/breaking/codegen zero-diff |
| `pixi run -e dev test-system` | production Web + 隔离真实 API 的 Playwright |
| `pixi run -e dev harness-check` | 根 Agent/Skill/hook/eval 静态验证 |
| `pixi run -e dev check` | 唯一跨栈快速门 |
| `pixi run -e dev ci` | 覆盖率、PIT、prototype、E2E、安全与制品全门 |
| `pixi run -e dev check-changed` | Agent 本地反馈；未知路径 fail closed |

Web 目录中的 Bun scripts 是叶子开发入口，不定义另一套跨栈 `check/ci` DAG。
完整 `ci` 还会通过固定 digest 的 scanner image 构建、扫描并 smoke 后端容器，
因此本地执行需要可用的 Docker daemon；daemon 不可用时任务会 fail closed。

## API 契约

FastAPI 的 side-effect-free app factory 是 API 语义源，提交后的唯一跨语言契约为
`contracts/openapi/v1.json`。流水线执行：

1. 规范化导出并做字节比较；
2. Redocly `recommended-strict` lint；
3. oasdiff 对 merge base 与最新 release 做 breaking check；
4. 离线 `openapi-typescript` 生成并 zero-diff；
5. Web 通过 `openapi-fetch` 的 `paths` 类型消费，feature adapter 再映射为 view model。

禁止手改 canonical snapshot 或 generated schema。API 变更请先阅读
[`contracts/AGENTS.md`](contracts/AGENTS.md)。

## 运行时与本地优先边界

生产进程不依赖 Git checkout、`.git`、`pixi.toml` 或 `parents[n]` 推断路径：

- `DITTO_CONFIG_ROOT`：显式配置；
- `DITTO_STATE_ROOT`：SQLite、账本与运行状态；
- `DITTO_CACHE_ROOT`：可删除缓存。

API 默认只监听 loopback，CORS 使用精确 allowlist。Web 正式制品通过无秘密的
`ditto-runtime-config.json` 获得 API origin；正式构建不得启用 mock。Cloudflare 或
其他公网部署不属于默认架构，必须另立 ADR 与威胁模型。

## 正确性不变量

- 数据帧与表计算只使用 Polars，不引入 pandas。
- PIT 查询 fail closed；knowledge date、publication cutoff 和 source snapshot 必须传播。
- rolling 窗口左闭；因子、回测和信号必须有 future-sentinel 证据。
- 订单 FSM、账本、恢复、幂等、审计与重放语义不得被 UI 或 adapter 重定义。
- `agent` 只能通过 `application` 使用业务能力。
- 禁止用 `TYPE_CHECKING`、延迟 import、re-export、`type: ignore` 或宽泛 `noqa`
  隐藏边界/类型问题。

## 发布

后端与 Web 构建为独立制品，但正式发布单位是同一 tag 的 cohort。manifest 的
`release` 记录 `product_version`、`git_sha`、`api_contract_version` 与
`api_contract_sha256`，顶层 `backend_artifact` / `web_artifact` 记录两项制品
digest；部署与回滚可以分别进行，但只支持声明的当前/前一 cohort 兼容矩阵。

## 协作入口

- Agent 规则：[`AGENTS.md`](AGENTS.md)
- 架构快速参考：[`docs/architecture/agent-context-pack.md`](docs/architecture/agent-context-pack.md)
- 边界标准：[`docs/architecture/boundaries-and-abstraction-standards.md`](docs/architecture/boundaries-and-abstraction-standards.md)
- Monorepo ADR：[`docs/adr/0010-polyglot-monorepo.md`](docs/adr/0010-polyglot-monorepo.md)
- 测试指南：[`docs/engineering/testing.md`](docs/engineering/testing.md)
- Harness：[`docs/engineering/agent-harness.md`](docs/engineering/agent-harness.md)

变更前读取根到目标目录的全部 `AGENTS.md`。一项任务使用一个分支和一个 worktree；
contract、lockfile、migration 与 generator 配置由单一 integrator 写入。
