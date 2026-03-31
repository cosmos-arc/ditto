# Ditto 统一术语表

> **版本**: v2.4
> **日期**: 2026-03-31
> **上游**: 全部 spec 文档 (00-15)
> **下游**: UI 设计、AICoding、前端实现、内容审核

---

## 1. 文档目标

Ditto 覆盖首页指挥台、市场观察、因子研究、策略构建、交易执行、风控、AI Agent 和平台运维八大产品域。文档数量已达 16 份，涉及数百个专业术语。

在跨文档审查中发现 10+ 处中英文术语不一致的问题——同一概念在不同 spec 中被不同称呼，导致设计评审、AI coding 和前端实现时产生歧义。

本术语表的目标：

1. **统一称呼** — 每个概念在 Ditto 内只有一组标准中英文名称
2. **消除歧义** — 明确标注"不用"的旧称或误称
3. **跨文档对齐** — 后续所有 spec 文档修改、UI 文案、代码命名均以本表为准

### 使用规则

- 新文档或修改文档时，必须使用本表的标准术语
- 若发现本表未收录的术语，应先补充本表再使用
- 代码中的变量名、CSS token 名、路由路径以英文为准
- UI 面向用户的文案以中文为准

---

## 2. 市场结构

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Market | 市场 | 泛指金融市场或某一具体市场，如 A 股市场、港股市场 | 01 |
| Regime | 市场状态 | 三种状态：Risk-On（风险偏好）/ Risk-Off（风险规避）/ Mixed（混合） | 01 |
| Risk-On | 风险偏好 | 市场状态之一，表示风险资产受追捧 | 10 |
| Risk-Off | 风险规避 | 市场状态之一，表示避险情绪占主导 | 10 |
| Mixed | 混合 | 市场状态之一，表示无明显方向 | 10 |
| Breadth | 涨跌比 | 上涨家数与下跌家数之比，反映市场参与广度。**不用"广度""偏强"** | 02 |
| Flow | 资金流向 | 资金进出方向与规模 | 02 |
| Trading Session | 交易时段 | 如 A 股早盘、午盘、美盘等。**不用"Session"单独出现** | 10 |
| Cross-Market | 跨市场 | 跨越多个市场（A 股/港股/美股等）的比较与扫描 | 01 |
| Cross-Market Overview | 全市场总览 | `/markets` 页面的正式名称。**不用"Markets Overview"** | 01 |
| Northbound Flow | 北向资金 | 沪港通/深港通北向资金流。**统一为"北向资金"，不用"北向流入""北向净流入"** | 02 |
| Movers | 领涨领跌 | 涨跌幅排名靠前的标的列表。**不用"Main Theme Activity""涨跌幅排名"** | 02 |
| Macro Drivers | 宏观驱动 | 如 DXY、US10Y、VIX、Gold 等跨市场宏观变量 | 13 |
| Volatility (Vol) | 波动率 | 市场价格波动的剧烈程度 | 02 |
| Sector | 板块 | 行业板块 | 02 |
| Theme | 主线 / 主题 | 市场主线或投资主题 | 02 |
| Instrument | 标的 | 泛指股票、ETF、债券等可交易品种 | 01 |
| Asset Class | 资产类别 | 如股票、债券、商品、外汇、利率 | 01 |
| Index | 指数 | 如沪深 300、中证 500 | 02 |
| ETF | ETF | 交易型开放式指数基金，不翻译 | 02 |
| A-Share | A 股 | 中国 A 股市场 | 01 |
| Market Cap | 市值 | 上市公司总市值 | 02 |
| Turnover | 换手率（市场） | 市场或个股的成交活跃度，成交量与流通股本之比 | 02 |
| Volume | 成交量 | 一定时间内的成交数量 | 02 |
| Total Turnover Value | 两市成交额 | A 股沪深两市当日总成交金额。**不用"Turnover Rate"（与换手率 Turnover 混淆）** | 13 |
| Limit Up / Limit Down | 涨停 / 跌停 | A 股特有，当日价格波动达到上限或下限 | -- |
| Price Limit | 涨跌停板 | 当日价格允许波动的最大幅度限制（A 股主板 ±10%，ST ±5%，创业板/科创板 ±20%） | -- |
| Limit Up / Down Count | 涨跌停家数 | 当日达到涨停或跌停的标的数量 | -- |
| Advance / Decline | 涨跌家数 | 当日上涨与下跌的标的数量 | 02 |
| DXY | 美元指数 | US Dollar Index，衡量美元兑一篮子货币的汇率变化 | 13 |
| US10Y | 美国十年期国债 | 美国十年期国债收益率，全球资产定价锚 | 13 |
| VIX | 恐慌指数 | CBOE 波动率指数，衡量市场对未来波动性的预期 | 13 |

---

## 3. 因子研究

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Factor | 因子 | 量化研究中的预测变量或特征变量 | 01 |
| Factor Analysis | 因子分析 | 围绕单因子做多维诊断 | 01 |
| Factor Family | 因子族 | 同类因子的分组，如价值因子族、动量因子族 | 12 |
| Factor Monitor | 因子监控 | 研究工作台上对因子健康度的实时监控表 | 12 |
| Factor Exposure | 因子暴露 | 组合在某因子上的敞口大小 | 03 |
| Factor Return | 因子收益 | 因子多空组合的收益率 | 03 |
| IC (Information Coefficient) | 信息系数 | 因子预测能力的统计指标，因子值与未来收益的截面相关系数 | 12 |
| Rank IC | 排名信息系数 | 因子排名与未来收益排名的 Spearman 相关系数 | 12 |
| IR (Information Ratio) | 信息比率 | 单位跟踪误差的超额收益，衡量因子选股效率 | 12 |
| Decay | 衰减 | 因子信号随时间的衰减特性 | 12 |
| Decay Curve | 衰减曲线 | 因子信号随持有期衰减的曲线 | 12 |
| IC Trend | IC 趋势 | 信息系数随时间的变化曲线 | 12 |
| Coverage | 覆盖率 | 因子有效覆盖的标的数量占比 | 12 |
| Cross-Section | 截面 | 某一时点上所有标的的因子值 | 12 |
| Time-Series | 时序 | 某一标的或因子随时间的变化 | 12 |
| Distribution | 分布 | 因子值的统计分布 | 12 |
| Correlation | 相关性 | 因子或资产之间的统计相关性 | 12 |
| Alpha | 超额收益 | 超越基准的收益部分 | 12 |
| Beta | 贝塔 | 对市场系统性风险的暴露度 | 12 |
| Diagnostics | 诊断 | 对因子表现的多维健康检查 | 03 |
| Review Queue | 复审队列 | 等待人工审核的因子或信号列表 | 03 |
| Research Workspace | 研究工作区 | `/research` 页面的正式名称 | 01 |
| Regime Model | 市场状态模型 | 市场状态识别与切换的量化模型 | 01 |
| Factor Orthogonalization | 因子正交化 | 通过 Gram-Schmidt 或回归残差法消除因子间的线性相关性 | -- |
| Factor Combination | 因子合成 | 将多个因子按权重合并为综合得分的方法（等权/IC 加权/优化器） | -- |
| Factor Preprocessing | 因子预处理 | 因子使用前的标准化/去极值/中性化等工程化步骤 | -- |
| Factor Standardization | 因子标准化 | 将因子值转换为 Z-Score 或排序百分位，消除量纲差异 | -- |
| Factor Neutralization | 因子中性化 | 消除因子对行业/市值等风格因子的暴露（行业中性/市值中性） | -- |
| Turnover Penalty | 换手惩罚 | 在组合优化中对高换手率施加的成本惩罚 | -- |

---

## 4. 策略与回测

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Strategy | 策略 | 交易策略，由因子、规则、风控等组成 | 01 |
| Strategy Studio | 策略工作坊 | `/research/strategies/[id]/studio` 页面。**不用"策略构建器"** | 01 |
| Backtest | 回测 | 用历史数据验证策略表现 | 01 |
| NAV (Net Asset Value) | 净值曲线 | 策略或组合的净值变化 | 12 |
| PnL (Profit and Loss) | 盈亏 | 交易产生的利润或亏损 | 12 |
| Drawdown | 回撤 | 从净值峰值到谷值的跌幅 | 12 |
| MDD (Maximum Drawdown) | 最大回撤 | 历史最深的回撤 | 12 |
| Drawdown Recovery | 回撤恢复 | 从最大回撤恢复到前高的时间或百分比 | 03 |
| Sharpe Ratio | 夏普比率 | 风险调整后收益指标，年化超额收益 / 年化波动率 | 12 |
| Sortino Ratio | 索提诺比率 | 仅考虑下行波动的风险调整收益指标 | -- |
| Calmar Ratio | 卡玛比率 | 年化收益 / 最大回撤，衡量回撤效率 | -- |
| Annual Return | 年化收益 | 策略或组合的年度化收益率 | 12 |
| Win Rate | 胜率 | 盈利交易占总交易的比例 | 12 |
| Profit / Loss Ratio | 盈亏比 | 平均盈利交易收益 / 平均亏损交易收益 | -- |
| Skewness | 偏度 | 收益分布的不对称性，正偏度表示右尾更长 | -- |
| Kurtosis | 峰度 | 收益分布的尾部厚度，高峰度表示肥尾 | -- |
| Benchmark | 基准 | 对比用的参考指数 | 12 |
| Attribution | 归因 | 收益来源分解 | 12 |
| Experiment | 实验 | A/B 对比或参数扫描式的策略研究 | 01 |
| Slippage (Backtest) | 回测滑点 | 回测中模拟的成交价偏差 | 12 |
| Transaction Cost | 交易成本 | 回测中模拟的手续费、印花税等 | -- |
| Rebalance | 再平衡 | 按策略规则定期调整持仓 | -- |
| Holding Period | 持有期 | 策略持仓的平均时间长度 | 12 |
| Form Mode | 表单构建 | Strategy Studio 中以表单方式构建策略的模式 | 01 |
| Code Mode | 代码编辑 | Strategy Studio 中以代码方式编辑策略的模式 | 01 |

---

## 5. 交易执行

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Signal | 信号 | 交易策略产生的可执行建议 | 01 |
| Signal Queue | 信号队列 | 等待复核的信号列表 | 11 |
| Signal Review | 信号复核 | 对信号进行人工审核确认 | 11 |
| Order | 订单 | 提交给券商的交易委托 | 11 |
| Trade | 成交 | 已完成的交易 | 11 |
| Fill | 成交明细 | 单笔成交的具体价格与数量 | 11 |
| Position | 持仓 | 当前持有的标的与数量 | 11 |
| Side | 方向 | Buy（买入）/ Sell（卖出） | 11 |
| Buy | 买入 | 买入方向 | 11 |
| Sell | 卖出 | 卖出方向 | 11 |
| Route | 路由 | 券商通道，决定订单发送到哪个交易所或券商 | 10 |
| Execution | 执行 | 订单从提交到成交的全过程 | 11 |
| Ledger | 账本 | 交易流水的正式记录 | 11 |
| Execution Console | 执行控制台 | Ledger / Execution Console 的简称 | 11 |
| Session Strip | 交易时段条 | Trading Overview 上方的资金/保证金/风险预算/路由健康摘要 | 13 |
| Order Trace | 订单追踪 | 订单从提交到成交的完整状态时间线 | 13 |
| Reject / Rejection | 拒单 | 券商拒绝执行的订单 | 11 |
| Cancel | 撤单 | 用户主动撤销未成交的订单 | 11 |
| Partial Fill | 部分成交 | 订单只成交了部分数量 | 11 |
| Dry Run | 模拟运行 | 不实际下单的策略模拟执行 | -- |
| Broker | 券商 | 提供交易通道的金融机构 | 01 |
| Account | 账户 | 交易账户 | 01 |
| Book | 账本 | 交易账本，用于区分策略或资金的交易分组 | 10 |
| Slippage (Trading) | 滑点 | 预期价格与实际成交价格的差异 | 12 |
| Fees | 手续费 | 交易产生的佣金和费用 | 11 |
| Stamp Duty | 印花税 | A 股卖出时征收的交易税费 | -- |
| Commission | 佣金 | 券商收取的交易手续费 | -- |
| Margin | 保证金 | 融资融券交易中需要的担保资金 | -- |
| T+1 | T+1 交收 | A 股交易制度，当日买入的证券下一交易日方可卖出 | -- |
| Trading Signals Inbox | 信号收件箱 | `/trading/signals` 页面。**不用"信号中心"** | 01 |
| Review Mode | 盘后复盘模式 | Trading Overview 15:00 后自动切换的回顾模式（日归因/健康检查/明日预览） | 02 |

---

## 6. 风控

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| VaR (Value at Risk) | 风险价值 | 给定置信水平下的最大可能损失 | 11 |
| Exposure | 敞口 | 对某风险因子的暴露程度 | 12 |
| Gross Exposure | 总敞口 | 多头与空头敞口的绝对值之和 | 12 |
| Net Exposure | 净敞口 | 多头减空头的敞口 | 12 |
| Beta (Risk) | 贝塔敞口 | 组合对市场系统性风险的暴露度 | 12 |
| Breach | 突破 | 风控阈值被突破的事件 | 11 |
| Active Breaches | 活跃突破 | 当前正在发生的风控阈值突破 | 11 |
| Stress Test | 压力测试 | 极端场景下的组合风险模拟 | 11 |
| Near-limit | 接近限制 | 风险指标接近但未突破阈值 | 11 |
| Risk Center | 风险中心 | `/trading/risk` 页面的正式名称 | 01 |
| Risk Strip | 风险条 | Risk Center 上方的风险摘要指标行 | 13 |
| Risk Budget | 风险预算 | 分配给策略或组合的风险限额 | 11 |
| Risk Rule | 风控规则 | 定义风控阈值与触发条件的规则 | 11 |
| Incident Timeline | 事件时间线 | 风控事件的处理记录时间线 | 13 |
| Handling Log | 处置日志 | 对风控事件的处置操作记录 | 11 |
| Concentration Risk | 集中度风险 | 持仓过度集中于单一行业或风格的 risk | -- |
| Liquidity Risk | 流动性风险 | 持仓在市场波动时无法以合理价格成交的风险 | -- |
| Style Exposure | 风格暴露 | 组合对大小盘、价值成长等风格因子的敞口 | -- |
| Sector Concentration | 行业集中度 | 持仓在行业维度的分布集中程度 | -- |
| Drawdown Recovery Days | 回撤恢复天数 | 从最大回撤谷值恢复到前高所需的交易日数 | -- |
| Worst Day | 最大单日损失 | 策略或组合历史中单日最大亏损幅度 | -- |

---

## 7. A 股特有术语

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| A-Share | A 股 | 中国内地证券交易所上市的股票 | 01 |
| Northbound Flow | 北向资金 | 通过沪港通/深港通从香港流入 A 股的资金 | 02 |
| Southbound Flow | 南向资金 | 通过港股通从内地流入港股的资金 | 01 |
| Margin Trading | 融资融券（两融） | 向券商借入资金买入证券（融资）或借入证券卖出（融券） | -- |
| Margin Balance | 融资余额 | 投资者融资买入但未偿还的金额总和 | 13 |
| Short Selling Balance | 融券余额 | 投资者融券卖出但未归还的证券市值总和 | -- |
| ST (Special Treatment) | ST 标的 | 因财务异常被特别处理的股票，涨跌停限制 ±5% | -- |
| *ST | *ST 标的 | 退市风险警示股票，涨跌停限制 ±5% | -- |
| Price Limit | 涨跌停板 | A 股主板 ±10%、ST ±5%、创业板/科创板 ±20% | -- |
| Limit Up | 涨停 | 当日涨幅达到上限 | -- |
| Limit Down | 跌停 | 当日跌幅达到下限 | -- |
| T+1 | T+1 交收 | 当日买入的证券下一交易日方可卖出 | -- |
| Call Auction | 集合竞价 | 开盘前通过集中撮合确定开盘价的交易方式 | -- |
| Continuous Auction | 连续竞价 | 集合竞价后逐笔撮合的连续交易方式 | -- |
| ChiNext Board | 创业板 | 深交所面向成长型创新企业的板块，涨跌停 ±20% | 02 |
| STAR Market | 科创板 | 上交所面向科技创新企业的板块，涨跌停 ±20% | -- |
| Registration-based IPO | 注册制 | A 股新股发行的注册制审核制度 | -- |
| Dragon-Tiger List | 龙虎榜 | 公布当日涨跌幅/换手率异常的个股买卖席位信息 | -- |
| Block Trade | 大宗交易 | 达到一定数量和金额的证券大宗买卖 | -- |
| SSE Composite | 上证指数 | 上海证券交易所综合股价指数 | 02 |
| CSI 300 | 沪深 300 | 沪深两市规模最大的 300 只股票的指数 | 02 |
| CSI 500 | 中证 500 | 排除沪深 300 后的中型股票指数 | 02 |
| CSI 1000 | 中证 1000 | 排除沪深 300 和中证 500 后的小型股票指数 | -- |
| ChiNext Index | 创业板指 | 创业板市场的核心指数 | 02 |
| Main Board | 主板 | 沪深交易所的主板市场 | -- |
| Trading Suspension | 停牌 | 证券暂停交易 | -- |
| Trading Halt | 临时停牌 | 证券在交易时段内临时暂停交易 | -- |
| Stock Connect | 沪深港通 | 连接内地与香港股票市场的互联互通机制 | -- |
| SSE / SZSE | 上交所 / 深交所 | 上海证券交易所 / 深圳证券交易所 | -- |
| Tick Size | 最小升降单位 | A 股主板最小价格变动 0.01 元，科创板最小申报 200 股 | -- |
| Pre-market Auction | 盘前集合竞价 | 9:15-9:25 开盘前集中撮合时段。9:15-9:20 可撤单，9:20-9:25 不可撤单 | -- |
| Post-market Call Auction | 盘后集合竞价 | 创业板/科创板 15:05-15:30 的盘后固定价格交易时段 | -- |
| Continuous Auction | 连续竞价 | 9:30-11:30、13:00-15:00 的逐笔撮合连续交易时段 | -- |
| Trading Phase | 交易阶段 | A 股一个交易日内经历的时段：盘前集合竞价/连续竞价/午休/收盘集合竞价/盘后交易 | -- |
| Stamp Duty Rate | 印花税率 | A 股卖出时征收 0.05% 的交易税费，买入免征 | -- |
| Commission Rate | 佣金费率 | 券商收取的交易手续费，通常万 2.5（0.025%），双向收取 | -- |
| Trading Unit | 交易单位 | A 股最小买入单位为 100 股（1 手），卖出可零股 | -- |
| Corporate Actions | 公司行动 | 影响股东权益的公司事件（分红、送股、转增、配股、限售解禁等） | 02 |
| Lockup Expiry | 限售解禁 | 限售股解禁止流通，释放市场供给压力 | 02 |
| Ex-Dividend Date | 除权除息日 | 股票不再含分红/送股权利的日期，当日股价需复权处理 | 02 |

---

## 8. 系统与数据

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Pipeline | 管道 | 数据处理流水线 | 01 |
| Data Quality | 数据质量 | 数据的完整性、准确性和及时性 | 01 |
| Data Provider | 数据源 | 外部数据供应商 | 01 |
| MiniQMT | 迷你 QMT | QMT 客户端的轻量模式，通过 xtquant Python SDK 提供实时行情与实盘交易能力 | 18 |
| xtquant | xtquant SDK | MiniQMT 的 Python 接口库，支持行情订阅、下单撤单、持仓查询 | 18 |
| Cross-Validation | 交叉校验 | 同一标的不同数据源（tushare vs 通达信）的数值对比，发现数据异常 | 18 |
| Freshness | 数据新鲜度 | 数据最后更新的时效性 | 12 |
| Stale | 过时数据 | 数据已超过预期更新时间 | 12 |
| Data Delay | 数据延迟 | 数据更新滞后的程度 | 12 |
| Completeness | 完整性 | 数据覆盖的完整程度 | 12 |
| Accuracy | 准确性 | 数据值的精确程度 | 12 |
| Jobs | 任务 | 系统后台运行的异步任务 | 10 |
| Incident | 事件 | 系统异常或故障事件 | 10 |
| Logs | 日志 | 系统操作与事件记录 | 10 |
| Resources / Quotas | 资源/配额 | 系统计算资源与使用限额 | 10 |
| Audit Trail | 审计轨迹 | 操作变更的完整记录链 | 10 |
| Dependency | 依赖 | 系统组件之间的上下游关系 | 10 |
| Config Diff | 配置差异 | 配置变更前后的对比 | 10 |
| Settings | 设置 | 系统级别的全局配置 | 01 |
| Environment | 环境 | 如生产环境、测试环境 | 10 |
| Health Strip | 健康条 | Platform 页面上方的系统状态摘要行 | 13 |
| Platform Ops Console | 平台运维控制台 | `/platform` 页面。**不用"Ops Console"** | 01 |
| Sync | 同步 | 数据更新到最新状态的操作 | 10 |
| Retry | 重试 | 失败任务的重新执行 | 10 |
| Resolve | 解决 | 标记问题已处理 | 10 |
| Assign | 认领 | 将任务分配给特定处理人 | 10 |
| Payload | 原始数据 | 系统传输的原始数据内容 | 10 |
| Broker Health | 券商健康 | 券商通道连接状态与可用性 | 10 |
| Route Health | 路由健康 | 交易路由通道的连接状态与延迟 | 11 |

---

## 9. AI / Agent

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Copilot | 智能助手 | AI 分析与生成的统一工作台 | 01 |
| Agent | 代理 | 自主执行任务的 AI 代理 | 01 |
| Plan | 计划 | Agent 的执行计划 | 01 |
| Run | 运行 | Plan 或任务的一次执行 | 01 |
| Finding | 发现 | Agent 运行产出的洞察或结论 | 01 |
| Approval | 审批 | 人工对 Agent 操作的确认 | 13 |
| Tool Invocation | 工具调用 | Agent 调用外部工具的操作 | 13 |
| Tool Trace | 工具追踪 | Agent 工具调用的详细执行记录 | 13 |
| Agent Console | Agent 控制台 | `/ai/agent` 页面的正式名称 | 01 |
| AI Copilot Studio | AI 智能助手工作坊 | `/ai/copilot` 页面的正式名称 | 01 |
| Session | 会话 | Copilot 的一次对话会话 | 01 |
| Structured Output | 结构化输出 | Copilot 产出的非自由文本结果 | 01 |
| Context | 上下文 | AI 工作时参考的关联对象与信息 | 01 |
| Evidence | 证据 | AI 结论的支撑数据或来源 | 01 |
| Prompt | 提示词 | 发送给 AI 的输入指令 | 01 |
| Market Analysis Mode | 市场分析模式 | Copilot 的工作模式之一 | 01 |
| Stock Discovery Mode | 选股辅助模式 | Copilot 的工作模式之一 | 01 |
| Strategy Draft Mode | 策略草案模式 | Copilot 的工作模式之一 | 01 |
| AI Notes | AI 笔记 | AI 产出的分析笔记 | 13 |
| Conversation Block | 会话块 | AI 分析会话的结构化内容单元，非聊天气泡 | 13 |
| Suggestion Block | 建议块 | AI 给出的可点选采纳的建议 | 13 |
| Research Note Block | 研究笔记块 | AI 或用户沉淀的研究结论、假设、TODO | 13 |
| Agent Task Block | 代理任务块 | Agent 当前正在执行的任务状态展示 | 13 |
| Agent Run Timeline | 代理运行时间线 | Agent 多步执行链路的可视化时间线 | 13 |
| Approval Request Block | 审批请求块 | Agent 执行前发起的人工审批请求 | 13 |
| Output Artifact Block | 产出结果块 | Agent 产出的结构化结果（报告、数据集等） | 13 |
| Factor Discovery Mode | 因子发现模式 | Copilot 的工作模式之一，LLM 从新闻/报告/龙虎榜挖掘因子假设 | 02 |
| Multi-Agent Pipeline | 多 Agent 管道 | 多个 Agent 串行协作完成复杂研究任务的流水线 | 02 |
| AI Confidence | AI 置信度 | AI 结论的可靠程度分级（🟢 高 80-100 / 🟡 中 50-79 / 🔴 低 0-49） | 02 |
| Evidence Chain | 证据链 | AI 置信度背后的推理依据与数据源追踪链 | 02 |

---

## 10. 页面与组件标签

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Shell | 壳层 | 页面的外层结构框架 | 10 |
| Rail | 侧栏 | 全局导航的最窄侧栏，宽度 56px | 10 |
| Header | 标题区 | 页面顶部的标题与控制区，按 Shell 角色分为多种 | 13 |
| Strip | 状态条 | 水平排列的轻量信息行 | 13 |
| Band | 区域带 | 页面中一个水平区块（如 Analysis Band、Tab Band） | 10 |
| Panel | 面板 | 页面内的一个工作区域 | 13 |
| Badge | 标签 | 状态或分类的标记，分为 Status / Severity / Code 三类 | 13 |
| Chip | 筛选标签 | 筛选条件的交互标签，如 Filter Chip、Scope Chip | 13 |
| Toolbar | 工具栏 | 工作区级动作和视图切换条 | 13 |
| Inspector | 检查器 | Studio 右侧的配置/预览/输出面板 | 13 |
| Drawer | 抽屉 | 从侧边或底部滑出的临时面板 | 13 |
| Side Sheet | 侧面板 | 持续存在的上下文详情面板 | 13 |
| Activity Stack | 活动栈 | Analytical Workspace 右侧的连续辅助栏 | 12 |
| Command Palette | 命令面板 | 全局快捷命令入口 | 13 |
| Context Bar | 上下文条 | Radar 变体中展示客观环境变量的水平条 | 13 |
| Scope Strip | 范围条 | Radar 变体中展示解读摘要的水平条 | 13 |
| Context Pill | 上下文药丸 | Context Bar 内的单个客观变量展示单元 | 13 |
| Scope Chip | 范围标签 | Scope Strip 内的单个解读摘要单元 | 13 |
| Market Card | 市场卡片 | Cross-Market Overview 中展示单个市场的卡片 | 13 |
| Cross-Market Matrix | 跨市场矩阵 | 全市场总览中的热力矩阵比较表 | 13 |
| Macro Driver Block | 宏观驱动块 | 单个跨市场驱动变量的微型状态块 | 13 |
| Analysis Band | 分析带 | Analytical Workspace 底部的分析图表区 | 10 |
| Tab Band | 标签带 | Radar 变体底部的标签切换区 | 10 |
| Status Bar | 状态栏 | 页面最底部的系统状态行 | 00 |
| Meta Strip | 元信息条 | 对象页 Header 下方的一行元信息 | 13 |
| Filter Bar | 筛选栏 | 筛选条件的交互区域 | 13 |
| Saved View | 保存视图 | 用户自定义的表格列与筛选组合 | 13 |
| Compare Cart | 比较车 | Screener 中暂存待比较标的的功能 | -- |
| Compare Drawer | 比较抽屉 | 标的多维比较的展开面板 | 12 |
| Preview Panel | 预览面板 | Catalog Workspace 右侧的对象摘要面板 | 12 |
| Sparkline | 迷你趋势线 | 表格或卡片中的轻量趋势线 | 12 |
| Status Cell | 状态单元格 | 表格中表达状态的单元格组件 | 13 |
| Metric Cell | 指标单元格 | 表格中表达高价值数字的单元格组件 | 13 |
| Severity Badge | 严重度标签 | Ops Queue 中标记问题严重程度的标签 | 13 |
| Toast | 轻提示 | 短暂存在的操作反馈提示 | 13 |
| Banner | 横幅 | 页级持续可见的重要反馈 | 13 |
| Alert Item | 告警项 | 可处理事项，持续存在直到处理完成 | 13 |
| Blocker State | 阻断状态 | 不可忽视的严重问题，必须处理才能继续 | 13 |
| Universe | 标的池 | `/markets/universes` 页面，策略可交易的标的集合管理 | 01 |
| Watchlist | 观察列表 | `/markets/watchlist` 页面，用户关注的标的列表 | 01 |
| Intelligence | 情报中心 | `/markets/intelligence` 页面，多源情报聚合工作区（tab 视图） | 01 |
| Chart Lab | 图表实验室 | `/markets/chart-lab` 页面，交互式图表实验工作台 | 01 |

---

## 11. 壳层与模式

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Command Center Shell | 指挥中心壳层 | Home 页面 (`/`) 的壳层类型 | 10 |
| Analytical Workspace Shell | 分析工作区壳层 | 以分析/监控/判断为核心的壳层类型 | 10 |
| Catalog Workspace Shell | 目录工作区壳层 | 以对象集合管理与检索为核心的壳层类型 | 10 |
| Object Hub Shell | 对象中心壳层 | 围绕单一对象的综合操作壳层类型 | 10 |
| Studio Shell | 工作坊壳层 | 构建/编辑/对话/编排的创作型壳层类型 | 10 |
| Operations Console Shell | 运维控制台壳层 | 平台管理与配置的壳层类型。**不用"Ops Console Shell"** | 10 |
| Radar Variant | 雷达变体 | Analytical Shell 中以 scan/compare/drill-down 为核心的子变体 | 10 |
| Table-first | 表优先 | 主工作面以表格为主的变体 | 10 |
| Chart-first | 图优先 | 主工作面以图表为主的变体 | 10 |
| Mixed | 混合型 | 表图并存的变体 | 10 |
| Global Command Center | 全局指挥中心 | Home 的完整模式名称 | 11 |
| Analytical Overview Workspace | 分析概览工作区 | Analytical Workspace 的完整名称 | 11 |
| Catalog / Screener Workspace | 目录/筛选工作区 | Catalog 的完整名称 | 11 |
| Queue / Ops Console | 队列/运维控制台 | 处置/排查/监控/追踪的页面模式 | 11 |
| Ledger / Execution Console | 账本/执行控制台 | 订单/成交/执行状态链的页面模式 | 11 |
| Config / Integration Console | 配置/集成控制台 | 系统设置/账户/通道/集成的页面模式 | 11 |

---

## 12. 交互与状态

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Selected | 选中 | 当前选中的对象，驱动右侧与底部联动 | 04 |
| Hover | 悬停 | 鼠标悬停的轻交互状态 | 04 |
| Focus | 焦点 | 键盘焦点状态 | 04 |
| Active | 活跃 | 动作进行中 | 04 |
| Loading | 加载中 | 数据加载状态 | 04 |
| Running | 运行中 | 长任务执行状态 | 04 |
| Success | 成功 | 操作完成 | 04 |
| Partial | 部分完成 | 部分数据或部分成交 | 04 |
| Stale | 过时 | 数据已过预期更新时间 | 04 |
| Warning | 警告 | 需关注但不紧急 | 04 |
| Critical | 严重 | 影响判断/交易/系统安全 | 04 |
| Empty | 空 | 无数据状态 | 04 |
| Failed | 失败 | 操作失败 | 04 |
| Blocked | 阻断 | 无法继续操作 | 04 |
| Default | 默认 | 初始/正常状态 | 04 |
| Drill-down | 下钻 | 从汇总进入细节的交互模式 | 10 |
| Bulk Action | 批量动作 | 对多个选中对象的批量操作 | 04 |
| Command Search | 命令搜索 | 全局搜索与命令入口 | 10 |
| Today Pulse | 今日脉搏 | Home 首页的当日状态摘要区 | -- |
| Decision Banner | 决策横幅 | Home 首页的核心资产/盈亏/风险摘要横幅 | -- |
| Pending / Next Actions | 待办/下一步 | Home 首页的待处理事项区 | -- |

---

## 13. Design Token 与视觉

| 英文 | 中文 | 定义 | 首次出现 |
|------|------|------|---------|
| Design Token | 设计令牌 | 设计系统中的原子级视觉变量 | 14 |
| Foundation | 基础层 | Token 9 层架构的第 1 层：物理原语 | 14 |
| Semantic Surface | 语义表面层 | Token 9 层架构的第 2 层：界面表面语义 | 14 |
| Shell | 壳层 | Token 9 层架构的第 3 层：页面壳层布局 | 14 |
| Data Visualization | 数据可视化层 | Token 9 层架构的第 4 层：图表/热力图/sparkline | 14 |
| Component | 组件层 | Token 9 层架构的第 5 层：UI 组件结构 | 14 |
| Interaction | 交互层 | Token 9 层架构的第 6 层：交互状态 | 14 |
| Domain Semantic | 域语义层 | Token 9 层架构的第 7 层：业务域状态色 | 14 |
| Density | 密度层 | Token 9 层架构的第 8 层：密度档位切换 | 14 |
| Module Pattern | 模块模式层 | Token 9 层架构的第 9 层：模块级偏置 | 14 |
| Dense | 紧凑 | 密度三档中的最高密度（34px 行高） | 00 |
| Compact | 适中 | 密度三档中的中等密度（36px 行高，当前默认） | 00 |
| Comfortable | 宽松 | 密度三档中的最低密度（42px 行高） | 00 |
| Heatmap | 热力图 | 用色阶表达数值大小的矩阵可视化 | 14 |
| Treemap | 树图 | 用矩形面积表达权重的层级可视化 | 12 |
| Frosted Glass | 毛玻璃 | 半透明模糊背景效果 | 14 |
| Ambient Tint | 环境染色 | 卡片或行的轻微背景色调 | -- |

---

## 14. 不一致项修复记录

> 以下术语在跨文档审查中发现不一致，已在本术语表中统一。

| # | 概念 | 统一为 | 不用 | 来源 |
|---|------|-------|------|------|
| 1 | Breadth | **Breadth / 涨跌比** | 广度、偏强 | 02 核心页面蓝图、prototype |
| 2 | Movers | **Movers / 领涨领跌** | Main Theme Activity、涨跌幅排名 | 02 核心页面蓝图 |
| 3 | 北向 | **北向资金 (Northbound Flow)** | 北向流入、北向净流入、北向持仓 | 02 核心页面蓝图 |
| 4 | Operations Console | **Operations Console / 运维控制台** | Ops Console | 01 产品信息架构、10 Shell Family |
| 5 | 全市场总览 | **Cross-Market Overview / 全市场总览** | Markets Overview | 01 产品信息架构、02 核心页面蓝图 |
| 6 | 策略工作坊 | **Strategy Studio / 策略工作坊** | 策略构建器 | 01 产品信息架构 |
| 7 | 信号收件箱 | **Signals Inbox / 信号收件箱** | 信号中心 | 01 产品信息架构、02 核心页面蓝图 |
| 8 | 资金面 / 态势 | **态势** | 资金面 | 02 核心页面蓝图 Changelog (FIX-03) |
| 9 | LIVE / 实时 | **LIVE 状态指示器** | "实时"文字 | 02 核心页面蓝图 Changelog (COPY-09) |
| 10 | Trading Session | **Trading Session / 交易时段** | Session 单独出现 | 10 Shell Family |
| 11 | Turnover Rate | **Total Turnover Value / 两市成交额** | Turnover Rate（与换手率 Turnover 混淆） | 审计 FIX |
| 12 | MDD vs Current Drawdown | **MDD = 历史最大回撤，Current Drawdown = 当前回撤深度** | 混用 MDD 表达当前回撤 | 02 蓝图, 审计 FIX |
| 13 | /ai Pattern 归属 | **Global Command Center 轻量变体** | Object Hub（10 Shell）、Analytical Overview（11 Pattern 残留） | 01 IA + 10 Shell + 11 Pattern 审计对齐 |
| 14 | /trading/accounts | **已废弃** | 所有文档中的残留引用 | 11 Pattern, 10 Shell |

---

## 15. 术语添加规则

### 15.1 何时添加新术语

以下情况必须向本术语表添加新条目：

- 新增 spec 文档时引入的全新概念
- 现有 spec 修改中引入的新术语
- UI 文案中出现的新标签或新名称
- 代码中新增的 CSS token 或路由路径名

### 15.2 添加格式

每条术语必须包含四个字段：

```
| 英文 | 中文 | 定义 | 首次出现 |
```

- **英文**: 英文标准名称，首字母大写（专有名词保留原文大小写）
- **中文**: 中文标准名称
- **定义**: 该术语在 Ditto 中的使用场景和含义（一句话）
- **首次出现**: 该术语首次出现的 spec 文档编号（如 01、10、13），若为本次新增标注 `--`

### 15.3 术语冲突处理

若发现同一概念在不同文档中有不同称呼：

1. 以本术语表为准
2. 在"不一致项修复记录"中添加一条记录
3. 修改源文档中的旧称

### 15.4 命名原则

- **精简**: 术语应尽可能短，但不可短到产生歧义
- **专业**: 使用金融/量化/技术领域的标准用语
- **一致**: 同类术语命名风格应一致（如"xx 控制台"不混用"xx 台"）
- **中英对称**: 每个中文术语应有唯一对应的英文术语

---

## Changelog

### 2026-03-31 — v2.4

- 新增系统与数据术语 3 条：MiniQMT、xtquant SDK、Cross-Validation
- 术语表首次出现列新增 18 数据源规格作为来源

### 2026-03-31 — v2.3

- 新增 AI / Agent 术语 4 条：Factor Discovery Mode、Multi-Agent Pipeline、AI Confidence、Evidence Chain
- 新增交易执行术语 1 条：Review Mode / 盘后复盘模式
- 新增 A 股特有术语 3 条：Corporate Actions、Lockup Expiry、Ex-Dividend Date

### 2026-03-31 — v2.2

- 新增页面标签 4 条：Universe/标的池、Watchlist/观察列表、Intelligence/情报中心、Chart Lab/图表实验室
- 新增不一致修复记录 #15：`/trading/positions` Pattern 归属统一为 Analytical Overview Workspace（从 Ledger 移除）

### 2026-03-31 — v2.1

- 修正 Turnover Rate 命名为 Total Turnover Value（审计 FIX-11）
- 新增 A 股交易机制术语 8 条：Tick Size、Pre-market Auction、Post-market Call Auction 等
- 新增风控术语 2 条：Drawdown Recovery Days、Worst Day
- 新增因子工程术语 6 条：Factor Orthogonalization、Factor Standardization 等
- 新增交易成本术语 2 条：Stamp Duty Rate、Commission Rate
- 新增不一致修复记录 #11-14（审计发现）

### 2026-03-31 — v2.0

- 从 11 个类别重构为 14 个类别
- 新增"策略与回测"独立类别（从因子研究中拆出回测相关指标）
- 新增"A 股特有术语"类别（30+ 条，回应产品架构审计 P1-6/P2-6/P2-8）
- 新增高级回测指标：Sortino、Calmar、Skewness、Kurtosis、Profit/Loss Ratio
- 新增 A 股交易术语：T+1、涨跌停板、集合竞价、两融、龙虎榜、大宗交易等
- 新增 A 股市场术语：科创板、创业板、注册制、沪深港通、上证指数等
- 新增市场结构术语：DXY、US10Y、VIX、Turnover Rate、Advance/Decline
- 新增交易术语：印花税、佣金、保证金
- 新增风控术语：集中度风险、流动性风险、风格暴露
- 新增组件标签：Side Sheet、Toast、Banner、Alert Item、Blocker State
- 新增交互状态：Decision Banner、Pending / Next Actions、Today Pulse
- 统一"首次出现"列，标注术语来源 spec 编号
- 新增不一致项第 10 条：Trading Session vs Session

### 2026-03-31 — v1.0 创建

- 初始版本，覆盖 11 个术语类别
- 收录 130+ 条中英对照术语
- 记录 9 项不一致修复
