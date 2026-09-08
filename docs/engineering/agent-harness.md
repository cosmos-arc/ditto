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

`.importlinter` 是依赖边界机器事实源。Task tasks、Ruff、basedpyright、pytest 和 CI 执行质量规则；Markdown 只保留路由、风险和不变量。

## Skills

项目只保留 `ditto-pit-safety`，承载时间可见性与未来哨兵知识。API 兼容规则见
[OpenAPI 文档](../../contracts/openapi/README.md)，架构和测试规则由根 AGENTS 路由；
产品、设计和页面合同由 [Web AGENTS](../../apps/web/AGENTS.md) 按任务路由。
Web 工具位于 `apps/web/scripts/{page-contract,prototype,visual-audit}`，与 Bun 依赖一起运行。

编辑 `.agents/skills` 后运行：

```bash
task sync-agent-skills
task harness-check
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
Stop 3 秒。格式化使用 已准备 `.venv` 中的 `ruff format <files>`，仅消费已准备好的
环境。环境缺失、超时或格式化失败会提供非阻断反馈，不掩盖问题，也不替换已完成工具
的原始结果。命令策略和受保护写入仍在 PreToolUse 阻断。

Stop 不把已有脏文件推断为本任务编辑，不返回 `decision: block` 续跑；遇到
`stop_hook_active=true` 直接结束。它不读取或写入验证收据，因此没有收据不等于失败，
Stop 成功也不等于质量门通过。以下显式命令和根 CI 仍负责验证：

```bash
task check-changed
```

`check-changed` 按完整 changed set 分级，实时输出正在执行的命令和检查进度：

- 无 staged、unstaged、rename/delete、mode change 或未 ignore 的 untracked：直接通过。
- 普通文档：不运行 Python 套件。
- Harness：运行包含 `harness-check` 的根 `check`。
- 仅测试：目标测试、Ruff format-check/lint、测试类型检查。
- 普通后端/Web 生产代码：分别运行所属包测试与静态检查/`check-web`；跨包或高风险变更运行 `check`。
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
- 根 `bun.lock`、`uv.lock`；
- 非 `docs/**` 的 migration 目录或 `migration_*` 源文件；
- `.redocly.yaml`、`tooling/contracts/**` 和 Web OpenAPI generator script。

共享 lease 与原子 guard 位于 Git common-dir，因此同一仓库的所有 worktree 竞争同一
把锁；owner/task/worktree/lease ID/acquired/expiry 的本地 identity 位于各自 git-dir，
不会在 worktree 间共享。活动 lease 冲突、身份缺失、metadata 损坏或已过期都会
fail closed；格式正确的过期 lease 可由新 integrator 原子回收。TTL 最大四小时。

```bash
task integrator-lease -- acquire \
  --owner <agent-id> --task <canonical-task> --ttl-seconds 1800
task integrator-lease -- status
task integrator-lease -- release
```

持有者应覆盖生成、验证和最终 diff 检查的完整期间，完成后主动 release。PreToolUse
在 Edit/Write/apply_patch 前阻断非持有者，也识别 OpenAPI `--write`、Bun/uv lock
更新和直接重定向到受保护文件等已知 Bash writer；任意 shell 语义无法被完全可靠解析，
因此显式 `check-changed` 还会对完整 Git changed set 再做同一 lease 检查。validator 检查两个宿主必要事件的 matcher 覆盖与共享命令；允许合法附加配置。

## Policy 回归

`tooling/agent_harness/evals/v1/cases.json` 的预填 attempt/expected 是普通 policy/grader
测试数据，由 `harness-test` 执行。它覆盖漏报 changed set、非法依赖、契约漂移、
伪造 live 证据、PIT 哨兵缺失及验证范围不足等反例，不代表模型实测能力。
不再作为独立门重复执行；真实 agent 效果应以实际任务结果和工具日志判断。

## 本地与 CI 的验证分工

普通提交只检查 staged 文件，Ruff 不展开到全库；部分暂存由 pre-commit 的 stash
机制保护。重检查由显式 `check-changed` 和 CI 承担。
普通 Markdown/RST（包含近端 AGENTS）走文档范围；可执行文件、符号链接、模式变化、
schema、脚本和配置仍保守分类。页面设计源 `apps/web/DESIGN.md` 保留生成物检查。
`web-manifest-check` 作为明确要求的文档 freshness 审计保留，不阻断普通 UI 修改。

PR 复用 changed-scope 选择检查；根配置、共享工具和未知范围选择完整检查。
主分支、merge queue 和定期 CI 执行全套类型、行为、边界、平台、安全与制品验证。
关键 mutation 在每周安全流程执行；发布仍要求对应提交完整 CI 与 cohort 验证。
稳定 CI gate 始终运行，显式区分不适用与失败导致的跳过，缺失结果不会通过。

## 维护规则

- 不新增通用 planning/debugging/review/worktree/subagent skill；使用宿主原生能力。
- 新 skill 必须解决 Ditto 特有知识或可复用流程，保留标准 `name`/`description`；可选 metadata 与正文长度不设仓库私有格式门。
- Hook 保持标准库实现和窄策略，不做宽泛 shell 语义判断。
- 自动修复只发生在 PostToolUse 的明确 Python 文件；Stop、`check` 和 `ci` 必须只读。
- `docs/archive`、`docs/plans/archive` 等历史目录不参加活跃 workflow 依赖扫描。

## 验收

```bash
task harness-check
task check
task ci
git diff --check
task pre-commit-run
```

`harness-check` 执行 validator、policy/Harness 回归、开发/契约/质量工具测试和类型检查。
validator 检查可发现 skill 与 registry、完整镜像、wrapper 和必要 hook 覆盖，
不锁死 skill 数量、插件集合或合法 hook 组合。

从仓库根、`apps/web` 和目标 capability package 检查宿主发现：项目只应出现 PIT skill，
用户全局技能和本地 hook trust 不由仓库脚本修改。宿主实际发现与 CLI 验证分别报告。

### 推送范围验证

pre-push 使用 pre-commit 提供的提交范围选择检查，覆盖已提交且工作区干净的变更；不以未提交差异代替推送范围。待推送提交必须是当前 HEAD，工作区必须干净，缺少基线历史时执行 `task check`。纯 Web 推送和文件删除同样进入范围选择。
