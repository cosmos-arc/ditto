# ETF Paper 输入与验收（#408）

## 输入边界

| 输入 | 来源与时间 | 消费者 |
|---|---|---|
| ETF 身份、上市状态、跟踪指数、境内/QDII | Tushare 结构化 etf_basic；本次留存观察时间，不回填成历史已知 | 参考观察、候选、Paper eligibility |
| 原始收盘价格 | fund_daily → etf_daily；交易日和独立完成快照；不使用 NAV/复权 | handoff 持仓估值、signal sizing |
| 交易限制、交易币种 | 需要确切参考观察及其独立留存身份；上市状态不等同于无交易限制 | handoff 和执行拒绝边界 |
| lot、tick、settlement、price limit 规则 | 必须有适用于指定 ETF 的来源/配置、有效日和观察时间 | 执行 |
| 佣金率、最低佣金、税费 | 必须有已确认账户费用配置及有效时间；不能取测试默认值 | 执行 |
| 每日涨跌停价格 | Tushare etf_limit；独立于股票 stk_limit，单次上限 3000 | 执行日价格限制 |
| NAV | fund_nav；未知 ann_date 保留 null，#491/#492 | 展示/对账，不授予 Paper 决策可用性 |
| 交易日历 | 完成且留存的 calendar snapshots，各自 cutoff | handoff 次交易日、结算日 |

已核查官方接口：[etf_basic](https://tushare.pro/document/2?doc_id=385)、
[etf_limit](https://tushare.pro/document/2?doc_id=491)、
[2026-09-07 ETF 涨跌停迁移记录](https://tushare.pro/document/1?doc_id=9)。
etf_basic 的 index_code 不证明指数收益版本；etf_type 只表示投资通道，不能由名称推断币种或结算规则。

## 验收状态

进行中。代码、隔离测试和真实用户旅程分别记录；未完成真实 handoff/执行或估值前，
#408、#395、#390 保持开放。仓库中尚未找到带账户依据的 ETF 佣金/最低佣金配置，
已请求维护者提供；不得从系统测试夹具补齐。
