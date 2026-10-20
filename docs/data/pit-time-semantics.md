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

1. **cutoff 签发**（`APP/processes/selection/assemble_facts.py:422-486` `_resolve_cutoffs`）：
   请求声明或服务器时钟；`_LIVE_SKEW=5min`（`:143`）拒过去/未来时刻；
   因果序校验 `declared_knowledge <= as_of`。
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
