# Agent Harness

Ditto App 只维护一套项目事实与技能，同时适配 Claude Code 和 Codex。`AGENTS.md` 是共享常驻指令；`CLAUDE.md` 只导入它。`.agents/skills/` 是技能唯一编辑源，`.claude/skills/` 是提交到仓库的生成镜像。

## 组成

| 位置 | 职责 |
|---|---|
| `AGENTS.md` | 项目地图、风险、验证和审批边界 |
| `.agents/skills/` | 5 个项目特有工作流与 references |
| `.claude/skills/` | Claude 镜像，不直接编辑 |
| `scripts/agent_harness/hook.mjs` | 两个宿主共享的命令保护、文件格式化和 Stop 门禁 |
| `.claude/settings.json` | Claude Code 薄适配 |
| `.codex/hooks.json` | Codex 薄适配 |
| `scripts/agent_harness/validate.mjs` | 静态 harness 合同 |

## Skills

- `ditto-product-discovery`：从模糊产品方向形成可验证的 brief、假设和研究输入。
- `ditto-product-arch`：维护 IA、页面蓝图、流程、状态与产品架构事实。
- `ditto-design-cycle`：创建、评审和迭代 HTML prototype。
- `ditto-page-contract`：创建、验证、提升和同步页面合同。
- `ditto-app-dev`：合同驱动的 React 实现、交互与视觉验证。

通用 planning、debugging、review、worktree 和多代理编排由宿主提供，不在项目里重复封装。新增 skill 必须同时满足：知识是 Ditto App 特有、跨任务复用、不能由一条命令或常驻指令更清楚地表达。

## Hook 矩阵

| 事件 | 行为 |
|---|---|
| `PreToolUse/Bash` | 阻止 main 上 commit/push、force push、hard reset、`--no-verify`、危险递归删除和非 Bun 依赖修改 |
| `PostToolUse/Edit/Write/apply_patch` | 只对可靠提取出的已修改前端文件运行 file-scoped Biome fix |
| `Stop` | 按 docs、tests、styles、harness、source 分类运行最低无副作用门禁；相同 diff 使用 receipt 去重 |

Stop 首次失败会要求修复；宿主的二次 Stop 仍失败时允许结束，但必须在最终答复明确报告。receipt 位于 `.cache/ditto-agent-harness/`，不提交。

## 维护

1. 只编辑 `.agents/skills/`。
2. 运行 `bun run harness:sync` 生成 Claude 镜像。
3. 运行 `bun run harness:check` 校验名称、frontmatter、宿主配置、镜像与测试。
4. 提交源与镜像；CI 使用 `harness:sync:check` 防止漂移。

`agents/openai.yaml` 是 Codex/UI 元数据。`SKILL.md` frontmatter 只保留 `name` 和 `description`，正文保持快速路由，长规则只放一层 references。

## 发现检查

- Claude Code：根目录确认 `/memory` 只导入 `CLAUDE.md → AGENTS.md`，`/skills` 显示 5 项，`/hooks` 显示三类 hook。
- Codex：根目录确认 `/skills` 显示同样 5 项，hook 配置加载且无 AGENTS 截断警告。
- 两边各从根目录和 `src/features/` 启动一次，确认共享事实一致。

本检查不执行真实模型 A/B，也不把静态验收解释为行为质量证明。
