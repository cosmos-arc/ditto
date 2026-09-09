# Ditto 对齐业界 AI Coding 最佳实践：分维度对比与评分

后续状态（2026-09-09）：仓库实测为 public 且账号具 admin，下文 P0「套餐受限」的保留不成立；维护者已配置 ruleset `ditto-main`，[#131](https://github.com/cosmos-arc/ditto/issues/131) 为其补齐 fail-closed 探针并完成行为验收。其余事项对应 [#132](https://github.com/cosmos-arc/ditto/issues/132)–[#134](https://github.com/cosmos-arc/ditto/issues/134)。正文保留评估时点结论。

- 评估日期：2026-09-08。仓库基线：`fd8cd17a`（#111 三批全部合并后的 main）。
- 业界基准取自同日一手调研：[业界 AI Coding 最佳实践调研](2026-09-08-industry-ai-coding-best-practices-sources.md)（下称「调研」）；项目现状取自本轮仓库盘点、`gh` 只读查询与 [2026-09-06 评估](2026-09-06-ditto-harness-assessment.md)后的实施记录。
- 评分锚点（各维度 1–5 分）：**5** = 完全符合并有机器验证，或明显超越通行实践；**4** = 基本符合，存在已识别的小缺口；**3** = 方向正确，存在关键缺口；**2** = 部分偏离；**1** = 缺失。分数是按锚点校准的工程判断，每项附证据。

**总结论：综合 4.2 / 5。文档与知识管理、验证与 CI 两块处于业界先进水平（多数项目未达到）；唯一的关键缺口是 main 分支无机器保护，使「CI 是权威合并门」停留为约定而非强制；其次是缺少真实任务效果度量。**

## 总览

| # | 维度 | 评分 | 一句话结论 |
|---|---|---|---|
| 1 | Agent 指南文件 | 5.0 | 17 处层级化 AGENTS.md + 官方互通模式，体量与分层均优于通行实践 |
| 2 | 上下文工程与知识管理 | 5.0 | 渐进披露 + 知识生命周期 + 防漂移机器检查，超越业界常规 |
| 3 | Skills 体系 | 4.5 | 单一项目 skill 严格按渐进披露组织、CI 校验；缺真实任务效果评估 |
| 4 | Hooks 与质量门 | 4.0 | 三宿主共享 hook 覆盖官方推荐模式；Stop 仅提示、快路缺口待补 |
| 5 | 验证与 CI | 4.5 | 影响范围分层 + fail-closed 汇总门，CI 已全绿；PR 时长略超目标 |
| 6 | 任务交接与跨会话记忆 | 4.0 | GitHub Issues 权威交接符合主流方向；依赖执行纪律，无自动记忆层 |
| 7 | 安全与授权 | 3.5 | 密钥/权限/授权边界完善；但 main 无分支保护，机器强制链断裂 |
| 8 | 度量与评估 | 3.0 | 有 CI 时长/覆盖率/策略回归；无真实 agent 任务效果度量 |

## 1. Agent 指南文件 — 5.0

**业界实践**（调研 §1）：AGENTS.md 是跨工具事实标准（Linux Foundation 管理，60k+ 项目）；monorepo 用嵌套文件、就近优先；长度有硬约束（Codex 合并上限 32 KiB、Claude Code 建议 <200 行）；Claude Code 官方互通做法是 CLAUDE.md 顶部 `@AGENTS.md` 或软链；内容写可执行命令、风格、安全，避免过时指令。

**Ditto 现状**：17 处 AGENTS.md（根 36 行、包级 17–24 行、contracts 37 行），每处配 1 行 `@AGENTS.md` wrapper 的 CLAUDE.md——与官方互通建议逐字一致。根文件结构为「路由表 + 8 条关键不变量 + 授权边界」，全部体量远低于任何官方上限。构建/测试命令不内联，统一指向根 `Taskfile.yml` 与 CI 单一事实源，这是对「命令漂移」教训的合理取舍（9 月 6 日评估曾发现 skill 内命令矩阵指向不存在的入口，现已消除）。

**对比**：分层、体量控制、单一事实源、互通模式全部符合或优于通行实践；OpenAI 主仓库自维护 88 个 AGENTS.md 的分层用法与 Ditto 同构。未发现偏差项。

## 2. 上下文工程与知识管理 — 5.0

**业界实践**（调研 §2）：上下文是有限资源，核心是 right-sized information；四大策略（compaction / 结构化笔记 / subagent 隔离 / 按需检索）；渐进披露是核心落地模式；从简单系统起步、以真实信号驱动复杂度。

**Ditto 现状**：根 AGENTS 从 119 行减至 36 行并改为路由表，按需读取架构/契约/测试/harness 文档（`docs/architecture/agent-context-pack.md` 等即「按需检索」的仓库内实现）；skills 11 个 5,814 行收敛为 1 个（知识迁回 owner 文档）；[ADR 0013](../adr/0013-repository-knowledge-lifecycle.md) 确立知识生命周期，第三批退役 112 份历史计划并留恢复基线；`.knowledge-policy.toml` + `task knowledge-check` 把「活跃文档链接与机器输入位置」变成机器检查，直接针对「过时指令侵蚀信任」这一官方警告。`.ignore` 收敛默认检索范围与文档生命周期一致。

**对比**：业界多数实践停留在「写短一点的 CLAUDE.md」；Ditto 已把渐进披露、退役、防漂移做成制度加机器门，属于超越通行实践的部分。残留 `docs/plans/` 活跃计划与 `.ignore` 的摩擦已在 #111 中处理为「plans 不作台账、规格进 Issue」。

## 3. Skills 体系 — 4.5

**业界实践**（调研 §3）：Agent Skills 开放标准（agentskills.io）——必填仅 name+description（须写明「做什么+何时用」并含触发关键词）；三级渐进披露（metadata ~100 tokens 常驻 → 正文按需 → 资源按需）；SKILL.md <500 行；官方开发法「start with evals」；事实进 AGENTS/CLAUDE、流程进 skill。

**Ditto 现状**：唯一项目 skill `ditto-pit-safety`：SKILL.md 38 行 + `references/pit-contract.md`（正文短、细节在 references，标准三级披露）；`registry.toml` 登记 name+owner；`sync_skills.py` 做跨宿主字节级镜像，`validate.py`（471 行）校验 registry/镜像/hook 结构一致性，CI 有独立 `skill-validation` job；`evals/v1/cases.json`（15 个对抗用例）作为 policy 回归。

**缺口**：(a) 现有 eval 是确定性策略单测，不能证明 skill 对真实任务效果的影响——#111 计划文档已自我识别「policy eval 不等于 agent 工作流效果评估」，官方「start with evals」指的正是后者；(b) 未逐项核对 agentskills.io 规范字段（name 命名规则、description 触发关键词写法），跨宿主移植性靠自建校验而非规范符合性检查。

## 4. Hooks 与质量门 — 4.0

**业界实践**（调研 §4）：CLAUDE.md/memory 是上下文不是强制，「保证阻止必须用 PreToolUse hooks」；exit 2 阻断并把 stderr 反馈给模型；PostToolUse 注入 lint 结果实现自修复；Stop hook 用于拒绝未通过测试的「完成声明」。

**Ditto 现状**：`hook.py`（1,171 行）三宿主共享：PreToolUse 阻断危险命令 + 受保护路径 lease；PostToolUse 对编辑的 Python 文件 ruff format；Stop 提示未提交改动（不阻断，harness 文档明确此取舍）。`.claude/settings.json` 三段式 permissions（allow `Bash(uv|task|git|gh)` 等 / deny `sudo`、force push、`reset --hard` / ask `rm -rf`）。pre-commit：gitleaks、conventional commits、`no-commit-to-branch(main)`、大文件与私钥检测。`check-changed` 按 changed set 分级强制验证，「禁 type ignore / no-verify」写入不变量。

**缺口**：(a) 本地 hook 与 `no-commit-to-branch` 都只在提交者本机生效，`gh api` 推送或他机操作可绕过——服务端缺口归入维度 7；(b) PostToolUse 仅覆盖 Python format，Web 侧依赖 CI 与 `check-changed` 兜底（可接受但非官方推荐的即时反馈模式）；(c) Markdown 快路使纯文档变更的 skill 源/镜像修改不触发镜像校验（#111 已识别，轻量校验待实现）。

## 5. 验证与 CI — 4.5

**业界实践**（调研 §5 + 9 月 6 日外部证据）：给 agent 可独立运行的验证手段；测试范围匹配变更影响（OpenAI 指南）；spec-driven 用于复杂任务而非全部任务（Fowler 对大前置 spec 的警告）；TDD 是提升 agent 输出最一致的方式（Matt Pocock）；CI 失败反馈贴回会话迭代；required check 需区分跳过/失败/缺失。

**Ditto 现状**：[ADR 0011](../adr/0011-ci-verification-scope.md) 分层验证——普通 PR 按栈选粗粒度范围、根工具链/契约/高风险跑全套、main 与发布保留完整证明、PR 目标 10–15 分钟；`ci.yml` 17+ job 含 `repository-policy` 范围选择与 `ci-gate` fail-closed 汇总门（`always()` + 上游结果校验，正是 GitHub 文档推荐模式）。本轮 `gh` 实测：2026-09-08 最近 10 次 CI 全部 success，PR 全程 14–18 分钟（9 月 6 日时为连续失败 + 45 分钟超时，`#96`/`#109`/`#110` 后已修复）。测试四层（单元/集成/Golden-E2E/PIT mark）、覆盖率分支门槛 80%（后端实测 89.41%）、每周 mutation-critical。工作流按风险分流（小改直通、复杂任务访谈→规格→拆票）与 Fowler/Kiro/Spec Kit 的分层精神一致，且避开了「大锤砸核桃」。

**缺口**：(a) PR 实测 14–18 分钟，高于 10–15 分钟目标，未定位是排队还是分类保守；(b) 上述 skill/镜像快路缺口；(c) `merge_group` 触发已就绪但因分支未保护（维度 7），merge queue 实际未启用。

## 6. 任务交接与跨会话记忆 — 4.0

**业界实践**（调研 §6）：handoff 用结构化文件/Issue 记录（目标、当前状态、验证证据、下一步）；跨会话记忆双轨（常驻指令 + 自动记忆 MEMORY.md）；复杂任务评估最终状态而非过程路径。

**Ditto 现状**：GitHub Issues 是复杂任务规格/验收/交接的权威位置（ADR 0013）；`task-template.md` 含交接评论字段（批次目标/SHA/PR/验证结果/剩余事项）；`issue-tracker.md` 定义 wayfinder 操作（map/child/blocking/frontier/claim/resolve，用 GitHub sub-issues 与 dependencies）；本地验证 receipt 按 worktree 隔离。#111 十项决定跨四轮确认后全部进 Issue，本轮三批 PR 即按该记录执行——机制已被实战验证。

**缺口**：(a) 交接质量依赖「记得写交接评论」的纪律，无自动提醒或结构校验；(b) 无仓库级自动记忆层（宿主各自记忆不共享）——对单人项目影响有限，多宿主切换时（Claude Code/Codex/ZCode）决定与偏好仅存于 Issue。

## 7. 安全与授权 — 3.5

**业界实践**（调研 §7）：sandbox 定义边界、approval 决定何时询问；权限 allowlist 用精确命令；受保护路径防自我提权；secrets 需 pre-commit + CI + canary 多层；「危险操作需确认」写进指令已成官方示例惯例；网络抑制是最关键单点（OpenAI）。

**Ditto 现状**：授权边界清单（依赖升级、schema 迁移、CI 权限、真实数据、不可逆删除需明确授权）与 Codex 官方示例同构；gitleaks 三层（pre-commit + CI 全历史 + canary token 检测证明）+ OSV + detect-private-key；测试默认 null keyring 隔离；lease 单写者保护生成物；危险命令 deny 列表齐备。

**关键缺口**：本轮 `gh api` 实测 `branches/main/protection` 返回 **404 Branch not protected**，rulesets 为空——即：

- 「不在 main 直接 commit/push」「不 force push」只有本地 pre-commit 与 prose 约束，服务端不阻断；
- `ci-gate` 及全部 CI 未配置为 required check，「CI 是权威合并门」（ADR 0011）无机器载体；
- 任何人/任何 agent 会话在任意机器上可直接推 main 绕过整套验证链。

这正是业界反复强调的「上下文不是强制，强制要用机器门」在仓库层的镜像：Ditto 在工具层（hooks/permissions）做到了机器强制，在托管平台层（GitHub）却是空的，且与自身 ADR 的声明矛盾。次要缺口：CodeQL 上传受 Advanced Security entitlement 限制（已记录）、SECURITY.md 仅私漏报告指引、仓库自身不声明沙箱/网络边界约定（依赖各宿主默认）。

## 8. 度量与评估 — 3.0

**业界实践**（调研 §8）：无公认成熟度框架；事实基准是 DORA 四指标 + AI 采纳扩展；DORA 2025「放大器效应」与组织行动清单；METR RCT 证明自报不可靠，须用客观指标（任务耗时、返工率、人工干预）；agent 级评估从 ~20 个真实任务起步。

**Ditto 现状**：已有客观度量：CI 时长目标 + 实测、分支覆盖率（89.41%）、策略回归 15 用例、精简实施记录含前后对比（大查询 157.6s→22.4s、AGENTS 119→36 行、skills 11→1）。

**缺口**：[9 月 6 日评估](2026-09-06-ditto-harness-assessment.md)第 5 步设计的「8–12 个近期真实任务、同模型同验收的前后对照」尚未执行；无返工率、人工干预次数、验证通过率、token/耗时的持续记录；review batch 尺寸（DORA 指出的稳定性下降机制）未观测。当前所有「精简后变好」的证据是结构性的（文件数、行数、CI 时长），不是结果性的（任务完成质量）。

## 待优化清单

按优先级排序；P0 为关键缺口，P1 为高价值，P2/P3 为改进项。

| 优先级 | 事项 | 说明 | 验收 |
|---|---|---|---|
| **P0** | 为 main 启用分支保护/ruleset | 配置 require PR、required check（`ci-gate`）、block force push 与删除。注：私有仓库的经典分支保护需 Pro/Team 套餐、rulesets 需 Team/Enterprise 或公开仓库，9 月 6 日查询 403 提示套餐受限；若套餐不允许，退化方案是 CI 中检测 direct push to main 的工作流（告警 + 可选自动回滚），并记录为已知残余风险 | `gh api branches/main/protection` 非 404；direct push 与 force push 被服务端拒绝；required check 生效 |
| **P1** | 补上 skill/镜像 Markdown 快路校验 | `hook.py:624–633` 先分类 Markdown，纯文档路径的 skill 源/镜像修改不触发镜像校验；#111 计划内的轻量校验尚未实现 | 修改 `.agents/skills/**` 的 Markdown 在本地与 PR 均触发镜像一致性检查；普通文档仍走快路 |
| **P1** | 执行真实任务效果对照 | 落实 9 月 6 日评估的 8–12 任务协议：文档、小 UI、bug、API、PIT、跨包重构各若干，记录完成质量、返工、人工干预、重复验证次数、token、耗时。可先回溯 #96–#126 批次的真实会话做基线 | 得出精简前后可比数据；后续 harness 改动以此为准入证据 |
| **P2** | PR 时长进入 10–15 分钟目标区间 | 实测 14–18 分钟；先分辨排队与执行，再检查 `repository-policy` 分类是否对普通改动偏保守 | 连续若干次普通 PR 中位数 ≤15 分钟且不降低检查覆盖 |
| **P2** | 评估 Stop 阻断式验证的取舍 | 当前 Stop 仅提示不阻断（有记录的取舍）。可考虑仅当「声明完成且存在未验证改动」时运行分级 `check-changed` 的轻量挡板；保持响应时间约束 | 有明确决定（采纳或继续不阻断）并记录理由 |
| **P3** | 核对 agentskills.io 规范符合性 | 逐项核对 `ditto-pit-safety` 的 name 规则、description「做什么+何时用」+触发关键词写法；`registry.toml` 作为仓库扩展保留并注明 | `skills-ref validate` 或等效检查通过；跨宿主行为不变 |
| **P3** | 充实 SECURITY.md 与沙箱约定 | 补充 agent 会话的沙箱/网络边界约定（默认宿主沙箱、禁 bypassPermissions、真实数据操作需授权）与漏洞响应细化 | 文档更新且与现有授权清单无冲突 |

## 与 2026-09-06 评估的衔接

9 月 6 日评估指出的问题在本轮盘点中的状态：skills 11→1（已实施，知识落点迁移完成）；CI 五连红/45 分钟超时（已修复，今日全绿）；`bun run check/ci` 等命令漂移（随 uv/Task 迁移消除）；Pixi→uv、根图→Task（#109 完成，残留仅 `.pixi/envs/` 本地目录）；主观分数门槛、固定角色、重复确认（已删除）；14 个 tooling 测试接入与 branch protection 核验（branch protection 本轮确认为仍未解决，转为 P0）。

## 本轮证据与限制

- 现状事实来自只读盘点（17 处 AGENTS.md、skills/hooks/CI/Taskfile/ADR/文档结构、`.importlinter` 43 契约等）与 `gh` 只读查询（最近 12 次 workflow runs、branch protection、rulesets）；未运行任何检查或测试，未修改产品代码与配置。
- CI 时长取自 run 的 createdAt/updatedAt 差值，含排队与收尾，非纯执行时长；样本为 2026-09-08 单日 10 次成功运行。
- 分数为按锚点校准的工程判断，非统计结果；业界基准的完整来源见配套调研文档，其已知偏差（厂商输出集中于 Anthropic/OpenAI、DORA 数字以落地页为准）同样适用于本报告。
- 未评估：宿主实际运行时的 hooks 触发行为（静态配置与实际信任已由 #111 验收区分）、`agent_eval` 用例的覆盖质量、Web 侧 11,572 行脚本中剩余项的逐个去留。
