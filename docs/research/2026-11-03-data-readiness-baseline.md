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
原始 JSON 仅留在本地临时证据目录，含机器路径，不提交、不推送；下列摘要用其最终文件字节的 SHA-256 绑定。

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

## 消费与未验证边界

本轮消费路径只做静态源码核验：已有 application 查询、通用／专用行情入口、账本及快照读取；没有在真实根进行 HTTP／CLI／浏览器研究旅程演示，不能以物理表或 API 存在替代可用性。
核心价格复测沿用[旧审计](../data/price-identity-verification.md)的生命周期与状态归因规则，没有逐条核验这些基础身份／状态是否正确；旧截止数字可复现，不能据此把污染分母或源表达失真当作已解决。
其余基金／合约／事件的应有分母、历史身份与退市／ST／停牌真值、公告类型、来源权限、修订和 PIT 正确性、真实消费者、备份可恢复性及性能/SLA 均未由本次扫描证明。新 ready 判定必须补足这些承诺范围内的证据。
