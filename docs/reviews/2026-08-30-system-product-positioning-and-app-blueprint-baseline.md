# Ditto 系统产品定位与 `ditto-app` 蓝图基线报告

> 日期：2026-08-30<br>
> 状态：**已确认（CONFIRMED PRODUCT BASELINE）**<br>
> 范围：产品定位、能力边界、当前系统事实、信息架构与概念原型<br>
> 明确不包含：详细系统方案、数据库/API 设计、任务拆分、排期与实施<br>
> 生效日期：2026-08-30<br>
> 后续规则：本报告是后续系统方案、路线图、页面合同和实施计划的上游产品事实源；旧文档与本报告冲突时，以本报告第 18 节裁决为准。

## 0. 执行结论

Ditto 不应继续被定义为“A 股 ETF 自动交易平台”，也不应继续把“全球全品类和机构化”作为当前产品完成度的终点。

已冻结的新定位是：

> **Ditto 是面向个人全栈量化投资者的本地优先 A 股量化决策与组合管理工作站。**
>
> 系统以 A 股个股和 ETF 为可研究、可选取、可建模、可进入组合的主要资产；以 A 股核心指数、申万行业指数、全球核心股票指数、利率、汇率、商品和宏观数据作为市场环境与风险解释层；完成从宏观环境、跨市场状态、行业强弱、个股选择、策略验证、组合构建、风险评估，到 Paper Trading、手工实际账户记录和复盘归因的完整闭环。
>
> Ditto 不连接 A 股券商，不提交、撤销或修改真实订单，不托管真实账户凭据。用户在系统外完成交易后，可以在 Ditto 中手工录入、导入和追加式更正真实成交、现金与持仓信息。

这个定位中的关键词不是“交易终端”，而是：

- **市场解释**：宏观与全球市场信息最终要解释 A 股环境，而不是停留在图表展示。
- **选股决策**：行业、强弱、个股排名和候选形成是一级主流程。
- **研究验证**：策略、因子和回测要为实际决策服务，而不是独立实验室。
- **双账户闭环**：Paper 账户验证模型，Manual 账户维护用户真实经济事实。
- **证据驱动**：每个判断、信号、持仓变化和收益都可追溯到当时可知数据。

## 1. 本次分析的事实来源

### 1.1 后端事实源

- `docs/roadmaps/ditto-development-roadmap.md`
- `docs/evidence/r2/README.md`
- `docs/evidence/r2/20260803T142442Z-live/r2-report.json`
- `docs/acceptance/r1-g1-evidence-2026-07-16.md`
- 当前 `data / features / strategy / portfolio / risk / execution / backtest / application / apps` 源码与测试
- `.importlinter` 与 `docs/architecture/agent-context-pack.md`

### 1.2 前端事实源

- `ditto-app/docs/brief/product-brief.md`
- `ditto-app/docs/brief/system-description.md`
- `ditto-app/docs/designs/specs/00_ditto_product_criteria.md`
- `ditto-app/docs/designs/specs/01_product_information_architecture.md`
- `ditto-app/docs/designs/specs/02_core_page_blueprints.md`
- `ditto-app/docs/designs/specs/06_core_user_flows.md`
- `ditto-app/docs/designs/specs/prototypes/*.html`
- `ditto-app/docs/contracts/pages/*.contract.json`
- `ditto-app/docs/review/product-beta-20260830/`
- 当前 `ditto-app/src/` 源码

### 1.3 外部产品基准

本报告不主张复制竞品，而是提取已经被真实产品验证的工作流原则：

- [Koyfin Market Dashboards](https://www.koyfin.com/features/market-dashboards/)：全球指数、利率、外汇、商品、信用和宏观数据应被组织成可比较的市场视图。
- [TradingView Stock Screener](https://www.tradingview.com/support/solutions/43000718866-tradingview-stock-screener-trade-smarter-not-harder/)：选股需要可组合过滤、可配置列、保存视图和结果流转，而不是标的身份目录。
- [QuantConnect Paper Trading](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading)：Paper Trading 的核心是让实时数据进入策略、由虚拟资金和模拟成交承接，而不把订单路由到交易所。
- [Portfolio Performance](https://www.portfolio-performance.info/en/) 与其[交易模型](https://help.portfolio-performance.info/en/reference/transaction/)：手工账户应由买卖、入金、出金、费用、税费、分红和转入转出等事件维护，并由事件重建持仓和收益。
- [ALFRED](https://fred.stlouisfed.org/docs/api/fred/alfred.html)：宏观数据存在历史修订，历史研究应使用当时可见的数据版本，而不是今天的最终值。

## 2. 对最早产品分析的校正

`ditto-app` 在 2026-04-17 的原始 Product Brief 中已经提出：

- 当前以 A 股为核心；
- 引入大宗商品、贵金属、外汇和国际主流指数；
- 核心链路是 `Observe → Discover → Research → Validate → Execute → Monitor/Improve`；
- 产品是专业工作站，而不是信息门户或后台管理系统。

这个出发点总体正确，但其中三项假设已经失效：

1. `MiniQMT = 实时数据 + 交易` 不再是可持续产品前提。
2. “Execution” 不能再默认解释为券商真实订单执行。
3. “全球全品类”不应等同于全球资产交易。全球核心指数和宏观数据当前主要承担 A 股环境解释，而不是成为新的交易与结算域。

因此，原始闭环更新为：

```text
Observe
宏观、全球指数、A 股市场状态
    ↓
Discover
行业强弱、股票池、个股筛选与比较
    ↓
Research
因子、策略、假设和历史证据
    ↓
Validate
回测、样本外、稳健性、成本和风险
    ↓
Decide
候选、目标仓位、风险结论和人工确认
    ↓
Record
Paper 自动模拟 / 实际交易手工记录
    ↓
Review & Improve
收益归因、偏差、策略衰减和组合调整
```

“Execute” 被拆成 `Decide + Record`。这更符合当前无法连接券商、但仍需要持续维护组合事实的真实约束。

## 3. 产品对象与市场范围

### 3.1 三层市场对象

| 层次 | 对象 | 是否进入组合 | 产品作用 |
|---|---|---:|---|
| 可决策资产 | A 股个股、A 股 ETF | 是 | 选股、策略、组合、Paper 和手工实际账户 |
| 市场参照 | A 股核心/风格/行业指数、全球核心股票指数 | 默认否 | 市场状态、相对强弱、风险偏好和基准 |
| 环境驱动 | 宏观、利率、汇率、商品、波动率、经济事件 | 否 | Regime、行业解释、风险预警和策略条件 |

这一区分非常重要：**“可展示全球指数”不等于“要实现全球证券交易、外币现金、多市场税费与结算”。**

### 3.2 A 股可决策资产

必须覆盖：

- 沪深北 A 股个股；
- A 股 ETF；
- 上市、退市、停牌、ST、涨跌停和交易状态；
- 前复权/后复权/原始价格的明确用途；
- 公司行动、财报、估值和流动性；
- 指数与行业历史成分；
- 用户自定义股票池、观察列表和排除列表。

### 3.3 国内核心指数与行业参照

当前源码已经配置九个市场指数与九个风格指数，包括：

- 上证指数、深证成指；
- 沪深 300、中证 500、中证 1000；
- 上证 50、创业板指、科创 50、创业板 50；
- 大/中/小盘价值与成长、全指价值、全指成长和全指红利；
- 可动态接入申万一级/二级行业指数。

这些应当从“摄取常量”提升为正式的市场参照目录，具备：

- 角色：宽基、风格、行业、策略基准；
- 默认展示位置；
- 数据新鲜度与历史覆盖；
- 对应可决策 Universe；
- 相对强弱与轮动使用方式。

### 3.4 全球核心市场参照

建议首批观察篮子，而非交易资产范围：

- 美国：标普 500、纳斯达克 100、道琼斯、罗素 2000；
- 中国香港：恒生指数、恒生科技；
- 日本：日经 225；
- 欧洲：Euro Stoxx 50，必要时补充 DAX；
- 风险参照：VIX、美元指数、美国 2Y/10Y 国债收益率；
- 商品参照：黄金、WTI、Brent。

具体指数清单需要在数据源权限、历史覆盖、时区和使用价值验证后冻结。当前不能把这份目标清单声明为已支持。

### 3.5 宏观数据

宏观数据不应形成“指标陈列馆”。每个指标必须回答至少一个产品问题：

- 当前是增长、通胀、流动性还是风险偏好主导？
- 哪些行业处于顺风或逆风环境？
- 当前选股模型应提高质量、价值、成长、防御还是动量权重？
- 组合风险预算是否需要收缩？
- 下一个重要数据发布时间是什么？

建议范围：

| 主题 | 中国 | 全球/美国 | 用途 |
|---|---|---|---|
| 增长 | GDP、PMI、工业/消费等 | GDP、PMI/就业 | 经济周期与行业环境 |
| 通胀 | CPI、PPI | CPI、核心 CPI、PCE | 利率预期、风格切换 |
| 流动性 | M1/M2、社融/信贷、Shibor、LPR | M2、Fed Funds | 风险偏好与估值环境 |
| 利率 | 国债期限结构、资金利率 | 1Y/2Y/5Y/10Y/30Y、美债利差 | 折现率和成长/价值风格 |
| 汇率 | CNY/CNH | DXY | 外部压力与跨市场传导 |
| 商品 | 国内商品参照 | 黄金、原油 | 通胀、周期和避险 |
| 风险 | 市场宽度、信用代理 | VIX、信用/收益率代理 | 风险预算与预警 |
| 事件 | 中国经济日历 | 全球经济日历 | 发布风险和知识时间 |

## 4. 核心用户与产品承诺

### 4.1 核心用户

核心用户是一个人同时承担四个角色：

- 市场观察者：理解宏观、全球和 A 股状态；
- 量化研究员：开发和验证因子与策略；
- 组合经理：选择标的、配置仓位和管理风险；
- 账户记录者：维护 Paper 与自己实际账户的交易事实。

系统必须支持角色切换，但不能为每个角色制造一套割裂产品。

### 4.2 单一产品承诺

> 每个交易日，Ditto 帮助用户从“市场发生了什么”走到“我应该关注什么、为什么、配置多少、Paper 结果如何、实际账户发生了什么”，并保留完整证据。

### 4.3 产品非目标

- A 股券商连接和真实订单自动化；
- HFT、智能路由、算法执行和低延迟 OMS；
- 全球证券交易、外币结算和跨国税务；
- 商业 SaaS、多租户、复杂 RBAC 和机构运营；
- 把 AI Agent 塑造成可以自主决定资金操作的交易员；
- 为了“全功能”维持三十多个同权重空页面。

## 5. 两套账户与三类组合事实

### 5.1 三类事实

| 对象 | 含义 | 产生方式 |
|---|---|---|
| Model Portfolio | 策略建议的目标组合 | 选股、优化和风险流程产生 |
| Paper Account | 虚拟资金实际模拟出来的组合 | Paper Order / Fill / Cash 事件产生 |
| Manual Account | 用户在系统外真实交易的记录组合 | 用户录入、导入和更正事件产生 |

三者可以比较，但不能互相覆盖。

### 5.2 Paper Account

Paper 是正式产品运行模式，不是测试替身：

```text
Signal
→ Target Portfolio
→ Risk Decision
→ Paper Order
→ Simulated Fill
→ Paper Cash / Position / PnL
→ Reconciliation / Review
```

必须显示：

- `PAPER` 永久标识；
- 使用的行情时点；
- 成交、滑点、费用和流动性假设；
- T+1、涨跌停、停牌、最小交易单位和部分成交；
- 模拟失败、数据过期和风险拒绝原因；
- 相对同区间回测和 Model Portfolio 的偏差。

### 5.3 Manual Account

Manual Account 的产品名称建议为“我的账户”，并永久显示“手工记录”。它不是券商连接状态。

至少支持：

- 期初现金和期初持仓；
- 任意实际买入/卖出，不要求一定存在系统 Signal；
- 入金、出金、费用、税费、分红；
- 送转、配股、证券转入/转出；
- 交易备注和关联决策；
- CSV/Excel 导入；
- 追加式作废、替换和调整；
- 持仓、可卖数量、成本、现金、已实现/未实现收益；
- 与 Paper、Model Portfolio 和基准的比较。

### 5.4 更正原则

用户看到的交互可以是“编辑成交”或“调整持仓”，但系统记录必须是追加事件：

```text
原始成交 F-001
    ↓
更正事件 A-001（说明原因）
    ↓
替换成交 F-002
```

当前有效视图使用 F-002，原始事实仍保留。

## 6. 选股与轮动产品

### 6.1 选股是主流程，不是筛选工具页

完整链路：

```text
宏观与全球环境
→ A 股 Regime
→ 行业强弱与扩散
→ 可交易 Universe
→ 个股多因子排名
→ 逐级排除
→ 候选比较
→ 目标组合与风险约束
→ Paper / Manual 跟踪
```

### 6.2 四层筛选模型

1. **身份与可交易性**：市场、板块、上市时间、ST、停牌、涨跌停、流动性。
2. **行业与相对强弱**：行业排名、行业扩散、个股相对行业/指数强度。
3. **质量与估值**：盈利质量、成长、估值、财务稳定性。
4. **策略与风险**：因子得分、风险暴露、拥挤度、换手和组合贡献。

### 6.3 选股结果必须解释

每个候选应包含：

- 入选与被排除原因；
- 各因子贡献；
- 行业与规模暴露；
- 相对基准和行业的强弱；
- 数据截止时间和快照；
- 主要风险；
- 建议动作：观察、加入候选池、进入研究、加入 Paper 或记录实际交易。

## 7. `ditto-app` 信息架构蓝图

现有五域结构可以保留，但产品语义需要重写。

### 7.1 一级产品域

| 产品域 | 单一职责 | 核心页面 |
|---|---|---|
| Today | 今天最需要处理什么 | 首页、优先事项、数据/账户异常 |
| Markets | 当前环境如何，机会在哪里 | 宏观与跨市场、A 股、行业、筛选、自选、事件、标的 |
| Research | 一个想法是否可信 | 因子、Universe、策略、实验、回测、评审 |
| Portfolio | 模型、Paper 和实际账户发生了什么 | 信号、Paper、我的账户、流水、风险、归因与复盘 |
| System | 数据和自动化是否可靠 | Data Products、任务、Agent、配置 |

`Trading` 的可见产品名称建议改为 `Portfolio / 组合`。已有 `/trading/*` URL 可以在后续实施中暂时保留，避免让路由迁移阻塞产品重构。

### 7.2 页面优先级

不再把 33 条路由都视为同等完成目标。

#### 核心日常工作面

1. Today Command Center
2. Macro & Cross-Market
3. A-Share Market & Sector Rotation
4. Stock Selection Workspace
5. Instrument Hub
6. Research Workspace
7. Strategy & Backtest
8. Decision / Signals
9. Paper Account
10. My Account（手工记录）
11. Portfolio Risk & Review
12. Data Health

#### 二级工作面

- Factor / Experiment / Review 深页；
- Watchlist / Calendar / Intelligence；
- Orders / Transactions Ledger；
- Agent Console；
- Platform Settings。

## 8. 核心概念原型

以下是用于确认信息层级的低保真原型。它们不等于实施稿，不替代现有高保真 HTML prototype。

### 8.1 Today Command Center

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TODAY  2026-08-30  数据 17/19 Fresh   PAPER 正常   我的账户 待录入 1 笔     │
├──────────────────────────────────────────────────────────────────────────────┤
│ 市场到组合证据链                                                               │
│ 美债↑ / DXY↑ → 全球风险偏弱 → A股缩量震荡 → 科技转弱/红利增强 → 风险预算 65% │
├───────────────────────────────────────────────┬──────────────────────────────┤
│ 今日主决策                                    │ 市场脉搏                     │
│ 降低科技超配，复核 3 个卖出候选               │ 全球指数 / 中国宽基 / VIX    │
│ [查看证据] [进入信号] [加入 Paper]            │ 宏观发布 / 数据新鲜度         │
├───────────────────────────────────────────────┼──────────────────────────────┤
│ 优先队列                                      │ 账户与风险                   │
│ 1 行业集中度超限                              │ PAPER   NAV / 回撤 / 现金     │
│ 2 强行业候选池更新                            │ MANUAL  NAV / 待录入 / 差异   │
│ 3 宏观数据发布后 Regime 变化                  │ 两账户偏差与待复核事项         │
└───────────────────────────────────────────────┴──────────────────────────────┘
```

### 8.2 Macro & Cross-Market

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ MACRO & MARKETS   截止 14:55 CST   [1D] [1W] [1M]   快照 #20260830-1455   │
├──────────────────────────────────────────────────────────────────────────────┤
│ 增长  ↘     通胀  →     流动性  ↘     风险偏好  中性偏弱                   │
├───────────────────────────────┬───────────────────────┬──────────────────────┤
│ 全球核心指数矩阵              │ 中国市场              │ 关键事件             │
│ S&P / NDX / HSI / HSTECH      │ 沪深300 / 中证1000    │ CPI、PMI、Fed、财报   │
│ VIX / DXY / US2Y / US10Y      │ 风格 / 宽度 / 成交     │ 实际/预期/前值/修订   │
│ Gold / WTI                    │ 北向/汇率/资金利率     │ 何时进入可知状态       │
├───────────────────────────────┴───────────────────────┴──────────────────────┤
│ 传导判断：美元与美债走强 → 成长估值承压 → A 股科技相对强度连续 3 日下降     │
│ [查看证据] [固定观点] [进入行业轮动]                                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Stock Selection Workspace

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ STOCK SELECTION  Universe: 全A非ST  Snapshot: #...  候选 42 / 过滤 5,321    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Universe → 可交易性 → 行业强弱 → 质量/估值 → 动量/风险 → 组合约束          │
├───────────────────────────────────────────────────┬──────────────────────────┤
│ 排名  标的   行业   RS行业  质量  价值  动量 风险 │ 候选证据 Inspector       │
│ 01   600xxx  电子      92    78    61    88  中  │ 入选原因                 │
│ 02   300xxx  电力设备  88    82    55    84  低  │ 因子贡献 / 暴露          │
│ ...                                               │ 排除风险 / 数据截止       │
│                                                   │ [比较] [研究] [Paper]    │
├───────────────────────────────────────────────────┴──────────────────────────┤
│ 排除漏斗：停牌 12 | 流动性 301 | 财务缺失 47 | 行业弱势 620 | 风险 18      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 8.4 Portfolio Workspace

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PORTFOLIO   [Model] [PAPER] [我的账户·手工记录]   估值时间 15:05 CST       │
├──────────────────────────────────────────────────────────────────────────────┤
│ 总资产 / 现金 / 当日PnL / 累计收益 / 回撤 / 风险预算 / 待处理差异           │
├──────────────────────────────────────────────┬───────────────────────────────┤
│ 持仓                                         │ 组合分析                      │
│ 标的 数量 可卖 成本 现价 PnL 目标 差异       │ 行业 / 风格 / 因子暴露        │
│ ...                                          │ 风险事件 / 归因 / 基准        │
├──────────────────────────────────────────────┼───────────────────────────────┤
│ 流水与更正                                   │ 动作                          │
│ 买入 / 卖出 / 入金 / 分红 / 调整 / 更正      │ PAPER: 运行/暂停/复盘          │
│ 原始事实 → 调整事件 → 当前有效视图           │ MANUAL: 记录成交/资金/导入     │
└──────────────────────────────────────────────┴───────────────────────────────┘
```

## 9. 视觉与交互方向

### 9.1 保留现有设计资产

现有 Graphite Studio、密度体系、金融数字字体、A 股红涨绿跌语义和专业工作台比例总体正确，不建议重做品牌系统。

需要恢复的是原型的信息层级和工作流，而不是再设计一套新皮肤。

### 9.2 产品签名：市场到组合证据链

建议把现有 `Decision Spine` 深化为 Ditto 特有的：

> **Macro → Global → A-Share → Industry → Stock → Portfolio Evidence Ribbon**

中文可称“市场到组合证据链”。

它不是装饰性步骤条，而是在不同页面持续回答：

- 当前判断从哪里来；
- 哪一层发生了变化；
- 影响到哪些行业、股票和账户；
- 用户下一步应该去哪一个工作面。

### 9.3 必须统一的状态语言

| 类型 | 状态语言 |
|---|---|
| 数据 | Fresh / Stale / Partial / Unavailable |
| 决策 | Proposed / Review / Accepted / Rejected / Expired |
| Paper | Planned / Submitted / Simulated Fill / Blocked / Reconciled |
| Manual | Recorded / Pending Reconciliation / Corrected |
| 证据 | Observed / Estimated / Revised / Missing |

页面不能再把 fixture、metadata-only 和真实业务数据统一标记成 `Live`。

### 9.4 动作文案

需要删除或替换会暗示券商写入的动作：

- “下单” → “加入 Paper”或“记录实际成交”；
- “券商连接” → “行情数据源状态”；
- “执行订单” → “模拟执行”或“记录成交”；
- “全部平仓” → Paper 中为“模拟平仓”，Manual 中为“记录卖出”，不能混用。

## 10. 当前系统能力事实

### 10.1 已证明或有较强工程基础

- A 股股票、ETF、核心指数、财务、估值、公司行动、指数权重等数据模型与摄取主干；
- 国内核心/风格指数配置及申万行业指数动态接入；
- FRED 宏观、利率、美元指数、商品和 VIX 指标注册表；
- 宏观存储中的 `knowledge_date` 和 FRED/ALFRED vintage 查询基础；
- PIT、snapshot、lineage、研究治理、样本外与 multiple-testing 主干；
- 个股多因子选择、逐级排除、行业/规模中性化和 selection evidence；
- 组合优化、风险约束、A 股交易规则和追加式成交更正；
- 账户期初基线、与信号关联的人工成交、部分成交与更正；
- `PaperBrokerGateway` 和 Paper 风控编排的单元测试基础；
- `ditto-app` 的设计系统、高保真原型、页面合同和路由工程底座。

### 10.2 部分存在，但尚不能作为产品能力声明

| 能力 | 当前事实 | 不能宣称完成的原因 |
|---|---|---|
| 宏观数据 | 存储、FRED/Tushare adapter、实验级 API 存在 | API 标为 experimental；产品页未消费；当前数据与覆盖未 fresh 验证 |
| 宏观 PIT | FRED adapter 支持 ALFRED 参数和 vintage collapse | Application/API 未暴露明确 as-of；Tushare 使用估算 release lag，需要真实发布时间合同验证 |
| 国内指数 | 已有摄取和固定指数目录 | 当前产品没有完整指数行情/强弱/成分投影 |
| 全球指数 | 原型有跨市场内容，FRED 有部分风险代理 | 没有正式全球核心指数数据产品、认证清单和产品 API |
| Paper Trading | Gateway 与 Runtime 有单元测试 | 仍被文档称“最小冒烟”；没有持续运行、持久化恢复、公开用例与完整 UI 闭环 |
| 手工账户 | 有期初基线、intent-bound fill、void/replace | 任意实际交易、现金事件、分红/税费和独立账户流水尚不是完整产品 |
| 前端市场页 | 页面、原型和 overlays 都存在 | `/markets`、`/a-shares`、`/screener` live 只读取 instrument metadata |
| 前端组合页 | 高保真 UI 存在 | live contract 只读 Daily Decision，没有账户写入路径和双账户切换 |

### 10.3 未证明或明显缺失

- 全球核心指数的当前数据源、许可、历史覆盖、时区和新鲜度；
- 中国宏观数据真实发布时点与修订版本的完整合同；
- 宏观/全球数据进入 Regime、行业和选股的可解释消费链；
- 通用手工账户事件账本；
- Paper 的长期连续运行、崩溃恢复和回测同期对账；
- 当前环境中的 fresh Tushare/FRED 和实时数据接入验收；
- 20 个交易日以上的真实日常使用证据；
- 用户是否能依靠产品完成一次完整的市场判断、选股、Paper、实际记录和复盘。

## 11. 当前前端“完成”口径的问题

`ditto-app/docs/plans/2026-08-29-product-completion-board.md` 报告 33/33 workflow 完成，但它主要证明：

- 路由存在；
- 页面合同存在；
- 声明的 read path 存在；
- 通用状态和 overlay 有测试；
- React 与 prototype 几何接近。

它没有证明页面提供了目标业务能力。

三个关键例子：

1. `/markets` 原型展示全球指数、利率、外汇、商品和相对强弱；live contract 只读取 `/api/v1/metadata/instruments`。
2. `/markets/screener` 原型展示条件栈、行情、估值、行业、评分和结果去向；live 页面只筛选标的身份字段。
3. `/trading/portfolio` 原型展示持仓、现金、PnL 和风险；live contract 只读取 `/api/v1/trade/daily-decision/v3`，没有任何 write path。

因此，后续产品验收至少需要拆成：

```text
Route exists
≠ Contract exists
≠ Visual parity
≠ API is called
≠ Domain data is sufficient
≠ User workflow is usable
≠ Product outcome is proven
```

## 12. 架构边界

本定位不需要新顶级包，也不需要改变现有 import graph。

| 能力平面/Owner | Provider/实现 | 直接消费者 | 跨边界合同 |
|---|---|---|---|
| `data` | Tushare、FRED、其他只读行情源及存储 | `application`、研究/回测数据端口 | Dataset/snapshot、宏观/指数查询、时间可见性 |
| `features` | 宏观、市场、行业、个股特征与物化 | `application` 注入的 strategy/backtest 消费端 | Feature artifact、lineage、snapshot identity |
| `strategy` | Regime、行业轮动、个股选择与 signal | `application` | StrategySpec、SelectionEvidence、Signal |
| `portfolio` | Model/Paper/Manual 会计、现金和持仓 | risk、application | AccountView、PortfolioEvent/派生视图 |
| `risk` | 组合约束、暴露、压力测试、Paper 风控 | application/backtest | RiskDecision、RiskSnapshot |
| `execution` | Paper order/fill；外部实际成交事实记录 | application | 现有 Order/Fill；`BrokerGateway` 仅可作为 Paper 模拟边界复用，不得装配真实券商实现；必要时增加窄的外部成交合同 |
| `backtest` | 历史模拟成交、成本与绩效 | application | Backtest manifest/result/replay evidence |
| `application` | 跨市场判断、选股、Paper、手工账户流程 | apps/agent | query/command/process DTO |
| `apps` | API、CLI、Jobs、DI、前端传输适配 | 用户 | OpenAPI 与任务入口 |

优先复用现有 `MacroQuery`、dataset/snapshot、SelectionEvidence、AccountView 和 Order/Fill 合同；若复用 `BrokerGateway`，必须将其约束为 Paper 模拟端口，并以 composition 证据证明不存在真实券商实现。

真正需要新增窄合同的地方是 Manual Account：当前 `RecordFillCommand` 强制要求已有 `intent_id`，无法表达用户在系统外自主完成、但没有 Ditto signal 的实际交易，也不能表达入金、出金、分红等非成交事件。

## 13. 时间与 PIT 合同

所有宏观、指数、行业、选股和 Paper 路径必须区分：

- `observation/effective time`：数据描述哪个时期或何时生效；
- `publication/knowledge time`：系统何时可能知道；
- `source snapshot`：使用了哪一批修订版本；
- `decision time`：用户/策略在哪一时刻做判断；
- `execution eligibility`：Paper 最早何时允许成交；
- `recorded_at`：用户何时补录实际事实。

特殊规则：

- 美国指数的“同一个日历日收盘”通常不可能在 A 股收盘前已知，必须使用最后一个已完成交易时段；
- 宏观指标必须按真实发布时间和 vintage 进入历史研究；
- 行业归属、指数成分、ST/停牌状态必须 effective-dated；
- 使用 T 日收盘信息的信号不能在 T 日同一收盘价成交，除非数据合同明确证明可用；
- 实时数据要同时记录 source timestamp、receive timestamp、session 和 freshness；
- 手工实际成交以实际成交时间影响账户，以 `recorded_at` 保留补录审计；
- 缺少 cutoff、snapshot 或版本信息时 fail closed。

## 14. 应立即停止投入的过度设计

- A 股真实券商 gateway、凭据、session 和订单恢复；
- 全球多资产交易、外币现金簿、多市场结算与税费；
- 机构级多租户、RBAC、合规运营和复杂隔离；
- 低延迟 OMS、算法执行和 tick/HFT；
- 在核心数据和工作流尚未成立前扩建 Agent 角色体系；
- 继续以“页面数、overlay 数和 API path 数”驱动产品完成度。

## 15. 当前最明显的产品短板

按产品价值排序：

1. **市场环境没有成为真实产品数据**：宏观和全球视图仍主要存在于原型。
2. **选股工作台没有消费后端选股能力**：live 筛选器退化为 instrument metadata 目录。
3. **Paper 不是持续运行的正式账户**：存在代码骨架，缺产品化运行和证据。
4. **实际账户管理不完整**：现有人工成交必须绑定系统 intent，无法承担个人真实账户账本。
5. **双账户及 Model/Paper/Actual 偏差不可见**。
6. **前端完成门把视觉/合同完整误当成产品完整**。
7. **数据验收状态互相矛盾**：路线图部分文字称 live Gate 完成，但 R2 README 和 2026-08-03 report 仍显示 certification/配置阻塞。
8. **缺当前环境的真实连续运行**：历史证据不能替代现在可用。

## 16. 产品成功标准

### 16.1 每日使用

- 用户能在 5 分钟内理解宏观、全球和 A 股环境；
- 能从行业强弱进入可解释的个股候选；
- 能完成候选比较、目标组合和风险复核；
- Paper 自动记录当天计划、成交和账户变化；
- 用户能在 1 分钟内记录一笔实际成交或资金事件；
- 当日可完成 Paper 与实际账户复盘。

### 16.2 数据与证据

- 每个页面显示数据截止时间、快照和新鲜度；
- 每个候选和信号都可追溯到 Universe、因子、行业版本和数据快照；
- 宏观修订不会泄漏到过去决策；
- 全球市场时区不会形成同日未来数据；
- 缺数据时明确 unavailable，不生成伪判断。

### 16.3 账户

- Paper 账户可连续运行至少 20 个交易日；
- 每个 Paper Fill 可解释成交假设；
- Manual 账户可从期初基线和事件完整重建；
- 更正不删除原始事实；
- 现金、持仓、市值和 PnL 每日可对账；
- Model、Paper、Manual 的差异可解释。

## 17. 由本基线约束、尚未展开的下一阶段

产品裁决确认后，再分别形成：

1. 产品范围与优先级裁决；
2. 数据产品方案：宏观、国内指数、全球核心指数和实时行情；
3. 选股与行业轮动方案；
4. Paper 与 Manual 双账户领域方案；
5. `ditto-app` 新 IA、页面合同和高保真 prototype 调整；
6. 后端/前端跨仓库 API 与读模型方案；
7. 真实验证矩阵；
8. 分阶段执行计划和验收 Gate。

以上八项目前均不在本报告中提前展开为施工任务。确认产品边界不等于这些能力已经交付。

## 18. 已确认的产品裁决

以下十项于 2026-08-30 全部确认并立即生效：

| ID | 裁决 | 正式结论 | 状态 |
|---|---|---|---|
| D1 | 核心可决策资产 | A 股个股 + A 股 ETF | ACCEPTED |
| D2 | 全球范围 | 核心指数/利率/汇率/商品只作为市场参照，不做全球交易 | ACCEPTED |
| D3 | 宏观角色 | 必须进入 Regime、行业和风险解释，不做独立数据陈列馆 | ACCEPTED |
| D4 | 选股地位 | 一级核心主流程，与行业轮动共同构成 Discover 主干 | ACCEPTED |
| D5 | 执行边界 | 不连接 A 股券商，不提交、修改或撤销真实订单；实时数据接入只能是只读数据能力 | ACCEPTED |
| D6 | 账户模式 | Model + Paper + Manual 三类事实，Paper 与 Manual 双账本 | ACCEPTED |
| D7 | 手工账户 | 支持任意实际成交和现金事件，不强制绑定系统 Signal | ACCEPTED |
| D8 | 产品域 | Today / Markets / Research / Portfolio / System 五域 | ACCEPTED |
| D9 | 设计基线 | 保留 Graphite Studio，新增“市场到组合证据链”作为产品签名 | ACCEPTED |
| D10 | 完成口径 | 以真实数据和完整用户闭环验收，不再以 route/contract/overlay 数量判定 | ACCEPTED |

### 18.1 裁决解释规则

- `Paper` 是系统自动产生模拟订单、模拟成交、现金、持仓和收益的正式运行模式，不是券商沙盒的别名。
- `Manual` 是用户实际账户的手工事实账本；允许没有 Ditto Signal 的买卖、入金、出金、费用、税费、分红和转入转出。
- `Model` 是目标组合和调仓意图，不得与 Paper 或 Manual 的经济事实混为同一账本。
- “全球”只描述市场环境数据范围，不扩大可交易资产范围。
- “实时”只描述数据时效，不推导出券商连接或自动下单能力。
- 前端旧 `/trading/*`、`/platform/*` 路径可以在迁移期保留为技术兼容路径，但用户可见产品心智统一为 Portfolio 与 System。

### 18.2 重新打开裁决的条件

任何方案不得自行弱化或扩张 D1—D10。只有真实约束发生变化、形成可验证用户场景，并经过新的显式产品裁决，才允许重新打开对应决策。
