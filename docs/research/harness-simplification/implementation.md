# Harness 精简实施与验收（2026-09-06）

对应 [规格 #80](https://github.com/cosmos-arc/ditto/issues/80) 与 #81–#95；比较基点为
`688386be200af5fd8d92e138575f55f283b5dd05`，实施分支 `codex/harness-simplification`。
本报告区分代码实现、实际验证与发布资格，不能用删除行数或静态政策测试推断模型质量提升。

后续诊断更新：原始 `backend-coverage` 复验已通过（16,469 通过、73 跳过，覆盖率 89.41%），
八 worker 顺序重放的 7,464 次测试也全部通过。前轮两项超时仍未复现、根因未确认，没有以代码修改
宣称修复；以下保留实施时的原始记录，最新证据见 [超时诊断](timeout-diagnosis.md)。

## 实施结果

- 项目 skills 由 11 个降至 PIT 一个，两宿主镜像一致。API、产品、设计、测试和架构知识迁入近端文档；AGENTS 只保留条件路由及关键不变量。
- 页面合同、原型和视觉工具迁入 Web 工程目录，普通 Web 检查使用 route audit；冻结哈希、完成看板及历史 rubric 仅保留显式调用。
- 普通文档走轻量 scope；可执行文件、混合修改、根配置与未知路径仍保守。pre-commit 的 Ruff 只处理传入的暂存文件，移除提交时重复的全库类型/Harness 检查。
- 修复 Node 22/24 的 TypeScript loader、Windows oasdiff 资产名与冷 CI 依赖；开发、契约、质量工具测试接入根任务。
- PR 按范围选择 job，稳定汇总门拒绝 required job 的失败、取消、缺失或跳过。主分支、merge queue、定时与手动入口执行完整集合。
- Web 静态检查与测试分离，CI 单次覆盖率测试；镜像 build、smoke、export、SBOM 与扫描绑定一次构建的不可变结果。OCI index ID 与扫描器的 config ImageID 明确区分。
- 删除 stack inventory、语义词/行数硬门、未消费的一次性视觉探针和重复政策入口；保留真实导入边界、秘密检测、API/PIT 反例及覆盖率阈值。

## 代表任务的可比测量

| 维度 / 任务 | 实施前 | 实施后 | 解释与限制 |
| --- | --- | --- | --- |
| 项目技能发现 | 11 个项目 skill 的受控目录 | 根、Web、data 三个目录的 Codex/Claude CLI 均只报告 PIT | 实际宿主探针；Claude 不提供源路径元数据，路径另以镜像文件核对 |
| 固定上下文 | 根 AGENTS 119 行、Web 85 行 | 根 35 行、Web 24 行 | 文本体积，不能换算为准确率或 token 收益 |
| 大型研究请求：500 标的 × 96 月，同一覆盖率测试 | call 157.60 秒 | call 22.41 秒 | 同机单次测量，约下降 86%；不是全 CI 加速比例。按月索引替代重复扫描，50 项相关反例同时通过 |
| 全量后端覆盖率 | 历史 CI 44 分 35 秒超时，未完成 | 本地 pytest 886.44 秒；16,467 通过、73 跳过、2 超时；覆盖率 89.41% | 宿主和 worker 数不同，不作直接性能对比；全量仍未绿 |
| 重复测试 | Web unit 后再 coverage；后端已单次 coverage 加独立 PIT | Web CI DAG 改为单次 coverage；后端安排与日常局部入口保留 | DAG 与实际日志核对；未测长期 CI 分钟费用 |
| 暂存文件反馈 | Ruff 命令带全库路径、提交运行全库门 | 实际部分暂存探针通过：暂存、未暂存及无关文件均按预期保留 | 保留秘密、冲突、文件安全检查；全量 pre-commit 最终通过 |
| 人工中断 | 没有可比日志 | 实施中审查基点确认 1 次；没有重复请求同类操作批准 | 不是受控前后对照，不宣称降低了多少中断 |
| 返工 / 质量 | 没有同任务同模型基线 | 两轴审查发现并修复 4 个具体问题；完整 Web 入口另发现 Node 24 解析问题 | 发现与修复记录，不构成模型质量分数 |
| token | 未采集同模型同起点基线 | Codex 根目录探针 input 21,019（cached 12,928）、output 282；Claude 三目录原始 usage 有记录 | 仅技能发现探针，宿主默认模型不同，不估算实施 token 节省 |

性能修复没有提高超时、降低覆盖率、改变 worker 策略或跳过业务断言。全量中的两项失败为
`test_wrapper_isolates_keyring_before_collection_and_in_workers`（10 秒子进程上限）和
`test_run_eod_never_enters_prefect_engine_in_real_import_process`（90 秒）。两文件单独运行
11 项通过（9.00 秒），开启覆盖率后 11 项通过（16.46 秒）。这支持资源争用的假设，尚未证明根因；
后续需在 CI 宿主复核，不能将局部重跑替代全量成功。真实数据相关跳过需要外部凭证，另有既存 DI 隔离跳过。

## 验证证据

本机原始日志目录为 `/tmp/ditto-tickets-80/`，它不是持久 CI artifact；本报告保留结论与关键数字。

| 入口 | 实际结果 |
| --- | --- |
| `pixi run -e dev ci` | 失败于上述两项后端子进程超时；不宣称完整通过 |
| `coverage_gate.py --report coverage.json`，base 为实施前提交 | 全部原有覆盖率阈值满足 |
| `pixi run -e dev type-all` | 源码和测试均 0 errors / warnings |
| `pixi run -e dev check` | 完整通过：15,448 项后端测试、1,757 项 Web 测试及所有依赖门通过 |
| `pixi run -e dev pre-commit-run` | 全部通过；首次修正一处格式后重跑 |
| Hook / frontmatter 公共 CLI 回归 | 19 项通过；错误引号拒绝、扩展 metadata 和多个 hook 合法 |
| 页面合同 CLI | 5 项通过；生成失败时两份既有输出均保持不变 |
| Artifact / repository policy | 44 项通过，包含扫描 subject 不匹配反例 |
| Node 22 / 24 dependency graph | 实际图检查通过；Node 22 扫描 784 模块；ESM 与 CommonJS 解析回归通过 |
| Windows oasdiff | 官方 tar.gz 资产下载并经校验；原生 Windows 执行未测 |
| `pixi run -e dev web-ci` | 1,757 项前端测试、719 项原型/工具测试全部通过；覆盖率及生产构建预算通过 |
| `pixi run -e dev pit` | 401 项通过 |
| `pixi run -e dev arch-check` / `check-contract` | 全部通过 |
| `pixi run -e dev test-system` | 默认 cohort 与六项专项跨栈场景通过，命令退出 0 |
| `pixi run -e dev harness-check` | 工具测试、Harness 测试、类型、宿主配置与大文件检查通过 |

| `security-supply-chain` | 两版历史/当前树秘密扫描及检测哨兵通过；OSV 返回非零，11 个包受影响，摘要 85 条漏洞 |

实际 PR selector 对整个 `688386be…517eeb12` 差异选择全部 12 个 job，`analysis=true`。
这使用实际 CLI 和既有环境变量接口，仍不是远程 Actions 执行记录。

镜像链路以源码提交 `517eeb12345c4218d403c2a1f99b96736e859ac4` 验证。
Mac 默认 ARM Linux 构建被现有平台锁拒绝；设置原生 Docker 的 `DOCKER_DEFAULT_PLATFORM=linux/amd64`
后构建成功，未修改 lock 或平台集合。构建输出为
`sha256:8991c571e935b2be6e9e1db77775d77efe18677d121154bdfbd853517a94e74d`，
从同一导出 tar 计算的 config digest 为
`sha256:03035637c5aabcb44caceb19f38a9dc6ad25b4bdfbd311e8a0e99710cf6dc4ef`。
smoke 和 Syft subject 校验通过。Trivy 首次因 `mirror.gcr.io` 下载数据库 EOF 失败；
复用该 tar 并显式选择其自带的另一官方源 `ghcr.io/aquasecurity/trivy-db:2` 重试。
原 artifact gate 的非零结果保留，不将分步重试冒充完整 gate 成功。
重试扫描完成，返回 1：69 条 HIGH/CRITICAL 组件发现（65 HIGH、4 CRITICAL，31 个不同 advisory），
秘密发现为 0。Trivy JSON 的 ImageID 与上述 config digest 校验通过，因此实际 build、smoke、SBOM、
扫描的同一 subject 链路已有证据，但漏洞仍阻断制品门与发布资格。明细见 [当前镜像台账](trivy-current.csv)。
Trivy 同时提示 Conda 包仅支持 SBOM、不能进行漏洞扫描；不能将扫描范围误写成全部锁定依赖。

## 两轴代码审查

### Standards

首轮发现 hook command 经 shlex 分词后错误接受单引号导致的失效展开。已改为比较规范命令，
保留多 entry 扩展，并以两宿主 CLI 反例验证。复审 `5215e4e4` 未发现新增标准违规或可行动的代码异味。

### Spec

首轮发现普通 Web 门仍隐式检查冻结基线/看板、生成器第二份内容失败会留下第一份修改、release 调用者
仍使用可变标签。三项均修复，复审未发现新的具体实现遗漏。原生 Windows、远程 CI、外部服务与最终验收
证据不由代码审查替代。初轮 Standards 1 项、Spec 3 项，均已关闭；两个轴分别报告。
最终验证新增的 worktree 扫描修复也经两轴只读审查，无新增代码问题；复审指出报告误述后端去重，
已更正为仅 Web 去重、后端既有单次 coverage/PIT 分工保持不变。

## 保留机制与后续边界

**Receipts 保留。** 它们有实际的成功证据复用消费者，并绑定内容、工具和配置输入；删除会重复运行昂贵任务。
本地 receipt 不是防篡改证明，发布仍依赖独立 CI/cohort。尚未测命中率和过宽失效的成本，因此本轮不重写缓存协议。
只有日志证明某类输入造成显著无效重跑时，再缩小对应 fingerprint，并先补配置、工具版本和文件删除的失效反例。

**Leases 保留。** common-dir lease 协调多个 worktree 对 contract/lock/generator 的共享写入，过期、冲突、损坏均 fail closed。
它不能区分同一 worktree 内共享身份的多个 agent；这类写入仍由 integrator 单写。只有实际出现该冲突，才评估更细的 ownership，
并用并发争抢、过期回收和原子写入验证，不扩展通用编排框架。

**历史 erratum 与验收脚本按消费者保留。** oasdiff 的已知历史快照修正具有窄 hash 边界和负例；删除前需证明相关 base
不再进入比较。产品恢复、真实数据与版本验收仍有显式消费者，留作可选工具；本轮移除的是普通路径的强制调用和无消费者探针。
未改变 ADR 0010 的缓存失效、共享资源协调或 release cohort 决策，因此没有新增或改写 ADR。

## 尚未取得的资格

- [安全结果及逐项台账](security.md)：真实依赖/镜像漏洞仍需独立更新和验证；没有新增 ignore 或把失败降级为成功。
- CodeQL 分析与上传拆开；仓库服务授权阻断仍存在。required checks 的远程保护未核验，未改管理员权限、订阅或公开性。
- Codex CLI 探针报告全局 `codex-code-mode-host` 缺失；Claude 报 workspace 未信任，部分 allow 项被忽略。仅记录，未改全局配置或 trust。
- 本轮不执行真实数据、券商、发布或部署。功能改动完成不等于完整 CI 成功，更不等于具备发布资格。
