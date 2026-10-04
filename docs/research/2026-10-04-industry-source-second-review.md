# 数据层二次审阅：业界对标、全球与商品补源

> 范围更新（2026-10-04）：本分册保留研究事实及早期建议；最终实施以[维护者裁决](https://github.com/cosmos-arc/ditto/issues/451#issuecomment-5975629762)为准：灾后只恢复当前可用状态、接受旧实验不可重放；全球参考本轮只展示，完整历史vintage与跨市场策略PIT延后。具体规格见总报告及已修订实施票。

调研日期：2026-10-04。本文是研究结论与待裁决建议，不改实现，不更改既有 Issue 的状态或用户已作出的决定。范围为 A 股个股、ETF、指数主线，以及全球指数、宏观、大宗参考数据；美股只列未来重新选型的条件。预算沿用本轮 `<2000 元/年`，不能把该数额未经确认解释为新增预算。

本地依据：[数据层全景图](../data/data-layer-map.md)的“最终形态”与“同日审阅补充”，以及 [业界个人级量化数据层标杆对照](https://github.com/cosmos-arc/ditto/issues/421)、[全球指数与大宗候选数据源选型](https://github.com/cosmos-arc/ditto/issues/425)、[新数据源选型与全球指数/宏观大宗接入设计](https://github.com/cosmos-arc/ditto/issues/428)、[多资产扩展架构预留粒度](https://github.com/cosmos-arc/ditto/issues/429)、[新浪外盘期货 DataSource 接入](https://github.com/cosmos-arc/ditto/issues/436)的当日正文与评论。全景图下半部分明确是精简前历史观察，不能再把旧表数、行数与治理机制当当前实现。

## 结论

当前方向可以保留：本地 SQLite 元数据与簿记、Parquet 业务数据、Polars 计算、原始载荷与最小快照证据，足以支撑个人日频量化。没有证据支持为了“业界先进”重新加入 DuckDB 持久化第三轨、ArcticDB、通用数据治理平台或实时总线。

但前轮用来证明简化合理性的若干外部事实过度概括，需要纠正。**行情的时间可见性、历史版本、真实合约与参考序列区分是必要复杂度；独立审批工作流和无人使用的注册表才是另一类成本。**不能用“业界没同构实现”证明某项正确性保障没有价值。

补源建议仍是先用已接源、不开新采购。新增新浪应收窄为“方法与历史覆盖已逐品种登记的参考序列”，不能仅凭成功返回 CL 就宣布全部外盘连续期货可用于信号。EODHD 的 `$199/年` 价格属实，但“这一档覆盖 `.COMM` 连续期货、可统一兜底商品”的证据不成立：当前官方商品 API 是 FRED 序列转发，不是连续期货服务。[EODHD 定价](https://eodhd.com/pricing)、[EODHD 商品 API](https://eodhd.com/financial-apis/commodities-api-historical-prices-for-oil-gas-metals-agriculture-beta)。

## 一、先修正业界对标的证据边界

| 前轮表述 | 本轮可核实事实 | 对 Ditto 的含义 |
| --- | --- | --- |
| “行情侧无 PIT / knowledge date 概念” | LEAN 以 `EndTime` 和 time frontier 控制行情事件进入算法的时间，多个时区按各市场收盘交付日线。这与完整供应商修订历史不同，但明确属于行情防前视语义。[Time slices](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/timeslices)、[Periods](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods) | 应拆成“事件完成后可见”“供应商首次公开”“本地观察版本”三个问题；不因 bar 没有同名列而删除可见性检查。 |
| “Qlib 行情无 PIT，财报完整 as-of” | Qlib 的文件 PIT 确实记录公告日、报告期、值与同报告期后继记录；官方同时明确当前该数据库为季度/年度因子设计。文档证明查询机制，不证明任何第三方输入具有完整无遗漏历史。[Qlib PIT](https://qlib.readthedocs.io/en/latest/advanced/PIT.html) | 可复用公告期与版本分离思想，不能把支持 PIT 查询等同“来源全部严格 PIT”。 |
| “Zipline 无 PIT 语义” | Zipline `--bundle-timestamp` 可选择不晚于指定时间的摄取包；这是本地数据版本的复现。它不证明包内每条财报或行情在回测历史日已公开。[Data bundles](https://zipline.ml4trading.io/bundles.html) | 类比 Ditto 快照回放有意义；应称“版本级复现”，而非“无时间语义”或“已完整历史 PIT”。 |
| “带完成证据的三阶段账本业界零同构” | 这些引擎与存储产品承担不同职责；查到几个不同实现，只能证明样本内未发现完全一样的工作流。ArcticDB 的版本与 snapshot、Zipline 摄取包已有相近的复现目标。[ArcticDB Library](https://docs.arcticdb.io/6.20.0/api/library/)、[Data bundles](https://zipline.ml4trading.io/bundles.html) | 判断 fetch log 的依据应是崩溃恢复、部分成功、精确版本读取是否需要，不能用命名或结构不相同作删除理由。 |
| “没有数据监控 / 无常驻监控” | 当前 LEAN `DataMonitor` 记录成功/失败数据请求、生成缺失文件报告，并启动后台线程统计请求频率；QuantConnect 也有官方数据问题闭环。[DataMonitor 源码](https://github.com/QuantConnect/Lean/blob/705b9551be1aaa821c7f77896a7eb8fcd07b92ee/Common/Data/DataMonitor.cs)、[Data Issues](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/data-issues) | 不能外推为“个人量化不需要监控”；也不能倒过来据此要求 Ditto 部署独立全天候监控平台。每日任务的失败、缺口、陈旧数据报告已经能覆盖当前需求。 |
| “美股时只加数据与源、不改模型，与 LEAN/Zipline 同构” | LEAN 的永久 Symbol、市场区分和时点 ticker 是引擎语义；期货连续序列另有映射、归一化和真实合约。并非仅有一个 asset_class 列就等价。[Security identifiers](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/security-identifiers)、[Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/requesting-data/universes) | 可以决定现在不为未来美股改代码；不应承诺未来无需改模型。已经进入本轮的全球指数与国内/外盘期货，也不是“假想未来消费者”。 |

本轮源码读取对应 LEAN `705b9551be1aaa821c7f77896a7eb8fcd07b92ee`。上表修正的是论据，不自动撤销已确认的简化决定。

## 二、个人系统值得借鉴什么

### 保留：最小但闭合的数据事实链

建议维持“请求范围 → 原始响应/快照 → 标准化数据 → 完成证据 → 查询输入版本”的闭环。每段都应有当前消费者，而非另建认证、晋级、许可、人工审批对象。现有全景图已说明删除治理层后，快照存在、范围匹配、payload 留存、精确完成绑定仍由消费者使用；这些属于正确性，不是被删除工作流的附属物。[本地全景图](../data/data-layer-map.md)。

与其模仿机构全部双时态数据库，不如明确三种能力：

1. **行情可见性**：bar 完成后才可用于决策，时区与 session/date 不能混用。
2. **公开版本回放**：财报、宏观有版本证据时，按其发布时间与版本查询。
3. **本地观察回放**：只有本地快照时，保证从首次观察起可以重放；今天下载的旧日数据不因此成为“当时已知的原版本”。

这三个能力不必各造一套状态机。复用已有时间字段、快照和查询入口，并为无法证实的历史范围给出明确缺失即可。LEAN 的事件时间、Qlib 的财报 PIT、Zipline/ArcticDB 的版本回放分别展示了不同层次，不能混称同一种“PIT”。[LEAN 时间边界](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/timeslices)、[Qlib PIT](https://qlib.readthedocs.io/en/latest/advanced/PIT.html)、[Zipline bundles](https://zipline.ml4trading.io/bundles.html)。

### 保留存储，按实际瓶颈优化

DuckDB 可以直接读 Parquet，并做列投影与过滤下推，不需要先把全部文件复制入新数据库。[DuckDB Parquet](https://duckdb.org/docs/current/data/parquet/overview)。因此，删除没有真实消费者的持久化 DuckDB 轨是合理的；未来若出现复杂只读 SQL 或跨文件扫描瓶颈，可先测量直接查询，不能将“移除了第三份数据”变成“永远禁止 DuckDB 工具”。

ArcticDB 的版本化 DataFrame 能力值得参考，但当前已经有快照、Parquet 与 SQLite，直接引入会带来另一套版本管理和查询边界。除非现有实现的写入规模、并发与版本管理负担经测量成为瓶颈，否则不增加它。[ArcticDB Library](https://docs.arcticdb.io/6.20.0/api/library/)。

年分区本身不是问题。应优先核实热路径是否按日期/证券裁剪、是否反复读取同文件、是否摄取一次重写过大分区、是否产生过多小文件，再决定行组、分区粒度与缓存。本文没有跑 Ditto 基准测试，因此不宣称当前性能已足够，也不给无实测依据的分区迁移方案。

### 补齐数据产品语义，暂不建设通用多资产框架

建议一个轻量数据集/序列描述即可明确：`series_kind`、供应商代码、内部身份、币种、单位、频率、日期含义、时区、已知发布规则、价格口径、来源版本。优先使用现有 catalog/模型能力，只有当前字段表达不了已接数据时才补字段。

- 指数点位、价格指数、总回报指数不能混算；“原币原单位”中的指数通常单位是点，不是把点位当成可直接按 FX 换算的现金价格。
- 现货参考、合约行情、主力/近月连续、总回报商品指数不能共享一个未注明口径的 `close` 语义。
- 股票原始价、复权因子/公司行动应分开；ETF 的 NAV 与二级市场成交价应分开。
- 不要求现在建立全市场交易日历，但全球序列至少保留源日期与实际观察 UTC 时间。若以历史当地收盘时间决定信号可见性，节假日、半日市、DST 就必须有可信规则；纯日期加固定偏移不是完整证明。LEAN 将多市场 bar 按各自完成时间送入统一时钟，值得借鉴这一语义。[LEAN Periods](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/time-modeling/periods)。

自然日序列可用于存储全球参考数据；不能把周末自动补成新观察，更不能在中国上午使用同一个日期标签对应的美国当日晚间收盘。消费者按 `available_at <= decision_time` 做向后 as-of 对齐，保留原始 observation date 和陈旧程度，是当前场景足够小的方案。单靠 `shift(1)` 或全局 lag 常量不能覆盖这些情形；也无需因此提前实现美股交易账本。

## 三、新浪外盘：本次直接只读探测与边界

2026-10-04 对新浪 `GlobalFuturesService.getGlobalFuturesDailyKLine` 各请求一次 CL、GC、ZSD，匿名读取，没有登录、购买或写入。AKShare 官方实现仅构造此 URL 并解开 JSONP，未赋予数据额外质量与滚动方法保证。[AKShare 源码](https://github.com/akfamily/akshare/blob/fac1e50ebf9b907960d6aab4c3df658559689f39/akshare/futures/futures_foreign.py)。

| symbol | 本次行数 | 第一行日期 | 最后一行日期 | 最后记录的辅助字段 |
| --- | ---: | --- | --- | --- |
| CL | 7689 | 1996-10-04 | 2026-10-02 | volume=0、position=0、settlement=0 |
| GC | 2589 | 2016-10-04 | 2026-10-02 | volume=0、position=0、settlement=0 |
| ZSD | 2537 | 2016-10-04 | 2026-10-02 | volume=13404、position=0，**没有 settlement 字段** |

探测 URL：[CL](https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_S2026_10_4=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=CL&source=web)、[GC](https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_S2026_10_4=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=GC&source=web)、[ZSD](https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_S2026_10_4=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=ZSD&source=web)。这些 URL 返回的是可变当前视图；表格记录本次观察，不承诺未来相同。未保存生产数据、未验证逐行真实性与交易所一致性。

**直接影响**：

- CL 的 30 年历史不能外推到 GC；“CL/GC 等 1996 起”应改为逐品种覆盖验收。
- 响应出现 `settlement` 字段不证明提供了真实结算价；CL/GC 本次首尾都是零。不能把零当成有效结算、成交量或持仓，也不能未经源契约把全部零一律转 null；先保存原值并把未知/占位语义显式化，消费者不得依赖未证实字段。
- 所阅接口与适配器没有交付逐日映射合约、滚动日、连续构造方法或回溯调整规则。不能据此宣称它等价于“方法公开、可重现的连续期货数据库”。
- 历史深度刚好落在探测日的 10 年/30 年前，值得登记潜在滚动窗口风险；本次一次取样不足以证明具体截断规则。
- 接口匿名，照搬“无 API key 则跳过”会让新浪源无法启用；沿用已有显式启用设置即可，不应为匿名 API 发明假 key。

建议保留新浪源实施方向，但将验收从“CL 回填成功”提高到“逐品种口径可说明”：固定小白名单、真实覆盖报告、字段缺失/占位测试、重复日期/乱序/响应截断、HTTP 失败显式报告、查询 cutoff、准确来源身份。先用于图表与宏观环境参考；只有连续方法与跨日信号行为通过样本核对后，才把对应派生信号接入自动研究/决策。这里限制的是不明方法序列的用途，不是要求复制机构期货平台。

## 四、现货、结算、连续序列应怎样区分

| 对象 | 表达的事实 | 可以做什么 | 不能自动推导什么 |
| --- | --- | --- | --- |
| EIA/FRED 现货序列 | 指定地点、规格与单位的现货参考价格 | 宏观环境、产业成本、供需研究 | 期货可成交价、连续合约收益 |
| 真实期货合约日线 | 指定合约期限的成交区间与价格 | 单合约研究；有合约属性和执行模型后模拟交易 | 无换月成本的永久持有价格 |
| 每日结算价 | 交易所按规则计算的结算基准 | 合约逐日盯市、保证金盈亏核算 | 最后一笔成交价、任何时刻可成交价 |
| 连续/主力序列 | 不同到期合约按某规则拼接的研究序列 | 指标预热与明确口径的趋势研究 | 可直接下单资产、未经处理的真实投资收益 |
| 商品参考/总回报指数 | 由指数方法规定的篮子与收益口径 | 环境参考或基准对比 | 某个商品的现货价格或单合约回报 |

事实依据：CME 明确分别列出 Last 与 Settle，且其说明展示结算与未成交情形；LEAN 明确连续合约不可直接交易，订单使用映射到的真实合约；EIA 石油 API 明确是 spot price 及各自物理单位。[CME About Settlements](https://www.cmegroup.com/trading/about-settlements.html)、[LEAN Futures universes](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/requesting-data/universes)、[EIA 石油现货目录](https://www.eia.gov/opendata/browser/petroleum/pri/spt?data=value%3B&facets=series%3B&frequency=daily&series=RWTC%3B&sortColumn=period%3B&sortDirection=desc%3B)。

建议现阶段不自建连续合约引擎。如果真实需要国内期货趋势研究，先把 Tushare 的真实合约、主力映射与日线方法查清；若只是用油价解释 A 股行业，FRED/EIA 现货可能已足够，不必为了“覆盖大宗”新增所有期货品种。对于已决定接入新浪的工作，不能用现货替代其用途后宣称同一需求已完成。

## 五、EODHD：价格正确，商品能力与采购理由需要改写

本轮官方定价核实：Historian/EOD Historical All-World 年付 `$199`，含全球股票、ETF、Forex、指数等 EOD；历史指数成分是另外收费的 marketplace 产品。定价不能单独证明每个目标 ticker、历史区间和账户权益；总预算还须扣除现有源成本、税费与实际换汇。[官方定价](https://eodhd.com/pricing)。

当前官方 `Commodities API` 文档列出 23 个 FRED 来源序列，字段是日期和值及频率/单位元数据。能源部分为现货参考，金属/农产品主要为月度；文档没有把它描述为 `.COMM` 的 CL/GC 连续期货。[商品 API](https://eodhd.com/financial-apis/commodities-api-historical-prices-for-oil-gas-metals-agriculture-beta)。

本轮检索官方 API 目录、定价与 OpenAPI 仓库，未核实前轮 `CL.COMM`、相应连续合约方法、套餐权利与试样响应。因此结论是“该连续期货兜底方案尚未成立”，不是声称厂家绝无其他未公开产品。[API 目录](https://eodhd.com/financial-apis/)、[官方 OpenAPI](https://github.com/EodHistoricalData/eodhd-openapi)。

建议改写已有触发条件：

- 全球指数或未来美股日线出现明确缺口时，EODHD 可以进入候选试样比较。
- 不把 EODHD 的 FRED 转发算作独立大宗辅源；它不能帮助验证 FRED 上游数值错误。
- 外盘连续期货缺口触发时，重新核定真正提供所需合约/滚动方法的产品；不直接执行预设的 `$199` 购买。
- 采购前确认目标符号、价格口径、历史深度、退市与公司行动、留存权利和总年费。不是另建审批流，只是让一次采购与实际缺口对应。

## 六、是否还要加源

| 当前需求 | 本轮建议 | 何时重访 |
| --- | --- | --- |
| A 股个股、ETF 与中国指数 | 继续优先用 Tushare 兼容通路；fuyao 在同口径字段上交叉核验 | 具体历史/PIT/ETF 字段缺口无法由当前源和定点原件核实解决时 |
| 全球指数与 FX | 完成已经决定的 Tushare 白名单及落地；本轮不再并行加一套同覆盖收费 API | 所需指数、历史深度、日更新或价格口径实测不满足时 |
| 宏观与能源现货 | 先完善 FRED 的序列与版本语义 | 若需要 FRED 未覆盖的能源供需细分，评估免费 EIA v2 原始接口；不要复制已满足的 FRED 序列 [EIA API](https://www.eia.gov/opendata/documentation.php) |
| 外盘期货参考 | 新浪仅按小白名单与上述用途边界接入 | 真实需要单合约研究、滚动收益、结算/持仓质量时，另作期货源选型 |
| 未来美股 | 暂不采购。将 Alpaca 等列为当时的样本对照，不预定赢家 | 策略频率、历史证券池、公司行为、SIP/IEX 与延迟要求明确后 |

Alpaca 官方目前区分免费 Basic（实时股票仅 IEX、历史自 2016、有最近 15 分钟限制）和 `$99/月` 的全市场实时套餐。它说明“美股免费数据”必须按 feed、历史与延迟比较，不能将 IEX 成交量误认为全市场；`$99/月` 显然不应进入本轮预算内采购建议。日频用途可届时核对历史 SIP 权利与账户可用性，本文未开户或验证授权。[Alpaca Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api)。

不为未来美股一次性加入 Polygon/Massive、Alpaca、EODHD、FMP、Tiingo 多适配器；选择多家候选用于当时研究，不等于现在把它们全建进系统。

## 七、对既有决定的最小修订建议

1. **[业界个人级量化数据层标杆对照](https://github.com/cosmos-arc/ditto/issues/421)**：将“行情无 PIT、无监控、业界零同构”改为明确样本和层次的描述；补 LEAN time frontier/DataMonitor 与版本回放边界。
2. **[全球指数与大宗候选数据源选型](https://github.com/cosmos-arc/ditto/issues/425)**：撤回“EODHD $199 统一覆盖连续商品期货”的已证实口径；修正独立辅源、GC 历史深度与 settlement 字段解释。
3. **[新数据源选型与全球指数/宏观大宗接入设计](https://github.com/cosmos-arc/ditto/issues/428)**：维持不采购、原始单位和先有源落地；补参考序列用途边界与跨时区 as-of 消费合同。将“全球指数原币”精确化为指数点位及必要币种元数据。
4. **[多资产扩展架构预留粒度](https://github.com/cosmos-arc/ditto/issues/429)**：维持不预建美股系统；把“未来只加数据不改模型”改为“当前保留基础扩展点，接入时验证模型”。本轮全球数据的时区/单位/可见性属于当下正确性。
5. **[新浪外盘期货 DataSource 接入](https://github.com/cosmos-arc/ditto/issues/436)**：按上文补足字段质量、品种覆盖、匿名启用、合约/连续参考区分与消费限制；CL 成功仅是接口连通证据。

以上是供地图所有者裁决的具体修改点，不在本文自动修改或重开票据。无需因此再建一层新治理；将修正纳入原实施票的合同与验收即可。

## 验证边界

已完成官方文档/源码复查，以及新浪三品种单次匿名只读探测。没有运行 Ditto 功能测试、基准测试、持续日更、付费接口或真实交易；没有证明新浪历史数据真实无错、连续方法公开或商业源账户权益。价格和在线文档会变化，购买或实施时仍应核对精确目标。本文对库/引擎的比较不外推成对全部个人量化实践的统计结论。
