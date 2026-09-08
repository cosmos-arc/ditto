# Wave 1a First Real-Use Evidence

> Date: 2026-07-02
> Scope: ditto-app Trading domain frontend wiring for Wave 1a/1b.
> Frontend branch: `feat/wave1-backend-wiring`
>
> Historical evidence: commands and `VITE_*` flags below describe the original
> two-repository run. Current reruns use root `task dev` plus
> `ditto-runtime-config.json`; the Web tree now lives at `apps/web`.

## Summary

ditto-app Trading 域接线已完成：`VITE_USE_MOCK=false` 时 `/trading`、`/trading/signals`、`/trading/portfolio`、`/trading/orders` 走 `/api/v1/trade/*` live adapter；Risk/Session/Equity 与非 Trading 域显示结构化 prototype-only 空态。

真实后端 first-use smoke 于 2026-07-05 执行并验证 live 接通（截图 `docs/acceptance/wave1a-trading-live.png`）：`VITE_USE_MOCK=false` 时 `/trading` 经 Vite proxy 真实连后端，`daily-decision` 返回 `{data:{readiness:{status:"blocked",reasons:["no signal intents available"]},signal_intents:[],...},pagination:null}`，前端正确渲染结构化 blocked 空态、`LIVE 已连接 12ms`、page errors none。`readiness=ready` 仍需策略定义 publish 到 catalog（`publish-signals` 前置，超 wave1 范围），但 **live 接通 + 契约一致 + 空态渲染已闭环验证**。

## Frontend Evidence

该次运行在旧前端仓库执行；当前等价叶子目录为 `apps/web`：

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

## Live Smoke Evidence（2026-07-05 执行）

启动命令（关键 gap：`wave1_env.sh` 没导出 `TUSHARE_TOKEN`，server 启动会因 `data_source_validation` 失败 → 必须从 keyring 取 token export）：

```
source scripts/acceptance/wave1_env.sh
export TUSHARE_TOKEN="$(uv run --no-sync python -c "import keyring; print(keyring.get_password('tushare','token'))")"
task server --                    # granian :8000
# ditto-app: bun run dev           # Vite :5173, VITE_USE_MOCK=false, proxy /api → :8000
```

截图 `docs/acceptance/wave1a-trading-live.png` 验证点（全部通过）：

| 验证点 | 结果 |
|---|---|
| live 接通（非 MSW） | ✅ `LIVE 已连接 12ms` |
| daily-decision 真实响应渲染 | ✅ `DAILY DECISION ▼ 阻塞` + 中文 `no signal intents available` |
| Signals live 空态（非 mock 假信号） | ✅ `信号队列 / 暂无待复核信号` |
| Positions live 空态 | ✅ `持仓汇总 0` |
| Orders manual/paper ledger 空态 | ✅ `成交 0 / 尚未录入手工成交` |
| Risk/Session/Equity 降级空态 | ✅ `V1a 未接 live / 数据待后端补齐` |
| JS 错误 | ✅ page errors none |

契约一致性实测：前端 adapter 假设的 `APIResponse{data, pagination?}` 与后端实际响应 `{"data":..., "pagination":null}` 完全吻合，零漂移。

## Remaining Blocker（readiness=ready 需要）

`strategy publish-signals` 要求策略定义已 publish 到 catalog（实测 `AppBuilderError: 未找到策略定义: strategy_id=seed_etf_industry_rotation`）。CLI 无 publish-strategy-definition 命令；publish 入口在 `/strategies` API + application `publish_spec`（[commands/strategy.py:130](../packages/application/src/ditto_application/commands/strategy.py#L130)）。这属于策略上线流程，超 wave1（数据 + 前端）范围。

**两个 follow-up（独立于 wave1）：**

1. `wave1_env.sh` 应增加 `export TUSHARE_TOKEN`（从 keyring 取），让 server 启动开箱即用（CLI 用 keyring 不受影响）。
2. 跑策略上线流程（publish seed 策略定义到 catalog）后，`publish-signals` 即可产 intents，daily-decision 变 `ready`，可补「真实信号」截图。

## Required Follow-Up

后端可用后重新执行：

1. `source scripts/acceptance/wave1_env.sh`
2. 启动 Ditto API server。
3. 跑 EOD 或 publish-signals，产出 `seed_etf_industry_rotation` intents。
4. 以根 `task dev` 启动 `runtime=live`，打开 `/trading`、`/trading/signals`、`/trading/portfolio`、`/trading/orders`。
5. 记录 readiness、latest signal date、signal count、positions、deviation/pnl、Pipeline Strip、Portfolio 归因/交易流水。
6. 将截图或真实 response 摘要追加到本文件。
