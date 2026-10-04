# Tushare 数据层二次核查：接口契约、时间语义与待实施票据

> 范围更新（2026-10-04）：本分册保留研究事实及早期建议；最终实施以[维护者裁决](https://github.com/cosmos-arc/ditto/issues/451#issuecomment-5975629762)为准：灾后只恢复当前可用状态、接受旧实验不可重放；全球参考本轮只展示，完整历史vintage与跨市场策略PIT延后。具体规格见总报告及已修订实施票。

日期：2026-10-04。代码基线：`1acf7427090402e5724a52d3066235671c55f264`。范围：当前 Tushare adapter/client、既有数据源复核文档，以及 [Tushare 能力调研](https://github.com/cosmos-arc/ditto/issues/422)、[分页与频控修复](https://github.com/cosmos-arc/ditto/issues/431)、[四组接口增补](https://github.com/cosmos-arc/ditto/issues/434)、[全球指数全量注册与摄取](https://github.com/cosmos-arc/ditto/issues/435)、[跨源对账扩展路线](https://github.com/cosmos-arc/ditto/issues/438) 的正文与评论。

本次联网读取官方文档；未读取 token、环境凭据、Keychain，未调用付费数据 API，未修改实现或远端 Issue。既有调研评论中的成功探测属于此前执行者的证据，本次没有复现其账户权限、代理完整性或真实回填。文中“已验证”指官方文本、代码或明确列出的离线实验；“建议/推断”不表示已交付。

## 结论

保留现有 HTTP → Polars → 本地数据产品的路线。个人日频系统不需要为 Tushare 新建 SDK 包装平台、通用供应商能力引擎或分布式采集服务。优先级应从“增加接口数量”改成“已有与新增接口的值、单位、身份、可知时间正确”。

本轮计划方向合理，但存在五项必须改清的规格：分页页宽不能统一假设 2000；宏观接口已经接了一部分而且共享请求参数与官方月度参数不符；预告和快报不能统一当成万元；全球指数名单不含 NDX且点位不是货币金额；财务三表有字段契约偏差，已有双时间列不能证明历史版本 PIT 正确。ETF 结构化主数据、NAV 的时间语义依旧是主业务缺口，优先级高于无消费者的全市场期货历史铺量。

## 一、分页和频控：修根因，但不要扩成通用采集平台

**已验证代码及离线复现。** `packages/data/src/ditto_data/sources/tushare/client.py:33` 固定 `_PAGE_SIZE=9000`；`:248`—`:264` 向所有接口传入该 limit，返回少于 9000 即结束。实际 `TushareClient.query` 对一个有 2501 行、单页上限 2000 的假服务仅发出 `limit=9000, offset=0`，返回 2000 行，遗漏 501 行。此次复现不使用网络或真实配置。它证明逻辑缺陷存在，不证明任一生产分区已经丢了 501 行。

官方上限不是统一 2000–6000：

| 接口 | 当前专页上限/权限 | 对实施的意义 |
| --- | --- | --- |
| `daily` | 6000 行；停牌不出行 | 全市场按日期拉取；不能用证券数×日历直接断言完整 |
| `fund_daily` | 5000 行，5000 积分起 | 既有调研表的 2000 积分需要纠正 |
| `fund_adj` | 2000 行，2000 积分起 | 专页明确 `offset/limit`；不是 5000 积分起 |
| `index_global` | 4000 行，6000 积分 | 单只长历史也会跨页 |
| `forecast` | 3500 行，2000 积分；全市场季度使用 VIP | 不应把所有公告查询当日频行数 |
| `fut_daily` / `sf_month` | 2000 行，2000 积分 | 品种交易日/月份的覆盖口径各不相同 |
| `fut_basic` | 10000 行，2000 积分 | 反证“所有上限都低于9000”；不影响其他端点截断结论 |
| `index_dailybasic` | 3000 行；专页2000积分、总目录4000积分 | 官方页面自相矛盾；记录待账户验证，不能择一宣称实际权限 |
| `vix_index` | **300 行**，5000 积分 | “保守统一2000”仍可能截断；此新接口并不属于21指数 |

来源：[A股日线](https://tushare.pro/document/2?doc_id=27)、[ETF日线](https://tushare.pro/document/2?doc_id=127)、[基金复权](https://tushare.pro/document/2?doc_id=199)、[全球指数](https://tushare.pro/document/2?doc_id=211)、[预告](https://tushare.pro/document/2?doc_id=45)、[期货日线](https://tushare.pro/document/2?doc_id=138)、[社融](https://tushare.pro/document/2?doc_id=310)、[合约信息](https://tushare.pro/document/2?doc_id=135)、[指数估值专页](https://tushare.pro/document/2?doc_id=128)、[积分总目录](https://tushare.pro/document/1?doc_id=108)、[VIX](https://tushare.pro/document/2?doc_id=498)。

**建议修订分页票。** 现有终止条件已经是“返回行数 < 请求行数”，重复写这一条件不是修复。当前实际消费的接口用一张小型端点上限/分片表即可；只有已验证 `limit/offset` 语义的端点走 offset，其他按日期、月份、证券等官方支持参数分片。对未知端点，不应默认宣称自动分页完整。加入满页继续、整页重复/无进展失败、边界重复键检测；单次长查询与多个短窗口的键集合对比比“宇宙×交易日”可靠。稳定排序、数据请求过程中源端新增行的影响仍需用实际端点样本验证。

**最小验收。** 用服务端上限小于请求上限、恰好整页、空尾页、重叠页/重复页四类固定响应覆盖现有 client；真实验收分别选择行情、财务公告和月度宏观，比较分片键集合与较小查询集合，列出合理缺失。停牌、上市/退市、合约到期、无预告公司不能算数据丢失；财务/预告更不能按交易日数推算。

**已验证频控。** `sources/tushare/utils/rate_limiter.py:50` 的 paid global 为1000/min；`:40` 的 free global 为200/min。官方积分表15000档是500/min，而真正120积分免费档是50/min，因此不能再称 free 配置天然适合所有免费账户。5000/10000/15000的表定频率不等于某代理承诺。`client.py:54` 还允许 global/daily 显式覆盖，应保留真实服务契约可配置性，以已确认上限为默认。当前每个 limiter 使用进程内 MemoryStorage，多进程总预算是另一个边界；对个人机先保证单一调度/单活摄取，不为此上 Redis。[官方积分频次表](https://tushare.pro/document/1?doc_id=290)。

官方变更页还记录2025-11-10起单账户不能多IP同时提取、2025-11-03起取消多 `ts_code` 同时提取。部分专页仍保留逗号多代码描述，属于文档冲突。已有逐标的/按日调用无需重写；新增批量策略以按日期提全市场再本地过滤为首选，按目标 transport 验证。[官方变更记录](https://tushare.pro/document/1?doc_id=9)。

## 二、四组增补：保留范围，改成四份具体数据契约

### 商品期货

**已验证。** `fut_daily` 有 `close` 和 `settle`，还有 `pre_settle`、`oi`；成交金额单位万元，2020-01-01前后统计单双边口径变化。`fut_basic` 有合约/品种、交易单位、报价单位、上市和最后交易日；`multiplier` 的说明仅适用于国债和指数期货，商品不能无条件照用。[期货日线](https://tushare.pro/document/2?doc_id=138)、[合约信息](https://tushare.pro/document/2?doc_id=135)。此前评论中的 `close=null` 为旧实测，本次仅承认其记录，未再次探测。

**建议。** `market/commodity` 可以是已有文件分类，但数据集应明确是“期货合约日线”，不能同现货价格、商品指数混成一个无类型价格序列。保存合约ID、品种、交易所、交易日期、单位、结算价/收盘价和原始口径；若把旧双边量转为单边，必须记录转换规则及适用字段，不能不加区分对所有数值除二。主力/连续序列要有具体换月规则和合约映射，不能把供应商连续代码当可交易合约。

仅作A股/ETF宏观背景时，先为明确的油、铜、黄金或商品综合指标取得可解释序列；全市场全合约历史的存储并非成本大项，但清洗、换月和研究误用的维护成本真实存在。当前已裁决接期货的范围应保留，首批品种及回填深度由消费者决定，无需顺带实现期货撮合、保证金或交割引擎。

**最小验收。** 合约生命周期边界、万元换算、统计口径切换、`close=null/settle有效`、夜盘所属交易日；至少一个换月样本证明连续序列与合约原价没有混用。

### 业绩预告与快报

**已验证。** `forecast` 是上下界型预告，含 `first_ann_date`；净利润上下限为万元。`express` 的收入、净利润、资产等金额字段为元，含审计状态、同比和比较期字段；全市场报告期提取分别使用 `forecast_vip`、`express_vip`。二者不能共用一条“净利润万元”的转换规则。[预告](https://tushare.pro/document/2?doc_id=45)、[快报](https://tushare.pro/document/2?doc_id=46)。

**建议。** 报告期、公告日期、首次公告日期、采集时间、数据种类和原始响应身份分别保留；预告上下限允许单边为空，快报不当正式审计财报。`ann_date` 应约束可见版本，不是“按ann_date取最新就证明PIT”。日期粒度披露须选择保守可用时点；同日不同版本依赖快照身份而非仅日期去重。

**最小验收。** 同报告期两个公告日保留两个版本，后公告不能改变旧as-of；一个预告万元与一个快报元样本；同日更正冲突有显式处理；缺实际公开时间不得用报告期替代。

### 国内宏观

**已验证。** CPI/PPI并非全新接口：`sources/tushare/processors/mappings/macro.py:66`、`:78` 已分别注册同比字段。共享 `_fetch_single_api` 在 `adapters/macro.py:297`—`:303` 却统一传 `start_date/end_date`，而 CPI 与社融专页要求 `start_m/end_m` 的 `YYYYMM`。这至少是已确认的文档契约偏差；目标代理是否忽略错误参数并返回全历史，本次未知。[CPI](https://tushare.pro/document/2?doc_id=228)、[社融](https://tushare.pro/document/2?doc_id=310)。

`adapters/macro.py:390`—`:400` 已把自采日期作为 knowledge date，明确拒绝用固定 release lag 冒充历史公开时间。这是应保留的保护。注册表里的 lag 可以是说明，但不应重新进入历史回测可见性计算。

**建议。** 本票改成“补 `sf_month` 的三条系列、补明确需要的 CPI/PPI 字段，并修正/验收共享请求参数”。社融增量当月值与累计值是亿元，存量是万亿元，不能只用一个接口级 unit。先用既有长表 `indicator_code/value/unit/frequency/date/knowledge_date`，无需宏观专用数据库。季度GDP的参数同样需逐端点核对，不能按频率名称猜参数。

**最小验收。** 精确断言发出的月度/季度参数；请求窄窗口不带回未声明的全历史；三条社融不同单位；后采修订不能在旧knowledge cutoff出现；历史回填仅可作“当前修订值研究/自采以后回放”，不能宣称恢复历史发布版本。

### 指数每日估值

**已验证。** `index_dailybasic` 是部分大盘指数的社区计算指标，市值单位元、股本单位股，单次3000行；不能套用个股 `daily_basic` 的万元/万股。专页文字列六类指数，但示例含沪深300等更多代码，故不能由一段描述断言实际代码全集。权限专页2000与总目录4000也冲突。[指数估值](https://tushare.pro/document/2?doc_id=128)、[目录](https://tushare.pro/document/1?doc_id=108)。

**建议与验收。** 按实际支持的有限指数清单接线，空结果报告 `unsupported/unknown`，不填零、不承诺所有ETF跟踪指数估值；一个元/股样本、一个缺PE样本、一次端点权限与代码覆盖的只读验证即可。价格指数水平与估值指标分别存储。

## 三、全球指数：名单、点位、时间和缺口

**已验证的21代码**：`XIN9, HSI, HKTECH, HKAH, DJI, SPX, IXIC, FTSE, FCHI, GDAXI, N225, KS11, AS51, SENSEX, IBOVESPA, RTS, TWII, CKLSE, SPTSX, CSX5P, RUT`。官方表无 `NDX`；`IXIC` 是纳斯达克综合，不能替代纳斯达克100。全球指数全量票示例中的 `NDX` 应删除并列为未覆盖需求。OHLC字段是指数点位，vol/amount大部分缺失。[国际指数](https://tushare.pro/document/2?doc_id=211)。

代码 `adapters/index.py:27` 现有5个spec为 SPX/IXIC/DJI/GDAXI/N225。`:42` 已处理日本2024年收市时刻变化，`:191` 说明历史公开时刻未知，`:204`—`:206` 用实际采集时刻；`:255`—`:258` 将其写入 published/available/knowledge。这个保守边界不应为获得“历史数据可回测”而退化成 trade_date当天可知。另 `:220` 请求没有 amount，`:249` 直接补 null；官方支持的字段与本地实际保留字段要分清。

**建议改票：**

1. 将“原币原单位，消费端按fx_daily换算”改为“原指数点位、指数计价币种、收益口径分别记录；需要人民币收益时，使用对齐时点的指数收益与汇率收益构造并注明公式”。点位直接乘汇率不会自动成为有意义的人民币指数。原市场币种也不总能推出指数自身计价币种。
2. “observation date自然日序列”应指按供应商日期存观测，不是每天造一行、周末补价，或把自然日午夜当已公开。缺节假日历时可暂不判每个缺口为丢行，保留每市场日期和抓取时刻。
3. 不建多市场交易日历平台并不等于取消时区/夏令时/跨境截止时间。21个spec需要验证源指数本身的时区和收市语义；半日市/临时停市未知时，不伪造精确发布时刻。可先只以 observed/available 作研究可见性界线。
4. published_at若实际含义只是 observed_at，应在契约中明确“代用的保守可见时间”，不对外宣称源站发布证据。首次自采之前的严格历史PIT仍不可用。

**最小验收。** 名单精确匹配、拒绝NDX误映射、一个美股跨上海日期/夏令时样本、一个非中国交易日、一个全空量额样本、回填历史在采集前cutoff不可见。单日21条不足以验证各地假期、长历史跨页或历史起点。

**补源判断。** VIX已另有 `vix_index`，5000积分、300行；但其字段表宣称价格为字符串，样例又出现 `pre_close` 而非表中 `close`，应先核验真实响应，不能直接复制OHLC adapter。若FRED已有满足使用目的的VIX序列，不必再接第二份。[VIX专页](https://tushare.pro/document/2?doc_id=498)。NDX属于真实缺口，应按ETF跟踪基准需求单独核对候选，不把“21全量”叫全球基准完整。未来美股日线是独立权限体系，不随15000积分自动获得。[权限表](https://tushare.pro/document/1?doc_id=290)。

## 四、主业务仍缺的ETF和财务语义

### ETF身份、NAV及近期接口变更

**已验证。** `adapters/etf.py:52`—`:66` 仍从 `fund_basic(market='E')` 取代码/名称/上市日，再按名称包含ETF过滤。当前 `etf_basic` 提供跟踪指数、存续状态L/D/P、管理人、管理费和QDII通道；但不直接提供完整资产类别、产品规则或退市日期，不能宣称换端点就完成证券主数据。[ETF基础信息](https://tushare.pro/document/2?doc_id=385)。

`fund_nav` 不限场外/联接：官方参数明确 `market=E/O`，含 `ann_date` 与 `nav_date`，以及单位、累计、复权净值。这应纠正此前能力表对其用途的缩窄。ETF NAV对账需要先定义净值类型与公布日期；不能用两个同名“净值”浮点数直接对账，也不能将历史NAV当实时IOPV。[基金净值](https://tushare.pro/document/2?doc_id=119)。

**建议。** 在核心A股ETF产品中，结构化身份 + 跟踪指数 + 存续状态 + NAV类型/日期，通常比全市场期货铺量更值得先完成。现有API即可覆盖相当部分，无需新增行情供应商。费率、申赎限制、跨境时差等只补实际消费需要的字段，未知值保留未知。NAV独立数据产品先验收，再扩跨源对账；对账不能替代主数据接线。

官方变更日志记录2026-09-07将ETF涨跌停从 `stk_limit` 迁到 `etf_limit`。仓库检索只发现 `stock.py:384`—`:387` 调 `stk_limit`，未发现 `etf_limit` 接线。这不等于当前股票功能坏了，但如果交易约束或Paper要覆盖ETF，就必须验证ETF限价覆盖，不能认为个股接口仍含ETF。[变更记录](https://tushare.pro/document/1?doc_id=9)、[ETF涨跌停](https://tushare.pro/document/2?doc_id=491)。

### 三表不能由“有f_ann_date”自动升级成严格PIT

**已验证。** `adapters/fundamental.py:29`—`:44` 三张请求字段都没保留 `ann_date/report_type/update_flag`。`processors/mappings/capital.py:183` 把 f_ann_date映射knowledge_date；`:269` 同样处理现金流。官方财报契约区分实际公告日和报告类型，FAQ明确初始/修正记录；这些字段不证明全部历史版本完整，但丢弃它们会失去判断版本和口径的证据。[现金流量表](https://tushare.pro/document/2?doc_id=44)、[官方FAQ](https://tushare.pro/document/1?doc_id=122)。

**额外发现：字段拼写已造成确定的本地转换损失。** `_CASH_FLOW_FIELDS` 请求 `n_cash_flows_inv_act`，官方字段为 `n_cashflow_inv_act`。mapping在 `capital.py:262`、`:272`、`:275` 继续用前者。`transformer.py:79` 和`:112`会给未返回的声明字段补null。离线输入官方名称的投资现金流 -20，经真实transformer输出投资现金流和净现金流均null。此结果证明转换层面对官方字段时的损失；目标代理是否自有别名、真实存量损失规模尚未验证。

同一请求还包含 `depreciation/interest_paid/tax_paid`，官方当前cashflow表使用如 `depr_fa_coga_dpba`、`c_paid_for_taxes` 等不同字段/口径；不应简单重命名“利息支付”到包含股利利润利息的组合项。修此根因时应逐字段核验三表当前真实消费者，避免 null 填充掩盖必需字段缺失。无消费者的装饰字段可删除，有消费者的字段按定义映射，必要衍生项独立命名。

**建议。** 将“现有announcement range/VIP设计PIT正确”降为“具有增量公告查询与可见性基础，版本证据待验收”。保留报告期、实际公告日、报告类型、更新标志、原始内容身份/观察时间；以现有快照和版本存储承接，不建立第二套通用双时态引擎。对源端不能证明的旧版本，标识供应商日期约束或自采快照证据，不伪造历史。

**最小验收。** 使用官方命名的固定响应；初始披露/后更正/同日多口径/缺公告日四组反例；新修订加入后旧snapshot+cutoff结果不变；必需数值列若因字段名不匹配缺失必须显式失败或隔离，不以DQ“允许null”掩盖。

### 指数成分权重的时间含义

`capital_index.py:80`—`:96` 把 `index_weight.trade_date` 转成 effective_from，并丢掉原trade_date名称；官方称其月度权重观察数据，没有给出公开时间或调整生效通知。不能由月度观测日期推导成分调整前可知性。[指数权重](https://tushare.pro/document/2?doc_id=96)。

`index_member_all` 是**申万行业分类**的分级成员接口，不是所有市场指数的通用成分接口。默认 `is_new=Y`，历史查询必须明确取旧成员并处理in/out边界；它同样不提供公告时刻。[申万分级成员](https://tushare.pro/document/2?doc_id=335)。用它替代旧 `index_member` 应只修申万分类路径，不能笼统替代沪深300等成分权重。

代码还有局部契约风险：`capital_index.py:172` 读取 `con_code`，但同类 `fetch_index_weight` 在`:81`已改成 `source_ticker`。该分支只有 `with_weight=True` 且权重非空才触发；本次检索实际摄取注册调用的是fetch_index_weight，未找到业务直接使用该composition分支，故应记录为有界待修/待消费者核实，不能夸大为当前摄取整体故障。

## 五、对既有票据的最小修订清单

| 票据 | 应补充/修正的决策 | 最小交付边界 |
| --- | --- | --- |
| [分页与频控修复](https://github.com/cosmos-arc/ditto/issues/431) | 按实际端点上限与分页支持；删万能2000及“全都低于9000”；免费档与实际权益也核对；完整性不能统一宇宙×交易日 | 小型表+现有client修复+固定响应反例+选定真实分片对照 |
| [四组接口增补](https://github.com/cosmos-arc/ditto/issues/434) | 预告万元/快报元；社融增量亿元/存量万亿元；指数估值元/股；修已有月度参数；合约与连续/现货分清 | 四个有限数据契约+现有摄取接线，无新平台 |
| [全球指数全量注册与摄取](https://github.com/cosmos-arc/ditto/issues/435) | 精确21名单无NDX；点位不直接货币化；自然日观测不造交易日；保留首次采集可见性边界 | spec/registry/flow完善，并验证跨日与未知发布时刻 |
| [跨源对账扩展路线](https://github.com/cosmos-arc/ditto/issues/438) | 因子绝对水平可能锚点不同，应先约定比较事件或相邻因子比；ETF NAV先有同类型同日期的数据产品 | 本票仍只交adj_factor，后续路线不冒充已交付 |
| 需纳入现有正确性/数据规格工作，避免重复造票 | 三表官方字段核验、修订身份；ETF结构化主数据与NAV；ETF限价接口迁移；指数成分的公告/观测语义 | 先定位已有owner，缺owner再开聚焦决策/修复票 |

因子对账建议属于本次推断：Tushare FAQ说明前复权有end_date锚及分红再投；fuyao事件如何构造可比因子，需以其契约和样本确认。不能仅因两源绝对值不同判坏，也不能因一致便证明源头独立。[Tushare复权FAQ](https://tushare.pro/document/1?doc_id=122)。

## 六、复现记录与未验证项

本次执行 `uv run --no-sync python` 两个离线实验，均基于上文SHA，无磁盘业务写入：

- 实际client + 假 `_query`：2501行、每页最多2000，得到2000行/1次请求，静默遗漏501，断言通过。
- 实际cashflow transformer + 官方字段命名：输入投资现金流-20，输出investing/net cashflow为null，断言通过。首次运行因未初始化应用Metrics注册失败；第二次仅在实验进程patch为noop Metrics以隔离无关宿主绑定，转换代码未修改。

在仓库根目录执行以下分页反例：

```bash
uv run --no-sync python - <<'PY'
from types import MethodType
from ditto_data.sources.tushare.client import TushareClient

client = object.__new__(TushareClient)
rows = [[i] for i in range(2501)]
calls = []

def capped_page(self, api_name, fields, **params):
    calls.append(params)
    start = params["offset"]
    return {"fields": ["row_id"],
            "items": rows[start:start + min(params["limit"], 2000)]}

client._query = MethodType(capped_page, client)
result = client.query("fut_daily", "row_id")
assert result.height == 2000 and len(calls) == 1  # 当前缺陷；修复后应完整取回2501
print({"expected": 2501, "returned": result.height, "requests": calls})
PY
```

在同一目录执行以下现金流字段反例；只有无关的Metrics绑定被替换，实际列转换保持原样：

```bash
uv run --no-sync python - <<'PY'
from types import SimpleNamespace
from unittest.mock import patch
import polars as pl
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer
from ditto_data.sources.tushare.processors.mappings.capital import CASH_FLOW_MAPPING

frame = pl.DataFrame({
    "ts_code": ["600000.SH"], "end_date": ["20251231"],
    "f_ann_date": ["20260331"], "n_cashflow_act": [100.0],
    "n_cashflow_inv_act": [-20.0], "n_cash_flows_fnc_act": [-10.0],
})
metrics = SimpleNamespace(data_records=SimpleNamespace(add=lambda *args: None))
with patch("ditto_data.sources.tushare.processors.transformer.Metrics", metrics):
    result = TushareDataTransformer.transform(frame, "cash_flow", CASH_FLOW_MAPPING)
assert result["investing_cash_flow"][0] is None  # 当前缺陷；应保留输入-20
assert result["net_cash_flow"][0] is None
print(result.select("operating_cash_flow", "investing_cash_flow", "net_cash_flow").to_dicts())
PY
```

未验证：真实账户/代理权限、官方与代理差异、历史分区完整性、上述财务别名在代理上的行为、所有21指数历史起点/源时区、重述财报版本完整性、ETF全产品NAV覆盖、连续运行稳定性。它们需要有限的真实样本与运行证据，不能用本次文档核查和离线断言代替。
