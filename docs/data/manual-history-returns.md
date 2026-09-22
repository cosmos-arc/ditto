# 账户历史估值与资金流调整收益（Manual / Paper）

规格来源：[#249](https://github.com/cosmos-arc/ditto/issues/249)（三组合历史估值与资金流调整收益）、实施票 [#260](https://github.com/cosmos-arc/ditto/issues/260)（Manual）、[#261](https://github.com/cosmos-arc/ditto/issues/261)（Paper）。本文记录数值与查询合同；Model 腿与三组合共同区间比较由 #262/#263 后续接入，数值合同复用本文。

## 记录合同

- **外部资金流**只有 `deposit` / `withdrawal`（及开户时的 `opening_cash`）。买入卖出、分红、利息、费用与税费都是账户内部事件，不进入资金流调整。
- 自 #260 起，`deposit` / `withdrawal` 可声明 `flow_position`（`start_of_day` / `end_of_day` / `intraday`）：
  - `start_of_day` 流入当日分母：当日收益 = V_收 / (V_前收 + C) − 1；
  - `end_of_day` 流从当日末值中剔除：当日收益 = (V_收 − C) / V_前收 − 1；
  - `intraday` 盘中流缺少流前/流后估值，该日收益留空（`cash_flow_valuation_missing`）；
  - 未声明时点的**旧记录保持原样**，该日收益留空（`timing_unknown`），不人为假定为收盘流。
- `flow_position` 只在 `deposit` / `withdrawal` 上合法；未设置时不出现在事件哈希与持久化 payload 中，#260 之前的旧事件哈希字节不变、可继续重放。
- Paper 账户事件只能以 `source=paper_engine` 写入同一账本（`assert_accepts`）：模拟成交（`buy`/`sell`，含费用与税费）、公司行动（如 `dividend`）与入金（`deposit`）都在此来源下进入历史序列；Manual 账本永不被 Paper 查询读取。

## 查询合同（只读、精确身份、无 latest 回退）

两个入口共享同一重放引擎（`packages/application/.../queries/portfolio_history.py`），只差账户种类门、身份锚与错误码前缀：

- Manual：`GET /api/v1/manual/accounts/{account_id}/history`（`manual_get_history`，`GetManualHistoryQuery`，错误码 `MANUAL_HISTORY_*`）；
- Paper：`GET /api/v1/paper/accounts/{account_id}/history`（`paper_get_account_history`，`GetPaperHistoryQuery`，错误码 `PAPER_HISTORY_*`），请求额外携带 `session_id`：会话必须存在且 `session.account_id == account_id`，否则 `PAPER_HISTORY_SESSION_NOT_FOUND` / `PAPER_HISTORY_SESSION_ACCOUNT_MISMATCH` 拒绝；`session_id` 计入 `result_id`。

请求必须显式携带：

| 字段 | 说明 |
| --- | --- |
| `start_date` / `end_date` | 估值区间（YYYY-MM-DD） |
| `knowledge_cutoff` / `publication_cutoff` | PIT 双截止；允许晚于区间末（回溯认知），但发布 ≤ 知识 |
| `source_snapshot_ids` | 保留价格快照（内容寻址），逐条验证存在且不晚于知识截止 |
| `ledger_event_count` + `ledger_hash` | 账本修订身份：append 顺序前 N 条事件的有序哈希（`ledger_hash`）。`GET /{account_id}/ledger` 响应的 `ledger_revision` 提供当前值 |

验证规则：事件数不足或前缀哈希不符 → `*_LEDGER_REVISION_*` 拒绝；账户种类不符 → 拒绝；快照缺失/超知识截止 → 拒绝。

响应（`ManualHistoryResponse` / `PaperHistoryResponse`，字段逐一同构）绑定 `result_id`（`manual-history:sha256:…` / `paper-history:sha256:…`，覆盖请求身份、修订、方法与逐日价格 lineage），包含：

- 逐点行：`on_date`、`valuation_instant`（当日上海 23:59:59.999999）、`total_value` / `cash`（缺价日资产为 null、现金仍可独立查看）、`external_flow`、`period_return` / `cumulative_return`（nullable）、`segment_id`、`price_time`、`stale`、`source_snapshot_ids`、`quality`（原因码 + detail）；
- 分段：每段独立归一的链接 TWR、`closed_reason`（`range_end` / `loss_to_zero` / `full_withdrawal` / `valuation_gap` / `negative_equity`）与原因码；
- `method = "twr-linked-v1"`、`valuation_policy_version = "account-valuation-stale-evidence-v1"`（#261 起为 Manual/Paper 共用的单一权威政策版本，替代 #260 的 `manual-valuation-stale-evidence-v1`）、币种 CNY。

重放：同一请求身份重算得到相同 `result_id`；账本追加更正后，旧修订结果不变，新修订（新 count+hash）可解释地不同。查询不写任何账本。

## 数值规则（首期精确模式）

- 子段收益 = 子段末/子段初 − 1；TWR = 各子段增长因子乘积 − 1；无 Modified Dietz 或其他近似。
- 亏损归零：终腿记 −100% 并结束分段；全额赎回：末日腿为流前收益、绝不记 −100%；再注资开启新分段，不跨零链接；负净资产该腿留空并标 `negative_equity_unsupported`。
- 估值断口（缺价日）打断链接：下一点开启新分段，断口日以 null 资产行展示原因；单点分段只显示资产，不报告区间收益。
- 证券划转（`transfer_in`/`transfer_out`/`opening_position`）在 v1 只标记 `security_transfer_unsupported`，该腿留空。

## 估值价格策略（`account-valuation-stale-evidence-v1`）

- 价格只用原始收盘价（不复权、不乘复权因子）；来自请求声明的保留快照，按 PIT 三钟逐日严格过滤（occurred ≤ 当日、published ≤ 当日晚间、available ≤ 知识截止）。晚间重发布的 bar 在更早估值日不可见。
- 当日无 bar 时沿用最近可见原始价，条件是：候选 bar 之后可见交易继续（存在更晚 bar），或候选 bar 本身带停牌标记；否则视为未知退市残值 → `price_missing` 断口，不永久沿用最后价。
- 沿用价在可证明的交易日上标记 `stale_price`（含实际价格日）；非交易日（无任何持仓工具 bar）沿用是精确的，不标停牌。
- bar 的 `occurred_at` 是上海午夜时刻（UTC 前一日 16:00），所有日期比较先转到 Asia/Shanghai。

## 边界

- 请求区间末尾仍在进行的停牌（窗口内无复牌 bar、无停牌标记）按缺价处理——区分停牌与退市需要更多证据，留待后续票据。
- 停牌/退市判定仅基于保留价格与停牌标记；#259 的五类试样是数据集级准入证据，与本查询互不等待。
- Web 共享同一「历史收益」面板组件（`account-history-panel.tsx`）：Manual 标注「实盘记录（Manual）」、Paper 标注「模拟成交（Paper）」并显示会话绑定；表格与图表全部消费同一后端结果，前端不复制金融规则。

## 测试接缝

- 纯数值手算：`packages/portfolio/tests/unit/test_account_returns_unit.py`（入金 0%、10%×10%=21%、费用 −1%、除息 0%、全额赎回/亏损归零/再注资/断口/时点未知等 20 例）。
- 查询层：`packages/application/tests/unit/query/test_portfolio_history_unit.py`（修订重放、更正隔离、停牌沿用、缺价断口、PIT 重发布不可见等 15 例）与 `test_paper_history_unit.py`（会话绑定、费用/分红内部化、跨账户冲突、会话身份入 result_id 等 9 例）。
- 真实装配：`apps/backend/tests/integration/test_manual_history_live_fixture_integration.py` 与 `test_paper_history_live_fixture_integration.py`（保留价格 + 真实 DI 容器 + 入金/费用/分红 + 会话冲突 + 更正后旧身份不变）。
- 手算验收数值允许误差 1e−10；本切片全部 Decimal 精确断言。
