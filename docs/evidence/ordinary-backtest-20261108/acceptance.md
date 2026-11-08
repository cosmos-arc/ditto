# #723 普通股票／ETF 回测验收

本记录覆盖受限历史研究入口。候选代码为 `de7dc51c9a6ba9ec266cf716721d37a5b66b203c`，
比较基线为 #724 合并后的 `087870dd37abe50b70f82442da566242028b1e75`。
运行、下载文件与身份核对见 [workbench-acceptance.json](workbench-acceptance.json)。
这是本地隔离验收，后续只有证据和交付记录变更时，候选运行代码仍以上述 SHA 为准。

## 范围与准备

- 用户先确认独立五只主板股票池，再计算收益；冻结文件为
  [stock-pool-selection.json](stock-pool-selection.json)，ETF 继续使用既有
  [etf-pool-selection.json](etf-pool-selection.json)。原 `csi_a_share` 保留。
- 数据来自现有本地数据的隔离副本，数据库采用一致性备份，文件采用副本；未向生产数据写入本次运行。
  API `18172`、Web `15172` 与 state/cache/log 均隔离。API 与 Web 的完整 Git SHA、产品版本、
  OpenAPI 版本和摘要逐项一致；没有以开发兼容警告代替身份核对。
- 通过 `ditto_apps.scripts.materialize_research_universe --selection ... --apply`
  初始化独立股票池。首次缺 5 条、重复执行缺 0 条；使用既有 universe 写入口。
  以已发布 `seed_stock_selection_rotation@1` 复制独立策略，只替换 ID、名称和 universe，
  经现有 CreateStrategy／PublishStrategy handlers 发布为 `ordinary_stock_acceptance@1`。
  两个 ETF 消费者保留现有已发布 v1。
- 三条路径均从工作台“新建回测”提交，日期 `2026-10-08` 至 `2026-11-06`，初始资金 100 万，
  显式勾选实验数据。页面展示完成状态后，从页面按钮下载 JSON、净值 CSV 和 PNG。
  此入口在隔离 API 的后台线程调用既有 flow；本记录不冒称验证了部署中的 Prefect worker。

## 可检查的结果

| 路径 | 运行 | 成交笔数 | 页面下载 |
|---|---|---:|---|
| 独立主板股票池 | `232c7212` | 36 | [JSON](exports/ordinary_stock_acceptance.json) · [CSV](exports/ordinary_stock_acceptance.csv) · [PNG](exports/ordinary_stock_acceptance.png) |
| ETF 行业轮动 | `9a9ff529` | 59 | [JSON](exports/seed_etf_industry_rotation.json) · [CSV](exports/seed_etf_industry_rotation.csv) · [PNG](exports/seed_etf_industry_rotation.png) |
| ETF 趋势波段 | `998c7780` | 37 | [JSON](exports/seed_etf_trend_swing.json) · [CSV](exports/seed_etf_trend_swing.csv) · [PNG](exports/seed_etf_trend_swing.png) |


每条运行要求 22 个交易日、非空成交、22 个净值／基准点；JSON 中初始资金为 100 万，
净收益等于最终 NAV 相对初始资金的变化（费用已计入，不重复扣费）。
实际输入身份含五个交易标的和沪深 300 `3000162`；交易池本身仍只有五个成员。
预热证据从 `2026-07-08` 开始，基准证据为运行的 22 天，实际消费的历史复权因子和基准
由同次读取携带。报告读取使用运行时冻结的基准列。

导出文件保留受限历史研究、选择／存活者偏差、严格历史未认证及无自动晋级／信号／Paper
授权的说明。JSON 保留完整池、成员、来源、参数和时间守卫身份；CSV／PNG 携带对应运行及限制。

规则和费用依据见 [rules.md](rules.md)。[110 行 ETF 限价核对](etf-limits-verification.json)
比较真实日线前收盘与 Tushare `etf_limit` 的上下限，全部一致。该接口有 5 行 `pre_close` 为空，
计算输入使用实际 `etf_daily.pre_close`，没有以空值补零。

## 代码检查与审查

首轮完整测试发现 12 项失败，已集中修复：旧默认成本和缺数据容错预期、测试历史输入、
成交价按 tick 取整后的快照、应用层类型化错误。两路首审固定 `087870dd…b9e34131`；
`b9e34131…aa6515c3` 修复规则归属和输入身份；随后确认证据补读存在竞态，
`aa6515c3…de7dc51c` 将证据移至实际复权读取，原问题全部闭合。

回归覆盖缺成员／预热／基准、错数据集、未知规则、停牌／退出、T+1、费用、tick／限价、
首日资金和费用、未来哨兵、历史缺来源、仅改基准／预热即回放不匹配、股票／ETF 因子单读，
以及严格研究资格隔离。机器门禁的最终状态以 PR 对应提交检查为准。

本地 `task type-all` 的生产代码及测试代码检查均为 0 错误。
最终实现的 `task test -- --no-cov` 为 17,556 通过、71 跳过、1 项旧合成夹具失败；
随后只为恢复回放夹具补齐必需的合成复权来源，单独复跑该完整恢复／回放用例通过。
此前 182 项针对性检查通过；同次复权读取更新后的 provider 检查 27 项通过。
这些记录不把明确跳过的真实数据／外部系统检查计作通过；本批真实输入另由上表页面运行验证。


## 后续边界

原全市场池的旧证券身份、退出估值和未支持板块仍需独立补齐；当前入口明确拒绝未知规则或缺输入。
本批未合并、未进行 #707 最终部署。#722 的本批开发阻断由此实现与验收证据处理，关闭仍依赖合并。
#710 仍需部署后的当前交易日锚点；#711 实际 22:30／次日 09:15 观察保持 **0/5**。
