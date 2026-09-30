# 股票数据集运行职责与新鲜度策略（2026-09 晋级材料）

> 适用数据集:`stock_basic`、`stock_daily`、`stock_status`(Tushare 主源,经 `https://t.xiaodefa.top/` 代理;fuyao 为冗余源)。
> 本文档是 [#196](https://github.com/cosmos-arc/ditto/issues/196) 晋级准则二「document runtime owner, freshness SLA, and source failover policy」的评审材料,与 runtime 中 append-only 的 license/promotion 记录配套,不复制其事实。

## 运行负责人（runtime owner）

- 单操作者工作站(chevy),本地运行时,无部署环境。
- 数据面责任:按交易日终态更新、失败重试与 repair(`ditto data-products repair`)、覆盖缺口处置;不修改已冻结认证报告,coverage 回归先 revoke 再修复。
- 升级责任:provider 接口/权限/quota 变化时更新本文件与 license 记录(append 新版本,不改旧记录)。

## 新鲜度 SLA

| 数据集 | 频率 | SLA | 说明 |
|---|---|---|---|
| `stock_basic` | 按需快照 | 交易日 T 日终 | 全市场列表快照,身份/上市状态变更随快照重放 |
| `stock_daily` | 交易日 | T+0 晚间(约 17:30–20:00 窗口) | 日线 OHLCV+量额,单日全市场一次调用 |
| `stock_status` | 交易日 | T+0 晚间(随 daily 同窗) | 停复牌/交易状态,可投资集合判定输入 |

- 触发:工作日终人工执行 bootstrap/repair(个人工作站无常驻调度);次日开盘前补齐为达标线。
- 超期处置:新鲜度不足时下游 fail closed(maturity/readiness 门),不做静默旧值顶替。

## 主备与故障切换（source failover policy）

1. 主源 Tushare(代理端点),备源 fuyao(同花顺开源数据,已接 adapter 与本地 dump)。
2. 主源失败(配额/网络/接口变更)时:保持 blocked/stale 展示与最后认证快照身份;经人工确认备源口径(schema、复权、时间语义、许可)一致后,以 `--source fuyao` 显式补数,快照记录真实 provider 身份,不静默沿用主源身份。
3. 主备共用上游时不得视为独立校验;切换与回切都以新快照/新证据落账,旧结果不回写。
4. 连续失败或覆盖回归 → revoke 晋级,按 runbook 修复后重新认证。

## 版本

- 2026-09-30:随 #196 Batch 2 首次评审建立(chevy)。
