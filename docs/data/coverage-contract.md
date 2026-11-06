# 数据集覆盖合同（#622 / 父规格 #621）

> 2026-11-06 更新：当前47项量测、真实业务消费、补数与未闭合差额见 [#708执行记录](readiness-708-2026-11.md)。YAML和运行时limits已同步刷新；下文“头条结论”和场景勾选保留原测量时点，不作为当前就绪证明。基金不再按Q2/Q4推断全持仓；按需逐基金批次保留全部持有人，自动日更新鲜度尚未承诺。


机读真源：[coverage-contract.yaml](coverage-contract.yaml)（47 项逐条：声明侧 vs 实测侧、状态、缺口、消费者、真实接口）。
本文给出场景→必需输入追踪、头条结论与刷新方法；逐项细节以 YAML 为准。

- 实测时间：2026-10-30（夜链 10-29 之后）；YAML `meta.measured_at` 为 2026-11-03T00:15+08:00 刷新；方法与口径见 YAML `meta`。
- 状态词表：`ready`（预期范围完整且当前）/ `partial`（起点、末端、味道或品种有缺）/ `empty`（本地零行）。`unknown` 禁止出现——未测量项不得冒充就绪。
- **基线校准（#658 批次 0，2026-11-03）**：静态标签是测量快照，不构成 [#652](https://github.com/cosmos-arc/ditto/issues/652) 统一证据门验收；
  正式期望集合（47 项范围/起点/身份/限制/反例）已冻结于 [readiness-freeze-2026-11.md](readiness-freeze-2026-11.md)。
  本文与 YAML 中先于 2026-11-03 20:17 [只读基线](../research/2026-11-03-data-readiness-baseline.md) 的末端/行数判断以基线为准，合同数值刷新归后续实施批次。

## 基线校准详情（#658 批次 0）

先于 2026-11-03 20:17 基线扫描的过时结论（下文头条保留原测量时点记录，不回改）：

- `etf_nav` 末端已到 11-02（头条 4 的「末端 10-26 后缺」过时；1,528,803 行）；`fund_share` 末端 10-30；`margin_trading` 末端 10-30；`pledge_ratio` 报告日末端 09-18。
- `limit_list` 本地仍从 2026-09-30 起（840 行）；`futures_daily`/`index_valuation` 仍从 2026-10-26 起——更晚末端不补历史缺口。
- `macro_indicators` 885 行、indicator_id 仅 1–7、末端 09-01；51 个 FRED 系列探针可达但 0 落库。
- `commodity_daily` 现存 instrument 5000003–5000007；配置中的 FRED 油/VIX（5000001/5000002/5100001）未落库（#629 定界）。
- `earnings_forecast`/`earnings_express` 公告日追溯 2014，knowledge_date 最早却为 2026-10-30/11-02——历史回填不等于当年 as-of 可用。
- `dividend` 除权末端 11-02 vs knowledge 末端 10-13；`corporate_actions` action_date 至 2034（计划日）——业务日期、公开日期与采集日期不得混成一个「最新日期」。
- 消费入口静态核验：31 项有应用读取路径（含运维），16 项仅到 storage/data service——逐项现入口见冻结矩阵。
- 请求矩阵（10-27..11-02，46 项×5 日）229/230 完成覆盖；唯一 uncovered＝`industry_mapping` 11-02。
- 单位维度：本合同仅记 `currency`；计量单位（万元/万份/倍/股）核验归 P2 价格口径与 P3c 股数单位反例等 lane 实施票，P0 不伪造全覆盖。逐接口探针结果（62 条：tushare 56 + fred 4 + fuyao 2，含不可达归因）内嵌于 YAML `meta.permission_matrix.probes`。

## 头条结论

1. **「空源」叙事修正（再定界 P1/P3a/P5a）**：`margin_trading`、`hk_hold`、`fx_daily`、`earnings_forecast`、`earnings_express` 本地零行，但逐接口探针证明**源全部可达**（margin_detail 4,486 行/日、hk_hold 4,200 行/日、fx_daily 101 行/日）——是摄取链空转，不是源缺口。五者的修复归 P1（失败分类与补偿），不在 P3 采购/补源范围。**#625 已修 margin_trading 一员**：根因=margin_detail 官方口径 T+1 上午 8:30 更新（深市/北交所周五数据下周一更新），21:55 EOD 波恒空被 SUCCESS/0 固化；晚发布近窗重取（nightly repair force 近 5 交易日）+ 2013-01-04 起历史回补已落地，rzmre 列名语义修正（融资买入额·元，原误标 volume，#390 破坏窗口内改名），详见 docs/data/capital-fund-verification.md。
2. **Tushare 15000 档经代理 55 接口探针 52 可达**。仅 `rights`（50101，#517-#523 已裁决降级→corporate_actions 缺分配预案味道）与 `csrc_industrial`（2002 权限不足→industry_classification 仅申万线）不可达；`cn_macro` 是 provider 标签假象，真实 `cn_gdp/cn_cpi/cn_ppi/cn_pmi/cn_m/sf_month/shibor` 全部可达。**当前凭据没有需要补源的证据。**
3. **FRED 修通一半**：`series_observations`（含 ALFRED realtime 参数）全部 200，`.env` 有 key；夜链 macro/fx/commodity 仍 failed（10-29），根因在链路不在凭据（归 P1/P5a）。
4. **2014 目标达成面**：核心价格链 `stock_daily/adj_factor/stock_limit/etf_daily/fund_adj/index_daily/global_index_daily/moneyflow/valuation_metrics/index_weight/dividend` 均为 ready（多数 2013 起超目标）；`etf_nav`（末端 10-26 后缺）与 `fund_share`（末端 10-27）为 partial。`stock_status` 本地实测起点 2016-08-09（bak_basic 官方声明为2016年起）；`cyq_perf` 官方起点 2018。**#626 事件披露四接口已回补落档（2026-11-01）**：`top_list`（192,527 行/2014 起）/`top_inst`（2,343,110 行/2014 起）/`hsgt_top10`（50,730 行/2014-11-17 起）ready；`hk_hold` partial（4,224,382 行/2016-06-29 源墙起，北向按披露制度分段，2024-08-19 后仅季度末北向）——矩阵与对拍见 event-disclosure-verification.md。**#627 持仓披露三库已回补落档（2026-11-02）**：`top10_holders`（2,500,525 行/2014-01-02 起）与 `top10_floatholders`（2,097,949 行/2014-01-08 起）ready 新通路；`fund_portfolio` 609,923 行/1,544 只交易所基金/2014-01-20 起 partial（场外 .OF 子集边界量化定界——单披露日 9,031 只公募 97-100% 场外经 FK 过滤留痕；原季度推断已由#708撤回，报告类型及完整性须原文补证；未披露≠零持仓）——矩阵与对拍见 holdings-disclosure-verification.md。`limit_list/index_valuation/futures_daily/commodity_daily` 仍仅 2026-09/10 起无历史回补。
5. **10-29 夜链 5 个业务 failed 与 Prefect COMPLETED 并存**（etf_nav/fina_indicator/cash_flow/pledge_ratio/macro_indicators），#621 Problem Statement 的系统性缺口在最新一夜仍在发生。
6. **环境足迹**：CLI 不带 `DITTO_STATE_ROOT` 会静默落到 `~/.local/state/ditto` 陈旧库（2026-10-06）并被漂移守卫拦下，报错不指明库路径；`etf_reference` 存量 169 万行观察但 catalog 无条目（ops status 显示 missing）。

## 场景 → 必需输入追踪

符号：✓=ready　⚠=partial　✗=empty（详见 YAML 对应条目）。

| 场景 | 必需输入 |
| --- | --- |
| 看图/图表工作台（#193/#208） | stock_daily✓ adj_factor✓ etf_daily✓ etf_nav⚠ fund_adj✓ index_daily✓ global_index_daily✓ stock_limit✓ calendar✓ stock_basic✓ etf_basic✓ index_basic✓ etf_reference⚠（catalog 登记缺） limit_list⚠ moneyflow✓ top_list✓(回补,#626) |
| Price Action／威科夫研究 | stock_daily✓ adj_factor✓ stock_status⚠ namechange✓ st_history✓ calendar✓ |
| 行业/指数轮动 | industry_classification⚠ industry_mapping✓ index_weight✓ index_daily✓ stock_daily✓ valuation_metrics✓ |
| 资金面（#621 P3） | moneyflow⚠(BSE 源端限制,2026-10-31 起) margin_trading⚠(通路修复+回补,#625) hk_hold⚠(回补+制度分段,#626) hsgt_top10✓(回补,#626) fund_share⚠(尾部已愈,#625) top_list✓(回补,#626) top_inst✓(回补,#626) top10_holders✓(新通路+回补,#627) top10_floatholders✓(新通路+回补,#627) fund_portfolio⚠(2014 起回补+场外边界定界,#627) cyq_perf⚠ index_valuation⚠ pledge_ratio⚠ |
| 回测（严格 PIT，#621 P2/P4） | calendar✓ stock_daily✓ adj_factor✓ stock_status⚠ stock_limit✓ balance_sheet✓ income_statement✓ cash_flow✓ fina_indicator✓ dividend✓ corporate_actions⚠ valuation_metrics✓ index_daily✓ |
| 宏观/市场背景（P5a） | macro_indicators⚠ fx_daily✗ commodity_daily⚠ global_index_daily✓ futures_daily⚠ futures_basic✓ |

## 已并入的既有裁决（不重开）

- BSE 244 标的不覆盖（#575，2026-10-19 关票：国证2000/中证2000 自 2023 含 .BJ 成员，全宇宙 fail-closed）。
- `rights`/`csrc` 代理与权限限制维持 #517-#523 降级裁决。
- adj_factor 黄金集作用域（#620）；global_index 拼接旧故障不重立（#619）。
- fina 存量 33,851 组跨年错位已由 #620 修复（2026-10-27 分区修复 --apply，2026-11-03 复测零跨分区同键）；init_schema 漂移由 #620 影子库结构校验收口（#613 线留档）。

## 运行时消费（#628 起）

本合同不再只是文档：`packages/data/src/ditto_data/coverage/limits.py` 是其
运行时蒸馏（47 项 status/窗口/gaps/notes/measured_at），由
`packages/data/tests/unit/coverage/test_limits_sync_unit.py` 守卫与 YAML 同步
（刷新 YAML 后须同步蒸馏，否则测试响亮失败）。消费面：
`GET /datasets/coverage`（API 全量）、etf-nav 响应 `data_coverage`（图表链）。
验收记录见 [consumer-pit-verification.md](consumer-pit-verification.md)。

## 刷新方法

复测按 YAML `meta.measurement_method` 重做：`ops status --json`（带 `DITTO_STATE_ROOT`）+ Parquet 逐目录扫描 + SQLite 只读 URI 表级统计 + 每接口一次最小探针；产出回填 YAML 后由守卫测试 `apps/backend/tests/unit/data/test_coverage_contract_unit.py` 校验结构与注册表一致性。刷新属有界实施动作，随 P1/P5 票走，不在本合同内自动进行。
