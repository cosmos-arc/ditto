# 支撑源核验报告（#629 / 父规格 #621 P5）

实测时间：2026-11-02→11-03（fx/commodity/earnings 四库历史回补同日执行；
FRED 51 系列逐系列 `/series` 探针同日执行；11-02 21:55 夜链为窗口修复后的
首次活体验证：fx_daily 36 行/commodity_daily 31 行落地，零行时代结束）。

覆盖 #629 三项范围：FRED 品种×口径矩阵落档（凭据与端点结论沿用 #622/#631 不重
立）、全球指数/大宗/汇率/业绩事件品种与口径核验、加密范围独立运行协议声明
（不默认拼源）。

机读真源：[coverage-contract.yaml](coverage-contract.yaml) 对应条目（刷新后与
`packages/data/src/ditto_data/coverage/limits.py` 蒸馏同步，守卫测试钉住）。

## 根因修复：单日请求 vs 源端可得节奏（CODE）

#622 将 fx/earnings 零行定性为「摄取链空转、根因归 P1」。#623（失败分类）合并后
夜链仍 SUCCESS/0——本票实测定位真根因并修复：

- **fx_daily 六对全空**：FXCM 对 K 线按 **GMT 日**收盘（北京次日凌晨 08:00 闭合），
  21:30 夜链请求「北京当日」恒为未闭合日——单日请求结构上永远取不到行（10-26→
  10-30 连续五日 SUCCESS/0 实证；窗口探针同端点同 token 返回 10-27..10-29 行）。
- **commodity_daily 仅新浪腿落地（3 行/日）**：FRED 油/VIX 腿按美东发布节奏
  T+1 上市、FXCM 金属腿同 GMT 收盘——单日「今日」请求同样恒空；唯新浪端点无
  窗口参数（源侧全量返回后本地过滤）不受影响。
- **earnings 两库链路本已通**：forecast 10-30 落 1 行（002475.SZ）实证；零行=
  正常无公告日，非故障（与 #626 hk_hold 平日 0 行语义同类）。

修复（global_index 既有回看窗口模式推广，`dataset_registry.py`/`coordinator.py`）：

- fx/commodity 日更取数改 **7 日回看窗口**（`FX_COMMODITY_LOOKBACK_DAYS=7`），
  GMT 昨日行每日落地、迟到行窗口内自愈；`request_bounds` 声明同一窗口（证据
  retained payload 严格校验与请求区间一致，#635 教训），coordinator 取数与注册
  表声明同源（`fx_commodity_request_bounds` 单一实现）。
- 同值重拉由写入层 VERIFY_IDENTICAL 去重；跨年窗口行在两侧年分区各存一份、
  读取侧 key 去重（global_index 既有取舍，见其注册注释）。
- fx 历史回补路由 **月块区间单请求**（fx 端点本身即区间 API：6 对×154 月≈924
  请求，替代日级循环 ~28k 请求）；commodity 沿用既有区间路由。
- 回补 CLI 四命令：`backfill macro fx|commodity`、`backfill fundamental
  forecast|express`。

## fx 品种×口径矩阵

数据集 `fx_daily`（Tushare `fx_daily` 端点，FXCM bid 报价）。

| source_ticker | instrument_id | 品种 | 落库起点（实测） | 源端历史深度 |
| --- | --- | --- | --- | --- |
| USDCNH.FXCM | 4,000,001 | 美元/离岸人民币 | 2014-01-02 | 2012-02-18（离岸 CNH 2010 设立，晚于其余五对） |
| EURUSD.FXCM | 4,000,002 | 欧元/美元 | 2014-01-01 | 2001-09-09（实测探针） |
| GBPUSD.FXCM | 4,000,003 | 英镑/美元 | 2014-01-01 | 早于 2014（2014 目标窗内全覆盖） |
| USDJPY.FXCM | 4,000,004 | 美元/日元 | 2014-01-01 | 早于 2014（同上） |
| AUDUSD.FXCM | 4,000,005 | 澳元/美元 | 2014-01-01 | 早于 2014（同上） |
| USDCAD.FXCM | 4,000,006 | 美元/加元 | 2014-01-01 | 早于 2014（同上） |

回补落库：23,993 行，六对全部 2014-01-01/02 → 2026-10-31（3,945-4,044 行/对）。
`trade_date_utc` 合同精度 ms 无时区（UTC 墙钟）；存量分区已按无损迁移对齐
（correctness W2）。

口径要点（消费侧不得误读）：

- **bid 价格作 OHLC**（非 mid/ask）；`trade_date` 为 **GMT 日**，`trade_date_utc`
  为该 GMT 日 00:00 UTC——跨时区对齐时不得按北京日历直读。
- 周六存在部分日行（外汇 24/5，周日 GMT 行基本缺席）——周末 0 行=正常空。
- USDCNH 源端起点 2012-02-18 晚于其余五对（离岸人民币 2010 年才设立），2014
  目标窗内六对全覆盖。

## commodity 品种×口径矩阵

数据集 `commodity_daily` 为**三腿复合源**（完整性合同 #432：任一已配置腿失败
即整体 FAIL，不允许「只剩金银」批次被报完整；合法空=周末/节假日无观察行）。

| 腿 | 品种（instrument_id） | 口径 | 接线状态与落库实测 |
| --- | --- | --- | --- |
| FRED | COMMOD_WTI/DCOILWTICO (5,000,001)、COMMOD_BRENT/DCOILBRENTEU (5,000,002)、VIX_30D/VIXCLS (5,100,001) | 单值序列：仅 `close`，open/high/low 置空，不把单点参考值伪装成日内 OHLC；`trade_date_utc` 为纽约午夜占位（ms 无时区合同精度，#629 统一） | **已配置未接线**（见下） |
| Tushare(fx_daily) | COMMOD_GOLD/XAUUSD.FXCM (5,000,003)、COMMOD_SILVER/XAGUSD.FXCM (5,000,004) | FXCM bid OHLC，GMT 日（同上表 fx 口径）；FRED LBMA 金银系列已死，故走此路 | **2014-01-01 → 2026-10-31**（3,495/3,530 行） |
| 新浪（#436） | CL (5,000,005)、GC (5,000,006)、SI (5,000,007) | NYMEX WTI / COMEX 黄金 / COMEX 白银**连续合约参考**（美元/桶、美元/盎司）；免费无 SLA，端点无窗口参数（源侧全量返回后本地过滤） | CL 2014-01-01 →（3,326 行）；GC/SI 2016-11-02 →（各 2,588 行，端点历史深度） |

**FRED 油/VIX 腿「已配置未接线」的机制边界（实测定位，不视为故障）**：R2 证据
一致性守卫（`coordinator_factory.py`）规定 tushare 车道协调器不带 FRED 直连
（`fred_source=None`，worker 日志 5 次 `FRED source not configured` 警告实证）
——否则 FRED 直连行会进入 tushare 归属的证据链，破坏 PIT 审计的源归属；
而 `commodity_daily.supported_sources=('tushare',)`（无 fred 车道，
`fallback_mode=manual`）。三腿按源分解的车道设计变更超出本票口径（FRED
工作已收窄为矩阵落档），接线归后续票：需先解决复合源逐腿证据归属。**接线时
须一并裁决的已知口径债（correctness W3 留档，当前潜伏）**：FRED 腿查询窗=
北京日−1（`get_fred_query_date`），月块声明的首尾各含一行区间外观察日、
12-31 观察日确定由次年 1 月块取到——声明区间 vs 载荷行日的一致性、以及
相邻月块重取修订行的 VERIFY_IDENTICAL 拒收策略，随接线票一并定界。

- provider 标签 `commodity_reference` 非真实 API（#622 已定界）；金属腿真实端点
  为 tushare `fx_daily`（metal 通道）。
- SHFE 修正 ID 等坑沿用 #434-#437 既有规则，不重立。
- 2026 尾段新浪行经 force 近窗重取收敛（#625 语义：连续参考系列源端修订，
  KEEP_LAST 接受现值）。

## 修复实录：commodity 三腿 dtype 合同（CODE）

回补首跑 13 chunk 全失败：FRED 腿 `trade_date_utc` 为 μs-UTC、金属腿 μs-UTC、
新浪腿 ms-无时区——三腿首次真实合流时 `pl.concat` SchemaError。单日时代
FRED/金属腿恒空、从未参与 concat，缺口被掩盖。修复=两发射端对齐
`COMMODITY_SOURCE_SCHEMA` 的 ms-无时区（UTC 墙钟承载语义，与新浪腿及存量
分区一致），回归测试钉住 dtype 与三腿 concat。

## global_index_daily 品种×口径核验（不加改变）

21 个 source_ticker（#435 官方篮子，`ditto_data.models.GLOBAL_INDEX_CODES` 权威
清单）：

XIN9（富时中国A50）、HSI（恒生）、HKTECH（恒生科技）、HKAH（恒生国企）、
DJI（道琼斯）、SPX（标普500）、IXIC（纳斯达克）、RUT（罗素2000）、FTSE（英国
富时100）、FCHI（法国CAC40）、GDAXI（德国DAX）、N225（日经225）、KS11（韩国
KOSPI）、AS51（澳洲标普200）、SENSEX（印度孟买）、IBOVESPA（巴西）、RTS（俄
罗斯）、TWII（台湾加权）、CKLSE（马来西亚）、SPTSX（加拿大）、CSX5P（新加坡
海峡时报）。

口径要点：`currency=mixed`/`timezone=source_defined`（各自市场日历与货币，
不折算）；典型可得时刻 21:30 北京；**拉取即观察**（observation 知识轴），
7 日回看窗口自愈（#619 拼接修复后 28/29 连续成功，旧故障不重立）。instrument
列为 source_ticker，不发明本地 instrument 身份。

## earnings 两库口径（链路已通，历史回补归本票）

| 数据集 | 端点 | 键 | 口径要点 |
| --- | --- | --- | --- |
| earnings_forecast | forecast（按标的）/ forecast_vip（市场级公告日） | (source_ticker, ann_date, report_date, forecast_type, update_flag, knowledge_date) | 上下界型（净利润上下限**万元**）；区间允许单边为空；同日修订按 update_flag 保留为独立版本；公告日驱动（非报告期对齐） |
| earnings_express | express（按标的）/ express_vip（市场级公告日） | (source_ticker, ann_date, report_date, knowledge_date) | 快报为**已审数口径的浓缩披露**，与正式三表非同一颗粒度 |

- 日更=市场级单日 ann_date 单请求；回补走季块日级公告日循环（自然日序列）。
- 平日 0 行=正常无公告，非故障（fail-loud 仅作用于取数错误，#623 分类词汇）。
- **回补落库（2026-11-03 实测）**：forecast 120,461 行/2014-01-01→2026-10-30
  （唯一缺口 2024-01-31——forecast_vip 年度预告高峰日经代理确定性
  PaginationCorruptionError，直连探针实证、几何重试不收敛，按 #640 语义
  季块保持可重试、修复通道可见，不冒充完整）；express 24,412 行/
  2014-01-04→2026-10-30 全覆盖（回补期 11 个瞬态失败日已全部重试愈合）。

## FRED 系列矩阵（51 系列全部可达）

逐系列 `/fred/series` 探针（2026-11-02，51/51 HTTP 200，含真实覆盖区间与
单位——矩阵数字段实测，非文档转抄）。**接线状态是关键口径：51 个系列中 0 个
实际落库**——3 个进复合取数器但运行时腿未配置（R2 守卫，见 commodity 节），
其余 48 个为「已配置未接线」——凭据与端点可达 ≠ 已覆盖，
不虚构全覆盖：

| 接线状态 | 系列 | 频率 | 单位（示例） | 覆盖区间（实测） |
| --- | --- | --- | --- | --- |
| **复合取数器内、运行时腿未配置**（commodity_daily FRED 腿，R2 守卫边界见 commodity 节） | DCOILWTICO / DCOILBRENTEU / VIXCLS | D | 美元/桶、指数 | 1986/1987/1990 起 → 2026-10-27/29 |
| 未接线（registry 配置在 `sources/fred/indicators.py`） | 国债收益率曲线 DGS1MO-30Y（10 系列）、T10Y2Y/T10Y3M、盈亏平衡 T10YIE/T5YIE、SOFR/EFFR/DFF/FEDFUNDS、公司债 DAAA/DBAA/BAA/BAMLC0A0CM/BAMLH0A0HYM2 | D/M | Percent | 1954-2023 起 → 2026-09/10 |
| 未接线 | US 宏观（GDP/CPI/核心CPI/PCE/核心PCE/UNRATE/PAYEMS/M2） | Q/M | Percent、Index、Thousands of Persons | 1939-1959 起 → 2026-07/09 |
| 未接线 | 汇率 H.10（DEXJPUS/DEXUSEU/DEXCHUS/DEXUSUK）、美元指数 DTWEXBGS/DTWEXAFEGS | D | 每美元本币数、Index | 1971/1999/1981/2006 起 → 2026-10-23 |
| 未接线 | VIX 衍生（VXNCLS/RVXCLS）、汽油 DHHNGSP/GASREGW、IMF 月度商品（铜/铝/铁矿石/油/欧洲天然气/全商品指数） | D/W/M | Index、美元/加仑、美元/公吨 | 1990-2004 起 → 2026-09/10 |

- macro_indicators（tushare lane）仅取**中国 7 码**（cn_gdp/cpi/ppi/pmi/m/
  sf_month/shibor，884 行）；FRED 美国系列未进 macro_indicators 摄取——如需
  接线属新消费者驱动的增量票，本票不虚构。
- ALFRED realtime（vintage）参数路径 200（#631 实测），`vintage_dates` 端点
  404 为探针端点形状假象，不重立。
- 金银不走 FRED（LBMA 系列已死，见 commodity adapter 注释），经 Tushare
  FXCM bid。

## 加密币种范围：独立运行协议，不默认拼源

现状（2026-11-02）：**仓库无任何加密数据面**——无 crypto 数据集注册、无 provider
适配器、无存储落点、覆盖合同 45 项不含加密品种。Tushare FXCM 通道
（`fx_obasic` 分类）暴露 CRYPTO 类（如 BTCUSD），**本票明确不将其并入
fx_daily / commodity_daily 篮子**（#621 P5 条款：加密币种/交易所/现货衍生品
范围作为独立运行协议）。

未来若引入加密数据，须独立票面先行裁定并落协议，至少覆盖：

- 品种范围（币种清单）与交易所范围（中心化/去中心化、现货 vs 永续/期货衍生品
  分列，不混同口径）；
- 时间语义（7×24 无日历闭合、UTC 日界、交易所维护停机段的处理）与 PIT 证据
  （成交所快照身份、重放/修订语义）；
- 凭据、配额与源选型独立于 Tushare/FRED 既有预算（补源采购另行授权）。

## 测量结果（回补后落档）

见 coverage-contract.yaml 对应条目 `measured`（行数/起点/末端随本票刷新）；
本节数字以 YAML 为准，避免双真源漂移。

## 验收对照（#621 P5 条款）

- **品种×口径矩阵落档**：✓（本文件四张矩阵 + FRED 51 系列接线状态表）。
- **失败响亮不静默**：✓ 复合源完整性合同（缺腿整体 FAIL）+ #623 分类词汇 +
  本票新增窗口声明（request_bounds 与真实取数一致，证据链可审计）。
- **不虚构全覆盖**：✓ FRED 48 系列明确「已配置未接线」；USDCNH 源端起点
  2012-02-18 晚于其余五对如实落档；新浪腿「连续合约参考」非可回测合约。
- 加密不默认拼源：✓（独立运行协议声明，无实现面）。
