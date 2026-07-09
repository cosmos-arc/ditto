# Wave 1 前端接线实施清单（ditto-app 执行视图）

> **本清单职责：** ditto-app 侧的 task checklist + 契约速查 + 进度勾选。
> **权威设计：** ditto 仓库 [`docs/plans/2026-07-02-wave1-frontend-wiring-design.md`](../../../ditto/docs/plans/2026-07-02-wave1-frontend-wiring-design.md)（why / 架构决策 / 契约修正 / DoD / 风险）。
> **分工原则：** 架构调整改 ditto 设计文档；进度推进勾选本清单。两者职责不同，不互为副本，不会 drift。
> **分支：** `feat/wave1-backend-wiring`（从 `feat/prototype-three-zone-architecture` 拉）。
> **北极星：** `VITE_USE_MOCK=false` 时打开 `/trading`，从真实后端呈现 daily decision cockpit。

---

## 0. 契约速查卡（实施时随手查，后端 maturity = experimental）

### 后端端点（全部 `/api/v1/trade`，`strategy_id` 必填 query param）

| Method | Path | 用途 | Phase |
|---|---|---|---|
| GET | `/v1/trade/daily-decision` | **聚合 cockpit**（readiness + signal_intents + positions + deviation? + pnl?） | 3 |
| GET | `/v1/trade/intents` | 交易意图列表 | 3/4 |
| GET | `/v1/trade/fills` | 成交记录 | 4 |
| GET | `/v1/trade/positions` | 持仓快照 | 3 |
| GET | `/v1/trade/pnl` | P&L 汇总 | 3 |
| GET | `/v1/trade/signals/latest` | 最新信号日期的意图 | 3 |
| GET | `/v1/trade/signals/{signal_date}/intents` | 按日期查信号意图（**非 strategy_id**） | 3 |
| GET | `/v1/trade/deviation` | 信号 vs 成交偏差（bps） | 3 |
| GET | `/v1/trade/comparison` | backtest vs actual tracking error | 3（归因 tab） |
| PUT | `/v1/trade/intents/{intent_id}/status` | 更新意图状态 | 4 |
| POST | `/v1/trade/fills` | 录入手工成交 | 4 |

### APIResponse 形态（⚠️ 不是 `{code, message, data}`）

```
成功：{ data: T, pagination?: { total, limit, offset, has_more } }
错误：{ status_code, error, detail, error_code, request_id, timestamp }  →  ApiError(带 error_code)
```

### 关键约束

- **`strategy_id`**：所有 11 端点必填 query。前端 `DEFAULT_STRATEGY_ID` 常量（Task 3.1 第一步从后端 seed 确认 ETF 策略 id）。
- **signals 路径**：`{signal_date}/intents`，`strategy_id` 永远在 query。
- **`daily-decision`**：kebab-case；即使无信号也返回完整结构（`readiness=blocked, reasons=["no signal intents available"]`），前端不会收半截数据。
- **hook path**：写 `/v1/trade/...`，`apiClient` 拼 `API_BASE_URL=/api` → `/api/v1/trade/...`。**禁止** hook 里写 `/api/v1/...`（双 `/api`）。
- **maturity**：整个 trade 域 `experimental`，Trading 布局顶部常驻标注。

### codegen

```bash
bun run gen:api   # curl 后端 /openapi.json → openapi-typescript → src/types/generated/api.d.ts
```

commit generated snapshot 作基线；后端 experimental 变更时重跑刷新。

---

## 1. V1a live 边界速查（由后端能力决定）

| 后端能力 | 原型落点（复用已有组件） | V1a |
|---|---|---|
| `daily-decision` 聚合 | `DecisionBanner`（换 mock 源）+ Signals 队列 + Positions 区 | ✅ live |
| `signal_intents` | `SignalsList` + `SignalDetailPanel`（AI Review 三件套） | ✅ live |
| `positions` + `available_quantity` | `PositionsSummary`（DataTable + T+1 冻结 Badge） | ✅ live |
| `deviation` bps | `SignalDetailPanel` riskChecks 第 5 项（价格合理性） | ✅ live（增强） |
| `pnl` | `EquityPnlBlock` summary + Portfolio 概要 | ✅ live |
| `comparison` | **Portfolio 归因 tab**（蓝图 §12 未实现区） | ✅ 落地 |
| `fills` + `intents status` | Orders 已完成 tab + Portfolio 交易 tab + **Pipeline Strip** | ✅ Phase 4 |
| ~~session/equity/risk\*~~ | `TradingSessionStrip`/`EquityPnlBlock` sparkline/`RiskScopeStrip` 等 | ⚠️ 保留 MSW（后端无端点） |

**降级规则：** `VITE_USE_MOCK=false` 时，⚠️ 项显示结构化空态「V1a 未接 live，数据待后端补齐」——不删除组件、不伪造数据、不报错。

---

## 2. Task Checklist

> 每个 task 的 Files / Steps / Acceptance 详情见 ditto 设计文档 §6（Phase 3）/ §7（Phase 4）。

### Phase 3 — 只读 product slice

- [x] **3.1** 分支 + `.env.development` + vite proxy + `main.tsx` MSW gate + `apiClient` APIResponse 解包 + 确认 `DEFAULT_STRATEGY_ID`
- [x] **3.2** `gen:api` 脚本 + `daily-decision.ts` fetch + `mappers.ts` + 14 hook 改造（select 派生 + 降级）+ query-keys
- [x] **3.3** Overview + Signals live：`DecisionBanner` 换源、Signals 队列、`SignalDetailPanel`（+deviation 第 5 项 riskCheck）、**selected→overlay 联动修复**（复用 `orders-page.tsx` 模式）、状态矩阵硬底线
- [x] **3.4** Portfolio + Positions live：`PositionsSummary`、**Portfolio 归因 tab**（comparison）、**Signal-to-Order Pipeline Strip**（intents status）、pnl
- [x] **3.5** Risk/Session/Equity 降级空态 + 非 Trading 域空态 + MSW 双轨 handler
- [x] **3.6** V1a smoke + 证据（2026-07-05 执行：ditto server + ditto-app `VITE_USE_MOCK=false`，playwright 截图 `ditto/docs/acceptance/wave1a-trading-live.png` + 证据 `wave1a-first-real-use.md`；live 接通验证通过——daily-decision 真实响应、契约 `{data,pagination?}` 零漂移、`LIVE 已连接`、结构化 blocked 空态、0 JS error；readiness=ready 待策略定义 publish 到 catalog，独立 follow-up）

### Phase 4 — 写路径（Kill Switch manual/paper）

- [x] **4.1** record fill：`SignalDetailPanel` 订单确认 Sheet + `POST /fills` + invalidation
- [x] **4.2** intent status：`PUT /intents/{id}/status` + 高风险确认 overlay（spec §16.2）+ 状态机由后端强制
- [x] **4.3** Orders/Portfolio ledger + Pipeline Strip 补完四段

**依赖：** 3.1 → 3.2 → (3.3 ‖ 3.4 ‖ 3.5) → 3.6 → 4.1 → 4.2 → 4.3。每 task 一 PR，不混提。

---

## 3. 质量门禁（每 PR 必过）

```bash
bun run check   # biome + tsc + vitest，全绿
```

- 无 `any` / `@ts-ignore` / inline style 回归
- adapter 单测必须覆盖：`APIResponse.data` 解包、`/api` base path 拼接（断言 `/v1/trade/daily-decision` 非 `/api/v1/...`）、ready/review/blocked/failed 四态、`error_code` 映射
- 组件只 import view model（`types/trading.ts`），**禁止**组件直接 import generated DTO

---

## 4. Kill Switch（硬性）

- Phase 4 写路径（record fill / update intent status）走既有 application command handler + approval 路径，**不加自动交易**
- 前端写按钮在对应 task 完成前保持 disabled；paper/manual 是唯一执行面
- 状态机校验（pending/filled/partially_filled/cancelled/expired）由后端 command handler 强制

---

## 5. 跨仓库协作约定

```bash
# git 操作用 -C 显式指定仓库（不用 cd，避免触发权限提示）
git -C /home/chevy/projects/ditto-app status
git -C /home/chevy/projects/ditto-app add -A && git -C /home/chevy/projects/ditto-app commit -m "..."

# 前端检查（ditto-app）
git -C /home/chevy/projects/ditto-app exec bun run check
# 或在 /home/chevy/projects/ditto-app 目录直接 bun run check

# 后端联调检查（ditto，前端不改后端代码，仅 Phase 4 联调后跑）
pixi run -e dev check
```

- **契约同步：** 后端 trade API 变更 → ditto 提交 → ditto-app 跑 `bun run gen:api` 刷新 snapshot → 提交 snapshot
- **PR 互引：** ditto-app PR 描述注明对应后端 ditto PR（若有契约变更）
- **TodoWrite 跨仓库：** task 标注仓库（`[ditto-app] Task 3.1 ...` / `[ditto] 文档同步`）

---

## 6. 进度日志

<!-- 实施时按 task 追加：日期 / commit / 关键决策 / 偏差 -->

- 2026-07-02 / working tree / 完成 Phase 3-4 前端接线：live trade adapter、daily-decision 派生、manual/paper fill 与 intent status 写路径、fill ledger、Pipeline Strip、降级空态与 MSW 双轨。`bun run check` 通过（156 files / 1826 tests）。V1a live smoke 证据文件已新增到 ditto 仓库；当前环境后端 API server 不可用，文件内记录 exact blocker，未伪装真实联调成功。
- 2026-07-03 / working tree / 处理三方核查反馈：Overview live 信号队列改为 `useSignals`/daily-decision 派生，Overview 订单区改为 manual/paper fill ledger，5 个 live 派生 hook 消除条件调用 hook 模式，补 comparison adapter/hook 与 Portfolio `comparisonRunId` 数据路径。3.6 保持 partial/blocked，等待真实后端 first-use smoke。
- 2026-07-05 / ditto commit `1ff98089` / Task 3.6 live smoke 执行并验证：起 ditto server（**关键 gap**：`wave1_env.sh` 缺 `TUSHARE_TOKEN` export，server 启动 `data_source_validation` 失败，需从 keyring 取 token export）+ ditto-app `VITE_USE_MOCK=false`，playwright 截图 `/trading`。验证通过：daily-decision 真实响应（`{data,pagination?}` 契约零漂移）、`LIVE 已连接 12ms`、结构化 blocked 空态（Signals/Positions/Orders live 空态、Risk/Session/Equity 降级）、0 JS error。`readiness=ready` 仍 blocked，因 `strategy publish-signals` 缺策略定义 publish 前置（CLI 无 publish-strategy-definition 命令，入口在 `/strategies` API，超 wave1）。Task 3.6 标记完成（first real-use 路径证据达成），readiness=ready 作为独立 follow-up。
