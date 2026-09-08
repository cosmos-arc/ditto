# Ditto 本地验证与 GitHub CI 优化计划

状态：2026-09-08 用户已确认按建议实施。普通 PR 按明确影响范围检查，未知及高风险全量；本地日常检查相关范围，跨包/契约/工具链执行完整验收。

## 已确认目标

- 普通代码 PR 的完整合并门目标为 10–15 分钟；工具链、依赖锁、发布与共享安全边界变更允许更久。
- 只使用现有免费或已购买额度，不以新增付费 runner 为前提。
- Python 使用 uv、JS 使用 Bun，Task 继续作为根任务入口；不重新开启包管理器选型。
- 分开评估失败的正确性原因与耗时原因。不能以跳过有效检查、降低覆盖率阈值或吞掉扫描失败实现提速。

## 决策树

1. 已定：反馈目标与算力预算。
2. 已核查：最新失败根因、任务/步骤耗时、排队、重复执行与缓存实际收益。
3. 已定：普通 PR 的验证范围和高风险变更分类；各门在 PR、main、定期、发布阶段的职责。
4. 已定：本地编辑、提交前与完整验收入口的成本分配。
5. 后续：按测量结果选择测试分片、缓存范围、制品复用；定义失败处理、验收指标与分阶段落地顺序。
6. 已获实施授权；本次改动完成后以新提交的 CI 结果验收。

## 已核查的约束

[ADR 0010](../adr/0010-polyglot-monorepo.md) 要求同提交跨栈证据、稳定的 CI 汇总门、独立制品与 release cohort，以及 Task 单一入口。它禁止验证结果缓存；依赖下载缓存和有完整输入身份的构建缓存是不同机制。改变合并前证明范围需要明确讨论该 ADR 的完整验证取舍，而不能把路径过滤当成无风险优化。

术语继续沿用现有 release cohort、契约和验证收据含义。普通 CI 术语不是 Ditto 业务领域概念，本轮不会为它们新建根领域词汇表。只有形成需要长期解释的真实架构取舍时才新增 ADR。

## 官方实践依据

- [DORA 持续集成](https://dora.dev/capabilities/continuous-integration/)：短反馈周期、失败及时修复、持续改善测试速度；其约十分钟的方向用作目标参考，不视作当前项目已经达到的事实。
- [uv GitHub Actions 集成](https://docs.astral.sh/uv/guides/integration/github/)与[缓存语义](https://docs.astral.sh/uv/concepts/cache/)：区分安装缓存与环境，测量恢复/保存成本后选择 CI 缓存方式。
- [GitHub 依赖缓存](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)：缓存受 key、分支权限及容量约束，不是成功验证证据。
- [GitHub 工作流触发规则](https://docs.github.com/en/enterprise-cloud%40latest/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)：required workflow 不能靠顶层 paths 过滤跳过，否则可能永久 Pending；保留始终产生结果的汇总门。
- [Docker GitHub 缓存](https://docs.docker.com/build/cache/backends/gha/)：不同镜像显式分配 scope，控制缓存导入/导出成本和限流；未配置远端缓存的临时 runner 不会自动复用上次构建层。
- [pytest-xdist 调度](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)：按实际耗时、fixture 共享与隔离要求选择调度，不能简单叠加 worker 和 BLAS 线程。

## 实测基线与当前失败

核查提交：`b8a2cb90`；比较范围包含当前运行、此前完整成功运行和一次被后续提交取消的运行，不能据此计算 flaky rate 或 p95。

- [当前运行 34181678735](https://github.com/cosmos-arc/ditto/actions/runs/34181678735)：CodeQL 本地分析和 SARIF 留存成功，但 Python/JS 上传均被拒绝。GitHub default setup 已于 2026-09-08 02:33:56 UTC 启用，而仓库 `.github/workflows/security.yml` 仍使用 advanced setup。错误为 `CodeQL analyses from advanced configurations cannot be processed when the default setup is enabled`。这与 [GitHub 官方说明](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/results-different-than-expected) 一致，是配置所有权冲突，不是缺少授权套餐。
- [完整成功运行 34146971599](https://github.com/cosmos-arc/ditto/actions/runs/34146971599)：总耗时 **34m36s**；关键路径为 repository-policy **48s** → 后端测试 job **33m35s** → 汇总门。后端覆盖率步骤 **32m17s**，uv/toolchain 准备仅 **19s**。该运行各 job 执行时长合计约 **75.6 runner-minutes**，这是未按平台/套餐加权的运行量，不是账单金额。
- 同一成功运行：Web job **8m48s**、macOS **9m58s**、Windows **3m53s**、容器 **3m24s**。容器等待 Web，约第 13 分钟完成，不是总门 34 分钟的主要原因。
- 后端已启用 `xdist auto/loadfile`，成功 CI 实际 **2 workers / 16,576 items**。下一步应测量收集、慢测试文件、fixture、覆盖率及子进程开销，而不是简单“开启并行”。
- 被取消运行 34145908831 的测试中断不算测试失败；其镜像 Python 身份不匹配在后续成功提交中已纠正。当前没有相同提交多次运行的证据证明 flaky tests。

## 已确认改进路线

| 阶段 | 本地工程配置 | GitHub 配置 | 验收条件 |
| --- | --- | --- | --- |
| P0 恢复可靠绿灯 | 明确 Task check、完整 CI、制品验收各自证明什么；修正文档和命令透传的偏差 | CodeQL 统一一个所有者，建议保留仓库 advanced 配置并纳入 Actions 语言，再关闭冲突的 default setup；保证迁移时 required checks 连续有效 | Python、JS、Actions 分析和上传成功；不吞掉错误；失败时证据仍可下载 |
| P1 缩短主要关键路径 | 采集测试收集/执行/fixture/coverage 分段；明确 serial 测试；修复测试 CLI 参数透传 | 在现有额度内对比 2/4 个测试分片，控制各 job worker 与原生库线程；按同提交合并 coverage 后执行既有全局、敏感包和 changed-code 门 | 分片测试集合完整、无重复/漏测；任一失败/缺失分片导致总门失败；阈值不降低；以实测选择分片数 |
| P2 去除重复准备与构建 | 保持 Task 单入口，拆出明确的 Python/Web/运行时准备职责；本地验证不隐式安装；Docker 先安装外部依赖再构建 workspace | stdlib scope selector 独立于重安装；按 job 准备必要栈；生产 Web build 独立产出并供 E2E/cohort 消费；镜像构建提前启动，匹配身份后再组装 cohort | 冷缓存可通过；缓存损坏/锁漂移仍拒绝；复用制品绑定当前 SHA、契约、构建配置；缩短关键路径并减少总 runner-minutes |
| P3 分层检查 | 本地日常检查相关包与静态门，跨包及高风险完整验收；保留显式全量入口和轻量宿主 hooks | 普通 PR 按保守范围选择，高风险/main/定期/发布全量；只做可解释的粗粒度选择，未知全量；平台相关安全测试不可被遗漏 | 选择器覆盖新增/删除/改名/mode/共享输入反例；汇总门始终产生结果且 fail closed；不缓存测试成功状态 |
| P4 运营与持续改进 | 文档给出每个门的本地复现命令与证据位置 | 按可比较运行记录时长、首次有效反馈、关键路径、缓存开销、runner-minutes、取消与真实失败；告警针对可行动失败 | 连续样本验证普通 PR 目标，分别披露冷/热缓存和高风险变更；没有为降低耗时隐藏失败 |

缓存逐项测量后再启用。Bun 下载缓存、BuildKit 远端层缓存值得实验；浏览器缓存不能默认视为收益，因为系统依赖仍要准备、恢复大包也有成本。uv 已有缓存，不重复叠加。扫描器数据库缓存需要保持新鲜度，不缓存“上次无漏洞”结论。

PIT 已在覆盖率测试集合中执行，之后又单独执行；是否去掉重复执行要先证明独立/串行验收语义未丢失。macOS 名为 smoke 但实际跑完整 fast 后端和 Web 静态/单元；拟将平台敏感证明与平台重复的通用检查区分，普通 PR 保留平台敏感 smoke，高风险及非 PR 保留完整矩阵。

Codecov 等报告上传目前位于 PIT 或 Web 制品上传之前，外部报告服务失败可能阻止后续证据生成。计划先解除这种执行依赖，保留本地权威 coverage 门；是否让报告服务可用性单独阻断合并属于后续决策，不直接改为忽略失败。

两版 Gitleaks 的全历史扫描也存在重复，但成功样本仅约一分钟，优先级低于 32 分钟的后端步骤。迁移到单一受支持扫描器时必须保留检测哨兵、历史基线和完整 PR 提交范围，不能只扫描最终变更文件。

## 慢测试进一步定位

绿色运行日志的后端结果为 16,502 passed / 74 skipped，执行 1,929.15 秒。最慢三条调用：application integration 的容量恢复（2 workers）327.27 秒、backend E2E 容量恢复 296.96 秒、application integration 的容量恢复（4 workers）281.10 秒。

`apps/backend/tests/e2e/test_r3_scheduler_capacity.py` 直接调用 integration 用例的 `_preflight` 与 `_restart(..., 4)`，未引入单独 HTTP/CLI 边界。P1 首先确认并合并这类重复证明，保留真正的持久化、恢复与容量断言；不把删除必要测试当优化。两个 integration 参数场景位于同文件，现行 loadfile 调度会让至少约 608 秒集中到一个 worker，是分片/调度必须处理的长尾。调用时长之和不等于可承诺的墙钟节省。

Web 的约 474 秒步骤由 types 33 秒、architecture 6 秒、coverage 182 秒、prototype 215 秒、build 36 秒等组成。coverage 与 prototype 串行约占 84%；可实验拆为独立 job，分别限制内部 worker，避免把 CI job 并行和单机进程并行叠加到资源过载。

## 本轮落地与复现

- CodeQL 由仓库 advanced workflow 统一管理 Python、JavaScript/TypeScript 和 Actions；远端 default setup 已关闭，最终以新提交上传结果验收。
- 后端四分片分别完整收集、确定性分配，再分普通/serial 两条执行通道。串行标记不被覆盖。原 E2E 容量包装仅重复调用 integration，现已去重，命名验收入口直接运行原 integration 文件。
- Web 的静态/coverage、prototype 与 build 独立运行。系统 E2E 使用同提交构建，校验 Git SHA、产品版本及契约身份；容器构建不再等待 Web coverage/prototype。
- scope selector 只用标准库，昂贵 policy 验证独立运行。Python/Web job 分别安装所需 workspace；完整 runtime 版本检查仍保留。
- 保留独立 PIT、平台敏感 smoke、安全扫描及既有覆盖率阈值；完整路径仍运行原有平台广泛检查。Bun/浏览器/BuildKit 新缓存和扫描器去重暂不加入，后续需单独测量收益。

| 失败位置 | 本地复现入口 |
| --- | --- |
| 后端格式、类型、fast 测试 | `task check-backend`（含生产与测试类型检查，不含完整 integration coverage） |
| Web 静态与覆盖率 | `task web-quality` |
| Web 浏览器原型 | `task browser-install`，然后 `task web-prototype` |
| Web 生产构建 | `task web-build` |
| 契约 | `task check-contract` |
| 真实双栈 | `task test-system`（本地默认重新构建） |
| 分类器、推送范围、分片反例 | `task harness-check` |
| 完整后端覆盖率与 PIT | `task backend-ci` |
| 常规本机整仓验收 | `task check` |

CI 分片失败下载 `backend-shard-<index>-<run_id>`，包含所选 node IDs、JUnit、完整收集清单与 coverage；汇总证据为 `backend-coverage-<run_id>`。仅当四分片成功且身份/清单完整时合并覆盖率。报告服务仍可阻断门，不将服务故障伪装成成功。

验收时记录运行 URL、提交、事件类型、开始/完成时间、排队与最长 job，和此前 34m36s 基线比较；一次全量高风险运行不能证明普通 PR 的 p95，也不能证明冷/热缓存均达到目标。后续样本应从实际普通 PR 收集，不制造空提交刷成绩。
