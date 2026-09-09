# 业界 AI Coding（AI 辅助软件工程 / Agentic Coding）最佳实践调研

- 调研日期：2026-09-08
- 调研方法：WebSearch + 官方页面全文抓取（agents.md、Anthropic 工程博客、Claude Code 官方文档、Cursor 官方文档、OpenAI Codex 官方文档、OpenAI 工程博客、GitHub Spec Kit、AWS Kiro、DORA、METR、Martin Fowler / Matt Pocock）。所有 URL 均为本次调研实际抓取或搜索确认的链接。
- 来源类型标注：【规范】开放规范原文 /【官方文档】厂商官方文档 /【官方博客】厂商官方工程博客 /【官方开源】官方开源项目 /【社区】社区权威（个人/咨询）/【研究】研究机构。

---

## 1. Agent 指南文件约定（AGENTS.md / CLAUDE.md / .cursor/rules）

### 要点

1. **AGENTS.md 已成为跨工具事实标准**。agents.md 开放规范将其定位为「给 agent 看的 README」，被 60,000+ 开源项目采用；由 OpenAI Codex、Amp、Jules、Cursor、Factory 协作产生，现由 Agentic AI Foundation（Linux Foundation）管理。格式为纯 Markdown，零必填字段、零 schema，兼容所有主流 agent（Codex、Gemini CLI、Cursor、Copilot coding agent、Junie、Aider、Warp、Devin、VS Code 等）。OpenAI 主仓库自己维护了 88 个 AGENTS.md 文件。【规范】[agents.md](https://agents.md/)
2. **建议章节有事实共识**：项目概览、构建/测试命令、代码风格、测试说明、安全考虑。Codex 官方示例的分层内容：全局层写工作约定（改 JS 后跑 `npm test`、偏好 `pnpm`、新增生产依赖需确认），repo root 写仓库约定（PR 前跑 lint、公共工具写文档进 `docs/`），子目录写局部覆盖（如 `make test-payments` 代替 `npm test`）。【官方文档】[Codex: Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
3. **层级化与优先级**：monorepo 用嵌套 AGENTS.md；Codex 从 repo root 向下逐级拼接（以空行连接），**越靠近当前目录的文件优先级越高**（出现在合并提示末尾）；每个目录最多取一个文件，优先级 `AGENTS.override.md` > `AGENTS.md` > 配置的 fallback 文件名；搜索止于当前工作目录。【官方文档】[Codex: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、【规范】[agents.md](https://agents.md/)
4. **长度控制有硬约束**：Codex 合并总量默认上限 **32 KiB**（`project_doc_max_bytes`），超限截断，官方建议的解法是拆分到嵌套目录而非调大限制；Claude Code 官方建议 CLAUDE.md 每文件 **< 200 行**（>4 MiB 整体跳过）；Cursor 官方建议规则 **< 500 行**，超长拆为多条可组合规则。【官方文档】[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Claude Code memory](https://code.claude.com/docs/en/memory)、[Cursor rules](https://cursor.com/docs/rules)
5. **AGENTS.md 与 CLAUDE.md 的互通做法**：Claude Code 只读 CLAUDE.md；官方建议在 CLAUDE.md 顶部写 `@AGENTS.md` 导入，或 `ln -s AGENTS.md CLAUDE.md` 建软链；`/init` 可吸收 Cursor/Copilot 规则（`CLAUDE_CODE_NEW_INIT=1` 时也读 AGENTS.md/Windsurf/Devin/Cline 规则）。Cursor 官方同样推荐「`.mdc` 规则 + AGENTS.md」并存，Cursor 会读取 AGENTS.md 并建议迁移到 .cursor/rules。【官方文档】[Claude Code memory](https://code.claude.com/docs/en/memory)、[Cursor rules](https://cursor.com/docs/rules)
6. **应该写什么 / 不该写什么**（多方共识）：写人类可读、简短、常用的可执行命令、代码风格、验证方式；Anthropic 强调避免过度指定（over-specified）与过时指令（侵蚀信任），用 `IMPORTANT` 前缀强调关键规则；Cursor 强调避免模糊指导、给出具体示例文件；Codex 官方建议代码审查规则放进离被管代码最近的 AGENTS.md，格式化/lint 检查交给 CI 而不是塞进指令文件。【官方博客】[Claude Code best practices](https://code.claude.com/docs/en/best-practices)、【官方文档】[Cursor rules](https://cursor.com/docs/rules)、[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
7. **.cursor/rules 的结构约定**：`.cursor/rules/*.mdc`，YAML frontmatter 含 `description`、`globs`、`always_apply`；绑定方式五种：Always on / Auto attached（按 glob 触发）/ Agent requested（按 description 由 agent 决定）/ Manual / Never；扁平命名或嵌套目录均可。【官方文档】[Cursor rules](https://cursor.com/docs/rules)
8. **活文档原则**：agents.md 官方明确「AGENTS.md 是活文档，可随时更新，agent 每次运行重新读取」；Codex 文档确认指令每次运行重建、无缓存。【规范】[agents.md](https://agents.md/)

### 来源清单

| URL | 类型 |
|---|---|
| https://agents.md/ | 规范（开放规范官网） |
| https://learn.chatgpt.com/docs/agent-configuration/agents-md | 官方文档（OpenAI Codex） |
| https://cursor.com/docs/rules | 官方文档（Cursor） |
| https://code.claude.com/docs/en/memory | 官方文档（Claude Code） |
| https://code.claude.com/docs/en/best-practices（canonical，原 anthropic.com/engineering/claude-code-best-practices） | 官方博客/文档（Anthropic） |

---

## 2. 上下文工程（Context Engineering）

### 要点

1. **上下文是有限资源，存在「注意力预算」**：系统提示、工具定义、对话历史共享同一预算；三条红线——上下文耗尽（截断损失信息）、注意力稀释（无关 token 淹没关键指令）、工具定义过大。官方结论：上下文窗口内「每一 token 都有沉没成本」，低价值信息的机会成本极高。【官方博客】[Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
2. **上下文工程 ≠ 提示工程**：定义为「构建为 LLM 输出提供正确信息的正确系统」的动态学科，而非静态提示编写；核心是 **right-sized information**——追求刚好够用的信息而非最多信息。【官方博客】[Anthropic: effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
3. **四大系统级策略**（Anthropic 官方框架）：compaction（压缩对话保留关键信息）、structured note-taking（memory 结构化笔记）、sub-agent architectures（子代理隔离上下文）、just-in-time retrieval（按需检索取代常驻 RAG——工具返回摘要+文件路径而非全文）。【官方博客】[effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
4. **Claude Code 官方操作准则**：把上下文窗口当作最重要资源管理；`/clear` 优于 `/compact`（压缩丢失细节）；缩小工作单元；警惕「上下文底部」遗忘（长会话中早期计划/文件被遗忘，需重述关键上下文）；CLAUDE.md 内容在 auto-compaction 后保留。【官方博客/文档】[Claude Code best practices](https://code.claude.com/docs/en/best-practices)
5. **渐进式披露（progressive disclosure）是核心落地模式**：按需加载——skills（name/description 常驻、正文激活时加载）、嵌套 AGENTS.md（子目录按需）、Claude Code 路径作用域规则（`.claude/rules/` frontmatter `paths:` glob，仅在 Claude 触及相关文件时加载）。【官方文档】[Claude Code skills](https://code.claude.com/docs/en/skills)、[memory/rules](https://code.claude.com/docs/en/memory)
6. **导入的代价要显式认知**：`@path` 导入便于组织但不减少上下文占用（全部在启动时加载），递归最多 4 跳；`claudeMdExcludes` 可剔除无关文件。导入是组织手段不是省 token 手段。【官方文档】[Claude Code memory](https://code.claude.com/docs/en/memory)
7. **从简单开始、以数据驱动加复杂度**：Anthropic 明确建议从简单系统起步，仅在学到真实信号后逐步升级（简单 RAG → agentic search → 多 agent），反对一开始堆架构。【官方博客】[effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### 来源清单

| URL | 类型 |
|---|---|
| https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | 官方博客（Anthropic，2025-09-29） |
| https://code.claude.com/docs/en/best-practices | 官方文档/博客（Claude Code） |
| https://code.claude.com/docs/en/memory | 官方文档（Claude Code） |
| https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools | 官方教程（Claude Cookbook：memory/compaction/tool clearing 实操） |

---

## 3. Skills / 可复用能力包

### 要点

1. **Agent Skills 已是开放标准**（agentskills.io，Anthropic 2025-12-18 官宣开放，Microsoft Agent Framework 等采纳）：skill = 目录 + `SKILL.md`；必填 frontmatter 仅 `name`（≤64 字符、小写字母数字连字符、须匹配目录名、不得连续连字符）与 `description`（≤1024 字符、必须同时写「做什么 + 何时用」并含触发关键词）；可选 `license`、`compatibility`（≤500 字符）、`metadata`、`allowed-tools`（实验性）。【规范】[Agent Skills Specification](https://agentskills.io/specification)
2. **三级渐进披露是规范核心**：metadata（name+description，约 100 tokens，启动时常驻）→ SKILL.md 正文（激活时加载，建议 <5,000 tokens）→ 附加资源（`scripts/`、`references/`、`assets/` 按需加载；脚本被执行而非读入上下文）。SKILL.md 保持 **<500 行**，详细参考材料拆到独立文件，文件引用保持一层深度。【规范】[agentskills.io/specification](https://agentskills.io/specification)、【官方博客】[Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
3. **Claude Code 实现细节**：位置层级 enterprise > `~/.claude/skills`（个人）> `.claude/skills`（项目）> plugin（`plugin:skill` 命名空间）；skill 列表预算为**上下文窗口的 1%**（超出从最少调用的 skill 开始丢弃 description）；`description`+`when_to_use` 合计 ≤1,536 字符；compaction 后重挂最近一次调用（每 skill 前 5,000 tokens、共享 25,000 tokens 预算）。【官方文档】[Claude Code skills](https://code.claude.com/docs/en/skills)
4. **调用控制矩阵**：`disable-model-invocation: true` = 仅人工 `/` 调用（用于部署、提交等副作用工作流，同时阻止子代理预加载）；`user-invocable: false` = 仅模型可调用（纯背景知识）；`context: fork` + `agent` = 在隔离子代理中运行（重任务不污染主上下文）。【官方文档】[Claude Code skills](https://code.claude.com/docs/en/skills)
5. **Anthropic 官方 skill 开发方法论**（工程博客四步）：start with evals（先跑代表性任务找差距）、为规模而结构化（>500 行拆文件）、从 Claude 视角思考（优化 name/description 的触发质量）、与 Claude 迭代（让它把成功方法与常见错误写回 SKILL.md）。【官方博客】[Equipping agents with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
6. **与 CLAUDE.md 的官方分工**：始终需要的事实/上下文 → CLAUDE.md；按需加载的程序/参考 → skills；判断信号是「CLAUDE.md 的章节长成了流程而非事实」就该迁出为 skill；自定义命令（`.claude/commands`）已并入 skills 体系。【官方文档】[Claude Code skills](https://code.claude.com/docs/en/skills)
7. **脚本即确定性接口**：把精确操作（解析、转换、生成）写成 skill 自带脚本，模型只负责编排，不把脚本内容或大二进制读进上下文；`allowed-tools` 与正文同用 `${CLAUDE_SKILL_DIR}` 变量可让内置脚本免权限提示执行。【官方博客】[Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)、【官方文档】[skills](https://code.claude.com/docs/en/skills)
8. **安全与生态**：只从可信来源安装 skill、审计 bundled 脚本与外部网络指令（Anthropic 官方安全建议）；`skills-ref validate` 校验规范符合性；skill-creator 插件支持隔离评估（evals.json / 盲测 A/B 对比）。【官方博客】[Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

### 来源清单

| URL | 类型 |
|---|---|
| https://agentskills.io/specification | 规范（Agent Skills 开放标准） |
| https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | 官方博客（Anthropic） |
| https://code.claude.com/docs/en/skills | 官方文档（Claude Code） |
| https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview | 官方文档（Claude 平台） |
| https://learn.microsoft.com/en-us/agent-framework/agents/skills | 官方文档（Microsoft，采纳该规范） |

---

## 4. Hooks / 质量门

### 要点

1. **Hooks 是确定性的强制层，与「上下文型」机制分责明确**：Claude Code 官方明确 CLAUDE.md / memory 是上下文不是强制配置——「保证阻止必须用 PreToolUse hooks」；Anthropic 建议确定性动作用 hooks，非确定性判断用 guardrail MCP server 或 subagent。【官方文档】[Hooks reference](https://code.claude.com/docs/en/hooks)、[memory](https://code.claude.com/docs/en/memory)
2. **决策优先级与并发规则**：单 hook 输出决策优先级 `deny > ask > allow`；跨多个并发 PreToolUse hook 取最强决策（deny 优先于 ask 优先于 allow）；PreToolUse 并发上限 2、异步 PostToolUse 上限 10。【官方文档】[Hooks reference](https://code.claude.com/docs/en/hooks)
3. **退出码语义即质量门接口**：exit 2 = blocking error（stderr 反馈给 Claude 修正，PreToolUse 下阻止工具执行）；exit 0 = 成功；其他 = 非阻塞错误（stderr 仅用户可见）。这是「lint 失败反馈给 agent 自修复」的机制基础。【官方文档】[Hooks reference](https://code.claude.com/docs/en/hooks)
4. **PreToolUse deny 保护不可逆操作**：官方示例包括保护不该修改的文件（阻止对生产配置的 Edit）、阻止危险 git 命令、正则扫描 diff 后阻止包含秘密的 `Bash(git commit *)`——即「防秘密提交」是官方一等用例。【官方文档】[Hooks reference](https://code.claude.com/docs/en/hooks)
5. **PostToolUse additionalContext 实现 lint/format 强制**：Edit 后 hook 自动运行 lint/typecheck，将错误作为 additionalContext 反馈，Claude 在下一次调用自动修复——Anthropic best practices 明确列举此模式（lint 错误自动进上下文）。【官方文档】[Hooks](https://code.claude.com/docs/en/hooks)、[best practices](https://code.claude.com/docs/en/best-practices)
6. **Stop hook 实现验证循环**：拒绝模型「我已完成」的声明（exit 2 + 原因），直到测试全部通过——官方推荐用于强制 agent 用测试验证自己的工作，堵住「编造成功声明」。【官方文档/博客】[best practices](https://code.claude.com/docs/en/best-practices)、[hooks](https://code.claude.com/docs/en/hooks)
7. **工程化配置约定**：hooks 在 settings.json 按 matcher + 事件声明；脚本用 `$CLAUDE_PROJECT_DIR` 定位仓库内路径；官方建议 hook 文档放 `/docs/hooks` 索引、命令进 README；给 hooks 的 Bash 权限必须是精确整条命令字符串（非前缀通配）。【官方文档】[hooks](https://code.claude.com/docs/en/hooks)、[best practices](https://code.claude.com/docs/en/best-practices)

### 来源清单

| URL | 类型 |
|---|---|
| https://code.claude.com/docs/en/hooks | 官方文档（Claude Code hooks 参考） |
| https://code.claude.com/docs/en/best-practices | 官方博客/文档（Anthropic） |

---

## 5. 验证与工作流（spec-driven、plan/TDD、代码审查）

### 要点

1. **「给 agent 验证手段」是官方第一原则**：提供测试、build 脚本、linter 等可独立验证的工具，否则 agent 会对完成状态产生幻觉；用 Stop hooks 或验证 subagent 评估「任务真正完成」；把失败的 CI 运行、PR review 意见反复粘贴回会话迭代。**外部验证**（独立 subagent 检查输出）仅建议用于高风险任务。【官方博客】[Claude Code best practices](https://code.claude.com/docs/en/best-practices)
2. **官方工作流四段式**：先探索（子代理/explore 命令）→ 计划（plan mode，只读权限）→ 实现 → 提交（commit message 由 Claude 按 git log 与 diff 总结）。【官方博客】[best practices](https://code.claude.com/docs/en/best-practices)
3. **Spec-Driven Development 已工具化**：GitHub Spec Kit（官方开源，约 134k star，1.0 已发布）流程为 constitution（治理原则）→ specify（写 what/why）→ clarify（消歧）→ plan（技术方案）→ tasks → implement → converge（对照 spec 收敛，循环到 Converged）；checklist 被称为「unit tests for English」；支持 30+ agent（含 Codex skills 模式）。【官方开源】[github/spec-kit](https://github.com/github/spec-kit)
4. **Kiro（AWS）三工件模式**：每个 spec 生成 `requirements.md`（用户故事+验收标准）/ `design.md`（架构、时序图、测试策略）/ `tasks.md`（可跟踪任务）；任务执行做依赖分析成 waves，波间串行、波内并行；另有 vagueness 检测（Analyze Requirements）与 bugfix spec（根因+回归防护）。【官方文档】[Kiro Specs](https://kiro.dev/docs/specs/)
5. **社区权威的批判性框架**（Martin Fowler 站，Thoughtworks Birgitta Böckeler）：SDD 分三级 spec-first / spec-anchored / spec-as-source；明确警告——重流程对小任务是「大锤砸核桃」、冗长 markdown 造成 review 负担、大前置 spec 与「小步迭代验证」的既有控制机制相悖（虚假控制感：agent 仍会无视或过度套用指令）；人类角色核心是 **verify**。【社区】[Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)
6. **Matt Pocock 的流水线实践**（一手）：`/grill-me`（逼问需求，一次 16-50 个问题）→ `/to-spec`（对话转 spec）→ `/to-tickets`（垂直切片 tracer-bullet 票，建立阻塞关系支持并行 agent）→ `/tdd`（红绿重构）；核心论断：**「做真正的 TDD 是提升 agent 输出质量最一致的方式」**；批评 plan mode「理解尚未对齐就过早产出计划文档」；「垃圾代码库进、垃圾代码出」，大模块+薄接口对 agent 更友好。【社区】[5 Agent Skills I Use Every Day](https://www.aihero.dev/5-agent-skills-i-use-every-day)
7. **AI 在代码审查中的角色**：Claude Code 用只读 reviewer subagent（`tools: Read, Glob, Grep`）+ writer/reviewer 双 session 模式；Codex 官方建议在 AGENTS.md 写 `## Code Review Rules` 章节且规则靠近被管代码、格式化交给 CI；Anthropic 建议 CI 检查 agent 工作（failed CI 反馈贴回会话）。【官方文档】[sub-agents](https://code.claude.com/docs/en/sub-agents)、[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[best practices](https://code.claude.com/docs/en/best-practices)

### 来源清单

| URL | 类型 |
|---|---|
| https://code.claude.com/docs/en/best-practices | 官方博客/文档（Anthropic） |
| https://github.com/github/spec-kit | 官方开源（GitHub） |
| https://kiro.dev/docs/specs/ | 官方文档（AWS Kiro） |
| https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html | 社区（Martin Fowler / Thoughtworks，2025-10-15） |
| https://www.aihero.dev/5-agent-skills-i-use-every-day | 社区（Matt Pocock 一手） |

---

## 6. 多 agent / 后台 agent、Subagents 编排、Handoff 与跨会话记忆

### 要点

1. **编排模式 = orchestrator-worker（lead agent 规划 + 并行 subagent 执行）**：lead 把计划写入 Memory（上下文 200k token 会截断），spawn 并行 subagent，各自独立上下文窗口搜索并压缩结论；subagent 把产出写文件系统/artifact store、返回轻量引用而非全量对话转发（减少「传话游戏」）。多 agent 系统在内部研究评估上比单 agent 高 90.2%（广度优先任务优势最大），并行 tool call 使研究时间最多降 90%。【官方博客】[How we built our multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
2. **成本边界要显式**：token 使用解释 BrowseComp 80% 的性能方差（模型/工具调用次数是其余因素）；agent 耗 token 约 chat 的 4 倍、多 agent 约 15 倍——适合高价值、强可并行任务（研究/审查），**不适合普通编码**（独立子任务少）。选型时先问任务是否可分解、各分支是否需要独立上下文。【官方博客】[multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
3. **委派必须显式且按复杂度缩放**：每个 subagent 任务描述需含目标、输出格式、工具/来源指引、边界（模糊委派导致重复/跑偏）；官方量化：事实查找 1 agent（3-10 次工具调用）、对比研究 2-4 个、复杂研究 10+；工具描述质量直接决定 agent 行为（优化工具描述曾降低 40% 任务耗时）。【官方博客】[multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
4. **Claude Code subagents 工程细节**：`.claude/agents/*.md` 定义（frontmatter：name/description/tools/model/permissionMode/memory/isolation: worktree/maxTurns 等）；上下文隔离（看不到对话历史，仅返回摘要给主会话）；默认并发 20、嵌套 3 层；内置只读 Explore/Plan agent 做探查防污染主上下文；completed agent 保留 agent ID，可 SendMessage 续聊（带完整历史）；`isolation: worktree` 给临时 git worktree。【官方文档】[sub-agents](https://code.claude.com/docs/en/sub-agents)
5. **并行开发模式**：git worktrees 支持多 Claude session 并行不同 feature；writer/reviewer 分离（一个写码一个审查）；fan-out 模式（每 task 一个独立干净 session 后聚合）；后台 agent 有精简工具集。【官方博客】[best practices](https://code.claude.com/docs/en/best-practices)
6. **跨会话记忆双轨制**：CLAUDE.md（人写的常驻指令）+ auto memory（Claude 自动记录用户纠正/偏好，`MEMORY.md` 索引前 200 行 / 25KB 启动加载、topic 文件按需读、四类 frontmatter `type: user/feedback/project/reference`；按 git repo 定位，worktree 共享）；handoff 用 `/handoff` 文件、`--resume <sessionId>`、session-transcripts 落盘输出供下一个 session 接手。【官方文档】[memory](https://code.claude.com/docs/en/memory)、[best practices](https://code.claude.com/docs/en/best-practices)
7. **会话内压缩**：`/compact`（含 auto-compaction）摘要保留关键信息；`/clear` 彻底清空（上下文工程角度更优）；rewind/checkpoints 回滚；根 CLAUDE.md 在 compact 后保留。【官方文档】[best practices](https://code.claude.com/docs/en/best-practices)
8. **多 agent 评估方法**：从约 20 个真实查询起步即可驱动早期改进（30%→80% 成功率）；LLM-as-judge + rubric（事实准确、引用准确、完整性、来源质量、工具效率）与人类评分对齐最好；状态变更型 agent 评估**最终状态**而非逐步路径；生产化需要可恢复 checkpoint 与全量 tracing。【官方博客】[multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)

### 来源清单

| URL | 类型 |
|---|---|
| https://www.anthropic.com/engineering/built-multi-agent-research-system | 官方博客（Anthropic，2025-06-13） |
| https://code.claude.com/docs/en/sub-agents | 官方文档（Claude Code） |
| https://code.claude.com/docs/en/memory | 官方文档（Claude Code） |
| https://code.claude.com/docs/en/best-practices | 官方博客/文档（Anthropic） |

---

## 7. 安全与授权边界（权限模型、沙箱、secrets）

### 要点

1. **权限模式分层 + 自动审批分类器**：Claude Code 六种 permission mode（Manual / acceptEdits / plan / default / auto / dontAsk+bypassPermissions）；auto mode 由分类器实时评估每个命令安全性，可设 always allow / always deny 学习精确命令（官方建议只加完整精确命令字符串，绝不加前缀通配）；plan mode 限只读。【官方文档】[permission modes](https://code.claude.com/docs/en/permission-modes)、[best practices](https://code.claude.com/docs/en/best-practices)
2. **沙箱与审批职责分离（Codex 官方定义）**：「sandbox 定义技术边界，approval policy 决定 agent 何时停下询问」——沙箱减少审批疲劳。Codex 三档沙箱 `read-only` / `workspace-write` / `danger-full-access` × 审批策略 `untrusted` / `on-request` / `never`；低风险自动化推荐 `workspace-write + on-request`；全访问仅限 `danger-full-access + never` 显式组合。【官方文档】[Codex: Sandbox](https://learn.chatgpt.com/docs/sandboxing)
3. **OS 级沙箱执行**：Claude Code 用 macOS Seatbelt / Linux bubblewrap + socat 代理；默认可写仅工作目录 + 会话 temp（+ 显式 additionalDirectories），默认可读全盘（官方提醒必须显式 deny `~/.aws/credentials`、`~/.ssh`）；网络出站全部经沙箱外代理 allowlist（**无预放行域名**，首次使用询问）；受保护路径（`.claude` 配置/hooks/skills、`.mcp.json`、`.git/hooks` 等）永不可写，防 agent 自我提权；可选 strict sandbox / fail-closed（`sandbox.failIfUnavailable: true` 作安全门）。【官方文档】[Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing)
4. **凭证/secrets 保护有专用机制**：`sandbox.credentials` 支持 `deny`（文件不可读/环境变量置空）与 `mask`（沙箱内只见哨兵值，代理对 allowlist 主机注入真值；支持 AWS SigV4 代理重签名、JWT claim 掩码、extract 正则）；deny 规则跨 settings 层合并且只能收窄。【官方文档】[sandboxing](https://code.claude.com/docs/en/sandboxing)
5. **OpenAI 沙箱工程教训（一手）**：当 agent 以用户完整身份运行时，「网络抑制是最关键的单一安全措施」（网络边界是分层防御中影响最大的）；沙箱设计教训——初次实现求快，长期安全靠**小而可验证的边界**（可审计的实际机制优于纸面原则）；凭证范围最小化（Windows DPAPI 按 user+device 加密）；网络边界逐进程防火墙规则，规划未来按命令/域名精细化。【官方博客】[Building a safe, effective sandbox to enable Codex on Windows](https://openai.com/index/building-codex-windows-sandbox/)
6. **最小权限操作惯例**：Anthropic 建议精确 allowlist + 用 sandboxing 替代逐条放行命令；Codex 建议用 `writable_roots` 扩展可写目录而非撤沙箱、审批 scope 取最窄（单次 vs 会话）、用独立 project/worktree 隔离而非放宽全局权限。【官方文档】[sandboxing（Claude Code）](https://code.claude.com/docs/en/sandboxing)、[sandboxing（Codex）](https://learn.chatgpt.com/docs/sandboxing)
7. **危险操作需人工授权已成惯例**：Codex 官方 AGENTS.md 示例将「新增生产依赖需确认」「轮换 API key 需通知安全频道」写进全局指令——与「生产/真实数据写入、不可逆删除、CI/发布配置变更需显式授权」的通行做法一致（本项目 AGENTS.md 的授权清单即此模式）。【官方文档】[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
8. **Prompt injection 与供应链防御**：Claude Code 对 subagent 输出扫描 instruction-shaped text（标记行、反斜杠插入）作为注入防御；Skills 生态只从可信来源安装、审计 bundled 脚本与外部网络指令；MCP server 显式审批。【官方文档】[sub-agents](https://code.claude.com/docs/en/sub-agents)、【官方博客】[Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

### 来源清单

| URL | 类型 |
|---|---|
| https://code.claude.com/docs/en/permission-modes | 官方文档（Claude Code） |
| https://code.claude.com/docs/en/sandboxing | 官方文档（Claude Code） |
| https://learn.chatgpt.com/docs/sandboxing | 官方文档（OpenAI Codex） |
| https://openai.com/index/building-codex-windows-sandbox/ | 官方博客（OpenAI，2026-08-26） |
| https://code.claude.com/docs/en/best-practices | 官方博客/文档（Anthropic） |

---

## 8. 度量：AI coding 成熟度评估

### 要点

1. **无单一公认的「AI coding 成熟度」框架**；事实基准仍是 DORA（Google Cloud 研究项目）四指标——部署频率、变更前置时间、变更失败率、故障恢复时间——叠加 AI 采纳度扩展；团队效能领域并存 SPACE、DX Core 4 等框架。【官方】[DORA](https://dora.dev/dora-report-2025/)
2. **DORA 2025《State of AI-assisted Software Development》核心论断：「放大器效应」**——AI 放大组织既有的优势与劣势，AI 投资的最大回报不来自工具本身而来自组织底层系统（战略、文化、平台）；配套发布 **DORA AI Capabilities Model**（AI 辅助开发能力模型，可直接当成熟度自评清单用）。【官方】[DORA 2025](https://dora.dev/dora-report-2025/)
3. **量化悖论（Gen AI 报告）**：AI 采纳每 +25%，交付吞吐 -1.5%、交付稳定性 -7.2%（机制：AI 提速产码 → batch 变大 → review 更慢更易出错）；个体幸福感提升（心流、倦怠下降）但「有价值工作」时间反降（vacuum hypothesis）；信任是前提——39% 开发者对 AI 输出「几乎不信任」，收益未兑现。【官方研究】[Impact of Generative AI in Software Development](https://dora.dev/ai/gen-ai-report/)
4. **DORA 的组织级行动清单（可量化对照）**：透明沟通 AI 战略与岗位安全（团队采纳 +125%）、提供在岗学习时间（+131%）、明确 acceptable-use 政策（用例/数据隐私/安全，+451%）、强化自动化测试+快速 review+CI 反馈环（在 AI 错误进生产前拦截）。【官方研究】[gen-ai-report](https://dora.dev/ai/gen-ai-report/)
5. **2026 现状**：DORA 已暂停年度 survey（无 2026 传统年报），转向《ROI of AI-assisted Software Development》报告——把 AI 辅助开发指标换算为财务影响的框架；说明行业度量重心从「采纳率」转向「ROI/产出质量」。【官方】[Google Cloud: DORA ROI report](https://cloud.google.com/resources/content/dora-roi-of-ai-assisted-software-development)（另见 [InfoQ 报道](https://www.infoq.com/news/2026/05/dora-roi-ai-assisted-dev-report/)）
6. **自报生产力不可靠（RCT 证据）**：METR 随机对照实验（16 名资深 OSS 维护者、Cursor Pro/Claude 等）：用 AI 实际慢 19%，但开发者自认为快约 20%——感知与客观耗时系统性脱节，度量必须用客观指标（任务耗时、PR 粒度、返工率）而非问卷。【研究】[METR: Measuring the Impact of Early-2025 AI](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
7. **Anthropic 官方的 agent 级评估维度**（用于系统而非组织）：小规模真实任务 eval 起步（约 20 个真实查询即可驱动迭代）；LLM-as-judge + rubric（事实准确性、引用准确性、完整性、来源质量、工具效率）；状态变更型 agent 评估最终状态而非过程路径；skill 开发「start with evals」。【官方博客】[multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)、[Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
8. **可借鉴的团队级度量信号**：review batch 尺寸（DORA 指出 AI 导致 batch 变大是稳定性下降的直接机制）；失败 CI/PR review 的返工率（Claude Code 官方工作流以 CI+review 反馈为收敛信号）；agent 会话的验证通过率（Stop hook/测试门通过情况）。【官方研究/文档】[gen-ai-report](https://dora.dev/ai/gen-ai-report/)、[best practices](https://code.claude.com/docs/en/best-practices)

### 来源清单

| URL | 类型 |
|---|---|
| https://dora.dev/dora-report-2025/ | 官方研究（DORA 2025） |
| https://dora.dev/ai/gen-ai-report/ | 官方研究（DORA Gen AI） |
| https://cloud.google.com/resources/content/dora-roi-of-ai-assisted-software-development | 官方（Google Cloud，DORA ROI 框架） |
| https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ | 研究（METR RCT） |
| https://www.anthropic.com/engineering/built-multi-agent-research-system | 官方博客（Anthropic eval 方法） |

---

## 附：本次调研实际抓取全文的一手来源（完整性说明）

以下页面为本次调研全文抓取（非二手转述）：agents.md、Anthropic《Claude Code best practices》、Anthropic《Effective context engineering for AI agents》、Anthropic《Equipping agents for the real world with Agent Skills》、Anthropic《How we built our multi-agent research system》、Claude Code 官方文档（hooks / memory / sub-agents / skills / permission-modes / sandboxing）、Cursor rules 文档、OpenAI Codex 文档（AGENTS.md / sandboxing）、OpenAI《Building a safe, effective sandbox to enable Codex on Windows》、agentskills.io 规范、GitHub Spec Kit README、AWS Kiro Specs 文档、Martin Fowler SDD 三工具分析、Matt Pocock《5 Agent Skills I Use Every Day》、DORA 2025 报告页与 Gen AI 报告页、METR 研究（经搜索摘要确认，原文链接已核）。

已知偏差：OpenAI 官方对「AI coding 最佳实践」的公开工程方法论输出集中在 Codex 文档与沙箱博客（其 AGENTS.md 文档即官方指导）；Anthropic 输出最成体系（context engineering / skills / multi-agent / best practices 四篇 + 官方文档）。DORA 2025 报告正文细节以落地页与 Gen AI 摘要页为准，完整数字请以报告 PDF 为准。
