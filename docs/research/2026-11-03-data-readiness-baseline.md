# 47 项数据层只读库存基线

- 核验票：[47 项当前覆盖、消费入口与恢复证据的只读基线](https://github.com/cosmos-arc/ditto/issues/650)。
- 所属地图：[数据层 47 项统一就绪](https://github.com/cosmos-arc/ditto/issues/649)。
- 代码基线：`9d7f84e6f5fc67b1d53cede25b8a30c0045f9362`。
- 主扫描：2026-11-03 20:17:39.795784 ～ 20:17:52.166623（Asia/Shanghai）；SQLite 读取事务于 20:17:51.906362 结束。
- LIVE 窗口采集于 20:17:56；失败覆盖及补充日期轴查询于 20:18 完成，不与主扫描共享事务。

本次取得现有 47 项的物理行数与日期范围，确认合同存在陈旧末端及未闭合证据。
**物理库存不等于完整性或 ready**：追加的股票／ETF 逐证券核验仍发现缺口，其余数据的应有分母、真实消费和恢复成功尚未验收。

## 方法与证据身份

当前根由运行中的 Ditto Prefect worker 环境核对 config/state/cache 路径，只提取路径变量，不输出凭据；旧默认 XDG 库不作为当前事实源。具体机器路径不收入本报告。
按[覆盖合同](../data/coverage-contract.yaml)的 47 个 dataset_id 和 storage 定位采集：SQLite 使用 `mode=ro`、`PRAGMA query_only=ON`、同一 `BEGIN` 读取事务执行 `COUNT/MIN/MAX`；未使用 immutable、未执行 checkpoint。主扫描前两个运行库 WAL 均为 0 字节，此事实不替代事务隔离。
Parquet 使用现有 Polars 对合同目录的文件执行 `scan_parquet(..., hive_partitioning=False)` 和列投影聚合，streaming 收集；本次所测文件扫描前后的大小／mtime 无变化。SQLite 与 Parquet **不是跨存储原子快照**。
LIVE 复用[现有只读脚本](../../apps/backend/src/ditto_apps/scripts/data_live_gate.py)；FAIL 对照复用其完成快照 SQL 并追加同源约束。没有加载可能初始化数据目录／数据库的应用容器，没有执行摄取、回补、修复、迁移或恢复。
原始 JSON 已保存在本地私有证据归档，含机器路径，不提交、不推送；下列摘要用其最终文件字节的 SHA-256 绑定。

| 本地证据名 | 内容与复核方法 | SHA-256 |
| --- | --- | --- |
| `baseline.json` | 47 项聚合、catalog 与最近日志；复核上述 SQL／Polars 聚合 | `672275f60522a4ea790891bf4266a2fc64aa529a7eda90e14e2f84ad7ea1f936` |
| `live-window.json` | `collect_live_gate_matrix`，窗口 2026-10-27 至 2026-11-02 | `433a9c0b317dddd55e7057dcacba38acbe3d8464f0eb216a814bb376d5bcca84` |
| `failure-coverage.json` | 全部 FAIL 的 dataset/source/date 与完成请求覆盖布尔值 | `67730284bf91f5d4b4db96fbcae5e6d511494b87e00970f63158cac446f7628d` |

## 47 项物理库存

所有 47 项均取得行数，无扫描错误。日期轴按各表实际字段列出；`—` 表示此次未采集适用日期轴，不表示没有时间约束。catalog 有记录不代表该项消费或完整性已通过。knowledge_date 是**现存字段值**，不代表其语义已验证正确。

| dataset_id | 实测行数 | 业务日期轴与范围 | knowledge_date 范围 | catalog |
| --- | ---: | --- | --- | --- |
| `calendar` | 5,478 | `trade_date`：2013-01-01 ～ 2027-12-31 | — | 有 |
| `stock_basic` | 5,930 | `未采集日期轴`：— | — | 有 |
| `etf_basic` | 1,868 | `未采集日期轴`：— | — | 有 |
| `index_basic` | 20,897 | `未采集日期轴`：— | — | 有 |
| `etf_reference` | 1,716,146 | `effective_from`：2013-01-04 ～ 2026-11-02 | — | 无 |
| `stock_daily` | 13,028,978 | `trade_date`：2013-01-04 ～ 2026-11-02 | 2013-01-05 ～ 2026-11-03 | 有 |
| `etf_daily` | 1,620,235 | `trade_date`：2013-01-04 ～ 2026-11-02 | 2013-01-05 ～ 2026-11-03 | 有 |
| `index_daily` | 546,096 | `trade_date`：2014-01-02 ～ 2026-11-02 | 2014-01-03 ～ 2026-11-03 | 有 |
| `global_index_daily` | 60,781 | `trade_date`：2014-01-01 ～ 2026-11-02 | 2026-10-27 ～ 2026-11-02 | 有 |
| `stock_status` | 10,894,187 | `trade_date`：2016-08-09 ～ 2026-11-02 | — | 有 |
| `adj_factor` | 13,618,641 | `trade_date`：2013-01-04 ～ 2026-11-02 | 2013-01-04 ～ 2026-11-02 | 有 |
| `fund_adj` | 1,637,886 | `trade_date`：2013-01-04 ～ 2026-11-02 | 2013-01-04 ～ 2026-11-02 | 有 |
| `etf_nav` | 1,528,803 | `trade_date`：2014-01-01 ～ 2026-11-02 | 2014-01-03 ～ 2026-11-03 | 有 |
| `stock_limit` | 12,708,886 | `trade_date`：2014-01-02 ～ 2026-11-02 | 2014-01-03 ～ 2026-11-03 | 有 |
| `moneyflow` | 12,565,831 | `trade_date`：2013-01-04 ～ 2026-11-02 | 2013-01-05 ～ 2026-11-03 | 有 |
| `cyq_perf` | 9,575,847 | `trade_date`：2018-01-02 ～ 2026-11-02 | 2018-01-03 ～ 2026-11-03 | 有 |
| `limit_list` | 840 | `trade_date`：2026-09-30 ～ 2026-11-02 | 2026-10-01 ～ 2026-11-03 | 有 |
| `top_list` | 192,605 | `trade_date`：2014-01-02 ～ 2026-11-02 | 2014-01-03 ～ 2026-11-03 | 有 |
| `top_inst` | 2,343,763 | `trade_date`：2014-01-02 ～ 2026-11-02 | 2014-01-03 ～ 2026-11-03 | 有 |
| `hk_hold` | 4,224,382 | `trade_date`：2016-06-29 ～ 2026-09-30 | 2016-06-30 ～ 2026-10-01 | 有 |
| `hsgt_top10` | 50,750 | `trade_date`：2014-11-17 ～ 2026-11-02 | 2014-11-18 ～ 2026-11-03 | 有 |
| `fina_indicator` | 263,672 | `report_date`：2012-03-31 ～ 2026-09-30 | 2012-04-10 ～ 2026-10-31 | 有 |
| `fund_share` | 1,604,081 | `trade_date`：2013-01-04 ～ 2026-10-30 | 2013-01-05 ～ 2026-10-31 | 有 |
| `fund_portfolio` | 609,923 | `report_date`：2013-12-31 ～ 2026-09-30 | 2014-01-20 ～ 2026-10-26 | 有 |
| `top10_holders` | 2,509,682 | `report_date`：2010-12-31 ～ 2026-09-30 | 2014-01-02 ～ 2026-10-31 | 有 |
| `top10_floatholders` | 2,107,395 | `report_date`：2012-06-30 ～ 2026-09-30 | 2014-01-08 ～ 2026-10-31 | 有 |
| `balance_sheet` | 239,376 | `report_date`：2011-12-31 ～ 2026-09-30 | 2014-01-02 ～ 2026-10-31 | 有 |
| `income_statement` | 244,541 | `report_date`：2011-12-31 ～ 2026-09-30 | 2014-01-02 ～ 2026-10-31 | 有 |
| `cash_flow` | 226,526 | `report_date`：2011-12-31 ～ 2026-09-30 | 2014-01-02 ～ 2026-10-31 | 有 |
| `dividend` | 266,397 | `ex_dividend_date`：2014-02-12 ～ 2026-11-02 | 2014-01-03 ～ 2026-10-13 | 有 |
| `valuation_metrics` | 12,305,960 | `trade_date`：2014-01-02 ～ 2026-11-02 | 2014-01-03 ～ 2026-11-03 | 有 |
| `margin_trading` | 6,846,897 | `trade_date`：2013-01-04 ～ 2026-10-30 | 2013-01-05 ～ 2026-10-31 | 有 |
| `pledge_ratio` | 1,632,293 | `report_date`：2014-03-07 ～ 2026-09-18 | 2014-03-07 ～ 2026-09-18 | 有 |
| `macro_indicators` | 885 | `date`：2015-01-01 ～ 2026-09-01 | 2026-10-26 ～ 2026-10-30 | 有 |
| `fx_daily` | 23,999 | `trade_date`：2014-01-01 ～ 2026-11-01 | — | 有 |
| `commodity_daily` | 15,532 | `trade_date`：2014-01-01 ～ 2026-11-02 | — | 有 |
| `corporate_actions` | 92,934 | `action_date`：2007-05-23 ～ 2034-01-20 | 2014-01-02 ～ 2026-11-02 | 有 |
| `index_weight` | 1,908,665 | `trade_date`：2014-01-30 ～ 2026-09-30 | — | 有 |
| `industry_classification` | 31 | `未采集日期轴`：— | — | 有 |
| `industry_mapping` | 7,925 | `effective_from`：1984-05-09 ～ 2026-10-28 | — | 有 |
| `namechange` | 3,538 | `changed_date`：2013-01-10 ～ 2026-10-29 | — | 有 |
| `st_history` | 1,848 | `effective_from`：2013-01-14 ～ 2026-10-20 | — | 有 |
| `futures_daily` | 6,451 | `trade_date`：2026-10-26 ～ 2026-11-02 | 2026-10-26 ～ 2026-11-02 | 有 |
| `futures_basic` | 68,132 | `list_date`：1995-04-17 ～ 2026-11-02 | 2026-10-26 ～ 2026-11-02 | 有 |
| `earnings_forecast` | 120,461 | `ann_date`：2014-01-01 ～ 2026-10-30 | 2026-10-30 ～ 2026-11-03 | 有 |
| `earnings_express` | 24,412 | `ann_date`：2014-01-04 ～ 2026-10-21 | 2026-11-02 ～ 2026-11-03 | 有 |
| `index_valuation` | 90 | `trade_date`：2026-10-26 ～ 2026-11-02 | 2026-10-26 ～ 2026-11-02 | 有 |

## 相对旧合同的关键差异

- 合同静态标签仍为 29 ready／18 partial。当前 catalog 46 条；`etf_reference` 有 1,716,146 行而无 catalog 条目，登记缺口仍在。
- 股票／ETF 日线、状态、因子、NAV 等已到 11-02；NAV 末端 10-26 的旧判断已过时。`margin_trading`／`fund_share` 仍到 10-30，`pledge_ratio` 报告日仍到 09-18。
- `limit_list` 仍从 09-30 才开始；`futures_daily`／`index_valuation` 仍从 10-26 开始。更晚末端不能补足缺失历史。
- 宏观当前 885 行，indicator_id 仅 1–7，观察日期仍到 09-01。商品现有 instrument_id 为 5000003–5000007，未出现配置中的 FRED 油／VIX 5000001、5000002、5100001；10,645 个 provider snapshots 的 source 均为 tushare。
- `earnings_forecast`／`earnings_express` 公告日虽追溯至 2014，knowledge_date 最早却分别为 2026-10-30／11-02；全球指数同类最早为 10-27。历史回填不等于当年 as-of 可用，语义须与[来源与时间边界研究](2026-11-03-data-readiness-source-boundaries.md)分别验收。
- `dividend` 除息日末端为 11-02，knowledge_date 末端为 10-13；`corporate_actions` 计划日期至 2034 年，不能把业务日期、公开日期和采集日期混成一个“最新日期”。

## 请求矩阵与剩余失败证据

窗口为 2026-10-27、10-28、10-29、10-30、11-02，46 项 × 5 日：**229/230 有完成请求覆盖＝206 attested＋23 covered_empty；1 uncovered**。这不是 47 项全历史或逐证券就绪结论，也不是按消费截止时间核验过的连续 SLA。
唯一 uncovered 为 `industry_mapping` 的 11-02：该日仍是 FAIL、attempts=3；11-03 15:24 的重刷 SUCCESS 写入 7,925 行，但新快照 request_start/end 仅覆盖 11-03。当前已重刷不能改写成旧日证据已闭合。
摄取账本共 21,956 行、快照 10,645 条、分区 checkpoint 10,763 条。历史 FAIL 共 132 条，其中 84 条被同源完成请求窗口覆盖；剩 **48 条无这种覆盖，47 条 attempts≥3**。48 条包含源起点以前、非交易日、低频等待分类情况，**不能称为 48 个真实数据洞**；完成请求覆盖本身也不证明逐证券无缺损。

## 证据留存与恢复条件

- 20:17:56 核对 10,261 个声明 payload_retained 的快照引用，目标文件均存在；payload 树共有 10,341 个 Parquet 和 10,341 个 schema sidecar。本次**仅检查引用文件存在，未逐份读取、验证 schema 或全树重哈希**。
- 当前 metadata 库约 5.080 GB、trading 库约 70.96 MB；payload 树约 4.8 GiB。现有[备份配方](../operations/workstation-backup-recipe.md)排除 canonical Parquet，保留账本不等于恢复后的普通补数会重新生成文件。
- 备份查找范围仅为已确认运行根的 `backups/` 和 `metadata/`：发现 10-27 metadata 压缩备份、11-01 metadata 副本，未发现工作站完整备份 manifest，也未校验这两份副本。未检查的目录／外部介质不能据此判定无备份。
- worker 日志文件实测约 **17.72 GB**，当前卷剩余约 **58.40 GB**；这是空间观测，不是容量门或恢复时间承诺。本次未清理日志或任何数据。
- 旧[运维验收](../data/operational-acceptance-verification.md)中的恢复演练仍是历史记录；本轮未重做真实根 backup→restore→verify／消费者读取。此前临时 SQLite／文件反例证实恢复后删 payload 仍 verify 通过，只证明验证缺陷，不证明真实损失。

## 核心价格逐证券覆盖复测

独立复测于 **20:25:25.678655 ～ 20:25:53.215354 CST** 完成。CLI 会装配应用容器，故本次不运行 CLI；直接复用其[零 I/O 纯审计函数](../../packages/data/src/ditto_data/quality/coverage_audit.py)，按[现有服务](../../packages/application/src/ditto_application/processes/quality/coverage_audit.py)的输入口径读取只读 SQLite 名册／日历及 Parquet 业务键、停牌位。保留退市证券，沿现有全名册口径，不预先套用新的范围裁决；键去重遵循现有读取语义，没有复制归因算法。
四次串行子进程均正常完成：Polars 2 线程、每次 CPU 120 秒／墙钟 180 秒限制、4 GiB RSS 监控终止阈值；实测单次 1.3–13.1 秒，最高 RSS 约 3.20 GB，未触发限制。所读 Parquet 文件扫描期间均未变化；各轮仍非跨存储原子快照。
所有窗口起点为 2014-01-01。日历序列检查均通过；**四次会话审计均 passed=false**。这证明物理异常仍在，不证明 PIT、日历官方真值或最终研究分母正确。

| 资产／截止日 | 期望／在场会话 | trading_no_bar | status_row_missing | 有价缺因子 | 其他主要事实 |
| --- | ---: | ---: | ---: | ---: | --- |
| 股票／10-30 | 12,735,467／12,382,283 | 10,201 | 19,270 | 0 | 与旧报告三个核心统计一致 |
| 股票／11-02 | 12,741,048／12,387,857 | 10,201 | 19,274 | 0 | 较旧截止增加 4 个缺状态会话；停牌有价 1,841 |
| ETF／10-30 | 1,810,323／1,599,604 | 不适用 | 不适用 | 92 | no_status_dataset 210,719 |
| ETF／11-02 | 1,812,191／1,601,321 | 不适用 | 不适用 | 92 | no_status_dataset 210,870，不能直接判作丢行情 |

最新窗口另有股票上市日前 bar 76,267、缺上市日名册 3；ETF 上市日前 bar 3,481。因子只检查该业务键是否存在任一版本，未验证因子值或截止时点可见性。以下新增原始 JSON 同样仅本地留存：

| 证据名 | SHA-256 |
| --- | --- |
| `price-core-stock-2026-10-30.json` | `bd9a33f21d1368b2c94aef6e6605bb92a3fa382613cfa5c515a4bc504e43c0ed` |
| `price-core-stock-2026-11-02.json` | `d5a89f08f88070f80af6ad32d41b2d3874d60d7280e20cfdc7892ed6981451ec` |
| `price-core-etf-2026-10-30.json` | `8657400821afa1d59822509d9964ce9f0300458ca918380f2c610398019b844c` |
| `price-core-etf-2026-11-02.json` | `52f988a1b921728de3710d4651f1ed0ac81d6bd0455d8a15d20d404afbe62037` |
| `price-core-runs.json` | `3a9f551b798043f11a59518e3202283fc3ed322578b9c1e5f487787e6de6d33e` |

## 47 项消费入口静态核验

同一代码基线下，47 项均追到来源与存储实现：**31 项有 application 读取路径，16 项仅到 storage／data service**，没有仅靠合同声称存在的项。这里的“应用路径”包括内部研究和运维读取，不能解读为 31 项研究闭环已完成。至少 `stock_limit`、`moneyflow`、`cyq_perf`、`fund_share` 四项本轮只追到运维 DQ／覆盖审计；`fund_adj` 有显式复权的应用研究方法和审计入口，通用 ETF 行情接口仍有复权缺陷。

核验沿真实调用与依赖装配进行：来源／写入见[摄取注册表](../../packages/application/src/ditto_application/processes/ingestion/dataset_registry.py)和[DataWriter](../../packages/application/src/ditto_application/processes/ingestion/data_writer.py)；Reader／Store 装配见 data DI 的[行情](../../packages/data/src/ditto_data/di/market.py)、[资金](../../packages/data/src/ditto_data/di/capital.py)、[财务](../../packages/data/src/ditto_data/di/fundamental.py)、[元数据](../../packages/data/src/ditto_data/di/metadata.py)。[应用 providers](../../packages/application/src/ditto_application/providers_market.py)与[CLI query bundle](../../apps/backend/src/ditto_apps/registry/contexts/query.py)连接实际 facade，[HTTP route 注册表](../../apps/backend/src/ditto_apps/openapi_contract.py)确认外部路由已挂载。表中未将字符串命中、摄取／回补命令、catalog/status、稀疏证据恢复或通用 SQL／Parquet 检查算作研究消费者。

| dataset_id | 入口类型 | 真实调用链符号（来源／写入已沿上述注册表核对） |
| --- | --- | --- |
| `calendar` | 内部应用／运维 | `CalendarReader` → `MetadataService.calendar.list_calendar_range/list_trading_days` → `MetadataQueryFacade`／`QualityPatrolService`／研究数据装配 |
| `stock_basic` | HTTP／CLI 查询 | `InstrumentReader.find_securities` → `MetadataService` → `MetadataQueryFacade.find_securities/get_instrument` → metadata `list_instruments/get_instrument` |
| `etf_basic` | HTTP／CLI 查询 | instruments／ETF 观察行 → `MetadataQueryFacade` → metadata 查询及 `ETFCandidateQuery.list_candidates` |
| `index_basic` | HTTP／CLI 查询 | `InstrumentReader` → `MetadataQueryFacade.find_securities(asset_class=index)` → metadata `list_instruments`；目录可查不等于行情齐全 |
| `etf_reference` | HTTP 查询 | config 声明及 ETF basic/daily 观察 → `EtfReferenceObservationWriter`／`InstrumentReader.find_etf_reference` → `ETFCandidateQuery.list_candidates` → metadata candidates |
| `stock_daily` | HTTP／CLI 查询、研究 | `StockBarsReader` → `query_bars`／`MarketService.find_bars` → `MarketQueryFacade.find_bars` → market `post_bars`；另有图表／研究输入 |
| `etf_daily` | HTTP／CLI 查询、研究 | `EtfBarsReader` → 同一 bars 链；通用 ETF qfq/hfq 被忽略的已证实缺陷仍在 |
| `index_daily` | HTTP／CLI 查询、展示 | `IndexBarsReader` → bars 的 index 分支；保留 payload → MarketContext 指数收益投影 |
| `global_index_daily` | HTTP 展示 | 保留 payload → `ProviderPayloadMarketContextSource.load` → `_global_display_facts` → `MarketContextFacade.get_context`；仅展示，不进入 regime 决策输入 |
| `stock_status` | 内部研究／运维 | `StockStatusReader` → `MarketService.get_stock_status` → `RuntimeDerivedInputProvider._fetch_market_data`／`PriceCoverageAuditService`；另有图表状态证据 |
| `adj_factor` | HTTP 复权、内部研究 | `StockAdjFactorReader` → `apply_adjustment` → `query_bars`；另有图表／研究输入／L3 |
| `fund_adj` | 内部研究方法／运维 | `EtfAdjFactorReader` → `apply_etf_adjustment`／`get_etf_bars` → `ForwardReturnService.compute`／ETF runtime 输入；显式 adj 才复权，默认 factor-ic CLI 为 none；另有覆盖审计 |
| `etf_nav` | HTTP 查询 | `EtfNavReader` → `MarketService.get_etf_nav` → `MarketQueryFacade.get_etf_nav` → market `post_etf_nav`，`latest_available` |
| `stock_limit` | 运维读取 | `StockLimitReader` → `MarketQueryFacade.get_stock_limits` → `QualityPatrolService` → `ops dq`，statistical 规则已配置 |
| `moneyflow` | 应用 facade／运维读取 | `MoneyflowReader` → `CapitalStore.get_moneyflows` → `CapitalQueryFacade.get_moneyflows` → L3／`ops dq`；另有 `ops audit-capital-coverage` |
| `cyq_perf` | 应用 facade／运维读取 | `CyqPerfReader` → `CapitalStore.get_cyq_perfs` → 同名 facade → L3／`ops dq`，statistical 规则已配置 |
| `limit_list` | 仅 storage | `LimitListReader` 已注入 `MarketReaders`；未追到应用读取调用 |
| `top_list` | 仅 storage | `TopListReader` 已装配；`CapitalStore` 有保存方法，未追到对应应用读取 |
| `top_inst` | 仅 storage | `TopInstReader` 已装配；未追到对应 Store／facade 读取 |
| `hk_hold` | 仅 storage | `HkHoldReader` 已装配；未追到持仓研究应用读取 |
| `hsgt_top10` | 仅 storage | `HsgtTop10Reader` 已装配；未追到应用读取 |
| `fina_indicator` | 仅 storage | `FinaIndicatorReader` 已装配；未追到 Store／facade 读取或研究消费者 |
| `fund_share` | 运维读取 | `FundShareReader` → `MarketService.get_fund_share` → `PriceCoverageAuditService` → `ops audit-capital-coverage` |
| `fund_portfolio` | 仅 storage | `FundPortfolioReader` 已装配；未追到应用读取，摄取身份富化不算持仓研究 |
| `top10_holders` | 仅 storage | `Top10HoldersReader` 已装配；未追到 Store／facade 读取 |
| `top10_floatholders` | 仅 storage | `Top10FloatholdersReader` 已装配；未追到 Store／facade 读取 |
| `balance_sheet` | HTTP／CLI 查询 | `BalanceSheetReader.get` → `FundamentalStore.get_balance_sheet` → 同名 facade → fundamental `get_financials`，`pit_asof` |
| `income_statement` | HTTP／CLI 查询 | `IncomeStatementReader.get` → `FundamentalStore.get_income_statement` → 同名 facade → `get_financials`，`pit_asof` |
| `cash_flow` | HTTP／CLI 查询 | `CashFlowReader.get` → `FundamentalStore.get_cash_flow` → 同名 facade → `get_financials`，`pit_asof` |
| `dividend` | HTTP／CLI 查询 | `DividendReader.get` → `FundamentalStore.get_dividend` → 同名 facade → fundamental `get_dividend`，`pit_asof` |
| `valuation_metrics` | HTTP／CLI 查询 | `ValuationMetricsReader.get` → `CapitalStore.get_valuation_metrics` → 同名 facade → capital `get_valuation`，`pit_asof` |
| `margin_trading` | HTTP／CLI 查询 | `MarginTradingReader.get` → `CapitalStore.get_margin_trading` → `CapitalQueryFacade` → capital `get_margin`；标注 pit_asof，但 knowledge_date 错误仍阻断正确性 |
| `pledge_ratio` | 仅 data service | `PledgeRatioReader.get` → `CapitalStore.get_pledge_ratio`；未追到 application／HTTP／CLI 调用者 |
| `macro_indicators` | HTTP／CLI 查询 | `IndicatorReader.get` → `MacroService.find_indicators` → `MacroQueryFacade.find_indicators` → macro `post_indicators`；facade 未传 asof，为 `latest_available` |
| `fx_daily` | HTTP 查询 | `FxBarsReader` → `MarketService.list_bars` → `FXQueryFacade`／`InstrumentCodeQueryFacade` → fx `post_bars`，`latest_available` |
| `commodity_daily` | HTTP 查询 | `CommodityBarsReader` → `MarketService.list_bars` → `CommodityQueryFacade` → commodity `post_bars`，`latest_available`；来源腿有运行条件 |
| `corporate_actions` | HTTP／CLI 查询 | `CorporateActionsReader.query` → `FundamentalStore.list_corporate_actions` → facade → 同名 route；有 as-of 为 pit_asof，缺省 latest_available |
| `index_weight` | 历史证券池 HTTP | canonical `IndexCompositionWriter` 同时留 payload → `SnapshotReadService` → `HistoricalUniverseQuery.pin`／`PinnedHistoricalUniverse.resolve` → membership 投影 → universe `resolve_history` |
| `industry_classification` | 仅 data service | `IndustryReader.get_all` → `InstrumentService.find_industries`；未追到应用调用，不能借行业映射消费证明分类目录闭环 |
| `industry_mapping` | 回测内部应用 | `IndustryMappingReader.get_stock_industry` → `InstrumentService.get_stock_industry` → `build_classification_snapshot_fn` → `BacktestRuntimeBuilder` data feed／factor bundle |
| `namechange` | 选股 HTTP | `NameHistoryReader.get_names_batch` → `InstrumentService.get_stock_names` → `_metadata_identities.names` → `AssembleSelectionFacts.assemble` → selection `assemble_selection_run` |
| `st_history` | 选股 HTTP | `StChangeHistoryReader.get_st_status_batch` → `InstrumentService.get_st_status_batch` → `_metadata_identities.st_status` → 同一选股组装入口 |
| `futures_daily` | 仅 storage | `FuturesDailyReader` 已注入 `MarketReaders.futures_daily`；`get_bars_reader` 无 futures 分支，未追到应用查询 |
| `futures_basic` | 仅 storage | `FuturesBasicReader` 已装配；保存合约快照不等于注册为 metadata instruments，未追到应用读取 |
| `earnings_forecast` | 仅 storage | `EarningsForecastReader` 已装配；未追到应用研究读取 |
| `earnings_express` | 仅 storage | `EarningsExpressReader` 已装配；未追到应用研究读取 |
| `index_valuation` | 仅 storage | `IndexValuationReader` 已装配；`CapitalStore` 无对应读取，股票 valuation API 不消费此表 |

可复用消费家族的核对点：[行情 API](../../apps/backend/src/ditto_apps/api/routes/market.py)、[元数据 API](../../apps/backend/src/ditto_apps/api/routes/metadata.py)、[财务 API](../../apps/backend/src/ditto_apps/api/routes/fundamental.py)、[资金 API](../../apps/backend/src/ditto_apps/api/routes/capital.py)、[运维 CLI](../../apps/backend/src/ditto_apps/cli/commands/ops.py)、[历史证券池投影](../../packages/application/src/ditto_application/queries/historical_universe.py)、[回测分类截面](../../packages/application/src/ditto_application/processes/execution/classification_snapshot.py)与[选股身份装配](../../packages/application/src/ditto_application/providers_selection.py)。未接应用的 16 项是所查生产入口与调用链中的缺口，不是断言存储实现缺失。

**FRED 已有条件接线，代码存在与实际落库分别判断。** [SourcesProvider.fred_source](../../packages/data/src/ditto_data/di/sources.py) 在有 key 时创建并注册 FredSource；[coordinator_factory._source_fetchers_for](../../packages/application/src/ditto_application/processes/ingestion/coordinator_factory.py) 在 Source.FRED 下选择 MacroFetcher，已有宏观 latest 查询可消费写入后的指标。这不改变现场事实：当前只有 7 个中国宏观 indicator_id、快照 source 全为 tushare，配置的 51 个 FRED 系列尚未在本次库存中形成落库证据。商品的 FXCM／FRED／Sina 腿由 [commodity_fetcher](../../packages/application/src/ditto_application/processes/ingestion/commodity_fetcher.py) 组织；R2 且非 FRED 协调器主动关闭 FRED 腿，Sina 依赖 sina_enabled。未配置跳过、已配置调用失败、已落库但未验收必须分别记录，商品 HTTP 已接不证明每条来源腿可用。

## 单机备份容量决策

容量于 **20:40:57 CST** 用 `df`／`statvfs`／文件 `st_size` 与 `st_blocks×512` 只读核对；metadata 页归属于 20:42:24 用只读 `dbstat` 分组（含索引）。卷总 **245.107 GB**、可用 **58.422 GB**。下表 GB 为十进制，allocated 为文件实际块数，不计目录／manifest 少量开销；日志及旧备份副本不纳入新备份集。

| 内容 | 逻辑 GB | allocated GB |
| --- | ---: | ---: |
| metadata＋trading 库；独立 research／agent 库当前未初始化 | 5.150491 | 5.153825 |
| 全部 provider payload／schema；research artifacts 当前无目录 | 5.097177 | 5.157204 |
| 精简单份候选下限 B：上述所有不可重拉事实、现有证据及整份 metadata | 10.247668 | 10.311029 |
| 全部 canonical Parquet C | 1.518040 | 1.518658 |
| 完整单份 B＋C | 11.765707 | 11.829686 |

现有[SQLite 备份](../../packages/platform/src/ditto_platform/foundation/storage/sqlite_backup.py)使用 Backup API 写 `.partial` 后硬链接发布同一 inode，[payload 备份](../../packages/platform/src/ditto_platform/foundation/storage/payload_backup.py)使用 `copy2`；均原样保存，无 zip/gzip，不假设压缩收益，也不把同一 `.partial` 再算成一份独立副本。
若两代备份、一次隔离恢复、新一代暂存同时存在，仅四份内容就需完整 **47.319 GB**／候选精简 **41.244 GB**，还未计排序或重建工作区；因此选择**优先有证据的精简、日备份保留两代、备份与恢复互斥**。候选最大每份节省 1.519 GB canonical，保留整份 metadata、全部现有 payload 以及 paper/manual、策略、研究、agent 等不可重拉事实；不新增引用裁剪框架，不因研究快照表当前为空而删旧证据。
本轮仅检查留存 payload 引用存在，**未证明全部 canonical 可省略**。实施前逐分区验证备份载荷覆盖、版本／变换身份与重建结果；仅可重建分区可省略，旧快照重放必须使用原留存证据，重新拉取当前版本不能替代。不能证明可重建的分区仍须备份：若其 allocated 为 P GB，保守峰值重算为 `3×(10.311028736+P)+5.082251264 GB`，不满足空间门就阻断。
全部 canonical 通过重建验收时的候选峰值按 allocated 计算：`3B + W = 3×10.311028736 + 5.082251264 = 36.015337472 GB`。第三份槽位供新备份暂存或隔离恢复二选一；`W` **包含**恢复出的全部 canonical 1.518657536 GB，余 **3.563593728 GB** 供有界分区临时文件／WAL／校验排序，不能重复分配。完整方案同口径需 40.571310080 GB；候选精简峰值少 4.556 GB。
精简预算后剩 `58.422366208−36.015337472=22.407028736 GB`。以 **20 GiB（21.474836480 GB）** 为本项目保守剩余空间门，仅多 **0.932 GB**；这是规划假设，**不是 Mac 官方要求或已实测的重建峰值**。按分区重建并监测共享工作区；超预算或空间门不足必须阻断，保留证据，不自动删数据、缩小 47 项目标或牺牲已承诺重放。47 项补齐增长尚不能精确量化，补齐后及每次备份前重测。
metadata 的 5.080 GB 页占用中，11 张金融事实表及索引约 **3.350 GB**、ETF 参考观察 **0.845 GB**、其他身份／目录／摄取／策略等元数据 **0.210 GB**、freelist **0.674 GB**。金融事实是未来验证重建能力的候选，不是已证明可丢弃的数据；当前配方整体复制数据库，不把这些页算作现成节省，也不清理 freelist。进一步精简须先证明版本／来源与保存研究引用均可恢复。
本地证据 `capacity.json` SHA-256：`080070d26b9feb815708463f9f3b8a4140af80564af6038173b011426e9da39a`；`metadata-page-usage.json`：`84590167cd57b0a9ea2924ce3613a1d59398a3ce1f182cc5730613025fc6e6c6`。本次没有创建备份、执行恢复或测得 24 小时恢复能力。

## 未验证边界

本轮未在真实根运行 HTTP／CLI／浏览器研究旅程；上述静态调用链不是实际演示通过、PIT 正确或完整性通过。尤其通用 ETF 复权、两融可知日等已证实缺陷仍存在；声明 pit_asof 的 API 也不能仅凭标签过关。
核心价格复测沿用[旧审计](../data/price-identity-verification.md)的生命周期与状态归因规则，没有逐条核验这些基础身份／状态是否正确；旧截止数字可复现，不能据此把污染分母或源表达失真当作已解决。
其余基金／合约／事件的应有分母、历史身份与退市／ST／停牌真值、公告类型、来源权限、修订和 PIT 正确性、真实消费者、备份可恢复性及性能/SLA 均未由本次扫描证明。新 ready 判定必须补足这些承诺范围内的证据。
