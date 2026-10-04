# 数据层业界对标与数据源升级：结论汇编

> 2026-10-04。状态：调研与裁决已收官（#421–#425 事实底稿、#426–#429 四张裁决票
> 全部闭环），修复/实施票 #431–#439 已切分待执行。任务地图见
> [Issue #420](https://github.com/cosmos-arc/ditto/issues/420)，本报告为任务票
> [#440](https://github.com/cosmos-arc/ditto/issues/440) 的终点交付。
> 本文是[精简审阅结论](data-layer-review-2026-10.md)的续篇：现状全景与精简决定
> 不在此重复，见该文与[数据层全景图](data-layer-map.md)；本文聚焦本轮新增事实
> （业界对标、三源能力边界、新源选型）与据此作出的裁决。实际拉数入库与代码改造
> 在地图之外，按实施票执行。

## 背景与范围

本轮在 #390 精简收官（#391–#397 交付）之后，回答四个问题：与业界个人级量化数据层
逐维对照后，ditto 剩余的机制哪些是过度设计、哪些是缺口；tushare/fuyao/fred 三源
接入面如何调整；全球指数与宏观大宗数据源如何选型与接入；多资产（含未来美股）
架构预留到什么粒度。

方法链路：五张调研票各产出一份事实底稿（只列事实、不下结论，一手来源优先）——
[#421](https://github.com/cosmos-arc/ditto/issues/421) 业界对照、
[#422](https://github.com/cosmos-arc/ditto/issues/422) Tushare、
[#423](https://github.com/cosmos-arc/ditto/issues/423) fuyao、
[#424](https://github.com/cosmos-arc/ditto/issues/424) FRED/ALFRED、
[#425](https://github.com/cosmos-arc/ditto/issues/425) 新源选型；四张裁决票
（#426–#429）在 grilling＋domain-modeling 会话中逐问裁决，用户逐问作答；
裁决产出修复票 #431–#433 与实施票 #434–#439。既定裁决不重开（sqlite/parquet
双存储划分、instrument_id 身份模型、FRED 保留、fuyao 辅源角色、治理层不复活），
调研若出新事实可在裁决票内当场推翻——本轮确有一处（index_dailybasic 由「暂缓」
改「就接」）。

预算约束：数据源总预算 <2000 元/年；已持有 Tushare 代理 t.xiaodefa.top
（15000 积分）＋ fuyao ＋ FRED（免费 key）。

## 业界对照结论（#421 底稿 → #426 裁决）

### 对照对象与方法

对照七个对象：QuantConnect Lean（引擎＋成品数据生态）、Qlib（自定义 .bin 数据层，
财报 PIT 四列格式业界最深）、Zipline reloaded（bundle 摄取：bcolz＋SQLite 元数据）、
ArcticDB（版本化 DataFrame 存储，自述 bitemporal）、DuckDB+Parquet 个人实践
（CNEquity/astock/usstock/go-fdp 等可核验开源项目）、vn.py datafeed、backtrader
feed；机构级 PIT 约定（Compustat as-first-reported、IBES ANNDATS）仅作边界参照。
方法上一手来源优先（官方文档、仓库源码、样本数据），个人级实践不引用二手评测，
26 条证据索引见 #421 评论。

### 逐维并置（浓缩自 #421 §⑦）

| 维度 | ditto 现状 | 业界点名同类 | 差异事实 |
| --- | --- | --- | --- |
| 复权存储 | 原始价＋复权因子（parquet 侧） | Lean/Qlib/Zipline/CNEquity 同派；vnpy/astock/usstock 为源侧前复权单口径 | 与「原始＋因子」派同构 |
| 证券身份 | instrument＋instrument_mapping 有效区间（1990 下界仅保守） | Lean map_files/Permtick、Zipline equity_symbol_mappings、CNEquity 退市身份 | 均为区间映射/事件表；ditto 同构 |
| 名称/ST 历史 | 历史＋显式未知，无证据日期不回填 | Zipline supplementary_mappings；ST 概念国内项目未见同层 | ditto 深于点名国内项目 |
| 交易日历 | trading_calendar 表（8,401 行） | Lean market-hours、Zipline exchange-calendars、Qlib calendars | vnpy/backtrader/个人实践无独立日历 |
| 增量摄取 | flows{daily,eod,backfill,repair} | Qlib collector＋crontab；astock/usstock/CNEquity cron 增量＋断点续跑 | 同类普遍 |
| 完成证据 | 三阶段 fetch log＋complete_evidence_id 绑定内容寻址快照 | 未见同构；最近似＝CNEquity 失败范围续跑、Zipline timestr 整包、ArcticDB 版本树 | 零同构（三件套之一） |
| 行情 PIT | 行情 parquet 行级 knowledge_date＋cutoff 传播＋T+1 lag | 全部点名对象行情侧均无 knowledge date | 零同构（三件套之一）；财报侧才有同类（Qlib/CNEquity/机构） |
| 财报 PIT | knowledge_date＋ProviderSnapshot 修订观察链（A→B→A 保留） | Qlib 四列＋_next 链、CNEquity strict as_of、ArcticDB 版本＋as_of datetime | ditto 以快照观察链实现修订保留，与 Qlib 同派 |
| fail-closed | cutoff＋就绪检查＋行级过滤组合拒绝 | Qlib 禁止未来报告期、CNEquity strict 可空 | 组合式未见同构 |
| 元数据/行情分库 | metadata.sqlite＋Parquet 年分区 | Zipline（SQLite＋bcolz）、astock（SQLite＋Parquet） | 混合布局有同构先例 |
| 原始载荷留存 | provider_payloads 内容寻址不可变 | 仅 CNEquity staging 层同派 | 少数派做法（三件套之一） |
| 派生布局 | factors/features＋湖投影层 | Qlib calculated features/cache（hash 目录） | Qlib 为唯一显式派生缓存同类 |
| 质检 | DQ 四类检查＋跨源对账报告（#395 口径验收） | Qlib check_data_health、astock R1-R7/D1-D8、CNEquity cne check | 形态一致：离线命令＋非零退出 |
| 监控告警 | 无 | 点名对象均无常驻监控/告警 | 一致 |
| 治理工作流 | 认证/晋级/人工准入已删（#391/#392） | 无点名对象存在数据集认证/晋级工作流 | 删除后与业界形态一致 |

### 零同构三件套与维持理由（#426 裁决）

三件在全部点名对象中零同构：①行情侧行级 knowledge_date＋cutoff 传播＋T+1＋
fail-closed 组合；②三阶段 fetch log＋`complete_evidence_id` 内容寻址完成证据；
③`provider_payloads` 原始载荷留存。裁决全部维持：机构级靠供应商合同
（as-first-reported 分发、WRDS vintage）达成同等保证，个人级自实现是合理替代；
零同构是事实记录，不构成重开理由。provider_payloads 的内容寻址去重使磁盘成本
可控，且是对账/审计/重放的锚。

### 过度设计与缺口（#426 裁决）

- 过度设计新增清单＝**空**：#390 已砍到位，本轮对照未发现新条目。
- 缺口三项成立：跨源对账覆盖面（仅 stock_daily，定序归 #427）；Tushare 接口补缺
  （清单归 #427/#428）；正确性缺陷立修复票 #431/#432/#433（见实施路线）。
- 数据质量监控/告警**不做**：与全部点名对象一致（离线命令＋非零退出即验收），
  地图雾项裁空。

## 三源接入调整定案（#422–#424 底稿 → #427 裁决）

### Tushare 四组接口增补（全接）

基线事实（#422）：已接 44 个 api_name、14 个域适配器，与官方 HTTP 协议一致；
15000 积分档可用全部 2000–6000 分档接口、500 次/分；港美股行情被代理 403
（独立付费体系，非积分可得）。

| 组 | 接口 | 依据（#422 实测） | 口径注意点 |
| --- | --- | --- | --- |
| 商品期货 | fut_daily＋fut_basic | fut_daily 20260930 返回 1075 行全市场合约；1995-04-17 起史 | 金额**万元**；2020-01-01 起成交量单边、此前双边；close 可 null（结算价合约为准）；amount/oi 可 null |
| 业绩事件 | forecast＋express | 两者均 code=0 通过（需 ts_code 或 ann_date） | forecast 净利润区间/上年值**万元**，单边预告上下限可缺失；express 金额一律元；同 period 更正公告追加，须按 ann_date 取最新（与 PIT 设计匹配） |
| 国内宏观 | sf_month＋cn_cpi/cn_ppi 系列 | sf_month code=0 通过，为现有 facade 唯一明确缺失的核心宏观量（社融） | cn_cpi：nt_val 当月指数、nt_yoy/nt_mom 为 %、nt_accu 累计，单次上限 5000 |
| 指数估值 | index_dailybasic | code=0 通过；4000 分档已满足 | 用户裁决推翻「暂缓」推荐，本轮就接（估值因子需求随因子链立时启用） |

港美股行情维持不接（代理 403＋独立付费），随 #429 多资产预留届时再评。

### 对账全序列定序 ①→④

跨源对账从仅 stock_daily 扩展为全序列，按成本递增定序：

1. ①adj_factor 事件流对账（fuyao dump 已在本地，纯 checker 工作，直接完成 ADR
   三项对账的第二项）；
2. ②财务数值交叉对账（fuyao 财务三表端点已验证；只比数值不比披露时间——fuyao
   财务不作披露锚，唯一锚＝Tushare `f_ann_date`）；
3. ③指数近期对账（fuyao 指数仅 ~5 年深度＋无历史成分，只能做行情腿辅源）；
4. ④ETF NAV 对账（fuyao fund/performance 域，5 年窗口）。

对账口径沿用 #395 验收：报告比较数/未匹配/重复键与口径，零交集不得宣称一致。

### fuyao 二源化定案（#423 底稿 → #427 裁决）

fuyao 正式化为「A 股对账＋手动回填二源」：**不做自动降级**——故障回填人工触发、
source snapshot 显式；理由是无 SLA/动态限流，不能承诺 RTO。

能力边界事实（#423，97 端点全集）：A 股 26、公募基金 34、期货 21、期权 6、指数 4、
meta 2、dump 3、资讯 1；明确不含美股/港股/宏观/分钟 K/tick/L2。两个硬边界：

- **REST 大窗口尾部静默截断**（未见于任何官方文档，2026-10-04 实测）：
  `prices/historical` 对大窗口返回最旧优先的前 N 行且 code=0——A 股上限 ~2200 根
  （≈9 年）、指数 ~970 根（≈4 年）。现有用法（单日对账＋dump 回填）恰好避开；
  任何按标的多年 REST 拉取必须分窗分页并对「返回末根日期 ≥ 请求 end − ε」断言
  → 修复票 #433。
- **指数域**：历史仅 ~5 年（>≈5 年窗口静默空返回）、无历史成分股，不能替代
  Tushare index_daily/index_weight 全职能。

红线维持：ETF 原始价主源不给 fuyao（`market/historical` 恒前复权，公开面不存在
ETF 原始价，主源仍为 Tushare fund_daily＋fund_adj）；一致率 ≠ 正确率（与 Tushare
上游独立性未知）。`FUYAO_API_KEY` 配置入口不一致（根 .env 有效而
data_source.env 空值）→ #433 统一。

### FRED 扩充清单与 vintage 语义（#424 底稿 → #427/#428 裁决，修正归 #432）

FRED 注册扩充清单＝#424 候选全集：DHHNGSP/GASREGW（能源现货）、DEX* 汇率族、
DGS1MO–DGS20 全曲线、T10Y3M/T10YIE、SOFR/EFFR、VXNCLS/RVXCLS；实施随 #437
（←#432）。

vintage 语义钉死（#424，官方原文）：

- **vintage 时间戳＝发布日**（release dates excluding no-change releases），
  不是观察日；`realtime_start/end` 是该值「成为最新已知值」的首个/末个发布日。
- **行级 realtime 字段会被请求窗口裁剪**：默认请求（窗口＝今天）返回的每一行
  realtime_start=realtime_end=今天，包括几十年前的观察；推论模型为区间交集
  `max(发布日, 请求起点)` / `min(取代日, 请求终点)`。宽窗口与当前值路径下
  `knowledge_date = realtime_start` 会被污染（偏晚，不泄漏但版本链失真）；
  修正方向＝单日窗口锚点（方案 A，保守正确）或 output_type=3 增量流自建 vintage
  表（方案 B，lineage 精确）——归 #432 落地。
- **生产摄取未接线 realtime 参数**：dataset_registry 走「今天 vintage」，ALFRED
  PIT 路径仅测试在用，宏观表 knowledge_date 实际＝请求日 → #432。
- 月度序列 `date` 为每月 1 日（期初），**join 必须按 knowledge_date asof**，
  按 date join 即前视泄漏；缺失值 "." 已由 cast 正确转 null。
- 修订大户＝GDP（advance/second/third＋年度综合修订）、PAYEMS（当月回改＋年度
  基准）、季调核心 CPI/PCE（每年 2 月全历史重算）；UNRATE 需重标 need_pit=True；
  利率/VIX/EIA 现货/DEX 定盘类基本不回改。
- 3 个死注册序列：GOLDAMGBD228NLBM/SLVPRUSD（2022-01-31 IBA/LBMA 整体下线）、
  VIX9D（序列页 404）——金银现货迁已实现的 Tushare METAL 通道（#432/#434），
  VIX9D 需另寻源（CBOE 直连候选）。中国/日本宏观 OECD MEI 序列已冻结，需新源
  （A 股关心的中国信贷/社融/PMI 本就不在 FRED，走 Tushare cn_* 系列）。

## 新源选型与全球接入设计（#425 底稿 → #428 裁决）

### 免费收口清单（不接付费）

| 域 | 源 | 说明 |
| --- | --- | --- |
| 全球指数（21 只） | Tushare `index_global` | SPX/IXIC/DJI/RUT、HSI/HKTECH/HKAH、FTSE/FCHI/GDAXI/CSX5P、N225/KS11/SENSEX/TWII/CKLSE、AS51/IBOVESPA/RTS/SPTSX、XIN9；6000 分档已满足；vol/amount 大部分缺失、无自定义扩充、无 VIX |
| 汇率＋贵金属现货 | Tushare `fx_daily`（含 METAL 通道 XAU/XAG） | bid 口径、GMT 时区；金银现货自 FRED 死序列迁入此通道 |
| 宏观＋能源现货 | FRED | WTI/Brent/DHHNGSP/GASREGW 在更新；候选扩充见上节 |
| 外盘期货连续日线 | 新浪 GlobalFuturesService（**唯一新增免费源**） | CL 1996 年起 30 年日线；直接 httpx 实现底层端点，不引入 akshare 依赖 |

排除项（#425 实测）：investpy（2022 起死项目）、stooq（2026-10-04 实测 CSV 端点
JS PoW 反爬，程序化通道实质关闭）、Yahoo 官方 API（不存在；yfinance 仅作手工
研究回填，不进生产管线）、Tiingo（指数/大宗覆盖弱，需求不匹配）。

### EODHD 触发式备选

EODHD Historian（$199/年 ≈1430 元，预算内）设为**触发式备选**而非现在订阅：
仅当免费组合实测出现缺口（历史深度不足/稳定性差/覆盖缺失）再启动。其覆盖
（.INDX 指数＋.COMM 商品连续期货＋外汇一体、30+ 年、10 万次/天）是唯一同时补
齐三域的正规 API；该备选定位只覆盖指数/商品/外汇，**不外推到美股股票行情**。

### 新浪源红线

免费公开端点、无 SLA、无授权承诺、会漂移：接入必须容错＋**缺行显式报告，
不得静默**；无发布时间戳，PIT 只能取抓取时刻（与现有 index_global 适配器的
`published_at=available_at` 保守语义一致），全球指数/外盘参考价不得进入需要精确
publication cutoff 的决策链。

### observation date 与原币语义

- 全球指数按**自然日序列（observation date）**存储，不引入多市场交易日历；
  与 A 股日历的对齐在消费端做。存储域沿用已建的 `market/index_global`——适配器
  PIT 模板已建成，差距只是白名单/catalog 注册，非架构问题。多市场日历架构预留
  归 #429（本轮零改动）。
- **原币原单位存储**：全球指数原币、大宗美元；消费端按 `fx_daily` 换算——
  PIT 干净、无隐含换算时点。

### 身份/存储/频率映射（#428 接入设计定案）

| 数据域 | 源 | instrument 身份 | 存储域 | 频率与日历语义 |
| --- | --- | --- | --- | --- |
| 全球指数 | Tushare index_global | `asset_class=index`＋instrument_mapping(source='tushare', source_ticker=SPX/NDX/HSI/…) | `market/index_global` 年分区 | 日线；observation date 自然日 |
| 汇率 | Tushare fx_daily＋FRED DEX* | 按源 ticker 映射（现有 4M 段位模式） | `market/fx` | 日线；消费端换算基准 |
| 大宗现货 | FRED/EIA | 宏观序列注册项 | `macro/commodity` | 日/周/月；knowledge_date 语义随 #432 修正 |
| 外盘期货 | 新浪（新增独立 sina DataSource） | 按源 ticker 映射 instrument（commodity futures） | sina 源侧 | 日线；容错＋缺行显式报告 |
| 国内期货 | Tushare fut_daily | instrument 映射 | `market/commodity` | 日线；口径注意点见 #427 裁决 |

新源注册沿用 `di/sources.py` 按 key 缺省跳过模式（无 key 返回 None）。

## 多资产预留与美股改造点（#429 裁决）

**预留粒度＝零改动**：现状即终态预留——`instrument.asset_class`＋
`instrument_mapping` 有效区间＋分类扩展表、`trading_calendar` 单表多 exchange 行、
复权因子独立数据集模式、Currency/Exchange/时区映射枚举。与 Lean/Zipline 的
多市场抽象（market-hours 数据库＋symbol-properties 全局表）同为「接入时填数据、
不提前建机制」；美股接入时只加数据与源，不改模型；本轮不参数化任何全局常量
（当前无消费者，最小设计）。

「美股时已知改造点」登记（届时执行，本轮不动）：

1. `helpers/pit/policy.py` `KNOWLEDGE_DATE_LAG_DAYS=1` 全局常量 → per-market lag
   （美股收盘 vs 北京时间日界偏移）；
2. `sources/normalization.py` `default_currency=CNY` → per-source currency；
3. `trading_calendar` 填 NYSE/NASDAQ 日历行（表结构不变）；
4. 费率表 per-market（最低佣金 5 元等 A 股费率假设）；
5. 基准 `000300.SH`／指数白名单／大小盘偏好硬编码属产品层假设，随美股重访。

美股数据源＝届时再评：本轮不预算不预定；Tushare 港美股（独立付费 ~1000 元/年级别、
当前代理 403）与 EODHD 美股档届时一起评估。附带清雾：ETF 参考生成链（#395）
维持 A 股指数输入，全球指数接入不改变其数据依赖。

背景：多资产正向信号已有 12 处反向 A 股假设（trading_calendar 默认 SSE、
default_currency=CNY、KNOWLEDGE_DATE_LAG_DAYS=1 全局等）登记在 #420 地图 Notes，
本轮不逐一参数化，改造点清单即其收敛后的执行版。

## 实施路线

裁决产出的票据（图外执行）：

| 票 | 内容 | 依赖 |
| --- | --- | --- |
| [#431](https://github.com/cosmos-arc/ditto/issues/431) | Tushare 分页/频控修复：`_PAGE_SIZE=9000` 超全部已核实官方单次上限（2000–6000）致静默截断；paid profile 超官方 500 次/分 | — |
| [#432](https://github.com/cosmos-arc/ditto/issues/432) | FRED 适配修正：3 死序列移除/迁移（金银→METAL 通道）、UNRATE need_pit 重标、realtime 参数生产接线（vintage 裁剪语义修正）、FRED_API_KEY 补配置 | — |
| [#433](https://github.com/cosmos-arc/ditto/issues/433) | fuyao 分窗防护（尾部截断断言）＋密钥配置入口统一（FUYAO_API_KEY） | — |
| [#434](https://github.com/cosmos-arc/ditto/issues/434) | Tushare 四组接口接入（fut_daily＋fut_basic／forecast＋express／sf_month＋cn_*／index_dailybasic） | ← #431 |
| [#435](https://github.com/cosmos-arc/ditto/issues/435) | index_global 21 指数全量注册（白名单从 5 只扩至 21 只＋catalog） | — |
| [#436](https://github.com/cosmos-arc/ditto/issues/436) | 新浪外盘期货源（独立 sina DataSource，容错＋缺行显式报告） | — |
| [#437](https://github.com/cosmos-arc/ditto/issues/437) | FRED 扩充（#424 候选全集） | ← #432 |
| [#438](https://github.com/cosmos-arc/ditto/issues/438) | 对账①adj_factor 事件流（dump 已在本地） | — |
| [#439](https://github.com/cosmos-arc/ditto/issues/439) | fuyao 二源化（对账＋手动回填角色正式化） | ← #433 |

边界：[#418](https://github.com/cosmos-arc/ditto/issues/418) 因子物化二期独立
先行，本图实施票不重构其依赖的 stock_daily/adj_factor/balance_sheet 地基。
对账②③④（财务/指数/ETF NAV）未单独立票，随 #438 后按成本递增续切。全球指数/
宏观大宗的实际拉数入库在图外。

## 证据指针

本文为结论汇编，事实细节与证据原文见下列 issue 评论（含 #421 的 26 条证据索引
S1–S26 与 #422–#425 的官方文档/探测台账）：

| 议题 | Issue | 结论评论 |
| --- | --- | --- |
| 业界对照事实底稿 | [#421](https://github.com/cosmos-arc/ditto/issues/421) | [resolution](https://github.com/cosmos-arc/ditto/issues/421#issuecomment-5971419622) |
| Tushare 覆盖与接入 | [#422](https://github.com/cosmos-arc/ditto/issues/422) | [resolution](https://github.com/cosmos-arc/ditto/issues/422#issuecomment-5971376947) |
| fuyao 能力全集 | [#423](https://github.com/cosmos-arc/ditto/issues/423) | [resolution](https://github.com/cosmos-arc/ditto/issues/423#issuecomment-5971351266) |
| FRED/ALFRED PIT 语义 | [#424](https://github.com/cosmos-arc/ditto/issues/424) | [resolution](https://github.com/cosmos-arc/ditto/issues/424#issuecomment-5971477372) |
| 新源选型 | [#425](https://github.com/cosmos-arc/ditto/issues/425) | [resolution](https://github.com/cosmos-arc/ditto/issues/425#issuecomment-5971395131) |
| 裁决：过度设计与缺口 | [#426](https://github.com/cosmos-arc/ditto/issues/426) | [裁决](https://github.com/cosmos-arc/ditto/issues/426#issuecomment-5974814764) |
| 裁决：三源接入调整 | [#427](https://github.com/cosmos-arc/ditto/issues/427) | [裁决](https://github.com/cosmos-arc/ditto/issues/427#issuecomment-5974846212) |
| 裁决：新源选型与全球接入 | [#428](https://github.com/cosmos-arc/ditto/issues/428) | [裁决](https://github.com/cosmos-arc/ditto/issues/428#issuecomment-5974862899) |
| 裁决：多资产预留 | [#429](https://github.com/cosmos-arc/ditto/issues/429) | [裁决](https://github.com/cosmos-arc/ditto/issues/429#issuecomment-5974904307) |
| 任务地图 | [#420](https://github.com/cosmos-arc/ditto/issues/420) | 正文（Decisions so-far 与实施票索引） |

本地背景：[数据层全景图](data-layer-map.md)（现状全景与 #391–#396 最终形态）、
[精简审阅结论](data-layer-review-2026-10.md)（D1–D17 决定与 #390 总纲）。
