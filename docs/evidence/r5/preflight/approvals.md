# R5 Approval 证据

**记录时间：** 2026-08-16T01:32:55Z
**记录分支：** `codex/r5-governed-agent`
**请求来源：** 当前 Codex task 中 workspace user 明确请求 `/goal 全面完成 docs/plans/2026-08-12-r5-governed-quant-research-agent-implementation-plan.md 的功能开发计划`
**解释规则：** 该请求是对计划内实现动作的明确授权，不是把 2026-08-04 的原则性意见或设计文档接受推定为批准。授权只覆盖下面列明的 exact scope；A3 已由用户对 OrbStack 物理执行明确授权并形成 live evidence，A4 rev4 只授权 Coding Plan 合成在线验收，不授权 Plan 凭证用于 standalone/生产运行、真实数据外发、真实数据写入或真实清理。

## 状态总览

| ID | 状态 | 可越过的 Gate | 仍然阻塞 |
|---|---|---|---|
| A1 | GRANTED | Task 4 的第 13 包、机器边界和精确 SDK minor range | SDK range/license/边界超出 scope 的任何变更 |
| A2 | GRANTED, SCOPED | Tasks 7/9 Agent SQLite v1；Task 22 Research SQLite v1→v2 migration 的代码、临时 fixture、备份/恢复测试 | 真实用户 DB migration、真实 retention delete、超出列明对象的 schema |
| A3 | GRANTED / ACCEPTED | OrbStack VM、固定 OCI image/SBOM/lock/seccomp 与物理攻击验收 | runtime/profile/image/依赖/策略任一漂移；Linux/gVisor/Kubernetes 不在本次批准范围 |
| A4 | GRANTED / ONLINE ACCEPTED | 固定 GLM 5.3 + Coding Plan 内存凭证 + balanced/quality 各 120-case 合成在线验收 | Coding Plan 的 standalone/生产使用；生产部署必须替换标准 API key |

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
| Research `migration_v1_to_v2.sql` sealed artifact | 2 | v1 base DDL SHA-256 `697d10854fb12e324ddcff349bad55b9b442425b244cb5f1852d7192cfb7a8fd`；migration SHA-256 `34916eab0f426dc6a2c0401a76f8abc2b610e0e4c8a2c5fffb81919b7c7f0b78`；最终 SQLite catalog fingerprint `7b4a6d03f4ba879ca54fd47220b7d28728bcb58c87cdca3cdfe27a5466cd51e0`；95 个 catalog objects；实现 commit `672722c8` | VERIFIED 2026-08-16T10:01:40Z |

`PENDING ARTIFACT` 不阻塞在临时 fixture 上按已批准 scope 编写并测试 schema；它阻塞任何非临时数据库应用。

Task 9 在同一未发布 `user_version=1` 中加入 immutable Episode manifest 表和三个封存 trigger；路径、application ID、version、数据保留语义均未改变。Task 7 artifact 在任何非临时数据库应用前即被本行替代，因此不需要迁移或真实数据 mutation。

## A3 — OCI/gVisor runtime 与固定镜像

| 字段 | 记录 |
|---|---|
| decision | GRANTED rev2 / PHYSICAL ACCEPTANCE PASSED |
| requested by | R5 implementation plan Task 25 |
| approver / basis | 当前 task 的 requesting workspace user；明确表示“不需要 k8s，太重了”“你启动吧 我审批”，授权启动 OrbStack、构建固定测试镜像并执行物理攻击验收 |
| effective/evidence time | 2026-08-17 生效；rev2 最终 release evidence 捕获于 `2026-08-17T07:55:21.518181+00:00` |
| exact runtime | OrbStack 2.2.1；Docker context=`orbstack`、server 29.4.0、aarch64、kernel `7.0.14-orbstack-00380-ga7e0a2dc9535`、cgroupfs、runc 1.5.1；显式 `docker --context=orbstack`，调用前逐次验证 daemon profile |
| exact image | `ditto/r5-research-sandbox@sha256:1dfc536c998095f86ddf4e3922f9d52fb9e561e0a733499482cbbc5a45ab1d85`；`linux/arm64`；user/UID/GID `65532:65532`；entrypoint `/opt/ditto/bin/candidate-runner` |
| supply chain | base `python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8`；仅 `numpy==2.3.2`、`polars==1.32.2`；lock `3baecd036b99f08c219583cba5e5cf509450005508df250a8b70f5837f9469c6`；SBOM `13383b2b2f7b2e7ee6a3b290afc3ee2d74f29871633f7ba4aebf40dc99641f92` |
| security profile | network none、无 host mount/socket/env、non-root、read-only rootfs、bounded noexec tmpfs、cap-drop ALL、no-new-privileges、IPC none、CPU/memory/PID/tmpfs/wall/output limits；default-deny aarch64 seccomp hash `82bce6def5bbb123ff00790fe63b3efc562197fa7767c7d608d3372210100591` |
| excluded profiles | Kubernetes 不使用；`runsc` 在该 macOS runtime 不可用，不能继承为 gVisor 或 Linux rootless acceptance；Docker Desktop/ECI 也未声明 |
| canonical scope | `docs/evidence/r5/release/sandbox-live-status.json` 内 `approval_scope`；scope SHA-256 `0be61039d3d4160728fd7033b3818b27f61649f664deec9db780b7171c3065e1`；security evidence hash `16d0e35bf733ef1a110659aeb8a767f032a9c79d02d77a5c3e9574ca07918108` |
| physical evidence | 11/11 网络/socket/Docker socket/host mount/secret/root/rootfs/fork bomb/OOM/timeout/oversize-output 攻击符合预期；fresh-container、两容器并发、`fit→score`、零残留容器均通过；内部 report hash `65cfdc7f854b374c08e8b358617fa77374b903b1e579101d4c39f5caa4f0765f`，文件 SHA-256 `ffb9273b06fe4f1e828c67aff5289527d331dbcd5bccc85dae03b0d14d81dca1` |
| runtime boundary | Docker daemon/socket 只由 Apps composition 的 host runner 使用，绝不进入 Agent、application 或候选容器；普通 CI 继续使用 fake，不自动启动 daemon |
| revocation | runtime/profile/image digest/SBOM/dependency/security option 任一变化即失效 |

## A4 — Live model、数据外发与费用

| 字段 | 记录 |
|---|---|
| decision | GRANTED / R5 ONLINE ACCEPTANCE COMPLETE；PRODUCTION CREDENTIAL NOT GRANTED |
| requested by | 所有 live model acceptance 和 Task 37 live 对照 |
| approver | 当前 task 的 requesting workspace user；明确表示“直接使用 glm plan 我授权”“先拿这个做测试验证，最终上线替换成正式 api 不走 plan” |
| effective/evidence time | validation scope 与 120-case online acceptance 均于 2026-08-17 生效 |
| provider/endpoint | GLM OpenAI-compatible Responses；`https://open.bigmodel.cn/api/v1`；代码中固定，不从进程级 base URL 漂移 |
| credential boundary | `glm_coding_plan_validation`；macOS Keychain service=`codex-zai-api-key`、account=`chevy`，只注入固定环境名 `DITTO_AGENT_GLM_VALIDATION_API_KEY`；secret 不入库、不入报告、不进入 repr |
| project / MAM/ZDR | Coding Plan 不冒充 OpenAI project 或 MAM/ZDR；只允许无用户/市场/持仓/真实研究数据的冻结合成 eval，因此不构成生产数据控制证明 |
| model/version | 本次固定 `glm-5.3`；模型、endpoint 或 credential kind 改变即需新证据 |
| allowed dataset | smoke 使用 `synthetic-no-user-data-v1`；在线验收使用 manifest `6cd838cc190354e70c31aa6af94786578073beb1c17f8d98bea7f0ec55335114` 的 120 条冻结合成 cases；二者均不含真实 Ditto evidence |
| allowed execution context | 只限智谱官方支持的 Codex 开发任务；[Codex 专页](https://docs.bigmodel.cn/cn/coding-plan/tool/codex)规定 Responses endpoint 为 `https://open.bigmodel.cn/api/v1`，[Coding Plan FAQ](https://docs.bigmodel.cn/cn/coding-plan/faq)明确自建应用/独立 API 集成必须使用标准 API；单用户不扩大订阅范围 |
| prompt/tool identity | smoke 入口为 `packages/apps/src/ditto_apps/scripts/r5_glm_validation.py`，证据生成时文件 SHA-256 `000a7aef158ed2fca96ebfb0c2cc73fea80bfff0ff358f559cec0788db15ba05`；正式 120-case 的 provider prompt/function-tool schema 由 `packages/apps/src/ditto_apps/registry/agent/release_eval_provider.py` 语义化生成，manifest hash `6f0829b47d9ed24e54c4f0427f1829613327b220f8e95fb4e35e6c48e64d6c93`；release preflight 重新计算并绑定该 hash、A4 scope 与 A4 materials |
| budget/stop | smoke 恰好 2 requests / ≤4096 tokens；正式在线验收每个 profile 120 cases、最多 500,000 total tokens，并保留单 case request/turn/tool/output/timeout 限制；身份、质量、安全、usage 或延迟任一硬门不符立即失败 |
| API settings | Responses `store=false`；hosted tracing 关闭；只允许 function tool；禁用 Conversations/Files/Vector Stores/Background/Web/Search/Shell/Code Interpreter/MCP/connectors |
| canonical scope | `docs/evidence/r5/preflight/glm-coding-plan-a4-scope.json`；材料见 `glm-coding-plan-a4-materials.json`；固定 endpoint/protocol/credential kind、model/revision、dataset、provider controls、license/egress 与每 profile 500,000 token cap |
| scope SHA-256 | formal run identity 中的 A4 scope hash `0a3244486e365a275f3e99d6a5bbcef84d567b947c2b01db810b1709377cb219` |
| live evidence | smoke report hash `2cada92fbce27545fc90e7b625a0d2c810175f355306c4dc4265c82b884971b5`；balanced report hash `9120574701e0bc123e7a26944efe3ab78b52b51da0de364142190d71e033bf72`；quality report hash `3d41ef0e00b3bfde168effd18f631f5a222a1d9de7e6c93557d07a6a156fa412` |
| observed result | PASS：balanced 120/120、242,462 tokens、read P95 20.058 s、complex P95 22.729 s；quality 120/120、250,644 tokens、read P95 22.877 s、complex P95 21.935 s；两份报告所有 suite/质量/安全/usage/延迟硬门均通过 |
| production guard | Apps composition 对 Coding Plan credential + `production_mode=true` 必然拒绝；Coding Plan 固定 `/api/v1` Responses，GLM `formal_api` 固定 `https://open.bigmodel.cn/api/paas/v4` Chat Completions 且 continuation/provider identity 不互通；上线必须替换 credential 并重新完成正式 A4 |
| still forbidden | 真实行情/持仓/研究 evidence 外发；Coding Plan 生产使用或从 standalone Ditto/app/runtime 调用；把未评估的货币成本写成零成本；把本次结果冒充 GLM 标准 API 或 OpenAI provider 的生产验收 |
| production cutover requirements | 用 GLM 标准 API key 替换 Coding Plan credential，重新核对 provider 数据控制、license/egress、实际 model identity 与部署配置；如 model/profile/prompt/tool/dataset 或边界变化则重跑相关 eval。该 cutover 是部署前条件，不是 R5 实施计划的未完成项 |
| revocation | endpoint、credential source/kind、model、prompt/tool schema、dataset、budget 或 production mode 任一变化即使本 validation grant 失效 |

### A4 revision log

| Revision | 时间 | 结果 | 证据 |
|---:|---|---|---|
| 1 | 2026-08-16 | PENDING | 无正式 credential/dataset/usage cap；所有 live 命令 `not_run` |
| 2 | 2026-08-17 | GRANTED, VALIDATION-ONLY | 用户明确授权 GLM Coding Plan 测试；合成 smoke report hash `2cada92f…`；生产与 release gate 保持关闭 |
| 3 | 2026-08-17 | SCOPE CLARIFICATION | 官方 Codex 专页确认 `/api/v1` Responses；FAQ 确认订阅不得成为 standalone/self-built API 集成，canonical scope 增加 Codex execution context；未新增 provider call |
| 4 | 2026-08-17 | GRANTED / ONLINE ACCEPTED | 用户明确确认“只要在线验收的内容使用 plan 的 key 都通过了就行”；A4 materials/scope 固定合成数据、`glm-5.3`、balanced=`high`、quality=`max` 和每 profile 500,000-token cap；两份 120-case 报告及 release preflight PASS |

## 执行规则

1. 每个 Gate 的代码在调用物理依赖前验证 approval 状态；文档状态不是可绕过 runtime guard 的 feature flag。
2. A1/A2 只授权本计划列明的实现和临时验证，不授权真实数据 mutation 或外部系统操作。
3. A3 只对上述 OrbStack 2.2.1/aarch64 固定 scope 通过；A4 rev4 越过 R5 的合成 120-case 在线质量/SLO Gate，但不越过 standalone/生产 credential Gate；不能用 Fake、smoke 或 Coding Plan 结果冒充标准 API 生产验收。
4. 任何批准扩展都作为本文件独立 evidence commit，记录 approver、UTC time、canonical scope、scope/artifact hashes、限制和撤销条件。

R5 实施计划无恢复 blocker：Agent v1 DDL、Research v2 artifact、Task 25/A3、Task 37 双 profile 在线验收和 Task 38 release preflight 均已完成。后续若进入真实部署，恢复入口是生产 cutover：注入 GLM 标准 API key、复核生产 provider/data-control scope，并在任何受验收身份变化时重跑对应 eval。
