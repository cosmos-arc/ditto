# Wave 1a First Real-Use Evidence

> Date: 2026-07-02
> Scope: ditto-app Trading domain frontend wiring for Wave 1a/1b.
> Frontend branch: `feat/wave1-backend-wiring`

## Summary

ditto-app Trading 域接线已完成：`VITE_USE_MOCK=false` 时 `/trading`、`/trading/signals`、`/trading/portfolio`、`/trading/orders` 走 `/api/v1/trade/*` live adapter；Risk/Session/Equity 与非 Trading 域显示结构化 prototype-only 空态。

真实后端 first-use smoke 在当前 workspace **未完成**：本地 Ditto 后端未保持可用，`http://localhost:8000/openapi.json` 无可用响应，因此没有截图或真实 runtime response 可记录。本文件不伪装联调成功；当前证据为前端契约、adapter、组件和写路径的可重复测试结果。

## Frontend Evidence

在 `/home/chevy/projects/ditto-app` 执行：

```
bun run check
```

结果：

| Gate | Result |
|---|---|
| `biome check .` | passed |
| `tsc -b` | passed |
| `vitest run` | 156 files passed, 1826 tests passed |

覆盖范围包括：

- APIResponse `{ data, pagination? }` 解包与后端 error metadata 映射。
- `/api` base path 拼接，hook path 使用 `/v1/trade/...`。
- `daily-decision` adapter 与 readiness ready/review/blocked/failed mapper。
- Overview DecisionBanner live readiness / signal count / positions / deviation / pnl。
- Signals selected-to-Drawer 联动、SignalDetailPanel deviation risk check。
- Manual/paper `POST /v1/trade/fills` record fill 表单校验与成功反馈。
- Manual/paper `PUT /v1/trade/intents/{intent_id}/status` 高风险确认链路。
- Orders manual execution fill ledger。
- Portfolio positions/pnl、归因空态、fill ledger 与 Signal-to-Order Pipeline Strip。
- Risk/Session/Equity 降级空态。
- Home/Markets/Research/Platform `VITE_USE_MOCK=false` prototype-only 空态。
- MSW 双轨 handlers：旧 `/api/trading/*` 与新 `/api/v1/trade/*` 共存。

## Live Smoke Blocker

阻塞项：

1. 当前环境未运行可访问的 Ditto API server。
2. 无法从 `http://localhost:8000/openapi.json` 取得 live OpenAPI 或 runtime response。
3. 因此未能执行 EOD/publish-signals 后的真实浏览器截图采集。

## Required Follow-Up

后端可用后重新执行：

1. `source scripts/acceptance/wave1_env.sh`
2. 启动 Ditto API server。
3. 跑 EOD 或 publish-signals，产出 `seed_etf_industry_rotation` intents。
4. 在 ditto-app 以 `VITE_USE_MOCK=false` 打开 `/trading`、`/trading/signals`、`/trading/portfolio`、`/trading/orders`。
5. 记录 readiness、latest signal date、signal count、positions、deviation/pnl、Pipeline Strip、Portfolio 归因/交易流水。
6. 将截图或真实 response 摘要追加到本文件。
