# 数据集覆盖合同（#622 / 父规格 #621）

机读真源：[coverage-contract.yaml](coverage-contract.yaml)（45 项逐条：声明侧 vs 实测侧、状态、缺口、消费者、真实接口）。
本文给出场景→必需输入追踪、头条结论与刷新方法；逐项细节以 YAML 为准。

- 实测时间：2026-10-30（夜链 10-29 之后）；方法与口径见 YAML `meta`。
- 状态词表：`ready`（预期范围完整且当前）/ `partial`（起点、末端、味道或品种有缺）/ `empty`（本地零行）。`unknown` 禁止出现——未测量项不得冒充就绪。
- 单位维度：本合同仅记 `currency`；计量单位（万元/万份/倍/股）核验归 P2 价格口径与 P3c 股数单位反例等 lane 实施票，P0 不伪造全覆盖。逐接口探针结果（62 条：tushare 56 + fred 4 + fuyao 2，含不可达归因）内嵌于 YAML `meta.permission_matrix.probes`。

## 头条结论

1. **「空源」叙事修正（再定界 P1/P3a/P5a）**：`margin_trading`、`hk_hold`、`fx_daily`、`earnings_forecast`、`earnings_express` 本地零行，但逐接口探针证明**源全部可达**（margin_detail 4,486 行/日、hk_hold 4,200 行/日、fx_daily 101 行/日）——是摄取链空转，不是源缺口。五者的修复归 P1（失败分类与补偿），不在 P3 采购/补源范围。
2. **Tushare 15000 档经代理 55 接口探针 52 可达**。仅 `rights`（50101，#517-#523 已裁决降级→corporate_actions 缺分配预案味道）与 `csrc_industrial`（2002 权限不足→industry_classification 仅申万线）不可达；`cn_macro` 是 provider 标签假象，真实 `cn_gdp/cn_cpi/cn_ppi/cn_pmi/cn_m/sf_month/shibor` 全部可达。**当前凭据没有需要补源的证据。**
3. **FRED 修通一半**：`series_observations`（含 ALFRED realtime 参数）全部 200，`.env` 有 key；夜链 macro/fx/commodity 仍 failed（10-29），根因在链路不在凭据（归 P1/P5a）。
4. **2014 目标达成面**：核心价格链 `stock_daily/adj_factor/stock_limit/etf_daily/fund_adj/index_daily/global_index_daily/moneyflow/valuation_metrics/index_weight/dividend` 均为 ready（多数 2013 起超目标）；`etf_nav`（末端 10-26 后缺）与 `fund_share`（末端 10-27）为 partial。`stock_status` 起点 2016-08-09（bak_basic 官方可得起点）；`cyq_perf` 官方起点 2018；`fund_portfolio` 仅 2026 Q2/Q3；`limit_list/top_list/top_inst/hsgt_top10/index_valuation/futures_daily/commodity_daily` 均仅 2026-09/10 起无历史回补。
5. **10-29 夜链 5 个业务 failed 与 Prefect COMPLETED 并存**（etf_nav/fina_indicator/cash_flow/pledge_ratio/macro_indicators），#621 Problem Statement 的系统性缺口在最新一夜仍在发生。
6. **环境足迹**：CLI 不带 `DITTO_STATE_ROOT` 会静默落到 `~/.local/state/ditto` 陈旧库（2026-10-06）并被漂移守卫拦下，报错不指明库路径；`etf_reference` 存量 169 万行观察但 catalog 无条目（ops status 显示 missing）。

## 场景 → 必需输入追踪

符号：✓=ready　⚠=partial　✗=empty（详见 YAML 对应条目）。

| 场景 | 必需输入 |
| --- | --- |
| 看图/图表工作台（#193/#208） | stock_daily✓ adj_factor✓ etf_daily✓ etf_nav⚠ fund_adj✓ index_daily✓ global_index_daily✓ stock_limit✓ calendar✓ stock_basic✓ etf_basic✓ index_basic✓ etf_reference⚠（catalog 登记缺） limit_list⚠ moneyflow✓ top_list⚠ |
| Price Action／威科夫研究 | stock_daily✓ adj_factor✓ stock_status⚠ namechange✓ st_history✓ calendar✓ |
| 行业/指数轮动 | industry_classification⚠ industry_mapping✓ index_weight✓ index_daily✓ stock_daily✓ valuation_metrics✓ |
| 资金面（#621 P3） | moneyflow✓ margin_trading✗ hk_hold✗ hsgt_top10⚠ fund_share⚠ top_list⚠ top_inst⚠ cyq_perf⚠ index_valuation⚠ pledge_ratio⚠ |
| 回测（严格 PIT，#621 P2/P4） | calendar✓ stock_daily✓ adj_factor✓ stock_status⚠ stock_limit✓ balance_sheet✓ income_statement✓ cash_flow✓ fina_indicator✓ dividend✓ corporate_actions⚠ valuation_metrics✓ index_daily✓ |
| 宏观/市场背景（P5a） | macro_indicators⚠ fx_daily✗ commodity_daily⚠ global_index_daily✓ futures_daily⚠ futures_basic✓ |

## 已并入的既有裁决（不重开）

- BSE 244 标的不覆盖（#575，2026-10-19 关票：国证2000/中证2000 自 2023 含 .BJ 成员，全宇宙 fail-closed）。
- `rights`/`csrc` 代理与权限限制维持 #517-#523 降级裁决。
- adj_factor 黄金集作用域（#620）；global_index 拼接旧故障不重立（#619）。
- fina 存量 33,851 组跨年错位遗留与 init_schema 漂移守卫行为（#613 线留档）。

## 刷新方法

复测按 YAML `meta.measurement_method` 重做：`ops status --json`（带 `DITTO_STATE_ROOT`）+ Parquet 逐目录扫描 + SQLite 只读 URI 表级统计 + 每接口一次最小探针；产出回填 YAML 后由守卫测试 `apps/backend/tests/unit/data/test_coverage_contract_unit.py` 校验结构与注册表一致性。刷新属有界实施动作，随 P1/P5 票走，不在本合同内自动进行。
