# Hooks 决策复核：官方实践、项目约束与修改计划

日期：2026-09-15。本文是一次性研究结论，不是运行状态台账。区分官方支持的机制、当前本地证据，以及本项目的工程选择；官方示例不能证明某方案适合所有项目。

## Git hooks、pre-push、lease 与版本策略的独立复核

### F03：未安装成立，但不是远端安全边界失效

本轮只读复核：Git 2.55.0；`git config --show-origin --get-regexp '^(core\.hooksPath|hook\.)'` 无条目；`git rev-parse --git-path hooks/<event>` 得到的 pre-commit、pre-push、commit-msg 文件均不存在、不可执行。Git 2.55 还支持配置式 hooks，因此不能只检查 `.git/hooks`。[Git hook 官方文档](https://git-scm.com/docs/git-hook)

**保留建议：**使用已有 `Taskfile.yml:313` 的 `task pre-commit-install`，不引入另一套管理器。安装流程应保留已有 hooks，并在临时仓库验证真实 commit、消息拒绝和部分暂存恢复。安装状态诊断优先使用 Git 原生事件清单；旧 Git 再检查配置和解析后的路径。

**修正严重性表述：**这是已确认的本机交付流程缺口；若项目承诺本地自动运行，可列优先修复，但不能据此声称远端保护失效。客户端检查与服务端必需检查承担不同职责；本轮没有验证当前 GitHub ruleset。Git 官方明确本地提交 hooks 可被用户绕过；受保护分支可以要求状态检查。[Git hooks](https://git-scm.com/docs/githooks)、[GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

### F04：多 ref 范围缺口成立，不能直接推导出“必须造多提交隔离验证器”

本机 pre-commit 4.6.1 的 `pre_commit.commands.hook_impl._pre_push_ns()` 在首个可处理 ref 上返回。`tooling/agent_harness/pre_push.py:12` 只消费单组环境变量，并要求提交等于当前 HEAD、工作区干净。因此双 ref 不能证明全部受检；这与上游当前实现一致，而不是 Ditto 独有解析错误。[pre-commit 上游源码](https://github.com/pre-commit/pre-commit/blob/main/pre_commit/commands/hook_impl.py)

Git 原生 pre-push stdin 提供每个 ref 的对象 ID。pre-commit 对外文档列的是单组 `PRE_COMMIT_FROM_REF` / `TO_REF` 等变量，没有承诺所有 ref 分别执行完整产品测试。[Git pre-push 协议](https://git-scm.com/docs/githooks#_pre_push)、[pre-commit pre-push](https://pre-commit.com/#pre-push)

**推荐：**保留 pre-commit 管理和当前分支快速反馈；把文档明确为“pre-commit 选定范围的本地验证，常规单分支推送”，取消“已证明整个 push 全部提交”的表达。实际合并/发布仍由精确提交上的 CI 与服务端规则验收。先确认项目是否真的要求多 ref 推送前的完整保证，再决定扩展。

如项目明确要求“未验收 ref 绝不能推送”，才在 Git 原始 stdin 边界添加准确的单 ref 限制或逐 ref 验证。单 ref 限制也是新增工作流约束，不能静默加入；多 ref 隔离 checkout、依赖环境和结果缓存更不是通用最佳实践的必选项。只在现有 Python wrapper 检查环境变量无法发现被上游忽略的第二 ref。

**验收：**单 ref、两个 ref、创建分支、删除 ref、tag、非当前 HEAD、基线缺失，使用临时 bare remote。每种输入都报告实际选中范围与未覆盖范围；CI 验收绑定目标提交。如果选择严格本地合同，则全部输入必须满足该合同，不能仅修改说明后仍宣称全覆盖。

### F10：保留 integrator 协调，不把它升级成分布式锁

`docs/engineering/agent-harness.md:89` 的需求是指定 integrator worktree 单写契约、生成物、lockfile 等；`lease.py:462` 只在执行前授权，未包围真实写入。这个边界判断成立。独立 worktree 有自己的检出文件与部分私有 Git 状态，共享 refs 等仓库数据；不能把所有文件都称作同一物理共享资源。[Git worktree 细节](https://git-scm.com/docs/git-worktree#_details)

**推荐：**保留现有用户要求的协作规则，修正路径身份和误判，明确“协作授权租约”能力。撤回任何无条件追加 fencing、跨平台锁服务、长事务执行包装器的建议。只有真实资源存在并发写入且要求互斥时，才在该写入入口选择适当锁；Python 的 `fcntl.flock` 是 Unix 平台原语，不能充当跨平台通用方案。[Python fcntl](https://docs.python.org/3/library/fcntl.html)

当前 guard 的过期回收只按时间，`lease.py:349` 的实现还应做暂停持有者、竞争回收和释放竞态测试。但测试目标是租约元数据一致性与授权正确性，不能要求现有 precheck 架构证明整个业务写入的互斥。删掉全局 lease 或替换保证范围均应作为明确的协作合同调整，不随格式化修复附带实施。

### F11：版本声明需修，固定 tag 并非违反官方实践

配置 `minimum_pre_commit_version: 2.20.0` 与已使用的 stage 名称不匹配：官方说明这些名称自 3.2.0 才采用；`pyproject.toml:55` 实际要求 >=4,<5。建议最低版本至少与已声明支持线一致，并用锁定环境验证。[pre-commit stages](https://pre-commit.com/#confining-hooks-to-run-at-certain-stages)

**修正：**官方默认更新方式采用版本 tag，并提供 `autoupdate --freeze` 固定提交。不能把 tag 配置判成“不符合业界”。本项目追求更严格可重复性时，可以固定 SHA 并注释对应版本，沿用官方更新方式；先解析现有版本到 SHA，升级另行审查，避免把固定版本和升级依赖混成一个动作。[pre-commit autoupdate](https://pre-commit.com/#pre-commit-autoupdate-options)

本地 gitleaks v8.21.2 与 CI v8.30.1 的差异已再次确认。建议对齐检测器版本与适用规则，或明确记录保留差异的理由；配置中的 Python 工具版本一致性注释不能直接推导出 gitleaks 已违反版本承诺。相同版本也不代表 staged 与完整历史扫描覆盖相同。不能仅凭旧版本宣称漏洞。CI 镜像已固定 digest，应保留。

Ruff pre-commit 的 `check --fix` 在 `format` 前执行符合官方集成建议，保留；无需改成全只读，也无需为了使用官方示例而替换当前 uv 锁定环境的 local hooks。[Ruff integrations](https://docs.astral.sh/ruff/integrations/#pre-commit)

### 本次独立复核边界

只读检查安装状态、文档和依赖源码，并创建本研究文件。没有安装 hooks、修改源代码/配置/租约、变更 trust、修改插件、进行真实远端 push 或运行产品测试。之前报告中的隔离复现结果不冒充本轮重新执行结果。


## 总裁定：哪些保留，哪些修改，哪些撤回

本文覆盖最早审计的 F01–F12，并替代其中过宽的修改建议。严格意味着结论有证据、保证可验证，不意味着增加最多的机制。

| 对象 | 最终决定 | 依据与修正 |
| --- | --- | --- |
| PreToolUse | 保留并修复 | 目录身份、误判与漏判已有隔离反例；只承担宿主实际覆盖范围内的提前检查 |
| PostToolUse 自动 Ruff | 保留并修复目标路径 | 官方明确支持编辑后自动格式化；撤回默认删除建议 |
| pre-commit Ruff fix → format | 保留 | 顺序符合 Ruff 官方集成说明；不用改成全部只读 |
| Ponytail hooks | 保留，修会话状态和宿主适配 | 用户明确要求；已有本机反例与上游问题相互印证 |
| Stop | 保留当前轻量提醒 | 当前没有自动跑测试或阻止结束；没有删除它的充分依据，噪声偏好可另调 |
| integrator lease | 保留协作授权合同 | 修准确性与元数据竞态；不升级成整个业务写入期间的互斥锁 |
| Git hooks 管理 | 沿用 pre-commit | 修本机安装缺口，不引入第二套管理工具 |
| pre-push | 保留选定范围验证 | 明确多 ref 边界；撤回默认自建多 ref 隔离验证平台 |
| 共享宿主协议代码 | 保留可复用部分 | 两宿主当前接受同一输出；不因 `--host` 未分支就强制增加适配类 |
| tag 固定版本 | 合法；SHA freeze 可选 | 不是错误；严格不可变需求下使用官方 freeze，版本升级分开审查 |
| ZCode 项目配置 | 先验证安装版本 | 不凭与本机不一致的网页删除项目配置或迁移全局设置 |

### F01/F02：拒绝根因与修复边界

最早的误拒绝来自两条已复现的路径：`cat/head` 的参数包含生成器路径，被当成生成器写操作；hook 以自身进程 cwd 选根目录，导致在 A worktree 校验本应属于 B 的 lease。另一个更严重的反例是外部绝对目标被路径过滤掉，不能把“未识别”解释为“没有写入”。PostToolUse 同样存在目录错误：工具 cwd 在子目录时，实际 Ruff 格式化了根目录同名文件。

修复应落在现有共享目标解析处：保留会话 cwd、工具有效 cwd 与目标仓库/worktree 的区别；按照真实宿主 payload 解释相对路径，逐个解析绝对目标和 patch 多文件目标。无法确认的受保护写入给出明确拒绝与恢复方法，不能误处理另一个同名文件。

命令识别只对真实执行位置和受支持的命令语法作判断。当前先按分隔符切字符串、再在任意参数找 `git`/生成器名字，会把引用内文本当命令；例如 `printf` 参数里的 `git reset --hard`。需要覆盖 `git -C`、选项、生成器真实调用以及 force refspec 等已确认场景。不要为此实现完整 shell：对无法可靠解析且涉及受保护操作的输入明确说明限制、要求等价的简单调用；普通只读文本不得被关键词拒绝。

Codex 官方明确说明 Pre/Post 并非覆盖所有工具执行路径，部分专用工具不经过此事件，`write_stdin` 也不会重新触发 Bash 检查。因此这些修复不能宣传为完整 sandbox；完整执行权限由宿主权限机制承担。[Codex hooks](https://learn.chatgpt.com/docs/hooks)

### PostToolUse：自动格式化是合理实践

Claude Code 官方把编辑后格式化作为直接示例，Ruff 官方也支持原地格式化。因此保留此功能有明确依据；之前把它整体列为删除候选过于绝对。[Claude Code 自动格式化示例](https://code.claude.com/docs/en/hooks-guide#auto-format-code-after-edits)、[Ruff formatter](https://docs.astral.sh/ruff/formatter/)

具体采用现有项目锁定的 Ruff，仅处理成功编辑、能确认归属的 Python 文件；传递参数列表并使用选项终止符，保证特殊文件名不会变成选项。同步执行有利于下一步读取获得格式化后的内容，不能仅为降低延迟改成异步写入。缺少运行时、失败、超时应有简短反馈；成功无输出是正常实践，不强制每次增加提醒。保留现有 CI/提交前检查，因为这个便利 hook 并不覆盖所有修改来源。

### F05/F06/F09/F12：修复可靠性，不增加治理平台

- **F05 测试环境：**`check-changed` 测试专用分支直接启动 pytest，缺少既有测试入口的 null Keyring 环境。优先复用已有隔离边界，或在现有共享执行处准确传递环境；先比较 marker、xdist 和测试选择行为，不能盲目换入口改变验收范围。
- **F06 协议：**非对象 JSON 不能静默转换成允许；对需要判断却缺少必要字段的操作明确返回当前宿主支持的拒绝协议。进程失败不等于可靠拒绝。强制 Pre 必须同步；validator 检查真实宿主支持的禁用/异步语义，不能将未知字段一概认作有效开关。当前 legacy `decision: block` 被实际宿主支持，迁移输出格式不是必改项。[Codex 同步、异步与输出协议](https://learn.chatgpt.com/docs/hooks)
- **F09 时间与取消：**给短时 hook 的 Git 查询设置有限等待，内部执行与清理预算小于外层 timeout；保留现有 formatter 进程组清理。验证支持平台上的取消行为；不能承诺外部强杀父进程时仍可由父进程自行清理。若验收发现孤儿写入，再选择宿主或平台可保证的生命周期机制。限制诊断输出，不新建跨平台进程管理框架，也不把产品验证任务套进 hook 的短超时。
- **F12 诊断：**报告事件、有效 cwd、目标 worktree、拒绝策略和正常恢复动作，避免输出包含秘密的完整命令。配置通过、宿主发现、已信任、实际触发和行为正确分别表述；修正“禁止 cd 即可解决身份”的建议。不新增永久 prompts 日志、receipt 或基准平台。

### F07：Ponytail 的具体保留方案

本机 Codex 4.10.0 / ZCode 4.9.0 的隔离探针确认：两会话共享模式；ZCode off 后普通提示恢复 full。本轮又确认 Codex 切换 ultra 只输出模式名称，compact 后状态回到 full。测试使用临时状态目录，没有修改用户真实状态。

上游存在相符的未关闭问题：全局模式污染 [#809](https://github.com/DietrichGebert/ponytail/issues/809)、ZCode 输出适配 [#798](https://github.com/DietrichGebert/ponytail/issues/798)、compact 注入干扰 [#821](https://github.com/DietrichGebert/ponytail/issues/821)；切换时注入规则的 [PR #853](https://github.com/DietrichGebert/ponytail/pull/853) 本轮检查仍未合并。上游报告的推测不等于本机事实，例如不能照搬“systemMessage 不受支持”的猜测。

1. 全局默认与会话选择分开；沿用文件存储，以宿主与安全编码的 session ID 定位、原子更新。显式存储 off；没有 session ID 时不回退写全局共享模式。
2. startup 初始化；resume/compact 保留已选模式，只恢复必要规则，不重新问候、不重置当前任务。显式切换注入对应规则，不能只有模式名称。
3. Codex 官方说明子代理使用父会话的 session ID，可直接复用，不新增父子映射服务。[Codex 事件与 session_id](https://learn.chatgpt.com/docs/hooks)
4. ZCode 使用实际支持的原生事件、变量和 JSON 输出，去掉伪装 Qoder 的环境变量；使用实际启用版本，停止扫描缓存选择最大版本。缺失插件有可见非阻断诊断。
5. 优先采用验收通过的上游修复；若尚未发布，使用可审查的固定版本 fork/受控适配。不得把直接改缓存当长期方案。每宿主只有一个有效注入入口；更新插件、切换安装来源和 trust 属于后续部署步骤，本轮不执行。

验收：两会话交错切换互不污染；off 后多轮保持 off；resume/compact 模式不变且继续原任务；切换包含实际规则；子代理继承；插件停用后不注入。偏好插件故障不得阻断用户任务。

### F08：ZCode 必须按实际版本验收

本机 ZCode 为 3.11.2，bundle 中有 workspace trust 与项目 hooks 加载路径，当前官网却描述项目 hooks 被忽略，内置旧说明又不同。证据支持“版本资料不一致”，尚不能证明本机当前会话实际触发或已经信任。[ZCode 官方 hooks 文档](https://zcode.z.ai/en/docs/hooks)

计划保留现有项目入口，先完成本机有效配置和真实事件验证；不得自动添加 trust、修改全局安全设置或凭网页迁移配置。使用临时测试文件执行读允许、受保护写拒绝、持有正确 lease 后通过、准确格式化和 Stop 结束；记录宿主版本和事件证据。

## 完整修改计划与顺序

所有实现都从失败反例开始，使用现有测试体系；每批完成局部检查、实际宿主验证以及对应风险的仓库检查。不要求先建新测试框架。

| 批次 | 覆盖 | 修改内容 | 完成标准 |
| --- | --- | --- | --- |
| H1：目标与拒绝正确性 | F01、F02、F06，部分 F12 | 共享 cwd/worktree/目标解析；命令执行位置识别；协议输入与同步配置校验；准确拒绝信息 | cat/head 生成器文件通过；真实受保护生成拒绝；A/B worktree 与绝对/子目录目标准确；printf 不误拒；force refspec、git -C 等按既定策略判断；无效输入不静默允许 |
| H2：自动格式化与短时运行 | F01、F09，Post/Stop | 保留 Ruff 和 Stop；成功编辑精确路径；有限 Git 等待、formatter 失败与取消处理 | 无关同名文件零变化；patch 多文件与特殊文件名正确；缺 Ruff/失败可见；超时与取消无迟到写入；Stop 可正常结束 |
| H3：本地交付链 | F03、F04、F05、F11 | 修 Keyring 隔离、最低版本声明、pre-push 范围说明；检查后安装已有 hooks；决定并记录 gitleaks 一致性 | 测试收集/worker/子进程不访问真实 Keychain；临时仓库 commit、部分暂存、commit-msg、push 实测；选定范围与未覆盖范围准确；安装不覆盖独有用户 hooks |
| H4：Ponytail | F07 | 会话状态、持久 off、切换规则、compact/resume、原生 ZCode、稳定插件来源 | 上述会话交错与生命周期矩阵通过；实际宿主注入一次；故障不阻断 |
| H5：宿主与 lease 收口 | F08、F10、F12 | 实际版本/trust 验证；lease 元数据竞态反例及必要修复；文档校正 | Codex/ZCode 实际触发证据；正确 worktree 授权；过期/并发回收/释放保持元数据一致；不夸大业务写入互斥能力 |

H1 优先，H2 紧随；H3、H4 可在各自范围独立交付，H5 收口。不要把所有插件上游修复都变成 #180 的无限期前置条件。H5 中的宿主实际触发检查应随 H1/H2 同时开展，不能留到最后才发现配置没有生效。

### 与最早 #180 的关系

hook 审计修复是独立范围，不能悄悄把它全部塞进 #180。先解决会阻碍执行或写错文件的 H1/H2，并确认当前执行宿主生效；之后按 #180 原来的三批继续：

1. **活跃工程说明与生成器精简：**更新指令；删除 visual-audit 仅 MJS 分支，保留现有 shell/TS 路径、输入校验、prototype freeze、其他输出 lease 保障；保留用户已有 AGENTS 修改。
2. **Web 导入边界：**退出混合 API barrel；ApiError/ApiValidationIssue 归入无 transport 依赖的单一模块；直达导入并收紧依赖图；清理旧研究路由转发，保持 API/OpenAPI 行为。
3. **最小真实验收：**Model/Paper/Manual 浏览器流程与 API 数值/刷新；Agent Web 真实 DI/read-only query，仅模型可脚本化；非空账本与 Agent 恢复证据，保留现有恢复验收与停止 writer 前提。

每批独立可审查 PR，满足对应检查和精确提交 CI，按原交付约定由用户合并后进入依赖批次。本轮没有开始这三批实现，也没有提交、推送或安装 hooks。

### 明确不加入默认修改计划的内容

删除 PostToolUse、删除 Ponytail、删除 lease、默认删除 Stop；完整 shell 解析/执行引擎；多 ref 隔离构建平台；分布式锁/fencing；为两个宿主强制增加类层次；永久会话日志/receipt/cache 平台；自动改 trust 或全局配置。没有明确消费者或失败证据，不以“最严格”为由加入。

SHA freeze 可作为单独的可重复性增强；gitleaks 升级单独验证规则变化。若未来要求全 ref 的本地硬约束，应单独确认合同并在 Git 原始输入边界实现，不能把当前局限掩盖成全覆盖。

## 证据与交付边界

本轮重新核实 Git 安装、pre-commit 实现、版本、官方资料与 Ponytail 上游状态，并执行隔离的模式切换/compact 探针。最早审计的 81 个测试及 115 个 subtests 通过、validator 通过属于上一轮结果，不代表上述尚未实现的修复已验收，也不替代真实宿主执行。

本轮只新增这份研究与修改计划；未修改源代码、hook 配置、用户 trust、插件安装或真实状态。部署时保存现有配置与启用版本，分宿主验证并保留正常回退路径；不使用跳过 hooks/no-verify 掩盖失败。
