# PIT 时间语义全景（字段 · 摄取 · 消费筛选）

> 本文是全系统 PIT 时间字段的权威参考：每条字段怎么在摄取时写入、值从哪来、
> 每个使用场景用什么字段做什么筛选。核查基线 2026-10-20（main `0fe3cf7f`），
> 全部条目带 file:line 证据；活体车道 as_of 滚动语义变更见
> [Issue #583](https://github.com/cosmos-arc/ditto/issues/583)。
>
> 路径缩写：`APP=packages/application/src/ditto_application`，
> `DATA=packages/data/src/ditto_data`，`BT=packages/backtest/src/ditto_backtest`。

## 0. 四轴模型

| 轴 | 回答的问题 | 字段族 |
|---|---|---|
| **事实时间** | 这件事说的是哪天 | `trade_date`、`report_date`、`changed_date`、`end_date`、推导出的 `effective_from/to` |
| **知识时间** | 我们什么时候能知道 | `knowledge_date`、`observed_at`、`published_at`、`available_at`、披露锚 `f_ann_date/ann_date` |
| **系统时间** | 系统什么时候动的 | `created_at`、`updated_at`、`occurred_at`、`freshness_at`、`written_at`（一律 UTC 时钟） |
| **版本** | 用的是哪一版 | `snapshot_id`（内容寻址）、`checksum`、run 的 `input_hash` |

核心不变量（`.agents/skills/ditto-pit-safety/references/pit-contract.md`）：
知识/披露时间 ≤ 声明 cutoff、版本在 as_of 有效（左闭右开 `effective_from <= as_of < effective_to`）、
属于选定快照宇宙、缺任一维度即 fail-closed，禁止回退"最新数据"。

## 1. 摄取侧：字段怎么写进来

### 1.1 Provider 快照（证据链层）

| 字段 | 写入点 | 值来源 | 语义 |
|---|---|---|---|
| `created_at` | `DATA/catalog/source_snapshot.py:62`；提交时 `APP/processes/ingestion/ingestion_evidence.py:139` | 提交时刻 UTC 时钟 | 内容首次可见时间；同内容重观察只追加事件不改此值 |
| `observed_at`（观察账本） | `DATA/catalog/source_snapshot_store.py:105` | `max(now, created_at)` 追加；读取取 MIN | 本地目录对该内容的观察历史 |
| `request_start/end` | `ingestion_evidence.py:140-141` | 请求窗口或单日 trade_date | provider 请求区间锚，进 snapshot_id 哈希 |
| 分区 `updated_at` / 事件 `occurred_at` | `DATA/ingestion/partition_state.py:52,83` | 阶段推进 UTC 时钟 | chunk 恢复边界（PLANNED→PAYLOAD_COMMITTED→COMPLETE） |

### 1.2 knowledge_date 四类口径（核心差异）

| 口径 | 数据集 | 值 | 证据 |
|---|---|---|---|
| **供应商公告锚** | 财务三表＝`f_ann_date`（明确不用会被改写的 `ann_date`）；fina_indicator / fund_portfolio / etf_nav＝`ann_date` | provider 字段 | `DATA/sources/tushare/adapters/fundamental.py:30-34,242-243`；`processors/mappings/capital.py:185,232,270` |
| **T+1 推导** | 日线 OHLCV、stock_limit、limit_list、fund_share | `trade_date + 1` | `processors/mappings/common.py:31-33`；`mappings/basic.py:79-93,118-120` |
| **即日** | adj_factor | `= trade_date` | `common.py:60-66` |
| **观察日本身/采集日** | index_weight＝`trade_date`（#452：官方无公告时刻，不伪造）；forecast/express＝`date.today()`；macro＝检索观察日缺省今天 | 推导/时钟 | `adapters/capital_index.py:39-41`；`fundamental.py:100-101`；`adapters/macro.py:143` |

### 1.3 行级 PIT 区间与守门

- 财务三表摄取时把披露锚固化为 `knowledge_date → effective_from`、`effective_to=NULL`
  （`fundamental.py:240-244`；SQLite 表列 `DATA/storage/base/sqlite_table_spec.py:16-26`）。
  运行时不存在名为 `ann_date` 的筛选列——披露锚在写侧变成三列闸门。
- 落库前守门 `validate_sparse_pit_cutoff`：拒绝 `knowledge_date > cutoff(trade_date)` 的行
  （`APP/processes/ingestion/sparse_pit.py:49-79`）。
- `observed_at` **两个含义**：快照观察账本（§1.1）vs 名称/ST 历史行可知时间——后者
  **provider `published_at`（公告日）优先、缺省回退本地时钟**（`DATA/services/metadata/instrument.py:1346`）。

### 1.4 已知缺口（留档，改动须另票）

- 名称/ST 历史 `recorded_at` 只在行字典不落列（`name_history_writer.py:127-129` 仅作回退）。
- index_weight 无公告可知性轴（#452 设计取舍）；index_constituent 未接摄取。
- 回补时代无逐日版本史（轻度前视不可消除，靠 force 重拉 `VERIFY_IDENTICAL` 稳定性缓解）。

## 2. 消费侧：每个场景怎么筛

### 2.1 live 选池车道（#583 变更对象）

三层闸门：

1. **cutoff 签发**（`APP/processes/selection/assemble_facts.py` `_resolve_cutoffs`）：
   请求声明或服务器时钟；`_LIVE_SKEW`（5min）拒过去/未来时刻；
   声明值钳制在服务器时钟，且允许晚于滚动的 as_of（决策定在昨收、以当下知识做出，
   见 §1 `knowledge_date` 四类口径与 #583 裁决）。
   单位注记：`average_turnover`/`min_average_turnover` 以**元**为口径（bars amount
   千元入库、装配边界 ×1000 换算，#506/#507）；单位口径变更会改写 `input_hash`
   内容寻址身份——跨口径边界的重发产生新 run 而非重放旧 run，属预期。
2. **行级**（`assemble_facts.py:1174-1205` `_without_future_knowledge`）：
   bar 的 `knowledge_date <=` publication 截止的上海日；**同日知识行（kd==trade_date）
   当日 18:00（`_BAR_PUBLICATION_TIME`）前视为未发布；T+1 戳的行从自身 knowledge_date 起可见**。
   cross_date＝过滤后最大可见交易日（`:1230-1238`），不是 as_of 日期。
3. **快照/宇宙级**：#581 并集覆盖（`APP/queries/snapshot_readiness.py:217-291`）；
   `_observed_by` 取链上 cutoff 前最近观察成员（`APP/queries/historical_universe.py:277-290`）；
   `visible_history` 三列闸门 available≤knowledge、publication≤publication、区间含 as_of
   （`DATA/services/historical_universe.py:136-175`）。

运行记录：`input_hash` 把 as_of/knowledge/publication **三个 cutoff 全部纳入哈希**
（`packages/strategy/src/ditto_strategy/selection/canonical.py:241-242,299-316`）——
同策略不同 cutoff 必得不同 run；内容寻址重放即版本钉死，强于时间过滤。
rotation 与 selection 的三元组必须逐项相等（`run_industry_and_security_selection.py:63-79`）。

### 2.2 ETF Paper 链（#304/#306 裁决）

三 cutoff 因果序 `signal_cutoff <= reference_cutoff <= execution_cutoff` 且
`execution_cutoff > signal_cutoff`（`APP/etf_paper_execution.py:125-184`）；execution 须在
收盘后（生产 bar 是 T+1 知识，`_follows_close`）；reference cutoff 冻结进 package
（`etf_paper_handoff.py:157-184`）；账本读独立 `recorded_through` 闸门
（`APP/queries/account_ledger.py:101-119`）；信号相 D 日冻结基准、估值随 execute 相
（`queries/etf_paper_execution_facts.py:87-231`）。

### 2.3 快照重放与研究认证

- 重放（`APP/queries/provider_snapshot.py:37-130`）：单一 `knowledge_cutoff`；
  未来快照 fail-closed（不是静默丢行）；ticker 解析绑定同 cutoff；**无 publication_cutoff**（不对称，留档）。
- R3 认证（`APP/queries/research_certification.py`）：复用 `SnapshotReadinessQuery.assess`
  对声明窗口判 reason_codes，另校验研究快照记录身份。

### 2.4 回测引擎

- 知识滞后：`knowledge_lag_days=1`（`BT/config.py:167`）——T 日决策只信 ≤T-1 知识
  （`BT/synchronizer.py:40-59`）。
- 行级：bar `trade_date < as_of_date` 严格小于（`BT/data_feed.py:430-464`）；
  财务 SQLite 三列闸门 `knowledge_date <= ? AND effective_from <= ? AND effective_to > ?`
  （链路 `fundamental_snapshot.py:107-148` → `sqlite_table_reader.py:34-53`）。
- 宇宙/花名册只在 `start_date` 钉一次（`APP/builders/service_factory.py:498-515`），
  池成员走事实区间 `effective_from<=asof<effective_to`（`universe_reader.py:94-127`）。
- 研究快照血缘绑定 bar 的 `source_snapshot_id`，不完整即 fail-closed（`data_feed.py:301-339`）。

### 2.5 因子物化（#418）

`knowledge_cutoff = request_end` 进 manifest 并入哈希（`APP/processes/materialization/orchestrator.py:498-505`）；
编译缓存键无时间输入（时间身份由 manifest+分区窗口承载）；通用读侧行级
`knowledge_time <= evidence.knowledge_cutoff`（`packages/features/src/ditto_features/risk_estimation/`）；
market_context 请求校验三序 `publication <= knowledge <= as_of`
（`DATA/query/contracts.py:44-64` `PITQueryContext`）。

### 2.6 通用数据读取端点的语义声明与限制传播（#628 P4）

- **语义词汇表**（backend `models/common.py` `ReadSemantics`）：
  `latest_available`（现存行，无 PIT 过滤——受限研究）/ `pit_asof`
  （as_of 可见版本；**日粒度 as_of=上海日终**，date 精度知识当日全天
  不视为部分可见）/ `frozen_snapshot`（快照重放）。各数据端点 docstring
  逐一声明所属语义；`/market/etf-nav` 响应内联 `read_semantics`。
- **SQLite PIT 修订收敛**（`sqlite_table_reader.py _finalize`）：PIT 查询下
  同事实键多版本（修订公告双开区间行）收敛到 knowledge 最新可见版本
  （并列取 effective_from 更晚），输出确定性排序；非 PIT 读不收敛
  （corporate_actions 版本史契约）。corporate_actions 事实键含
  action_type（同日异类型≠修订）。回测/CLI/API 全消费端经此一层收敛。
- **覆盖限制传播**：`ditto_data/coverage/limits.py` 是 #622 覆盖合同的
  运行时蒸馏（守卫测试同步），`GET /datasets/coverage` 暴露全量；
  etf-nav 响应携带 `data_coverage` 直达图表降级文案与导出链
  （验收记录 docs/data/consumer-pit-verification.md）。
- **fail-closed 补口**：fundamental/capital 标识符解析失败 404（原静默
  空列表）；dividend 未披露数值 null 透出（原 amount 恒 0.0 伪映射）。

## 3. 三条车道的过滤规则（#583 讨论收敛的最终结论）

| 车道 | 卡不卡入库时间 | 防前视靠什么 |
|---|---|---|
| **回补历史**（如 2014-2025） | 不卡（没有"当时"） | 事实日期 ≤ as_of + 冻结 vintage |
| **live** | 卡 `available_at <= knowledge=现在`；as_of 滚动到最近完整交易日（#583），解除 knowledge ≤ as_of 耦合 | 行级 `effective_from <= as_of` 挡 T 日事实泄漏 |
| **live 时代重放/逐日 vintage 回测** | 卡 ≤ 模拟决策时点 | 入库时间闸门 + snapshot_id 钉死 |

两条横切原则：

1. **knowledge = 真实入库时刻（receipt time），永不回填**。它是真发布时刻的可证明上界
   （拿到 ≥ 发布），回测只会悲观不会前视；`publication_at` 只接受供应商自证值，否则等于
   入库时刻。估算发布时刻制造乐观误差（无声虚高），禁止。
2. **T 日决策不得执行在不可得的 T 日收盘信息上**：T+1 知识的 bar 从自身 knowledge_date
   起可见（18:00 规则只约束同日知识行）；执行时点显式建模（paper 链 `_follows_close`）。


### 3.1 普通历史重建的冻结输入（#751）

普通请求的 `historical_reconstruction=true` 落实“回补历史”车道：在请求冻结时点选定已留存的供应商快照，验证原始 payload 的校验和、schema 和绑定该身份的 COMPLETE 证据；完成时间晚于冻结时点不能补算为当时可用。更新但未完成或缺行的快照不能退回旧版本来掩盖缺口。

本路径读取留存 payload 中原有的事实/披露锚点，不改写 canonical 表或 receipt。供应商规范化字段 `knowledge_date` 在该原始载荷中表示业务可见日，与目录 `created_at` 的真实入库时刻不同：行情保持 T+1 可见，财务保持披露日、报告日及已有版本有效区间约束。原有因果历史过滤继续生效；当前最新分类和可变派生因子不能混入冻结输入。无法证实历史原始版本完整性时，报告仍为受限研究，不认证历史持有能力。

请求通过已有运行记录持久化，冻结来源及失败预检通过追加式 `historical_inputs` artifact 保存。失败后补证创建关联的新运行；已解析成员沿用原请求，重新冻结新的来源集合，旧记录不随补证改变。成员区间、上市身份及逐日参与见下节；分红、拆并、退市清算和完整历史资格仍由后续任务补齐。

代表性验证使用 2026 年实际入库的 2014 年行情、复权、基准和日历，在生产 UI/API/引擎的隔离状态目录完成 2014-10-13..2014-10-24 运行。合成系统旅程另行覆盖缺少复权来源、补证重试与旧请求不变；财务未来哨兵测试单独检查晚披露不可提前消费。来源、范围和规则依据见 [验收记录](../evidence/historical-request-751.md)。

### 3.2 普通历史重建的逐日成员（#752）

`historical_reconstruction=true` 在首次解析时冻结与请求窗口相交的成员区间和证券身份，按 `effective_from <= trade_date < effective_to` 逐日取成员，不以当前开放区间覆盖过去。上市前、已退出上市、当日不在池、交易日预热不足及上市初期规则未覆盖分别留有原因；这份事后登记资料仍不是历史原始版本完整性或当时可得性认证。补证的新运行沿用原冻结区间及上市资料；旧版仅保存起始成员 ID 的请求继续锁定原 ID。

预热起点由校验后的实际交易日历倒数取得，按决策 cutoff 前真正可见的原始行情计数；周末、假期及停牌估值不充数。缺少实际行情、复权、基准或必要状态仍拒绝运行，不以前填价格制造可交易行情。已确认全天停牌且缺报价时，执行估值可保留过去真实收盘价及其报价日期、来源，禁止成交且不进入信号历史，详见 [状态说明](../evidence/historical-status-756.md)。#753 已将历史重建主板股票的上市初期资格改为实际交易日规则；其他尚未覆盖资产仍保留明确限制。

选股只消费当日合格成员；估值、风险检查及卖出仍消费实际持仓所需行情，退出证券池不会抹去持仓。预检资格保存在 `historical_inputs`；运行结束或失败时，`daily_participation` 单独记录实际完成的日期。未完成日期不能标成已执行，可参与选股也不表示已买入。退市清算仍受独立门禁约束。

真实股票状态及涨跌停原始载荷可能没有 `knowledge_date`。这些字段仅用于当日执行约束，按业务日精确连接；不为其虚构披露/入库时间，不进入因子历史。股票价格、复权和财务原有可见日期约束继续生效。验收与限制见 [#752 记录](../evidence/historical-members-752.md)。

### 3.3 主板上市初期与逐日执行规则（#753）

普通历史重建按已冻结的沪深主板 A 股身份、上市日期和交易日历选取当日规则。2023-04-10 起上市的新股，前五个交易日不设日涨跌幅限制，第六日起使用普通 10% 幅度；长假不计数。实际信号所需的因果历史决定预热，不再用统一 60 日或上市满 30 个自然日阻止已具备输入的新股。上市日历不足仍拒绝，财务披露 cutoff 不放宽。

在运行详情展开“请求与冻结来源”，选择“逐日参与日期”，可回读当日执行规则的交易所、板块、生效日、涨跌幅、100 股买入单位、0.01 元报价单位及 T+1。旧记录缺少规则时显示“尚无已保存规则”；参与资格不是成交证明。实际成交、持仓和拒绝原因来自同一运行保存的报告与审计记录。计划阶段的涨跌停等拒绝也保留，补证后创建新运行，原请求不变。

普通日的原始涨跌停价须与当日规则及前收盘价一致；新股无限幅由上市日期和交易日历证明，不能仅凭供应商的极值或空值推断。买入当日份额不可卖，到下一交易日先结算，再生成交易计划。日线成交模型仍是研究假设，不重建盘中申报笼子、队列和临停细节。

深市无限幅阶段不接受市价申报，该限制同时进入规则说明、提交前拒绝记录及成交守卫。策略声明的订单类型不会被系统暗中替换。代表新股成交使用显式 `market_on_close` 研究设置，沿现有收盘集合竞价模型撮合；它不代表向交易所提交原生“收盘市价单”，也不证明真实队列或保证成交。

规则来源、固定样例与真实留存数据分别见 [#753 验收记录](../evidence/mainboard-rules-753.md)。2014 起交易规则资料与可执行的完整资金核算不是同一项：股票费用已由 [#757](../evidence/historical-fees-757.md) 按成交日分段并保存账单，ST/停牌按 [#756](../evidence/historical-status-756.md) 区分真实停牌、ST、零成交和未知，分红拆并与退出清算待各后续任务；这些缺口继续阻断相应运行，三类 2014 起完整目标仍未关闭。

### 创业板改革与上市初期（#754）

普通历史重建覆盖创业板股票身份，包含 302 号段，排除存托凭证和同码指数。2020-08-24 前普通股票使用 10% 限幅，此日起使用 20%；注册制新股前五个实际交易日无日涨跌幅限制，第六日起 20%，不把 2023 年主板注册制日期套用到创业板。国庆等休市日不计入上市交易日。

规则说明与执行共同使用当日单笔申报上限：改革前 100 万股，改革后限价 30 万股、市价 15 万股。收盘集合竞价研究单按限价上限；超量申报在缩量或部分成交前拒绝，并在审计证据保留原因。无日涨跌幅限制阶段仍不接受深市市价申报。回测与 Paper 复用相同申报守卫，历史费用继续独立按成交日计算。

资料、固定样例、真实数据缺口与产品操作见 [创业板验收记录](../evidence/chinext-rules-754.md)。三只存量退市整理股票的旧规则例外保留，但状态与退出账务仍需 #756/#763；缺证不能被当作普通状态，也不能以永久拒绝核销这些目标。

### 历史费用账单（#757）

在回测详情的“成交”页展开“逐笔费用账单”，查看包括未平仓买入在内的实际成交，逐笔核对佣金、卖出印花税、过户费及采用费率的生效日。金额单位为人民币元，数量为股或份。页面最多显示六位小数；原始精度随报告 JSON 导出，重开读取已保存账单。旧报告未保存该账单时明确显示缺失，不用今天的费率补算。

普通回测的策略佣金输入是小数费率：0.0003 表示万三，每次实际成交最低 5 元。它包含经手费、证管费及券商留存，**已经剔除另列的中登过户费**；录入实际券商全佣前需先核对并剔除重叠项。普通回测不模拟券商逐项分币舍入、当日多次成交合单优惠或个人佣金合同。ETF 免股票印花税和过户费。该研究假设及 2014—2015、2015/2022/2023 断点见 [费用依据与验收](../evidence/historical-fees-757.md)。

请求缺少历史来源时沿用原有补证恢复入口，新运行保留父运行关系，原失败请求不变。账单成功不表示历史完整性、策略资格或 Paper 授权已通过。

### 财务因子按披露锚参与选股（#765）

股票多因子普通历史运行逐会话消费冻结的 `income_statement`/`balance_sheet` 披露行：会话 knowledge_date 早于披露锚（`f_ann_date`→载荷 `knowledge_date`）时因子缺失、不参与该因子排序，公告日起取当时可见版本；报告期（`report_date`）早于会话不构成可知性；同一报告期多次披露按当时可见最新披露版本收敛，披露锚晚于运行终点的行不进入冻结帧（未来哨兵）。披露锚与快照拉取日是两个时间轴：财务冻结按（证券, 报告期, 披露锚）直接归并全部可见快照 payload（同键晚观察快照胜出，对齐活车道 #628 收敛），不按拉取日窗解析逐格 lineage——跨周末公告等只出现在后续拉取 payload 的披露行不会被静默剔除（#765 F1）。运行保存的 `historical_inputs` 含两表快照身份与真实 receipt，作为公布、修订及来源边界。

股票历史冻结在运行范围内一份披露都冻不到时显式拒绝（`missing retained income_statement/balance_sheet`），不再静默空帧成全现金运行；补证走 #751 恢复入口，重跑产生新身份，旧运行报告不变。行业分类尚未进入历史冻结输入（`sector_id` 仅活车道注入），按当时生效版本参与历史选股留档于 #801。固定样例旅程、真实库代表案例与已知边界见 [验收记录](../evidence/financial-factors-765.md)。

## 科创板历史执行（#755）

普通历史研究现支持具有冻结身份的 SSE 688 股票。2019-07-22 之前不创建科创板上市历史；
证券上市前排除，依策略所需可见历史完成预热后才参与选股。上市前五个实际交易日不限日
涨跌幅，第六日起 20%；200 股起报、逐股递增，限价/收盘集合竞价单笔不超过 10 万股，
市价不超过 5 万股；不足 200 股仅允许一次卖出全部余额。日线研究不还原盘中价格笼子、
临停、保护价或盘口，收盘集合竞价不代表盘后交易。规则日期、股数单位、拒绝原因、
来源及费用均可从原结果回读和导出。操作、实际窗口与未完成范围见
[科创板验收记录](../evidence/star-rules-755.md)。
