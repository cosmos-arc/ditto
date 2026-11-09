# PAP-08 Paper 五日预验收

## 结果

PASS。确定性预验收在 fresh 临时 SQLite 中按 2026-08-24 至 2026-08-28 五个工作日运行，每日关闭并重新打开 Paper session store 与账户 journal。股票与 ETF 均被覆盖。

每个交易日第一次提交均为 `created`，相同 idempotency key 与相同 payload 的第二次提交均为 `replayed`；持久层每天只有 1 个 execution、1 个 fill 和 1 个对应账本事件。五个 EOD reconciliation 均平衡，重启后仍可读取同一 reconciliation。

| 日期 | 资产 | 标的 | execution | fill | ledger fill | EOD |
|---|---|---:|---:|---:|---:|---|
| 2026-08-24 | stock | 600519 | 1 | 1 | 1 | balanced |
| 2026-08-25 | ETF | 510300 | 1 | 1 | 1 | balanced |
| 2026-08-26 | stock | 1 | 1 | 1 | 1 | balanced |
| 2026-08-27 | ETF | 159915 | 1 | 1 | 1 | balanced |
| 2026-08-28 | stock | 601318 | 1 | 1 | 1 | balanced |

## 边界声明

该证据是受控、加速的 PAP-08 预验收：使用明确的 certified snapshot identity，在一次测试运行中重放五个日期。它不是五个自然流逝的真实交易日，不使用 live provider，`real_trading_day_count` 明确为 0，且不推进或满足 PAP-09 的连续 20 个真实交易日 soak。

## 校验身份

- 最终 ledger hash：`account-ledger:sha256:d8c59e0527ffd91b91d78710c509be7d8ca3db764ecac8571939eb3d2a199ff1`
- evidence hash：`sha256:24b5fd203c4126dce6158af87184db6f2ba2422654e45c8b08d00faf2954f4f4`
- 机器证据：[`20260831-paper-five-day-preacceptance.json`](20260831-paper-five-day-preacceptance.json)
- 可重放命令：`uv run --no-sync python scripts/evidence/paper_five_day_preacceptance.py`

演练数据库仅位于自动清理的临时目录，不触碰生产或真实账户数据。

2026-11-09 随 #757 重新生成当前确定性样例。费用表新增 `transfer_fee_per_share=0.0` 进入请求身份，五日请求哈希及对账校验和相应更新；成交、账本事件、最终账本和全部行为断言不变。本次重放不刷新历史 Q4/PAP-09 的运行或发布资格。

同日随 #754 再次重放：交易规则新增两个单笔申报数量上限字段，默认空值也进入完整请求身份。仅请求哈希、对账校验和、证据哈希与生成时间变化，成交、金额、账本及五日行为断言不变。

同日随 #755 重放：新增最小申报量字段进入请求身份，仍仅变动五日请求/对账及派生证据身份，成交、金额和最终账本不变。当前样例不代表真实连续运行。
