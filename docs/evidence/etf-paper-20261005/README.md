# ETF Paper 输入与验收（#408）

## 输入边界

| 输入 | 来源与时间 | 消费者 |
|---|---|---|
| ETF 身份、上市状态、跟踪指数、境内/QDII | Tushare 结构化 etf_basic；本次留存观察时间，不回填成历史已知 | 参考观察、候选、Paper eligibility |
| 原始收盘价格 | fund_daily → etf_daily；交易日和独立完成快照；不使用 NAV/复权 | handoff 持仓估值、signal sizing |
| 交易限制、交易币种、lot/tick/结算/涨跌幅、佣金/最低佣金/税费 | `config/default/etf_reference.json` 维护者确认声明（source=config，#408）；每条事实独立 basis+生效日；经真实摄取链落 `etf_reference` 快照与观察行 | handoff 可投资判定、执行规则与费用 |
| 每日涨跌停价格 | 已核验 Tushare etf_limit 适用 ETF、上限 3000；尚未生产接线；执行侧按 pre_close×price_limit_pct 推导 | 后续执行日价格限制 |
| NAV | fund_nav；未知 ann_date 保留 null，#491/#492 | 展示/对账，不授予 Paper 决策可用性 |
| 交易日历 | 完成且留存的 calendar snapshots，各自 cutoff | handoff 次交易日、结算日 |

已核查官方接口：[etf_basic](https://tushare.pro/document/2?doc_id=385)、
[etf_limit](https://tushare.pro/document/2?doc_id=491)、
[2026-09-07 ETF 涨跌停迁移记录](https://tushare.pro/document/1?doc_id=9)。
etf_basic 的 index_code 不证明指数收益版本；etf_type 只表示投资通道，不能由名称推断币种或结算规则。
规则依据：510300.SH 招募说明书条款（买入申报 100 份整数倍、最小变动 0.001 元、
上市首日起 ±10% 涨跌幅）与上交所交易规则；印花税依《印花税法》对基金转让免征；
过户费按中国结算 2022-04-29 起 0.001% 双边标准口径（维护者 2026-10-05 确认）；
佣金 万1/最低 5 元为维护者确认的券商账户费率（2026-10-05）。

## 验收状态

**授权链与估值已 LIVE 完成；执行腿受 PIT 合同限制需活体节奏，排程于 2026-10-08/10-09 晚间。**

CODE/TEST（41ed18ab）：

- `etf_reference` 成为 source=config 的真实数据集：声明文件 → 真实摄取链
  （快照+payload 留存+完成证据+幂等）→ `etf_reference_observation` 观察行；
  config 身份映射登记（fuyao 同语义），未解析身份 fail closed。
- 读侧合同不变：handoff/execution 以 `etf_reference` 补充输入取得
  trading_restriction/trading_currency/lot/tick/结算/涨跌幅/佣金/最低佣金/
  印花税/过户费；未声明标的保持缺失并精确拒绝（`trading_restriction:missing` 等）。
- 集成测试 3 项（真实摄取链→investable、快照身份错配拒绝、未注册身份拒绝）
  + 声明读取器单元 14 项通过；lint/format/type 全绿。

LIVE 用户旅程（[journey-live.json](journey-live.json)，全量 report.json 在隔离根）：

绑定 `41ed18ab3ef8db9ed19b992f9ae918769ffe60ab`，2026-10-05 15:04:21–15:04:43 UTC，
隔离根 `/private/tmp/ditto-etf-paper-journey-20261005-final`。命令：

```bash
uv run --no-sync python docs/evidence/etf-paper-20261005/paper_journey.py \
  --root /tmp/ditto-etf-paper-journey-20261005-final \
  --config-root /Users/chevy/Desktop/code/ditto
```

（重放须换新根；脚本拒绝覆盖已有根。）

1. 真实 Tushare 摄取：calendar 396、etf_basic 1779、etf_daily 1650 行 success；
2. config 声明摄取：10 条事实 success，重复摄取 skipped（幂等）；
3. PAPER 账户经真实命令路径建立（opening cash 10000）；
4. handoff facts：510300.SH（instrument 2000801）investable，其余 1778 只
   ETF 以 `trading_restriction:missing`/`trading_currency:missing` 精确拒绝；
5. 真实授权链：保存版本（50% 510300 + 50% 现金，跟踪 000300.SH）→ submit →
   approve → Paper 授权 → handoff 会话创建并启动，intended_trade_date=2026-10-08
   （真实日历：国庆假期后首个交易日）；
6. 真实估值：target 5000 元 @4.432（9/30 实际收盘价）vs 实际 10000 现金，
   drift -5000bps，估值完整。

**执行腿（PIT 合同边界）**：`etf_paper_execution._after_close` 要求版本
knowledge cutoff 落在信号日当天收盘后——信号日当晚报版、次交易日收盘后执行
是本系统设计的活体节奏。本次旅程的版本在信号日（9/30）之后保存，其生命周期
按设计止于 handoff+估值。活体执行验证安排：2026-10-08 晚（摄取当日数据→
保存→授权→handoff，trade 10-09）+ 2026-10-09 晚执行，复用同一脚本。

此前 LIVE 输入实测（bdff6c97，2026-10-05 11:55 UTC）与
[live-inputs.json](live-inputs.json) 保留为输入侧证据（当时隔离根已被上方旅程取代）：
calendar 396、etf_basic 1779、etf_daily 1650 行成功留存；重复日线摄取跳过；
510300.SH 原始收盘价 4.432 进入持仓估值（10443.20）。该轮仅证明输入侧，
限制/币种/规则费用缺口由本轮 config 声明数据集补齐。
