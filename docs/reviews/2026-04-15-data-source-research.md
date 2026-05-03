> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# 数据源调研报告：行情/宏观/商品/舆情

> 调研日期：2026-04-15
> 调研目标：评估候选数据源在宏观、贵金属、大宗商品、舆情维度的增量价值
> 前置条件：Tushare Pro 10000 积分

---

## 一、Ditto 当前数据源现状

| 数据源 | 定位 | 已接入能力 |
|--------|------|-----------|
| **Tushare** | 主数据源 | ETF/股票/指数日线、基本面、资金流、SHIBOR、国债收益率、外汇、贵金属（fx_daily METAL） |
| **FRED** | 美国宏观/商品 | GDP/CPI/PCE/非农/利率曲线/VIX/美元指数/WTI/Brent/伦敦金/银 |
| **TDX** | 质量对账 | 本地通达信文件读取，不参与主数据摄入 |

### 数据缺口清单

| 缺口类别 | 严重程度 | 说明 |
|----------|---------|------|
| 中国宏观经济指标 | **高** | MacroTushareAdapter 仅接入 SHIBOR 隔夜，缺 GDP/CPI/PPI/PMI/M2/社融/LPR 等 |
| 国内大宗商品期货 | **高** | 完全空白，缺铜/铝/螺纹钢/铁矿石/豆粕/PTA 等品种 |
| 新闻/情绪数据 | **高** | 完全空白，无任何舆情管线 |
| CFTC/LME/EIA 仓储 | 中 | FRED 部分覆盖，但不完整 |
| 美股/港股数据 | 低 | 当前 A 股 ETF only，远期需求 |

---

## 二、行情数据源对比

### 2.1 Tushare（已有，10000 积分）

**积分门槛与权限：**

| 积分 | 频次限制 | 可用接口 |
|------|---------|---------|
| 120 | 200 次/分 | 基础行情、日历 |
| 600 | 200 次/分 | cn_gdp、cn_cpi、cn_ppi、shibor |
| 2000 | 500 次/分 | cn_pmi、money_supply、cn_trade、fut_daily/fut_mapping |
| 5000 | 无上限 | cn_shrzgm（社融）、fut_holding（持仓排名） |
| **10000** | **无上限** | **几乎所有常规接口** |

**大宗商品能力（10000 积分全部可用）：**

| 接口 | 功能 | 积分要求 |
|------|------|---------|
| `fut_daily` | 期货日线行情 | 2000 |
| `fut_mapping` | 主力合约映射 | 2000 |
| `csm` | 交易所仓单 | 2000 |
| `fut_holding` | 前 20 大会员持仓 | 5000 |
| `fut_margin` | 保证金参数 | 2000 |
| `fut_settle` | 结算参数 | 2000 |

**结论：10000 积分可完全覆盖中国宏观 + 国内期货数据，无需额外数据源。**

### 2.2 其他行情数据源

| 数据源 | 市场 | 稳定性 | 成本 | 对 Ditto 价值 |
|--------|------|--------|------|-------------|
| **AkShare** | A 股为主 | **低**（爬虫，目标网站变更即挂） | 免费 | 行情维度无价值；宏观/商品接口已被 Tushare 覆盖 |
| **Baostock** | 仅 A 股 | 中（独立服务器） | 免费 | 与 Tushare 高度重叠，仅当积分不足时作为免费降级方案 |
| **Pytdx** | 仅 A 股 | 中（依赖通达信客户端） | 免费 | 已有 TDX 集成 |
| **YFinance** | 美股/全球 | 中（Yahoo 频繁变更 API） | 免费 | 仅限远期美股扩展 |
| **Longbridge** | 美股/港股/A 股 | **高**（券商官方 API） | 免费（需开户） | 远期港股/美股扩展时首选 |

---

## 三、宏观数据对比

### 3.1 中国宏观（Ditto 最大缺口）

| 指标 | Tushare 接口 | 积分要求 | Ditto 现状 |
|------|-------------|---------|-----------|
| GDP | `cn_gdp` | 600 | **未接入** |
| CPI | `cn_cpi` | 600 | **未接入** |
| PPI | `cn_ppi` | 600 | **未接入** |
| 制造业 PMI | `cn_pmi` | 2000 | **未接入** |
| M0/M1/M2 | `money_supply` | 2000 | **未接入** |
| 社会融资规模 | `cn_shrzgm` | 5000 | **未接入** |
| LPR | `shibor_lpr` | 600 | **未接入** |
| 进出口 | `cn_trade` | 2000 | **未接入** |
| SHIBOR 隔夜 | `shibor` | 120 | **已接入** |
| 中债国债收益率 | `yc_cb` | 2000 | **已接入**（BondYieldTushareAdapter） |

**结论：MacroTushareAdapter 当前只接了 SHIBOR 一个接口，Tushare 10000 积分可覆盖全部中国宏观指标，只需扩展 Adapter。**

### 3.2 美国宏观（FRED 已完善）

FRED 当前覆盖：GDP/CPI/PCE/核心CPI/核心PCE/非农/M2/国债收益率曲线（1Y-30Y）/联邦基金利率/VIX/美元指数。

**无缺口，无需补充。**

---

## 四、大宗商品/贵金属对比

| 品种 | Tushare | FRED | Ditto 现状 |
|------|---------|------|-----------|
| WTI 原油 | - | `DCOILWTICO` | **已接入**（FRED） |
| Brent 原油 | - | `DCOILBRENTEU` | **已接入**（FRED） |
| 伦敦金 | fx_daily METAL | `GOLDAMGBD228NLBM` | **已接入**（双源） |
| 伦敦银 | fx_daily METAL | `SLVPRUSD` | **已接入**（双源） |
| 沪铜/沪铝/沪锌 | `fut_daily` | - | **未接入** |
| 螺纹钢/热卷 | `fut_daily` | - | **未接入** |
| 铁矿石 | `fut_daily` | - | **未接入** |
| 豆粕/豆油/棕榈油 | `fut_daily` | - | **未接入** |
| PTA/甲醇/玻璃 | `fut_daily` | - | **未接入** |
| CFTC 持仓 | - | `CFTC_*` | 部分可接入 |
| LME 库存 | - | - | 未接入 |

**结论：国内期货品种全部可通过 Tushare fut_daily + fut_mapping 接入，无需 AkShare。**

---

## 五、新闻搜索数据源对比

| 数据源 | 定位 | 中文能力 | 结构化输出 | 免费额度 | 付费价格 | 推荐度 |
|--------|------|---------|-----------|---------|---------|--------|
| **Tavily** | AI-native 搜索 | 中 | **强**（AI 摘要） | 1000 次/月 | ~$5/千次 | **推荐首选** |
| **Bocha（博查）** | 国产 AI 搜索 | **强** | **强**（AI 摘要 + 模态卡） | 有 | ~¥0.03/次 | **推荐备选** |
| **Brave Search** | 隐私搜索引擎 | 中 | 中 | $5 信用/月 | $3-5/千次 | 可选 |
| **SerpAPI** | Google 代理 | **强** | **强** | 100 次/月 | $50/5千次 | 太贵 |
| **Anspire** | 中文优化搜索 | **强** | 中 | 有 | 未知 | 生态弱 |
| **MiniMax** | AI 大模型搜索 | **强** | 中 | 有 | 未知 | 生态弱 |

**结论：Tavily 是新闻搜索最优选，1000 次/月免费额度足够开发测试。Bocha 作为中文补充。**

---

## 六、国内社交舆情数据源

A股市场没有标准化社交情绪 API，可行路径：

| 来源 | 数据类型 | 获取方式 | 稳定性 | 情绪维度 | 推荐度 |
|------|---------|---------|--------|---------|--------|
| **AkShare `index_news_sentiment_scope`** | A 股新闻情绪指数 | 一行调用 | 中（依赖 chinascope） | 情绪得分 | **推荐** |
| **AkShare `news_economic_baidu`** | 百度财经新闻 | 一行调用 | 中 | 新闻标题/内容 | **推荐** |
| **Tavily/Bocha 搜索** | 全网新闻 | API | **高** | 需 NLP | **推荐** |
| 东方财富股吧 | 散户讨论 | 爬虫 + 反爬对抗 | **低** | 帖子/阅读数/评论数 | 中 |
| 雪球 | 投资者讨论 | 爬虫（动态反爬严重） | **极低** | 帖子/热度 | 低 |
| 同花顺 iFinD | 专业舆情 | 付费终端 | **高** | 结构化指标 | 远期 |

**结论：A股舆情需要自建"新闻采集 → NLP 情绪打分 → 因子化"管线。AkShare 的情绪指数接口可作为现成因子来源。**

---

## 七、综合建议

### 行动优先级

```
P0 — 扩展现有 Tushare 适配器（零额外成本）

  1. MacroTushareAdapter 扩展
     接入：cn_gdp / cn_cpi / cn_ppi / cn_pmi / money_supply /
           shibor_lpr / cn_shrzgm / cn_trade
     工作量：中等（复用现有 adapter 模式）

  2. 新增 FuturesTushareAdapter
     接入：fut_daily / fut_mapping（主力合约映射）
     覆盖：沪铜/沪铝/螺纹钢/铁矿石/豆粕/PTA 等
     工作量：中高（新 adapter + 新 Schema + 新存储）

P1 — 新闻/情绪管线（新增能力）

  3. AkShare 轻量集成
     仅接入：index_news_sentiment_scope + news_economic_baidu
     定位：情绪因子数据源，不作为行情/宏观补充
     工作量：低（两个独立接口）

  4. Tavily 集成（可选）
     当需要事件驱动策略时接入
     工作量：低（标准 REST API）

不需要
  - AkShare 宏观/商品接口 → Tushare 10000 积分完全覆盖
  - Baostock → 与 Tushare 重叠
  - Pytdx → 已有 TDX
  - SerpAPI → 太贵
  - Stock Sentiment API → 仅美股社交
  - Anspire/MiniMax → 生态弱
```

### 核心判断

> **10000 积分下，Tushare 本身就是最全面的 A 股数据平台。当前核心问题不是"数据源不够"，而是"已有数据源的接口没接全"。最有效的投入是扩展 MacroTushareAdapter + 新建 FuturesTushareAdapter。**
>
> AkShare 唯一的不可替代价值是 A 股新闻情绪指数（`index_news_sentiment_scope`）和百度财经新闻（`news_economic_baidu`），可作为轻量级情绪因子来源。

---

## 参考资料

- [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) — 数据源分类参考来源（30k stars）
- [Tushare 积分权限表](https://tushare.pro/document/1?doc_id=290)
- [AKShare 宏观数据文档](https://akshare.akfamily.xyz/data/macro/macro.html)
- [AKShare 指数/情绪数据](https://akshare.akfamily.xyz/data/index/index.html)
- [AKShare 期货数据](https://akshare.akfamily.xyz/data/futures/futures.html)
- [Brave Search API](https://brave.com/search/api/)
- [Tavily API](https://tavily.com)
- [2026 年量化数据源选型（知乎）](https://zhuanlan.zhihu.com/p/2005025480454197447)
- [2026 年量化数据源深度拆解（掘金）](https://juejin.cn/post/7605537925149261876)
