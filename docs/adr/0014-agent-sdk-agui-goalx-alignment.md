# 0014 - 研究 Agent 沿用 OpenAI Agents SDK，以 AG-UI 对齐 GoalX 交互

**状态**：Accepted（方向已批准，产品接线未实施）
**日期**：2026-09-20
**依据**：[研究 Agent 产品边界决定](https://github.com/cosmos-arc/ditto/issues/247)。维护者确认四项建议，并明确要求技术栈和前端交互与 GoalX 一致，使用 AG-UI 和 OpenAI Agents SDK。

## 背景与已核实基线

Ditto 已依赖 `openai-agents>=0.20.0,<0.21`，`packages/agent/src/ditto_agent/models/openai_adapter.py` 已调用 Runner.run/run_streamed，并处理工具审批中断与恢复。不是重新引入 Agent 框架；现有持久化事件、SDK 适配器、session/run 与治理能力应复用。

GoalX 参考基线为 `fad2dd48ba351bda5d9a84f08905bfcdfa05f3f9`：

- [后端 ask.py](https://github.com/cosmos-arc/goalx/blob/fad2dd48ba351bda5d9a84f08905bfcdfa05f3f9/apps/backend/src/goalx_backend/llm/ask.py)：Python Agents SDK → AG-UI typed events / SSE encoder；无存证情报时明确降级。
- [前端 transport](https://github.com/cosmos-arc/goalx/blob/fad2dd48ba351bda5d9a84f08905bfcdfa05f3f9/apps/web/src/api/agui-transport.ts)与[追问面板](https://github.com/cosmos-arc/goalx/blob/fad2dd48ba351bda5d9a84f08905bfcdfa05f3f9/apps/web/src/components/ask-analyst.tsx)：Vercel AI SDK useChat + @ag-ui/client，业务详情内追问、流式文字、来源/时点徽章及错误反馈。

核查边界：GoalX 后端 extract_question 只取最后一条 user 消息；transport 的 reconnectToStream 返回 null，当前徽章列出上下文情报而非逐条证明回答引用。它是技术栈和交互参考，不是 Ditto 多轮记忆、精确引用、停止/恢复已经完成的证据。本轮只读 GoalX 源码，没有运行其浏览器或模型调用。

## 决策

| 层 | 选型与职责 |
| --- | --- |
| 模型运行 | Python OpenAI Agents SDK，沿用 Ditto SDK adapter；不在 TS 或前端再运行模型编排 |
| 服务端交互 | FastAPI + ag-ui-protocol，SDK/持久化业务事件映射为 AG-UI；不增加 Node BFF |
| Web 交互 | React + Vercel AI SDK useChat + @ag-ui/client 薄 transport，经 feature adapter 进入 Ditto view model |
| 展示 | 对齐 GoalX 的业务对象内追问、流式回答、来源/时点、证据不足及错误反馈；沿用 Ditto token/组件，不引入第二 UI 体系 |

[AG-UI](https://docs.ag-ui.com/introduction)负责 Agent 与用户界面的事件交互。[OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk)负责应用内模型运行；业务部署、工具、状态与审批仍由宿主掌握。二者不是互斥框架，也不要求改变模型供应商。

- 允许保留原始要求、修订、经用户确认的结构化约束和证据引用。前端可用自然语言连续追问，不再以“禁止自由文本/社交气泡”代替产品边界；每轮仍为独立可审计 run，研究入口锚定对象。
- 会话/研究状态与审批、预算、试验族由 Ditto 权威存储管理，不新增另一套互相覆盖的 SDK session 真相源。模型生成摘要是待验证解释；用户原文、外部文本、AG-UI context/state/tools 均不是权限凭据。
- 工具仍经 agent → application 执行业务能力；时间、快照、许可和审批由服务端验证。切换研究/账户时重新核验，跨 session 的同一研究不能重置预算与试验族。证据过期/修订显式失效。
- AG-UI 为展示投影，不能替代持久化审计链。事件 ID、顺序、重复、终态和游标须映射；断线重放不得重新执行模型或工具。取消与重试分别定义，失败流不得被当作成功完成，费用与预算不能因断线或失败遗漏。
- SDK 与 AG-UI 只读/工具/审批状态以真实服务端事件呈现；批准必须走既有独立授权命令，不由模型文本或客户端状态补丁完成。保留 tracing 隐私与导出许可控制。

## 实施与验证边界

先在已有研究 Agent 票中定义消息、run/session 身份、流事件和恢复映射，再接一个完整对象内多轮旅程。公共 API、协议引用/扩展、鉴权与 SSE 版本纳入同提交 OpenAPI/typed transport 合同，不照搬 GoalX 的自由字段或类型断言。兼容期间只保留一个权威事件源；旧传输的退出以消费者迁移为准。

版本以两仓 lockfile 和实际兼容性验证为准，不直接复制 GoalX 的宽版本范围。实施需核对 Python SDK、AG-UI 两端与 AI SDK 的取消/错误/恢复行为；本轮只改计划，不安装依赖，不启动付费模型。

验收覆盖：两轮条件修订、旧证据失效、精确引用、跨对象越权、注入文本、预算累计、审批恢复、取消、断线重复重放及失败计费。保存可读产物、实际执行结果与持续使用证据，不能只以 SSE 通流作为完成。

Campaign 从已有 OCI 验收的精确范围复核当前环境，再做单一搜索方向的真实闭环；安全与研究效果分开。MCP 以 Codex 的数据质量、研究证据、组合比较三项只读试用判断价值，不成为主线前置。

## 后果与替代方案

统一两项目的技术栈与交互心智，复用 Ditto 已有 SDK，新增复杂度集中在必要的协议投影与恢复接线。持续承担协议版本兼容与跨轮语义测试成本。

不选择第二 Agent 框架、Node BFF 或独立聊天平台；不逐行复制 GoalX 的单问/无重连实现；不以 SDK 自带能力取代 Ditto 的金融时间、审批和恢复保障。原 D17 中仅结构化跨轮、禁止自由文本的条款由本决定替代，其独立 run、审计与权限原则保留。
