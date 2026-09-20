# A 股与 ETF 专业个人量化工作台：数据源再审视

调研日期：2026-09-20。代码基线：`4c968e1d3f21828ab20308cdfdea550babee6454`。仅依据当前源码、GitHub 票据和供应方/交易所/基金公司一手资料；未调用付费 API、读取凭证、验证实际授权或重跑数据回填。下文“建议”不是已经完成的能力，也不是采购授权。开发改动成本不作为否决条件；原有每年 1000 元运营预算未被取消，另列专业方案供选择。

## 判断

保留 Tushare 格式主源与 fuyao 辅源是合理的预算内起点，但现有“双源已经定稿”的表述过强。真正缺口是**来源身份、历史版本与可知时间、ETF 产品身份和跨境估值语义**，而非再增加十个行情接口。当前计划把积分、接口通畅、数据质量、PIT 和连续运行混成了同一种验收，需要拆开。

最值得保留：原始价与公司行动分离；外部数据落地后再研究；展示快照与研究数据分离；跨源单位归一与对账；不接券商自动下单。最应修订：把 `f_ann_date` 叫作“唯一 PIT 锚”；把两个 API 叫作“独立双源”；把 ETF 名称匹配当产品主数据；把免费开源客户端当永久数据授权；把回填完成当连续运行验收。

## 已确认的四个计划与事实偏差

| 原计划 | 当前证据 | 修订建议 |
| --- | --- | --- |
| ETF 日线和复权均需 8000 积分，所以必须购买 10000 档 | 当前 `fund_daily` 专页写 5000 起、8000 更高频；`fund_adj` 写 2000 起、5000 更高频。`etf_basic` 才明确 8000 | 保留 10000 档作为含结构化 ETF 主数据的候选，改掉错误购买理由。按实际必需接口逐项核验权益 |
| 实施是“官方 10000 积分升级” | 数据升级票据评论写第三方代理与 15000 积分 token，并记载用户已裁决采用；对应 PR 标题和正文也明确代理 transport | 尊重既有授权；ADR 如实记录 `接口协议=Tushare`、`传输服务=代理`、`权益=代理声明/实测接口能力`，不可升级为已验证官方账户权益 |
| `paid` 档就是官方 10000 的配额 | 本地 `paid()` 为 global 1000/min；官方积分表 10000 档是 500/min、特色 300/min | 限流按实际服务契约与端点设定，不能由枚举名称推断权益 |
| 财务只要替换 `ann_date` 就完成 PIT | 当前三表 adapter 已请求 `f_ann_date`，但请求字段未保留 `report_type`、`update_flag`；mapping 直接映射日期 | 字段迁移只能认定为 CODE 完成线索，历史重述版本、时间边界、存量迁移另验收 |

来源：[ETF 日线](https://tushare.pro/document/2?doc_id=127)、[基金复权](https://tushare.pro/document/2?doc_id=199)、[ETF 主数据](https://tushare.pro/document/2?doc_id=385)、[积分表](https://tushare.pro/document/1?doc_id=290)、[Tushare 升级与 ETF 摄取校准](https://github.com/cosmos-arc/ditto/issues/200)、[开发代理与付费限流配置](https://github.com/cosmos-arc/ditto/pull/221)。官方概览页与接口专页亦有分值差异，专页也不能代替账号实际权益验证。

本地证据：`packages/data/src/ditto_data/sources/tushare/utils/rate_limiter.py`、`adapters/fundamental.py`、`processors/mappings/capital.py`。票据记载 ETF 日线约 165 万行、DQ 通过但有 1 条 alert；这是 2026-09-18 的执行者记录，本次未重现。一周 EOD 无配额错误仍是独立观察项。

## 财务与研究 PIT：日期是必要条件，不是充分条件

Tushare 三表提供实际公告日、报告类型等字段；官方 FAQ 说明修正记录可通过 `update_flag` 区分初始与修正。该说明不能证明所有历史版本完整，也不能证明每条重述值在对应日期已经可见。`disclosure_date` 是披露安排/实际日期信息，不能单独证明某份财务数值版本的可知时间。[现金流量表](https://tushare.pro/document/2?doc_id=44)、[官方 FAQ](https://tushare.pro/document/1?doc_id=122)、[披露日期表](https://tushare.pro/document/2?doc_id=162)。

建议用三种证据等级，而不宣称所有历史数据一律严格 PIT：

- **公告版本可回放**：有原始公告身份、报告口径、实际公开时间及其数值版本，允许对应时点回测。
- **供应商日期约束**：有实际公告日但历史版本完整性未证实，标注研究限制；不能无条件升级成严格历史 PIT。
- **自采快照可回放**：从首次留存日起可靠重现观察结果；今天抓到的十年前报表不能凭回填动作证明十年前看到的版本。

最小契约至少区分报告期、公开时间/日期、首次采集时间、原始内容 hash、修订身份与合并/母公司/累计/单季口径。按日披露但无时分秒时，预先规定保守可交易时间，例如次一交易日开盘，并用盘中/盘后反例验收。无需建立复杂通用双时态数据库，先让既有快照与查询明确上述语义。

财务验收样本应覆盖初始披露后重述、同日多报表、年报比较期重列、缺失实际公告日、报告类型变化、退市证券。新增未来修订记录后，旧 as-of 查询与旧实验数据身份必须保持不变。`f_ann_date` 缺失不应悄悄退回报告期；`update_flag=1` 也不能成为“取最新即可”的捷径。

RQData 的官方 `get_pit_financials_ex` 明确有 `date`、`statements='all'`、`info_date` 和修订展示，值得作为专业方案的对照样本供应商，而不是无依据归类为“无 PIT 证据”。仍需试样本验证与报价。[RQData 季度财务 PIT](https://www.ricequant.com/doc/rqdata/python/stock-mod)。

## fuyao：可保留，不能过度承诺

官方仓库明确自称由同花顺提供维护，且具备 REST、MCP、CLI、Python 入口；本次证据支持把它识别为同花顺公开金融数据服务。MIT 是仓库软件许可，本次未取得覆盖数据留存、再分发、对外展示、LLM 第三方处理、长期免费与 SLA 的完整服务合同。因此不能由 MIT 或“当前免费”推出这些权利永久成立。[官方仓库](https://github.com/HiThink-Tech/Financial-API)、[REST 契约](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/README.md)。

已核准边界：全市场 dump 是约十年未复权日线，另有十交易日增量和公司行动事件；ETF 历史只支持单只、最长五自然年窗口、前复权。ETF 响应 `adjust=null` 仍不代表原始价。事件 dump 有除权日期、现金分红、送股、配股等字段，未展示公告公开时间字段。它支持价格校验和复权计算，不足以证明公司行动预知信息的历史 PIT。[Market Dumps](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/market-dumps.md)、[ETF 历史契约](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/fund/market-historical.md)。

本地 `FuyaoSource` 已主动排除 ETF 前复权数据进入原始价摄取，这个实现比旧决策“ETF 近端回补”更严谨，应让计划向实现对齐。A 股 `_bars_frame` 和 `daily_k_frame` 从前一行原始 close 推导 `pre_close`/涨跌幅；跨源比较必须单列除权日，因为前一日成交收盘价与除权参考价不是同一个量。源切换还应验证首行缺失前价、停牌、数据窗口外前值、交易所代码，不以行情列齐全认定等价。

当前 `_to_thscode` 用首字符推断后缀并默认深圳，而官方契约要求不要猜后缀；应通过证券主数据确定身份，重点覆盖北交所新旧代码与不能识别的输入。临时 dump 下载后会删除，本次未追踪完外层快照写入链，不能据此判定全局无快照；应把“能从 snapshot_id 找回原始响应/原始文件并校验 hash”纳入验收。

两个服务商不等于两套独立原始采集链。Tushare 基金介绍明确包含网络公开渠道和第三方合作；Tushare 本身还有 THS 类特色接口。主源与 fuyao 同值可能来自共同上游，不能把一致率当正确率。建议按数据集记录原始发布者/聚合方/transport，保留“上游独立性未知”；争议值抽样核对交易所或基金公司原件。[Tushare 基金来源说明](https://tushare.pro/document/1?doc_id=18)。

## ETF 必须成为产品域，而不只是另一种 K 线

本地 `fetch_etf_basic()` 目前请求 `fund_basic(market='E')`，只取代码/名称/上市日，再用名称含 ETF 过滤。这不足以可靠区分 ETF、联接基金、LOF、货币型、跨境、商品与债券产品，也不含跟踪指数和退市边界。当前 Tushare 已有 `etf_basic` 的跟踪指数、上市状态、管理人等结构化字段，应替换名称启发式，保留终止/退市历史版本。[ETF 主数据](https://tushare.pro/document/2?doc_id=385)。

| 数据产品 | 最小必需字段/语义 | 主要用途与验收 |
| --- | --- | --- |
| ETF 身份 | 上市/退市、管理人、资产类别、跟踪指数、币种、复制方式、费率、生效期 | 同指数产品可比较，历史池无幸存者偏差；用交易所及基金合同核验 |
| 市场价格 | 原始 OHLCV、成交额、价差/快照时间、停牌与交易规则 | 可交易性与成本；不把所有 ETF 套股票 T+1 |
| 净值 | 单位/累计/复权 NAV、净值所属日、披露日/时间、币种 | 总回报与跟踪偏离；禁止把 NAV 日期当发布时刻 |
| 规模和份额 | 份额口径、单位、日期、披露时点 | 容量/清盘风险；份额变化×NAV 只是近似净流量，不能冒充精确资金流 |
| 分红/拆分 | 公告、权益、除息、支付、生效与修订 | 净值总回报和价格复权一致 |
| 基准 | 指数身份、价格/全收益版本、币种、汇率转换 | ETF 相对收益不混用不同收益口径 |
| 跨境状态 | 境内外日历、时区、NAV 时滞、汇率时间、申赎限制/额度 | 显示可信折溢价所需的时点条件 |

Tushare 现有基金净值、份额接口提供预算内入口，但它们存在不代表 Ditto 已有完整产品接线。[净值](https://tushare.pro/document/2?doc_id=119)、[份额](https://tushare.pro/document/2?doc_id=207)。交易所的基金档案和 PCF 可作为基金身份、申赎状态与争议证据的定点核对源，不必建设第三个全市场行情平台。[上交所基金档案](https://etf.sse.com.cn/fundlist/funddetail/index.shtml)、[上交所 PCF](https://www.sse.com.cn/assortment/fund/list/etfinfo/redemptionlist/)、[深交所基金披露](https://www.szse.cn/disclosure/fund/etf/index.html)。

跨境 ETF 的价格/NAV 比值不能自动叫实时溢价。基金公开材料明确提示 QDII 净值披露滞后及 IOPV 风险；UI 应同时显示价格时间、净值日期/披露时间、IOPV 时间与计算来源，不能用一个醒目百分数遮蔽时差。上交所 2026-02-13 通知已将相关 IOPV 计算职责迁往中证指数公司，说明连“由谁计算 IOPV”都应按产品与日期管理，不能照搬旧投教统一说法。[基金公司净值时滞示例](https://www.efunds.com.cn/Mobile/fund/012871.shtml)、[IOPV 计算源调整通知](https://big5.sse.com.cn/services/tradingtech/notice/c/10809566/files/87e6499e4e234f36b2d3b853cf3a77ca.pdf)。

## 历史证券池与指数成分

Tushare 有上市状态和月度指数成分权重能力，本地也有 L/D/P 枚举查询与指数 range adapter，这些值得复用。但“拿到了退市列表”不证明退市前行情、终止日期、历史 ST/停牌/行业均齐全；“月度权重日期”不等于调整公告日或成分生效日。[Tushare 数据目录](https://tushare.pro/document/1?doc_id=108)。

专业验收应给出逐年证券数量、上市/退市交集、缺失历史覆盖和指数调入调出样本。指数公布前不得反向使用新成分；未有历史成分证据时，实验必须显式使用“固定当前池研究”，不称历史可投资池回测。`CapitalIndexTushareAdapter` 将 `trade_date` 映射 `effective_from` 的实现，应针对月度快照语义复核，而不是先假定正确。

## 替代源比较与采购原则

| 候选 | 本次证据支持的定位 | 限制/价格 | 建议 |
| --- | --- | --- | --- |
| Tushare 官方 | 预算友好的广谱日频数据与 ETF 入口 | 官网 5000 档 500 元/年、10000 档 1000 元/年；独立权限另算，账号未核验 | 保留默认候选，按必需能力清单选档 |
| 当前 Tushare 兼容代理 | 已有用户授权与历史调用记录 | 价格、上游授权链、权益保证、SLA 本次未知 | 不撤销既有裁决；诚实标记 transport 与证据等级 |
| fuyao | A 股原始行情/事件校验与展示，基金资料候选 | 长期价格/数据使用合同本次未知；ETF 历史为前复权 | 逐数据集准入，不承诺全能力自动替补 |
| RQData | 明确 PIT 历史财务 API，独立 Python 与 HTTP 数据使用 | 商业报价、套餐权限、本机连通性未知 | 专业方案优先试样本；不能因旧调研泛称无 PIT 证据排除 |
| JQData | 候选本地数据服务与研究生态 | 本次官方文档入口返回地区不支持；不能据此判定用户网络也被封；报价未知 | 重新取得可访问官方样本/报价后比较，不在当前推荐中宣称已核准 |
| AKShare | 多站点数据接口库、缺口探索与定点核对 | 源站与接口会变，软件许可不等于每个数据集授权，不能整体认定独立数据源 | 不建设全量自动降级；有确切缺口再选单接口 |
| BaoStock | 可重新候选为特定日频交叉校验 | 本次官网未返回可核验接口正文，ETF/退市/PIT 支持不下确定结论 | 不重复旧“不支持 ETF”的未经刷新断言；不为填满双源表而引入 |
| 交易所/指数公司/基金管理人 | 原始公告、基金合同、PCF、产品身份与争议事实 | 公开浏览不自动等于批量数据授权；历史接口/再分发需分别核实 | 必须允许定点证据补充，不受“严格只有两家”限制 |
| iFinD / Wind 数据服务 | 专业服务候选，询价并请求端点样本 | 本次未核准个人价格、目标套餐、macOS/Linux 无终端方式和留存权利 | 不按“贵”预先排除，也不未经证实推荐购买 |

一手入口：[RQData 使用说明](https://www.ricequant.com/doc/rqdata/python/manual.html)、[RQData HTTP](https://www.ricequant.com/doc/rqdata/http/data-process)、[JQData](https://www.joinquant.com/help/api/help?name=JQData)、[AKShare 官方仓库](https://github.com/akfamily/akshare)、[BaoStock 官网](https://www.baostock.com/)、[iFinD 数据接口](https://quantapi.51ifind.com/)、[Wind 数据服务](https://www.wind.com.cn/portal/zh/WDS/index.html)。接口存在与营销介绍都不是验收结果。

**预算内方案**：在现有约 1000 元/年纪律内优先保障日频 A 股/ETF、结构化 ETF 身份、复权、财务、日历和可投资池。fuyao 做具备等价契约的辅源，原件核对按需；文本、分钟、实时 IOPV 不自动加购。若选择官方 5000 档只能满足部分能力，需把 8000 起的 ETF 主数据替代方案与缺口明列，不能为了省预算隐瞒产品退化。

**专业方案**：用同一组真实研究样本比较 RQData、JQData、iFinD/Wind 中可获正式权限的套餐，选一家解决历史版本财务/证券池/ETF 语义缺口的主力；Tushare/fuyao 保留明确必要角色即可。优先为“能解释和重放旧决定”的数据付费，再考虑更多频率/另类数据。报价未知，不能提供虚构总价，也不建议同时购买全部候选。

## 对已有票据和规范的具体修订

1. [数据源双源决策](https://github.com/cosmos-arc/ditto/issues/191)：把“定稿”改成基于当前预算的准入基线；纠正权限门槛，披露代理实际接线；将“唯一 `f_ann_date` 锚”改为可验证公开版本与保守可用时间；原始证据补充不受两源数量限制。
2. [fuyao 冗余源接入](https://github.com/cosmos-arc/ditto/issues/199)：补充身份/单位/复权/前价/历史覆盖契约；ETF 前复权不做原始行情回补；核对事件流/财务对账真实实现与运行证据，不能由已存在门面函数推断三项对账全部完成；记录独立性未知。
3. [Tushare 升级与 ETF 摄取校准](https://github.com/cosmos-arc/ditto/issues/200)：将权益来源、接口矩阵、回填、DQ 告警解释、一周运行分开；不把代理账号声明计作官方升级证据。
4. [财务披露锚迁移](https://github.com/cosmos-arc/ditto/issues/219)：保留已完成代码，不重复改字段；后续验收覆盖修订版本、公开时刻、报告类型、缺失值、旧实验回放以及存量数据差异。
5. [backfill 重试幂等性](https://github.com/cosmos-arc/ditto/issues/220)：`--force/KEEP_LAST` 是恢复操作便利性，不足以成为完整幂等策略。相同输入重复执行应一致；变更输入必须产生可追踪版本，保留旧 snapshot/旧实验复现；写入成功但分区状态未提交也要可恢复。
6. 新增决策题：ETF 产品主数据与估值时间契约；历史证券池/指数成分可靠范围；数据服务授权与供应商基准样本。它们分别阻塞 ETF 产品比较、严谨横截面研究和专业数据采购，避免拆成几十个没有明确消费者的接口接入任务。

建议最终验收交付一个小而可复现的证据包：一只重述财报股票、一只退市股、一次指数调仓、一只分红 ETF、一只跨境 ETF，分别保留原件、标准化结果、可知时间、as-of 反例、两源差异与人工裁决。再加连续运行记录证明每天能生产可信结果。代码测试、上游契约、实际样本和连续运行四者分别报告。
