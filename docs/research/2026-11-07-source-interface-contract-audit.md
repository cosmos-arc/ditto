# 数据接口选择与调用契约审计（2026-11-07）

## 范围与证据等级

本报告包含接口清点、当前官方文档核查与 #713 实施结果；下方逐接口表保留审计时的基线描述，最终处置见本节。初读源码基线为 `6a504cf1b964590b79c00030cb6c50786e137619`；#712 合并后工作树基线为 `99b92f1f135b5448021decbb54ba3b1e0f1a43ca`，#708 已关闭，本报告服务于后续 #713。核查时间为 2026-11-07。已完成下述只读真实源复核、代码修复及用户另行授权的申万存量单位修正；未更改账号、源路由或依赖。

- [覆盖合同](../data/coverage-contract.yaml) 基线中有 **58 个 Tushare provider API 名称**；结合实际字符串、动态 API 选择及辅助适配器补齐为 **69 个 Tushare 调用入口**。本批将其中四个财务VIP补入覆盖合同，合同现为62个名称。新增清点的 11 个是 `balancesheet_vip/income_vip/cashflow_vip/fina_indicator_vip/bse_mapping/sw_daily/index_member/yc_cb/shibor_lpr/libor/hibor`。
- 另有 **11 个 Fuyao 固定 REST 入口、1 个 FRED observations 入口、1 个 Sina 日 K 入口**，共 **82 个固定入口**；Fuyao 返回的预签名文件 GET 单列为传输步骤。辅助、可选、未接摄取计划的入口也列入，但不把它们算成当前日更消费者。仅在页宽表出现、无实际 query 的 `etf_limit` 不计入。
- **官方已核验**：本次在线读取的 59 个 Tushare 专页覆盖 65 个 API 名称（六个 VIP 在标准接口页面说明）；Fuyao 官方 [LLM 索引](https://fuyao.aicubes.cn/llms.txt) / [全文](https://fuyao.aicubes.cn/llms-full.txt) 及下表对应页面；FRED 官方 API 文档。
- **LIVE 历史证据**：[2026-11-06-708 目录](../data/evidence/2026-11-06-708/)，其中记录时间包含 2026-11-07；只证明当时配置的传输及参数表现，不能冒充 Tushare 直连普遍契约。此前研究仅作索引，不作当前官方证据。
- **当前未知**：`rights/csrc_industrial/index_member/hk_hold` 未得到可用的当前专页。旧 [index_member doc182](https://tushare.pro/document/2?doc_id=182) / [hk_hold doc188](https://tushare.pro/document/2?doc_id=188) 本次返回 404。文档缺失不等于 API 不存在；现有不可用/排除状态仍以已记录实测和消费者边界为准。

## 实施结果与验证边界

[真实验证证据](../data/evidence/2026-11-07-713/interface-validation.json)区分当前网络响应、保留快照和离线检查。基线82个入口逐一核对；新增复用五个 Fuyao batch 路径后，固定入口为87个（原单码入口仍服务单目标请求）。不宣称87个都重新跑过全历史。

| 发现 | 最终处置 | 验证 |
|---|---|---|
| F1 | 重试下移到失败 HTTP 页；确定性参数/4xx不重试，408/网络/5xx仍有界重试；分页损坏只保留一次既有换页宽尝试，500下限不无限循环；公告日等待仅处理明确限流。 | 参数错误1次；瞬态尾页不重发首页；速度/线程限流显式分类；无进展拒绝。 |
| F2 | 删除VIP指标手写页循环，复用共享分页与原披露选版。 | 2026Q3原始6701行，选版后5590条披露/5588码，2次请求含尾探；短页有后继离线反例由499恢复600唯一披露。 |
| F3 | 龙虎榜范围按精确日期请求；两处分红adapter去掉无效范围参数，按公告日期本地筛选。已有公开分红facade与公告日批量路径沿用。 | 龙虎榜两日5/50条；600519分红原范围返回全部106行，正确公告范围6行；未来公告哨兵排除，除权日保持。 |
| F4 | 现有股票、指数、三表多码对账复用原生十码batch；身份、缺组/重组、每码日期/单位守卫保留。 | 五路径各两码：单码与批量最终帧全字段相同；12码离线2请求，缺组/重复组不污染其余码。单码仍走原接口，指数历史说明改5年。 |
| F5 | 标准fina页宽100；SW4000、龙虎榜10000；明确官方上限与历史传输实测页宽来源。 | 不把VIP改成标准100；其余已有实测9000/10000保留，短页探测仍启用。 |
| F6 | 更正覆盖合同的“官方20180102”归属；保留实测起点及数据。 | 一月68420行/3175码/22日与2026-10-10保留快照逐行一致；当前官方称20180201。 |
| F7 | FRED声明总数或offset与完整响应不符即拒绝。 | 截断文档单次失败、不重试；未新增无当前需求的分页框架。 |
| F10 | 财务指标单码优先已验证VIP、完整历史按公告窗筛选；去掉错误旧helper分流；确定性接口名错误不重试。 | 两版全历史139行等价；旧报告新披露、未来哨兵、筛码忽略拒绝测试；daily_vip不可用明确留证。 |
| F8/F9 | 多SW目标按市场日批量并筛冻结目标；单码/批量共享万股→手、万元→千元换算。 | 三个阳性代码与单码结果完全一致，6→2请求；官方样例与实际raw相同，量×100、额×10。 |

**存量修正已执行**：用户明确授权后，2026-11-07 03:38 UTC 沿现有身份、L1/L2、年锁、写入与证据登记流程修复SW旧数据481557行/155码（13个年分区）。只有量×100、额×10，其他字段和非SW行逐值不变；13年真实reader与application消费者均相同。保留13个原分区及一致性SQLite备份，169个旧载荷和194个旧指数快照不变，新增13个快照明确记载“本地修正，非新HTTP观察”。锁内校验前像；计划、演练、脚本、预制和备份散列均绑定；重复应用及旧量额普通重放已验证拒绝。[修复清单](../data/evidence/2026-11-07-713/sw-unit-repair-plan.json)、[实际回执](../data/evidence/2026-11-07-713/sw-unit-repair-applied.json)。旧快照保持原始单位，不能因canonical已修好而宣称旧快照也已归一。

#708 的388只NAV持续分页失败、缺失发布证明和各源历史限制继续成立；本批没有通过放宽守卫、扩大并发或更换账号消除这些限制。对于没有当前可靠官方契约的4个Tushare入口及Sina，保留原限制而非推测批量/分页能力。未发现问题的入口维持已有正确调用，逐项理由见下表。

## VIP 与普通接口逐项选择

按用户要求，69个Tushare入口全部核对VIP替代，不限于财务指标。下表新增逐项选型列；[VIP复核证据](../data/evidence/2026-11-07-713/vip-selection-validation.json)保存59个官方专页的时间/散列、候选实测及边界。六对财务共12个入口；daily另有官方具名VIP候选；52个当前专页没有找到具名VIP替代；4个专页未知。后两类不等于证明服务端不存在VIP，不能据任意动态SDK方法猜测名称。

| 接口族 | 标准 / VIP最低积分 | 日期范围 | VIP页宽依据与当前选择 |
|---|---|---|---|
| income / balancesheet / cashflow | 各2000 / 5000 | 公告日期；period为报告期 | 市场任务优先各VIP，请求9000为历史配置传输实测，非官方通用上限；单码原标准路径仍有效，未证明切换能减少现有单页请求。 |
| fina_indicator | 2000 / 5000 | **报告期**，不等于公告日期 | 市场及单码均优先VIP；标准100与VIP请求10000独立。单码600519全历史139行两版全字段相等；VIP筛码有效，公告窗口在取尽后本地过滤；错误返回其他代码即拒绝。标准adapter保留为明确低权限兼容入口，不对错误自动降级。 |
| forecast | 2000 / 5000 | 公告日期 | 市场公告日优先forecast_vip；标准3500不能套VIP，VIP当前请求2000+续探，独立硬顶未知。单码标准合法，未证明单页请求的切换收益。 |
| express | 2000 / 5000 | 公告日期 | 市场公告日优先express_vip；两者未公布独立硬顶，当前各自默认2000+续探；单码标准合法。 |

六对权限和“参数一致”的依据分别为[利润表](https://tushare.pro/document/2?doc_id=33)、[资产负债表](https://tushare.pro/document/2?doc_id=36)、[现金流量表](https://tushare.pro/document/2?doc_id=44)、[财务指标](https://tushare.pro/document/2?doc_id=79)、[预告](https://tushare.pro/document/2?doc_id=45)、[快报](https://tushare.pro/document/2?doc_id=46)。已合并fina新旧helper为同一正确分流；修复单码公告窗误传报告期窗，测试保留“旧报告的新披露”并拒绝未来/空公告日期。

[官方更新记录](https://tushare.pro/document/1?doc_id=9)于2025-01-09提到daily_vip可单次10000；标准daily专页仍为6000。[官方SDK可见源码](https://github.com/waditu/tushare/blob/master/tushare/pro/client.py)直接把方法名作为api_name，无自动别名映射。本次当前配置通道实测daily_vip(trade_date=20261105,limit=10000,offset=0)返回50101“请指定正确的接口名”；不能因官方有名称就切换到当前不可用入口。普通daily同日5572行且尾探0，保持可用路径。该确定性接口名错误现只请求一次，未知50101仍不一概判永久。

Fuyao/FRED/Sina同样依据各自原生批量/权限契约，不套用Tushare的VIP概念；五种Fuyao多码批量的实际采用与等价证据见本报告。

## 优先处理的问题

| 编号 / 优先级 | 当前可验证事实与影响 | 最小处理及验证边界 |
|---|---|---|
| F1 / 高 | [Tushare client](../../packages/data/src/ditto_data/sources/tushare/client.py) 在整次 query 外对所有 SourceFetchError 重试三次，包括确定性参数错误和分页损坏。#708 [offset 边界探针](../data/evidence/2026-11-06-708/fund-oct27-boundary-probe.json) 于 2026-11-07 01:30 UTC 记录 offset=102000/102001 参数校验失败；任务执行已观察到整段重取。 [http_utils](../../packages/data/src/ditto_data/sources/tushare/utils/http_utils.py) 仅识别两种中文频次信息，漏掉此次“速度过快/IP超限”。 | 复用现有异常分类，把已知确定性参数/页损坏从整查询重试中排除；限流单独识别与退避。保留网络/服务瞬态重试。官方没有完整错误码表，不能将所有非零码或所有 code=2000 一概判永久。验证确定性失败不会重取已完成页，瞬态仍可重试，已知限流文字被正确分类。 |
| F2 / 高 | [fundamental adapter](../../packages/data/src/ditto_data/sources/tushare/adapters/fundamental.py) 的 fina_indicator_vip 手写 limit=2000/offset 循环绕过共享短页续探与进展守卫；短页可能截断、无进展满页可能无限循环。其“共享守卫拒收页内重复”注释已过时：共享 client 现仅告警并保留页内业务重复。 | 删除该手写循环，复用现有 client.query 自动分页，保留后续披露键去重/update_flag 选版。用含页内重复、短页有后继、忽略 offset 的响应验证完整性/有界失败；一个真实 VIP 季度核对唯一披露集合，勿新增第二套分页框架。 |
| F3 / 中 | 当前官方 top_list/top_inst 只列必填 trade_date 与可选 ts_code，dividend 只列代码/事件日选择器；[capital_flows](../../packages/data/src/ditto_data/sources/tushare/adapters/capital_flows.py)、[capital_market](../../packages/data/src/ditto_data/sources/tushare/adapters/capital_market.py) 及另一 dividend 入口存在 start/end 参数路径。文档未承诺这些范围有效。 | 先追踪真实消费者；对一个短窗口比较范围请求与逐事件日并集，证实不支持或忽略后才改成官方日期切片及本地筛选。不能仅因表中写 ts_code 必选，就否定 top10_* 已实测有效的市场公告日批量。 |
| F4 / 中 | [Fuyao source](../../packages/data/src/ditto_data/sources/fuyao/source.py) 指数与财务对账逐码请求；当前官方有最多 10 码的五种 historical/financial batch，见下文。当前指数方法注释写 ≤10 年，官方指数历史实际为近 5 年。 | 先确认多码调用规模，选一个现有多码消费者接入原生 batch，保留每码缺失/失败、日期边界及字段单位；验证批量与单码结果一致。请求数理论最多降至约 1/10，不作为已测性能结果。修正 5 年说明，不扩大当前单日对账窗口。 |
| F5 / 中 | [pagination 表](../../packages/data/src/ditto_data/sources/tushare/utils/pagination.py) 将官方限制和 2026-10-10/11/19 配置传输实测值混称“已核实官方”，并称最低已消费上限为 2000；当前官方 fina_indicator=100、stock_st/pledge_stat/fx_daily/bse_mapping=1000 已反证。标准 fina_indicator 不在表中，默认 2000，短页降档下限 500 无法覆盖官方 100。 | 注明配置值的证据来源/时间；标准 fina 的已知低上限用精确页宽验证。不要把 VIP 当标准版的 100，也不要把已有 LIVE 优化的市场日 10000/财表 VIP 9000 盲目改小。复用已有短页续探/跨页进展守卫。 |
| F6 / 中 | 当前 cyq_perf 官方起点 2018-02-01；覆盖合同将 2018-01-02 写成“官方源起点”。 | 先检查已有一月历史及证据，再修正来源描述或覆盖边界；不据当前网页删除已存在数据，不伪造早期有源。 |
| F7 / 低 | [FRED client](../../packages/data/src/ditto_data/sources/fred/client.py) 单次请求，解码后丢弃 count/offset/limit；官方有 100000 行上限。当前短历史窗口未证明发生截断。 | 最小可先校验响应 count 与原始返回条数，发现不足就拒绝完整性声明；确有超过一页的消费者再加分页。沿用现有永久/瞬态错误区分。 |
| F8 / 条件优化 | [index adapter](../../packages/data/src/ditto_data/sources/tushare/adapters/index.py) 对所有目标代码逐码拉取，包含 .SI；sw_daily 官方例子明确支持 trade_date 全申万市场（4000 行）。index_daily 则仍必填代码。 | 仅当真实目标含多只申万指数时，按日一次获取并筛目标集合，保留目标缺失/越日/重复检查；普通指数不能照搬。单位同时按 F9 核实修正。 |
| F9 / 高 | [sw_daily 官方字段](https://tushare.pro/document/2?doc_id=327) 为 vol 万股、amount 万元；当前 index adapter 的 _query_daily 对 .SI 只补 pre_close/改涨幅列，未换算量额，就进入 [共同 OHLCV mapping](../../packages/data/src/ditto_data/sources/tushare/processors/mappings/common.py)；后者明确仓库口径为 volume 手、amount 千元且原值入库。源码与官方存在 100 倍量、10 倍额的单位冲突。 | 以一组真实源样本核对当前传输单位后，在 SW 原始帧归一入口将 vol×100、amount×10；单码与市场日共用该入口。测试校验已知数值而非仅有列/非空；任何既有数据修正需先盘点受影响 .SI 日期与实际存储口径。 |

#708 已完成的 fund_portfolio 三选一、真实截止日、fund_nav accum_nav 字段以及已执行的市场日/代码批次，不作为本报告待修重复项。源返回空、不支持、权限不足、分页损坏及真正无数据应继续分开记录。

F9 的有界对拍锚：[doc327 当前示例](https://tushare.pro/document/2?doc_id=327) 调用日期为 `20230705`，示例输出 `801001.SI` 的 vol=`275984.00`、`801002.SI` 的 vol=`1540720.00`，单位万股。示例输出未显示 trade_date/amount，因此日期来自同页调用，不能将其当成本次实时获取的完整历史行情；金额没有可引用的精确样本。申万[一手行情页面](https://www.swsresearch.com/institute_sw/allIndex/releasedIndex) 搜索缓存表头使用百万股/百万元，但本次直取遭 HTTP 508/502，缓存数据无可核对交易日，不能拿缓存量额与指定日对拍。当前传输是否预先换算仍待实现阶段短探针确认。

## Tushare 共用契约

[Tushare HTTP 说明](https://tushare.pro/document/1?doc_id=130) 规定 POST JSON 的 api_name/params/fields，fields 是逗号字段列表；响应含 code/msg/data.fields/data.items，仅明确举出 2002 权限错误，未提供穷举错误分类。精确字段集应继续保留数据键、公告/报告日期、修订和归一化所需列；不可为省字节删掉取尽或选版依据。

[2026-11-05 官方变更](https://tushare.pro/document/1?doc_id=9) 明确 fund_portfolio 至少选代码/公告日/报告期之一、daily 单码、index_weight 必填指数代码；不能从单个“必选”单元格脱离互为替代的说明推导逐码义务。[积分频次表](https://tushare.pro/document/1?doc_id=290) 属官方账户政策，不证明当前配置传输的可持续速率。[FAQ](https://tushare.pro/document/1?doc_id=122) 的超时重试建议也不授权对确定性坏参数无限/整段重放。

下表“上限”指当前专页所写单次行上限，不自动证明配置传输执行相同硬顶。多数专页只建议按代码/日期循环，未逐一明确 generic offset；`fund_adj` 明列 limit/offset。共享分页的实际可用性仍需已有 LIVE 证据和运行时进展守卫；“短页”只有在页宽、续探和分页响应均可信时才可认作取尽。除标出的互斥/至少一项外，不自行发明参数限制。Tushare 日期默认 YYYYMMDD，宏观另按季度/月，外汇日期为 GMT。更新时刻不是未经公告证据就可回填的 PIT 可见时刻。

### 股票、资金与事件（22）

| 接口 / 当前官方证据 | 合法选择与批量边界 | 上限 / 更新 | 字段、单位与日期 | 当前代码 / 处理建议 | VIP 选择结论 |
|---|---|---|---|---|---|
| [stock_basic](https://tushare.pro/document/2?doc_id=25)（已核验） | 列表；ts_code/market/list_status/exchange 可筛选，默认 L；代码单值 | 6000；50 次/分；静态表建议缓存 | 代码、上市/退市日、交易所；不可只取 L 当历史全集 | stock；现有状态分组保留 | 原生选择器；当前专页无具名VIP证据 |
| [trade_cal](https://tushare.pro/document/2?doc_id=26)（已核验） | exchange + start_date/end_date；默认 SSE；is_open 可筛选 | 上限未标；按年度/窗口 | cal_date 是交易日历日；pretrade_date 不等于自然日前一日 | stock；沿用交易所日历 | 原生选择器；当前专页无具名VIP证据 |
| [stock_st](https://tushare.pro/document/2?doc_id=397)（已核验） | ts_code/trade_date/start_date/end_date 可筛选 | 1000；每日 09:20；20000101 起 | ST 名单时点；不是完整上市状态历史 | stock；保留历史证据与分页 | 原生选择器；当前专页无具名VIP证据 |
| [namechange](https://tushare.pro/document/2?doc_id=100)（已核验） | ts_code；start_date/end_date 为公告区间 | 上限/固定时刻未标；事件型 | ann_date 与更名起止有效日不同 | stock；保留三类日期 | 原生选择器；当前专页无具名VIP证据 |
| [bse_mapping](https://tushare.pro/document/2?doc_id=375)（已核验） | o_code/n_code 可筛选；辅助全量映射 | 1000；更码事件 | 旧码、新码、生效日期；不可抹掉旧代码历史 | stock；辅助入口，未列在 58 项中 | 原生选择器；当前专页无具名VIP证据 |
| [bak_basic](https://tushare.pro/document/2?doc_id=262)（已核验） | trade_date/ts_code；表中未列日期范围 | 7000；2016 年起；日频 | 股本亿股、资产亿元、每股指标元；不是 daily_basic 的万单位 | stock；全市场日优先，现有 10000 为传输实测 | 原生选择器；当前专页无具名VIP证据 |
| [daily](https://tushare.pro/document/2?doc_id=27)（已核验） | 单码历史或 trade_date 全市场；start_date/end_date；当前变更说明禁止逗号多码 | 6000；交易日 15–16 点 | 未复权；价格元、vol 手、amount 千元；停牌无行 | stock；不将单码改成逗号批码 | `daily_vip` 当前通道拒绝接口名；保留daily |
| [adj_factor](https://tushare.pro/document/2?doc_id=28)（已核验） | 单码 + 日期范围，或全市场 trade_date | 上限未标；09:15–09:20 | 复权因子无量纲；不能作为原始价格 | stock；市场日批量已存在 | 原生选择器；当前专页无具名VIP证据 |
| [daily_basic](https://tushare.pro/document/2?doc_id=32)（已核验） | ts_code/trade_date 二选一；范围可用；必选列 Y 不能脱离二选一说明 | 6000；15–17 点 | 市值万元、股数万股、比例 %；与指数估值单位不同 | capital_market；市场日批量正确 | 原生选择器；当前专页无具名VIP证据 |
| [stk_limit](https://tushare.pro/document/2?doc_id=183)（已核验） | ts_code/trade_date/start_date/end_date | 5800；09:00；20070104 起 | 涨跌停价元；历史页面基金表述需结合变更说明 | stock；当前股票消费者不扩张 ETF 范围 | 原生选择器；当前专页无具名VIP证据 |
| [suspend_d](https://tushare.pro/document/2?doc_id=214)（已核验） | ts_code（页内称支持多码）/trade_date/范围；suspend_type S/R | 5000；不定期；20000103 起 | 停复牌事件及时间；不能以零行推出可交易 | stock；保留市场日与已证实的较大页宽 | 原生选择器；当前专页无具名VIP证据 |
| [cyq_perf](https://tushare.pro/document/2?doc_id=293)（已核验） | 表列 ts_code 必选；另列 trade_date/范围；市场日可用性有本地 LIVE 证据 | 6000；18–19 点；官方当前起点 20180201 | 成本分位数价格、winner_rate 比例；非真实全体投资者仓位 | capital_flows；覆盖合同 20180102 与当前官方不一致，先核实历史 | 原生选择器；当前专页无具名VIP证据 |
| [hsgt_top10](https://tushare.pro/document/2?doc_id=48)（已核验） | ts_code/trade_date 二选一；范围；market_type=1/3 | 上限未标；18–20 点 | 每日成交排名事件；amount 等金额元，rank 不是权重 | capital_flows；可按市场日 | 原生选择器；当前专页无具名VIP证据 |
| [top_list](https://tushare.pro/document/2?doc_id=106)（已核验） | trade_date 必选、ts_code 可选；未列 start_date/end_date | 10000；2005 年起；日榜 | 成交/净额等金额元；reason/重复事件键保留 | capital_flows；逐码范围调用须查实支持，见 F3 | 原生选择器；当前专页无具名VIP证据 |
| [top_inst](https://tushare.pro/document/2?doc_id=107)（已核验） | trade_date 必选、ts_code 可选；未列 start_date/end_date | 10000；日榜 | 机构买卖/净成交金额元，比例字段单独保留 | capital_flows；逐码范围调用须查实支持，见 F3 | 原生选择器；当前专页无具名VIP证据 |
| [moneyflow](https://tushare.pro/document/2?doc_id=170)（已核验） | 股票或时间至少一项；trade_date/范围可用 | 6000；2010 年起；日频 | 分档成交量手、金额万元；不是账户净流入 | capital_flows；市场日优先 | 原生选择器；当前专页无具名VIP证据 |
| [limit_list_d](https://tushare.pro/document/2?doc_id=298)（已核验） | trade_date/ts_code/limit_type(U/D/Z)/exchange/范围 | 2500；2020 年起；日频 | 封板/炸板事件；不包含 ST；成交额元 | stock；不外推至全体涨跌停 | 原生选择器；当前专页无具名VIP证据 |
| [top10_holders](https://tushare.pro/document/2?doc_id=61)（已核验） | 表列 ts_code 必选；ann_date/period/报告期范围；现有市场公告日 LIVE 支持 | 上限/固定更新时刻未标；披露事件 | hold_amount 股、hold_ratio %；报告期与公告日分开 | capital_flows；不据必选列禁用已验证公告日批量 | 原生选择器；当前专页无具名VIP证据 |
| [top10_floatholders](https://tushare.pro/document/2?doc_id=62)（已核验） | 同类公告日/报告期选择；表列 ts_code 必选与批量 LIVE 分开记录 | 上限/固定更新时刻未标；披露事件 | 持流通股数量股、比例 %；非全股东名册 | capital_flows；保留披露版本 | 原生选择器；当前专页无具名VIP证据 |
| [pledge_stat](https://tushare.pro/document/2?doc_id=110)（已核验） | ts_code/end_date；end_date 为快照日；未列 start_date | 1000；周快照 | 质押比例 %、股数万股；非日频事件空值 | capital_market；代码已说明忽略兼容范围参数并按快照取数 | 原生选择器；当前专页无具名VIP证据 |
| [repurchase](https://tushare.pro/document/2?doc_id=124)（已核验） | ann_date/start_date/end_date（公告范围）；输入表未列 ts_code | 不传参数默认 2000；事件更新 | 公告日、回购起止日不同；金额元、数量股、价格元 | capital_corporate；检验本地筛码，勿将公告日当实施日 | 原生选择器；当前专页无具名VIP证据 |
| [share_float](https://tushare.pro/document/2?doc_id=160)（已核验） | ts_code 或 ann_date 至少一项；float_date/范围为解禁日 | 6000；事件更新 | float_share 股、float_ratio %；公告与解禁日分开 | capital_corporate；二选一不解释成单码必填 | 原生选择器；当前专页无具名VIP证据 |

### 基金与 ETF（7）

| 接口 / 当前官方证据 | 合法选择与批量边界 | 上限 / 更新 | 字段、单位与日期 | 当前代码 / 处理建议 | VIP 选择结论 |
|---|---|---|---|---|---|
| [etf_basic](https://tushare.pro/document/2?doc_id=385)（已核验） | ts_code/index_code/list_date/list_status/exchange/mgr 可筛选 | 5000；基础信息随事件变化 | 上市状态/跟踪标的；不能覆盖场外基金 | etf；与 fund_basic 名册职责分开 | 原生选择器；当前专页无具名VIP证据 |
| [fund_daily](https://tushare.pro/document/2?doc_id=127)（已核验） | ts_code/trade_date/日期范围 | 5000；收盘后；20000103 起 | 价格元、vol 手、amount 千元；交易价不是 NAV | etf；市场日批量 | 原生选择器；当前专页无具名VIP证据 |
| [fund_adj](https://tushare.pro/document/2?doc_id=199)（已核验） | ts_code（页面支持多码）/trade_date/范围；明确列 limit/offset | 2000；日频 | 复权因子无量纲 | etf；保留独立字段与分页 | 原生选择器；当前专页无具名VIP证据 |
| [fund_basic](https://tushare.pro/document/2?doc_id=19)（已核验） | ts_code、market E/O、status D/I/L；默认市场 E | 15000；名册事件更新 | 成立/发行/上市/终止日期不同 | fundamental；现有两市场三状态共六组已修正 | 原生选择器；当前专页无具名VIP证据 |
| [fund_nav](https://tushare.pro/document/2?doc_id=119)（已核验） | ts_code 或 nav_date；market E/O 可选；范围是净值日期 | 上限/固定时刻未标；净值披露 | unit_nav 单位净值、accum_nav 累计净值、adj_nav 复权净值；ann_date 独立 | etf；#708 已修复字段；market=E 与当前传输空结果冲突见已有证据 | 原生选择器；当前专页无具名VIP证据 |
| [fund_portfolio](https://tushare.pro/document/2?doc_id=121)（已核验） | ts_code/ann_date/period 至少一项；symbol 可筛选；官方范围为报告期 | 上限未标；季度持仓披露 | amount 股、mkv 元、比例 %；不等于完整持仓/全部资产 | fundamental；#708 三选一已修；当前传输范围按公告表现另记 LIVE | 原生选择器；当前专页无具名VIP证据 |
| [fund_share](https://tushare.pro/document/2?doc_id=207)（已核验） | ts_code/trade_date/范围；market 是 SH/SZ，非 E/O | 2000；日频 | fd_share 万份；份额不是金额 | etf；市场日批量、专属单位 | 原生选择器；当前专页无具名VIP证据 |

### 指数与行业（10）

| 接口 / 当前官方证据 | 合法选择与批量边界 | 上限 / 更新 | 字段、单位与日期 | 当前代码 / 处理建议 | VIP 选择结论 |
|---|---|---|---|---|---|
| [index_basic](https://tushare.pro/document/2?doc_id=94)（已核验） | ts_code/symbol/name/market/publisher/category；symbol 支持多值；默认 SSE | 8000；18:00；1990 年起 | 指数代码/类别/发布方，不是成分成员 | index；按实际指数市场取名册 | 原生选择器；当前专页无具名VIP证据 |
| [index_daily](https://tushare.pro/document/2?doc_id=95)（已核验） | ts_code 必选；trade_date/范围；不含申万 | 上限未标；一般 18:00，部分指数次日下午 | 点位、vol 手、amount 千元；各指数到达时间不同 | index；申万已路由 sw_daily | 原生选择器；当前专页无具名VIP证据 |
| [index_weight](https://tushare.pro/document/2?doc_id=96)（已核验） | index_code 必选；trade_date/范围 | 上限未标；月度权重，当前说明月末交易日 | weight %；快照日期不是已知公告时间 | capital_index；按指数月分片，不能全市场无代码 | 原生选择器；当前专页无具名VIP证据 |
| [index_dailybasic](https://tushare.pro/document/2?doc_id=128)（已核验） | trade_date/ts_code/范围；有限大盘指数名单 | 专页未重申行上限；日频；200401 起 | 市值元、股数股、比例 %；不可套 daily_basic 万单位 | capital_market；页宽 3000 是当前表配置，非本次新增官方证明 | 原生选择器；当前专页无具名VIP证据 |
| [index_classify](https://tushare.pro/document/2?doc_id=181)（已核验） | index_code/level/parent_code；src=SW2014/SW2021，默认 SW2014 | 上限未标；分类版本事件 | 行业分级代码；正文 scr 为拼写不一致，输入表为 src | industry；显式 SW2021 已有 | 原生选择器；当前专页无具名VIP证据 |
| [index_member_all](https://tushare.pro/document/2?doc_id=335)（已核验） | l1/l2/l3/ts_code；is_new 默认 Y | 2000；成分调整事件 | 仅申万分级成分；in_date/out_date 不等于公告日 | industry；现有 Y/N 两组保留历史 | 原生选择器；当前专页无具名VIP证据 |
| [sw_daily](https://tushare.pro/document/2?doc_id=327)（已核验） | ts_code/trade_date/范围；申万 2021 版 | 4000；18:30；日频 | 点位、vol 万股、amount/市值万元；不得直接按 index_daily 的手/千元入库 | index；动态路由，58 清单未列；市场日可合批，当前量额转换缺失见 F9 | 原生选择器；当前专页无具名VIP证据 |
| [index_global](https://tushare.pro/document/2?doc_id=211)（已核验） | ts_code/trade_date/范围；21 个国际指数 | 4000；按各市场更新 | 点位、可空成交量额；境外交易日与本地发布时间不同 | index；保留各市场日期语义 | 原生选择器；当前专页无具名VIP证据 |
| `index_member`（当前未知；仅历史/代码） | 当前专页未核验；旧 doc_id=182 返回 404 | 未知；历史记录 | 不可将泛指数成员与申万分级成员互换 | capital_index；代码明确未接 ingestion plan、无当前消费者 | 专页未知；无已验证VIP替代 |
| `csrc_industrial`（当前未知；仅历史/代码） | 未找到当前官方专页；不得虚构 selector | 未知；历史记录 | 证监会分类与申万分类不同 | industry；保留已知不支持/回退边界 | 专页未知；无已验证VIP替代 |

### 财务与披露（13）

| 接口 / 当前官方证据 | 合法选择与批量边界 | 上限 / 更新 | 字段、单位与日期 | 当前代码 / 处理建议 | VIP 选择结论 |
|---|---|---|---|---|---|
| [income](https://tushare.pro/document/2?doc_id=33)（已核验） | 标准版 ts_code 必选；ann_date/f_ann_date/公告范围/period/report_type/comp_type | 标准版上限未标；季报披露 | 金额元；ann_date/f_ann_date 与 end_date 报告期分开 | fundamental；单码历史 | 市场优先 `income_vip`；单码保留标准 |
| [income_vip](https://tushare.pro/document/2?doc_id=33)（已核验） | 同页明确 VIP 可按季度全市场；其余参数同类 | VIP 专属 cap 未标；当前传输实测 9000（2026-10-19） | 金额元、报告类型和修订版本保留 | fundamental；全市场批量，不降回逐码 | 已用VIP；独立权限/页宽 |
| [balancesheet](https://tushare.pro/document/2?doc_id=36)（已核验） | 标准版 ts_code 必选；ann_date/公告范围/period/report_type/comp_type | 标准版上限未标；季报披露 | 金额元；报告期非可见日 | fundamental；单码历史 | 市场优先 `balancesheet_vip`；单码保留标准 |
| [balancesheet_vip](https://tushare.pro/document/2?doc_id=36)（已核验） | 同页明确 VIP 按季度全市场 | VIP 专属 cap 未标；当前传输实测 9000（2026-10-19） | 金额元、公告/报告期/修订分别保留 | fundamental；全市场批量 | 已用VIP；独立权限/页宽 |
| [cashflow](https://tushare.pro/document/2?doc_id=44)（已核验） | 标准版 ts_code 必选；ann_date/f_ann_date/公告范围/period/report_type/comp_type/is_calc | 标准版上限未标；季报披露 | 金额元；累计报告口径不得擅自当单季度 | fundamental；单码历史 | 市场优先 `cashflow_vip`；单码保留标准 |
| [cashflow_vip](https://tushare.pro/document/2?doc_id=44)（已核验） | 同页明确 VIP 按季度全市场 | VIP 专属 cap 未标；当前传输实测 9000（2026-10-19） | 金额元；累计/报告类型保留 | fundamental；全市场批量 | 已用VIP；独立权限/页宽 |
| [fina_indicator](https://tushare.pro/document/2?doc_id=79)（已核验） | 标准版 ts_code 必选；ann_date/period；start_date/end_date 为报告期范围 | 标准版 100；季报披露 | 每股金额/比例/周转次数按字段，不统一缩放 | fundamental；当前默认页宽 2000 与 500 降档下限不能覆盖官方 cap=100 | 市场/单码优先VIP；标准adapter保留兼容 |
| [fina_indicator_vip](https://tushare.pro/document/2?doc_id=79)（已核验） | 同页说明 VIP 可按季度全市场；不能推论标准版也可 | VIP 专属 cap 未标；10000 是 2026-10-11 传输实测 | 保留 update_flag 与披露去重选版 | fundamental；手写 2000 循环绕过共享保护，见 F2 | 已用VIP；独立权限/页宽 |
| [forecast](https://tushare.pro/document/2?doc_id=45)（已核验） | 标准版单码；ann_date/公告范围/period/type；参数表代码与公告二选一表述需结合版本说明 | 3500；20–21 点；披露事件 | 净利润上下界万元，变动比例 % | fundamental；标准/VIP 选择按权限与市场范围 | 市场优先 `forecast_vip`；单码保留标准 |
| [forecast_vip](https://tushare.pro/document/2?doc_id=45)（已核验） | 同页 VIP 按公告日/报告期批量；不是逐码必填 | 同页 3500，VIP 独立 cap 未单列；披露事件 | 利润万元；公告日与预计报告期分开 | fundamental；动态 API 名计入清单 | 已用VIP；独立权限/页宽 |
| [express](https://tushare.pro/document/2?doc_id=46)（已核验） | 标准版 ts_code 必选；ann_date/公告范围/period | 上限未标；业绩快报披露 | 营收/利润金额元；与 forecast 万元不同 | fundamental；单码查询 | 市场优先 `express_vip`；单码保留标准 |
| [express_vip](https://tushare.pro/document/2?doc_id=46)（已核验） | 同页 VIP 按公告日/报告期全市场 | VIP 独立 cap 未标；披露事件 | 金额元；快报不是正式财报替代 | fundamental；动态 API 名计入清单 | 已用VIP；独立权限/页宽 |
| [dividend](https://tushare.pro/document/2?doc_id=103)（已核验） | ts_code/ann_date/record_date/ex_date/imp_ann_date 至少一项；未列 start_date/end_date | 2000；20–21 点；20000101 起 | 每股派息/送转比例；各事件日期不同 | fundamental + capital_market；两个适配入口的范围行为需确认，见 F3 | 原生选择器；当前专页无具名VIP证据 |

### 期货、外汇、宏观及其他（17）

| 接口 / 当前官方证据 | 合法选择与批量边界 | 上限 / 更新 | 字段、单位与日期 | 当前代码 / 处理建议 | VIP 选择结论 |
|---|---|---|---|---|---|
| [fut_basic](https://tushare.pro/document/2?doc_id=135)（已核验） | exchange 必选，六交易所；fut_type=1/2；fut_code/list_date | 10000；合约名册事件 | 合约乘数/交易单位/交割日；连续代码不是实盘合约 | futures；按交易所批量 | 原生选择器；当前专页无具名VIP证据 |
| [fut_daily](https://tushare.pro/document/2?doc_id=138)（已核验） | trade_date/ts_code/exchange/范围 | 2000；日频；19950417 起 | 结算价与收盘价不同；金额万元、持仓量/成交量按合约规则 | futures；市场日可取，保持交易所口径 | 原生选择器；当前专页无具名VIP证据 |
| [shibor](https://tushare.pro/document/2?doc_id=149)（已核验） | date/start_date/end_date | 2000；利率发布日 | 各期限 %；日期不是全天可见保证 | macro；D 窗口 | 原生选择器；当前专页无具名VIP证据 |
| [shibor_lpr](https://tushare.pro/document/2?doc_id=151)（已核验） | date/start_date/end_date | 4000；当前月度；20131025 起 | 1Y/5Y 利率 %；不要据旧日频文案推断每日新值 | macro mapping 可选入口，非新增消费需求 | 原生选择器；当前专页无具名VIP证据 |
| [libor](https://tushare.pro/document/2?doc_id=152)（已核验） | date/start_date/end_date；curr_type 默认 USD，可 EUR/JPY/GBP/CHF | 4000；历史日频；各币种终止时间须另查 | 期限利率 %；存在历史端点不证明当前持续发布 | macro mapping 可选入口 | 原生选择器；当前专页无具名VIP证据 |
| [hibor](https://tushare.pro/document/2?doc_id=153)（已核验） | date/start_date/end_date | 4000；发布日更新 | 各期限 % | macro mapping 可选入口 | 原生选择器；当前专页无具名VIP证据 |
| [cn_gdp](https://tushare.pro/document/2?doc_id=227)（已核验） | q/start_q/end_q，YYYYQn；fields 可选 | 10000；季度 | GDP 亿元、同比 %；统计期与发布期分开 | macro；现有 Q 窗口 | 原生选择器；当前专页无具名VIP证据 |
| [cn_cpi](https://tushare.pro/document/2?doc_id=228)（已核验） | m/start_m/end_m，YYYYMM；m 可逗号多月 | 5000；月度 | 指数与同比/环比 % 分开 | macro；现有 M 窗口 | 原生选择器；当前专页无具名VIP证据 |
| [cn_ppi](https://tushare.pro/document/2?doc_id=245)（已核验） | m/start_m/end_m，YYYYMM；m 可逗号多月 | 5000；月度 | 指数同比/环比/累计口径按字段 | macro；现有 M 窗口 | 原生选择器；当前专页无具名VIP证据 |
| [cn_pmi](https://tushare.pro/document/2?doc_id=325)（已核验） | m/start_m/end_m；fields | 2000；月度 | pmi010000 等字段名小写；指数不能当增长率 | macro；#708 字段大小写已有证据 | 原生选择器；当前专页无具名VIP证据 |
| [cn_m](https://tushare.pro/document/2?doc_id=242)（已核验） | m/start_m/end_m；fields | 5000；月度 | M0/M1/M2 亿元；同比/环比 % | macro；共享请求后拆序列 | 原生选择器；当前专页无具名VIP证据 |
| [sf_month](https://tushare.pro/document/2?doc_id=310)（已核验） | m/start_m/end_m | 2000；月度 | 增量/累计增量亿元、存量万亿元 | macro；共享请求后拆序列 | 原生选择器；当前专页无具名VIP证据 |
| [fx_daily](https://tushare.pro/document/2?doc_id=179)（已核验） | ts_code/trade_date/start_date/end_date/exchange | 1000；日频；GMT 日期 | bid/ask 分开；20230601 代码规则变化，贵金属仍 FXCM 后缀 | fx；不能直接当中国本地交易日 | 原生选择器；当前专页无具名VIP证据 |
| [yc_cb](https://tushare.pro/document/2?doc_id=201)（已核验） | ts_code=1001.CB；curve_type=0/1；trade_date/范围/curve_term | 2000；发布日；独立权限，不以积分替代 | 到期/即期曲线分开；期限年、收益率 % | bond_yield；辅助入口 | 原生选择器；当前专页无具名VIP证据 |
| [margin_detail](https://tushare.pro/document/2?doc_id=59)（已核验） | trade_date/ts_code/start_date/end_date | 6000；T+1 08:30，部分周五数据周一到达 | 融资金额元、融券数量股；余额与交易量不同 | capital_market；不能按当日收盘已可见处理 | 原生选择器；当前专页无具名VIP证据 |
| `hk_hold`（当前未知；仅历史/代码） | 旧 doc_id=188 当前 404；专页 selector 未核验 | 未知；历史与当前制度分段 | 持股披露频率变化；零行不证明永久无数据 | capital_flows；沿用 #708 限定证据与制度边界 | 专页未知；无已验证VIP替代 |
| `rights`（当前未知；仅历史/代码） | 未找到当前官方专页；不得凭同名旧接口补参数 | 未知；历史记录 | 配股事件，不等同增发/分红 | capital_corporate；保留已知不支持/排除说明 | 专页未知；无已验证VIP替代 |


## 非 Tushare 的 13 个入口

### Fuyao（11）

以下均为 2026-11-07 当前官方文档核验，代码位于 [Fuyao source](../../packages/data/src/ditto_data/sources/fuyao/source.py)。省略共同前缀域名，路径保持真实调用形状。fields 不适用其固定 JSON 返回结构；只消费已校验字段。快照、日 K、财报和净值更新不能互相代替。

| 当前 REST 入口 / 官方页面 | 选择、批量与分页 | 时间、字段与单位 | 当前选择 / 最小建议 |
|---|---|---|---|
| `/api/a-share/prices/historical` · [文档](https://fuyao.aicubes.cn/docs/api-reference/prices/) | thscode 单码、interval=1d、start/end 毫秒必填，窗口不超过 10 年，无 offset | 历史 K 线；价格元，量/额依返回字段；时间戳需转交易日 | 股票单码路径正确；多码消费者可验证 historical-batch；全市场回补优先既有 dump |
| `/api/a-share-index/prices/historical` · [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) | thscode 单码、start/end 毫秒、interval=1d；当前文档近 5 年，无 offset | 指数点位，无复权；返回日期必须落请求窗口 | 当前指数对账逐码；文内 ≤10 年说法过时；可验证 10 码 batch |
| `/api/a-share/financials/income-statements` · [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) | 单码；period annual/quarterly；limit=1..20 与 start/end 区间互斥；区间须两端且 ≤10 年 | 金额为原币元；period_end_ms 报告期、report_date_ms 披露日；披露更新 | 对账逐码循环；可验证对应 10 码 batch |
| `/api/a-share/financials/balance-sheets` · [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) | 与利润表相同；annual 取 Q4；最新 N 期倒序 | 资产/负债金额元；同样保留报告期及披露日 | 对账逐码循环；可验证对应 10 码 batch |
| `/api/a-share/financials/cash-flow-statements` · [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) | 与利润表相同；不能同时传 limit 与区间 | 现金流金额元；报告期和披露日独立 | 对账逐码循环；可验证对应 10 码 batch |
| `/api/fund/performance/nav` · [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-performance/) | thscode 单码；range 是 week/month/tmonth/hyear/year/twoyear/tyear/fyear 相对窗口，省略取最新；nav_type unit/adj/both | 披露更新；单位净值/复权净值，未承诺累计净值；无任意日期分页 | 当前 year + unit 再筛目标日正确；不能用于修补 Tushare accum_nav |
| `/api/a-share/prices/snapshot` · [文档](https://fuyao.aicubes.cn/docs/api-reference/prices/) | 显式 thscodes 逗号多码按指定代码返回；不传才用 limit 默认 100 + offset | 盘中快照；price/volume/amount 与历史复权模式区分 | 现有多码调用保留；快照不替代历史 |
| `/api/fund/market/snapshot` · [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-market/) | thscode 支持逗号 1..100 码；ETF/LOF | 盘中价格/份额等按字段单位；不是 NAV 披露 | 当前单码合法；有多码消费者时才合批 |
| `/api/dump/market-dumps/daily-k/download-url` · [文档](https://fuyao.aicubes.cn/docs/api-reference/market-dumps/) | 取临时下载 URL，再 GET 文件；全市场滚动约 10 年 | 全量日 K dump；不以 URL 代表稳定数据快照身份 | 现有路径保留；下载后继续验证实际日期/代码覆盖 |
| `/api/dump/market-dumps/daily-k-10d/download-url` · [文档](https://fuyao.aicubes.cn/docs/api-reference/market-dumps/) | 取临时下载 URL；最近 10 个交易日 | 近期日 K dump；不覆盖更老请求 | 不能以 10 日文件缺行宣告长期无历史 |
| `/api/dump/market-dumps/adjustment-factors/download-url` · [文档](https://fuyao.aicubes.cn/docs/api-reference/market-dumps/) | 取临时下载 URL；复权因子事件流 | 因子无量纲、事件日期；不是每日一条保证 | 沿用实际事件填充/回放约束，勿将缺日当缺数据 |

**额外传输步骤（不增固定 API 计数）**：GET 上述 download-url 返回的预签名对象 URL。官方说明短时有效（通常约 5 分钟）；现有“临时获取后立即下载”符合语义，不能将 URL 持久化为长期凭据或数据身份。限流依据官方 HTTP 429 / 业务码 4001；无限总量不是无限速率，不从文档推算未发布的可持续吞吐。

**已核验、尚非当前调用的批量替代**：`/api/a-share/prices/historical-batch`、`/api/a-share-index/prices/historical-batch`、`/api/a-share/financials/income-statements-batch`、`/api/a-share/financials/balance-sheets-batch`、`/api/a-share/financials/cash-flow-statements-batch`。均以 `thscodes` 接受最多 10 个原始代码（重复输入也计原始数量），按代码分组返回；不能把它们的多码参数传给原单码接口。财务批量同样遵守 latest-N 与日期窗互斥、两端日期及 10 年窗，指数仍为近 5 年。仅为当前已存在的多码消费者验证后替换，不据此新增产品能力。[价格](https://fuyao.aicubes.cn/docs/api-reference/prices/)、[指数](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/)、[财务](https://fuyao.aicubes.cn/docs/api-reference/financials/)。

### FRED 与 Sina（各 1）

| 入口 / 证据状态 | 选择与分页 | 时间、单位与更新 | 当前边界及建议 |
|---|---|---|---|
| `/fred/series/observations` · [官方已核验](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) | series_id + API key；file_type=json；observation_start/end 观测窗；limit 默认/最大 100000、offset，响应 count/offset/limit；无多 series 批量 | realtime_start/end 是实时可见/修订窗口，与观测日期分开；默认 units=lin 原序列单位，各序列频次不同 | 单序列窗口选择合理；见 F7 完整性检查。宏观与商品腿共用此 API，不重复计算端点 |
| `GlobalFuturesService.getGlobalFuturesDailyKLine`（路径 `/futures/api/jsonp.php/var%20_S=/GlobalFuturesService.getGlobalFuturesDailyKLine`）· 当前正式 API 契约未知 | 当前 [Sina adapter](../../packages/data/src/ditto_data/sources/sina/source.py) 按 symbol 请求滚动 JSONP，再本地筛日期；未发现官方版本化分页/全历史承诺 | CL/GC/SI 各合约价格与交易日期规则须保留；网页存在不证明滚动响应覆盖 2014 全历史 | 仅用 #708 已测返回区间/真实缺口证据；不能把整段请求空结果当永久无源，也不能宣称可用 offset 回补 |

FRED 的 [实时区间规则](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) 允许只指定过去 realtime_end；不把未传 realtime_start 杜撰成缺陷。[错误说明](https://fred.stlouisfed.org/docs/api/fred/errors.html) 列 400/404/423/429/500，429 对应 120 次/分钟政策；现有 FRED 永久错误及 Retry-After 处理可作为 Tushare 的局部参考。Sina 当前仅有 [一手行情网页](https://finance.sina.com.cn/futures/quotes/CL.shtml) 与仓库实际请求形状，未核验到完整官方 API 契约。

## 最小后续验收

1. 先收敛 F1/F2：故意构造确定性参数错、限流、页内业务重复、跨页无进展和短页有后继；验证有界请求数、全量集合与披露选版均保持。必要真实核对限一个季度/短窗口，不再开启全历史并发试错。
2. F3/F5/F6 先比对当前源行为与已留证据：把“官方文档不保证”和“当前传输实测不支持”分开；未证明错误前不删合法调用形状，不调整已有数据。
3. 对真正多个目标的 Fuyao / sw_daily 消费者做一次单码与批量等价检查；记录请求数、目标集合、缺失/失败集合、越窗及单位，避免仅以更快或非空判成功。
4. 未接摄取的 index_member、可选利率映射、rights/csrc 的已知不支持路径只标明事实边界，不为凑全覆盖新增数据源、依赖、权限或通用执行平台。

基线清点的计数核对为 Tushare 69 行 + Fuyao 11 行 + FRED 1 行 + Sina 1 行；五个 Fuyao batch 的最终采用与验证见实施结果。
