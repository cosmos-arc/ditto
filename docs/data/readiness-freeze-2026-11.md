# 47 项数据统一就绪冻结基线（#658 批次 0）

- 冻结时间：2026-11-03（Asia/Shanghai）。规格入口 [#658](https://github.com/cosmos-arc/ditto/issues/658)；
  权威裁决：[#652 统一证据门](https://github.com/cosmos-arc/ditto/issues/652)、
  [#653 正确性修复](https://github.com/cosmos-arc/ditto/issues/653)、
  [#654 首个消费流程](https://github.com/cosmos-arc/ditto/issues/654)、
  [#655 47 项范围](https://github.com/cosmos-arc/ditto/issues/655)、
  [#656 运行与恢复](https://github.com/cosmos-arc/ditto/issues/656)、
  [#657 实施安排](https://github.com/cosmos-arc/ditto/issues/657)；地图 [#649](https://github.com/cosmos-arc/ditto/issues/649)。
- 代码基线：`9d7f84e6f5fc67b1d53cede25b8a30c0045f9362`（归并研究资产时的 main HEAD）。
- 测量基线：[47 项只读库存基线](../research/2026-11-03-data-readiness-baseline.md)
  （2026-11-03 20:17 扫描，含逐证券复测、消费入口矩阵与容量盘点）和
  [来源与时间边界研究](../research/2026-11-03-data-readiness-source-boundaries.md)；
  本地证据 JSON 的 SHA-256 见基线文档。引用基线数字必须带时间，不作为未来当前值。
- 领域词汇表：[CONTEXT.md](../../CONTEXT.md)（本批已归并「数据就绪」「历史信息重建／本地快照重放／受限历史研究」，
  以及三件套「适用来源公开时间规则」与「重拉恢复＝按重建证据界定」两处修订）。

## 冻结的意义与边界

本文件冻结 47 项的**正式期望集合**：范围与身份、历史起点规则、声明消费用途、限制与现存反例，
供批次 1–5 实施与验收消费。冻结不改变代码与数据现状——所有修复、补数、接线、重测归后续批次；
本批不重做事实扫描。冻结后修改范围、起点或限制须维护者新决策，不得以改标签、删难项或缩分母替代。

- 47 项 `dataset_id` 以 [coverage-contract.yaml](coverage-contract.yaml) `datasets` 键为机读真源
  （守卫测试保证与 `Dataset` registry、`INGESTION_SPECS` 三方一致），本文件不另立第二份 ID 清单。
- 验收门＝#652 统一六门：范围与身份／覆盖与新鲜度／时间与版本／实际消费／运行与补偿／恢复。
  合同静态 `ready/partial/empty` 是 2026-11-03T00:15 的测量快照，**不构成最终验收结论**；
  47 项最终状态由批次 5 逐项重测给出。
- **测量计数不是分母**：20,897 个指数定义、546,096 行指数行情、90 行指数估值等只证明物理库存。
  指数、FRED 系列、期货合约等正式期望集合按矩阵「范围与身份」在实施中从权威配置冻结实际代码名单并留证据。
- 三种历史使用（最新观察／历史信息重建／本地快照重放）按 CONTEXT.md 定义分别验收；缺证据只准受限历史研究。
  日期级 as-of 维持上海日终语义；22:30／09:15 是新鲜度承诺，不自动创造日内 PIT 能力。

## 共同边界（适用全部 47 项）

- 核心历史目标 2014-01-01 起；晚于此的上市／成立／合约上市／真实来源起点按有据适用者开始，
  不以本地首次采集日替代目标起点；保留更早历史与必要前值，不做无需求裁剪。
- 股票正式范围＝沪深 A 股含退市历史；BSE 个股完整链在范围外（存量与北证指数展示保留）。
  公募持有人覆盖全部可取得披露含场外 `.OF`；持有人身份与可交易证券身份分开，不伪称基金全部资产。
- 事件／季度按应披露事件对照验收，不按逐日行数；未发生≠源未产生≠制度不披露≠抓取失败，分别归因。
  Q2/Q4 报告期不能单凭月份推定全持仓；同报告期不同公告日不一律折叠为修订。
- 全球背景（现有 21 指数、6 外汇对、商品与宏观系列）仅展示与参考，不自动接入策略/交易输入。
- 公司行动＝回购/解禁（rights 排除）；行业＝申万（CSRC 排除）；
  期货＝六所实际合约（SHFE/CZCE/DCE/INE/CFFEX/GFEX），无主连拼接与换月回测。
- 采购未授权：现有源不足时记录精确补源依据与报价待裁决，不恢复旧年度预算上限。

## 47 项冻结矩阵

列说明：**起点规则**为冻结期望（非实测值）；**现入口**为 2026-11-03 基线的静态消费核验结论
（含运维读取；「仅存储」＝已装配 Reader 但未追到应用读取）；批次代号
B1=修正安全链、B2=补数与存量纠正、B3=首个真实流程、B4=其余范围、B5=总验收。
分页/补偿/恢复 verify 三类共享缺陷见下节，适用全部摄取型数据集，不在逐行重复。

| dataset_id | 冻结范围与身份 | 起点规则 | 声明消费用途（现入口） | 现存反例与缺口 → 批次 |
| --- | --- | --- | --- | --- |
| `calendar` | 覆盖 2014 目标及所需前后边界；市场交易日、北向交易日、结算日分开 | 2013-01-01 前后边界（实测至 2027） | 日历/研究/运维（应用+HTTP） | 北向/结算日历未分离 →B1（两融/北向适用日历） |
| `stock_basic` | 沪深全生命周期名册含退市；历史身份与当时可见名册分别取证 | 全历史 | 名册/选池（HTTP+CLI） | 11-02 审计窗缺上市日名册 3 只 →B2 归因 |
| `etf_basic` | 约定 ETF 全生命周期含退市/旧码；ETF/LOF/场外分类准确 | 全历史 | ETF 链路（HTTP+CLI） | 分类准确性核验 →B4 |
| `index_basic` | 目录可保留；正式消费集合及历史定义版本明确 | 全历史 | 目录查询（HTTP+CLI） | 20,897 定义≠分母；正式集合已冻结（178 码，[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `etf_reference` | 现有真实参考观察及后续；不伪造历史 config | 观察起点 2013-01-04 | ETF 候选（HTTP） | catalog 无登记条目（ops status missing）→B2 登记 |
| `stock_daily` | 沪深 A 股（含退市），逐证券缺口及生命周期归因 | 2014-01-01 或上市起 | 图表/研究（HTTP+CLI+研究） | 10,201 个 trading_no_bar、上市日前 bar 76,267 →B2 归因纠正 |
| `etf_daily` | 约定 ETF（含退市/旧码）；无状态证据与真实缺行情分开 | 2014-01-01 或上市起 | 图表/研究（HTTP+CLI+研究） | 通用入口 qfq/hfq 被忽略 →B1；no_status_dataset 210,870 会话归因 →B2 |
| `index_daily` | 权威宽基/风格及消费申万集合；停供历史明确 | 2014-01-02 或实际发布/源起点 | 展示/研究（HTTP+CLI） | 代码名单已冻结（178 码，[4d 声明包](formal-sets-and-declarations-2026-11.md)）；三申万断供已治愈留档（#648） |
| `global_index_daily` | 现有 21 个参考指数 | 2014 或真实起点 | 仅展示（HTTP） | knowledge_date 最早 2026-10-27（回填语义）；版本限制已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `stock_status` | 沪深（含退市）；更早无证据不造状态、不放行严格消费者 | 2016-08-09（已证源起点） | 研究/审计（内部应用） | 19,274 个缺状态会话 →B2 归因 |
| `adj_factor` | 与正式股票行情逐证券逐会话对齐；值/生效日/版本共同验证 | 与行情同窗 | 复权/研究（HTTP+研究） | 股票侧有价缺因子=0（11-02 窗）；对齐验证 →B5 重测 |
| `fund_adj` | 与 ETF 行情对齐 | 与行情同窗 | ETF 复权（内部方法+运维） | 92 个有价缺因子会话 →B1 接线、B2 归因关闭 |
| `etf_nav` | 单位/累计 NAV、公告延迟、修订及末端 | 2014-01-01 或基金成立起 | ETF 估值（HTTP） | 末端已到 11-02（基线仅证末端，中间日连续性未证）；22:30 新鲜度门 →B3 |
| `stock_limit` | 与沪深价格范围一致；上市特殊限幅/停牌规则 | 2014-01-02 起 | 限幅事实（现仅运维 DQ） | 研究消费接线与特殊限幅规则 →B4 |
| `moneyflow` | 沪深逐证券；缺口归因 | 2014-01-01 起 | 资金画像（facade+运维） | 画像消费 →B3；BSE 源端限制留档（#575） |
| `cyq_perf` | 真实源；2014–2017 不造数 | 2018-01-02（源起点） | 筹码（facade+运维） | 研究消费接线 →B4 |
| `limit_list` | 沪深涨跌停事件 | 2014 起或经证实端点真实起点 | 事件查询（现仅存储） | 本地仅 2026-09-30 起（840 行）→B4 历史回补+查询+起点取证 |
| `top_list` | 沪深龙虎榜事件；无事件≠漏页 | 2014-01-02 起 | 资金画像（现仅存储） | 消费接线 →B3；事件归因 →B4 |
| `top_inst` | 同一股票事件范围的机构席位；单边 null/重复保真，不推导总持仓 | 与 top_list 同窗 | 资金画像（现仅存储） | 消费接线 →B3；席位≠总仓位语义传播 →B3 |
| `hk_hold` | 通道真实开通/源起点；2024-08-19 制度分段；多持有人身份 | 2016-06-29（源起点） | 持仓研究（现仅存储） | knowledge_date 自然日+1 →B1；存量纠正 →B2；查询 →B4 |
| `hsgt_top10` | 沪/深通道实际开通起；制度后缺买卖/净额不填零 | 按通道开通日（实测最早 2014-11-17） | 北向十大（现仅存储） | 查询接线 →B4 |
| `fina_indicator` | 2014 起可知事实，保留更早比较期；版本 | 2014-01-01（保留 2012 起） | 财务指标（现仅存储） | 查询接线 →B4；#620 跨年错位已修留档 |
| `fund_share` | 正式 ETF 范围 | 2014-01-01 或上市起 | 份额研究（现仅运维） | 研究消费 →B4；发布节奏新鲜度 →B4 |
| `margin_trading` | 沪深实际两融标的生命周期 | 2014-01-01（保留 2013 起） | 资金画像（HTTP+CLI） | knowledge_date 映射错误 →B1；存量纠正 →B2；09:15 窗口消费 →B3 |
| `pledge_ratio` | 沪深；周频公开时间核新鲜度 | 2014-03-07 或真实源起点 | 质押（现仅 data service） | 末端 2026-09-18；读取入口 →B4 |
| `fund_portfolio` | 全公募持有人含 `.OF`；独立身份、报告类型和原文证据 | 2014-01-01 或基金成立起 | 持仓研究（现仅存储） | 现仅交易所基金 1,544 只；全公募+报告类型识别+查询 →B4 |
| `top10_holders` | 沪深公告；名单退出/送转/股份类别/修订正确 | 2014-01-02 起（保留更早） | 持仓研究（现仅存储） | 查询接线 →B4 |
| `top10_floatholders` | 同上，独立流通股榜口径 | 2014-01-08 起（保留更早） | 持仓研究（现仅存储） | 查询接线 →B4 |
| `balance_sheet` | 2014 起可知事实及所需前值；时点和版本正确 | 2014-01-01（保留 2011 起） | 财务（HTTP+CLI，pit_asof） | 无新增反例；#628 修订收敛已修留档 |
| `income_statement` | 同上；累计/单季与报表类型明确 | 同上 | 财务（HTTP+CLI，pit_asof） | 报表类型口径已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `cash_flow` | 同上；失败分区/末端真实闭合，不借其他财报推定完整 | 同上 | 财务（HTTP+CLI，pit_asof） | 12 分区代理 EOF 留档（#196）→B4 末端闭合核验 |
| `dividend` | 2014 起公告及实施事件；公告/登记/除权/到账分开，null 非 0 | 2014-01-01 起 | 分红（HTTP+CLI，pit_asof） | 除权末端 11-02 vs knowledge 末端 10-13——口径分离已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `valuation_metrics` | 沪深逐证券；分母、负值/null、版本及单位 | 2014-01-02 或上市起 | 估值（HTTP+CLI，pit_asof） | 无新增反例 |
| `corporate_actions` | 2014 起可知回购/解禁事件及生效日期；rights 排除，未来计划日合法 | 2014-01-01 起 | 公司行动（HTTP+CLI） | action_date 至 2034（计划日）——消费口径分离已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `earnings_forecast` | 2014 起公告；历史发布时间/版本不能凭回填日期推定 | 2014-01-01 起 | 业绩预告（现仅存储） | 2024-01-31 源异常（代理翻页损坏）→B2 回补；查询 →B4 |
| `earnings_express` | 2014 起公告；is_audit 与修订保真，不一概称已审计数 | 2014-01-01 起 | 业绩快报（现仅存储） | 查询接线 →B4 |
| `macro_indicators` | 中国现有 7 类 + 51 FRED 宏观系列；latest 与 vintage 用途分开 | 2014 或真实起点 | 宏观背景（HTTP+CLI，latest） | 51 系列 0 落库（探针已到）→B4 接线落库；末端 2026-09-01 |
| `fx_daily` | 现有 6 对；GMT 日/bid 口径 | 2014-01-01 起 | 外汇背景（HTTP） | 23,999 行全覆盖（#629）；历史用途限制已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `commodity_daily` | FXCM 金银、Sina CL/GC/SI、FRED 油/VIX 及配置项；逐腿证据 | 2014-01-01 或源真实起点 | 商品背景（HTTP） | FRED 油/VIX 腿未落库（#629 定界）→B4 逐腿接线；Sina GC/SI 2016-11 起（源深度） |
| `index_weight` | 现有 23 个宽基/风格指数实际成员/权重历史；公开时间非观察日，成立前不回造 | 2014-01-30（实测最早） | 历史证券池（HTTP） | observation 锚语义已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)；#452 as-of 语义留档） |
| `industry_classification` | 申万版本与分类定义；CSRC 排除 | 全历史版本 | 行业目录（现仅 data service） | 应用目录消费 →B4 |
| `industry_mapping` | 2014 研究所需有效区间及前值；历史公开证据与当前有效日期分开 | 有效区间全历史 | 回测分类截面（内部应用） | 11-02 请求矩阵唯一 uncovered（FAIL attempts=3，11-03 重刷仅覆盖当日）→B2 窗口证据闭合 |
| `namechange` | 沪深更名史含退市/旧码；公告与生效分开 | 2014 所需+前值 | 选股身份（HTTP） | 公告/生效口径已声明（[4d 声明包](formal-sets-and-declarations-2026-11.md)） |
| `st_history` | 沪深 ST 变更史及前值；不能用当前简称造历史 | 2014 所需+前值 | 选股身份（HTTP） | 无新增反例 |
| `futures_daily` | 六所实际合约日线 | 2014 或各合约上市/源起点 | 期货背景（现仅存储） | 本地仅 2026-10-26 起 →B4 历史回补+查询 |
| `futures_basic` | 与期货日线同范围含到期合约；身份、上市/到期定义 | 全历史 | 期货背景（现仅存储） | 查询接线 →B4 |
| `index_valuation` | 现有源支持的正式指数估值集合；冻结代码列表 | 2014 或真实起点 | 指数估值（现仅存储） | 本地仅 2026-10-26 起 90 行 →B4 历史+读取+列表冻结 |

## 已证实缺陷与现存反例（批次 1 修复范围）

代码事实均核验于 `9d7f84e6`，详证见 [#653 裁决](https://github.com/cosmos-arc/ditto/issues/653#issuecomment-6604370176)：

1. **分页 fail-open**：尾部探针把 `SourceFetchError` 变成 `False`
   （`packages/data/src/ditto_data/sources/tushare/client.py:433`），探针失败不能判定取尽却发布 COMPLETE；
   旧测试 `test_truncation_probe_failure_fails_open` 固化了错误预期。探针重复已见行/offset 失效同理。
2. **补偿终态失真**：retry/holes/daily 三个独立 flow 失败字典正常返回
   （`apps/backend/src/ditto_apps/jobs/flows/repair.py:130`），耗尽项从选择集合消失；
   须按最终未解决 `(dataset, source, date)` 判定。
3. **ETF 复权静默退回原价**：通用查询仅 stock 复权
   （`packages/data/src/ditto_data/services/market_queries.py:254`）；专用入口缺因子也返 raw。
4. **两融/北向可知时间错误**：自然日 T+1 映射
   （`packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py:82` 及 `:446`），
   不符交易所披露制度与北向专用日历；含已落库存量。
5. **恢复 verify 漏检**：manifest 中 `present=true` 证据树未全部校验存在与哈希；
   旧 COMPLETE 令缺文件重建静默跳过。

现存数据反例（基线 2026-11-03 20:17–20:25 复测，四次会话审计均 passed=false）：
股票 10,201 个 trading_no_bar、19,274 个缺状态会话（10-30→11-02 增 4）、停牌有价 1,841；
ETF 92 个有价缺因子会话、no_status_dataset 210,870；股票上市日前 bar 76,267、缺上市日名册 3。
这些是**待归因异常，不是已确认源端丢数**，归因与有界纠正归 B2。
请求矩阵（10-27..11-02，46 项×5 日）229/230 有完成请求覆盖；唯一 uncovered＝`industry_mapping` 11-02。
历史 FAIL 48 条无同源完成覆盖（47 条 attempts≥3），含源起点以前/非交易日/低频等待分类，不能称为 48 个真实数据洞。

## 恢复与容量冻结口径（详证见 #656 与基线文档）

- 备份策略＝每日、最近两份完整有效代次、**有重建证据的精简**：保留整份 metadata、全部 provider payload、
  paper/manual、策略、研究、agent 等不可重拉事实；canonical 仅逐分区证明可重建后省略。
- 20:40 现场：卷可用 58.422 GB；候选精简单份 10.311 GB、完整单份 11.830 GB；
  全部 canonical 可重建时候选峰值 36.015 GB，预算后余 22.407 GB；20 GiB 剩余空间门为规划假设非官方要求。
  不能证明可重建的 canonical 占 P GB 时保守峰值为 `3×(10.311+P)+5.082` GB，超门阻断。
- 17.72 GB worker 日志需轮转与保留安排，未清理前不计入可用余量。
- 恢复验收＝备份→隔离恢复→verify→实际查询股票/ETF＋承诺快照重放；具体门以 #656 为准。

## 与现有文档的关系

- [coverage-contract.yaml](coverage-contract.yaml)：测量真源（本批已在 `meta.baseline_calibration` 挂基线指针）。
- [coverage-contract.md](coverage-contract.md)：场景→必需输入视图（本批已校准陈旧末端结论）。
- [pit-time-semantics.md](pit-time-semantics.md)／[consumer-pit-verification.md](consumer-pit-verification.md)：
  时间语义与消费者 PIT 验收，本矩阵不重复。
- 范围外清单（BSE 个股链、rights、CSRC、分钟/Tick、期权、Crypto、期货交易/主连、新平台、
  整盘损坏保护、无证据回溯快照、未授权采购）见 [#658 Out of Scope](https://github.com/cosmos-arc/ditto/issues/658)。
