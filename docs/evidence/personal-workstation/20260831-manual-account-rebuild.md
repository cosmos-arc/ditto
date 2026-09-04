# MAN-08 Manual 账户完整重建演练

## 结果

PASS。演练在 fresh 临时 SQLite 中创建 MANUAL 账户并写入 7 个不可变事件，关闭数据库后重新打开，再以显式估值价格完整重放两次。持久化 round-trip、重复重放、ledger hash 和人工对账均一致。

## 场景

事件依次为：期初现金、期初持仓、原买入、买入更正、原存款、存款冲正、部分卖出。该序列同时覆盖期初、交易、费用/税费、settlement、correction 和 reversal。

显式估值输入为 `instrument_id=42, price=14.0000, as_of=2026-08-31`。人工独立计算期望值：

| 项目 | 期望 | 重放结果 |
|---|---:|---:|
| 可用/已结算现金 | 99,559.25 | 99,559.25 |
| 数量/可用数量 | 150 | 150 |
| 平均成本 | 10.9250 | 10.9250 |
| 市值 | 2,100.00 | 2,100.00 |
| 已实现 PnL | 198.00 | 198.00 |
| 未实现 PnL | 461.25 | 461.25 |
| 累计费用 | 10.75 | 10.75 |
| 总资产 | 101,659.25 | 101,659.25 |

## 校验身份

- ledger hash：`account-ledger:sha256:e6426e90ff2fe63037d47786692e2e97f6413fc26e171bd04bb84bd73ea854c4`
- evidence hash：`sha256:5c777bdaac99b2b9fbe611c820a2dfd8170d342964ed98e515c10d40f6faf4a5`
- 机器证据：[`20260831-manual-account-rebuild.json`](20260831-manual-account-rebuild.json)
- 可重放命令：`pixi run -e dev python scripts/evidence/manual_account_rebuild.py`

演练数据库仅位于自动清理的临时目录，不触碰生产或真实账户数据。
