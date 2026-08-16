# R5 Approval 证据

**记录时间：** 2026-08-16T01:32:55Z
**记录分支：** `codex/r5-governed-agent`
**请求来源：** 当前 Codex task 中 workspace user 明确请求 `/goal 全面完成 docs/plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md 的功能开发计划`
**解释规则：** 该请求是对计划内实现动作的明确授权，不是把 2026-08-04 的原则性意见或设计文档接受推定为批准。授权只覆盖下面列明的 exact scope；live OCI、外发、费用、真实数据写入和真实清理仍需各自证据。

## 状态总览

| ID | 状态 | 可越过的 Gate | 仍然阻塞 |
|---|---|---|---|
| A1 | GRANTED | Task 4 的第 13 包、机器边界和精确 SDK minor range | SDK range/license/边界超出 scope 的任何变更 |
| A2 | GRANTED, SCOPED | Tasks 7/9 Agent SQLite v1；Task 22 Research SQLite v1→v2 migration 的代码、临时 fixture、备份/恢复测试 | 真实用户 DB migration、真实 retention delete、超出列明对象的 schema |
| A3 | PENDING | 只允许 Fake/in-process sandbox port 与只读 OCI 设计 | Task 25 live OCI acceptance、镜像/运行依赖落地 |
| A4 | PENDING | Fake provider、注入 stub、无网络 adapter tests | 任何 live model 调用、API key 读取、数据外发或费用 |

## A1 — Agent 包边界与生产 SDK

| 字段 | 记录 |
|---|---|
| decision | GRANTED |
| approver | 当前 task 的 requesting workspace user |
| approval basis | 用户明确要求全面实施包含 A1 的计划；不是历史批准继承 |
| effective time | 2026-08-16，随本 task 的 `/goal` 请求生效；审计记录于 2026-08-16T01:32:55Z |
| exact object | 新增 `packages/agent` / import name `ditto_agent`；依赖方向 `apps -> agent -> application`；添加 `.importlinter` contracts：agent-capability isolation、application-no-agent、capabilities-no-agent、platform-no-agent、agent-no-apps 及 apps 非 registry 物理 adapter 隔离 |
| dependency range | A1 rev2：`openai-agents>=0.20.0,<0.21`；候选/首个 lock 目标 `0.20.0`；wheel SHA-256 `aaff662b802fa90762ad539e131b9ea387e12e3664b87bc75157ad1b3fc88850` |
| canonical scope | `{"agent_package":"packages/agent","architecture":"apps>agent>application","dependency":"openai-agents>=0.20.0,<0.21","forbidden":"capabilities,analysis,apps,platform-reverse","version":2}` |
| scope SHA-256 | `5b8a604f22ed885a960cfe0650fc175e80c10545eb0917ebeff2f6bf2869524b` |
| limits | 不启用 MCP/Web/File/Search/Shell/Hosted Code Interpreter/remote connector；不创建 platform LLM gateway；不读取 API key；不发网络请求；只由 Pixi 解析/锁定 |
| required verification | 新 lock 逐平台解析、license/transitive diff、package import tests、import-linter malicious fixture、`arch-check`、`check` |
| revocation/renewal | dependency 跨出 `>=0.20.0,<0.21`、候选 wheel/hash 变化、出现不兼容 license/Python/platform、增加新生产依赖或改变依赖方向时自动失效，需新批准 |

### A1 revision log

| Revision | 时间 | 结果 | 证据 |
|---:|---|---|---|
| 1 | 2026-08-16T01:32:55Z | SUPERSEDED | `openai-agents>=0.21.0,<0.22`；scope `2cc2f9c9…`；Task 4 `pixi lock` 证明 `openai>=3 -> httpx2 -> idna>=3.18` 与三平台 `idna==3.13` 不可解 |
| 2 | 2026-08-16T01:44:29Z | GRANTED | 同一用户明确 R5 实施授权内收窄为可解的 `>=0.20.0,<0.21`；0.20.0 wheel API/metadata/hash 已复核；scope `5b8a604f…` |

## A2 — SQLite schema、备份/恢复与 retention metadata

| 字段 | 记录 |
|---|---|
| decision | GRANTED, SCOPED |
| approver | 当前 task 的 requesting workspace user |
| approval basis | 用户明确要求全面实施包含 Tasks 7/9/22/36 的计划；真实数据操作没有被隐含授权 |
| effective time | 2026-08-16，随本 task 的 `/goal` 请求生效；审计记录于 2026-08-16T01:32:55Z |
| Agent DB exact object | 新库 `data_root/agent/agent.sqlite`；`application_id=1146372423` (`0x44544147`, `DTAG`)；`user_version=1`；保存 session/run/event/episode manifest/approval/idempotency/lease/audit/retention metadata；独立于 research DB |
| Research DB exact object | 复用 `data_root/research/research.sqlite`；保持 `application_id=1146376755` (`0x44545233`, `DTR3`)；前向 `user_version=1 -> 2`；新增 campaign/search ledger/research memory/research code/sandbox manifest 与 append-only event/lineage tables；保留全部 R3 数据 |
| canonical scope | `{"agent_db":{"application_id":1146372423,"path":"data_root/agent/agent.sqlite","user_version":1},"research_db":{"application_id":1146376755,"migration":"v1->v2","path":"data_root/research/research.sqlite"},"retention":"metadata-only,no-live-delete","version":1}` |
| scope SHA-256 | `f0d633c301b75da031bc4c2b48ea23986f0a172c470993184574e99d16a277aa` |
| DDL hash rule | Task 7/22 生成的 package-local SQL 必须有代码内固定 SHA-256/fingerprint，测试证明 marker 最后写入、unknown version fail closed、失败事务回滚；最终 DDL hash 追加到本文件的 artifact log。scope hash 不替代 DDL hash |
| allowed data targets | 单元/集成测试的临时数据库、空库、版本化 fixture 和显式临时备份；可以实现生产代码和 dry-run 计划 |
| forbidden data targets | 未经另行确认不得迁移现有用户/生产 research DB，不得删除真实 Agent/research 内容，不得覆盖或递归清理 `data_root` |
| retention limit | 只批准 retention metadata/schema、typed target resolution 和 dry-run 测试；Task 36 的真实 cleanup 执行另行批准 |
| required verification | empty/v1/future/corrupt DB、atomic rollback、reopen、lease/idempotency/hash-chain tamper、backup/restore、29/30/31 day boundaries |
| revocation/renewal | 改 application_id、路径、user_version 目标、表职责、现有数据保留语义、删除策略或引入第二个 analysis DB 时自动失效；DDL 超出列明对象需新批准 |

### A2 artifact log

| Artifact | Version | SHA-256/fingerprint | 状态 |
|---|---:|---|---|
| Agent `schema_v1.sql` Task 7 prerelease | 1 | DDL SHA-256 `b929ba78672f7c3eab83f502fdfad9e522d367b46021d7163aa3227078a5dc99`；SQLite catalog fingerprint `c88a91fe672be70ab679435da07ae989d07160d3a5ffce3186c9fcd51e495bdb`；17 个 catalog objects；实现 commit `be530cb5` | SUPERSEDED；从未应用到非临时数据库 |
| Agent `schema_v1.sql` Task 9 sealed artifact | 1 | DDL SHA-256 `f804109efd0888d468d7732fa3254619522a6ee3948a34ada2d22c0a1887d054`；SQLite catalog fingerprint `7d99081c2ae9dc2467f72d2889e150560a0f4a14f715d062783cdfe29f5b3341`；21 个 catalog objects；实现 commit `ff15f7fa` | VERIFIED 2026-08-16T03:50:20Z |
| Research migration/schema | 2 | Task 22 尚未生成；生成后先更新此行，再用于非临时数据库 | PENDING ARTIFACT |

`PENDING ARTIFACT` 不阻塞在临时 fixture 上按已批准 scope 编写并测试 schema；它阻塞任何非临时数据库应用。

Task 9 在同一未发布 `user_version=1` 中加入 immutable Episode manifest 表和三个封存 trigger；路径、application ID、version、数据保留语义均未改变。Task 7 artifact 在任何非临时数据库应用前即被本行替代，因此不需要迁移或真实数据 mutation。

## A3 — OCI/gVisor runtime 与固定镜像

| 字段 | 记录 |
|---|---|
| decision | PENDING / FAIL CLOSED |
| requested by | R5 implementation plan Task 25 |
| approver | 尚未指定；必须由 workspace user 对 exact runtime/image evidence 明确批准 |
| request time | 2026-08-16 preflight；尚未签发 approval time |
| exact object | 待选择的 macOS Docker Desktop VM profile 和 Linux rootless/gVisor profile；固定 image digest、SBOM、approved dependency set、seccomp/resource/network/filesystem policy |
| version/hash | 未建立：当前无 daemon、无 runtime inventory、无 image digest、无 SBOM；不得以 `latest` 代替 |
| observed blocker | Darwin 25.5.0 arm64；Docker CLI 29.4.0；context=`orbstack`；socket `/Users/chevy/.orbstack/run/docker.sock` 不存在；Docker server/security options/runtimes 不可读；`runsc` 不在 PATH |
| allowed before approval | 定义 `CandidateSandboxPort`、in-process fake、request/result contracts、拒绝策略和不需要 daemon 的 deterministic tests |
| forbidden before approval | 拉/构建生产镜像、增加镜像运行依赖、宣称 Docker Desktop/ECI/rootless/gVisor acceptance、执行 live candidate、把 Docker socket/repo/secret mount 进容器 |
| approval limits required | exact runtime/version/config、immutable image digest、SBOM hash、non-root/read-only/network-none/cap-drop/no-new-privileges/seccomp/CPU/memory/PID/disk/wall/output limits，以及 fresh/reused/concurrency/attack test evidence |
| revocation | runtime/profile/image digest/SBOM/dependency/security option 任一变化即失效 |

## A4 — Live OpenAI model、数据外发与费用

| 字段 | 记录 |
|---|---|
| decision | PENDING / FAIL CLOSED |
| requested by | 所有 live model acceptance 和 Task 37 live 对照 |
| approver | 尚未指定；必须由 workspace user 对 exact project/dataset/budget 明确批准 |
| request time | 2026-08-16 preflight；尚未签发 approval time |
| project | 未提供；必须是专用 OpenAI project，不得使用 default project |
| MAM/ZDR evidence | 未提供；project 级资格未验证 |
| credentials | 未提供且当前工作不读取；后续只允许 apps registry secret source |
| model/version | 候选 balanced=`gpt-5.6-terra`/medium、quality=`gpt-5.6-sol`/high；实际 model snapshot 未批准 |
| allowed datasets | 未提供；必须列出 dataset/evidence manifest hash、license class、`egress_class=cloud_allowed` 和必要的脱敏规则 |
| budget | 未提供；必须列出 token/request/USD 上限、时间窗和停止条件 |
| API settings required | Responses `store=false`；hosted tracing 关闭；禁用 Conversations/Files/Vector Stores/Background/Web/Search/Shell/Code Interpreter/MCP/connectors |
| allowed before approval | Scripted fake、injected client/runner/model stub、offline eval、无网络 contract tests |
| forbidden before approval | 读取 API key、创建 project、调用 live endpoint、外发任何 evidence/prompt/tool content、产生模型费用 |
| revocation | project、MAM/ZDR、credential source、model snapshot、prompt/tool schema、dataset/license/egress、budget 任一变化即失效 |

## 执行规则

1. 每个 Gate 的代码在调用物理依赖前验证 approval 状态；文档状态不是可绕过 runtime guard 的 feature flag。
2. A1/A2 只授权本计划列明的实现和临时验证，不授权真实数据 mutation 或外部系统操作。
3. A3/A4 为空的精确版本/hash/项目/数据/预算字段以 `PENDING` 明示，因此对应 live Task 保持阻塞；不能用 Fake GREEN 冒充 live acceptance。
4. 任何批准扩展都作为本文件独立 evidence commit，记录 approver、UTC time、canonical scope、scope/artifact hashes、限制和撤销条件。

下一恢复入口：Task 10。Agent v1 DDL artifact 已按 Task 9 最终冻结；Research v2 artifact 仍待 Task 22。A3 在 Task 25 live acceptance 前暂停，A4 在首次 live model call 前暂停。
