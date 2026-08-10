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
scripts/agent_harness/       同步、验证、hooks 和测试
.claude/settings.json        Claude 薄适配
.codex/hooks.json            Codex 薄适配
```

`.importlinter` 是依赖边界机器事实源。Pixi tasks、Ruff、basedpyright、pytest 和 CI 执行质量规则；Markdown 只保留路由、风险和不变量。

## Skills

| Skill | 触发范围 |
|---|---|
| `ditto-architecture-change` | 跨包、公共 API、DI、依赖和架构重构 |
| `ditto-pit-safety` | 查询、窗口、join、因子、回测和时间可见性 |
| `ditto-test-first` | Bug、行为、契约、PIT、风控和交易语义 |
| `ditto-change-review` | 用户 review、PR 前或高风险 diff 审查 |
| `ditto-quality-eval` | 用户明确要求的全库质量评估 |

编辑 `.agents/skills` 后运行：

```bash
pixi run -e dev sync-agent-skills
pixi run -e dev harness-check
```

`sync_skills.py --check` 和 validator 比较完整文件集与字节内容，镜像缺失、额外文件或漂移都会失败。

## Hook 矩阵

| 事件 | 匹配 | 共享策略 |
|---|---|---|
| PreToolUse | Bash | 阻止 main commit/push、force push、hard reset、`--no-verify`、危险递归删除和绕过 Pixi 的环境修改 |
| PostToolUse | Edit/Write/apply_patch | 只对能精确解析出的 Python 文件运行 file-scoped Ruff fix/format |
| Stop | 全部 | 按 tracked diff 分级运行 changed-scope 验证 |

Stop 分级：

- 无 tracked diff：直接通过。
- 普通文档：不运行 Python 套件。
- Harness：运行 `harness-check`。
- 仅测试：目标测试、Ruff format-check/lint、测试类型检查。
- 生产 Python、依赖、架构、配置或 CI：运行只读 `check`。

首次失败返回阻断反馈。若宿主以 `stop_hook_active=true` 再次调用且仍失败，允许结束，但向模型注入必须在最终答复报告失败的消息。

成功结果按 `git diff --binary HEAD` 的 SHA-256 缓存在 `.cache/ditto-agent-harness/`。完全相同的 tracked diff 不重复验证；任何字节变化都会产生新摘要。

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

静态 validator 检查指令行数、wrapper、5 个 skills、镜像一致性、JSON/TOML/frontmatter、hook 目标、插件集合、遗留目录和非归档 workflow 依赖。

发现验证需分别从仓库根和 `packages/data` 启动宿主：Claude `/memory`、`/skills`、`/hooks` 与 Codex `/skills`、`/hooks` 应显示相同共享约束、5 个 skills 和三类 hooks，且无 AGENTS 32 KiB 截断告警。
