# 数据就绪度所依赖的来源与时间边界

- 核查日期：2026-11-03（Asia/Shanghai）。
- 研究票：[调研：迟发披露、宏观版本与受限来源的官方边界](https://github.com/cosmos-arc/ditto/issues/651)。
- 所属地图：[数据层 47 项统一就绪：复审修正、真实消费与恢复验收](https://github.com/cosmos-arc/ditto/issues/649)。
- 代码基线：`9d7f84e6f5fc67b1d53cede25b8a30c0045f9362`，与复审报告一致。
- 方式：官方公开文档与源码只读核验；未调用真实凭据，未扫描运行数据根，未执行数据写入。

结论：两融与北向的统一自然日 T+1 映射不符合已核实的公开规则；
FRED 已有版本读取能力，应复用并验收接线。基金披露范围还需纠正“凭报告期判断全量”的假设。
本研究不能证明 47 项当前完整、当前账号已获权限，或历史快照可被重新创造。

## 1 四类时间必须分别取证

| 时间 | 代表什么 | 不能替代什么 |
| --- | --- | --- |
| 观察或报告期 | 事实描述的日期，例如交易日、季度末 | 不是披露日 |
| 市场公开时间 | 交易所、基金管理人或原始发布者公开事实的时间 | 不是供应商已可返回的证明 |
| 供应商可得时间 | 指定端点能够返回该版本的时间 | 不是本地已经取得的证明 |
| 本地 observed_at | 本地首次留存该快照的时间 | 不能追溯改写成历史公告日 |

上述区分遵循 [PIT contract](../../.agents/skills/ditto-pit-safety/references/pit-contract.md)。
日期级查询已有“上海日终”约定，见 [消费者 PIT 验收](../data/consumer-pit-verification.md)。
推断：修正日期规则能关闭已知提前可见反例，但不自动证明日内可见性、历史版本完整或本地历史重放。

## 2 两融的发布与节假日边界

**已证实。** [Tushare margin_detail](https://tushare.pro/document/2?doc_id=59)
说明上一日数据约 08:30 更新，并特别说明深交所、北交所周五数据在周一上午更新。
该页面是供应商公开说明，不能把“约”升级为逐日精确到秒的保证。
[深交所官方问答](https://investor.szse.cn/knowledge/stock/margin/t20190724_568897.html)
给出的交易所规则是每个交易日开市前公布前一交易日数据。
[上交所实施细则解读](https://big5.sse.com.cn/services/tradingservice/margin/edu/c/10074042/files/a1f1c4833302451fb9130dbb94116c56.pdf)
同样描述交易日开市前公布，不能据供应商仅点名深/北就断言沪市周六必定可得。

**代码事实。** [MARGIN_TRADING_MAPPING](../../packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py)
第 82 行直接使用自然日加一。应用 `CapitalQueryFacade.get_margin_trading` 经
`CapitalStore` 进入 [SqliteTableReader](../../packages/data/src/ditto_data/storage/base/sqlite_table_reader.py)，
确实执行 knowledge_date 与版本区间过滤；错误来自输入的可知日，不是缺一个查询过滤器。

**未知。** 本次未获得三所所有历史节假日、临时延迟、供应商修订的精确时间记录；
也没有证明当前运行库已出现周末泄漏或已补齐深市迟发记录。
决策影响：需按交易所与适用日历定界，同时保留供应商与本地证据；
验收周五、长假前后、发布前后边界，并安排既有错误 knowledge_date 的存量纠正。
将自然日 T+1 机械改为普通交易日 T+1，不足以宣布全历史严格 PIT ready。

## 3 北向披露制度与专用日历

**已证实。** [HKEX 当前持仓查询说明](https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=sz)
明确自 2024-08-19 起改为季度披露，前一季度数据在季末后第 5 个北向交易日公布。
[2024-04-12 公告](https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en)
提供制度调整依据；当前查询页进一步确认生效日期。
[HKEX 日历入口](https://www.hkex.com.hk/mutual-market/stock-connect/reference-materials/trading-hour%2C-trading-and-settlement-calendar?sc_lang=en)
分别提供交易日历与北向结算日历，不应以普通 A 股日历或结算日历替代北向交易日历。

**代码事实。** `HK_HOLD_MAPPING`（同上 capital.py 第 446–459 行）仍用自然日加一。
该文件同时声明：同证券多持有人行被确定性收敛，不能据现存单行推导整体持仓加总。
[覆盖合同](../data/coverage-contract.yaml) 已分出每日与季度制度段，故无需重新发明分段模型。

**未知。** 官方公开查询窗口不等于供应商全部历史范围；当前账号的历史可取得范围、
各季度准确返回时刻、旧制度期间发布延迟均未实测。
决策影响：季度末不等于可知日；先确认读取消费范围与多持有人处理，再开放严格消费者。
验收应覆盖制度切换、国庆跨季、北向休市日及披露前后的未来哨兵。

## 4 FRED 与 ALFRED 已有能力和未完成部分

**已证实。** [FRED Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
区分“今天看见的历史”与历史时点已知版本；默认 real-time 区间为今天，
`realtime_start` / `realtime_end` 指定闭区间。观察日期不能替代版本公开日期。

**代码事实。** [MacroFredAdapter](../../packages/data/src/ditto_data/sources/fred/adapters/macro.py)
已暴露 real-time 参数，过滤 as-of 之后的 vintage、每个观察日保留当时最新版本，
并将 `realtime_start` 保存为 knowledge_date。默认模式的注释明确其可能只是采集日，
不能伪称首次发布时刻。这些是现有实现，不应重复建设一个版本框架。

[支撑源核验](../data/supporting-sources-verification.md) 记录了 51 系列配置/探针，
并说明 commodity 的 FRED 油/VIX 腿未接入当前 Tushare 车道：需保持逐源证据归属。
该记录属于仓库历史证据；本研究没有刷新 51 系列落库量或日链状态。

**未知。** 逐系列可用 vintage 起点、完整修订史、请求参数与真实响应一致性、
实际摄取与消费覆盖均待隔离探针和运行验收。
决策影响：latest 宏观背景与严格历史策略输入要分别声明语义；
即使同一数据集达到 ready，也不能把 latest 输出直接转作严格历史输入。
复用已有适配器；新增工作优先是来源接线、品种分母、单位/频率与消费者证据。

## 5 基金持仓的披露范围不能仅由报告期推断

**已证实。** [Tushare fund_portfolio](https://tushare.pro/document/2?doc_id=121)
面向公募基金，参数包含基金、公告日、报告期；示例基金为 `.OF`。
官方页面标示 5000 积分以上每分钟 200 次、8000 积分以上每分钟 500 次。
[fund_basic](https://tushare.pro/document/1?doc_id=19) 区分 E 场内和 O 场外，默认 E。
这些是公开产品条件，不是当前账号或代理权限的实测结果。

[CSRC 公开规范性文件汇编](https://www.csrc.gov.cn/csrc/c101950/c1047975/1047975/files/%E9%99%84%E4%BB%B61_%E4%B8%AD%E5%9B%BD%E8%AF%81%E7%9B%91%E4%BC%9A%E5%86%B3%E5%AE%9A%E4%BF%AE%E6%94%B9%E7%9A%84%E8%A7%84%E8%8C%83%E6%80%A7%E6%96%87%E4%BB%B6.pdf)
分别规定季度、半年度、年度报告；季度报告列示主要股票持仓，半年/年度报告正文提供全部股票明细，
其摘要仍可仅列部分股票。必须识别报告类型与正文/摘要，不能只看季度末月份。

**需要纠正的推断。** 现有 [持仓验收](../data/holdings-disclosure-verification.md)
按 06-30/12-31 推定“全量”，并把同报告期不同公告日称作修订，依据不充分。
Q2/Q4 同样存在季度报告；Tushare 官方样例中相同 2018-06-30 报告期有 7 月与 8 月公告行。
它们可能属于季度报告与半年报的不同披露范围，不能未经公告核验就认定后者是纠错修订。
“全部股票持仓”也不等于基金全部资产类别。

**代码事实。** [DataWriter](../../packages/application/src/ditto_application/processes/ingestion/data_writer.py)
第 1429 行起将基金持仓送入通用身份富集，第 1380 行过滤无法解析的 instrument_id；
源端接收 `.OF` 不代表当前库保留 `.OF`。这与现有 ETF/LOF 子集合同一致。

**未知。** 未核实当前每只基金每次披露的报告类型、完整性及所持资产范围。
决策影响：全公募需求需补持有人身份；不得直接取消身份校验或把全部基金纳入可交易池。
验收须区分季报/半年报/年报/真实修订，披露前后可见性与“未披露不等于零持仓”。

## 6 rights 与 CSRC 分类的访问条件

**本次公开核查结果。** [Tushare 官方接口目录](https://tushare.pro/document/2)
和 [官方积分表](https://tushare.pro/document/1?doc_id=108) 未检出精确名称
`rights`、`csrc_industrial` 对应的公开访问条件；精确接口身份、是否另行开通、
最低积分/付费条件、历史深度均应标为**未知**。
“未检出公开文档”不能推导服务绝对不存在，也不能推导购买更高档必然解锁。

**仓库历史证据。** [覆盖合同](../data/coverage-contract.yaml) 的 probes 记录
`rights` 经代理返回 50101、`csrc_industrial` 返回 2002；当前 corporate_actions
与 industry_classification 因此各有范围缺口。此处引用的是历史记录，本次未复测。
公开官方支持、代理是否透传、当前凭据是否授权是三个问题，不能互相替代。

**待补证据。** 精确 endpoint 官方确认、同端点最小合法请求、代理与官方直连的区别，
以及该账户的真实返回。取得新授权或补源的范围与成本留给维护者裁决。
本研究不沿用旧调研中的“每年 2000 元”预算，不把权限未知当作已经授权付费。
决策影响：如果全量 ready 包括这些语义，保留阻断；不能仅删掉配置或收窄名字使其变绿。

## 7 历史事实重建与原本地快照重放

**代码事实。** [历史证券池查询](../../packages/application/src/ditto_application/queries/historical_universe.py)
第 278–289 行只选择本地 observed_at 不晚于 cutoff 的快照，否则报 HISTORY_NOT_OBSERVED。
[原始历史投影](../../packages/data/src/ditto_data/services/historical_universe.py)
将 raw stock_basic/status 的 publication_at、available_at 设为 observed_at，
避免将今天的名册或回填事实偷偷带入过去。缺状态会形成不可投资原因。
[研究数据集入口](../../packages/application/src/ditto_application/processes/research_dataset.py)
逐交易日解析同一组固定证据，仍受该门约束。

**推断。** 今天回填 2014 行情或 2016 状态可以增加历史事实，但不能创造当年本地快照。
如果存在可追溯的原始公告、历史发布版本及身份映射，可进一步研究历史市场信息重建；
那是不同证据承诺，不能冒充原本地观测重放，也不能以现在的最新修订替代当时值。
**未知。** 本次没有实测库中最早可用快照、ST 变更史、历史成员链或证券池消费者输出。

## 8 对后续裁决与验收的约束

1. 47 项全部 ready 可以共用证据门，但起点、频率、发布精度、版本语义须逐项有依据。
2. 对来源不存在或尚不可取得的历史，不允许合成通过；保留缺口，决定补源或调整明确范围。
3. 已有代码能力优先复用；新工序必须对应真实消费者或本研究列出的未证实条件。
4. 研究票完成仅表示事实与未知项已清楚；不表示权限已开通、数据完整、代码修复或 LIVE 验收通过。

本文件仅新增研究材料；验证采用 `git diff --check`。没有执行生产数据、PIT 或端到端测试。
