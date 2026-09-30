# #196 Batch 2 股票数据集晋级证据(2026-09-30)

> 规则见 [R2 Evidence Index](../../README.md):本目录只归档命令直接生成的机器输出与 reviewer 事实;runtime 中的 append-only 认证/晋级/license 记录是唯一权威,此处不复制其内容。

## 晋级范围(有限范围,显式声明)

| 数据集 | 声明覆盖 | 认证报告(runtime identity) | 结果 |
|---|---|---|---|
| `stock_basic` | 2026-09-30 快照(5922 只) | `certification:bc79d1795183242606b0733dd1d886bbd8b331db9eb6140f0ee90c43450dad79` | promoted → initial-focus |
| `stock_daily` | 2025-01-01→2026-09-29(423 交易日,230 万行) | `certification:941831ac922cf090ccc94b3e9a3fe1c9b263f5025da0dfc0e60e051de412c6e9` | promoted → initial-focus |
| `stock_status` | 2025-01-01→2026-09-29(423 交易日,231 万行) | `certification:deda3c54…`(content_hash 见 runtime) | promoted → initial-focus |

财务数据集(balance_sheet/income_statement 等)按票面保持 experimental:无历史版本证据不晋级。

## 证据文件(均由命令/脚本直接生成)

- `recovery-idempotency-stock_{daily,basic,status}.json` — 已完备区间重跑引导,planner 零处理、零 durable 写入。
- `consumer-read-stock_{daily,basic,status}.json` — 真实读路径消费检查(canonical parquet / instrument registry)。
- `formal-gate-verification.json` — 真实 promotion store 上的无 bypass 运行门核验:股票道放行、财务受限、研究 opt-in 语义保留。

## 运维责任

runtime owner / freshness SLA / failover policy 见 `docs/operations/stock-data-runtime-ops.md`(晋级准则二证据)。

## 已知缺口(如实记录)

- `index_daily` 经代理取回 0 行且单日期耗时约 3 分钟(适配器/代理待诊断),正式股票策略运行(需基准)验证顺延至下一批;`adj_factor` 已补 2026-06→2026-09 有界窗口。
- 一次未带日期参数的 `repair` 曾按目录计划从 2004 年开始回填,中途停止,留下 2004–2008 部分年份的散点快照(目标外部分覆盖,不影响本批次声明区间的覆盖完整性;后续全历史认证时按 planner 补齐或显式 exception)。
- 字段级 replay(`replay-snapshots`)在认证字段证据建立前 fail closed,属预期顺序:certified fields 建立后可回放。
