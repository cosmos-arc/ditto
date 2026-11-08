# 2014 年起股票与 ETF 普通历史回测：缺口与最小补齐路线

2026-11-08；研究票：[2014 年起股票与 ETF 普通回测的实际缺口与补齐路线](https://github.com/cosmos-arc/ditto/issues/733)，父地图：[传统量化工作台产品可用化](https://github.com/cosmos-arc/ditto/issues/726)。源码固定于 `f331761e66438921723254646f469a4c3eaef23e`。以下区分已核事实、工程推论和缺证；没有运行历史回测、重扫库存、改生产代码或写真实数据。

**结论：2014 年起可用不能靠改起始日期和扩大十只白名单实现。** 现有日线、复权、策略模板、规则接口和结果身份值得复用；真正的依赖是历史成员与状态、分时段执行规则、公司行动的现金/份额处理，以及这些能力接入普通入口后的任务验收。完成这条普通历史重建路线，仍不等于取得严格历史 PIT 资格。

已确认目标是本人盘后研究与次日计划，股票多因子选股、ETF 轮动和趋势三类任务；可视条件/因子组合与高级受控公式，Python 自由策略后置。时间目标是 **2014 年起、至少十年**；晚成立证券按实际生命周期进入，不能把目标改成最近几年或固定十只成功样本。本研究不扩展海外股票、宏观、券商下单或新研究平台。先逐任务验收，真人日用周期另定。

## 1. 限制属于正式普通入口，不能泛化成整个回测引擎

已核调用链为 [Web createBacktestRun][web-run] → [HTTP POST /runs 与后台任务][api-run] → [run_backtest_flow][job-run] → [run_backtest_from_catalog][process-run] → [普通运行时工厂][ordinary-factory] → [build_ordinary_rules][ordinary-builder]。工厂无条件调用普通规则构造器；不是仅示例页面或某个测试夹具受限。

[ordinary_equity.py][ordinary-rules] 明确限定五只主板股票和五只境内股票 ETF、`2023-08-28 ≤ start ≤ end ≤ 2026-11-08`；拒绝上市未满 30 自然日、运行期内退市、股票 ST/状态未知，以及运行区间内池成员复权因子发生变化。ETF 通过正成交量确认交易发生，缺报价/零成交量不能自动变成已知停牌。它们是当前有限证明范围的保护，不是 2014 年历史可用性的实现。

通用引擎可注入规则、数据和经纪模拟器；[冻结研究工厂][frozen-factory]另有冻结行情/日历/成员/财务/分类数据路径。因此应补普通消费者的历史能力，不能宣称“引擎只能回测十只”，也不能把普通用户强行送入严格研究路径来绕开守卫。

## 2. 先把物理库存、执行条件和历史资格分开

下表是 [11 月 7 日验收报告][inventory]继承的 02:01 UTC 覆盖扫描，**不是本研究重新扫描**。`read` 只说明所测消费者读通，`ready` 也只对已声明用途有效。原报告整体仍为 `NOT_PASSED`。

| 所需内容 | 已记录库存/能力 | 对 2014 普通回测仍需证明 |
| --- | --- | --- |
| 股票/ETF 日线与日历 | 两类日线从 2013-01-04；日历从 2013；均有 partial | 声明证券生命周期内逐会话缺口归因、单位、重复、基准与预热连续性；总行数不代替分母 |
| 名册、退市、ST、停牌 | stock/ETF basic partial；stock_status 仅从 2016-08-09；namechange、st_history 有更早记录 | 2014–2016 状态证据的来源和可推导边界；ST 未覆盖不能当正常；交易发生不证明整日均可成交 |
| 复权与限价 | 股票 adj_factor 从 2013 且 ready；fund_adj partial；stock_limit 从 2014 且 ready | 实际交易使用原价；规则和事件对拍；股票限价行不能补造缺失停牌或历史身份 |
| 分红与公司事件 | dividend 从 2014、ready；corporate_actions ready | 前者当前采集字段不足以做完整现金/送转处理（见第 6 条）；后者用途是回购/解禁且排除配股，并非完整公司行动账 |
| 选池与因子 | 财务指标/财报、行业历史、指数权重已有库存与消费者 | 历史成员生效、公告/修订可见性及所需字段；最新指数权重不能充作历史成员证明 |

[冻结范围][frozen-scope]原本就包括沪深含退市证券，以及 ETF 退市/旧码，起点为 2014 或真实上市/成立起点。这些分母应保留；允许按证据批次推进，不得用幸存证券或挑选无分红窗口掩盖剩余缺口。

## 3. 普通历史重建与严格 PIT 必须有不同、可追踪的资格声明

[时间语义文档][time-lanes]已区分回补历史、live 和 live 时代逐日 vintage 重放：回补历史没有当年真实入库时刻，依靠事实时点和冻结 vintage；严格重放还要当时可得证据。真实 receipt time 不能回填成 2014。当前普通工厂[主动拒绝 research_snapshot_id][ordinary-factory]，库存报告也明确主表最早可证观察为 2026-10-03，严格历史仍未认证。[资格现状][qualification]

**工程推论：**补齐路线必须将“以本次冻结来源重建历史”落实到实际查询、报告及导出，标明修订/成员/选择偏差；历史财务因子仍不能按报告期提前获知公告。当前 [get_history][history-feed]还显式过滤 `knowledge_date <= cutoff`，不能仅凭文档里的回补车道就宣称 2014 已读通。应核对真实字段来源、回补查询策略及两条资格边界，给出反例验证；不能简单删 knowledge 过滤、改旧入库时间或借 `allowExperimental` 放行。

盘后研究还须固定信号信息截止、执行会话及价格假设。现普通规则采用保守知识滞后；是否调整为某个盘后至次日合同属于明确的行为改变，不能在拉长历史时顺带偷偷改变。[当前可见性与结果约定][ordinary-evidence]

## 4. 历史证券池、生命周期与缺行情处理是一个消费者缺口

普通工厂目前只在 **start_date 解析一次 universe**；[输入预检][input-validation]要求该固定集合的每个成员在全部预热和运行交易日都有有效 OHLC。它能抓缺输入，但不能表达 2014 后成立 ETF、运行中上市/退出、真实停牌不成交及当时成员变化。把这些行简单补零、前填成可成交价格或丢掉证券都会改变研究样本或账户价值。

最小正确工作是让已声明任务按日期消费成员及生命周期：未上市不参与、预热不足不参与信号且有理由、真正缺证阻断；持仓停牌与无法估值分别处理，退市/终止上市保留资产及明确退出/估值事实，不能按最后报价虚构清算。显式固定候选池可以保留，但报告必须承认选择偏差，不能冒充历史全市场选股。现有冻结研究 feed 已有 [membership 数据边界][research-feed]，可以复用其合同和反例；不因此把严格资格移植给普通数据。

工厂目前以 `2 × lookback` 自然日估算加载窗口，再验证足够交易日；2014 首段与长假边界要按真实交易日取得前置数据。现成股票 seed 使用 252 日窗口，不能以“2013 有最早一行”推定所有成员都有足够预热。[加载与因子注入][ordinary-factory]、[三类种子策略][seed-specs]

## 5. 规则和费用需要历史分段，现有接口可承担，不必新建规则平台

[InMemoryRuleProvider][rule-provider]已经接受多版本交易规则和费用，按生效区间查找；普通构造器目前每证券只装一个版本。应先为实际消费的证券类别补齐带来源的区间，按交易日期注入。接口的生效日期选择本身不证明历史当时可得性。

以下为本轮核实的**必要断点及范围**，不是完整生产规则表：

| 范围/断点 | 一手证据支持的事实 | 仍需补证或限制 |
| --- | --- | --- |
| A 股印花税，2023-08-28 | 2008-09-19 起卖方 1‰，2023-08-28 起减半；2014 至该日前后不能同费率。[财政部 2008][stamp-2008]、[财政部 2023][stamp-2023] | 不把股票印花税直接套给 ETF；股息税是另一制度 |
| A 股过户费，2015-08-01、2022-04-29 | 中国结算记载 2015-08-01 才统一双边成交额 0.02‰，2022 再减半；2022 官方收费表为 0.01‰。[中国结算大事记][csdc-history]、[收费表][csdc-fees] | 2022 精确起日由实际收费方[国金证券通知][gj-transfer]交叉核对；本轮未取得中国结算原通知独立页。2014–2015-07-31 沪深计费基数、最低费与包费关系仍待原规则 |
| 科创板、创业板、主板注册制 | 科创板 2019 上市前五日不限幅、随后 20%；创业板及指定基金 2020-08-24 切换 20%，有退市过渡例外；主板注册制首批 2023-04-10，上新前五日制度改变。[上交所科创说明][star-rules]、[深交所发布会][chinext-rules]、[主板首批上市][mainboard-date]、[2023 手册][mainboard-rules] | 必须同时看板块、状态、日期和特例；2014-06-13 发布的首日机制另有[申报区间规则][ipo-2014]，2014 更早区间仍须另核；现“上市满 30 自然日”是受限研究条件，不能当历史制度 |
| ETF 历史品种规则 | 上交所符合条件的跨境 ETF 当日回转从 2015-01-19 起；深交所 20% 基金有指数成分/合同条件及名单。[上交所通知][etf-t0]、[深交所条件][etf-limits] | 按历史品种和名单，不按代码前缀或今天分类回填；此处是境内上市 ETF 分类边界，并未扩大为海外股票研究 |
| 2026 年规则修订 | 当前证据包已列沪深 2026 修订及 7 月 6 日实施，共有普通现金证券规则才被有限复用。[现规则依据][ordinary-evidence] | 2014–2026 全区间还应逐次核对中间修订、暂缓条款、报价单位/订单数量/限价例外；本表不假称穷尽 |

佣金、最低费、滑点和成交容量是研究假设/账户费率，不应伪装成交易所统一规定。当前最低 5 元是保守假设。须说明是否包含规费/过户费，避免重复扣费；日线 OHLC 也不能证明涨停可买、跌停可卖或精确成交队列。[现规则与费用声明][ordinary-evidence]

## 6. 公司行动必须先有事件事实，再接现金、份额与可卖状态

当前普通市场变换[遇复权因子变化即拒绝][ordinary-rules]；引擎 [step chain][engine-steps]没有独立公司行动步骤。更关键的是：现 [股票分红适配器][dividend-adapter]只请求 `ex_date/cash_div/record_date/ann_date/div_proc`，未请求派息日、红股上市日、送转数量及税前金额，而 [Tushare 自有文档][tushare-dividend]确实定义这些字段。因此 dividend 的库存 ready 是既定披露用途的证明，不能直接升级为现金/股本会计就绪。

白名单内已有足够强的反例：510300 的 2025 分红，登记、除息、发放分别为 6 月 17、18、27 日；510500 在 2015-04-14 折算，4 月 13–14 日停牌、15 日复牌，且份额取整有具体规定。[510300 管理人公告][etf-cash]、[510500 管理人公告][etf-split]。中国结算还记载沪市权益分派新增股份从 2023-04-20 才由原 R+2 提前到 R+1 流通。[中国结算记录][csdc-history]

**工程推论：**原价成交与估值、信号用按 cutoff 复权的历史，需与事件权益登记、应收/到账现金、总份额/可卖份额、零碎份额和成本处理一致。应收尚未到账不能提前再投资，除息不能凭空损失应收权益，股息不能再当外部入金重复贡献收益。因子变化只能提示需核事件，不能唯一反推现金分红、送转、配股或折算方案。

可复用 [Manual 事件词汇][ledger-types]、[份额及成本投影][ledger-projection]与[收益对外部流分类][account-returns]的已验证语义，以及[事件/因子比率对账][adjustment-checker]；后者是 DQ 推导，不是事件入账器，也没有因此获得付款/可卖时点。不要把 Manual 账本直接塞入回测边界。股票分红税、送转税、配股认购/现金需求、退市后价值等未核全的情形继续明确不支持并保留持仓，不可默认为零；覆盖三类长期任务所必经事件后才替换当前全拒绝。

## 7. ETF 应按品种与生命周期入池，NAV、复权和事件各有用途

现普通白名单只声明境内股票 ETF；[上交所 ETF 问答][etf-faq]明确股票 ETF 为 T+1，债券、黄金、跨境、货币等部分品种可 T+0；买卖单位与报价单位也有明确定义。国内上市但跟踪海外资产的 ETF 仍需要品类、时区/停牌和日历解释，不能因为统一叫 ETF 就同规则。首批具体 ETF 品种集合需要实施规格锁定，未纳入类型要可见地排除，不能伪装成全 ETF 已通过。

ETF 二级市场价格决定本范围内成交；单位/累计净值、跟踪指数和 PCF 不能互相代替，也无需为本任务建设一级申赎模拟。现 [47 项库存][inventory]未证明 ETF 分红/折算完整事件链；本次在生产 packages/apps/contracts 检索未找到 `fund_div` 消费。供应商[基金分红接口][tushare-fund-div]可作为补证候选，具有登记/除息/派息与每份现金字段，但是否覆盖目标 ETF 的历史、交易代码映射及修订仍待实际核对；有接口不等于库存已到位，也不替代折算公告。

## 8. 三类任务优先复用已有模块，补足运行证据与失败恢复

| 任务 | 可复用能力 | 最小必补消费 |
| --- | --- | --- |
| 股票多因子选股 | stock selection seed、quality_roe/value_pe/momentum、表达式编译；现工厂已注入财务与分类快照 | 当时成员/状态、财报公布与修订、历史交易和费用规则、公司行动/退出处理；不能把全市场选股缩成幸存五股 |
| ETF 轮动 | industry rotation seed、排序/权重/再平衡和通用回测 | 晚成立/终止上市与预热、品类/行业映射、历史限价/结算、分红折算、成员覆盖报告 |
| ETF 趋势 | trend swing seed、信号窗口和执行/风险组件 | 连续原价与当期复权窗口、停牌/限价不能成交、持仓事件和成本；“只挑无事件区间”不构成 2014 验收 |

依据：[种子策略注册][seed-specs]、[普通工厂数据注入][ordinary-factory]。自由 Python、ML/Agent 不是上述依赖的前置条件。也不能反向把 seed 存在写成图形化策略编辑器已经可用。

已有普通结果会冻结实际行情/复权/基准来源，NAV 已扣成本，基准跟随运行结果而非展示时读最新值，应保留。[现结果约定][ordinary-evidence]。补齐时将规则版本、成员/事件证据、范围缺口及普通历史重建资格一并传至报告和导出。缺证提示要指明证券、日期、原因和恢复动作；保留配置后补证重跑，不能静默缩短日期、换池、跳过持仓或返回零收益成功。事件重复、修订与中断恢复要证明不会重复派现/送股；补证后产生新输入身份，旧报告保持原貌。

## 9. 验收用代表任务与制度边界，不以成功次数代替正确性

以下是后续实施验收的样本类型，不是本研究已完成的测试，也不要求本阶段认证全市场每天：

| 样本类别 | 应看到的证据 |
| --- | --- |
| 三类 2014 起任务 | 明确声明池与生命周期，运行至所声明末日；晚成立者正确进入；股票任务不只五股；输出曲线、持仓、成交、成本、年度结果及可解释排除 |
| 历史规则切换 | 2015/2022 过户费、2023 印花税切换前后逐笔手算；板块/IPO/ST/退市过渡样本按真实有效日；未核区间拒绝 |
| 公司行动 | 510300 登记持仓/除息应收/现金到账；510500 折算数量/取整/停复牌；股票送转可卖日期、重复和修订事件；现金+应收+资产价值可对账 |
| 上市、退出与成员 | 晚上市无上市前成交，预热不足可解释；历史退市者不消失；成员切换不借未来名单；未有退出事实不能虚构清算 |
| 交易/结算日 | 长假、周末、首末日、T+1 可卖与卖出资金可再用分开；足量预热；信号不读未来执行日收盘 |
| 缺失和未知 | 已知停牌、真缺 bar、无 status、零成交、缺因子/基准、缺事件分别提示；null 不作零，缺报价不偷偷前填成交 |
| ETF 品种边界 | 纳入的 T+1/T+0、10%/20% 类别及其历史切换；未纳入类型准确阻断；NAV 不替代可成交价 |
| 因子及冻结身份 | 财报公告后才可用、修订冻结、未来哨兵、成员/因子来源缺失拒绝；更新库存不改变旧报告；普通重建不显示严格资格 |
| 页面、恢复与导出 | 用户从条件/公式进入同一策略版本，任务失败能定位和重跑，结果比较保持区间与口径，CSV/报告与运行逐值对拍；恢复不重复事件；然后再安排真人日用 |

## 最小依赖路线

| 顺序 | 可规划交付边界 | 进入下一步所需证据 |
| --- | --- | --- |
| A：冻结三类任务的历史合同 | 保持 2014 目标；声明证券/ETF 类型、生命周期、信号/执行时间、普通重建资格与输出；记录尚缺证区间 | 样本分母与拒绝/恢复行为明确；不新增自由 Python 或研究平台 |
| B：补足实际消费的历史事实 | 名册/成员/状态与规则费率分段；股票分红字段、ETF 分红/折算等事件；原有采集/存储优先复用 | 每项证据绑定来源、日期、单位/空值、修订及缺口；2014 状态与早期费率未知保持阻断 |
| C：接入生命周期与会计 | 普通 feed 按日期消费成员；原价/复权分离；持仓事件、应收/现金/份额/可卖状态及中断恢复 | 手算小样本和反例正确；不存在假成交、重复事件、资产消失或临时移除 PIT 守卫 |
| D：接普通工作台和结果 | 复用模板/受控表达式、运行身份、报告/比较；提供具体缺证提示和补证重跑 | 三类 2014 起任务从页面完成，导出同源同值；失败与旧结果可追溯 |
| E：逐任务验收 | 上述边界样本与范围覆盖共同验收，记录未支持部分；保留严格历史未认证 | 用户验收具体任务后再决定日用周期；研究票关闭不代表产品/数据资格通过 |

B 的规则取证、状态缺口核实和事件字段核实可并行；C 依赖 B 的事实合同，D 可先准备明确的缺证反馈，但不能先宣传历史可用。只对新消费者确有必要的 schema/数据补齐另行实施并按仓库授权交付。

仍需在相应实施规格中明确：2014–2016 状态的可靠补证来源；2014–2015 早期沪深收费细则与个人佣金包费；个人股票分红税/配股及无法估值退出的处理边界；首批 ETF 类型及具体池。它们是精确缺证或会计选择，不改变已经确认的 2014 目标，也不由本研究替用户作资产策略选择。

## 核验范围

源码调用链、普通规则、数据覆盖记录、已有 feed/规则/账本/策略复用点已读；制度与事件由独立背景研究者核查一手来源，并对关键财政部、中国结算和两只 ETF 原公告复核。仅文档校验与提交门禁；未采集生产数据、未运行 2014 回测、未做页面或真人日用验收。外部页面读取日期 2026-11-08；今天可读公告不证明 Ditto 当年已有该公告快照。

[web-run]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/apps/web/src/features/backtest/api/backtests.ts#L4
[api-run]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/apps/backend/src/ditto_apps/api/routes/backtest_run_routes.py#L186
[job-run]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/apps/backend/src/ditto_apps/jobs/flows/backtest.py#L193
[process-run]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/application/src/ditto_application/processes/execution/strategy_run_process.py#L423
[ordinary-factory]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/application/src/ditto_application/builders/service_factory.py#L496
[ordinary-builder]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/application/src/ditto_application/builders/ordinary_backtest.py#L19
[ordinary-rules]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/execution/src/ditto_execution/reality/ordinary_equity.py#L38
[frozen-factory]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/application/src/ditto_application/builders/research_backtest_factory.py#L217
[inventory]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/docs/data/readiness-711-2026-11.md#L36
[frozen-scope]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/docs/data/readiness-freeze-2026-11.md#L54
[time-lanes]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/docs/data/pit-time-semantics.md#L141
[qualification]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/docs/data/readiness-711-2026-11.md#L6
[history-feed]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/backtest/src/ditto_backtest/data_feed.py#L552
[input-validation]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/backtest/src/ditto_backtest/data_feed.py#L340
[research-feed]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/application/src/ditto_application/processes/experiments/research_data_feed.py#L97
[seed-specs]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/strategy/src/ditto_strategy/alpha/seeds.py#L26
[rule-provider]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/execution/src/ditto_execution/rules.py#L27
[ordinary-evidence]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/docs/evidence/ordinary-backtest-20261108/rules.md#L8
[engine-steps]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/backtest/src/ditto_backtest/engine_steps.py#L329
[dividend-adapter]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/data/src/ditto_data/sources/tushare/adapters/fundamental.py#L484
[ledger-types]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/portfolio/src/ditto_portfolio/account_ledger.py#L98
[ledger-projection]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/portfolio/src/ditto_portfolio/account_projection.py#L387
[account-returns]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/portfolio/src/ditto_portfolio/account_returns.py#L1
[adjustment-checker]: https://github.com/cosmos-arc/ditto/blob/f331761e66438921723254646f469a4c3eaef23e/packages/data/src/ditto_data/quality/checkers/adjustment_events.py#L1
[stamp-2008]: https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm
[stamp-2023]: https://m.mof.gov.cn/czxw/202308/t20230827_3904226.htm
[csdc-history]: https://www.chinaclear.cn/zdjs/dsj/about_dsj.shtml
[csdc-fees]: https://www.chinaclear.cn/zdjs/editor_file/20220701154723234.pdf
[gj-transfer]: https://download.gjzq.com.cn/gonggao/nr/CSDC_About_Transfer_Fee_Decrease_Tips.html
[star-rules]: https://www.sse.com.cn/star/media/news/c/c_20190719_4866789.shtml
[chinext-rules]: https://www.szse.cn/aboutus/trends/conference/t20200821_580925.html
[mainboard-date]: https://big5.sse.com.cn/site/cht/www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20230404_5719112.shtml
[mainboard-rules]: https://investor.szse.cn/institute/rules/t20230629_601434.html
[ipo-2014]: https://www.szse.cn/aboutus/trends/news/t20140613_518480.html
[etf-t0]: https://english.sse.com.cn/news/newsrelease/c/4947611.shtml
[etf-limits]: https://investor.szse.cn/knowledge/t20201118_583202.html
[etf-faq]: https://www.sse.com.cn/assortment/fund/etf/question/
[etf-cash]: https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-06-11/510300_20250611_ZAU4.pdf
[etf-split]: https://www.sse.com.cn/disclosure/fund/announcement/c/2015-04-12/510500_20150413_1.pdf
[tushare-dividend]: https://tushare.pro/document/2?doc_id=103
[tushare-fund-div]: https://tushare.pro/document/2?doc_id=120
