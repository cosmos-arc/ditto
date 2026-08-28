# R1–R5 前端补齐与 R5 Governed Agent 实施计划

> **状态：** 执行中
> **日期：** 2026-08-18
> **实施仓库：** `ditto-app`
> **后端依赖：** `ditto`
> **使用场景：** 单用户、本地或单实例部署、人工决策与 paper/manual 执行
> **北极星：** 在 `VITE_USE_MOCK=false` 下，用户能够从真实后端完成 R4 风险决策复核，并监督、恢复、审批 R5 治理型研究 Agent；任何降级都结构化、可解释且不回退到 mock。

---

## 1. 执行摘要

当前前端不是“从零开始”，而是呈现明显的版本断层：

- R1 交易只读与 manual/paper 写路径基本完成，缺当前版本的真实后端写路径回归证据。
- R2 数据产品目录已经 live，运营治理、修复审批、源健康与 fallback 尚未接入。
- R3 研究实验、holdout、评审和策略治理已经完成 live 验收，不重做。
- R4 后端已完成，前端仍停留在 Daily Decision V2；Risk 页在 live 模式下仍是占位。
- R5 后端运行时和首批命令 API 已完成，但当前 Agent Console 仍调用不存在的原型端点，无法视为产品接入。

因此实施顺序为：

1. 先冻结展示契约并同步 OpenAPI，补齐 Agent 的恢复、审批和可读证据投影。
2. 直接利用已有 Daily Decision V3 交付 R4 风险决策面。
3. 交付 R5 的 Evidence、Run 恢复和精确审批核心闭环。
4. 再补 Author、Campaign、Decision Briefing 与运行态治理。
5. 最后完成跨 R1–R5 的真实后端验收。

### 1.1 单人开发优先级

| 优先级 | 交付物 | 原因 |
|---|---|---|
| P0 | Wave 0 契约、R4、R5 Evidence/Run/Approval | 形成第一条真正可用且可验收的治理闭环 |
| P1 | R2 运营治理、R5 Author、Campaign | 补齐治理动作与批量研究能力 |
| P2 | Decision Briefing、运行态/用量视图、跨页面入口 | 提升日常效率，但不阻塞核心闭环 |

完整范围按单人全职投入预估为 **45–65 个有效工程日**，其中后端展示契约约 5–10 日、前端约 40–55 日；不含正式模型 API 的采购、生产部署和真实交易接入。应按 Wave 逐段验收，不建议一次性长分支开发。

---

## 2. 事实基线与未完成清单

以下结论以 2026-08-18 的源码、测试、OpenAPI 和验收报告为准。

### 2.1 R1–R5 状态矩阵

| Release | 当前状态 | 已完成 | 仍未完成的前端工作 | 本计划处理方式 |
|---|---|---|---|---|
| R1 交易接线 | 基本完成 | Daily Decision V1/V2、signals、positions、P&L、comparison、intent/fill、fill correction | 当前版本真实后端的 fill create/replace/void、intent status 回归；清理已经被 R4 替代的 `V1a 未接 live` 文案 | 只补 live 回归和陈旧边界，不重做 UI |
| R2 数据产品 | 核心完成、运营缺失 | 19 个数据产品的 overview/coverage/quality/runs/evidence/license | remediation backlog/approval/execute、source health、source fallback、promotion readiness/history/revoke | 在现有 Data Product Workbench 增加“运营治理”，不另造通用运维平台 |
| R3 研究治理 | 已完成 | experiment create/detail/recovery、candidate selection、one-shot holdout、review queue/detail、strategy governance/reactivation | Agent 的上下文入口与回跳；持续回归 | 保留现有页面，R5 仅嵌入入口和结果关联 |
| R4 组合与风险 | 后端完成、前端未接 | 后端 Daily Decision V3 已提供完整首版风险决策面 | V3 adapter、决策 cockpit、组合构建证据、ES/VaR、因子贡献、压力测试、对账、PIT provenance | P0 独立 Wave 完成交付 |
| R5 Governed Agent | 后端核心完成、前端未接 | session/run/campaign 创建、单体查询、取消、审批、SSE 事件端点 | 能力发现、列表恢复、可读证据投影、审批队列、Evidence/Author/Campaign/Decision Briefing/运行态 UI | P0–P2 分阶段交付 |

### 2.2 OpenAPI 漂移

当前 `ditto-app/src/types/generated/api.d.ts` 记录 122 个后端路径；`ditto/docs/openapi/v1.json` 记录 134 个。缺失的 12 个路径恰好是：

- 11 个 `/api/v1/agent/**` 路径：session、run、campaign、approval 和 SSE。
- `/api/v1/trade/daily-decision/v3`。

前端 snapshot 没有多余的旧后端路径，但 Agent 原型代码绕过 generated DTO，直接调用了并不存在的 `/ai/**`、`/agents/runs` 和 `/ai/copilot/**`。

### 2.3 R4 现有契约能做什么

`DailyDecisionV3Response` 已足够完成首版 R4 前端：

- `v2.actions`：instrument、current/target/delta weight、数量、执行状态和 risk flags。
- `portfolio_construction`：求解器、版本、模式、状态、耗时、policy digest、failure code。
- `tail_risk`：Historical ES99、Historical/Parametric/Monte Carlo VaR99 与 seed。
- `factor_risk`：可用性、总风险、边际贡献、百分比贡献、Euler residual。
- `stress_tests`：catalog version、scenario losses、unavailable scenarios。
- `reconciliation`：状态、差异、alert idempotency key。
- `provenance`：decision/knowledge/publication cutoff、source snapshot IDs、generated time。

首版不需要新增 R4 API。完整的逐条约束、边界 slack 或优化目标分解目前不在 V3 响应中，只有确认日常操作确实需要时才补充专用 read model，不能阻塞首版。

### 2.4 R5 当前契约为何还不足以做产品 UI

已有接口可以创建和查询已知 ID 的对象，但页面刷新后无法恢复工作上下文，也缺少可读、脱敏的研究结果：

- 没有 session/run/campaign 列表查询。
- 没有 pending approval 列表与完整审批详情。
- SSE 只提供事件 ID、类型和 hash，适合通知与审计，不足以直接渲染研究内容。
- run/campaign 查询没有完整的可读输出、引用证据、工具执行摘要和 guardrail 详情。
- 没有 DecisionOpinion/shadow briefing 的公开查询 API。
- 没有 capability、provider runtime、model profile 可用性和降级原因的只读 API。

这些属于“前端展示契约”，应在 Wave 0 以最小 read projection 补齐，而不是让浏览器猜测内部事件或读取数据库。

---

## 3. 产品范围与非目标

### 3.1 本期必须达成

- R4 决策页面从 V2 升级到 V3，并在 blocked/review/stale/partial/unavailable 时 fail closed。
- Agent Console 可以创建、查看、恢复和取消 session/run/campaign。
- Evidence Copilot 输出必须能追溯到具体来源、cutoff、snapshot 和事件链。
- Author Copilot 的每个高影响动作都显示精确 payload、hash、有效期和影响范围，用户单独批准或拒绝。
- Campaign 在批准前不可运行，运行中可恢复、可观察、可取消。
- Decision Briefing 明确是 shadow-only，不改变 Daily Decision readiness、组合、订单或执行。
- provider key 只存在于后端运行环境；浏览器不录入、不保存、不回显 key。
- live 模式下接口不可用时展示结构化原因，不切换到 mock。

### 3.2 明确不做

- 不做 Kubernetes、微服务拆分或多节点调度控制台。
- 不做多租户、组织级 RBAC、团队协作与复杂权限矩阵。
- 不做通用聊天产品、无限对话历史、人格配置或 prompt 市场。
- 不做拖拽式 Agent DAG、任意工具编排器或多 Agent 群体协作 UI。
- 不在前端做 provider key vault、Coding Plan 登录或 API key 测试器。
- 不做精细到每次 token 计费的复杂财务系统；只显示后端提供的硬预算、已用量和停止原因。
- 不把 Agent 连接到自动交易；所有影响研究资产或决策产物的动作保持 HITL，真实交易继续走现有执行合同。
- 不为了移动端复制完整三栏工作台；移动端只保证查看、恢复、审批和取消等关键动作。

---

## 4. 信息架构与前端边界

### 4.1 路由落点

| 路由 | Release | 页面职责 | 处理方式 |
|---|---|---|---|
| `/trading` | R1/R4 | Daily Decision V3 总览、readiness、动作和关键风险 | 升级现有页面，不新增平行 cockpit |
| `/trading/portfolio` | R4 | current/target/delta、求解器证据、policy digest | 升级现有 Portfolio 页 |
| `/trading/risk` | R4 | ES/VaR、因子贡献、压力测试、对账和 provenance | 替换 live 占位页 |
| `/platform/data-products` | R2 | 数据产品目录与运营治理 | 在现有 workbench 增加 Operations 视图 |
| `/platform/agents` | R5 | session/run/campaign/approval 的监督与恢复 | 替换当前原型 Agent Console |
| `/research/**` | R3/R5 | 研究对象主界面；从已知上下文发起 Evidence/Author | 保持 R3 页面，只加上下文动作和回跳 |
| `/trading/**` | R4/R5 | 从确定的 decision identity 请求 shadow briefing | 嵌入式只读面板，不变成聊天页 |

### 4.2 能力边界

- `src/features/agent/**` 作为新的 R5 feature 边界，替代分散且使用旧契约的 `src/features/ai/**`。
- `src/features/trading/**` 只消费 R4 view model；Agent 结果通过稳定的 decision-opinion view model 嵌入，不能直接读取 Agent 内部事件。
- `src/features/research/**` 只传递 strategy/experiment/candidate/evidence identity 给 Agent，不复制 Agent 状态机。
- API 层消费 generated DTO，adapter 转为 feature view model；React 组件禁止直接 import generated DTO。
- TanStack Query 管理 server state；不新增全局 Agent store。仅把当前 tab、筛选和选中 ID 放在 URL/search params 或局部 UI state。
- SSE 是“有新事件”的通知通道；收到事件后按 ID 刷新 projection。不要把 SSE 流当作唯一数据源或持久状态。

### 4.3 浏览器与密钥边界

- 前端只看到 `enabled/disabled/degraded`、provider 名称、可选 profile 和脱敏错误码。
- GLM/OpenAI key、Coding Plan credential、base URL 和实际模型映射均由后端环境配置。
- 不允许 key 出现在 HTML、JS bundle、localStorage、sessionStorage、URL、Sentry payload 或浏览器日志中。
- 测试使用 deterministic fixture 或后端测试环境；最终正式上线时替换后端 key，不改前端构建。

---

## 5. 视觉与交互方向

### 5.1 用户、任务与视觉语气

- **用户：** 单个量化研究/交易操作者，而非聊天机器人用户。
- **单一核心任务：** 监督治理型研究运行，检查证据，并对精确动作作出可审计决定。
- **语气：** 延续现有 “Ditto Graphite Studio” 高密度专业工作台；AI 是研究能力，不是独立娱乐式聊天产品。

### 5.2 色彩、字体与布局

不新建品牌色板，复用现有 token：

- Graphite app：`oklch(0.166 0.010 253)`。
- Panel：`oklch(0.184 0.011 253)`。
- Lapis/平台：`oklch(0.640 0.120 235)`。
- Research purple：`oklch(0.732 0.095 300)`。
- Approval amber：`oklch(0.7341 0.1177 79.66)`。
- Critical red：`oklch(0.6656 0.1479 21.89)`。

字体继续使用 Geist Sans 标题、Inter/Noto Sans SC 界面文本、JetBrains Mono 展示 ID、hash、时间、预算和 provenance。主布局保持高密度三栏，但只在 Agent Console 使用；Trading/Risk 沿用既有页面骨架。

### 5.3 识别性设计：Evidence Spine

Agent Console 的唯一标志性元素是纵向 **Evidence Spine**：按 event sequence 展示 objective、模型输出摘要、工具调用、证据引用、guardrail、approval 和最终产物，每个节点带状态、时间和可核对 hash。它替代通用聊天气泡，使“证据从哪里来、动作在哪里被批准”一眼可见。

```text
Desktop /platform/agents
┌─────────────────────────────────────────────────────────────────────────────┐
│ Governed Research      provider: GLM · profile: balanced · degraded: none  │
├───────────────┬─────────────────────────────────────┬───────────────────────┤
│ Sessions/Runs │ Evidence Spine                      │ Inspector             │
│               │                                     │                       │
│ ● Run 104     │ 09:12  Objective ─────── hash       │ Evidence detail       │
│ ◌ Campaign 12 │   │                                 │ source/cutoff/snapshot│
│ ✓ Run 103     │ 09:13  Tool: factor evidence       │                       │
│               │   │     4 cited refs                │ Exact approval payload│
│ filters       │ 09:14  Guardrail: pass              │ hash / expiry / scope │
│ recovery      │   │                                 │ [Reject] [Approve]    │
│               │ 09:16  Result artifact              │                       │
├───────────────┴─────────────────────────────────────┴───────────────────────┤
│ status / event cursor / usage / cancel                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

```text
Mobile
┌──────────────────────────────┐
│ Governed Research   degraded │
│ [Runs] [Campaigns] [Approvals]│
├──────────────────────────────┤
│ Run 104 · waiting approval   │
│ Objective / status / budget  │
│                              │
│ Evidence Spine               │
│ ● objective                  │
│ │                            │
│ ● cited evidence             │
│ │                            │
│ ● approval required          │
├──────────────────────────────┤
│ [Inspect exact action]       │
└──────────────────────────────┘
```

### 5.4 自我审查与约束

- 三栏只服务“选择—证据—审查”关系；不能把所有 R5 功能堆在同一屏。
- Evidence Spine 只用于 Agent 事件与证据，不泛化成全站 timeline 组件。
- 任何状态不得只依赖颜色；同时显示文本、图标和可访问标签。
- hash、provenance、预算默认摘要，按需展开；避免让治理元数据压过研究结论。
- 审批按钮只有在完整 payload、hash、影响和有效期均加载成功后才可用。

---

## 6. Wave 0：契约冻结与实施基线（P0）

> **目标：** 在写 UI 前消除恢复、证据和审批契约缺口。此 Wave 是 R5 产品接入的硬前置。

### F0.1 记录现状与刷新 OpenAPI

- **目标文件：** `src/types/generated/api.d.ts`、`scripts/gen-api.sh`、本计划进度日志。
- **实施：** 从当前 `ditto` OpenAPI 生成前端类型；确认 134 条路径全部进入 snapshot；重点锁定 Daily Decision V3 和 11 条 Agent API。
- **测试先行：** 增加 compile-time/path test，先证明 V3 与 Agent path 在旧 snapshot 中不存在。
- **验收：** generated snapshot 与后端无路径漂移；不手写 DTO，不编辑生成文件修错。

### F0.2 冻结 Agent 最小展示契约（后端前置）

- **目标边界：** `ditto` 的 `application` query projection、`apps` API DTO/route；前端 `src/features/agent/api/**`。
- **必须补齐：**
  - capabilities/status：运行时 enabled、provider、profile availability、degradation reason；
  - session/run/campaign 分页列表和按 owner/context 过滤；
  - pending approval 列表、审批详情、精确 action payload/hash/expiry；
  - run/campaign 可读 projection：objective、status、output summary、redacted tool records、evidence refs、guardrail result、artifact refs、usage/budget；
  - event cursor 与 projection version，支持刷新后恢复。
- **契约裁决：** SSE 保留轻量事件通知；可读内容从 projection GET 获取，不在 SSE 中复制大 payload。
- **验收：** 空列表、disabled/degraded、partial、expired、cancelled 均有稳定 error/status code；所有敏感字段在服务端脱敏。

### F0.3 冻结 DecisionOpinion 只读契约（后端前置）

- **目标边界：** Daily Decision identity → shadow opinion read projection。
- **字段：** decision identity、status、generated_at、model profile、summary、disagreements、uncertainties、evidence refs、provenance match、shadow outcome identity、unavailable reason。
- **硬约束：** opinion 不得覆盖或改变 V3 readiness、actions、weights、risk、orders 或 execution state。
- **验收：** Agent disabled/failed 时 Daily Decision V3 仍成功；opinion 单独显示 unavailable。

### F0.4 更新页面合同和原型

- **目标文件：**
  - `docs/contracts/pages/agent-console.contract.json`
  - `docs/contracts/pages/trading-overview.contract.json`
  - `docs/contracts/pages/portfolio.contract.json`
  - `docs/contracts/pages/risk-center.contract.json`
  - `docs/contracts/pages/platform.contract.json`
  - 对应 `docs/designs/specs/prototypes/**`
- **Agent 状态：** loading、empty、disabled、degraded、running、partial、blocked、waiting-approval、approval-expired、guardrail-blocked、cancelled、failed、completed、reconnecting、stale。
- **覆盖层：** run create、cancel confirm、approval exact-action、evidence detail、artifact preview、campaign draft/approval、guardrail detail。
- **验收：** contract generator、route audit、token audit 和 prototype gates 全部通过；禁止用 `PrototypeOnlyOverlay` 表示本期 live 能力。

### Wave 0 出口

- 前端 OpenAPI snapshot 无漂移。
- 后端最小展示契约经过契约测试并已发布到 OpenAPI。
- R4/R5 页面合同已明确所有状态、数据来源和写动作。
- 浏览器密钥边界写入合同与安全测试。

---

## 7. Wave 1：R1 收尾与 R2 运营治理（P1）

### F1.1 R1 当前版本真实后端回归

- **目标范围：** `/trading/signals`、`/trading/orders`、`/trading/portfolio`。
- **场景：** record fill、replace/correct fill、void fill、intent status 更新、刷新后 ledger 一致。
- **证据：** 使用受控 paper/manual 数据；记录 request ID、前后状态和截图。测试 fixture 不能代替此项。
- **验收：** 写动作由后端拒绝非法状态转换；失败后缓存正确回滚；没有 mock fallback。

### F1.2 R2 运营查询层

- **目标文件：** `src/features/data-products/api.ts`、`hooks/**`、`types/**`、`components/data-product-workbench.tsx`。
- **接入端点：** remediation backlog/detail、source health summary/detail、source fallback summary/policies、promotion readiness/evidence/history。
- **实现：** generated DTO → operations view model；复用现有 workbench 增加 Operations 一级视图。
- **测试：** ready/empty/partial/stale/degraded/error；分页和 query key 隔离。

### F1.3 R2 受治理写动作

- **范围：** remediation approval decision/execute、fallback preview/approval/activation/retirement、promotion revoke。
- **交互：** preview → exact payload/hash → approve/reject → execute；高影响操作二次确认并显示作用数据产品、provider 和时间范围。
- **验收：** mutation 成功后只失效相关 query；重复提交显示幂等结果；过期 approval 不可提交。

### F1.4 R2 页面验收

- 目录浏览不被运营接口故障阻塞。
- source degraded/fallback active/promotion blocked 均能从数据产品页追溯证据。
- 补 deterministic acceptance 和一次当前真实后端只读/受控写 smoke。

---

## 8. Wave 2：R4 组合与风险前端（P0）

### F2.1 Daily Decision V3 adapter 与 hook

- **目标文件：**
  - `src/features/trading/api/daily-decision.ts`
  - `src/features/trading/api/mappers.ts`
  - `src/features/trading/hooks/use-daily-decision-v3.ts`
  - `src/features/trading/api/query-keys.ts`
- **RED：** 先增加 V3 URL、APIResponse unwrap、nullable/partial/PIT 缺失、blocked/review/ready 的失败测试。
- **GREEN：** generated DTO 映射为 `DailyDecisionV3ViewModel`；组件不接触 raw DTO。
- **验收：** strategy/account/trade date 进入 query key；V3 不可用时结构化报错，不悄悄降到 V2。

### F2.2 `/trading` V3 决策驾驶舱

- 将 V2 identity/actions/position 继续作为主体，新增 readiness、blocking reasons、风险 headline 和 provenance freshness。
- readiness 为 blocked 时，不显示任何“可执行”暗示；review 与 ready 视觉语义不同。
- 对每个 action 展示 current/target/delta、sizing readiness、risk flags 和 execution progress。
- **验收：** V3 ready/review/blocked/stale/partial 五态组件测试与 page-contract 测试通过。

### F2.3 `/trading/portfolio` 组合构建证据

- 展示 current/target/delta 表、总敞口、现金基线、solver/mode/version/status/duration、policy digest 和 failure code。
- 首版不虚构逐条约束；无该字段时显示“当前契约仅提供 policy digest”，而不是生成假约束。
- **验收：** solver failed/partial 时完整解释并链接到 blocking reasons；target/delta 与 V2 actions 一致。

### F2.4 `/trading/risk` 风险中心

- **替换：** 删除 live 模式下 `V1a 未接 live` 占位。
- **模块：** ES99 headline、三类 VaR99、factor contribution、Euler residual、stress matrix、unavailable scenarios、reconciliation differences、PIT provenance。
- **图形：** 只用能提升比较效率的条形图/贡献图；表格保留精确值和可访问文本。
- **验收：** unavailable factor、missing scenario、reconciliation mismatch、cutoff/snapshot 缺失均 fail closed。

### F2.5 R4 跨页一致性与验收

- `/trading`、Portfolio、Risk 共享同一 decision identity 和 freshness 语义。
- 加载或切换 strategy/account/date 时，旧数据标记 stale，不能伪装为新 identity。
- 运行 component/integration/page-contract/prototype visual matrix；增加一次真实后端 V3 smoke。
- **出口：** R4 前端可以独立宣告完成，不依赖 Agent provider 在线。

---

## 9. Wave 3：R5 Agent 基础设施（P0）

### F3.1 建立 `features/agent` 边界并清退旧端点

- **目标文件：** 新建 `src/features/agent/{api,hooks,types,components}/**`；逐步移除 `src/features/ai/**` 的旧接口使用。
- **删除/替换：** `/ai/agents/findings`、`/agents/runs`、`/ai/agents/plans`、`/ai/agents/quick-view`、`/ai/pulse`、`/ai/copilot/**`。
- **验收：** 全仓 `rg` 不再出现无后端契约的生产请求；mock handler 只存在于测试环境。

### F3.2 Capability 与降级门

- 页面首请求 capability/status；显示 runtime disabled、provider unavailable、profile unavailable、degraded reason。
- provider 不可用时仍允许查看历史 run/campaign/evidence；只禁用新建动作。
- profile 仅暴露 `balanced/quality` 等后端白名单值，不允许输入任意 model ID 或 key。
- **验收：** disabled/degraded 状态不会产生重试风暴，也不影响 R3/R4 页面。

### F3.3 可恢复 SSE 客户端

- 实现 feature-local event stream adapter：event ID、`Last-Event-ID`、指数退避上限、visibility 恢复、认证/404/410 的明确停止条件。
- 收到事件后更新 cursor 并刷新 projection；重复事件按 ID 去重。
- 页面卸载、切换 run/campaign 时关闭旧连接。
- **测试：** disconnect/reconnect、重复事件、乱序通知、cursor expired、server complete/cancelled、tab sleep/resume。

### F3.4 Agent Console shell

- 将 `/platform/agents` 改为 Runs/Campaigns/Approvals 三个任务视图，复用同一个 selection/inspector 模式。
- URL 保存 tab、filter、selected ID，保证刷新、后退和可分享恢复。
- 实现 desktop 三栏与 mobile 单列详情/底部关键动作。
- **验收：** 键盘导航、焦点返回、状态 announce、窄屏不丢审批上下文。

---

## 10. Wave 4：R5.1 Evidence Copilot 与 Run 闭环（P0）

### F4.1 Session/Run 列表与恢复

- 支持最近 session/run 分页、状态过滤、context identity 搜索和 last event cursor。
- fresh load 不依赖内存中的 ID；直接从列表选择并恢复 projection/SSE。
- empty 与 unavailable 分开；历史存在但 provider disabled 时仍可浏览。

### F4.2 创建和取消 Run

- 创建表单仅包含 objective、上下文、retention、model profile 和简化预算。
- 预算默认由服务端提供；用户只在需要时覆盖 token/spend hard cap，界面不做复杂成本估算。
- cancel 显示 run identity、当前阶段和影响，确认后提交并等待服务端终态。
- **验收：** duplicate submit 幂等；取消后禁止新工具动作；刷新后状态一致。

### F4.3 Evidence Spine 与 Inspector

- 节点类型：objective、model summary、tool request/result、evidence citation、guardrail、approval、artifact、completion/failure。
- Inspector 显示来源、knowledge/publication cutoff、snapshot IDs、hash、redaction 和关联研究对象。
- 未返回正文时只显示“内容未在展示契约中提供”，禁止从 hash 猜测内容。
- **验收：** 引用可以回跳到 R2/R3/R4 的真实对象；缺 provenance 的结论标记 blocked。

### F4.4 Evidence Copilot 跨上下文入口

- 在 strategy、experiment、candidate、factor、Daily Decision 页面增加“请求证据分析”。
- 入口只传稳定 identity 和用户 objective；不复制页面中的任意文本拼 prompt。
- Agent 完成后回链原对象；历史 run 可从对象再次找到。
- **验收：** context identity 一致、无越权工具、页面刷新不丢关联。

---

## 11. Wave 5：R5.2 Author Copilot 与 HITL（P1）

### F5.1 Author 预览

- 从 Strategy Studio/Experiment 创建页发起 authoring run。
- 结果以结构化 diff/preview 呈现：对象 identity、字段级变更、证据依据、validation/guardrail 和 artifact hash。
- 预览不是已应用状态；不能用自然语言回答替代结构化变更。

### F5.2 Approval Inbox 与精确审批

- Approval 视图支持 pending/expired/decided，展示 action type、target、payload、authority hash、artifact/manifest hash、expiry 和影响。
- Approve/Reject 只针对当前 hash；projection 更新后 hash 改变必须重新确认。
- payload、hash 或 expiry 任一缺失时按钮禁用。
- **测试：** stale approval、double decision、expired、hash mismatch、server rejection、network retry。

### F5.3 应用结果与 R3 回跳

- 批准后显示后端实际产物 identity，不在前端乐观伪造成功。
- 回到 Strategy Studio/Experiment 后重新查询权威对象并展示版本变化。
- Agent 失败或 guardrail block 不影响原研究对象。

---

## 12. Wave 6：R5.3 Campaign（P1）

### F6.1 Campaign Draft Wizard

- 分步构造 immutable manifest：hypothesis、baseline candidate、experiment plan、budget、唯一 search axis、stopping rule、allowed tools、prohibited actions、输入 hashes。
- 每步即时显示后端 validation；不支持任意 JSON 作为主流程，可提供只读 manifest preview。
- 单用户场景不做模板市场或团队共享。

### F6.2 Campaign 精确审批

- 提交 draft 后展示 canonical manifest 与 exact hash；批准必须包含 expiry 和同一 hash。
- 修改 draft 产生新 hash，旧批准自动视为失效。
- 批准与启动状态分开显示，避免“点击批准就假定已运行”。

### F6.3 Campaign 监控、恢复与取消

- 展示阶段、trial/预算进度、stopping reason、run links、evidence/artifact 和 guardrail。
- SSE 断线后从 event cursor 恢复；刷新后从 campaign list 重建页面。
- cancel 显示 exact authorization hash；完成/取消后关闭流并刷新最终 projection。

---

## 13. Wave 7：R5.4 Decision Briefing 与 R5.5 运行治理（P2）

### F7.1 Decision Briefing

- 在 `/trading` 与 Risk 页增加 shadow opinion 面板：summary、disagreement、uncertainty、evidence refs 和 provenance match。
- 固定显示 `SHADOW ONLY`，与 V3 authoritative decision 使用不同层级；不得出现“采纳并交易”。
- Agent unavailable/failed 只影响该面板，不改变页面 readiness。

### F7.2 Provider/Runtime 状态

- 在 Agent Console header/inspector 显示 provider、profile、runtime health、degradation reason 和最近检查时间。
- 只读显示后端选择；不提供 key、base URL 或任意 model ID 编辑。
- 如未来需要修改 provider，走后端环境/配置和重启流程，不在本计划前端范围。

### F7.3 简化用量与审计

- 每个 run/campaign 展示 hard budget、used、remaining、stop reason 和审计 identity。
- 提供按时间/状态的轻量汇总，不做复杂账单、货币换算或预测成本图。
- 审计导出使用后端 artifact/download 契约；前端不拼接原始审计日志。

### F7.4 Home/Research 旧 Agent 内容收敛

- 盘点 `home` 中仍调用旧 Agent finding 的模块：要么改接稳定只读 projection，要么在 live 模式移除。
- 不允许首页因 Agent runtime 不可用而整体报错。

---

## 14. Wave 8：跨 R1–R5 验收与发布证据

### F8.1 自动化质量矩阵

| 层级 | 必须覆盖 |
|---|---|
| API/adapter | URL、APIResponse unwrap、generated DTO 映射、nullable、error code、identity |
| Hook | query key、enabled 条件、retry、invalidation、stale data、SSE refresh |
| Component | 所有 page-contract 状态、审批门、键盘与 screen reader |
| Integration | fresh load 恢复、断线重连、审批 hash、campaign cancel、R4 identity 切换 |
| Prototype | desktop/mobile、loading/empty/error/stale/degraded/approval/blocked |
| Live | R1 write smoke、R2 治理 smoke、R4 V3、R5 Run/Approval/Campaign/Briefing |

### F8.2 安全与治理检查

- 对构建产物、DOM、storage、URL 和浏览器日志扫描 key/header/token 泄漏。
- 模拟 provider disabled、quota exhausted、timeout 和 malformed output，确认业务页面保持可用。
- 模拟 missing provenance、approval expired/hash mismatch、SSE cursor expired，确认 fail closed。
- 任何 Author/Campaign/Decision Opinion 都不能绕过 application 和 approval 合同。

### F8.3 最终 live 验收场景

1. 真实后端启动，前端 `VITE_USE_MOCK=false`，OpenAPI 无漂移。
2. R4 V3 ready/review/blocked 各验证一次，切换 identity 后无旧数据串线。
3. 创建 Evidence run，观察事件、断线恢复、检查证据、刷新页面恢复历史。
4. 创建 Author run，检查 exact payload/hash，分别验证 reject 与 approve。
5. 创建并批准 Campaign，观察进度，验证 cancel 和最终 projection。
6. Decision Briefing 成功与 unavailable 各验证一次，确认 V3 authoritative 内容不变。
7. provider/key 仅在后端；浏览器端扫描无 secret。

### F8.4 完成定义

- `bun run gen:api` 后生成类型与后端 OpenAPI 无漂移。
- `bun run ci`、`bun run audit:routes`、`bun run audit:tokens`、`bun run build:tokens:check` 全绿。
- 更新过的 page contracts、prototype gates 和 visual matrix 全绿。
- 若修改后端展示契约，`pixi run -e dev check` 与 `pixi run -e dev arch-check` 全绿。
- R1–R5 live 验收报告包含环境、命令、request/event IDs、截图、失败注入和结果。
- live 模式不存在生产 mock fallback，不存在旧 `/ai/**` 请求，不存在浏览器 provider key。

---

## 15. 依赖关系与里程碑

```text
F0.1 OpenAPI ───────────────┬──> Wave 2 R4 ───────────────> R4 accepted
                            │
F0.2 Agent projections ─────┼──> Wave 3 foundation ──────> Wave 4 Evidence/Approval
                            │                                  │
F0.3 DecisionOpinion ───────┘                                  ├──> Wave 5 Author
                                                               ├──> Wave 6 Campaign
Wave 1 R1/R2 ──────────────────────────────────────────────────┤
                                                               └──> Wave 7 Briefing/Ops
                                                                        │
                                                                        v
                                                                 Wave 8 final acceptance
```

### 建议里程碑

- **M0 契约可实施：** Wave 0 完成。
- **M1 非 Agent 产品补齐：** Wave 1 + Wave 2 完成，R1–R4 前端闭环。
- **M2 R5 核心可用：** Wave 3 + Wave 4 + F5.2 完成，Run/Evidence/Approval 可日常使用。
- **M3 R5 完整：** Wave 5–7 完成。
- **M4 前端 R1–R5 完成：** Wave 8 live 验收通过。

---

## 16. 审批边界

以下事项实施前需要单独确认精确目标：

1. 后端新增或修改公开展示 API、DTO 与错误码。
2. 页面合同、路由信息架构或 prototype schema 的结构性变更。
3. 正式 provider API key 启用、生产环境配置与真实用量。
4. 对真实数据执行 remediation/fallback/promotion revoke 等写动作。
5. 任何连接真实券商、自动交易或影响生产订单的动作。

普通前端组件、adapter、hook、测试、文档和只读 smoke 可按 Wave 直接推进。当前已验证的 GLM Coding Plan key 只作为先前在线验收证据；独立产品运行必须使用后端支持的正式 API credential。

---

## 17. 每个 PR 的最低验证

```bash
# ditto-app
bun run routes:generate
bun run generate-contracts       # 仅 page contract 变更
bun run check
bun run audit:routes              # 路由/页面合同变更
bun run audit:tokens              # 视觉 token 变更
bun run build:tokens:check        # 视觉 token 变更
bun run ci                        # Wave/里程碑合并前

# ditto（仅后端展示契约有改动）
pixi run -e dev check
pixi run -e dev arch-check
git diff --check
```

单元测试中的 MSW 用于确定性状态矩阵，不得被描述成真实后端验收。live 验收必须记录实际 server、环境、请求与事件证据。

---

## 18. 进度日志

实施时按以下格式追加，不提前勾选：

```text
- YYYY-MM-DD / Wave.Task / commit-or-working-tree
  - 实际改动：
  - 实际验证：
  - 失败/偏差：
  - 下一步：
```

- 2026-08-18 / Wave 0.F0.1 / working-tree
  - 实际改动：新增 generated API 必需路径的编译期哨兵；从相邻 `ditto/docs/openapi/v1.json` 重新生成前端 OpenAPI snapshot，纳入 Daily Decision V3 与 11 条 Agent API。
  - 实际验证：旧 snapshot 上 `bun run type` 按预期 RED（TS2344）；`OPENAPI_FILE=../ditto/docs/openapi/v1.json bun run gen:api` 后 `bun run type` GREEN；`bun run check` 通过（154 个测试文件、1421 个测试）。
  - 失败/偏差：首次完整检查只发现新增类型哨兵的 Biome 格式差异，修正后全绿；现有后端 OpenAPI 仍缺 F0.2/F0.3 所需展示投影。
  - 下一步：确认后端公开展示 API 与五个页面合同/原型结构变更范围，随后完成 Wave 0。

- 2026-08-18 / Wave 0.F0.2 / working-tree (`ditto` + `ditto-app`)
  - 实际改动：在后端增加 Agent capabilities、session/run/campaign/approval 列表与详情投影；新增独立脱敏的 `agent-presentation.sqlite3`，公开 objective、summary、tool/evidence/artifact、guardrail、usage、cursor/version 和 partial reason；SSE 继续只承担通知。
  - 实际验证：Agent presentation、runtime、API、campaign 与 CLI 相关测试 42 + 15 条通过；相关 Ruff 与 basedpyright 通过；OpenAPI route/snapshot 测试通过并重新生成前端类型。
  - 失败/偏差：核心 Agent DB 仅保留 hash，不能直接承担可读 UI；采用独立、可重建、脱敏 presentation projection，避免扩大核心审计存储的明文面。
  - 下一步：由 `src/features/agent/**` 消费公开 projection，完成刷新恢复与 SSE cursor 重连。

- 2026-08-18 / Wave 0.F0.3 / working-tree (`ditto` + `ditto-app`)
  - 实际改动：新增按完整 Daily Decision identity 查询的 shadow DecisionOpinion projection；升级 shadow DB schema/index；公开 summary、disagreements、uncertainties、evidence、provenance match、outcome identity 与 unavailable reason。
  - 实际验证：DecisionOpinion query/schema/route/isolation 相关测试 28 条通过；Ruff 与 basedpyright 通过；隔离测试证明 opinion 不修改 V3 readiness、weights、risk 或 orders。
  - 失败/偏差：无；disabled/failed/unavailable 被建模为独立 shadow 状态，Daily Decision V3 保持成功。
  - 下一步：在 Trading/Risk 嵌入 `SHADOW ONLY` briefing，并保持独立 query/error boundary。

- 2026-08-18 / Wave 0.F0.4 / working-tree
  - 实际改动：升级 Agent、Trading、Portfolio、Risk、Platform 五份页面合同；冻结 live API、无 mock fallback、浏览器零密钥边界、完整运行态和具体 React overlay 组件；同步五个 prototype，Agent 采用 Evidence Spine，Risk 压力证据改为 V3 只读抽屉。
  - 实际验证：RED 合同测试先命中状态、overlay 和 live/security 缺口；`bun run generate-contracts`、`bun run audit:routes`、`bun run audit:tokens`、`bun run build:tokens:check` 通过；contract/prototype 目标测试 189 条通过。
  - 失败/偏差：首次 prototype gate 发现 8 个状态徽章仅依赖颜色语义；补充 READY/风险/有效/完成等文本标记后全绿。
  - 下一步：完成 R4 缺失字段与跨页一致性，再进入 R2 和 Agent 产品接入。

- 2026-08-25 / Wave 1–2.F1.1–F2.5 / working-tree (`ditto` + `ditto-app`)
  - 实际改动：完成 R1 Fill Ledger 真实后端回归、R2 运营查询与受治理写动作、Daily Decision V3 adapter、Trading 驾驶舱、Portfolio 与 Risk 页面；补齐 loading/empty/error/stale、ready/review/blocked 和 identity 隔离。
  - 实际验证：R1 partial/replace/void/非法重复 void、R2 remediation/fallback 全生命周期以及 R4 三态 live 验收通过；R2 后端目标测试 63 条通过；页面合同、目标组件测试与四视口视觉检查通过。
  - 失败/偏差：Trading 新增 shadow 分析带后，旧原型只按四区计算高度；将分析带高度提升为 180px shell token，并更新合同测试为五区治理关系后恢复跨视口门禁。
  - 下一步：完成 Agent 公开投影消费、可恢复 SSE 与完整治理闭环。

- 2026-08-25 / Wave 3–4.F3.1–F4.4 / working-tree (`ditto` + `ditto-app`)
  - 实际改动：建立 `features/agent` 边界，清退旧 `/ai/**` 端点；实现 capability/degraded gate、cursor SSE、Console shell、Session/Run 恢复、Run 创建/取消、Evidence Spine/Inspector 和跨上下文入口。
  - 实际验证：生产 Agent router + SQLite 隔离实例完成 run create、SSE、refresh recovery、cancel 与审计 event/hash 回读；Agent Console 页面及 overlay 的 desktop/mobile 行为测试全绿。
  - 失败/偏差：presentation projection 与核心审计存储的数据职责必须分离；实现保持独立脱敏、可重建投影，SSE 只作为通知而非事实源。
  - 下一步：完成 Author、Approval、Campaign、Decision Briefing 与运行治理。

- 2026-08-25 / Wave 5–7.F5.1–F7.4 / working-tree (`ditto` + `ditto-app`)
  - 实际改动：完成 Author preview、exact Approval、应用结果回跳、Campaign Draft/validation/approval/monitor/cancel、Decision Briefing、provider/runtime、usage/audit 以及旧 Agent 内容收敛。
  - 实际验证：approve/reject、Campaign 四阶段 validation 和完整生命周期均通过 live HTTP、UI 与 SQLite event 回读；Decision Opinion 成功与 unavailable 均通过真实 route 验证，且 V3 authoritative 内容不变；20 条失败注入测试全绿。
  - 失败/偏差：正式 provider credential 不在验收授权范围；成功态采用受控的真实 route composition，完整生产 application 验证无 provider 时的 clean unavailable。
  - 下一步：执行最终质量矩阵、安全扫描和 M4 live 证据归档。

- 2026-08-25 / Wave 8.F8.1–F8.4 / working-tree (`ditto` + `ditto-app`)
  - 实际改动：刷新 OpenAPI、合同生成物、28 个视觉矩阵与 18 张 live 截图；补齐 Agent overlay/page 行为覆盖率，并归档 request/event IDs、失败注入、安全扫描和环境边界。
  - 实际验证：前端 `bun run ci`、route/token audits、prototype gates/visual matrix/visual audit 全绿；后端 `pixi run -e dev check`（12,927 passed、1 expected xfail）与 `arch-check` 全绿；OpenAPI 连续生成哈希一致。
  - 失败/偏差：浏览器工具政策禁止枚举 browser storage 内容；第一方业务源码无 storage 写入，bundle 仅含 Router 滚动恢复与 Zustand 通用 persist 实现且 secret 扫描零命中，以 live DOM/URL 与 console 零异常补充边界证据。
  - 下一步：无。M4 达成，详见 `docs/review/r1-r5-live-acceptance/report.md`。
