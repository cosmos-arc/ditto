# Ditto Agent Hooks：官方语义与优化建议

调研日期：2026-09-06。范围：Codex、Claude Code 官方 hooks 文档与 Python 子进程文档；不是全库审查。以下区分文档事实和针对 Ditto 的工程建议。

## 官方语义

- **Codex**：命令 hook 默认同步等待；`Stop` 的 `decision: "block"` 会生成续跑提示，`stop_hook_active` 表示已经由 Stop 续跑。Stop 的成功输出须为 JSON，不能直接打印测试日志。[官方 Stop](https://learn.chatgpt.com/docs/hooks#stop)
- **Codex**：异步 hook 只能报告，不能阻止或修改触发操作；每会话最多 8 个并发，结束会话会取消未完成任务。修改为异步会改变强制检查的语义。[官方异步约束](https://learn.chatgpt.com/docs/hooks#run-hooks-in-the-background)
- **Codex**：配置层的匹配 hooks 合并执行，可能并发；项目配置加载不等于本轮编辑范围。命令运行于会话 cwd；从 Git 根解析项目脚本可以兼容子目录启动。变更 hook 定义后需要重新信任。[官方配置与信任](https://learn.chatgpt.com/docs/hooks#where-codex-looks-for-hooks)
- **Codex**：PreToolUse 拒绝用 `hookSpecificOutput.permissionDecision: "deny"` 和理由，或 exit 2/stderr；其 `continue: false` 目前不支持，不能作为拒绝协议。[官方 PreToolUse](https://learn.chatgpt.com/docs/hooks#pretooluse)
- **Claude Code**：Stop 是回复结束事件，不代表提交或整个项目完成；检查 `stop_hook_active` 防止无限续跑。当前文档还描述连续 8 次阻断上限，不能推断 Codex 也有该上限。[官方 Stop](https://code.claude.com/docs/en/hooks#stop)
- **Claude Code**：格式化示例限定在 `PostToolUse` 的 `Edit|Write`；shell 也能修改文件，因此这种匹配不保证覆盖所有改动。[官方匹配指南](https://code.claude.com/docs/en/hooks-guide#filter-hooks-with-matchers)
- **Python**：`subprocess.run(timeout=...)` 超时会杀掉并等待直接子进程；`Popen.communicate(timeout=...)` 自身不杀进程，需显式清理。`start_new_session=True` 可在 POSIX 创建独立会话。[官方 subprocess](https://docs.python.org/3/library/subprocess.html)
- **Python**：`os.killpg` 向指定进程组发信号，限 Unix。[官方 killpg](https://docs.python.org/3/library/os.html#os.killpg)

## 针对 Ditto 的建议

下面是依据上述事件语义及本机复现作出的设计判断，**不是厂商规定所有 Stop 都不得运行测试**。

| 位置 | 建议职责 | 原因 |
| --- | --- | --- |
| PreToolUse | 保留快速、确定的危险操作与生成物写入策略；准确输出 deny JSON | 必须在操作前做决策；不要在此启动环境安装或测试 |
| PostToolUse | 只格式化本次工具实际编辑的受支持文件，设置短超时 | 整库格式化会修改无关文件，并将重复成本乘以工具调用次数 |
| Stop | 仅快速检查、读取真实验证证据或提示缺少证据；不自动启动全量 CI | 每轮回复均可能触发；已有脏文件会把普通讨论也变为长检查 |
| 显式任务 / CI | 执行 `check-changed`、完整质量门和提交前 CI | 保留验证要求，并让长任务的进度与失败可见 |

1. **移出重任务**：目前仅 AGENTS.md 脏改动就触发全量 `pixi run -e dev check`，同步 Stop 的 900 秒预算会长时间占住回复完成阶段。增大超时无助于交互；这是当前主代理提供的复现观察，不是本文独立测量。
2. **避免续跑循环**：如保留一次提醒型阻断，先检查 `stop_hook_active`；第二次允许结束并明确未验证，不能把未执行、超时或跳过写成通过 receipt。
3. **区分范围**：仓库 dirty set 不是当前任务 changed set；已有改动、另一任务与同仓库会话都可能贡献 dirty files。格式化以实际工具输入为准；验证证据必须匹配实际 checkout、文件内容与命令。
4. **避免重复**：仓库配置用一个来源，检查用户级与插件级是否重复注册相同职责；不要增加一套与 Pixi/CI 平行的任务 DAG。
5. **超时分层**：建议轻量 Stop/PreToolUse 目标在秒级，格式化有短预算；脚本内部超时小于宿主超时，预留退出和输出时间。这些预算是本项目建议，需用本机测试确定。
6. **清理子孙进程**：若启动 Pixi 等多层进程，不能假设杀掉包装进程会清理整棵树。必要时用独立进程组，超时先 TERM、短等待后 KILL，再 wait；只清理本次创建的进程组，不做全局 pkill。
7. **可观测性**：stdout 留给协议 JSON；诊断写 stderr 或任务隔离日志，记录事件、cwd、命令、耗时和退出码；保留输出长度上限，不记录秘密。长任务直接在工具终端执行以便看见进度。
8. **最小验证**：覆盖 Stop 无改动/已有无关改动/重入，PreToolUse deny 协议，格式化路径与超时，以及超时后无残留子进程；验证配置的 timeout 大于内部总清理预算。
9. **不自动重新启用**：保留用户已关闭的 Ditto hooks 及现有 trust；代码验证完成后再由用户审阅当前定义。不要通过更改 trust 数据或 bypass 参数规避审阅。

## 适用性限制

官方文档为调研日页面，可能包含晚于本机二进制的能力；采用新字段前应对照本机版本、schema 与实测。上面的官方语义调研本身不替代本机验证；本机诊断与实测见下节。


## 本机诊断与已实施改动

主代理在独立 worktree `../ditto-agent-hooks`、分支 `codex/optimize-agent-hooks`
实施修改；未重新开启用户关闭的 hooks，未更改 trust，也未覆盖主目录已有的 AGENTS.md 修改。

### 根因证据

- 原 Stop 在调用 `stop_decision` 前无条件生成 manifest，包含 Pixi 工具版本探测；干净仓库也会启动项目工具。
- 主目录只有一处已有 AGENTS.md 修改，分类为 Harness，按照根验证矩阵触发全量 `pixi run -e dev check`。
- 原脚本实测超过 15 秒仍无 stdout/stderr；本次探测进程树包含 Pixi、type.py、basedpyright、Node。探测到时只终止本次创建的进程组。
- 检查输出原本由 `capture_output=True` 缓冲；900 秒宿主超时没有为用户提供检查进度。失败会返回 Stop block，再次续跑时仍先执行验证才检查重入标志。
- 显式 `check-changed` 原先不保存或复用 Stop 的成功收据，手动验证后也可能再跑一遍。
- Ponytail 4.9.0 的 hook 是 SessionStart、SubagentStart、UserPromptSubmit，预算各 5 秒，没有 Stop；它与这里的结束验证并非同一个触发点。用户级 Claude settings 中没有额外 hooks。

### 实施方案与测量

| 部分 | 改动 | 实测或验证 |
| --- | --- | --- |
| PreToolUse | 保留危险命令、受保护路径 lease；不改变拒绝策略 | 真入口测试覆盖允许普通命令、拒绝危险命令和未持有 lease 的结构化写入 |
| PostToolUse | 一次精确文件 Ruff format；Pixi --as-is；内部 5 秒预算和进程组清理；失败非阻断反馈 | 真实格式化 0.15 秒；超时测试确认后代进程不会继续写文件 |
| Stop | 先检查重入；只读 Git 改动并提示；宿主预算从 900 秒降到 3 秒 | 在原主目录已有修改条件下，Codex 0.25 秒、Claude 0.12 秒；未启动 Pixi、未写验证收据 |
| check-changed | 完整验证保留，流式显示输出；复用同一份真实成功收据逻辑 | 相同 manifest 两次显式调用只验证一次；失败不得缓存成成功 |

这些是单次本机测量，不是性能保证。生命周期回归测试覆盖无修改、已有修改、Stop 重入；先观察旧实现失败，再修改实现。

### 独立仓库问题（首次检查）

当前 HEAD 没有跟踪根 `package.json`，`.gitignore` 中 `/*.json` 把它忽略了；主工作目录实际存在该文件。
全新 worktree 的 `harness-check` 因缺失 JSON 失败，`bun-install` 因找不到 package.json 失败。
本次仅复制主目录已有清单到验证 worktree，安装现有冻结锁文件依赖；没有增加依赖或修改锁。
该本地验证前提不能证明干净 checkout 可构建。已在同一分支补上清单跟踪和 ignore 例外，未变更依赖版本或锁文件。


### 首次检查结果

- RED：旧实现的 Stop 三种场景均超出测试预算；显式成功收据复用和禁止格式化时安装环境的回归测试失败。
- GREEN：`pixi run --locked -e dev harness-check` 通过，包含 84 项单元测试、15 项 Agent Eval、Harness schema 校验、类型检查、技术栈清单和文件大小门禁。
- `pixi run --locked -e dev pre-commit run agent-harness --files .codex/hooks.json .claude/settings.json tooling/agent_harness/hook.py` 通过。
- Harness Ruff lint / format-check 与 `git diff --check` 通过。
- 新登录 zsh 中 `codex --version` 返回 `codex-cli 0.153.3`，命令路径为 `~/.local/bin/codex`；终端初始化另有 Starship 在 TERM=dumb 下的提示，不影响 Codex 命令解析。

- 全量 `pixi run --locked -e dev check` 未完成，不能标记通过：lint、format-check、后端类型检查通过；pytest 到 99% 后停在 `apps/backend/tests/registry/test_config_data_unit.py::TestConfigProviderData::test_data_source_settings_provider`。对唯一仍运行的 worker 采样发现主线程在 macOS `SecItemCopyMatching → SecKeychainItemCopyContent → SecurityServer → mach_msg` 等待。它进入了真实系统 Keychain；未判断或修改具体权限，也未读取秘密。最终只终止本次检查独立进程组，退出 143。它解释了全套检查除了慢以外还可能无限等待的风险；不证明用户原先那一轮一定卡在相同测试。
- 独立 `pixi run --locked -e dev check-web` 失败，Web lint/type 通过；Vitest 共 208 文件，197 通过、11 失败；1757 测试中 1726 通过、31 失败，包含多项 5000ms 超时。本次未修改这些页面或测试；由于未在基线独立复跑，不能宣称全部是既有失败或已定位原因。
- 完整门禁未通过，未创建全库验证通过收据；专项门禁通过不替代 CI。

复现日志保留在本机 `/tmp/ditto-agent-hooks-check.log`、`/tmp/ditto-agent-hooks-web.log`、
`/tmp/ditto-agent-hooks-harness-check.log` 和 `/tmp/ditto-agent-hooks-pytest-final-sample.txt`。


## 后续修复：同一 hooks 分支

- 根 `package.json` 已加入 Git，`.gitignore` 为它添加精确例外；回归测试使用 `git check-ignore --no-index`，修复前返回被忽略，修复后通过。没有升级或新增依赖。
- `apps/backend/tests/registry/conftest.py` 为 registry 测试临时设置 keyring 自带 null backend，结束后恢复原 backend。使用真实 ConfigProvider，生产密钥读取保持原样。真实系统 backend 被故障探针替换为立即失败时，修复前目标测试失败，修复后 registry 49 项全部通过（3.47 秒）。
- 完整复测进一步发现收集阶段也会触发真实 Keychain。因此 `scripts/test.py` 在 pytest 启动前固定子进程的 null backend，覆盖收集、xdist 和子进程；不改应用正常运行的 backend。黑盒回归测试在入口执行前检查隔离并真实启动 Python 子进程读取 null backend，同时验证退出码传递；修复前失败，修复后相关 6 项测试通过。
- Web 同一工作区、相同 5 秒测试预算下单独复跑，208 个文件、1757 项测试全部通过（53.52 秒）。前次检查同时运行后端 8 个 pytest worker 和 Web；结果支持资源争用解释，不能将其计为 31 个已确认的 UI bug。没有修改页面行为、放宽断言、增加超时或重试。
- 测试指南记录系统密钥隔离及本机顺序验收约定；后续完整门禁按根 DAG 执行。


### 修复后完整验收

`pixi run --locked -e dev check` 已以退出码 0 完成：后端 15,471 项测试通过
（186.96 秒），Web 208 个文件 / 1757 项测试通过，架构、契约、Harness 门禁通过；
Harness 包含 85 项测试和 15 项 Agent Eval。
`pixi run --locked -e dev type --tests`：0 errors、0 warnings。
这取代上文首次检查未完成的状态；不是完整 `ci` 或生产发布验收。

修复在 `codex/optimize-agent-hooks` 独立 worktree 完成。变更不会启用或修改用户的
hook trust；主目录原有 AGENTS.md 改动保留。提交与 PR 的状态以 Git/GitHub 为准。
完整检查日志：`/tmp/ditto-hooks-fixed-check.log`；测试类型日志：
`/tmp/ditto-hooks-fixed-test-types.log`。

本次全部变更文件的 pre-commit 通过（包括 Harness、Ruff、Pyright、秘密扫描）；日志：`/tmp/ditto-hooks-fixed-precommit.log`。`git diff --check` 与暂存区版本也通过。


### PR 前完整 CI

实际执行 `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring pixi run --locked -e dev ci`：
源码及测试类型、后端覆盖率、PIT、架构、契约、跨栈、Harness 通过；覆盖率套件
16,492 passed / 73 skipped，覆盖率 89.41%，门槛通过；PIT 401 passed。
完整 CI 在 `security-supply-chain` 的 OSV 扫描处退出 1，现有依赖 / sandbox SBOM 存在漏洞，
后续 artifact-gate 未运行；bun.lock、pixi.lock 和 sandbox SBOM 均未在本次修改。
另外，Docker 内 Git 历史扫描未挂载 worktree 所指向的公共 Git metadata，出现无法识别
Git 仓库的错误，不能把它的零提交扫描视为有效历史安全证据。
本次创建 Draft PR 并保留上述阻塞，不升级依赖或更改安全门槛来换取通过。
CI 日志：`/tmp/ditto-hooks-pr-ci.log`。
