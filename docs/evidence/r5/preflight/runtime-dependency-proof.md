# R5 Runtime 与依赖技术证据

**核对日期：** 2026-08-16
**代码基线：** `b5dbb921`
**性质：** 只读 preflight；没有安装依赖、拉取镜像、创建 OpenAI project 或发起模型请求

## 结论

- 建议生产依赖范围为 `openai-agents>=0.21.0,<0.22`，由 Pixi lock 固定实际 wheel；本轮核对的候选 wheel 是 `openai-agents==0.21.0`。
- adapter 能用当前 Python API 实现 typed run/stream/resume、function-tool approval 和本地 continuation state；普通测试必须使用 scripted fake 或注入的 runner/model stub，不访问网络。
- 每个 Responses 调用必须显式设置 `ModelSettings(store=False)`；SDK hosted tracing 禁用，Ditto 在 model/tool 边界写既有 OpenTelemetry spans。
- 当前官方 profile 映射仍可用：balanced=`gpt-5.6-terra`/medium，quality=`gpt-5.6-sol`/high。真实调用仍被 Approval A4、专用 project、MAM/ZDR、egress/license 和预算 gate 阻塞。
- macOS 主机只具备 Docker CLI，当前 context 是 `orbstack` 且 daemon/socket 不存在；没有 `runsc`。因此这里只能冻结 OCI contract，不能形成 live sandbox acceptance。

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
| 核对版本 | `0.21.0`，Python `>=3.10`，MIT |
| 建议范围 | `>=0.21.0,<0.22`；快速演进 API 不跨 minor 自动升级 |
| wheel | `openai_agents-0.21.0-py3-none-any.whl` |
| wheel SHA-256 | `06cec842ed681ce51fbbf466891d194eb25771511067f927892b8689d75516ca` |
| 下载地址 | `https://files.pythonhosted.org/packages/f5/2a/0903d04d448531a6d1f4f246ba72e184c11d8814cfc71f7082861efd6882/openai_agents-0.21.0-py3-none-any.whl` |
| 当前仓库 | Python 3.13；`openai`、`openai-agents` 和 `mcp` 尚未出现在 `pixi.toml`/package metadata/lock 中 |
| 安装方式 | 仅在 A1 后修改 package/root Pixi metadata 并重解 `pixi.lock`；不用 pip/poetry/conda 手工改环境 |

候选范围必须在 Task 4 后以新 lock 的每平台解析结果复核；本文件不把 PyPI 当前版本当成已安装版本。

### 直接 transitive review

| SDK 约束 | 2026-08-16 metadata 观察 | License | 与当前 Ditto 的关系/风险 |
|---|---|---|---|
| `openai>=3,<4` | 3.1.0 | Apache-2.0 | 新增；网络 client 与 Responses 数据控制是主要安全面 |
| `mcp>=1.19,<3` | 2.0.0 | MIT | 新增且依赖面较大；R5 不注册 MCP server/tool/connectors，SDK 间接安装不代表产品启用 |
| `griffelib>=2,<3` | 2.1.0 | ISC | 当前 lock 已有兼容 2.x；重解 lock 后核对平台一致性 |
| `pydantic>=2.12.2,<3` | 2.13.4 | MIT | 项目约束 `>=2.10,<3`，当前 lock 有兼容 2.13.x |
| `requests>=2,<3` | 2.34.2 | Apache-2.0 | 当前 lock 有兼容 2.x；不用于 Agent tool 任意出网 |
| `typing-extensions>=4.12.2,<5` | 4.16.0 | PSF-2.0 | 兼容；低风险 typing runtime |
| `websockets>=15,<17` | 上游最新已到 17.x；SDK 上限排除 17 | BSD-3-Clause | 当前 lock 为兼容 16.x；Task 4 不应突破 SDK 上限 |

Task 4 需要保存 Pixi solver diff 并确认：没有 license 禁止项、没有 Python 3.13 平台缺包、没有把 MCP/hosted tools 暴露为 R5 能力、没有覆盖 Ditto 已有 OTel 或 HTTP 配置。

## Agents SDK adapter API 证据

候选 wheel 的公开 API 与签名核对结果：

| R5 需要 | SDK 0.21.0 surface | adapter 裁决 |
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
| macOS Docker Desktop VM | Linux VM 隔离；仅显式 bind mount 可见 host；无 Docker socket/repo/secret mount | 主机是 Darwin 25.5.0 arm64；CLI 29.4.0，但当前 context=`orbstack`，不是已验证 Docker Desktop profile | 未通过 |
| daemon/runtime inventory | 可读取 SecurityOptions/Runtimes/DefaultRuntime | socket `/Users/chevy/.orbstack/run/docker.sock` 不存在，`docker info`/server version 无法连接 | 未通过 |
| Docker rootless | daemon/containers 在 user namespace 中以 non-root 运行 | macOS 本机不构成 Linux rootless acceptance；需单独 Linux runner | 未验证 |
| Docker Desktop ECI | user namespace/Sysbox 强隔离；Business-only；启用时 runtime 选择语义不同 | 无 Desktop/ECI 状态证据 | 未验证，不可宣称 |
| gVisor `runsc` | 截获 guest syscall、减少 host kernel surface；仍需外部 network/resource policy | `runsc` 不在 PATH，daemon runtimes 不可读 | 未验证 |
| network | `--network none`，无代理/host gateway；DNS/connect 测试失败 | 无 daemon，不能运行攻击测试 | 待 Task 25 |
| filesystem/process | non-root、read-only rootfs、tmpfs、cap-drop ALL、no-new-privileges、seccomp、PID/CPU/memory/disk/wall limits | 无 daemon，不能验证 flags/escape probes | 待 Task 25 |
| image provenance | immutable digest、SBOM、批准依赖，无动态下载 | image/digest/SBOM 尚未选定 | Approval A3 阻塞 |

macOS 与 Linux 不共享一份“已验证”结论：macOS acceptance 必须证明 VM profile 和无 host mount/socket；Linux acceptance 必须证明 rootless daemon，并优先验证 gVisor runtime。gVisor 减少内核攻击面，但不替代 `--network none`、resource limits、read-only filesystem、serialization/schema limits 或 fresh-container isolation。

## 后续批准与恢复入口

| Gate | 精确对象 | 当前状态 |
|---|---|---|
| A1 | `openai-agents>=0.21.0,<0.22` 与 solver/lock transitive diff | 待 approvals evidence；用户目标允许实施计划，但 Task 3 仍需记录审计范围 |
| A3 | 指定 OCI runtime/profile、image digest、SBOM 和攻击测试矩阵 | 阻塞：本机无可用 daemon/runtime/image evidence |
| A4 | 专用 project、MAM/ZDR、API key source、model snapshot、egress/license dataset、token/spend budget | 阻塞：不进行 live 调用 |

下一恢复入口是 Approval A1（Task 3）；Fake provider、contracts 和不依赖 live OCI 的 deterministic 工作可以在相应审批范围内继续。
