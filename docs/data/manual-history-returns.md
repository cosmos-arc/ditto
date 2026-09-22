# 账户历史估值与资金流调整收益（Manual / Paper / Model）

规格来源：[#249](https://github.com/cosmos-arc/ditto/issues/249)（三组合历史估值与资金流调整收益）、实施票 [#260](https://github.com/cosmos-arc/ditto/issues/260)（Manual）、[#261](https://github.com/cosmos-arc/ditto/issues/261)（Paper）、[#262](https://github.com/cosmos-arc/ditto/issues/262)（Model 目标重放）。本文记录数值与查询合同；三组合共同区间比较由 #263 后续接入，数值合同复用本文。

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
- Paper：`GET /api/v1/paper/accounts/{account_id}/history`（`paper_get_account_history`，`GetPaperHistoryQuery`，错误码 `PAPER_HISTORY_*`），请求额外携带 `session_id`：会话必须存在且 `session.account_id == account_id`，否则 `PAPER_HISTORY_SESSION_NOT_FOUND` / `PAPER_HISTORY_SESSION_ACCOUNT_MISMATCH` 拒绝；`session_id` 计入 `result_id`。HTTP 映射上会话缺失为 404，其余（含账户缺失，与 Manual 路由一致）为 422。

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

## Model 历史目标重放（#262）

入口：`GET /api/v1/portfolio/model-history`（`portfolio_get_model_history`，`GetModelHistoryQuery`，错误码 `MODEL_HISTORY_*`）。请求携带 `strategy_id`、区间、显式 `initial_capital`（正数，Decimal）、PIT 双截止与可选 `artifact_ids`：

- `artifact_ids` **留空**＝解析当前知识截止内可见的 active SIGNAL_PACKAGE（`signal_date` 落在区间、`created_at ≤ knowledge_cutoff`、逐日唯一；同日多个 active → `ARTIFACT_DATE_AMBIGUOUS` 拒绝）；响应 `targets` 回带解析到的 (signal_date, artifact_id, checksum) 供后续钉住。
- `artifact_ids` **非空**＝精确钉住重放身份：工件必须属于该策略（`ARTIFACT_NOT_FOUND`）、信号日落入区间（`ARTIFACT_DATE_OUT_OF_RANGE`）、checksum 校验通过（`ARTIFACT_INTEGRITY_INVALID`）。工件是不可变行，status 可被后续发布归档，但钉住读取不受影响——**未来目标变化不改写旧身份的重放结果**。

重放语义：从 `initial_capital` 出发，在每个工件自己的 `signal_date` 收盘按保存的 `target_weight` 再平衡（金额量化 0.01、数量量化 0.0001，残差为现金，现金不得为负），之间按持有数量以原始收盘价漂移估值。逐日价格来自**该生效工件声明的 `dataset_snapshot_ids`**（逐条验证存在且不晚于知识截止），沿用 `account-valuation-stale-evidence-v1` 停牌沿用政策。首个保存目标之前的交易日为显式 `target_missing` 空档（资产/收益留空）；区间内无可见目标时返回空 targets/points/segments，不伪造任何一天。模型腿没有外部资金流（`external_flow` 恒 0）；当前**没有已注册的成本规则**，重放按无费用、无公司行动处理——不会与 Paper/Manual 的实际费用与分红重复计入；未来注册成本规则时必须作为重放身份的一部分被钉住。`result_id`（`model-history:sha256:…`）绑定策略、区间、初始资本、双截止、工件集（日期+id+checksum）与逐日价格 lineage。

Web：组合比较工作台内「历史收益（保存目标重放）」面板（`model-history-panel.tsx`），复用共享的 `AccountHistoryResult` 展示（分段卡、首段曲线、逐日表），并标注「模型目标（Model）」与保存目标工件清单；与 Manual/Paper 面板共用同一后端数值，前端不复制金融规则。

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
- 查询层：`packages/application/tests/unit/query/test_portfolio_history_unit.py`（修订重放、更正隔离、停牌沿用、缺价断口、PIT 重发布不可见等 15 例）、`test_paper_history_unit.py`（会话绑定、费用/分红内部化、跨账户冲突、会话身份入 result_id 等 11 例）与 `test_model_history_unit.py`（保存目标漂移重放、钉住工件抗替代、首包前空档、缺历史空视图、未来发布不可见、权重/快照/身份反例等 14 例）。
- 真实装配：`apps/backend/tests/integration/test_manual_history_live_fixture_integration.py`、`test_paper_history_live_fixture_integration.py` 与 `test_model_history_live_fixture_integration.py`（保留价格 + 真实 DI 容器 + 真实工件存储：入金/费用/分红、会话冲突、更正后旧身份不变、目标被替代后钉住重放不变）。
- 手算验收数值允许误差 1e−10；本切片全部 Decimal 精确断言。
