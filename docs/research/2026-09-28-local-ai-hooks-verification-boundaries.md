# 本地 Git hooks 与 AI hooks：职责、反馈预算和验证复用

日期：2026-09-28。研究票：[研究：本地 Git hooks 与 AI hooks 的职责、反馈预算和验证复用](https://github.com/cosmos-arc/ditto/issues/334)。代码基线：`2b928893fdd17141bcc1a625c89265ae0dbb875c`。本文提供后续决策的证据和候选方案，不修改门禁，也不代替维护者决定哪些检查可以移走。

## 结论与证据等级

现有分工已经把 AI 同步 hooks 与产品质量验证分开：PreToolUse 做操作前策略，PostToolUse 精确格式化，Stop 只提示。当前能直接确认的重复成本主要位于显式检查、pre-push 与 Task 内部。优先测量和消除同一次验收中的重复执行，再决定是否改变 pre-push 职责或恢复结果缓存。不能把每一层重新执行都视为无效：staged 内容、工作区内容、推送提交和 CI checkout 的身份及信任边界不同。

| 来源事实 | 对 Ditto 的推断或候选方向 | 需要实测或裁决 |
| --- | --- | --- |
| pre-commit 临时移走未暂存差异，只检查暂存内容；自动修复会使当前检查失败。[官方说明](https://pre-commit.com/#pre-commit)、[4.6.1 执行实现](https://github.com/pre-commit/pre-commit/blob/v4.6.1/pre_commit/commands/run.py#L200-L211) | 保留 staged 格式化和秘密扫描；不要用编辑后格式化替代提交检查 | 部分暂存与自动修复冲突时的恢复行为、热/冷启动耗时 |
| Git pre-push stdin 含每个 ref；pre-commit 4.6.1 在首个可处理 ref 返回选定范围。[Git 协议](https://git-scm.com/docs/githooks#_pre_push)、[实现](https://github.com/pre-commit/pre-commit/blob/v4.6.1/pre_commit/commands/hook_impl.py#L120-L176) | 当前本地保证是选定范围，不是全部 ref；常规单分支工作流无需先造隔离构建平台 | 是否确实需要多 ref 本地强保证 |
| Codex 默认同步等待；异步只能反馈，不能阻断；多个匹配来源可并发。[官方 Hooks](https://learn.chatgpt.com/docs/hooks) | 安全决策保持同步；把重测试改 async 并不能保持原门禁语义，还可能加重资源竞争 | 实际加载来源、事件次数、耗时、并发数 |
| Codex 非托管 hook 定义需信任；Stop block 是续跑。[官方信任与 Stop](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks) | 配置存在与实际生效分别验收；Stop 成功不是测试通过 | 当前桌面会话的版本、信任、实际触发证据 |
| ZCode 官网称项目 hooks 被忽略；本机 3.14.3 bundle 却有 workspace hooks 与信任接口（下文） | 不能凭官网直接删除仓库配置，也不能凭 bundle 字符串称已部署 | 新会话的有效来源及真实事件；文档/版本差异 |
| Ditto 已退役 manifest/receipt；本地每次执行 scope 计划。[当前说明](../engineering/agent-harness.md#hook-矩阵)、[退役提交](https://github.com/cosmos-arc/ditto/commit/2659684a) | 先减少重复调度和不必要范围，再评价缓存收益 | 同内容重复验证频率、可节约时间、输入身份能否准确覆盖 |

## 一手资料的边界

Codex 官方文档本轮从 developers.openai.com 搜索入口打开，重定向至 `learn.chatgpt.com/docs/hooks`。其协议与 Claude Code 不是一份合同：本文未借用 Claude 的重试上限、输出处理或配置路径。Codex async 在会话结束可取消，结果到安全时点才送达；不能作为验收完成证明。同步 PostToolUse 也不能撤销已发生的副作用。这些是机制事实，不是“所有项目必须这样分工”的厂商规定。[Codex 官方 Hooks](https://learn.chatgpt.com/docs/hooks#run-hooks-in-the-background)

Ruff 官方要求开启 lint fix 时先 lint、后 format；Ditto 当前顺序符合该建议。没有必要仅为贴近示例而替换 `uv` 锁定环境中的 local hooks，或新增 Husky/lint-staged。[Ruff 官方集成](https://docs.astral.sh/ruff/integrations/#pre-commit)

pre-commit 对部分暂存使用临时 patch 保存和恢复；若恢复与 hook 修复冲突，回滚修复后恢复原差异。因此让 formatter 自动改文件并不等于自动把修复纳入提交。上述语义已核对本机 4.6.1 安装源码，与固定版本上游实现一致；本轮未重新做部分暂存动态实验。[staged_files_only.py](https://github.com/pre-commit/pre-commit/blob/v4.6.1/pre_commit/staged_files_only.py#L50-L113)

Git 会向 hook 导出仓库环境变量；在 hook 内进入其他仓库时应清除相关变量。Ditto pre-push 在运行验证命令前清理 `git rev-parse --local-env-vars` 的结果；应保留这一隔离，避免测试创建的临时 Git 仓库继承原仓库上下文。[Git 官方说明](https://git-scm.com/docs/githooks#_description)、[本地实现](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/pre_push.py#L64-L75)

## 当前本地链路

以下源码链接固定到调查基线，行号不会随后续改动漂移。

| 入口 | 实际范围、动作与失败含义 | 事实源 |
| --- | --- | --- |
| pre-commit | 文件卫生、Python `ruff check --fix` → `ruff format`、gitleaks；没有 pytest/type | [.pre-commit-config.yaml](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/.pre-commit-config.yaml#L11-L81) |
| commit-msg | conventional commit 消息检查 | [配置](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/.pre-commit-config.yaml#L86-L102) |
| pre-push | pre-commit 选定的 base/target；要求工作区干净且 target 为 HEAD；必要时基于 origin/main merge-base 或回退 `task check`；串行执行 scope 命令 | [pre_push.py](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/pre_push.py#L16-L86) |
| check-changed | 未提交完整 changed set；检查包管理规则和受保护路径 lease，再按 scope 显式运行验证，失败返回非零 | [hook.py](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1287-L1394) |
| PreToolUse | 已识别危险命令及受保护写入授权；不跑测试 | [策略](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L669-L696) |
| PostToolUse | 只对已可靠解析且存在的 Python 文件运行准备好的 Ruff；格式化失败反馈给模型，不替换为产品验证通过 | [格式化](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L724-L777)、[协议输出](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1512-L1527) |
| Stop | 读取 Git changed set 并提示；重入直接返回；没有测试、成功收据或结束阻断 | [stop_feedback](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1397-L1418) |

配置的宿主超时为 Pre/Post 各 10 秒、Stop 3 秒；formatter 内部 5 秒并清理其进程组。它们是当前上限，不是实测 p95，也不是业界统一推荐值。[Codex 配置](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/.codex/hooks.json)、[ZCode 配置](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/.zcode/config.json)、[formatter 清理](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L699-L777)

本轮主 checkout 的 pre-commit/pre-push/commit-msg 均为已存在的可执行文件，使用主 checkout `.venv` 的 pre-commit 4.6.1；Git `core.hooksPath` 和配置式 `hook.*` 查询没有条目。此结果取代旧研究的“尚未安装”快照，但只证明安装文件存在。本轮研究文档的正常提交会经过实际文档 hooks；这不证明 Python、pre-push 或 AI 事件已动态验收。

## 已证实的放大与重复入口

1. **局部 backend scope 仍付出全库静态检查。** Owner 合并 fast 测试之前运行根 lint、fmt-check、type-all；后者是 `--all --clean`，对源与整个测试集合分别检查。仅修改测试文件也执行全部测试类型检查。文档“共享包级静态检查”的描述不够准确。[scope 命令](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1229-L1239)、[测试类型入口](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1098-L1109)、[Task 定义](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/Taskfile.yml#L8-L43)、[type.py](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/scripts/type.py#L19-L53)
2. **scope 选择阶段又有 collection 探针。** `_owner_fast_coverage` 收集每个 owner 的 fast 用例，之后正式测试再收集。缓存只是该 Python 进程的 `lru_cache`，不是跨显式检查/pre-push 的成功证明。现有文档仍称“不再独立预探测”，与基线源码不符。探针有防止某 owner 零用例被合并调用掩盖的独有保障，不能只删进程而漏掉这一合同。[探针与调用](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1158-L1228)、[文档](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/docs/engineering/agent-harness.md#L70-L73)
3. **一次 Web static 内确定重复 lint。** `web-static` 调用 web-lint 后又调用 web-architecture，后者 `arch:check` 内再次 `bun run lint`。这是同一门内可直接审查的去重候选，是否值得先做仍取决于成本。[Task](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/Taskfile.yml#L185-L200)、[Web scripts](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/apps/web/package.json#L11-L20)
4. **扩大 scope 的规则已比 AI 事件频率更直接。** API/models/transport 按 contract 升到 check+system；根配置、harness、未知路径到 check；高危包另加 PIT。PIT 没被 fast 表达式排除，因此可能先在 owner 测试中运行，再被全局 PIT 重跑。这是静态可达重复，尚未测具体相交用例数量与耗时。[分类与计划](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py#L1243-L1284)、[fast 表达式](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/scripts/test.py#L72-L85)

这些事实不支持“AI Stop 仍每轮跑全库”的诊断。整个开发循环中相同内容可能先手工 check-changed，再 pre-push，再 CI；但有多少次确属相同输入，尚无本轮统计。

## ZCode：官网与安装版本尚未对齐

官网目前说明：用户配置需 `hooks.enabled`，插件可携带 hooks，项目 `.zcode/config.json` 被忽略，并建议新会话核查。它同时在设置操作段仍提 workspace scope，资料内部也有不一致。[ZCode 官方 Hooks](https://zcode.z.ai/en/docs/hooks#configuration-sources)

本机只读检查得到：

- `/Applications/ZCode.app/Contents/Info.plist` 的 `CFBundleShortVersionString` 为 **3.14.3**，不是旧研究的 3.11.2。
- 随 app 交付的 `Contents/Resources/glm/zcode.cjs` SHA-256 为 `b1df2ef3e5bd76c4af3ecb296bc003a10d3f13191a26610bd0ba940feadad529`。
- bundle 存在 `workspace/hooks/trustGrant`、`workspace-hook-` review item、`hookDeclarationDigest`、`sourceEnabled:o.hooks.enabled` 与按 `hooks.events` 装配的代码。精确字符串 `config_project_hooks_ignored` 未找到。
- 当前 shell PATH 无 `zcode` CLI；未启动新 ZCode 会话，未读取用户私密配置或更改信任。

这些安装制品证据只能确认本版本有相关实现线索。未找到某日志字符串不证明项目 hooks 一定执行，静态 review item 也不证明运行路径可达。后续需要以该版本实际有效配置、信任状态、事件日志及允许/拒绝/格式化行为收口；不得用旧版本研究或另一宿主 API 补齐空白。

本机 `codex --version` 返回 `codex-cli 0.155.0-alpha.9.2`；CLI 版本也不能替代当前桌面宿主版本。二者实际触发状态均在本票保持未测。

## 候选职责矩阵：供决策，不直接生效

| 层 | 建议保留的职责 | 删除或迁移的候选 | 预算与验收依据 |
| --- | --- | --- | --- |
| AI PreToolUse | 确定的危险操作拒绝、目标 worktree 与 lease 校验 | 不在此新增 lint/test/环境安装；重复来源相同规则可合并 | 操作前完成；测 p50/p95 与失败路径，保留拒绝回归 |
| AI PostToolUse | 精确 Python 文件的快速格式化 | 若 formatter 与编辑器重复且实测可感，再评价去重；重测试移到显式入口 | 当前内部 5 秒/宿主 10 秒仅作上限；无迟到写入、无无关文件改动 |
| AI Stop | 简短改动与未验证提示 | 不恢复自动全量测试或每轮续跑；提示噪声是否删除由用户决定 | 当前 3 秒上限；讨论/旧脏文件不得启动测试 |
| pre-commit | staged 卫生、格式、秘密扫描、提交消息 | 不加入产品全套测试；不另建 hook 管理器 | 单文件与批量 staged 冷/热实测；部分暂存保持完整 |
| 显式验证 | 有输出进度的受影响行为/类型/边界验证 | 同一次计划中重复 lint、重复收集应统一归属；扩大范围需有消费者证据 | 分解规划、启动/收集、执行、清理耗时 |
| pre-push | 最终选定提交范围与工作区身份核对 | A 保留当前验证但避免用户先手工重复；B 改为有界快速门、重门移显式/CI；C 验证成功结果按内容安全复用 | A/B/C 是待裁决替代项，不能默认实施 B/C；比较首次失败反馈与总等待 |
| 远端 CI | 目标提交上的合并门、平台与独立环境证据 | 本地通过不能直接取消远端验收 | 由远端 CI 研究票和风险决策统一确定 |

预算必须来自典型改动集的测量，不用一个任意“十秒内”指标迫使检查跳过。同步事件频繁调用，既要量单次时长，也要量一次任务累积次数。异步反馈可作为可选诊断，但自动并行全量测试会让输入持续变化、结果过时，并与 xdist/Vitest 争抢资源；它不是免费加速。

## 重复验证：先调度去重，再决定是否缓存

最小候选是沿用一个权威 Task 计划，清楚分开“为了定位失败的专项”与“本次最终完整验证”。同一内容将由正常 pre-push 验收时，不先手工再跑相同全量计划；现有测试指南已有此约定。失败后的修复只重跑受影响检查，然后由最终门补证。此举不新增持久状态。[测试指南](../engineering/testing.md#修复与反馈顺序)

若实测表明不同入口确实反复支付大量相同成本，再比较结果缓存与继续重跑。**缓存条件是工程推断，以下不是本票批准恢复 receipt：**

| 必须识别的变化 | 为什么不能继续复用旧成功 |
| --- | --- |
| 选定 base、target、路径集合、删除/重命名/模式、未跟踪输入、staged 与工作区内容差异 | 同名文件或同一 HEAD 不代表验收了同一内容；范围变更会改变所需门 |
| 命令、参数、marker、scope 分类规则、测试/fixture/conftest、生成器与契约配置 | 测试集合或断言变了，旧结果无从证明新计划 |
| 实际依赖、锁文件、解释器/工具版本、OS/架构、相关环境变量 | 相同源码在不同执行条件下不是相同验收；源码树指纹还不足够 |
| 运行期间任何输入变化、失败、超时、取消、证据缺失 | 不得记录成功；需快照或运行前后身份一致性证明 |
| 远端数据、时间、权限/租约、宿主 trust 与规则状态 | 这些不是纯函数输入，不能长期缓存“允许执行”或外部现场验收 |

优先复用各工具原生安全缓存而非搭建新缓存服务；仅 mtime 不足以证明内容身份。也不能不经核验便认定 `scripts/type.py` 删除的目录是 basedpyright 当前有效增量缓存。PIT/资金/契约/安全门若试行本地结果复用，要保持对应反例与最终提交 CI；本地 receipt 不升级为服务端合并凭证。

## 最小后续实测与验收材料

1. 固定主机、工具版本、SHA 和代表性范围：文档、单 Python 测试、单 owner 源码、高危包、单 Web、跨栈/contract；冷/热分开，主机保持单套完整验收。记录显式检查与 push 的重复次数，先测一次诊断性样本，再对确有成本的路径采足比较样本。
2. 分离 scope 选择/collect-only、Ruff、源/测试类型、xdist 启动与收集、测试 setup/call/teardown、Web static 子步骤。计入失败、取消和资源竞争，不能只报成功样本平均值。
3. 在一次性 Git 仓库和 bare remote 验证 staged/unstaged、formatter 改文件、单 ref、新分支、删除、非 HEAD、多 ref 的准确覆盖和恢复；不向真实 remote 推送探针。
4. Codex/ZCode 各自新会话核验配置来源、信任、事件触发、已识别允许/拒绝、准确格式化、Stop 重入、超时清理。不给用户当前信任自动赋值；不以静态 validator 替代这一步。
5. 若提缓存方案，再用输入内容/命令/环境变更与运行中写入反例验证失效。没有命中率与节省时间数据，就不恢复完整 receipt/manifest 平台。

本票已完成官方资料、当前仓库链路与安装制品只读核查，并形成上述决策输入。截至研究取证结束，未测完整本地 CI 耗时、未运行全量测试、未触发真实 pre-push、未验证当前 AI 会话信任，也未更改 hooks/CI/全局宿主设置；后续研究分支发布时的正常文档范围 pre-push 另行记录，不代表产品范围或宿主事件验收。研究结论可以关闭知识缺口；职责迁移、反馈预算和缓存是否实施仍需后续决策票。
