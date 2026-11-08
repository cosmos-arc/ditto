# 普通回测样本池初始化与验收阻断

本批落实 [#707](https://github.com/cosmos-arc/ditto/issues/707) 的版本化 worker 日志默认值和
[#722](https://github.com/cosmos-arc/ditto/issues/722) 的冻结 ETF 池、普通创建入口及结果限制传播。
**这不是双资产回测验收或最终部署记录。** 实际执行链发现的资产规则、成员完整性、基准和来源问题
已登记 [#723](https://github.com/cosmos-arc/ditto/issues/723)，继续阻断 #722、#707 最终部署和后续 #710／#711。

## 固定目标与实际写入

- 起始代码：`cfc87820b25cd53835ecd67bec627edb1b9b8fe5`。
- 选择文件：[etf-pool-selection.json](etf-pool-selection.json)，选择和来源观察时点均为
  `2026-11-08T05:01:37.058051+00:00`，先冻结，再读取回测输入；未计算收益后挑选成员。
- 文件 SHA-256：`fd62b15402fbc1e199fb467353c59a73a9154ff103ebe725bb0b2afa12ab32a1`。
- 目标为主 checkout 的现有 `data/metadata/metadata.sqlite`，仅新增 `csi_etf_broad` 定义和 5 条成员区间。
  来源为本地 `instrument_registry` 的真实注册信息，选定五类境内股票宽基 ETF；不代表官方中证成分。
- 初始化经 `ditto_apps.scripts.materialize_etf_universe`（#723 后更名为 `materialize_research_universe`） 调用现有 universe 域写入口。
  首次 apply 缺 5 条，重复 apply 缺 0 条；正式观察时点 `2026-11-08T05:08:14.759625+00:00`。
  其他 universe 定义与写前一致，操作未触及账户、订单或账本。写入时可用空间 33.05 GiB。
- 规范化选择内容的来源身份：
  `instrument_registry:sha256:eb07f70577af15d3f12ab2157ec7d62dc5053b7d1e3d4679f00e8a80eb3b6d81`。
  此 hash 标识本次选择内容，不冒充数据商快照或历史 knowledge date。

成员区间采用注册表的实际上市／退出日期，池的选择时间另外保留。
当前固定样本存在选择与存活者偏差；严格历史可得性未认证，且不自动授予策略晋级、信号或 Paper 权限。
池身份、选定理由、区间、来源和限制写入运行的 `strategy_promotion.sample_pool` 与既有 `usage_context.limitations`。
`usage_context.sample_pool=recorded_input_union` 保留既有语义，页面和 CSV／PNG 仍能展示实际运行输入集合。

## 输入预检与剩余阻断

真实应用 builder 已验证两个 published v1 消费者
`seed_etf_industry_rotation` 和 `seed_etf_trend_swing` 均解析出相同 5 只 ETF。
候选区间为 2026-10-08—2026-11-06：旋转策略每只读取 24 条前置行情，趋势策略每只读取 32 条；
对应表达式最大 lookback 分别为 21 与 27。此项只证明读取，未授予预热或执行合格结论。

只读核对存储可得五只 ETF 的 110 条窗口行情、110 条复权因子，以及沪深300基准的 22 条行情。
但是实际应用切片的基准为空、涨跌停为空，ETF 来源被标为 `stock_daily`。普通运行还没有
接入资产规则及 T+1 结算，使用的默认费用／滑点也未绑定策略声明。这些必须在 #723 修复。

股票侧起始池有 5,574 个成员，窗口行情仅覆盖 5,570 个。完全缺失的四个 ID 为
`1005574`、`1005577`、`1005578`、`1005573`；须核实旧证券身份／更名／生命周期。
不得删掉缺行情成员凑通过。#723 保留精确查询、状态与退出缺口以及反例验收范围。

## 本批验证边界

- worker 测试通过真实临时 Prefect server、flow 和子进程验证默认 INFO／ERROR 保留、DEBUG 抑制，显式 DEBUG 仍有效。
- 初始化集成测试覆盖真实 SQLite 域写入、默认只读、重复执行、上市／退出区间、无关历史保留及冲突拒绝。
- serializer 和 builder 测试覆盖池身份传播与既有输入语义；Web 测试覆盖策略选择、日期、资金、实验数据默认关闭及提交跳转。
- 首审发现的跨 feature 取数已移到 `workflows/backtest-catalog`；样本语义标记恢复兼容，类型错误已修复。
- 完整门禁与当前提交的结果以 PR 检查和提交关联记录为准；本文件不替代 CI 证据。

尚未执行本轮真实股票／ETF工作台 create → execute → view → JSON／CSV／PNG 验收。
尚未切换 API、Web、worker 或 Prefect deployments；共享 Prefect Server 保持原状。
#710 仍需最终部署身份及当前交易日锚点。#711 为 **0/5**，未来实际 22:30／次日 09:15
留档不能由测试或事后查询替代。
