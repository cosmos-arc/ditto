# A0 · 前端 ditto-app 接真实后端 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 让 ditto-app 从"MSW mock 原型"变成"能消费真实后端、能记录决策"的可日常使用产品。

**Architecture:** ditto-app（独立仓库 `/home/chevy/projects/ditto-app`，React 19 + TanStack Query/Router + Vite + Biome + bun）。四步：① Vite proxy + env，关掉 dev 默认 MSW；② OpenAPI codegen 消除手写 type 漂移；③ 用已有 `apiClient.post/put` 接写路径（`useMutation`）；④ 去 mock、关键页接真实 API。

**Tech Stack:** React 19 / TanStack Query 5 / TanStack Router / Vite 8 / Biome / Vitest / MSW / openapi-typescript；**bun**（禁 npm/yarn/pnpm）。

**战略索引:** [wave1 主计划](2026-06-24-wave1-implementation-plan.md) §5；[战略定位](2026-06-24-strategic-positioning-and-functional-gap-analysis.md) §4。

> **⚠️ 独立仓库：** 本工作流在 `/home/chevy/projects/ditto-app`（非 ditto 后端仓库），遵循 **ditto-app/CLAUDE.md**（bun、biome、零 `any`/`@ts-ignore`、零 inline style、Feature-based、`bun run check`）。
> **⚠️ 后端依赖：** A1（eod publish）+ B3（真实数据 promotion）是"前端看到真实信号"的前置；A0 联调前二者须就绪。

---

## 现状实证

- [main.tsx](../../ditto-app/src/main.tsx) L34-39：`enableMocking()` 在 `import.meta.env.DEV` 下**无条件**启 MSW（`worker.start({ onUnhandledRequest: "bypass" })`）。
- [api-client.ts](../../ditto-app/src/lib/api-client.ts) L1：`API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api"`（无 env → fallback `/api` 打到 dev server 自己 → 404）。**写方法已存在**：`apiClient.post/put/patch/delete`（L74-87）——问题是被使用次数 = 0，不是不存在。
- [vite.config.ts](../../ditto-app/vite.config.ts)：无 `server.proxy`。
- [package.json](../../ditto-app/package.json)：`openapi-typescript` 已装（devDep）但**无 codegen 脚本**；`msw@2.12`；`bun run check` = biome + tsc + vitest。
- 后端 `/trade` 闭环 API（ditto 仓库）：`POST /trade/fills`、`PUT /trade/intents/{id}/status`、`GET /trade/signals/latest`、`GET /trade/deviation` 等。`types/trading.ts` 有 `ConfirmSignalRequest`/`ValidateOrderRequest` 定义但未用。

---

## Task A0.0：Vite proxy + env + 关 MSW

**Step 1：** 加 `ditto-app/.env.development`：
```
VITE_API_BASE_URL=/api
VITE_USE_MOCK=false
```
**Step 2：** 改 `vite.config.ts` 加 dev proxy（后端端口须确认——ditto granian 端口，Grep `pixi.toml` server 任务确认；假设 `http://localhost:8000`）：
```ts
server: { proxy: { "/api": { target: "http://localhost:<backend-port>", changeOrigin: true } } }
```
**Step 3：** 改 `main.tsx` `enableMocking`：仅当 `import.meta.env.VITE_USE_MOCK === "true"` 启 MSW；默认 false（连真实后端）。MSW 仅作测试/演示开关保留。
**Step 4（RED→GREEN）：** Vitest 测试：`VITE_USE_MOCK` 未设时不启 worker（mock import 不触发）；设为 true 时启。
**Step 5：** 冒烟：`bun run dev` + 起后端 → 某只读页（如 `/market`）能打到真实 API（无 404/MSW fixture）。
**Step 6：** `bun run check` + Commit `feat(app): wire vite proxy + gate MSW behind VITE_USE_MOCK`。

---

## Task A0.1：OpenAPI codegen

**Step 1：** ditto 后端导出 OpenAPI（apps 已有 maturity-aware schema 生成）。确认导出方式（如 `ditto` CLI 或 `/openapi.json` 端点）。
**Step 2：** 加 `package.json` script：`"gen:api": "openapi-typescript <openapi-source> -o src/types/generated/api.d.ts"`。
**Step 3：** 生成 `src/types/generated/`；逐步用生成类型替换 `src/types/*.ts` 的手写 API 响应类型（保留手写 view model）。
**Step 4：** `bun run check` + Commit `chore(app): add openapi-typescript codegen`。

---

## Task A0.2：写路径（决策闭环 useMutation）

> 目标：用**已有** `apiClient.post/put` 接通后端写端点。零 `any`，类型来自 codegen。

**Step 1（RED）：** 为 `useRecordFill`（`POST /trade/fills`）写 Vitest + RTL 测试：渲染含按钮的组件 → 点击 → 断言 `apiClient.post` 以正确 payload 调用、query invalidate。
**Step 2（GREEN）：** 在 `features/trading/hooks/` 新增：
- `useRecordFill` → `apiClient.post("/trade/fills", payload)` + invalidate signals/positions；
- `useUpdateIntentStatus` → `apiClient.put(\`/trade/intents/\${id}/status\`, payload)`；
- （可选）`useConfirmSignal`。
payload 类型用 A0.1 生成的类型（或 `types/trading.ts` 既有 `ConfirmSignalRequest` 等）。
**Step 3：** 给 [trading overview "执行调仓"按钮](../../ditto-app/src/features/trading/trading-page.tsx)（无 onClick）接 `useRecordFill`/confirm 流程。
**Step 4：** `bun run check` + Commit `feat(app): add trade write paths (record fill / update intent status)`。

---

## Task A0.3：去 mock + 关键页接真实 API

> 逐页推进，每页一个 commit。先 Read 该页 + 其 hook/mock，再接真实 API、删 mock 常量。

**清单（按价值排序）：**
1. **signals inbox**（`GET /trade/signals/latest`）—— 决策入口，最高优先。
2. **positions**（`GET /trade/positions`）+ **pnl**（`GET /trade/pnl`）。
3. **deviation**（`GET /trade/deviation`，推荐 vs 实际）—— 复盘核心。
4. **comparison**（`GET /trade/comparison`，回测 vs 实际）。
5. portfolio / strategy list / backtest list / factor list / watchlist（去硬编码 mock）。

**每页 Step：**
1. Read 页组件 + 当前数据源（mock 常量 or MSW handler）。
2. 用 TanStack Query `useQuery` 接真实端点（类型来自 codegen）；删 mock。
3. RED→GREEN：Vitest 覆盖 loading/error/empty/data 状态。
4. `bun run check` + Commit `feat(app): wire <page> to live backend`。

> instrument/risk 页若有 `待实现` 标记，本轮可保留 stub 但接真实只读端点。

---

## Task A0.4：端到端联调（首次真实使用预演）

**前置：** ditto 后端 A1（eod publish）+ B3（真实数据 promotion）就绪。
**Step 1：** 起后端（granian）+ 前端 dev（`bun run dev`，`VITE_USE_MOCK=false`）。
**Step 2：** 跑一次 eod（或 `ditto strategy publish-signals`）→ 前端 **signals inbox** 看到真实信号。
**Step 3：** 录一笔 fill（A0.2 写路径）→ **positions** 更新 → **deviation** 显示推荐 vs 实际偏差。
**Step 4：** 视觉验证（ditto-app 四层模型 L0-L3，见 `ditto-app/.claude/rules/visual-verification.md`）——至少 L0 完整性 + L2 布局不破。
**Step 5：** Commit `chore(app): e2e smoke with live backend`（或仅记录证据）。

---

## DoD

- [ ] dev 默认连真实后端（MSW 仅 `VITE_USE_MOCK=true` 启）；vite proxy 生效。
- [ ] OpenAPI codegen 接入；手写 API type 不再漂移。
- [ ] 写路径（record fill / update intent status）可用；trading 决策按钮有 onClick。
- [ ] signals/positions/deviation/comparison 接真实 API；关键 mock 移除。
- [ ] 端到端联调：看到真实信号 → 录 fill → 看 deviation。
- [ ] `bun run check` 全绿；零 `any`/`@ts-ignore`/inline style。

## 风险

| 风险 | 缓解 |
|---|---|
| 后端端口/CORS 未对齐 | A0.0 先确认 granian 端口 + proxy；CORS 由后端中间件或 proxy 绕过 |
| codegen 与手写 type 冲突 | 增量替换，保留 view model；生成的放 `types/generated/`，禁止手改 |
| 联调依赖 A1/B3 未就绪 | A0.0-A0.3 可先用 MSW handler（基于真实 OpenAPI 生成）开发；A0.4 联调待后端就绪 |
| 去 mock 后页面空状态/错误态缺失 | 每页 RED 测试覆盖 loading/error/empty；遵循 ditto-app 设计系统空态 |
