# CI、测试分层与 monorepo 影响分析：一手依据与适用边界

研究日期与来源访问日期：2026-09-28。状态：**决策输入，不是生效规范或改造实施**。
对应[研究：CI、测试分层与 monorepo 影响分析的业界依据及适用边界](https://github.com/cosmos-arc/ditto/issues/333)。
本地复核基线：`2b928893fdd17141bcc1a625c89265ae0dbb875c`。

## 结论

优化对象应是日常改动到可合并的完整等待。最有依据的方向是：先把测试验证的职责与
执行资源分开描述，消除多入口重复准备和执行，再建立可信的影响传播，最后调整分片、
缓存和检查发生的阶段。单纯给慢用例打标签、增加 worker 或改写 job 名称不能完成这些工作。

以下“直接采用”指可直接用于后续分析的原则，**不表示已经批准删测试、改 required gate、
迁移构建系统或改变发布身份合同**。具体性能预算与风险取舍仍由地图的后续决策确认。

| 候选 | 研究建议 | 条件与代价 |
|---|---|---|
| 将 scope 与 size/隔离/时长分开 | 直接采用 | 先重审代表用例的真实调用链；不能由目录或耗时自动迁层 |
| 以保障语义判断重复，按 owner 与消费者保留责任 | 直接采用 | 删除前记录被保留的反例及实际入口；AST 相似只能找候选 |
| 对 collection、setup/call/teardown、串行尾部单独计时 | 直接采用 | 复用现有日志与 JUnit，避免立即增加观测平台 |
| affected 覆盖 owner 的反向消费者闭包 | 直接采用原则，条件实施 | 图必须包含非 import 输入与生成链；不确定时扩大验证 |
| 把同一输入的廉价准备与验证结果复用 | 条件采用 | 先区分下载缓存、任务结果缓存、验证证据和发布制品 |
| 重划 commit/push/PR/main/schedule/release | 条件采用 | 每项关键保障有 owner、触发条件、失败归属和当前身份 |
| 改 worker、分片、fixture scope、线程数 | 条件采用 | 同提交受控实测；保存隔离性、收集完整性与失败清理 |
| 引入 Nx/Pants/Bazel 或远端结果缓存平台 | 当前不采用 | 本文借其原则；尚无证据证明替换根 Task 比修现有 DAG 更划算 |
| 固定行业测试比例、统一时限、只测改动文件、只追覆盖率 | 当前不采用 | 没有普适依据，且容易隐藏当前保障缺口 |

## 1. 既有研究哪些继续有效，哪些需要重新取证

已复核[既有一手来源研究](2026-09-26-review-ci-industry-sources.md)、
[CI 反馈审计](2026-09-26-ci-feedback-audit.md)与
[多轮 CR 诊断](2026-09-26-review-ci-diagnosis.md)。Google/DORA 关于小批次、快速反馈、
可行动失败和稳定测试的方向继续成立；GitHub 的 cache、concurrency、PR 事件语义本轮
重新浏览官方资料。旧报告的 PR 样本与耗时是历史事实，不当作当前分片后的性能基线。

当前源码只作适用性核查，不作为全库审计完成的声明：

- `scripts/test.py` 已有 fast/unit/integration/snapshot 分流，但 integration 入口固定 `-n 0`；
  “集成职责”和“必须串行”是两个待分离的问题。
- `tooling/quality/test_shards.py:run_shard` 在每片先做 inventory collection，再执行
  parallel/serial 两车道；parallel 为四 worker、`loadfile`。可验证存在多个 collection
  阶段，但本研究没有计时，不能直接声称它是最大瓶颈。
- `tooling/agent_harness/hook.py:_backend_source_commands` 已合并多个 owner 的 fast
  测试调用，保留 owner 无测试或无 fast 用例的保守升级。该函数按改动 owner 选路径，
  不能将此局部优化表述为已经完成反向消费者影响分析。
- `tooling/agent_harness/ci.py` 已对 unknown/root/contract 等保守选门；push 分支只选
  常驻门与平台 smoke，注释信任 PR 等价内容。等价成立需要独立身份取证，见第 6 节。
- 当前测试指南的 0.5 秒、5 秒分类阈值和 10 秒 fast 硬超时是 **Ditto 的现有政策**，
  不是本研究找到的行业通用值。本文不更改这些值。

## 2. 测试职责与资源大小分开

**一手事实。** Google 原作者在《Software Engineering at Google》明确区分 scope
（验证哪些代码路径）与 size（运行需要的内存、进程、时间等资源）；small/medium/large
的执行约束与 unit/integration/system 的职责不是一一对应关系。见
[Testing Overview](https://abseil.io/resources/swe-book/html/ch11.html)。
其早期[Test Sizes](https://testing.googleblog.com/2010/12/test-sizes.html)更强调执行约束；
不要把早期近似类比升级成“单元必然等于小测试”的定义。

**Ditto 推断。** 先用两组问题治理，暂不发明一串新 marker：

| 职责轴 | 应证明什么 | 资源轴另问什么 |
|---|---|---|
| 单元/纯规则 | 输入、边界、拒绝与状态转换的业务语义 | 是否需要 I/O、全局状态、实际时钟；耗时发生在哪一段 |
| 组件 | 一个 owner 对外行为，内部实现可有多个对象 | 是否单进程；测试替身与生产实现的差异 |
| 集成/契约 | DB、DI、HTTP、序列化、生成代码和跨组件的真实接缝 | DB/端口能否隔离；进程是否可并行；外部服务是否受控 |
| 系统/用户旅程 | 关键流程跨真实边界能共同工作 | 浏览器、容器、平台、测试数据和启动成本 |

例如纯函数测试即使昂贵，也不因超时变成集成测试；快速 SQLite 测试也不因低于
0.5 秒变成纯单元测试。一个集成测试可以很快、可并行；一个组件测试也可以验证多层
内存逻辑。PIT/资金/审批是跨职责的风险主题，不应靠“某目录全部通过”代替场景证据。

**适用边界与代价。** 采用上述词汇需要逐步抽查真实行为，不能只批量改目录。
Google 关于减少过多 E2E 的建议是为改善可靠性和诊断性，文章也说比例依团队不同；
它没有证明 Ditto 应机械采用某个测试金字塔百分比。见
[Just Say No to More End-to-End Tests](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html)。
保留必要的真实边界与少量关键旅程；向低层移动的是可独立证明的规则组合，不是所有
失败路径都用 mock 取代实际装配。

## 3. 去重以保障语义为准

**一手事实。** Google 的[Unit Testing](https://abseil.io/resources/swe-book/html/ch12.html)
强调围绕行为测试、公共 API 和可读性，避免过度依赖实现细节；测试代码的去重与易读
之间也存在取舍。pytest 的[参数化文档](https://docs.pytest.org/en/stable/how-to/parametrize.html)
说明每组参数仍是独立执行，叠加参数会形成组合，传入可变参数不会自动复制。

**Ditto 推断，不是来源提供的自动等价算法。** 每个删除候选比较四项：相同的业务主张、
相同的触发前提、相同的可观察断言、相同的真实边界。再追踪 fixture/autouse、marker、
参数、平台、clock/cutoff/source snapshot、事务与失败清理。四项有差异时，不能仅靠
函数体/AST 相似或覆盖同几行代码判定重复。

- 纯规则用例穷举边界，HTTP/DB/系统层只需证明边界正确接入该规则及边界特有失败。
  多层都带一份独立风险并不重复；多层反复穷举同一规则的全部组合才是精简候选。
- 参数化可以减少代码，不自动减少收集项或运行成本。把二十个函数改成二十个参数，
  没有证据可声称提速；笛卡尔积还可能增加成本。
- 删除前给出“移除用例 → 保留用例/独有反例 → 对应保障”的小表，运行受影响层。
  关键规则可少量注入故障检验断言会失败；当前不采用全仓 mutation 平台作为前置门。

**代价。** 语义比较比文本扫描贵，但可以先从耗时最大的 fixture/用例组入手。
没有等价证据的存量测试先保留；删除数、测试数下降和覆盖率不变都不是收益本身。

## 4. 先解释执行成本，再决定并行与分片

| 一手事实与来源 | Ditto 的可验证推断 | 条件/风险 |
|---|---|---|
| xdist 每 worker 独立完整收集本次输入集，controller 校验各 worker 的 nodeid 顺序一致。[机制](https://pytest-xdist.readthedocs.io/en/stable/how-it-works.html) | 更多 worker 会增加 import/collection 工作；预探针、每片 inventory、各车道启动需分别计时 | 不能把 `--collect-only` 当零成本，也不应自行序列化 pytest item 再广播 |
| session fixture 跨 worker 会多次执行；xdist 没有内置“一次全局 session”语义。[How-tos](https://pytest-xdist.readthedocs.io/en/stable/how-to.html#making-session-scoped-fixtures-execute-only-once) | 先降低 fixture 内容成本，复用只读构造数据；需隔离可变 DB/全局状态 | 提升 scope 可引入污染；锁文件共享并非默认答案，会新增协调与清理职责 |
| `loadfile/loadscope/loadgroup` 控制分组，`worksteal` 提供另一分配方式，`-n auto` 通常按物理核数。[分配](https://pytest-xdist.readthedocs.io/en/stable/distribution.html) | 按文件可减少 fixture 重建，但最长文件可能决定尾部；用实际耗时比较分组与 worker | 改分配方式不能消除共享状态，增加 shard 还增加 runner 准备成本 |
| pytest fixture 有多种 scope，且参数化 fixture 在同一 scope 内也可能多次调用。[fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html) | 区分只读数据准备、每例隔离状态、资源启停；只读基线可复用，事务/临时目录按需要隔离 | 提升到 session 不等于只初始化一次，也不等于测试可任意排序 |
| Polars 线程池参数需在进程启动前设置，官方一般建议自动值。[线程池](https://docs.pola.rs/api/python/stable/reference/api/polars.thread_pool_size.html) | pytest worker × 每进程 Polars/其他线程池可能超订阅，先实测少量组合 | 不无证据全局设为 1；Python/Polars 密集 workload 与机器应分别测 |
| pytest 提供 `--durations`、setup/teardown 展示及 JUnit 报告。[输出](https://docs.pytest.org/en/stable/how-to/output.html) | 用现有工具区分 collection、fixture、call、teardown，补外层 wall-clock | 单用例 duration 不代表启动/收集/排队；并行 duration 相加不等于等待 |

对已知 DAG，理想总时长受关键路径约束。若同一 runner 先并行后串行，则串行尾部仍
直接进入总等待；增加并行 worker 不能缩短这部分。本结论是依赖关系的推导，不是
Ditto 已测收益。真正的全局资源冲突要标明资源范围：单 runner、单机器还是跨 runner。
在每片内 `-n 0` 只保证该车道串行，不能保证所有 CI runner 全局互斥。

最小实验：相同 SHA、相同选中 nodeid 集、相同 coverage 模式与依赖，比较少数 worker/
分片配置；分别记录冷暖准备、收集、fixture、测试、尾部及 runner-minutes。先消除重复
进程与重复全量门，再试时长均衡分片。重复轮数按测量方差决定，不预设收益比例。

## 5. monorepo：路径 owner 不是完整受影响集合

**一手事实。** [Nx affected](https://nx.dev/docs/features/ci-features/affected)先把改动文件映射
到项目，再找依赖这些项目的消费者；默认 lockfile 变化影响全部项目，细化须有可解析
依赖信息。[Pants advanced selection](https://www.pantsbuild.org/stable/docs/using-pants/advanced-target-selection)
提供 direct/transitive dependents，并提醒第三方依赖传播的能力边界。两者说明
“受影响”是由图和输入计算出来的，不是文件后缀过滤的同义词。

**Ditto 推断。** 先以包为可理解粒度复用现有依赖约束与源码，不急建符号级分析器。
起点为改动 owner；沿反向依赖到 application/apps、Web adapter/页面和相应测试。
同时显式纳入 import 看不见的边：DI/registry、SQL/fixture、配置、模板、生成器输入、
OpenAPI snapshot → generated types/runtime metadata → typed transport → feature adapter。
Python import 边界约束本身是“允许依赖什么”的规则，不能当作实际测试影响图。

| 变化 | 选择器最少需要证明什么 |
|---|---|
| 删除/重命名/移动 | 用 base 与 head 处理旧 owner/旧依赖和新 owner/新依赖；不能只看当前存在文件 |
| 共享 fixture/conftest/插件 | 覆盖其作用范围内的消费者，不只是改动测试文件 |
| 公共类型/协议/函数返回值 | 类型检查与行为测试分别覆盖消费者，owner 自测绿不足 |
| 契约/生成器/运行元数据 | 沿完整生成与消费链验证，保留精确身份匹配 |
| lockfile、根配置、工具链、全局环境 | 不能证明细分影响时升级相关全域检查 |
| 未知路径、缺 base、图失效、解析失败 | 明确报错或扩大范围；不能转成“无测试可跑”的成功 |

**建议的验收。** 使用当前 selector 的机制做有限对照：固定删除、rename、跨 owner、
shared fixture、契约、工具链、空收集、未知路径反例；比较选中集合与受控全量结果。
为每次选择保留 base/head、规则版本和选中原因，便于查漏报。shadow 对照只能提高
信心，有限样本无漏报不构成完备证明；未知输入仍保守扩大。不要为审计额外长期维护
一份与代码实际依赖可能漂移的手工图。

## 6. 缓存与身份：相同代码、相同验证、相同制品是不同主张

**一手事实。** [Nx inputs](https://nx.dev/docs/reference/inputs)可声明源码、环境变量、工具
运行版本等输入。[Bazel hermeticity](https://bazel.build/basics/hermeticity)说明可重现性依赖
隔离并识别输入；[Bazel remote caching](https://bazel.build/remote/caching)指出环境与
未跟踪宿主工具可能造成错误共享缓存。采用其正确性原则不意味着 Ditto 应迁移工具。

| 复用种类 | 可以省什么 | 不能替代什么 |
|---|---|---|
| uv/Bun/浏览器依赖下载缓存 | 下载、部分安装准备 | lockfile 校验、实际运行检查、当前漏洞扫描 |
| 确定性任务结果缓存 | 完整输入相同的检查/构建 | 未声明环境、时间、外部服务或生成器变化 |
| 本地验证 receipt | 同范围、同内容与工具规则下的重复运行 | 远端 required status；更改后的未验证输入 |
| 构建制品复用 | 同一字节制品的重复构建 | 新提交的来源证明、另一平台测试、过期安全数据 |

GitHub[依赖缓存](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
支持精确和前缀恢复，且缓存有可访问范围与不可信输入风险。前缀恢复可用于重新核验
的依赖包，不能用于直接宣布测试成功；缓存不存个人状态或 secrets。先测解压/保存
是否比重新准备更贵，再判断价值。

**PR/main 关键身份事实。** GitHub 的
[pull_request 事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
默认检出 test merge commit；`GITHUB_SHA` 与 `pull_request.head.sha` 不同。
[required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
对最新 SHA 有要求，且可能使用 test merge commit 的结果。因此“最终 HEAD 绿”需要
说清 PR head、base、被检出的 test merge、main/squash commit 及 artifact 各是什么。

**Ditto 推断。** 内容相同不能自动证明依赖身份相同：构建可能嵌入 SHA，扫描数据可能
更新，main 的 workflow/环境也可能不同。若减少 main 重跑，必须确认适用 PR 证明、
合并方式、实际 tree、工具/配置、制品字节和来源合同之间的映射；无法证实则重跑
相应检查。当前精确发布身份合同若要求同提交，不以“tree 一样”自行改写。
这是后续 HITL 决策与取证项，本文没有判定当前 main 快路径安全或不安全。

## 7. 验证阶段如何分工，仍需 Ditto 的风险决定

**一手事实。** [DORA CI](https://dora.dev/capabilities/continuous-integration/)强调频繁集成、
数分钟的可靠反馈，同时保留完整 E2E 与可重复构建；它提出约十分钟的反馈目标，不能
推出全部安全、平台与发布证明都必须十分钟内完成。该页面也强调下游复用权威构建包。

以下是供决策比较的候选，而非已经确定的门禁迁移表：

| 阶段 | 候选职责 | 不应由这个阶段独自承担的证明 |
|---|---|---|
| 编辑/AI completion | 定位错误、给出待验证范围与已有证据 | 对未验证内容盖章、隐藏执行整套发布验收 |
| commit | staged 内容的廉价格式、语法、敏感信息检查 | 全系统可合并性 |
| push | 实际 push 范围的确定性受影响检查、已知失败复验 | 远端环境与制品当前身份 |
| PR | required gate 汇总、消费者闭包、关键风险/契约/必要系统路径 | 与最新候选无关的旧绿灯 |
| main | 合并后的整合事实、按身份规则补证/可信复用 | 假定任意合并方式都自动等价 |
| schedule | 漂移、安全情报、宽平台/容量/长期测试与选择器抽查 | PR 所需关键保障的事后补救 |
| release | 同一发布对象的打包、SBOM、安全、兼容、恢复证据 | “源码测过”直接等于发布物测过 |

GitHub required workflow 被 paths 过滤可能一直 Pending，而条件跳过的 job 可以报告
成功；依赖 job 失败还可能导致下游被跳过。官方建议 required 聚合 job 使用 `needs`
与 `always()`；Ditto 还应检查“本次必须执行”的集合，不把 missing/skipped/cancelled
当作已执行成功。依据见上述 required checks 文档。

[workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
可取消过期验证。候选是复用已有按 PR/workflow 的并发组，避免新旧 SHA 互抢；发布与
带副作用作业需不同取消策略。取消旧 run 只节省资源，不证明新 SHA 正确。

## 8. 覆盖率、类型检查与优化成功标准

**覆盖率事实。** Google 的
[Code Coverage Best Practices](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html?hl=es_NI)
把覆盖率作为暴露未测区域的间接指标，不保证断言正确，也没有适用于所有产品的理想
百分比。不要通过堆低价值断言维持数字，也不要把这条研究当作直接降低现行阈值的授权。

分片后用同一源码/配置/身份的数据合并，不平均各片百分比。
[coverage combine](https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html)
按执行数据并集合并，可用 paths/relative_files 映射不同工作目录；是否缺片、混 SHA、
混配置需由调用方校验。受影响子集覆盖率不能直接冒充全库覆盖率。

**Ditto 推断。** 快速行为测试与带 coverage 的权威验证可分阶段，但若 coverage 是已知
失败，本地应先复现对应模式；不能再用无 coverage 的测试通过作为远端门已修复证据。
需要测量 coverage instrumentation 与合并/上传成本，不能事先指定固定倍率。

**类型检查事实。** pytest 的[Typing in pytest](https://docs.pytest.org/en/stable/explanation/types.html)
说明类型标注/检查同样适用于测试与 fixture；
[TypeScript noEmit](https://www.typescriptlang.org/tsconfig/noEmit.html)支持只检查而由其他
工具输出 JS。[Pyright CLI](https://github.com/microsoft/pyright/blob/main/docs/command-line.md)
提供项目与文件等选项，但“能指定文件”不意味着自动覆盖所有反向消费者。

**Ditto 推断。** 转译/构建通过、行为测试通过与类型检查通过是不同证据。公共类型与
fixture 变化保留消费者检查；包级增量类型检查只有在依赖与项目边界完整时才采用。
先测当前 `type-all --clean` 的组成与必要性，不以删除 tests typing 或只检查 diff
文件来获得表面提速。

**优化成功的最小证据。** 下表是针对本次目的设计的口径，不冒充外部统一标准：

| 指标 | 定义与解释 |
|---|---|
| 首个可行动失败时间 | 从明确起点（本地命令启动或 push 接收）到首条可定位并能修复的真实失败；本地/远端分别统计 |
| 到可合并的等待 | 本批首次候选开始验证，到最终候选所有适用门与所需审查落单；人工修改/等待另记，不混成 CI 运行时长 |
| 关键路径与资源成本 | wall-clock 按时间区间/依赖图计算；runner-minutes 为资源和，包含重跑和取消前消耗 |
| 可靠性与质量 | 同 SHA 确认 flake、选择器漏选、关键保障缺口、合并后回归/回滚；保留首次失败原因 |
| 样本可比性 | 按 docs/test-only/单 owner/跨包/契约等分组，注明 SHA、runner、冷暖状态、nodeid 数与样本量 |

p50/p90 和最大尾部结合看；样本少则列原始范围，不用百分比假精确。把某门移到 schedule
可以降低 PR 时长，但若把关键缺陷暴露推迟，则不算等价优化。改变 scope、机器、coverage
模式、测试数量后，不能把所有差额归因于分片算法。

## 后续决策所需输入与边界

本研究已经给出来源与候选原则；不在本票确定测试目录、marker、性能预算、门禁分工或
工具替换。后续至少需要：同 SHA 的本地/远端阶段时间、代表测试的职责与 fixture 审计、
现有图/selector 漏报反例、required rules 与实际 checkout/artifact 身份、迁移前后同保障
对照。优先用现有 Task、pytest、Actions 日志和短表完成，收益不足时不新建平台。

未执行：全量性能 benchmark、全库语义重复审计、GitHub 保护配置变更、产品代码修改、
测试删除/迁移、依赖升级或构建系统替换。本研究中的技术机制均来自上列一手页面；
标注为 Ditto 推断或候选的内容是将机制应用到当前仓库的分析，不能视作来源替 Ditto
完成了工程决定。
