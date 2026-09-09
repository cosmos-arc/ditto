# Ditto AI Coding 基建审视与精简建议

调研日期：2026-09-06。工作区基线：`688386be`。优先级按用户要求：模型与流程负担 → CI 与门禁 → 自建脚本必要性；技术栈以适配度为准，不以工具数量为目标。

**建议保留现有产品技术栈，显著缩减编排模型行为的流程，重整 CI 的触发与执行环境。** 当前有足够证据支持精简；主要依据是本库真实的命令漂移、无效阻断、重复验证和 CI 失败，而不是假定新模型已经不会犯错。

本轮只新增研究文档，没有修改 skills、hooks、质量策略、依赖、CI、GitHub 配置或产品代码。下文是可审阅的建议，不是已生效的新规则。

## 判断依据

近期一手资料支持让模型自行选择实现路径，减少通用流程指令，保留项目知识和明确验收。OpenAI 当前指南特别建议审计 skills/AGENTS 中的冲突，按变更影响校准测试，避免无新证据的重复验证。[OpenAI 官方指南](https://developers.openai.com/api/docs/guides/latest-model)

Anthropic 2026-07-24 报告其内部对新模型大幅删减系统提示，并将部分 review/verification 改为按需 skill。这是厂商内部经验，不能把其删除比例作为 Ditto 的指标。[Anthropic 原文](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)

独立实验的结论并非“所有指导都无用”：AGENTS.md 研究 v2 未发现显著正确率收益，并观察到成本增加；另有失败驱动的指导优化在特定模型上取得收益。模型、任务、内容都影响结果，应在本项目上验证。[完整外部调研与实验局限](2026-09-06-ai-coding-harness-industry-research.md)

本报告采用三种去留标准：

| 内容 | 应由谁负责 | Ditto 例子 |
| --- | --- | --- |
| 可以明确判错、失败代价高的不变量 | 类型、测试、约束、运行时边界 | PIT 时间可见性、账本守恒、API 兼容、依赖方向、秘密泄漏 |
| 模型不能从通用知识可靠推导的项目事实 | 就近文档；必要时短 skill | source snapshot 传播、composition root、契约生成入口、页面状态定义 |
| 实现路径、阅读顺序、角色数量、审美判断 | 模型根据任务选择 | 是否画组件树、何时写普通 UI 测试、几轮设计、是否委派审查 |

减少第三类的硬规定，不等于取消第一类的验证。

## 1. 最应先解决的是指令失真和流程膨胀

本库有 **11 个项目 skills**，不是 12 个。`.agents/skills` 下 52 个 Markdown 文件共 **5,814 行**，其中 `ditto-design-cycle` 为 **2,984 行**。这些文件并不都会在每轮进入上下文；数字反映维护体量，不能当作实际 token 消耗。真正的问题是触发后可能加载的流程及其互相矛盾。

| 发现 | 证据 | 建议 |
| --- | --- | --- |
| skill 引导执行不存在的命令 | [app-dev:44](/Users/chevy/Desktop/code/ditto/.agents/skills/ditto-app-dev/SKILL.md:44) 和 :47 要求 `bun run check/ci`，根和 Web package.json 都没有这两个入口 | 删掉重复命令矩阵，统一指向 Pixi 的实际入口；这是事实漂移，应先处理 |
| 参考流程要求组件方案再次确认 | [architect.md:53](/Users/chevy/Desktop/code/ditto/.agents/skills/ditto-app-dev/references/architect.md:53) 要求组件架构阶段之后必须再次确认；本轮未回放实际会话中断 | 普通常规实现交给模型决定；真正缺失的产品决定或未授权副作用才提问 |
| 主观分数成为硬门槛 | [execution-flow.md:174](/Users/chevy/Desktop/code/ditto/.agents/skills/ditto-design-cycle/references/execution-flow.md:174) 以“气质分 7.5”决定能否继续 | 保留审美描述、截图和用户反馈，删除自评分数决定 pass/fail 的机制 |
| 小范围反馈也携带角色与交付仪式 | [execution-flow.md:337](/Users/chevy/Desktop/code/ditto/.agents/skills/ditto-design-cycle/references/execution-flow.md:337) 指定七角色；:275 起还包含 commit、tag、报告和合同状态推进 | 根据实际独立问题委派；只有任务要求版本化原型交付时才推进生命周期 |
| 验证过程被重复规定 | [AGENTS.md:79](/Users/chevy/Desktop/code/ditto/AGENTS.md:79)、test-first、architecture-change、api-contract、app-dev 都再次规定 RED/GREEN 和扩大验证 | 只保留一处风险策略；bug 保留复现与回归测试，PIT/财务/交易保留敏感测试；普通可逆改动允许选择合适验证方式 |
| 内容可用性未被形式门捕获 | 本轮运行 validator 返回通过，但上述缺失命令仍在；[verify.md:80](/Users/chevy/Desktop/code/ditto/.agents/skills/ditto-app-dev/references/verify.md:80) 还指向不存在的 rules 文件 | 去掉旧规则和重复事实源，保留少量链接/入口可用性检查；不要新造一个理解全部 prose 的校验系统 |

`validate.py` 目前强制 frontmatter 只能含 name/description、skill 不超过 120 行、Claude 只能开启指定插件，以及精确的 hook 形状。[metadata 限制](/Users/chevy/Desktop/code/ditto/tooling/agent_harness/validate.py:248)、[插件集合限制](/Users/chevy/Desktop/code/ditto/tooling/agent_harness/validate.py:392)

这些规定保护了“当前配置长什么样”，但不能证明指令仍正确。建议保留必要字段、同步完整性、hook 目标存在、真实危险边界等检查；宿主支持的额外 metadata、用户插件选择、具体行数不再作为产品正确性的硬门。跨宿主字段须分别遵循其 schema，不能机械透传。

### 11 个 skills 的去留

| Skill | 建议处置 | 应保留的内容 |
| --- | --- | --- |
| `ditto-pit-safety` | 保留，按时间语义实际变化触发 | knowledge/publication cutoff、snapshot、窗口边界、future sentinel；单纯目录命中不应决定全部测试范围 |
| `ditto-api-contract-change` | 退役独立 skill，知识迁入契约文档 | contracts/AGENTS 保留短路由和不变量；生成事实源、兼容语义、运行时校验及操作说明在契约文档各保留一份 |
| `ditto-architecture-change` | 退役独立流程包装 | 在既有架构文档保留 provider/consumer、能力归属、DI 与依赖边界；不要求每次按固定模板先声明 |
| `ditto-test-first` | 退役项目包装 | 将风险与回归证据要求收在一处；用户明确要求 TDD 时使用通用工具流 |
| `ditto-change-review` | 退役项目包装 | 原生 review 查阅简短 Ditto 风险清单；PIT、会计、接口风险不能随包装一起丢掉 |
| `ditto-app-dev` | 普通 React 开发直接交模型 | 状态/adapter/token 事实留在 Web AGENTS；视觉对齐操作放按需文档 |
| `ditto-design-cycle` | 退役独立 skill，保留按需设计文档与真实工具 | 产品审美、目标 viewport、真实截图和交互反馈；删除固定角色、主观分数门槛和每轮仪式 |
| `ditto-page-contract` | 退役独立 skill，保留合同规范、CLI 和消费者 | 现有 JSON/generator/consumer 继续工作；普通页面小改不重新走创建和提升流程 |
| `ditto-product-discovery` | 退役独立 skill，项目事实融入现有产品文档 | 产品约束、研究来源、需要验证的假设；不默认生成六类文件和 manifest |
| `ditto-product-arch` | 退役独立 skill，保留产品规格和领域词汇 | shell/page/state 词汇、实际受影响的 IA 和交互状态；不强制全套蓝图流程 |
| `ditto-quality-eval` | 退役独立 skill，必要时查阅普通评估方法文档 | 用户要求历史可比评分时采用版本化 rubric；普通审视直接输出事实、风险和建议 |

建议目标收敛为 **PIT 一个项目 skill，其余项目知识通过就近文档读取**。可以从四个通用开发包装（architecture-change、test-first、change-review、普通 app-dev）开始实施，再处理包含工具的目录，但**不要直接删除它们整个目录**。`apps/web/package.json` 正在调用 skill 内的 visual-audit、page-contract generator，prototype gate 也调用 design-cycle 内的脚本。先保留或迁移这些真实消费者，再删除文字流程。[Web 工具入口](/Users/chevy/Desktop/code/ditto/apps/web/package.json:23)

这修订了初版对 API skill“保留并压缩”和其他几项“按需 skill”的建议：知识和工具有价值，并不意味着需要独立 skill 入口。API 规范已大量存在于 contracts/AGENTS，设计与产品已有自己的事实源，保留双份路由与流程增加维护点。PIT 暂保留独立入口，是因为跨 data/features/strategy/backtest 的时间语义检查具有隐蔽失败模式；它也应保持短小，并接受真实任务结果的检验，而非永久豁免精简。

迁移遵循四个边界：

- **AGENTS**：只写适用范围、少数关键不变量和触发式文档入口；详细规范放在相关文档，不把原 skill 全文搬进常驻上下文。
- **文档**：保留项目独有事实、决定的理由、易踩坑事项和必要工具用法；源码/配置可直接查到的清单不再复制。
- **代码和工具**：schema、生成器、运行时校验、测试及明确门禁保持可执行；独立 skill 的退役不改变这些行为。
- **直接删除**：固定角色、主观分数关卡、阶段仪式、重复测试矩阵和无新决策的确认。将它们改名为文档并不能减负。

其中 quality-eval 的固定权重与报告结构，只在用户需要与旧报告比较时保留为可选评估口径。一般架构/质量审视由模型按问题选择证据和输出，不再默认构造雷达分数或全套章节。page-contract 的迁移则需要同步 package scripts、generator/schema 路径、lease registry 和相关测试；它是一项可验证的工具搬迁，不能靠删除 SKILL.md 自动完成。

具体落点优先使用已有文档：

| 退役入口 | 知识落点 | 迁移时的取舍 |
| --- | --- | --- |
| API contract | [contracts/AGENTS.md](/Users/chevy/Desktop/code/ditto/contracts/AGENTS.md)、[cohort 兼容说明](/Users/chevy/Desktop/code/ditto/contracts/cohorts/README.md)、Web 架构文档 | 保留语义破坏性变更（单位、币种、时区、时间戳含义、未知 enum）及高风险响应运行时校验；去掉重复过程规定 |
| Design cycle | [DESIGN.md](/Users/chevy/Desktop/code/ditto/apps/web/DESIGN.md)、[产品设计标准](/Users/chevy/Desktop/code/ditto/apps/web/docs/designs/specs/00_ditto_product_criteria.md)、Web 测试文档 | 设计意图、视口与实际交互验证留存；角色、分数和阶段仪式删除 |
| Page contract | [合同 JSON 目录](/Users/chevy/Desktop/code/ditto/apps/web/docs/contracts/pages)、[Web 测试文档](/Users/chevy/Desktop/code/ditto/apps/web/docs/engineering/testing.md) | 机器合同仍是事实源；文档仅说明实际 CLI/刷新操作；脚本归入现有 Web scripts 后再删原入口 |
| Product architecture | [PRODUCT.md](/Users/chevy/Desktop/code/ditto/apps/web/PRODUCT.md)、[产品信息架构](/Users/chevy/Desktop/code/ditto/apps/web/docs/designs/specs/01_product_information_architecture.md) 及现有页面/状态/流程规格 | 保留项目已经作出的决定与词汇，不迁移六阶段和固定产物清单 |
| Quality eval | [测试指南](/Users/chevy/Desktop/code/ditto/docs/engineering/testing.md)、[Web 架构说明](/Users/chevy/Desktop/code/ditto/apps/web/docs/engineering/frontend-architecture.md)；历史报告继续保留 | 证据型审视直接交模型；固定权重不进 AGENTS，无历史比较需求就不必迁移评分框架 |

这些落点也需清理陈旧内容：现有 Web 架构/测试文档仍出现 `bun run check/ci`，不能因为从 skill 迁入 docs 就视为已正确。质量 rubric 中任意覆盖率目标和与当前依赖规则冲突的条目也应舍弃，不在新位置继续执行。

全局 skills 是另一层来源。全局 code-review 默认双轴并行（缺 spec 时可跳过 Spec）、全局 TDD/prototype 等，可能与项目流程叠加；删除仓库技能不会清除这些全局行为。本轮只读核对了相关说明，未修改用户全局技能或插件。

## 2. CI 首先需要恢复可信反馈，再做分层

检查了 GitHub 最近 30 次运行，并进一步读取近期 CI 的 jobs/失败日志。最新有记录的 main CI 是 [run 34007684137](https://github.com/cosmos-arc/ditto/actions/runs/34007684137)，对应 `4cff1fe8`；当前工作区只多一笔 AGENTS 文档提交，受审 CI/tooling/Pixi 文件与该运行版本一致。该运行不等于当前全部产品测试的独立复跑。

| 实际观察 | 意义与处理 |
| --- | --- |
| 后端 coverage 步骤约 44 分 35 秒，在 86% 左右被取消；job 约 45 分 17 秒，配置预算 45 分钟 | 当前完整反馈未完成，后续 PIT 未运行、coverage 文件未生成。应定位慢测试/覆盖率成本，不能简单把超时改长或删除断言 |
| Harness 85 项测试中 5 个错误，日志为缺少 `bun` | architecture-harness job 只装 Pixi，没有 setup-bun；这是环境准备错误，不能据此认定业务代码失败 |
| System E2E 缺 `chromium_headless_shell` | 恢复匹配版本的浏览器准备，再判断 E2E 本身的质量 |
| Web architecture 报 `Cannot read properties of undefined (reading 'readFile')` | 工具链/解析器故障待定位，不能当成已发现依赖方向违规 |
| Windows bootstrap 下载 oasdiff Windows archive 失败 | 核实固定版本实际发布资产与 bootstrap，不要让无关 smoke 被不需要的工具下载绑住 |
| CodeQL 上传因 Advanced Security 未启用失败 | 与仓库实际可用能力对齐；不要把无能力执行的上传作为永久红门 |
| OSV/Trivy 有漏洞报警 | 与以上环境错误分开分流，核对具体依赖、可达性和修复版本；不得为了绿色整体关闭安全扫描 |

最近五个已完成 CI 均为失败，中间另有一次取消：

| Run | 事件 | createdAt → updatedAt |
| --- | --- | --- |
| [34007684137](https://github.com/cosmos-arc/ditto/actions/runs/34007684137) | main push | 45 分 52 秒 |
| [34007623658](https://github.com/cosmos-arc/ditto/actions/runs/34007623658) | PR | 45 分 26 秒 |
| [34005800092](https://github.com/cosmos-arc/ditto/actions/runs/34005800092) | PR | 45 分 30 秒 |
| [33970262880](https://github.com/cosmos-arc/ditto/actions/runs/33970262880) | main push | 45 分 28 秒 |
| [33970070224](https://github.com/cosmos-arc/ditto/actions/runs/33970070224) | PR | 45 分 28 秒 |

这些是包含排队/收尾的 run 生命周期时长，不是纯测试耗时；短期样本也不代表长期成功率。并发 job 耗时不能相加后当作用户等待时间。详细证据可查看 [backend coverage job](https://github.com/cosmos-arc/ditto/actions/runs/34007684137/job/101417834624)、[Harness job](https://github.com/cosmos-arc/ditto/actions/runs/34007684137/job/101417834726)、[system job](https://github.com/cosmos-arc/ditto/actions/runs/34007684137/job/101417834744)。上述日志表明当前验证链没有产出完整通过证据。

另一个比减门更重要的盲区：`tooling/dev/tests`、`tooling/contracts/tests`、`tooling/quality/tests` 共 **14 个 Python 测试文件**未进入默认 pytest `testpaths`，也未在审查到的根 DAG/CI 中获得统一显式执行。它们覆盖 supervisor、契约生成/下载和 coverage policy 等自建基础设施。[pytest 配置](/Users/chevy/Desktop/code/ditto/pyproject.toml:289)

Harness unittest、Web tooling 的 JS 测试、release/security 的显式测试应与这 14 个文件区分。不能用现有 Harness 绿灯代替全部基础设施的回归证据。保留下来的脚本，其有价值测试应接入适当的 changed-scope job；无需再制造一套元测试框架。

与此形成对照的是 [repository policy test:43](/Users/chevy/Desktop/code/ditto/tooling/release/tests/test_repository_policy.py:43)：它要求 job 集合精确相等、所有 semantic jobs 都没有 `needs`、trigger 不配置 `paths`、gate script 不出现 `skipped`。这会阻止合理的构建产物复用和范围分流。应测试“需要的验证一定执行、失败不能变绿、权限不扩大”等行为，解除精确结构锁定。

### 已确认的范围扩大与重复

- [AGENTS.md:96](/Users/chevy/Desktop/code/ditto/AGENTS.md:96) 要求每次提交/PR 前运行完整 `ci`；但该命令包含安全扫描和 Docker 制品验证。这使普通开发默认承担发布级准备。
- `check-changed` 对 `AGENTS.md` 或单个 skill 编辑返回根 `check`；对 `packages/data/README.md` 返回 `check-backend` 加全部 PIT。本轮使用真实分类函数复现，未运行那些大套件。[分类](/Users/chevy/Desktop/code/ditto/tooling/agent_harness/hook.py:586)、[命令展开](/Users/chevy/Desktop/code/ditto/tooling/agent_harness/hook.py:726)
- pre-commit 的 pyright hook 没有 Python 路径筛选，且 `pass_filenames: false`；Ruff 的 Pixi 入口含 `.`，接收文件参数也不会自然变成只查修改文件。[pre-commit 配置](/Users/chevy/Desktop/code/ditto/.pre-commit-config.yaml:49)
- Web `web-ci` 同时依赖单测和 coverage；它们分别运行同一 `src` 测试套件。`type` 与 `build` 也都执行 route generation/`tsc -b`。后者可能已有增量收益，不能把每个重复入口都算成完整重复成本。[Pixi Web DAG](/Users/chevy/Desktop/code/ditto/pixi.toml:244)、[Web scripts](/Users/chevy/Desktop/code/ditto/apps/web/package.json:8)
- CI 每次 PR/main push 无条件安排多个环境及制品链；仓库已有 bootstrap，workflow 又手写 oasdiff 下载。应先统一职责与入口，再考虑缓存或分片。
- container smoke 与 security workflow 分别构建镜像，构建参数也不完全相同。优先让一次构建的同一不可变 image digest 接受 smoke、扫描和 SBOM，既减少构建，也使验证对象一致。
- backend coverage 默认包含 PIT，之后再执行一次 PIT。若第二次旨在验证串行/隔离语义，应写明并保留；否则拆分套件、合并覆盖结果，避免为了减少重复把关键测试漏掉。

Pixi 在同一 DAG 中对共享依赖的处理，与多个独立入口/进程重复运行是两回事；不能仅按 TOML 引用次数推算浪费。

### 建议的检查安排

| 时机 | 默认责任 | 可省去的负担 |
| --- | --- | --- |
| 模型修改过程 | 目标测试、相关类型/lint；视觉改动用截图或交互验证 | 每个阶段重新跑 aggregate、反复提交 RED/GREEN 报告 |
| 本地提交 | staged 文件的格式、lint、秘密/冲突检查 | 文档修改跑全库类型；普通提交默认 Docker/全量 CI |
| PR 必需检查 | 明确影响范围内的测试与类型；关键依赖方向、API/PIT 的相应证明；稳定汇总结果 | 同一套 Web 单测再无条件跑一遍；纯文档触发全部栈 |
| 共享基础设施、依赖、接口、跨栈改动 | 保守扩大验证，覆盖间接消费者；相关工具先 bootstrap | 凭简单文件后缀就漏掉配置和生成链影响 |
| 定期与发布 | 完整回归、mutation、较广平台矩阵、制品构建/扫描和 cohort | 将所有发布证明压到每个本地 commit |

初期只对纯文档和已明确可独立验证的 Harness prose 做保守分流，其余代码继续较宽检查；建立漏检证据后再细分，避免用另一套复杂影响图替换旧复杂度。高风险财务/PIT 的核心回归仍应在相关 PR 阻断，不能全部移到 nightly。artifact、lock、release 配置变化也应在 PR 提前验证相应制品。

保留 `ci-gate` 的 `always()` 和上游结果校验。当前脚本锁死“12 个 success”，引入条件 job 后需区分明确不适用、失败/取消、应执行却缺失，不可简单接受所有 skipped。GitHub 对跳过 workflow 和跳过 job 的状态语义不同。[GitHub required checks 文档](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)

只读 branch protection 查询返回 HTTP 403，提示需要更高套餐或公开仓库。因此本轮**无法核验** GitHub 是否实际把 `ci-gate` 配为必需条件，不能由 YAML 存在推断已受保护。

## 3. 自建脚本：按职责精简，不按行数删除

按 tracked 文件统计、不含测试，`tooling/agent_harness` 有 3,477 行 Python；架构 smell 单脚本为 3,522 行；contracts tooling 有 2,471 行代码；Web scripts 有 11,572 行，其中包含 2,713 行 generated config，不能全部算手写维护负担。这些数字是定位入口，未证明相同比例都可删除。

| 脚本/机制 | 判断 | 具体处置 |
| --- | --- | --- |
| `scripts/architecture/check_architecture_smells.py` | 混合了重要边界和低价值风格判断 | 保留真实 import、composition、环境读取等可证伪约束；将 800 行、helpers/utils 名称、通用词禁令、包初始化文件一律声明 `__all__` 降为 review 建议；与 import-linter 已覆盖的规则合并 |
| f-string/业务词文本匹配 | 有可复现误报 | 本轮仅一行注释中的 `logger.info(f...)` 就被判失败。优先删掉这种硬门；若确需日志规则，验证 Ruff 的现有规则对 Loguru 的实际覆盖，不另外扩大自写 parser |
| `agent_eval.py` + 静态 cases | 有效的 policy grader 回归，不能测真实 agent 成效 | 主函数仅加载预填 JSON，比较 `case.attempt` 与 expected；改为普通 policy 单测并准确命名，不将通过次数当作模型可靠性。[入口](/Users/chevy/Desktop/code/ditto/tooling/agent_harness/agent_eval.py:696) |
| `hook.py` 验证 receipts | 有真实去重价值，也有较多输入/版本/路径维护 | 先修分流和重复入口，测量实际命中收益。若删除收据机制，应同时停止跨任务复用通过结论，改为运行必要检查；不能去掉 fingerprint 却继续信任旧收据 |
| `lease.py` 跨 worktree 单写者 | 保护目标合理，但仓库全局锁范围值得复评 | 独立 worktree 文件并非同一物理写入目标；常规单任务不需承担全局 TTL/identity 仪式。先确认真实并发生成事故，再决定缩到共享 checkout/实际资源或取消默认启用；整合时契约/锁仍需统一生成验证 |
| 自写 shell 危险命令判断 | 可提供快速提示，不是完整安全隔离 | 优先复用宿主已配置的权限/沙箱；确认等效防护再去重复。真实数据、凭据、生产操作边界保留；不要持续扩充 shell 字符串解释器 |
| `stack_inventory.py` | 正确但低风险的 README 同步器 | 本轮调用仅 0.003 秒，删它不是性能优化。可将 README 版本表改为事实源链接，连同步器及专门测试一起删除；若保留表，仅相关依赖/README 变化时校验 |
| `web_manifest_freshness.py` | 可证明输入字节变了，不能证明设计语义仍一致 | 对产品/设计产出作为按需提示；不要让任意源文件变化强迫更新人工维护的全局摘要哈希。机器事实能即时计算就不再持久化副本 |
| `large_files.py` | 应保留体积限制，审视额外证明成本 | 当前 5 MiB 全库策略与 pre-commit 1,000 KiB 新文件策略不一致；可统一目标/豁免。精确历史证据哈希只用于确需不可变身份的资产；本轮校验 0.155 秒，不是 CI 慢源 |
| `sync_skills.py` / mirrors | 双宿主共享确有需要 | 保留一个编辑源和薄镜像校验；删减技能时同步减少镜像。不要仅为少一个脚本重做跨平台分发 |
| `scripts/type.py` | 多数为 CLI 转发 | 可收为 Pixi 中源码/测试两个直接入口；`--clean` 删除缓存是否有效先核实，不能把注释中的“增量/清缓存”当性能证据 |
| `scripts/test.py` | 保留必要环境隔离，简化转发 | pytest 的选项/markers 可以由原生命令表达，但启动前 null keyring 隔离有真实历史根因，不能随 wrapper 一起丢掉 |
| `supervisor.py` / `system_tests.py` | 保留 | 隔离端口、state/cache/log、真实服务生命周期与清理，属于有实际调用者的执行工具 |
| `frontend_architecture.mjs` / leaf dependency check | 保留契约与依赖判断，减少重复扫描 | 已安装 dependency-cruiser 和 TS parser；标准图规则能覆盖的交回标准工具，Ditto typed transport 规则保留；替换前用既有反例验证别名/动态入口覆盖 |
| `l3-*` 首页诊断脚本 | 优先退役硬编码的一次性探针 | 多个文件固定 localhost、page-home、`/tmp/proto-l3.png`；模型可用通用浏览器工具完成临时诊断。`l3-pixel-diff.mjs` 仍被验证文档引用，先替换其引用/能力再删，不能一刀删除整个 glob |
| prototype freeze / completion board / edition gates | 主要是设计管理工具 | 退出普通 UI PR 必经路径，按明确原型交付运行；实际路由可达性、accessibility、关键交互测试保留 |
| token export、contrast、build budget | 保留生成/用户可感知约束，按范围运行 | token 单一来源、可读性、体积预算有实际价值；不必把每次设计讨论都变成全套 token/viewport 扫描 |
| release/cohort、安全工具 | 保留行为，调整触发与重复构建 | 服务的是制品身份、兼容和安全，不应因 coding agent 变强被取消；日常迭代不必预先承担全部发布流程 |

这一轮没有逐个运行所有 Web 接受脚本。R1/R3/Q2/Q3 历史验收脚本应按仍支持的产品行为和 system E2E 重叠程度整理；不能仅因名字像旧阶段就宣告无用。

receipt 是真实执行成功后写入的本地缓存，和静态 agent-eval fixture 不同。但它包含 staged/unstaged 状态，同样内容暂存后也可能失效；它不校验对话中的完成声明，也不是同权限 agent 无法修改的防伪凭证。[fingerprint](/Users/chevy/Desktop/code/ditto/tooling/agent_harness/evidence.py:273)

lease 的 identity 则按 worktree 共享，不能区分同一工作树里的多个 subagents；它当前主要协调不同 worktree 的整类生成物写入。只读 `check-changed` 也会检查有效 lease，所以生成后释放 lease 再验证可能被阻断。缩小它的范围应针对真实协调需求，不应把“有一把锁”直接等同于每个并行写者已被正确隔离。

当前覆盖率和 mutation 的具体数值门槛没有足够误报/缺陷检出证据支持调低；先修执行路径与冗余，之后结合 mutation 和实际漏检判断。主观设计分数与测试覆盖率不应混为一类。

### 两个“大脚本”不应整体删除

`generate_web_schema.py` 已经调用 openapi-typescript，并没有重新实现 TypeScript 类型生成。额外代码投影请求参数、响应状态/媒体类型、SSE 元数据，分别由 [transport.ts:450](/Users/chevy/Desktop/code/ditto/apps/web/src/api/transport.ts:450)、[transport.ts:691](/Users/chevy/Desktop/code/ditto/apps/web/src/api/transport.ts:691)、[agent-validation.ts:127](/Users/chevy/Desktop/code/ditto/apps/web/src/api/agent-validation.ts:127) 消费。openapi-typescript 生成的是不含运行时校验的类型，不能替代这条行为链。[官方说明](https://openapi-ts.dev/introduction)

`oasdiff.py` 也已经调用真实 oasdiff。较好的精简对象是历史 erratum 的重复结构证明：完整 SHA 已锁定唯一旧快照，后面还逐个验证响应数、位置和多个子哈希。保留完整输入身份、有界修正和结果回归后，可以减少内部重复。当前默认 merge-base 不触发该旧纠错，release 为 no-baseline；显式旧 release/旧分支仍可能需要，必须先确定支持期限。[旧基线分支](/Users/chevy/Desktop/code/ditto/tooling/contracts/oasdiff.py:699)

merge-base 与 release 两种兼容比较保护不同风险，不能因看似重复就删掉其一；当两者字节相同时可复用一次结果。通用 JSON Pointer/ref 解析是否交给已安装工具，需验证其对现有 SSE 投影、ref sibling/cycle 的支持，再决定替换。

## 4. 技术栈判断：目前无需大迁移

“最佳选择”依赖本项目的量化数据、跨平台、本地运行和交互要求；本轮没有足够运行时基准去宣称某个栈全局最优。

| 选择 | 当前建议 | 理由及重新考虑条件 |
| --- | --- | --- |
| Python / FastAPI / Polars / DuckDB / SQLite | 保留 | 与现有计算、HTTP 边界、分析及事务存储职责一致；模型发展本身不是迁移理由 |
| React / TypeScript / Vite / TanStack Query/Router / Zustand | 保留 | 已明确服务端状态、跨页面偏好、局部 UI 的分工；优先消除配置漂移，而非替换框架 |
| Pixi + Bun | 保留 | 一个根 DAG、两套生态依赖所有权已成形；先优化任务内容与触发。uv 具备真实 workspace 能力，但换管理器不会消除现有流程仪式和测试成本 |
| Ruff / basedpyright / Biome / tsc | 保留快速静态反馈 | 删除过严流程不需削弱类型边界；一般风格默认交给既有格式器。是否更换 type checker 应先比较本库 diagnostics/兼容性/耗时 |
| pytest / Vitest / Playwright / Hypothesis / Schemathesis | 按职责保留 | 单元、UI、跨栈、性质与 schema 测试各有对象；优先减少重复执行和修复环境，不按测试框架数量裁撤 |
| Dishka / Prefect | 暂保留，不能以“复杂”直接删除 | 源码已在 composition root 和实际 ingestion/backfill/research flows 使用；若要替换，应单独衡量启动成本、生命周期和重试/部署能力，当前无收益证据 |
| Nx / Bazel / Pants / Turborepo 等新根工具 | 本轮不引入 | 问题主要是现有策略和入口，而不是缺少另一个 task runner；跨机器缓存或复杂 affected graph 产生可测需求后再比较 |

Pixi 已有任务依赖和输入/输出缓存机制；可以先评估用于确定性 build/codegen。不能仅因为工具提供缓存就缓存所有验证结果，输入与外部状态必须完整。[Pixi tasks](https://pixi.prefix.dev/latest/workspace/advanced_tasks/)、[uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)

有两处值得小范围核查：根 TypeScript 固定 5.9.3，Web 为 ~6.0.2，并有 dependency-cruiser TS loader；这至少增加解析路径差异，需结合 Web CI readFile 错误验证，尚未证实因果。Web 同时声明 `radix-ui` 与单包 dialog，源码检索显示实际 UI 使用聚合包，后者是依赖清理候选，不是已证明可直接删除的结论。[Web 清单](/Users/chevy/Desktop/code/ditto/apps/web/package.json:48)

四行的 Vitest coverage provider 适配器则有明确 Bun linker 解析用途；它已经足够小，删掉只会把问题重新推给调用方。无需为了“原生”再造替代层。

## 5. 实施顺序与验收

1. **先删流程负担。** 修不存在的命令/链接；清除隐藏确认、角色数、气质门槛、隐式 commit/tag；收敛重复测试规定。保留知识与真实脚本消费者。该步不需等待所有 CI 优化完成。
2. **修好当前验证链。** Bun/Chromium/Windows bootstrap/CodeQL 能力对齐；定位 coverage 超时；把保留下来的 14 个 tooling 测试文件接入正确 job；将漏洞报告独立分流处理。
3. **按影响分配检查。** 先解决文档/PIT 错误分类、本地提交全 CI、Web tests/coverage 重复；保持间接依赖和失败结果传播的回归反例。修完后再测时长，不能预报节省百分比。
4. **删除低价值脚本与自证机制。** 先一次性 L3 探针、README 版本副本、纯形式/禁词门；再依据实际命中率处理 receipts 和跨 worktree lease。契约与运行时边界最后单独审。
5. **小规模对照后继续减。** 选 8–12 个近期任务，覆盖文档、小 UI、bug、API、PIT、跨包重构和生成物；保持同一模型、起点和独立验收，比较精简前后。普通模型波动需复跑可疑样本，不宣称小样本统计等效。

观察指标只需现有日志和一个简表：完成质量/回归、人工中断、返工、实际加载的指令、重复测试次数、token、耗时、CI 首个有效失败与总等待时间。硬边界用固定断言，设计评价由人判断。**不要为了证明 Harness 可以变轻，再建设一个大型 Harness 评估平台。**

验收应体现用户体验：改一份普通说明不跑财务测试；常规 UI 修改不因参考文档重新请示；同一必要验证没有新变化就不重复；PR 红灯能指出可行动的问题；PIT/契约等故意注入的错误仍会被拦截。

现有 [ADR 0010](/Users/chevy/Desktop/code/ditto/docs/adr/0010-polyglot-monorepo.md:1) 明确规定 receipt 和验证缓存边界；删除这些机制或采用新的 task-result cache 需要显式修订相关决策。当前根 AGENTS 的验证与单写者规则也应与实现同步更新。本报告不悄悄改变这些约束。

## 本轮证据与限制

- 阅读根/近端 AGENTS、11 个项目 skills 及相关 references、Pixi/Bun/pytest/type 配置、CI/pre-commit、关键脚本与消费者；外部资料以实际打开的一手原文为准。
- `git status --short`：起始干净；本轮新增两份研究 Markdown。
- `pixi run --as-is -e dev python tooling/agent_harness/validate.py`：退出 0，`Harness validation passed.`；**这是静态 validator，不是完整 harness-check**。
- 通过 `pixi run --as-is -e dev python` 调用真实纯函数：README inventory 为 True，约 0.003 秒；large-file 校验无违规，约 0.155 秒。单次本机函数耗时，不含完整启动和 CI 安装。
- 同一 Python 探针复现 comment-only f-string 误报、helpers 路径及 801 行阻断；这些是构造输入对现有函数的验证，不是声称仓库当前已有对应失败文件。
- 分类函数复现 `docs/research/example.md → 无测试`、`packages/data/README.md → backend + PIT`、`AGENTS.md/skill → 根 check`。
- GitHub runs/jobs/logs 与 branch protection 使用只读查询；未触发远程运行、未发布消息或修改配置。
- 没有运行完整 check/ci、产品测试基线、依赖迁移或逐个 Web 接受脚本；没有测量实际模型会话的 token/成功率变化，因此没有承诺删除比例或提速幅度。
- 新增文档的本地链接与行号、尾部空白及文件末尾换行检查通过；`git diff --check` 通过。新增文件另用 `git diff --no-index --check /dev/null <file>` 检查，无空白错误输出；其退出码 1 表示文件相对空文件有差异，初次包装检查误将该状态记为错误，核对后已更正判定。
