# #196 Batch 2 股票数据集摄取与晋级材料(2026-09-30)

> 规则见 [R2 Evidence Index](../../README.md):本目录只归档命令直接生成的机器输出与 reviewer 事实;runtime 中的 append-only 认证/晋级/license 记录是唯一权威,此处不复制其内容。

## 最终状态(评审收敛后,fail-closed)

**数据、license 与摄取证据保留;认证与晋级均已撤销,三数据集 maturity 回到 experimental,运行门恢复拦截。** 二轮机器评审证实晋级证据不充分(stock_status 消费未走 catalog 读模型、字段级 `replay-snapshots` 在 certified fields 建立前 fail closed、恢复演练仅证明 skip 幂等而非中断恢复、正式策略运行因 index_daily 缺数据未执行),按"不跳过门禁取得绿灯"原则撤销,补齐后重新走认证与晋级。

| 数据集 | 已摄取覆盖 | runtime 终态 |
|---|---|---|
| `stock_basic` | 2026-09-30 快照(5922 只 instrument 注册) | experimental;certification revoked(evidence_invalidated) |
| `stock_daily` | 2025-01-01→2026-09-29(423 交易日,2.3M 行,L1/L2 DQ passed) | experimental;certification revoked |
| `stock_status` | 2025-01-01→2026-09-29(423 交易日,2.3M 行,L1/L2 DQ passed) | experimental;certification revoked |

辅助数据:`adj_factor` 2026-06-01→2026-09-29(4 月度块);`index_daily` 经代理取回 0 行/日期(待诊断)。

撤销的 append-only runtime 身份(权威记录在 runtime SQLite,此处仅引用):

| 数据集 | 认证撤销事件 | maturity 晋级撤销事件(event_id, reason) |
|---|---|---|
| `stock_basic` | certification_events revoked @ 2026-09-30T11:59:09Z, actor chevy | promotion_events #4, evidence_invalidated @ 2026-09-30T11:59:53Z |
| `stock_daily` | certification_events revoked @ 2026-09-30T11:59:13Z, actor chevy | promotion_events #5, evidence_invalidated @ 2026-09-30T11:59:58Z |
| `stock_status` | certification_events revoked @ 2026-09-30T11:59:17Z, actor chevy | promotion_events #6, evidence_invalidated @ 2026-09-30T12:00:03Z |

## 重新晋级清单(下一批,全部满足后才重走 promotion)

1. `index_daily` 修复(适配器/代理诊断)→ 正式策略运行双例:种子财务策略被运行门拦(负例)+ 无财务 sector_rotation 策略无 bypass 通过(正例)。
2. 认证补 certified fields → 字段级 `replay-snapshots` 在声明区间内通过。
3. 真正的中断恢复演练(中断首跑 + 前后 durable identity/写尝试计数),替代 skip 幂等。
4. 三个数据集的 catalog 读模型消费检查(stock_daily 已有脚本模式,stock_basic/stock_status 补)。
5. 全历史覆盖(stock_basic 2015 起/stock_status 2016 起)或在读路径上落实区间外 fail-closed 后,再评估有限范围晋级的边界声明。

## 证据文件(机器生成,含 repo_head 与生成命令;时间戳早于所在提交)

- `recovery-idempotency-stock_{daily,basic,status}.json` — skip 幂等检查(声明为 skip 幂等,非中断恢复)。
- `consumer-read-stock-daily.json` — 真实 DI 容器 ServiceBackedDataProvider 读模型功能检查(PIT 列 knowledge_date/source_snapshot_id);**不**声称行使 maturity 门(get_bars 无 opt-in 输入)。
- `consumer-read-stock-basic.json` — instrument registry 读路径。
- `consumer-read-stock-status.json` — canonical parquet 直接读(读模型覆盖待补)。
- `formal-gate-verification.json` — 撤销后真实 promotion store 上的门核验:股票道恢复 experimental 拦截、财务仍受限、研究 opt-in 语义保留。

## 运维责任

runtime owner / freshness SLA / failover policy 见 `docs/operations/stock-data-runtime-ops.md`(晋级准则二证据模板)。

## 已知缺口(如实记录)

- `index_daily` 经代理取回 0 行且单日期约 3 分钟;2004–2008 散点快照来自一次无日期参数 repair 的部分回填(目标外部分覆盖)。
- 普通行情读路径(`MarketQueryFacade`/`ServiceBackedDataProvider`)不执行 per-read 新鲜度/覆盖检查;新鲜度仅作用于 readiness/status overlay 层。
