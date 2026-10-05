# ETF Paper 输入与验收（#408）

## 输入边界

| 输入 | 来源与时间 | 消费者 |
|---|---|---|
| ETF 身份、上市状态、跟踪指数、境内/QDII | Tushare 结构化 etf_basic；本次留存观察时间，不回填成历史已知 | 参考观察、候选、Paper eligibility |
| 原始收盘价格 | fund_daily → etf_daily；交易日和独立完成快照；不使用 NAV/复权 | handoff 持仓估值、signal sizing |
| 交易限制、交易币种 | 需要确切参考观察及其独立留存身份；上市状态不等同于无交易限制 | handoff 和执行拒绝边界 |
| lot、tick、settlement、price limit 规则 | 必须有适用于指定 ETF 的来源/配置、有效日和观察时间 | 执行 |
| 佣金率、最低佣金、税费 | 必须有已确认账户费用配置及有效时间；不能取测试默认值 | 执行 |
| 每日涨跌停价格 | 已核验 Tushare etf_limit 适用 ETF、上限 3000；尚未生产接线 | 后续执行日价格限制 |
| NAV | fund_nav；未知 ann_date 保留 null，#491/#492 | 展示/对账，不授予 Paper 决策可用性 |
| 交易日历 | 完成且留存的 calendar snapshots，各自 cutoff | handoff 次交易日、结算日 |

已核查官方接口：[etf_basic](https://tushare.pro/document/2?doc_id=385)、
[etf_limit](https://tushare.pro/document/2?doc_id=491)、
[2026-09-07 ETF 涨跌停迁移记录](https://tushare.pro/document/1?doc_id=9)。
etf_basic 的 index_code 不证明指数收益版本；etf_type 只表示投资通道，不能由名称推断币种或结算规则。

## 验收状态

**BLOCKED，#408 / #395 / #390 保持开放。**

CODE/TEST：结构化 ETF 身份、原始日线价格投影及独立快照组合已实现；缺限制/币种准确拒绝。
Web transport 支持输入身份集合，当前页面尚未提供选择这些补充快照的交互。
规则/费用只有既有参考观察读侧，尚无已确认配置的生产导入；etf_limit 只核验接口和分页上限，未接入生产摄取/执行。
隔离测试中的规则、费用和授权均为显式测试数据，不是生产来源可用证明。

LIVE 输入实测绑定 `bdff6c97d13bf0fbfe432efc61da817c01ffa1fb`，
2026-10-05 11:55:57–11:56:10 UTC，隔离根 `/private/tmp/ditto-etf-paper-20261005-final`。
使用现有配置的 Tushare 来源（已有代理入口），无新增订阅。
命令：

```bash
uv run --no-sync python docs/evidence/etf-paper-20261005/probe.py \
  --root /tmp/ditto-etf-paper-20261005-final \
  --config-root /Users/chevy/Desktop/code/ditto
```

该根已存在；重放必须换新根，脚本拒绝覆盖。快照/校验和、候选字段和结果见
[live-inputs.json](live-inputs.json)，原始完整报告在隔离根 `report.json`。
calendar 396、etf_basic 1779、etf_daily 1650 行成功留存；重复日线摄取跳过。
510300.SH 原始收盘价 4.432；显式模拟期初现金 10000 与持仓 100 份，
估值 10443.20，`valuation_complete=true`。这只证明原始价格进入持仓估值。

用户旅程未完成：选中 ETF 的 handoff facts 缺 `trading_restriction`、`trading_currency`；
lot/tick/settlement/price limit/佣金/最低佣金/税费也缺已确认依据。
没有创建授权、handoff 会话或执行成交。不能把模拟期初持仓估值等同于 handoff→execution/valuation。
需维护者提供适用 ETF/账户的既有规则和费用配置位置、来源及有效时间，再补最小生产接线和完整真实旅程。
