# R1–R5 前端完成与 Live 验收报告

**结论：PASS**

**验收日期：2026-08-25**

**范围：** `docs/plans/2026-08-18-r1-r5-frontend-completion-plan.md` 的 Wave 0–8、F0.1–F8.4。

## 1. 验收环境与边界

- 前端：`ditto-app`，Bun，Vite `VITE_USE_MOCK=false`，`127.0.0.1:5173`。
- 后端：相邻 `ditto` 仓库的生产 FastAPI/Granian application composition，隔离数据根位于 `/private/tmp`，真实 SQLite persistence，`127.0.0.1:8000`。
- 原型：本地静态服务 `127.0.0.1:8888`，验证 1536、1366、1024、768 四档视口。
- 浏览器：Codex 内置浏览器，验证 live DOM、交互、截图和控制台诊断。
- 本次未启用正式 provider credential、真实券商或生产环境；未发起真实 provider 调用、真实订单或生产数据写入。后端只使用无外呼的占位 token 启动隔离验收实例。
- Decision Opinion 的成功态使用真实公开 route 与受控的测试 composition 验证；完整生产 application 验证 `unavailable` 降级。正式 provider 采购与线上用量不属于本计划。

## 2. 自动化质量矩阵

| 门 | 结果 | 证据摘要 |
|---|---|---|
| `bun run ci` | PASS | 快速阶段 165 files / 1426 tests；覆盖率阶段 163 files / 1410 tests；全局 statements 82.53%、branches 76.83%、functions 80.96%、lines 84.59%；prototype/Playwright、build 全绿 |
| `bun run audit:routes` | PASS | 33 条 IA routes 全覆盖 |
| `bun run audit:tokens` | PASS | gating token pairs 全绿；仅保留 200 条非门禁 prototype dead-link 信息项 |
| `bun run build:tokens:check` | PASS | 355 tokens / 9 layers，一致性通过 |
| `bun run prototype:gates` | PASS | 28 个原型门全绿 |
| `bun run prototype:visual-matrix` | PASS | 28 个视觉矩阵产物重新生成 |
| `bun run visual:audit` | PASS | 0 warnings |
| `pixi run -e dev check` | PASS | Ruff、format、basedpyright 0 errors；12,927 passed、1 expected xfail；imports 43 kept / 0 broken；architecture smell 与 harness 全绿 |
| `pixi run -e dev arch-check` | PASS | 后端架构门全绿 |
| 两仓库 `git diff --check` | PASS | 无 whitespace error |

OpenAPI 从后端重新导出并在前端连续生成两次，生成物哈希一致：

```text
b7cc0396220131f183e132af443760bc3a0d4d4ba05263602c0eeb8c3e7b2a26  src/types/generated/api.d.ts
```

R5 preflight：`release_status=passed`，报告哈希：

```text
169eda470e4a784da5ae0ff5ed9ee53776d2748dd4723f3e843d49f05d87030b
```

页面合同状态：Agent Console v4、Trading Overview v2、Portfolio v2、Risk Center v2、Platform v2 均为 `contract-ready`；landing contract 按 schema 设计保持 `draft`，不构成消费页面门禁失败。

## 3. R1 Fill Ledger Live 验收

输入使用确定性 seed artifact：

```text
signal-package-seed_etf_industry_rotation-v1-2026-07-10-eod-2026-07-10-seed_etf_industry_rotation-1-e7e67237358d
manual-r1-paper-seed_etf_industry_rotation
sig-eod-2026-07-10-seed_etf_industry_rotation-1-2026-07-10-e7e67237358d-600519-buy
```

| 动作 | 结果 | Request ID |
|---|---|---|
| 写入 partial A `live-r1-partial-a` | accepted | `dd398fb0-17e5-49ea-a65f-010028c90991` |
| 写入 partial B `live-r1-partial-b` | accepted | `1ebad64b-af8f-4b1d-80d6-4fa398c8b890` |
| replace A 为 `live-r1-partial-a-corrected` | accepted，adjustment `live-r1-adjust-replace` | `0ce170b1-a9bf-48fa-8e94-d76c8f9595b5` |
| void B | accepted，adjustment `live-r1-adjust-void` | `ed0c4dee-c71d-42f5-8d01-a02d4d8578fe` |
| 对已 void 记录再次执行非法 void | 409，fail closed | `d1edf7d9-ab21-4189-964d-62adfe520b10` |
| 读取 raw ledger | 200 | `915d8094-e6c1-429a-8172-7114d18ad4f6` |
| 读取 effective ledger | 200 | `15d81c2b-24e5-467c-9781-c7efbbccd7b3` |
| 读取 adjustments | 200 | `cb46a34d-09e2-40d9-bda8-7f3ccab3e01b` |
| 读取最终 Daily Decision V3 | 200 | `d8f3026b-4492-441f-a461-86c7e9cca401` |

最终 UI 和 V3 一致显示有效成交 `750 / 4000`、剩余 `3250`。截图：[R1 Fill Ledger](screenshots/r1-fill-ledger.jpg)。

## 4. R2 运营治理 Live 验收

- Catalog 真实查询返回 19 个 data products；Operations 页面同时呈现 backlog 2、source health ready、fallback review-required、promotion blocked。
- Remediation 创建精确审批 `remediation-approval-21cf6b07c0b94dcc9be29718661880ca`，payload hash `a9668d15642ba9e0af18b17f3e06f37ab01e53e67a5483bad3b4695fb13ece90`；读取 request `c1e61803-0796-43f5-93de-69c1cb639c4a`，reject request `f343b969-ad78-44e7-8758-84c8f50482e9`。
- Fallback policy `source-fallback-policy-5c654e75-27b0-461d-8c95-acb6201158d3` 完成 list、approve、activate、retire 和 events 回读；request IDs 依次为 `830ec8c9-9ab8-4e5b-9de0-41776242a2ed`、`52083227-cd16-430f-9e23-2c6423e82893`、`44d82744-b342-4454-b6b4-94e542f0f43c`、`662320b2-a1fe-4e9d-96b4-37e7c9d14e9f`、`7a901265-e4e9-41fb-b732-8d12ae6196c3`。
- UI 仅在合同允许的状态暴露治理动作，精确 payload/hash 预览后才允许确认。

截图：[Operations](screenshots/r2-operations.jpg)、[Remediation Approval](screenshots/r2-remediation-approval.jpg)。

## 5. R3 回跳与 Author 应用边界

- Author preview、Approval Inbox、exact payload/hash、approve/reject、应用结果与研究/评审回跳均由公开 Agent projection 驱动。
- application 与 approval 合同保持独立；前端不存在跳过审批直接应用的路径。
- 刷新、filter、pagination、drawer、mobile/desktop action tests 均覆盖；旧 `/ai/**` 请求和旧 Copilot 产品入口已清退。

## 6. R4 Daily Decision V3 / Portfolio / Risk Live 验收

| 场景 | 结果 | Request ID |
|---|---|---|
| ready | 完整、可行动；effective fill `750 / 4000` | `4a596c7a-7fc7-4fd2-9911-e93d0775435f` |
| review | `需复核`；0 actions；ES99 `4.10` | `4c8f5bba-db25-4f71-b247-aa0dff745de4` |
| blocked | `阻塞`；5 个 reason codes；actions closed | `2d34e73f-2463-4f75-ae33-b0469efd7a2d` |

- Trading、Portfolio、Risk 使用同一完整 Daily Decision identity，切换 identity 后未发现旧数据串线。
- Portfolio 显示 OSQP solver；Risk 使用 Historical ES99。
- Decision Briefing 标记 `SHADOW ONLY`，独立 error boundary；生产 application 返回 unavailable 时 V3 authoritative 内容、readiness、weights、risk 和 orders 不受影响。
- Decision Opinion 成功态真实 route request：`acceptance-628ce759-f2d1-42bb-a8e6-71b5862c2008`；完整生产 application unavailable request：`e2a317b1-2834-4844-b408-8111ae16dda9`。
- Trading 分析带使用 design token 固定为 180px；四视口均满足主工作区大于状态横幅，且主工作区加分析带大于横幅的两倍。

截图：[Ready](screenshots/r4-ready.jpg)、[Review](screenshots/r4-review.jpg)、[Blocked](screenshots/r4-blocked.jpg)、[Portfolio](screenshots/r4-portfolio.jpg)、[Risk](screenshots/r4-risk.jpg)。

## 7. R5 Agent Run / Approval / Campaign Live 验收

验收数据根：`/private/tmp/ditto-r1-r5-live-final.gF2wFb`。前端通过生产 Agent/Campaign routers 与真实 SQLite persistence 完成以下闭环。

### Run 与 SSE

- Run：`run-fa45dd53816058f58e4da480b963ad56`。
- Session request：`acceptance-b652d8ee-3427-493c-acbd-48153565c840`。
- Create request：`acceptance-52250478-31a0-4194-a43c-3dd49003b4dc`。
- Cancel request：`acceptance-cf8266c6-d496-49d6-b820-d006889ef735`。
- SQLite audit event 2：`run_queued`，hash `284f1dc41eb50694068b830b262aa488edf54f1c159218ddc444f10250cc007a`。
- SQLite audit event 3：`run_cancelled`，hash `ea366fd46d205b0b81710f50ecc2164e1dfe1cec2f53880d35f8025122206021`。
- 创建、SSE 更新、断线 cursor 恢复、刷新后历史恢复、取消与最终 projection 均通过。

### Approval

- Exact approval approve request：`acceptance-312d9b5c-8c3f-4ad4-a186-044f5e6c6183`。
- Exact approval reject request：`acceptance-e798f1b1-aab0-46f4-ae51-c744ed4dc4a6`。
- UI 在确认前显示 exact target、payload 和 hash；过期、hash tampered 与状态冲突均 fail closed。

### Campaign

- Campaign：`campaign-live-acceptance`。
- 四阶段 validation requests：`acceptance-55f3e71c-95f8-48bd-9ef3-00ab5fd181c7`、`acceptance-f0340355-ff5f-4aab-9613-35a532a90aea`、`acceptance-8ceb7239-2b7b-4b7a-9abe-ce11726bc40e`、`acceptance-6d6c7272-974f-4627-8bb4-70b98d0109b6`。
- Create / approve / cancel requests：`acceptance-908a5c2c-7212-4301-9129-12f8962083e4`、`acceptance-90cbfd97-563d-47d9-9156-eb36595f1466`、`acceptance-6a4b48b9-e8fd-4113-9a1e-d53b0b007f1c`。
- 持久化事件：`campaign-campaign-created-09e083acc44205e8b81bc9e5`、`campaign-campaign-authorized-b0acd423ac7f92f6a369dea7`、`campaign-campaign-cancel-requested-b0acd423ac7f92f6a369dea7`、`campaign-campaign-cancelled-b0acd423ac7f92f6a369dea7`。
- Draft Wizard、逐步 manifest validation、exact approval、监控、刷新恢复、取消与最终 projection 全部通过。

截图：[Run Create Ready](screenshots/run-create-ready.jpg)、[Run Created](screenshots/run-created.jpg)、[Run Cancelled](screenshots/run-cancelled.jpg)、[Approval Exact Preview](screenshots/approval-exact-preview.jpg)、[Approval Approved](screenshots/approval-approved.jpg)、[Approval Rejected](screenshots/approval-rejected.jpg)、[Campaign Draft](screenshots/campaign-draft.jpg)、[Manifest Validated](screenshots/campaign-manifest-validated.jpg)、[Campaign Approved](screenshots/campaign-approved.jpg)、[Campaign Cancelled](screenshots/campaign-cancelled.jpg)。

## 8. 失败注入与恢复

后端目标失败注入测试 20 / 20 通过，覆盖：

- provider、database、sandbox、exporter outage；provider disabled 与 no-fallback；
- spend、token、turn budget 及 overrun 不调用 provider；
- expired approval、hash tampering、重复/冲突动作；
- provider timeout、进程重启后 continuation、SSE cursor 恢复；
- malformed sandbox output、Campaign 逐步 validation failure。

R2 治理目标测试 63 / 63 通过。所有破坏性或受治理动作均采用显式确认，失败时保留 authoritative 状态且不静默 fallback。

## 9. 安全、Mock 与浏览器检查

- Live 页面 DOM 和构建扫描未发现生产 mock fallback 或旧 `/api/v1/ai`、`/api/ai/`、`/ai/` 请求。
- `src` 与 `dist` 的 provider secret 扫描为零命中，覆盖 `TUSHARE_TOKEN`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GLM_API_KEY`、常见 `sk-...` 和 Bearer token 模式。
- Agent、Trading、Data Products 的第一方生产源码未发现 `localStorage`、`sessionStorage` 或 `indexedDB` 持久化调用。生产 bundle 包含 TanStack Router 的 `sessionStorage` 滚动恢复和 Zustand 依赖的通用 persist 实现；二者均无 provider secret 命中，也没有第一方代码把 provider key、Agent payload 或治理 payload 接入这些 storage API。
- 浏览器控制台 warnings/errors 为零；页面无未处理 alert。
- 浏览器工具政策不允许读取 profile、cookie 或 storage 内容，因此未直接枚举浏览器 storage；以第一方数据流、生成 bundle 的 secret 零命中扫描、live URL/DOM 和控制台证据覆盖泄密边界。Router 的滚动位置仍会按框架设计保存在 session storage。
- 原始 HTTP request log 仅存在于临时隔离验收根，没有提交到仓库；本报告保留可复核的 request/event IDs 和脱敏截图。

## 10. 最终判定

Wave 0–8 的实现、合同、原型、自动化、真实后端隔离验收、安全门和发布证据均通过。R1–R5 前端完成里程碑 M4 达成；剩余的正式 provider credential、生产部署、真实券商连接和生产写入仍受原计划审批边界约束，不是本次完成项。
