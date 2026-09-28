# Ditto 验证调用链、测试清单与耗时基线

日期：2026-09-28。对应 [取证：重建当前验证调用链、测试清单与端到端耗时基线](https://github.com/cosmos-arc/ditto/issues/335)，属于 [Ditto 验证体系全链路重整：CI、Hooks、测试分层与 monorepo 影响范围](https://github.com/cosmos-arc/ditto/issues/332) 的事实输入，不是已经生效的优化方案。

固定源码基线：`2b928893fdd17141bcc1a625c89265ae0dbb875c`。性能命令在原主工作区运行，报告在独立文档 worktree 写入；没有修改生产代码、CI、hooks、测试语义、依赖或宿主信任。

## 本轮实测摘要

准备好的 macOS 26.6.2 arm64 环境，8核、16GiB；Python3.13.14、uv0.12.13、Task3.53.1、Bun1.3.14、Node24.20.0、pytest9.1.1/xdist3.8.0、Ruff0.15.11。桌面其他应用正常运行，未控制为独占实验机；本任务的重型验证按串行执行。表中是单次进程wall，只有特别注明的重复两次；不称p95，也不作百分比回归结论。命令、阶段边界、全部远端样本、owner矩阵见[证据附录](2026-09-28-verification-baseline-evidence.md)。

| 入口 | wall | 结果与范围 |
|---|---:|---|
| `task check` | 546.406s | exit0；Python fast15,780 passed/1 skipped；Web232文件/1,980测试；contract/harness等通过 |
| `task type -- --tests` | 9.737s | exit0；全测试工程类型，不是单文件类型 |
| `task pit` | 91.561s | exit0；600 passed/16,539 deselected；正式可复核重测 |
| `task test-system` | 255.907s | exit0；隔离本地服务/生产Web/Playwright，含本地构建和启动，不是纯浏览器case时间 |
| `task web-coverage` | 74.356s | exit0；232文件/1,980测试；statements86.87%、branches81.26%、functions84.88%、lines88.86% |
| kernel owner fast，第1/2次 | 3.732 / 3.695s | 每次285 passed；已准备依赖，同机相邻运行，不是全冷/全热 |
| 全仓单进程 collect-only | 17.666s | exit0；17,139 case，不含tooling/scripts默认范围外测试 |
| application owner collect-only | 7.475s | exit0；4,535 case；说明只做scope计划也可能先付明显收集成本 |

`task check` 内的主要顺序边界：type-all31.472s；fast192.686s；import-boundary16.505s；architecture10.679s；Web全段135.464s（其中type43.911s、测试85.830s）；contract全段约30.1s；harness全段128.719s（harness pytest91.880s、tooling pytest34.206s）。Ruff lint/format分别约0.144/0.067s。本轮主要成本在测试、类型与反复装配；不是所有名为“检查”的步骤都值得优化。

coverage这次比前面的普通Web测试快，反映顺序/缓存/负载混杂，**不表示coverage没有成本或能让测试提速**。Vitest setup/environment 等累计指标跨worker重叠，不能相加作为wall。Biome现有190 warnings/3 infos不阻断；本票未修改。

补充实际入口：application owner fast为118.999s，4,469 passed，证实按包执行确实选择全仓 fast 会排除的integration用例；外部观察插件累计setup3.215s、call234.543s、teardown1.033s。多选188例的call累计49.114s，**不能将其从wall直接减去**。`test_planning_process_unit.py` 单文件累计101.422s，在loadfile调度下值得优先检查文件内场景/装配；本票不把这101秒判为重复或可删除。setup指标只包含pytest报告的fixture阶段，函数正文内自行创建DB等仍归call。

准备好hook环境、独立文档分支，`pre-commit run --files packages/kernel/src/ditto_kernel/identity.py --hook-stage pre-commit` 两次0.749/0.657s，全部适用hook通过、无源码改变；不是partial-staged/真实commit全过程。单独空Ruff缓存与复用同缓存各0.447/0.066s，均通过；只隔离Ruff工具缓存，未清用户缓存或重装依赖。这些结果不支持优先移除廉价文件检查。

## 测试清单与入口漂移

Git tracked Python存量1,294文件、14,485个AST候选test定义；不是运行case数。目录unit1,109文件/12,939定义，integration131/1,119，contract2/3，e2e14/105，其余38/319。Web src232文件、prototype/scripts53文件、系统19 spec；26份conftest。完整owner×目录表见附录。

动态默认全仓收集17,139 case；fast选15,781，包含440个PIT（专项共600）。所有owner单独收集的nodeid集合均与全仓相应子集一致，但标记会随入口变化：

| owner | 独立owner fast | 全仓对应fast | 独立入口多选 |
|---|---:|---:|---:|
| analysis | 1,301 | 1,283 | 18 |
| application | 4,469 | 4,281 | 188 |
| backtest | 955 | 875 | 80 |
| strategy | 1,082 | 1,038 | 44 |

四包合计多选330例，原因是独立入口缺少全仓时附加的integration标记；其中backtest有83例标记变化，但另3例同时被其他fast排除项过滤，所以多选80。platform两入口fast数量相同，却149例serial标记不同；kernel285例独立入口缺unit标记。不能只比总测试数，或把 `--unit`、`--fast`、目录名称视为稳定同义词。

源码对应 `apps/backend/tests/conftest.py` 与 `packages/platform/tests/unit/conftest.py` 的全局 collection hook 按路径为其他包item加标记；data/execution的hook则限定自身owner。backend还存在导入期Prefect替换与autouse temporary_settings；本票只动态证明marker/选中集合差异，没有证明全部运行环境效应。

## monorepo 路径样本

17种输入已实际调用当前planner并记录本地命令与远端jobs，完整矩阵见附录。这里只列行为结论：

- docs本地无验证命令，PR仍policy+security但analysis=false；skill加harness-validate/skill-validation且analysis仍false。
- 单测改动本地检查指定文件、全测试类型、指定测试；删除测试回退owner测试，未直接忽略。
- kernel/platform/普通agent源文件：全仓lint+format+type-all、owner fast；尚无反向消费者测试图。PR仍选全仓backend shards、capacity、contract、system及Web build等，不能将局部owner范围直接指控为整体覆盖缺失。
- high-risk application：上述local命令再PIT，PR全量。跨backend合并owner成一次fast，先独立预收集；本轮application planner7.326s，agent+application7.551s。
- Web本地check-web；PR选Web质量/prototype/build、contract/system、安全。跨栈/契约本地check+system，PR全量。
- tooling/lock/config/unknown升级check与全量PR。模拟跨owner重命名输入包含旧新路径，两owner均保留。

矩阵不创建真实改动；未覆盖全部路径组合、文件mode或缺历史异常。scope所选静态检查、平台与安全也必须纳入预算，不能只计算pytest。


## 当前入口与调用链

权威源码为同一 SHA 下的 [Taskfile](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/Taskfile.yml)、[Git hooks](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/.pre-commit-config.yaml)、[范围选择器](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/tooling/agent_harness/hook.py)、[pytest wrapper](https://github.com/cosmos-arc/ditto/blob/2b928893fdd17141bcc1a625c89265ae0dbb875c/scripts/test.py)。以下箭头表示顺序，同一格并不意味着并行。

| 入口 | 实际工作 |
|---|---|
| pre-commit | 文件卫生/格式有效性/冲突/分支保护；Python staged 文件 Ruff fix → format；Gitleaks。没有 pytest 或类型检查 |
| commit-msg | conventional-pre-commit 校验消息类型 |
| pre-push | pre-commit 传入提交范围 → pre_push 核对当前 HEAD、干净工作区、基线 → 共用 scope planner → 执行命令；缺历史回退全量，不复用上次成功结果 |
| check-changed | 完整 changed set、lease 检查 → scope planner；与 pre-push 共用规则，但 diff 输入语境不同 |
| AI Pre/Post/Stop | Pre 拦截危险 Git/越权写入等；Post 对精确 Python 文件限时 format；Stop 提示脏工作区。都不代替显式验证 |
| check-backend | 环境 → lint → fmt-check → type-all(clean) → test-fast → import boundary → architecture smells |
| check-web | 环境 → lint → type → routes → token links → architecture（含再次 lint）→ Vitest src |
| check-contract | Python环境 → snapshot/generated/契约静态检查 → OpenAPI conformance → cohort compatibility |
| harness-check | 环境 → validator → harness pytest → dev/contracts/quality pytest → Bun quality tests → harness type |
| task check | toolchain → check-backend → check-web → check-contract → harness-check，全为串行 Task cmds |
| task ci | backend-ci（额外 PIT）→ contract → system → harness → artifact-gate；不是 GitHub 的并行 job DAG |
| web-ci / artifact-gate | Web static → coverage → prototype → build；artifact-gate 再执行制品构建/验收 |
| 系统测试 | 隔离 API/state + 生产 Web + Playwright 旅程；CI 下载本 run 的 Web 构建，本地入口可能自行构建 |

`task check` 不含全部集成、Web coverage/prototype、系统测试、容器、安全分析和发布验收，因此通过它不能称“完整 CI 已通过”。`task test -- --fast` 排除 slow/integration/snapshot/sandbox_live/capacity；普通模式排除 snapshot/sandbox_live，integration 模式固定 n=0，unit 模式 n=auto。本地 fast 使用配置中的 xdist；不会像远端自建 shard runner 一样拆 serial 车道。

## 已证实的重复与范围放大

1. `hook.py:_backend_source_commands` 把 owner 测试合并到一次 fast 调用，但静态部分仍是全仓 lint、format、type-all。仅测试改动也调用整个测试工程的类型检查。“包级检查”不能理解为所有组件都只检查包内文件。
2. 同函数在正式运行前调用 `_owner_fast_coverage`，先独立收集 owner fast 用例。其 `lru_cache` 只在当前 Python 进程内有效；新的 check-changed/pre-push 进程重新支付。探针有防止某 owner 零 fast 用例被合并调用掩盖的保障，减少收集时仍须保留。
3. 单次 `web-static` 直接调用 web-lint，随后 `arch:check` 再次执行 `bun run lint`。type/coverage/build 都生成路由，type/build 都执行 `tsc -b`；后者实际成本受增量状态影响，不能只数调用次数估算收益。
4. 本轮 `task check` 日志证实四个 OpenAPI conformance case 先在 fast 测试通过，又在 contract-conformance 串行通过。PIT 同样被普通 fast/CI shard 表达式包含，再在专项入口执行。是否存在独有执行语境要在职责决策中逐项确认。
5. 六个 CI shard 各自先 collect inventory，再运行本片 parallel/serial 两车道；xdist worker 各自收集本次输入。按 nodeid round-robin 还可能让同文件 fixture 在不同 runner 重建。这里只确认执行结构，未把总 collection 次数直接乘成提速收益。
6. 时长治理门在有新增用例时最多启动 head/base/slow/unit/integration 五次 collection。真实远端样本的该 step 为 205/225 秒，位于分片后的串行尾部；门曾拦截超标测试，不能据成本直接判无效。

## 测试职责的代表性反例

| 证据 | 实际职责/资源 | 对后续决策的约束 |
|---|---|---|
| `packages/data/tests/unit/storage/metadata/test_sqlite_trading_rule_store_unit.py` | tmp_path SQLite、真实 schema/reader/writer、PIT边界 | unit 路径不代表纯规则；存储和时间保障必须保留 |
| `packages/agent/tests/unit/storage/test_lease_audit.py` | 真实 AgentDatabase、lease fencing、审计与恢复 | 关键恢复测试可重划 owner/层级，不能仅因慢而降频 |
| `packages/platform/tests/integration/observability/test_observability_integration.py::TestPresetConfig` | 构造配置并断言字段；其他类有真实 SDK 接缝 | 只处理具体类/用例，不能把整个文件判成纯单元或重复 |
| `packages/analysis/tests/unit/experiments/test_pbo_plan_validation_unit.py` 的两个同体校验函数 | 装饰器参数分别覆盖非序列、日期顺序/空值等不同输入 | AST指纹忽略装饰器会误删；合并也必须保留输入类 |
| `apps/backend/tests/unit/test_db_fixtures_unit.py` | 三组重复 hasattr 断言，真实 DB fixture；名称声称 scope但断言未证明跨测试隔离 | 是语义质量与装配成本候选，不等于已批准删除 |
| capital/fundamental identifier route 单测 | 两文件部分测试都直接调用同一个 `resolve_identifier_for_api` | 共享 helper 是收敛候选；不因此删除各 HTTP route 自己的保障 |
| `test_record_models_unit.py` 同体 equality | 各类 `_make` 返回不同 Record 类型 | 文本相同不是同被测对象 |
| scheduler capacity / OCI timeout | 真实存储/状态恢复或物理进程/管道与墙钟限制 | 保留容量和物理时间语义；不以缩小输入或 fake clock 获得表面提速 |
| observability `wait_for_export` | 源码称内存 reader 同步，仍固定 sleep(0.05)，调用点36处 | 需核实当前 SDK；1.8秒仅是声明等待之和，不是已测 wall 收益 |

旧 [等价重复用例清单](https://github.com/cosmos-arc/ditto/issues/321#issuecomment-5854166615) 仅以函数体和参数名初筛，不能成为批量删除授权。其正文排除 PIT 等关键保障，但评论仍列 SQLite fee/trading rule 的 PIT 边界等候选；二者使用不同实现与 schema。清理票必须先修正候选口径。

Web 的 `src` 测试统一 jsdom+MSW，包含纯逻辑、adapter和DOM交互；`scripts` 项目名为 prototype、环境为 node，但部分用例实际使用 JSDOM/Playwright Chromium。Python E2E、原型浏览器和生产 Web/API 系统旅程的被测对象不同，不能按目录或相同 selector 自动去重。

## 远端执行、DAG 与身份

最近11个完成的全量PR样本（来自2026-09-27的两个集中开发分支）：created→最后job结束中位数862秒，范围797–1053秒；job interval总和中位数6090秒。后者包括准备/上传，不是计费时间、CPU时间或用户等待。它不是长期随机样本，不能外推失败率/p95。

| 样本 | wall | 关键证据 |
|---|---:|---|
| [chart成功PR](https://github.com/cosmos-arc/ditto/actions/runs/36354484049) | 1053s | 最后分片+575s；aggregate+578→1049s，其中duration gate205s、PIT171s、coverage combine31s |
| [时长门成功PR](https://github.com/cosmos-arc/ditto/actions/runs/36347752794) | 881s | duration gate225s、PIT62s；不能把另一运行的171s固定套用 |
| [chart失败PR](https://github.com/cosmos-arc/ditto/actions/runs/36352766776) | 944s | 系统测试约+352s已有可行动locator失败；整轮完成时间不同于首次失败反馈 |
| [当前main成功](https://github.com/cosmos-arc/ditto/actions/runs/36357148934) | 705s | macOS642s，backend340s/Web244s；只跑常驻门与platform，未重跑六分片/coverage/system |
| [较早main成功](https://github.com/cosmos-arc/ditto/actions/runs/36352736583) | 446s | 平台与安全仍有实质成本；不同提交/负载，不作受控回归百分比 |

8个时长门开发失败样本的治理step耗时182–245秒，失败确实列出新集成测试超过5秒。最近100条CI记录全为attempt=1，不同SHA触发不是同SHA重跑。另4次cancelled样本耗费合计14818 job-interval秒；取消原因未取得，不能全部归因于自动替代或称为计费成本。

真实checkout日志及commit API证明两组三者tree相同：

| PR | source head | 实测test merge | 最终squash/main | 三者tree |
|---|---|---|---|---|
| [Chart time and sources](https://github.com/cosmos-arc/ditto/pull/308) | 46e0e90c | ccabdaa7 | 2b928893 | b60f6893323ad968b1595460356b06519db40f62 |
| [New test duration gate](https://github.com/cosmos-arc/ditto/pull/328) | 6983ce17 | 4ffca56a | 840601d0 | 5c3cb3fc6291e52418e9badda6a27722833e7975 |

仅对上述样本证明tree相等；当前selector的push分支没有主动核验tree等价，含SHA的构建制品也不能据此视为相同身份。

当前声明的流程：CI支持PR/main push/merge_group/每周schedule/dispatch。PR按scope，schedule/merge_group/dispatch全量，push仅常驻+platform。多数job直接依赖repository-policy；web-build产物供system/container复用，system实际日志确认DITTO_REUSE_WEB_BUILD=1。六shard中每片先parallel后serial；backend aggregate后置治理/PIT；CI gate使用always并核验本次选择集合。Security只由workflow_call调用，CodeQL/OSV按analysis选择，Gitleaks常驻，链接检查只随schedule。旧说明“security自己有schedule”与源码不符。

抽样uv/Bun/Playwright均见缓存命中，setup是数十秒，主要测试step是数百秒；没有测仓库级命中率。Web产物按同run复用，不是跨run任务结果缓存。没有自定义测试成功结果缓存。

[实时ruleset ditto-main](https://github.com/cosmos-arc/ditto/rules/11363741)有效、无bypass、要求PR/线性历史，required context为`CI gate`且strict=true，线程须解决、审批数0；无merge_queue。传统branch protection API返回404并不否定ruleset。未执行绕过/保护破坏性试验。

Release源码要求精确SHA的main push CI成功，再构建、smoke、扫描、SBOM/checksum、attestation与发布。API当前可见release run为0，merge_group为0；schedule仅2条旧非成功记录。因此本票只证明这些入口的配置/源码，没有当前成功发布或周度验收证据；也不把API零条记录写成历史上从未执行。


## Git 与 AI hooks 的实际证据

三个Git hook安装文件存在且可执行，pre-commit版本4.6.1。上轮两份研究材料的实际commit/commit-msg/pre-push均成功；文档路径只证明该范围，不证明源码测试已覆盖。分支发布不替代本轮的独立性能测量。

| 宿主 | 动态证据 | 限制 |
|---|---|---|
| Codex Pre | 研究子任务有一次真实main保护拒绝，显式git -C正确worktree后成功 | 没有独立逐事件耗时；这是策略反馈而非CI耗时 |
| Codex Post | 已记录至少4次仓外临时Python文件创建后收到缺少该目录ruff的反馈；创建成功，任务继续 | 证明非阻断路径触发，不证明formatter成功；无elapsed |
| Codex Stop | 项目配置存在 | 未取得可归属Stop执行记录，不能称零次 |
| ZCode Pre | 精确归属Ditto的15个session中，3条项目hook.run.failed为82/81/115ms | 只代表3次失败，不代表成功路径或整体分布 |
| ZCode项目配置 | 两日日志196条pending_trust诊断 | 是诊断条数，不是执行/失败/session数量；不能推断项目hook从未触发 |

Codex日志还有39条started/39条completed通知，但缺事件名、run-id和duration，不将相邻时间差推算成延迟。ZCode session/user-prompt阶段日志可能混有插件/用户来源，也不用于代表项目Pre/Post/Stop。未更改信任、未开启新AI会话、未发布原始对话或私密配置。当前证据不支持把整体CI高耗时归因于AI Stop；完整逐事件预算需要后续有明确归属的短期采样。


## 当前事实与旧材料的差异

- Stop 已仅作提示；manifest/receipt已退役。旧资料中的 Claude mirror、Stop全量验证、收据复用不得沿用。
- 文档称“不再独立预探测”，当前代码仍执行 owner collection；“包级静态检查”实际为全仓静态检查。
- main push 已收窄；旧票“main全量双付”的前提已失效，剩余问题是平台/安全门职责和身份正确性。
- `slow` 从本地fast排除，但普通CI shard仍包含；只有 capacity 有独立专用job，不能把打slow标签说成已迁到低频车道。
- 本地普通fast不特别调度serial，CI自建runner才拆serial车道；每片串行不等于所有runner全局互斥。
- 当前 backend aggregate 下载 capacity 产物却没有显式 `needs: backend-capacity`。样本未出现竞态；后续职责/DAG决策需要处理这个依赖缺口。

## 后续决策可使用的证据边界

本票提供当前机器路径、动态collection和真实远端运行证据；不批准删除测试、迁移门禁、改动保护规则或恢复receipt。性能预算应分别描述准备好的环境、冷环境、首个可行动失败、最终适用门完成及人工返工，不能直接把并行job之和当作等待。

已测：当前源码入口、Git安装状态、归属明确的部分AI hook历史记录、17种planner输入、全部owner与全仓collection、代表性本地执行、远端17 run/逐job关键step及两个PR身份链、实时ruleset。

尚未测：新机器首次安装/全冷依赖、整个编辑→commit→push→审查返工→可合并的真实连续用户旅程、全套fixture逐项profiler、长期失败/flake分布、所有AI宿主事件延迟、真实provider/物理容器sandbox专项、成功周度/merge-group/发布运行、计费与取消原因。没有清空用户缓存、修改信任、创建真实交易/数据写入或触发发布。

第一次外部inventory探针因临时 `queue.py` 遮蔽标准库导致递归启动诊断进程；发现后停止整棵本任务进程树、改名隔离、作废受影响数据。报告仅引用修正后的collection、scope及重测PIT/type；此前已结束的check/system有效。这个失误不归因于Ditto本身。所有正式测量退出码列在附录；未运行的项目不写成通过。

这些缺口不妨碍讨论职责与试点，但后续预算只能先作为目标；落地前须通过对应真实路径与关键保障反例验收，不能把本报告当优化收益已经兑现。

待裁决问题分别归 [决策：本地、PR、主干与发布各自承担哪些验证职责](https://github.com/cosmos-arc/ditto/issues/336)、[决策：按职责重划测试层级、所有权与重复用例判定规则](https://github.com/cosmos-arc/ditto/issues/337)、[决策：monorepo 改动如何映射到受影响代码、消费者与验证范围](https://github.com/cosmos-arc/ditto/issues/338)，再汇入 [决策：性能预算、优先级与分批迁移的验收和回滚方案](https://github.com/cosmos-arc/ditto/issues/339)。已有实施票继续保留，不能由本报告自动更改它们的范围或授权。
