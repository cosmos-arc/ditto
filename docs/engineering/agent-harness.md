# Ditto Agent Harness

Ditto 只维护 Claude Code 与 Codex 两个宿主。Harness 将项目事实、可复用知识、宿主适配和机器门禁分层，避免把通用代理工作流重复包装成项目规则。

## 结构与事实源

```text
AGENTS.md                    跨宿主共享根指令
CLAUDE.md                    @AGENTS.md wrapper
packages/*/AGENTS.md         包级约束
packages/*/CLAUDE.md         包级 wrapper
.agents/skills/              Skills 唯一编辑源
.claude/skills/              生成并提交的 Claude 镜像
tooling/agent_harness/       同步、验证、hooks、确定性 eval 和测试
  evals/v1/cases.json        版本化 adversarial case registry
  lease.py                   common-dir 单写者 lease
.claude/settings.json        Claude 薄适配
.codex/hooks.json            Codex 薄适配
```

`.importlinter` 是依赖边界机器事实源。Pixi tasks、Ruff、basedpyright、pytest 和 CI 执行质量规则；Markdown 只保留路由、风险和不变量。

## Skills

| Skill | 触发范围 |
|---|---|
| `ditto-architecture-change` | 跨包、公共 API、DI、依赖和架构重构 |
| `ditto-api-contract-change` | FastAPI/OpenAPI、兼容性、codegen 与类型化消费者 |
| `ditto-app-dev` | React/Web 行为实现与前端质量门 |
| `ditto-pit-safety` | 查询、窗口、join、因子、回测和时间可见性 |
| `ditto-test-first` | Bug、行为、契约、PIT、风控和交易语义 |
| `ditto-change-review` | 用户 review、PR 前或高风险 diff 审查 |
| `ditto-quality-eval` | 用户明确要求的 backend/web/system 质量评估 |
| `ditto-design-cycle` | 原型与实现之间的设计迭代 |
| `ditto-page-contract` | 页面合同的生成和验证 |
| `ditto-product-arch` | 产品信息架构与跨 feature workflow |
| `ditto-product-discovery` | 产品需求发现与证据整理 |

编辑 `.agents/skills` 后运行：

```bash
pixi run -e dev sync-agent-skills
pixi run -e dev harness-check
```

`sync_skills.py --check` 和 validator 比较完整文件集与字节内容，镜像缺失、额外文件或漂移都会失败。

## Hook 矩阵

| 事件 | 匹配 | 共享策略 |
|---|---|---|
| PreToolUse | Bash/Edit/Write/apply_patch（按宿主能力） | 阻止危险命令，并在结构化写工具执行前检查受保护路径 lease |
| PostToolUse | Edit/Write/apply_patch | 只对能精确解析出的 Python 文件限时运行 Ruff format；不安装环境、不执行 lint fix |
| Stop | 全部 | 快速提示工作区仍有改动；不执行测试、查询工具版本或宣称验证通过 |

同步 hooks 的职责是快速反馈，不是每次回复后的 CI。Codex 与 Claude 的预算一致：
PreToolUse 10 秒；PostToolUse 10 秒（格式化内部 5 秒，超时清理本次进程组）；
Stop 3 秒。格式化使用 `pixi run --as-is -e dev ruff format <files>`，仅消费已准备好的
环境。环境缺失、超时或格式化失败会提供非阻断反馈，不掩盖问题，也不替换已完成工具
的原始结果。命令策略和受保护写入仍在 PreToolUse 阻断。

Stop 不把已有脏文件推断为本任务编辑，不返回 `decision: block` 续跑；遇到
`stop_hook_active=true` 直接结束。它不读取或写入验证收据，因此没有收据不等于失败，
Stop 成功也不等于质量门通过。以下显式命令和根 CI 仍负责验证：

```bash
pixi run -e dev check-changed
```

`check-changed` 按完整 changed set 分级，实时输出正在执行的命令和检查进度：

- 无 staged、unstaged、rename/delete、mode change 或未 ignore 的 untracked：直接通过。
- 普通文档：不运行 Python 套件。
- Harness：运行包含 `harness-check` 的根 `check`。
- 仅测试：目标测试、Ruff format-check/lint、测试类型检查。
- 普通后端/Web 生产代码：分别运行 `check-backend`/`check-web`。
- 契约或跨栈路径：运行 `check` 与 `test-system`。
- data/features/strategy/portfolio/risk/execution/backtest，以及 application 的
  query/process/builder、交易类 command 和对应 backend 入口：额外运行 PIT 专项；
  同时属于 API 契约的路径保留契约、system 与 PIT 三类证据。
- 根 toolchain、未知路径或混合 Harness 变更：fail closed 到只读 `check`。

显式验证失败返回非零退出码，不写成功收据。最终答复必须报告实际执行的检查和失败；
不能以 Stop 没有阻断作为通过证据。普通讨论和只读任务不应因已有改动自动运行全库门禁。

摘要包含 base/HEAD SHA、每个路径的 mode 与内容 hash、未跟踪文件内容，以及相关
tool/config/lockfile 和实际工具版本。成功 receipt 写入当前 worktree 自己的 Git metadata
`<git-dir>/ditto-agent-harness/receipts/`；不同 worktree 不共享 mutable receipt。完全相同
的证据通过显式 `check-changed` 不重复验证，任一字节或工具事实变化都会失效。

hooks 定义或 timeout 修改后，Codex 会要求重新审阅相应定义。代码更新不改写用户的
enabled/trust 状态；不要使用 bypass 参数代替审阅。官方事件语义和设计依据见
[Hooks 最佳实践调研](../research/agent-hooks-best-practices.md)。

## Integrator 单写者 Lease

以下路径只能由当前 integrator worktree 写入：

- `contracts/**` 与 `apps/web/src/api/generated/**`；
- 根 `bun.lock`、`pixi.lock`；
- 非 `docs/**` 的 migration 目录或 `migration_*` 源文件；
- `.redocly.yaml`、`tooling/contracts/**` 和 Web OpenAPI generator script。

共享 lease 与原子 guard 位于 Git common-dir，因此同一仓库的所有 worktree 竞争同一
把锁；owner/task/worktree/lease ID/acquired/expiry 的本地 identity 位于各自 git-dir，
不会在 worktree 间共享。活动 lease 冲突、身份缺失、metadata 损坏或已过期都会
fail closed；格式正确的过期 lease 可由新 integrator 原子回收。TTL 最大四小时。

```bash
pixi run -e dev integrator-lease acquire \
  --owner <agent-id> --task <canonical-task> --ttl-seconds 1800
pixi run -e dev integrator-lease status
pixi run -e dev integrator-lease release
```

持有者应覆盖生成、验证和最终 diff 检查的完整期间，完成后主动 release。PreToolUse
在 Edit/Write/apply_patch 前阻断非持有者，也识别 OpenAPI `--write`、Bun/Pixi lock
更新和直接重定向到受保护文件等已知 Bash writer；任意 shell 语义无法被完全可靠解析，
因此显式 `check-changed` 还会对完整 Git changed set 再做同一 lease 检查。两个宿主
的 matcher 和精确命令同时由 validator 与 deterministic Agent Eval 校验。

## Deterministic Agent Eval

`tooling/agent_harness/evals/v1/cases.json` 是版本化用例事实源，
`tooling.agent_harness.agent_eval` 使用严格 schema 解析并从 changed set、逐层
`AGENTS.md`、实际工具结果、生成物 provenance 与运行 profile 做确定性评分。

v1 至少覆盖：

- 未读取根到近端的完整 `AGENTS.md` 层级；
- 非法 Python/Web import；
- OpenAPI 与 generated types 漂移，以及手工编辑生成物；
- 漏报未跟踪文件；
- 用 mock 证据冒充 live 行为；
- PIT future sentinel 缺失或失败；
- 声称通过但没有成功工具证据的测试；
- changed-scope 验证范围小于 Harness 分类要求。

运行：

```bash
pixi run -e dev agent-eval
```

该任务是 `harness-check` 的强制依赖。用例只接受确定性 fact/receipt；LLM judge
可用于设计质量讨论，但不能决定这些治理门的 pass/fail。registry、grader 或分类规则
变化会进入 receipt fingerprint，使旧验证证据失效；Eval 还独立检查 Claude/Codex
的 PreToolUse 写工具 matcher、命令和 timeout，避免 validator 自身成为单点。

## 维护规则

- 不新增通用 planning/debugging/review/worktree/subagent skill；使用宿主原生能力。
- 新 skill 必须解决 Ditto 特有知识或可复用流程，使用标准 `name`/`description`、正文不超过 120 行，详细资料放一层 `references/`。
- Hook 保持标准库实现和窄策略，不做宽泛 shell 语义判断。
- 自动修复只发生在 PostToolUse 的明确 Python 文件；Stop、`check` 和 `ci` 必须只读。
- `docs/archive`、`docs/plans/archive` 等历史目录不参加活跃 workflow 依赖扫描。

## 验收

```bash
pixi run -e dev harness-check
pixi run -e dev check
pixi run -e dev ci
git diff --check
pixi run -e dev pre-commit-run
```

`harness-check` 同时运行静态 validator、版本化 adversarial Agent Eval、Harness 单测
与类型检查。validator 从 registry 检查 11 个 skills、指令行数、wrapper、镜像一致性、
JSON/TOML/frontmatter、hook 目标、插件集合、遗留目录和非归档 workflow 依赖。

发现验证需分别从仓库根、`apps/web` 和目标 capability package 启动宿主：Claude
`/memory`、`/skills`、`/hooks` 与 Codex `/skills`、`/hooks` 应显示相同共享约束、
registry 中的 11 个 skills 和三类 hooks，且无 AGENTS 32 KiB 截断告警。
