# 批次2 安全补数与存量纠正报告（#658）

交付时间：2026-11-04（Asia/Shanghai，夜链 11-03 波后停写窗口执行）。
范围＝冻结矩阵批次2（B2）行：备份验恢复、两融/北向存量 knowledge_date 纠正、
逐证券缺口归因、etf_reference 登记、earnings_forecast 2024-01-31 回补、
industry_mapping 11-02 窗口闭合、迟发窗口验证。工具与证据均为本批交付；
未列项归后续批次（见「已知边界与移交」）。

## 1. 备份与恢复路径（先备份后写）

- 备份代次：`ditto-workstation-backups/generation-20261104-pre-b2-correction`
  （运行目录外；manifest v2＝metadata 5,079,531,520 B＋trading 70,959,104 B
  ＋provider payload 树 20,750 文件，全 sha256/logical_sha256 在册，
  integrity ok）。**本代次保留为 B2 有界纠正的回滚点。**
- 隔离恢复演练（`/tmp` 空根）：restore preflight 重验身份后恢复；
  **verify（批次1C 强化版）passed=true，退出码 0**——2 库
  integrity+restored_content PASS、13 条业务事实全 PASS、payload 树
  tree_hash PASS（B1C 证据树哈希校验首次在真实根演练执行）、
  4 条 WARN＝未初始化域声明＋旧实验不可重放声明（预期边界）。
- 边界留档（#446/#630 原边界不变）：跨库恢复不原子（停写窗口内演练）；
  Parquet 数据树不在备份清单（可重拉缓存），本次纠正工具的隔离试跑为此
  把 capital 树拷入恢复副本补齐验证（见 §2）。

## 2. 两融/北向存量 knowledge_date 有界纠正

工具：`ditto_apps.scripts.data_kd_stock_correction`（scan/apply，幂等）。
纠正语义＝#653「正确性修正与存量保护」：新版本行经标准写入端口按冲突键
落库（新 knowledge_date/effective_from＝新身份），**旧行与 payload／快照
证据原样保留**（本地快照重放语义保留「当时机器所见」；PIT 读取按
knowledge_date 收敛到新版本）；每个被纠正 (dataset, trade_date) 在
ingestion_log 记 `source='kd_correction'` SUCCESS 原因行（rows=新版本
行数、checksum=纠正计划哈希），与 tushare 源行互不干扰。

### 2.1 盘点与纠正总账（scan 2026-11-04T01:02，真实根）

| 数据集 | 纠正日期数 | 新版本行数 | 策略 |
| --- | ---: | ---: | --- |
| margin_trading | 713 | 1,457,767 | 下一交易日（B1 权威策略模块） |
| hsgt_top10 | 575 | 10,540 | 下一交易日 |
| hk_hold 日频段 | 404 | 880,272 | 下一交易日 |
| hk_hold 季度段 | 9 | 32,671 | 账本观察锚（见 2.2） |

错误形态＝映射层历史自然日 T+1：周五/节前行的 knowledge_date 早于交易所
真实披露（深市周五数据下周一上午更新），构成 PIT 泄漏；周三等
自然日+1＝下一交易日的行不受影响（值恒等，无需重写）。

### 2.2 hk_hold 季度段观察锚

2024-08-19 起北向改季度披露，真实发布日＝季末后第 5 个北向交易日；
北向日历尚未入库，无发布日证据时以 **provider_snapshots 账本观察时间**
（覆盖该季末日且 row_count>0 的最新快照 created_at，fail-safe 宁晚不早）
为 knowledge_date。九个季度日全部锚定 **2026-11-01**（#625 历史回补
观察日）——旧值（季末自然日+1）对 2024Q3 起的行声称了长达两年余的
虚假前知，纠正后可知时间诚实为本机实际观察日。无覆盖快照的行
（unanchorable）拒绝改动（本次为 0 行）。

### 2.3 隔离试跑（写入端口全链路）

对隔离恢复副本执行 apply（capital 树拷入后覆盖 parquet 路径）：
margin 1,457,767 行＋hsgt 10,540 行＋hk_hold 912,943 行全部写入成功，
抽样验证双版本并存（如 margin 2013-01-04 instrument 1000001：
旧 kd=01-05＋新 kd=01-07；hk_hold 2024-09-30：旧 kd=2024-10-01＋新
kd=2026-11-01）、账本原因行 713+575+413 条齐全。试跑通过后才执行
真实根 apply。

### 2.4 真实根执行结果（applied_at 2026-11-04T01:28）

| 数据集 | dates_corrected | rows_written |
| --- | ---: | ---: |
| margin_trading | 713 | 1,457,767 |
| hsgt_top10 | 575 | 10,540 |
| hk_hold | 413 | 912,943 |

unanchorable=0。真实根验证：margin 2013-01-04 instrument 1000001 双版本
（旧 kd=01-05＋新 kd=01-07）；hk_hold 2024-09-30 双版本（旧 kd=2024-10-01
＋新 kd=2026-11-01）；账本原因行 713＋575＋413；PIT as-of 语义实测——
as_of=旧 kd 日可见旧行（本地快照重放语义），as_of≥新 kd 日收敛到新版本
（`test_get_transition_dual_version_baseline` 同款）。执行时点在 11-03
夜链波后、11-04 夜修波前的停写窗口；备份代次（§1）为回滚点。

## 3. 逐证券缺口归因（基线计数关闭）

工具：`ditto_apps.scripts.data_gap_attribution`（只读；复用
`PriceCoverageAuditService`→`audit_session_coverage` 同一审计引擎）。
生命周期五桶：`bse_out_of_scope`（BSE 个股链范围外——冻结矩阵共同
边界）、`never_any_bar`（窗口内从无行情）、`head_before_first_bar`
（首价前）、`tail_after_last_bar`（末价后＝退市/停供尾部）、
`silent_stretch`（前后有价的中段静默）。

### 3.1 股票（窗口 2014-01-01…2026-11-03，期望 12,746,630 会话）

| 基线计数 | 归因分桶 |
| --- | --- |
| trading_no_bar 10,201 | 中段静默 9,004（长停状态失真——suspend_d 不覆盖长期停牌股，状态行误标未停牌，与旧报告 002260/000670 头部实证一致）；尾部 678；从无行情 368；首价前 51；BSE 100 |
| 缺状态会话 19,278 | 首价前 9,812；尾部 4,453；中段静默 2,355；从无行情 2,115；BSE 543 |
| 停牌有价 1,844 | #507 C1 矛盾证据类，报告不裁决（同前） |
| pre_status_era 190,059 | 2016-08-09 状态源起点前＝证据边界（非失败） |
| 上市日前 bar 76,267 | **100% .BJ**——BSE 920 新码含新三板史，范围外存量保留（不裁剪） |
| 缺上市日名册 3 | 600849.SH／300060.SZ／002525.SZ（list_date NULL，历次名册未给值） |

### 3.2 ETF（期望 1,814,059 会话）

| 基线计数 | 归因分桶 |
| --- | --- |
| no_status_dataset 211,021 | 尾部 144,011（68%，退市/J 旧码/车道尾部缺口——512390.SH 行情止于 10-22、560650.SH 类同）；首价前 43,172；中段静默 12,279；从无行情 11,559（LOF/场外源不覆盖） |
| 有价缺因子 92 | 65 只 ETF：60 只各 1–2 会话（上市边缘滞后形态）；512390.SH 20 会话（2026-09-14 起因子止于 09-09——车道尾部缺口）；560650.SH 8 会话（2026-07 窗） |
| 上市日前 bar 3,481 | 新旧码转换（SH 2,372＋SZ 1,109） |

**归因结论**：冻结矩阵 B2 项「待归因异常」全部分桶完毕——范围外
（BSE/旧码）与生命周期边界（首价前/尾部/从无行情）合计占比见上表；
**残余真缺数候选＝中段静默桶**（股票 9,004＋2,355、ETF 12,279），
其主因已定位为 stock_status 对长期停牌股的表达失真（suspend_d 源端
不覆盖），缺状态证据时停牌与缺数不可分辨——显式留作残余，不以改
分母消除；stock_status 源端覆盖改善归后续批次。车道尾部缺口
（512390/560650 等）归 B5 重测与 fuyao 车道跟进。

## 4. etf_reference catalog 登记

经 config 源一次性摄取（`create_ingestion_bundle("config")` +
`coordinator.ingest_date("etf_reference", "2026-11-03")`，走真实证据链——
非手工 INSERT）：`data_catalog_entries` 新行（metadata|etf_reference|[]）、
source=config 快照（10 行，payload retained）、ingestion_log SUCCESS、
观察行 10 条落账（全表 1,730,639 行，2013-01-04…2026-11-03）；
二次执行 skipped（幂等）。合同条目已校准（catalog_latest 2026-11-03
fresh，守卫测试绿）。**语义声明**：夜链 tushare 对 etf_reference 恒
SOURCE_UNSUPPORTED 属设计；SLA 168h 随时间转 stale——config 声明变更时
手动重摄取，无自动节奏、不伪造历史 config 观察（冻结口径）。live-gate
矩阵该数据集仅登记日 attested，历史日 uncovered 属 config 声明源与逐日
市场级覆盖语义的错配，B5 重测按 freshness 口径评。

## 5. 补数

### 5.1 earnings_forecast 2024-01-31（源异常关闭）

季块重放（`backfill fundamental forecast -s 2024-01-01 -e 2024-03-31 -p 1`）
＋直连官方端点单日 force 重取（HTTP_BASE_URL=http://api.tushare.pro）双
通道尝试：**两条通道均确定性复现跨页重复损坏**（forecast_vip 峰值日
~5,000 行跨页重复，页宽位移重试不收敛，B1 强化守卫正确拒发截断数据——
FETCH_ERROR 留痕，attempts 累计 12）。**结论=源端数据异常**，按 #623
证据归因语义关闭（非本地数据洞）：2024Q1 chunk 保持可重试
（PAYLOAD_COMMITTED），代理或官方修复该日数据后重放自然补齐；按标的
forecast 端点回填需 ~5,000 请求，预算不允许，不采用。02-01/01-30 等邻日
已在 #629 落账（3,506 行/日），仅 01-31 单日缺口。

### 5.2 industry_mapping 11-02 窗口闭合

force 单点重刷（`ingest_daily("industry_mapping", "2026-11-02", force=True)`，
~57 请求 SPECIAL 车道）：SUCCESS 7,925 行；live-gate 11-02 格
**attested（7,927）**——10-27…11-02 请求矩阵唯一 uncovered 格闭合，
请求矩阵此后 46 项×5 日全覆盖。

## 6. 迟发窗口验证与夜链事故处置（两融）

margin T 日数据 T+1 上午发布；EOD 夜链 21:55 常得 0 行（SUCCESS rows=0
零行观察固化），由 02:00 daily-repair 滑窗 force 重取（5 交易日窗口）
覆盖。实测（2026-11-04 02:00 夜修）：**margin 11-02 翻转为 SUCCESS
4,485 行且 knowledge_date=2026-11-03（下一交易日）——B1 校准在生产链路
确认生效**；11-03 行按披露制度待 11-04 上午发布后由后续夜修/09:15 窗口
（批次3）补齐。

**11-03 21:55 夜链事故**（DailyIngestionBusinessFailure 5 项）逐项处置：

| 数据集 | 失败形态 | B2 处置与结果 |
| --- | --- | --- |
| index_weight | FETCH_ERROR/transient | 02:00 夜修自动重试治愈（SUCCESS 0=合法无事件） |
| fx_daily | 窗口旧日值修订冲突（#629 七日窗回归） | force 重取 SUCCESS 36 行（KEEP_LAST 收敛到修订值） |
| commodity_daily | 同上 | force 重取 SUCCESS 31 行 |
| etf_nav | 同上（写冲突）；force 重取又撞代理窗口翻页损坏 | 仍 FAIL（FETCH_ERROR/transient，夜修重试通道继续）；与 §5.1 同类源端翻页形态，留待自愈或源端修复 |
| calendar | PARTITION_LIFECYCLE_FAILED（证据提交段） | 分块全 COMPLETE、日历至 2027 完整——无数据洞，后续夜链自然重试 |

#629 七日窗口回归单独立票：窗口内旧日值被供应商修订时，夜链非 force
写入的 identical 守卫拒绝（「retry contains changed values」→
UNKNOWN_ERROR/permanent，不入重试通道）。B2 已用 force 收敛治愈当日并
在此留档；根治（窗口写入策略或冲突分类）归该票。

## 7. 已知边界与移交

- **hk_hold 季度段写入路径 F1 根修未做**：新摄取仍按 run_date 锚定
  （当日写入确定性成立；跨日 force 重放同快照会 SNAPSHOT_CANONICAL_DRIFT
  响亮阻断——B1 已留档边界维持）。北向日历入库后按制度重算发布日并
  出新版本归后续批次；本批观察锚已消除存量前视。
- **#629 七日窗口修订冲突回归**（§6）：fx_daily/commodity_daily/etf_nav
  夜链在窗口旧日值被修订时 deterministic 失败；立票跟踪。
- **margin 出窗残检空白**：`audit-capital-coverage` 明确不含
  margin_trading（无两融标的池名册，期望会话不可推导）；5 交易日滑窗
  外的迟发补发依赖 ops 复查。归后续批次与 #652 统一门重测。
- **中段静默残余**（§3.1）：stock_status 长停表达失真是根因，修复归
  源端覆盖改善（suspend_d）批次。
- 车道尾部缺口（512390.SH／560650.SH 等因子与行情末端）归 fuyao/
  ETF 车道跟进与 B5 重测。
- 2024-01-31 earnings_forecast（§5.1）与 etf_nav 窗口翻页（§6）为
  源端确定性异常，chunk 均保持可重试，源端修复后重放自然补齐。

## 复测入口

```bash
# kd 纠正（scan 只读 / apply 停写窗口内）
.venv/bin/python -m ditto_apps.scripts.data_kd_stock_correction scan --data-root data
# 归因（只读）
.venv/bin/python -m ditto_apps.scripts.data_gap_attribution \
  --data-root data --start 2014-01-01 --end <滚动>
# 备份配方（§1）
.venv/bin/python -m ditto_apps.scripts.workstation_backup_recipe backup \
  --data-root data --backup-dir <新目录>
```
