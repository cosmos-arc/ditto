# 资金资格与发布后修补（#706 / #707）

本批实现按 #705 的最新观察语义交付。CODE/TEST 与 LIVE 分开：下面的真实根盘点为只读，
尚未在真实根应用纠偏或切换 worker，不能据此关闭运行验收。PR 由维护者合并。

## 版本与影响

普通 SQLite/Parquet 读取先排除撤销资格，再选有效事实。纠偏先写不可变影响清单与资格
规则，再通过原 writer 写替代版本；中断后允许缺数据，不能重新泄漏旧版本。原投影、
provider payload 和快照身份保留。显式 `ProviderSnapshotQuery.read_for_audit` 仍重放
绑定的原 payload，不能作为新研究的当前正确性通过证据。

`scan --output` 包含事实键、日期、标的、通道、旧新知识日、目标分区、来源快照、既有
`kd_correction` checksum、消费者及规则版本。`apply` 在任何 canonical 写入前保存
完整清单到 `operations/capital-corrections/<sha256>.json`；查询只读
`capital/corrections/<dataset>/<sha256>.json` 的紧凑日期/旧知识日规则。

2026-11-07 13:42–13:43（上海），对 `/Users/chevy/Desktop/code/ditto/data` 的只读扫描：

| dataset | 待撤销日期/旧版本组 | 旧版本事实键数 |
|---|---:|---:|
| margin_trading | 713 | 1,457,767 |
| hsgt_top10 | 575 | 10,540 |
| hk_hold | 422 | 945,614 |

没有 ambiguous/unanchorable 组。扫描文件为工作树
`.cache/issues-706-707/capital-impact.json`，383,597,134 bytes，SHA-256
`06eff9005bb79726ef8244f49b85479f3b323aa8bf2f4bc3c65bd30bcc5a1d61`。
这是带事实清单的本机操作证据，不将 366 MiB 历史清单提交到 Git。实施前须在停写窗口重扫；
当前扫描不冻结仍运行的 worker，也不授权扩大 dataset 范围。

消费者核对同时检查 dataset、业务日期/标的和解释规则；原快照身份不变也可能受影响。
已知在线消费者为两融 HTTP/CLI、资金画像、hk_hold/hsgt HTTP；Web 刷新仅 refetch 当前
capital-profile query。因子 `materialization/dependency_registry.py` 未注册这三个输入，
不触发全库物化。

冻结产物交叉核查（同一真实根，2026-11-07）：research spine/dataset spec/snapshot
四表均 0 行、derived_run 0 行；磁盘（排除 backups）未发现 manifest JSON。另检查
2 个 strategy_run 的 config/checkpoint、5 个 selection_run 的 payload、Paper 的
1 session / 3 mutations / 10 executions / 1 reconciliation 的 payload。没有三个资金
数据集引用；selection 输入是 stock_basic/stock_daily/stock_status/adj_factor，两个
backtest lineage 的输入为 market_data 与 seed_stock_selection_rotation，输出为
backtest_report。没有仅因 lineage 无边而判定无依赖。本轮未发现命中冻结产物，不创建
无消费者的新 run。后续若出现命中，按新规则生成新 snapshot/run/manifest 并记录替代关系，
不得原地覆盖旧产物；不能只用 snapshot ID 比较免除解释修正。

## 发布后补取与终态

新增 Prefect 部署：08:35、08:50、09:05 仅检查上个交易日两融，完成后停止请求；
09:15 独立最终检查，不再发起补取。使用本地交易日历处理周末/节假日，证据按计划交易日
归属；真实完成时间晚于截止不算准时。每次证据内容寻址，迟到结果不能覆盖旧截止失败。
默认依据 [margin_detail 官方发布说明](https://tushare.pro/document/2?doc_id=59)。

FRED 独立 source 每天 07:30 运行现有 macro_indicators 摄取。仍用既有按频率回看窗口，
记录逐系列末端及缺失配置系列，不新增每系列调度。该时间与 21:55 日摄取、02:00 修补错峰；
实际历史回补保持 parallel=1，避开晨间窗口，不同时启动共享凭据回补。

retry/holes 的显式 required_start/end 与 daily 的 required_dates 指定必需范围；daily
默认最近五个交易日。最终读取完整账本，永久错误、耗尽、limit 排除均不能获得成功终态。
后续兄弟步骤治愈同一 dataset 后重新判定。范围外历史项保留；accepted_gaps 要求
精确 dataset/source/date/error_code 和裁决 evidence。显式研究所需历史范围仍阻断。

## 真实失败核查与阻断

2026-11-07 只读 ledger：top_list 的 11-04/05/06 已 SUCCESS（79/68/78 行）；
etf_nav 11-04 与 11-06 为 FETCH_ERROR，11-05 SUCCESS 10,040 行。
当前源参数/分页修复基线为 #714，详见
[来源契约审计](../research/2026-11-07-source-interface-contract-audit.md)。

最初临时探针直接构造 `DataSourceSettings()`，误用了官方默认地址；维护者的凭据
仅适用于既有代理，该次“token 不对”的结果已作废，不能作为实际运行凭据失效或旧
FETCH_ERROR 的根因证据。真实 worker 为 development 环境，必须经同一
`ConfigProvider.data_source_settings(ConfigLoader(...))` 加载代理地址、限频、超时和
凭据，并注册实际数据指标后，再调用 `ETFTushareAdapter.fetch_fund_nav`。

已按实际配置重新探测 11-04、11-06；代理上的前置 `etf_basic` 可正常返回。后续
`fund_nav` 同范围结果记录在本机 `nav-probe-configured.json`（不含凭据），最终状态
在 #707 交接中记录。原 `nav-probe.json` 仅保留为错误探针的审计记录，不用于验收。
源读取成功仍需完成 snapshot 与真实消费者闭合；不能把源失败当作空响应、合法无事件
或尚未发布。

正确代理配置下两个只读窗口分别返回 10,148 / 10,112 行、各 1,693 个 ETF。正式补取
进一步复现 `RemoteProtocolError: Server disconnected without sending a response.`；
原共享请求层只捕获 NetworkError/TimeoutException，漏掉此异常，无法进入单页重试。
本批将服务端协议断连纳入同一有限重试（最多三次）；已成功页不重拉，耗尽时拒绝部分结果。
没有将 LocalProtocolError 等本地请求错误纳入重试。

同时核对到主目录仍为 `d3e4c94d`，尚无已合并的 #712/#714 源修复；只读探针和候选
验证使用独立工作树的新代码。合并后须同步实际运行目录，再切换启动入口/部署，不能
将候选 CI 或一次手工补取当作旧 worker 已升级的证据。

本轮不能声称真实发布后 09:15、FRED 末端或连续 5 个交易日已验收；5 日结论由 #705
最终验收包统一记录。

## 日志启动与部署

应用保持 INFO，主日志/错误日志各默认 20 MiB、5 个历史文件。外层 stdout/stderr 通过
标准库 RotatingFileHandler 同样限额；仅轮转日志，不触碰 payload、账本、研究产物。
新入口 `scripts/start-prefect-worker.sh` 读取现有 `.env`，复用同一 process work pool，
将 stdout/stderr 合并到 `$DITTO_CACHE_ROOT/prefect-worker/worker.log`。

已核对真实 PID 4219：pool=ditto-data-pool、worker=ditto-data-1，配置根为主 checkout、
state 为上述 data 根，fd 1/2 指向主 checkout `.cache/prefect-worker/worker.log`。
旧 `.cache/prefect-worker/start-worker.sh` 仍由终端/nohup 启动，不能假定新增包装器自动生效。
合并并部署后，让该入口委托版本化 `scripts/start-prefect-worker.sh`，停止旧 worker 后
启动一次，再核对 PID/父子进程和日志 fd；不要停止共享 Prefect Server。调度由现有
`ditto_apps.jobs.flows.deploy --only ingestion` 入口更新。当前未切换运行进程。

容量只读检查：盘余量 44,991,596 KiB（大于 20 GiB 门）；真实 metadata WAL
4,177,712 bytes，mtime=11:38，本轮只读操作未更新；data/logs 1,324 KiB、data/temp 0。
本轮影响清单及标准输出约各 366 MiB，属于隔离临时证据增量，不是生产日志增长验收。
真实回补/部署前后须重新记录余量、WAL、日志与临时空间，不提前声明该运行门通过。

## 独立审查与修复

首审固定 `8bd3d31d...76e9307d`，两条独立审查分别给出以下发现；没有用其中一轴
替代另一轴。规范轴 3 项：未完成 revision 仍可能得到晨间 ready、忽略 TERM 的 worker
让包装器无限阻塞、application 承担物理证据 I/O。需求轴 3 项：旧大日志轮转后仍超限、
单独 retry/holes 默认全历史、表外季度已有首锚导致其他旧投影未撤销。

集中修复恢复 pending revision 守卫，使用独立 10 秒停止计时器，证据存储下沉到 data；
启动时仅对目标日志及数字代保留有界尾部，补偿入口统一五交易日默认窗，保留季度首锚
同时纠正未锚定旧行。新增反例覆盖忽略 TERM、已有 64 KiB 日志、默认历史留账与显式
研究阻断、未完成新 revision。

本次 OpenAPI 默认语义变更使 R5 preflight **汇总**中的 interface_contracts 哈希变化。
通过原 `r5_agent_release_preflight` 生成器更新派生汇总，只改变契约与汇总身份；没有
重写底层 sandbox/live eval 证据，也不声称重新完成 R5 真实运行验收。

规范复审识别出首锚修复中的跨标的时间回退：未锚行不能借用另一标的的较早观察锚。
已保留既有已锚版本，并让未锚行继续使用可核验来源观察时间；新增不同观察日期的
反例，来源 02-01 时不得改成另一标的的 01-15。该问题分类为修复引入，未影响本机
官方披露表内的上述只读盘点数字。
