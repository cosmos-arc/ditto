# R5 Runtime 与依赖技术证据

**核对日期：** 2026-08-17
**代码基线：** `b5dbb921`
**性质：** Task 4 Pixi lock、A3 OrbStack 物理 sandbox、A4 Coding Plan 在线验收与生产 credential 边界证据；未创建 OpenAI project

## 结论

- 建议生产依赖范围为 `openai-agents>=0.20.0,<0.21`，由 Pixi lock 固定实际 wheel；本轮核对的候选 wheel 是 `openai-agents==0.20.0`。0.21.0 已被实际 Pixi solver 证据排除。
- adapter 能用当前 Python API 实现 typed run/stream/resume、function-tool approval 和本地 continuation state；普通测试必须使用 scripted fake 或注入的 runner/model stub，不访问网络。
- 每个 Responses 调用必须显式设置 `ModelSettings(store=False)`；SDK hosted tracing 禁用，Ditto 在 model/tool 边界写既有 OpenTelemetry spans。
- OpenAI adapter 与 GPT profile 仍保留为显式可选路径，不被 GLM 配置覆盖；使用时必须提供相应 OpenAI credential/scope 并重跑 provider-specific eval。本轮实际在线验收固定 GLM `glm-5.3`：balanced=`high`、quality=`max`。
- A3 已在 OrbStack 2.2.1 的 `orbstack` context 上完成物理 acceptance：固定 arm64 image/SBOM/lock/seccomp，通过 11 类攻击、fresh-container、并发和 `fit→score`。Kubernetes 未使用；`runsc` 不可用，因此结论不外推为 gVisor 或 Linux rootless acceptance。
- GLM endpoint 已按 credential kind 硬分流：Coding Plan 在线验收使用 `/api/v1` Responses；生产 GLM 使用 `/api/paas/v4` Chat Completions。Coding Plan balanced/quality 各 120-case 已通过并关闭 R5 在线验收；标准 API 尚未调用，生产启用前必须替换 key 并复核 provider 数据控制与实际 model identity。

## 上游事实源

仅使用官方产品/项目文档和候选 wheel metadata：

- OpenAI [Agents SDK 概览](https://developers.openai.com/api/docs/guides/agents)、[Python quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart)、[运行 Agent](https://developers.openai.com/api/docs/guides/agents/running-agents)
- OpenAI [Guardrails 与人工审批](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals)、[运行结果](https://developers.openai.com/api/docs/guides/agents/results)、[Observability integrations](https://developers.openai.com/api/docs/guides/agents/integrations-observability)
- OpenAI [数据控制](https://developers.openai.com/api/docs/guides/your-data) 与 [模型目录](https://developers.openai.com/api/docs/models)
- Docker [rootless mode](https://docs.docker.com/engine/security/rootless/)、[Docker Desktop 容器隔离 FAQ](https://docs.docker.com/security/faqs/containers/)、[Enhanced Container Isolation](https://docs.docker.com/enterprise/security/hardened-desktop/enhanced-container-isolation/)
- gVisor [Docker quick start](https://gvisor.dev/docs/user_guide/quick_start/docker/)、[security model](https://gvisor.dev/docs/architecture_guide/security/)、[production guide](https://gvisor.dev/docs/user_guide/production/)

## Python 依赖冻结

### 候选包

| 项 | 证据/裁决 |
|---|---|
| package | `openai-agents` |
| 核对版本 | `0.20.0`，Python `>=3.10`，MIT |
| 建议范围 | `>=0.20.0,<0.21`；快速演进 API 不跨 minor 自动升级 |
| wheel | `openai_agents-0.20.0-py3-none-any.whl` |
| wheel SHA-256 | `aaff662b802fa90762ad539e131b9ea387e12e3664b87bc75157ad1b3fc88850`（下载后本地复算一致） |
| 下载地址 | `https://files.pythonhosted.org/packages/9f/8b/18528f00cb1a5d0b8e00f457f7dc88e7b17439bc520861aae2b638b88710/openai_agents-0.20.0-py3-none-any.whl` |
| 当前仓库 | Python 3.13；Task 4 已把 `openai-agents>=0.20.0,<0.21` 写入 `pixi.toml` 和 `ditto-agent` metadata，并由 `pixi.lock` 固定 0.20.0 |
| 安装方式 | A1 rev2 后通过 Pixi metadata 重解 `pixi.lock`；没有用 pip/poetry/conda 手工改环境 |

Task 4 已以新 lock 复核全部三平台。`openai-agents==0.20.0` 与 `openai==2.54.0` 在 `osx-arm64`、`linux-64`、`win-64` 一致；SDK 的宽 `mcp>=1.19,<3` 约束在 macOS 解析为 2.0.0，在 Linux/Windows 解析为 1.29.0。该平台差异不改变 R5 能力面，因为产品不注册 MCP server、connector 或 tool；后续 SDK 升级仍须重新审批和锁定。

### 直接 transitive review

| SDK 约束 | 2026-08-16 metadata 观察 | License | 与当前 Ditto 的关系/风险 |
|---|---|---|---|
| `openai>=2.45,<3` | lock 2.54.0（全平台） | Apache-2.0 | 新增；保留 `httpx<1` 路径，网络 client 与 Responses 数据控制是主要安全面 |
| `mcp>=1.19,<3` | lock 2.0.0（macOS）；1.29.0（Linux/Windows） | MIT | 新增且依赖面较大；R5 不注册 MCP server/tool/connectors，SDK 间接安装不代表产品启用；平台差异已显式保留 |
| `griffelib>=2,<3` | 2.1.0 | ISC | 当前 lock 已有兼容 2.x；重解 lock 后核对平台一致性 |
| `pydantic>=2.12.2,<3` | 2.13.4 | MIT | 项目约束 `>=2.10,<3`，当前 lock 有兼容 2.13.x |
| `requests>=2,<3` | 2.34.2 | Apache-2.0 | 当前 lock 有兼容 2.x；不用于 Agent tool 任意出网 |
| `typing-extensions>=4.12.2,<5` | 4.16.0 | PSF-2.0 | 兼容；低风险 typing runtime |
| `websockets>=15,<17` | 上游最新已到 17.x；SDK 上限排除 17 | BSD-3-Clause | 当前 lock 为兼容 16.x；Task 4 不应突破 SDK 上限 |

Task 4 的 Pixi solver 和三平台 `pixi tree` 证据确认：没有已识别的 license 禁止项，没有 Python 3.13 平台缺包，没有把 MCP/hosted tools 暴露为 R5 能力，也没有覆盖 Ditto 已有 OTel 或 HTTP 配置。Pixi 对 `pyjwt[crypto]` 输出 extra metadata warning；lock 仍成功且 R5 不使用 MCP/JWT 能力，该 warning 记为后续依赖升级复核项，不把它解释为产品能力授权。

## Agents SDK adapter API 证据

候选 wheel 的公开 API 与签名核对结果：

### 0.21.0 solver rejection

2026-08-16 在仓库三平台 lock 上实际运行 `pixi lock`。`openai-agents==0.21.0 -> openai>=3 -> httpx2>=2.7`，而可用 `httpx2` 要求 `idna>=3.18`，当前 conda solve 固定 `idna==3.13`，且没有可满足版本；solver 明确判定 requirements unsatisfiable。0.20.0 保留 `openai>=2.45,<3 -> httpx<1`，同时 wheel 检查确认 R5 所需 API 未丢失。该结果是把 A1 从候选 rev1 收窄到 rev2 的原因，不通过跳过 lock 或手工 pip 绕过。

| R5 需要 | SDK 0.20.0 surface | adapter 裁决 |
|---|---|---|
| agent/run | `Agent`、`Runner.run`/`run_sync`/streaming、`RunConfig`、`ModelSettings` | `AgentModelPort` 只公开 R5 所需 typed run/stream/resume；SDK 类型不穿过 agent 公共合同 |
| 自定义/注入模型 | `agents.models.interface.Model` 的 `get_response`/`stream_response`；`ModelProvider.get_model` | OpenAI adapter 注入 client/model/runner；Fake 不继承网络 client |
| function tools | `function_tool(...)`，支持 `needs_approval` | 只注册显式 allowlist；hosted Web/File/Search/Shell/Code Interpreter/MCP 永不注册 |
| HITL interruption | `RunResult.interruptions`、`RunResult.to_state()`；state `approve(...)`/`reject(...)` 后 `Runner.run(agent, state)` | SDK interruption 只是模型 continuation；Ditto 仍计算并复核 authority/action hash/expiry |
| 状态序列化 | `RunState.to_json(...)` 与 async `RunState.from_json(initial_agent, state_json, ...)` | 脱敏 JSON 存本地 Agent SQLite；禁止 pickle；恢复前重建同一 manifest 并验证 hash/authority |
| Responses storage | `ModelSettings.store` 传入 Responses request | 每个 profile 固定 `store=False`，不能依赖 SDK/API 默认值 |
| tracing | `RunConfig.tracing_disabled`、`trace_include_sensitive_data`、trace processors | 固定 `tracing_disabled=True`、`trace_include_sensitive_data=False`；不向 OpenAI hosted tracing 发 prompt/tool payload |

### mock 与 shared contract

普通 CI 使用两层 deterministic 测试：

1. `ScriptedAgentModel` 实现 `AgentModelPort`，脚本化 typed final output、tool call、usage、interruption、timeout/rate-limit/failure 和 continuation token。
2. OpenAI adapter 单测注入 runner/model/client stub，捕获构造参数和 request settings，证明 `store=False`、hosted tools 拒绝、usage/interruption/state 映射正确；禁止真实 HTTP。

Fake 和 adapter 运行同一 shared contract suite。只有独立 live suite 才能读取 API key，且不能替代 deterministic suite。

### approval continuation

SDK state 不是 Ditto 的权限事实源。安全恢复顺序固定为：

1. tool intent 先由 Ditto canonical codec 生成 action hash，持久化 `ApprovalRequest`、run event 和 SDK continuation JSON；
2. operator 决策写本地 append-only audit；
3. resume 时复核 action hash、operator authority、tool allowlist、temporal/snapshot identity、expiry 和 budget；
4. 只对完全相同的 SDK interruption 调用 `approve`/`reject`；
5. 从序列化 state 恢复同一 run，副作用工具另受 idempotency key 与 lease 约束。

改变参数、PIT、snapshot、预算、权限或 expiry 会得到新 action hash，旧 state 不能授权新动作。

### OTel bridge

R5 不使用 SDK 的 OpenAI-hosted trace 作为审计事实源。`ditto_agent` 在 `AgentModelPort`、tool dispatch、approval、store 和 campaign 边界创建 Ditto OTel spans，并只写低基数、非敏感 identity/hash/usage/status attributes。现有 apps registry 注入 tracer/exporter；adapter 不调用全局 `set_trace_processors`，避免改变其它进程。Agent SQLite hash-chain 和 Episode 是可回放证据，OTel 是观测副本。

## OpenAI 数据与模型 profile

官方数据控制文档说明 API 数据默认可能用于最长 30 天 abuse monitoring；MAM/ZDR 需要获批组织/project。Responses 在 `store=true` 或默认存储路径下还涉及 application-state retention。因此 R5 live gate 要求：

- 专用 OpenAI project，不使用 default project；
- 该 project 的 MAM 或 ZDR 资格有可审计证据；
- 每个 Responses 请求 `store=false`；
- 禁用 Conversations、Files、Vector Stores、Background mode、hosted tools 和远程 connectors；
- 仅 `egress_class=cloud_allowed` 且 license 允许的最小 evidence 进入 prompt/tool output；
- API key 只从 apps registry secret source 注入，不进 config dump、event、Episode 或测试 fixture。

| profile | model id | reasoning | 2026-08-16 目录价格 | 用途/限制 |
|---|---|---|---|---|
| balanced | `gpt-5.6-terra` | medium | input $2.50 / output $15，每百万 token | 默认解释、tool selection、普通草案 |
| quality | `gpt-5.6-sol` | high | input $5 / output $30，每百万 token | 高难假设、代码生成、独立复核 |

模型可用性、价格和 snapshot 是时变事实。A4/live acceptance 必须重新核验并把实际 model snapshot、prompt/tool schema hash、token/spend budget 写入 manifest；这里不授权调用或费用。

## OCI feature matrix

| 环境/能力 | 所需安全语义 | 本机观察 | Gate |
|---|---|---|---|
| macOS OrbStack VM | Linux VM 隔离；不挂载 host/repo/secret/Docker socket | OrbStack 2.2.1；Docker server 29.4.0；aarch64；kernel `7.0.14-orbstack-00380-ga7e0a2dc9535` | A3 已通过 |
| daemon/runtime inventory | 每次运行前核对 context、server、OS、arch、kernel、cgroup、security options、runtimes | context=`orbstack`；cgroupfs；seccomp/cgroupns；runc 1.5.1；profile 漂移即拒绝 | A3 已通过 |
| Docker rootless | daemon/containers 在 user namespace 中以 non-root 运行 | macOS 本机不构成 Linux rootless acceptance；需单独 Linux runner | 未验证 |
| Docker Desktop ECI | user namespace/Sysbox 强隔离；Business-only；启用时 runtime 选择语义不同 | 无 Desktop/ECI 状态证据 | 未验证，不可宣称 |
| gVisor `runsc` | 截获 guest syscall、减少 host kernel surface；仍需外部 network/resource policy | `runsc` 不在 PATH，也不在批准 runtimes 中 | 不在本次 A3 scope |
| network | `--network none`，无代理/host gateway；socket/connect 均被阻断 | physical network/socket probes PASS；自定义 seccomp 不允许 socket syscalls | A3 已通过 |
| filesystem/process | non-root、read-only rootfs、tmpfs、cap-drop ALL、no-new-privileges、seccomp、PID/CPU/memory/disk/wall/output limits | root/host mount/secret/rootfs/fork/OOM/timeout/oversize probes 全部符合预期；uid/gid 65532 | A3 已通过 |
| image provenance | immutable digest、SBOM、批准依赖，无动态下载 | image digest `1dfc536c…`；SBOM `13383b2b…`；lock `3baecd03…`；seccomp `82bce6de…` | A3 已通过 |

macOS 与 Linux 不共享一份“已验证”结论：本次证据仅覆盖上述 OrbStack VM profile。若以后引入 Linux runner，必须重新证明 rootless daemon，并优先验证 gVisor；Kubernetes 对单用户本地部署没有必要。gVisor 即使可用也不替代 `--network none`、resource limits、read-only filesystem、serialization/schema limits 或 fresh-container isolation。

## 后续批准与恢复入口

| Gate | 精确对象 | 当前状态 |
|---|---|---|
| A1 | `openai-agents>=0.20.0,<0.21` 与 solver/lock transitive diff | GRANTED rev2；0.21.0 的 unsatisfiable 证据已记录，0.20.0 三平台 lock 已通过 |
| A3 | 指定 OCI runtime/profile、image digest、SBOM 和攻击测试矩阵 | GRANTED/PASSED：OrbStack 2.2.1 arm64；11/11 attacks + fresh/concurrency/fit-score |
| A4 | Coding Plan credential、冻结合成 dataset、provider controls、license/egress、model revision、每 profile token cap | R5 ONLINE ACCEPTED：balanced/quality 各 120/120 PASS；不授权生产 credential |

R5 实施计划已无未完成 Gate。生产 cutover 时替换为 GLM 标准 API credential，复核 provider 数据控制、license/egress、实际 model identity 与部署配置；任何 provider/model/profile/prompt/tool/dataset 变化都重跑相关 eval。A3 profile 任一漂移也必须重新验收。
