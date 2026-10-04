# fuyao 与 FRED/ALFRED 接入二次复审

> 范围更新（2026-10-04）：本分册保留研究事实及早期建议；最终实施以[维护者裁决](https://github.com/cosmos-arc/ditto/issues/451#issuecomment-5975629762)为准：灾后只恢复当前可用状态、接受旧实验不可重放；全球参考本轮只展示，完整历史vintage与跨市场策略PIT延后。具体规格见总报告及已修订实施票。

调研日期：2026-10-04。Ditto 阅读基线：`1acf7427090402e5724a52d3066235671c55f264`。fuyao 官方文档检出：`HiThink-Tech/Financial-API@3bca7805a4127ece8d81961917e740d2effac6ec`。

范围：复核「fuyao 源能力全集与角色潜力」「FRED/ALFRED 序列覆盖与 PIT 语义」的评论证据及其实施票。使用官方文档、官方序列页、当前源码；未读取密钥，未调用鉴权数据 API、未写真实数据、未执行实现验证。前轮真实 API 探测保留为前轮证据，本轮不伪称重新实测。

## 结论

三源分工无需推倒：Tushare 负责 A 股/ETF 主数据，fuyao 负责交叉对账和人工历史补齐，FRED 负责宏观、利率及参考序列。但现有实施票有几处会把“有数据”误当成“语义等价”：FRED 日更按观察日查询会漏发布；最新 dump 回填不能反证历史可知；FRED 单值不是 OHLC；伦敦定盘、FXCM 报价、上海金交所价格不是同一基准；fuyao 公司行动事件不是 Tushare 累积复权因子。应先改这些验收口径，再扩注册项。

原调研还有可纠正的事实错误：`CPIAUCSL` 是季调序列；FRED 有日度 `DBAA` 和 `BAA10Y`；全商品指数有正确 ID `PALLFNFINDEXM`/`PALLFNFINDEXQ`。不应因几个猜测 ID 返回 404 就新增供应商。

## 1. FRED：需要修的是摄取与版本语义，而不只是传两个参数

### 1.1 四种时间必须分开

| 概念 | 正确含义 | Ditto 应如何使用 |
|---|---|---|
| Observation date | 数值描述的时期；月度通常标记月初 | 保留为观察期，不直接当信息可知日 |
| 请求 realtime 区间 | 检索哪个历史信息时期，边界均包含 | 与观察日期区间独立，不用 `observation_start` 充当默认 realtime 起点 |
| 真实 revision 生效日 | 该值成为当时最新值的日期 | 保存为版本可见性事实；不能从任意裁剪响应无条件倒推 |
| 抓取时间与快照身份 | 本系统何时拿到哪个响应 | 保留独立 observed_at/source snapshot；不以 vintage 日代替 |

官方明确默认 realtime 区间为今天，采用闭区间。默认响应示例中，1929 年等旧观察的行级 `realtime_start` 与 `realtime_end` 都是请求当天，证明它们不总是“原始发布日”。[FRED realtime 定义](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)、[observations 示例及参数](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)。

ALFRED 的完整实时期输出把 start/end 定义为该修订是最新可用值的首日/末日。`vintagedates` 端点列出有新增或修订的发布日；**用户传入的 `vintage_dates` 可为任意历史日期**，不一定是发布日。因此“vintage 永远等于发布日”过宽。`realtime_end` 是版本最后有效日，也不是 publication cutoff 的同义字段；转换为 Ditto 半开区间时，有限的日粒度结束日需要转换边界，不能直接照搬。[ALFRED 下载格式](https://alfred.stlouisfed.org/help/downloaddata)、[vintagedates 定义](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)。

本轮已证实默认响应裁剪问题；任意宽窗口响应是否严格遵循 `max(原始start,请求start)` 的逐行交集公式、`output_type=3` 的 JSON 实际形态，仍需有 key 的少量只读请求保存脱敏 fixture 确认。不能把前轮未运行的探测写成已证实。

### 1.2 生产日更遗漏发布和修订，比参数缺线更根本

当前调用链：

- `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py:348` 的非 Tushare 路径只调用 `fetch_macro_indicators(ctx.trade_date)`。
- `packages/data/src/ditto_data/sources/fred/fred_source.py:75` 至 `:85` 把 `observation_start=observation_end=trade_date`，即使传了 realtime_end 仍如此。
- `packages/data/src/ditto_data/sources/fred/adapters/macro.py:95` 用观察起点作为 realtime 起点的缺省值，`:105` 随即将多 revision 折叠为每个观察日一行；`:127` 无条件把返回 realtime_start 命名为 knowledge_date。

具体反例：9 月失业率的观察日是 9 月 1 日，10 月发布时日更查 10 月 2 日的观察；该请求不会包含 9 月值。年初回改数年前季调值，同样不会被“只抓今天观察”发现。官方 [UNRATE 页面](https://fred.stlouisfed.org/series/UNRATE) 区分月度观察和发布时间。

最小修法应复用现有宏观长表和摄取管道：区分“按发布日期摄取”和“按观察期查询”；初次回填保留完整 revision，增量按新增/修订日期推进。可优先研究 `output_type=3`，或为小规模注册集采用明确覆盖的观察范围与完整 realtime 语义；**固定短回看并不覆盖年度历史重算，不能单独作为完全性保证**。查询侧再选 as-of 的最新版本，不在历史版本入库前全部 collapse。无需引入消息总线或新的通用事件平台。

发布只有日期而无可靠时刻时，A 股开盘决策不能假设美国同日发布已发生。明确“已完成的发布日之后才可用”或采用有证据的发布时刻；不要把美国日期直接映射成北京时间当日零点。该可用性规则与“数据很少修订”是两个维度。

### 1.3 类型与口径缺陷

| 当前事实 | 影响与调整 |
|---|---|
| `indicators.py:65`、`:75`、`:85`、`:95`、`:127` 的 `_YOY` 注册拉的是 CPI/PCE 指数或 M2 存量；client 未设置转换、macro adapter 直接透传 value | 名称承诺同比、值却是水平。原始序列用明确 level/index 名称；同比若有消费者，再在同一 vintage 宇宙内用当前和 12 个月前值推导。禁止一个源取当前修订、另一个分母取旧修订。FRED 官方转换参数为 `pc1`，不是旧评论里的 `pch1`。 |
| `indicators.py:106` UNRATE 与 `:127` M2SL 的 need_pit=False | UNRATE 必改；M2 季调且可能回改，也应纳入 revision 管理。`need_pit=False` 不得等于无发布滞后。 |
| `indicators.py:21` FrequencyType 仅 daily/monthly/quarterly | 接入 GASREGW 必补 weekly，并保留周周期含义；不伪装日度。 |
| `commodity.py:86` 将 FRED value 复制给 O/H/L/C，`:89` 将日期附会为纽约午夜；`commodity_schemas.py:12` 的源 schema 无知识日 | 单点参考值没有日内高低价、成交价格或该时刻可见的保证。新增序列优先走已有宏观 value 长表；确有展示兼容需要，也必须携带 observation_kind/reference 标签，禁止流入可成交 OHLC 算法。这里证明的是适配层丢失语义，**不据此断言外层没有快照或 PIT 保护**。 |
| `client.py:185` 只取 observations，不检查 count/offset | 开启完整 vintage 历史后可能超过单页，必须按 count 检查完整性或分页；当前小窄窗口未必触发。 |

官方 [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL) 为季调指数，[M2SL](https://fred.stlouisfed.org/series/M2SL) 为季调十亿美元存量。[BLS CPS 方法](https://www.bls.gov/cps/seasonal-adjustment-methodology.htm) 明确年末重算过去五年季调序列，同时说明年内通常不逐月发布对过去月份的这些重算；原评论笼统说 UNRATE“月度当月回改+年度基准”应细化。

### 1.4 死序列与“换源”的边界

FRED 删除 IBA/LBMA 金银属于官方证实的事实，清除注册是必要修复。[2022 年移除公告](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/)。本轮 VIX9D 页面访问失败，结合前轮 404 记录可将它从默认批次隔离；不把工具访问错误单独视作供应商正式下架公告。

“金银迁 METAL（sge_daily 等）”须改写：当前 `packages/data/src/ditto_data/sources/tushare/adapters/metal.py:4`、`:23`、`:106` 实现的是 `fx_daily` 的 `XAUUSD.FXCM/XAGUSD.FXCM`，取 **bid OHLC**，不是 SGE。它和历史 FRED LBMA fixing 共用 `5_000_003/5_000_004`，因此直接替换可能在同身份下混进不同基准。SGE 又是人民币、本地场所和合约的价格，不能当成美元伦敦定盘的直接继任者。

最低要求：独立保留 benchmark/venue/quote side/currency/unit，保留历史源断点；若产品只需要“黄金参考”，在展示/特征映射层明确选择基准。不要在存储层用统一金银别名偷偷拼接。是否需要真正延续 LBMA 定盘，取决于具体研究消费者，未必值得另买源。

另外，生产 `commodity_fetcher.py:107` 已经将金银路由给 Tushare；该票不应重新开发一次“迁移”，而应清除残留 FRED 注册、补身份约束。`commodity_fetcher.py:80` 的 FRED 列表含全部 VIX 映射，单条失效序列可令整个 FRED 批次抛错，随后 `:95` 捕获异常继续返回金银。当前 frame 不保留 source 列，`coordinator.py:135` 与 `post_ingest.py:248` 又传递单一配置源名：**混源结果是否错记源、只剩金银的批次是否仍标 COMPLETE，需要端到端核实**。把“一腿失败”加入本票及商品参考类型票的验收，不仅测试两个源均成功的 concat；本轮未运行这一链路，不能宣告已发生错误落库。

## 2. 候选序列：先纠正 ID 与用途，再讨论增加供应商

「FRED 序列扩充注册与摄取」正文说“候选全集”，但只列部分族；应改为明确 series ID 白名单与用途，不能把 `DEX*`、`DGS1MO~DGS20` 当可执行规格。

| 类别 | 建议与边界 | 官方核对 |
|---|---|---|
| 能源 | DHHNGSP 可作天然气现货宏观参考；GASREGW 是周频零售含税汽油调查，不是期货或日度交易价 | [DHHNGSP](https://fred.stlouisfed.org/series/DHHNGSP)、[GASREGW](https://fred.stlouisfed.org/series/GASREGW) |
| 利率 | 先补实际使用的短端 DGS1MO/DGS3MO、T10Y3M/T10YIE、SOFR/EFFR；缺少具体消费者时无须补齐每个期限 | [SOFR](https://fred.stlouisfed.org/series/SOFR) |
| 汇率 | DEXCHUS、DEXJPUS、DEXUSEU、DEXUSUK 可作官方宏观参考；H.10 周发布的每日观测不能当实时 FXCM bid/ask 二源互换，方向也各异 | [H.10](https://www.federalreserve.gov/releases/h10/)、[DEXCHUS](https://fred.stlouisfed.org/series/DEXCHUS) |
| 信用 | “Baa 无日度”不成立：DBAA 与 BAA10Y 日度序列当前可读。作为信用条件代理可避免急接新源，但 Moody's 收益率利差**不是** ICE OAS 同一指标 | [DBAA](https://fred.stlouisfed.org/series/DBAA)、[BAA10Y](https://fred.stlouisfed.org/series/BAA10Y) |
| ICE OAS | 三年窗口限制官方仍明确。要长期 OAS 原口径才需要原提供商，不能说所有长期信用条件数据都必须新源 | [BAMLC0A0CM](https://fred.stlouisfed.org/series/BAMLC0A0CM) |
| 全球全商品 | 原调查的 PALLFNF/PALLFIN 不存在不代表能力缺失：正确月度 PALLFNFINDEXM 和季度 PALLFNFINDEXQ 可读；本轮月度至 2026-07。足以成为先评估的候选，未来更新与 API vintage 仍待验 | [月度全商品指数](https://fred.stlouisfed.org/series/PALLFNFINDEXM)、[季度全商品指数](https://fred.stlouisfed.org/series/PALLFNFINDEXQ) |
| 波动率 | VIXCLS 保留；VXNCLS/RVXCLS 仅当美股科技/小盘风险有消费者再注册；不因 endpoint 可接就全量扩充 | 前轮官方页/CSV 证据，本轮未重新探测这两条 |
| 非美宏观 | 逐序列看最后观察、更新时间及原提供商状态；Next Release Not Available 本身不能证明死亡。本轮未重做全部 OECD 序列探测 | 前轮证据应逐项保留，不扩大成“所有 OECD 已停” |

总体不建议现在额外建设 IMF/EIA/Fed 直连适配器：已有 FRED 可复用的序列应先用正确 ID 接入。仅当更新时效、授权或明确缺失覆盖妨碍当前消费者，再增加原始源。FRED 不是未来美股交易主源；美股行情、公司行动、退市历史应届时单独选型。

## 3. fuyao：保留轻量二源，分清 REST 与 dump

### 3.1 官方确认的能力边界

- 官方 A 股 REST 为单标的、最长十年请求窗口，默认 `adjust=forward`；Ditto 显式 `none` 正确。volume 为股、turnover 为货币金额，当前 `source.py:105`、`:106` 的 **除以 100/1000** 才是内部手/千元归一。旧评论“×100/×1000”不应复制成实现验收。[A 股价格契约](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/a-share/prices.md)。
- ETF 历史固定前复权且最长五年，`adjust=null` 并不表示原始价。继续排除原始价管道，快照展示与 NAV 对账可以按需考虑。[基金行情](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/fund/fund-market.md)。
- 指数历史官方写十年窗口、无 offset；前轮约五年覆盖和长窗口空返回是特定样本的实测观察，不是官方 SLA。新消费者应保存可核查响应并检查覆盖，不把 970/2186 固化为永久行上限。[指数契约](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/index/a-share-index.md)。
- 公开面没有美股、港股行情及宏观，不能将它升级为全球来源。无累计请求次数限制不等于不限流；有动态限流，不承诺 QPS。[官方 README](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/README.md)。

### 3.2 截断防护应检测完整性，不能机械要求“非空且到 end”

`source.py:162` 的单标的 REST 没有分窗或响应边界核验，缺陷真实；`source.py:238` 对账只用单日，当前风险较小。

不过“空返回显式报错”“末根日期必须贴近 end”会误报周末、休市、停牌、上市前、退市后、请求到将来等情况。最小正确做法是：明确请求的有效交易范围，分成有界窗口，检查标的/区间/重复键和可期待覆盖；不能证明完整时返回 incomplete/not-comparable，不能静默标成功。分窗会造成窗口首条 pre_close 丢失，必须合并、去重、排序后统一 shift，或多带一条前序观察。无需单独建设分页框架。

### 3.3 人工回填不需要先完成所有 REST 分窗

官方 dump 明确推荐全市场批量获取，`daily-k` 为约十年未复权历史，`daily-k-10d` 用于近期增量，落后超过七个交易日建议全量刷新以留重叠。dump 的核心验收是文件可读、字段口径、日期/证券覆盖、重复与回填区间；它不使用 REST 多年价格窗口。因此「fuyao 手动回填二源正式化」以“回填多年所以必须等待 REST 分窗”作硬依赖，理由不成立。配置/身份/回填管道可依赖，REST 修复可并行。[官方 dump 文档](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/market-dumps.md)。

现有 `apps/backend/src/ditto_apps/cli/commands/fuyao.py:83` 已有 dump 下载命令；新增回填应复用它的能力和正常 DQ/写入链路，避免第二套存储引擎。`source.py:197` 当前读完整文件再变换；若十年多百万行确有内存压力，可复用 Polars lazy scan 在投影/日期过滤后 collect，不先引入分布式批处理。

人工触发不等于自动具备安全等价。至少保证：

1. 明确目标日期、股票范围和是否填缺；有 Tushare 主源事实时不悄悄覆盖，由源选择规则决定消费者读哪一份。
2. 下载事实、请求范围、内容 hash、schema/单位、采集时间与 ProviderSnapshot 对应；同一输入重复运行幂等，坏文件不发布游标。
3. 验证 dump 的 `currency=CNY`、`interval=1d`、`adjusted=none`，再删除这些常量列。当前 `daily_k_frame` 选择 BAR_COLUMNS 前未验证，不能仅凭函数注释保证口径。
4. 身份用证券主数据/来源映射。`source.py:74` 裸码前缀猜后缀且默认 SZ，和官方“不要猜交易所后缀”相反，未来新代码段会误映射。[通用契约](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/README.md)。
5. `source.py:220` 的 `knowledge_date=trade_date+1天` 是日线可用性的约定，不是此修订实际首次发布证据。今天下载的历史修正价不能仅靠 T+1 冒充当时已知；须区分重建历史与实有历史快照，明确策略回放允许哪一类。
6. `source.py:215` 的 pre_close 是上一根原始收盘，与除权日参考价不同；不能因填入同名 STOCK_DAILY 列就宣告跨源完全等价。上下文不足的首条应保持未知，不补造。

### 3.4 复权对账比较事件或因子相对变化

官方 `adjustment-factors` dump 是分红、送股、配股事件，含 `dividend_per_share`、`per_share_bonus`、`allotment_ratio`、`allotment_price`，不是每日累积 `adj_factor`。REST 事件接口列出的字段还少于 dump，不能假设两者同构。[dump 契约](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/market-dumps.md)、[REST 事件契约](https://github.com/HiThink-Tech/Financial-API/blob/3bca7805a4127ece8d81961917e740d2effac6ec/docs/api/a-share/corporate-actions-adjustment-factors.md)。

「跨源对账扩展路线（本票交付①adj_factor）」应先定义：比较公司行动事件本身，还是按同一规则由事件推导除权变动，再比较 Tushare 因子的相对变化。不要直接比较两边绝对因子（基期可能不同），不要把股/元单位换算搬到无量纲因子。现金分红、送股、配股、复合事件及缺前价各需有明确可比性判定；缺事件字段就是 not_comparable，零交集不是成功。

## 4. 实施票的最小修改与验收

| 实施票 | 应修改的规格 | 最小有意义验收 |
|---|---|---|
| [FRED 适配修正——死序列清理、金银迁 METAL、UNRATE need_pit、realtime 生产接线](https://github.com/cosmos-arc/ditto/issues/432) | 补发布日驱动摄取、修订保留/分页、裁剪响应与原始知识日的区别；修正 YOY 名称和 M2；金银明确 FXCM/SGE/LBMA 身份而非直接换源 | 经过真实 production factory 的固定响应场景：发布日抓到前月观察，年度修订不丢，发布前/后查询各返回正确 vintage；含裁剪、缺值、跨时区可见性；新旧金价不混同 |
| [fuyao 大窗口拉取静默截断防护＋数据源密钥配置入口统一](https://github.com/cosmos-arc/ditto/issues/433) | 防护改为交易范围完整性，允许合法空窗；配置核对有效 DI 注入，不由某文件空值断言缺 key | 截断失败、周末/停牌/上市前合法空窗、分窗边界不丢 pre_close；缺 key 明确诊断，配置来源可定位但不输出值 |
| [FRED 序列扩充注册与摄取（候选全集）](https://github.com/cosmos-arc/ditto/issues/437) | 把族通配改为白名单/频率/单位/用途；纠正 DBAA 与全商品 ID；避免“全集”变无消费者范围膨胀 | 每种实际频率至少一条摄取路径；weekly 不降格 daily，`.` 保留缺失；H.10 不提前到 observation 当天；衍生同比两个输入来自相同 as-of |
| [跨源对账扩展路线（本票交付①adj_factor）](https://github.com/cosmos-arc/ditto/issues/438) | 定义事件↔因子相对变化规则、基期归一、缺事件字段和权利类型 | 一个复合除权例、一个基期不同但相对变化相同例、一个缺前价或缺配股字段例；报告不能给错误“匹配” |
| [fuyao 手动回填二源正式化](https://github.com/cosmos-arc/ditto/issues/439) | 解除 dump 对 REST 分窗的伪依赖；增加填缺/不覆盖主源、实际观测身份、历史重建可信级别和文件契约 | dry-run 无写入；重跑幂等；坏 adjusted/currency/重复键被拒；源选择可追溯；未来修订哨兵不能通过假 T+1 泄入旧回放 |

上述验收应复用既有测试框架和 fixture，优先贯穿入口/查询消费者的一组小场景；不需要为每个新增 series 复制一套测试类。

## 5. 未知与边界

- 未重新调用鉴权 API；FRED 宽窗口原始行字段、JSON 增量格式、fuyao 截断可重复性需实施前最小脱敏 fixture 取证。
- 本轮未检查真实 key 值或运行账户权限。`DataSourceSettings` 与 DI 已有入口（`config/data_source.py:30`，`di/sources.py:85`、`:96`）；“某 env 文件为空”不能独自证明最终运行环境缺 key。也不能把前轮根 `.env` 的存在当长期配置规范。
- 未证明 fuyao 上游与 Tushare 数据生产链独立；一致率只能作二源一致性证据。
- 未完成全量历史数据质量审计或恢复演练；报告评价代码/契约和实施规格，不宣告生产数据已经可信。
- 仅创建本研究文件，未修改实现、远端票、生产配置或数据；没有运行实现测试，不能将文档完成等同于修复完成。
