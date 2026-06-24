# AI 趋势发现机制设计（全球映射 Trend Discovery, Phase T）

> 制定日期: 2026-06-23
> 范围: 跨市场（美股/台韩先行 → A 股扩散）AI 趋势发现机制
> 产出形态: CLI/报告（`ditto ops trend-discover`）
> 定位: 与 Phase 3 并行的独立能力域（Phase T），非选股 MVP 的延续
> 来源: brainstorming 产出，待 writing-plans 拆解为实施任务

---

## 一、背景与诉求

建立一套**发现机制**：观察到 AI 领域由美国/台湾/日韩先行启动，再扩散到 A 股；希望尽早捕捉这种跨市场领先-滞后趋势，在 A 股**提前布局**。投资市场以美股 + A 股为主。

诉求拆解为三类信号融合：
- **S1 产业链映射**：美股龙头（英伟达/台积电）突破 → A 股供应链映射标的
- **S2 技术扩散**：专利/招聘/产能/KOL 观点的渗透拐点（最前瞻，预留）
- **S3 资金情绪**：资金/情绪的领先-滞后（聪明钱先行）

---

## 二、可行性判断

**结论：可行，且踩中了机构正在系统化做的主流框架。**

核心证据——"美股先行→A 股扩散"在卖方研究里有正式名字：**全球映射（Global Mapping）框架**。

| 证据 | 来源 |
|------|------|
| "A 股科技定价已难独立于全球逻辑，需系统性全球映射框架" | 兴证策略（2026-05） |
| **"美股 AI 是主线，A 股 AI 是主题"**（A 股跟随、带滞后） | 东方财富研报 |
| 传导链真实存在：英伟达→台积电→服务器→光模块/PCB/散热/电源 | 多家券商产业链研报 |

这个"滞后窗口"正是发现机制要捕捉的 alpha。**失效边界**（设计必须处理）：
1. 映射会切换逻辑——出口管制收紧时，"英伟达映射"→"国产替代映射"，标的池整体替换
2. 传导时滞不恒定（有时领先 1-2 周，有时同步甚至反向）
3. A 股 AI 链波动极大（如 2025-11 板块单日跌 3.38%），纯信号易吃回撤，须叠基本面验证

---

## 三、业界调研精华

### 3.1 投研 SKILLS（人 + 流程）

| 能力 | 业界做法 |
|------|---------|
| Alpha 流程 | 买方"假设→验证→持仓"闭环，深度自研驱动超额 |
| 研究管理 | 从 Excel/Evernote 迁移到 Bipsync 等专业研究管理平台（process 专业化） |
| 另类数据 | 专利/招聘/卫星/信用卡/网络流量；市场 $29.6B→$276.9B（2026-2033，CAGR 37.6%），78% 美对冲基金已用 |
| 供应链图谱 | 显式建模 BOM 传导（英伟达→台积电→服务器→光模块/PCB/散热/电源） |

### 3.2 AI 驱动投研最佳实践

| 实践 | 说明 |
|------|------|
| 多 Agent 工作流 | 筛选/分析/评估分由专职 agent 承担（CFA Institute、AWS Bedrock） |
| RAG 接地 | LLM 输出锚定在财报/披露，防幻觉 |
| Agent 评估 Agent（A2A） | 独立 agent 做质量门禁，互评防"自我感觉良好" |
| Human-in-the-loop | AI 出信号/草稿，人做最终判断（A 股主题轮动尤其需要） |

**共识**：AI 不替代判断，而是把"广度扫描 + 结构化 + 早期信号"从几天压到几分钟。

### 3.3 数据源选型（已过 ditto 约束筛：polars-only / httpx / 合规）

| 数据需求 | 推荐源 | 否决项 |
|---------|--------|--------|
| 美股行情/估值 | **Tiingo**（专业美股源 + 免费 tier + httpx JSON） | ❌ yfinance（强制 pandas + 违反 Yahoo ToS + rate limit） |
| 美股财报/披露 | **SEC EDGAR**（免费 + 合规 + RAG 友好） | — |
| A 股资金流（北向/主力） | 扩 tushare `moneyflow`/`hsgt`（1 万分够） | — |
| A 股全链路 | 复用现有 tushare（已是强项） | — |
| 产业链映射 | ditto 内建 mapping 模型（手工种子 + LLM 辅助） | — |
| 舆情/X 大V | KOL 跨平台 RSS + 第三方 API（可插拔，v2/v3） | ❌ X 官方 API（$5K-42K/月）/ 裸爬虫（违反 ToS） |

---

## 四、总体架构

```
┌──────────────────────────────────────────────────────────────┐
│  数据底座  packages/data —— 新增 sources/adapters             │
│  Tiingo美股(免费起步)  SEC EDGAR   A股资金流(扩)   舆情/X(可插拔)│
│         │  统一 schema → parquet storage                       │
└─────────┼──────────────────────────────────────────────────────┘
          ▼
┌─ 信号层  packages/features —— 各自独立因子 + 各自 IC 验证 ────┐
│   S1 产业链映射        S3 资金情绪         S2 技术扩散(v3预留) │
│   美股龙头突破         北向/主力+板块      专利/产能/KOL      │
│   → A股映射标的池      资金领先-滞后       渗透率拐点(可插拔) │
└─────────┬─────────────────────────────────────────────────────┘
          ▼
┌─ 融合层  packages/features —— 综合领先指数 ──────────────────┐
│   LeadIndex = w1·S1 + w2·S3 + w3·S2  (IC加权→可学习)         │
│   产出：标的榜单 + 领先强度 + 可解释触发原因                  │
└─────────┬─────────────────────────────────────────────────────┘
          ▼
┌─ 产出层  packages/application queries + apps CLI ────────────┐
│   ditto ops trend-discover → Markdown 发现报告/标的榜单      │
│   (仿 factor-ic；信号物化为 derived artifact 走 IC 验证)      │
└──────────────────────────────────────────────────────────────┘
```

**数据流**：外部数据 → data sources 规整入仓 → features 各信号独立计算 + IC 验证 → 融合成 LeadIndex → application 渲染 → apps CLI 输出报告。

**四条核心纪律**（确保不失控、不污染 ditto）：

1. **先分后合**：每类信号是独立因子，先单独 IC 验证有效，再进融合层——融合不变成黑盒的唯一保证。
2. **数据源分层隔离**：新源走 data 包 `sources/adapters`；**抓取类（X/EDGAR HTML）隔离在外部 cron/服务**产出 parquet，ditto 只消费结构化结果，封号/ToS 风险不进核心。
3. **CLI 复刻 factor-ic 范式**：业务逻辑在 `application/queries`，apps 只编排 + 渲染，provider 在 `providers_market.py`。
4. **物化才能验证**：信号物化为 derived artifact，才能复用现成 `FactorEvaluationFacade` 做 IC 诊断——验证管线零新建。

---

## 五、数据底座

### 5.1 数据源选型矩阵

| 数据源 | 覆盖 | ditto 落点 | 约束/合规 | 阶段 |
|--------|------|-----------|----------|------|
| **Tiingo 美股** | EOD 价格(50年)+PE+财报(v2) | `sources/tiingo/`（price/fundamental/news adapters） | 免费 tier 够 v1；httpx JSON；`tiingo/token` keyring | **T1** |
| **A 股资金流** | 北向 `hsgt`+主力 `moneyflow` | 扩 [capital_market.py](packages/data/src/ditto_data/sources/tushare/adapters/capital_market.py) | 1 万分全开；扩现有 adapter | **T1** |
| **产业链映射** | 英伟达→A 股标的 | `data/metadata/supply_chain_mapping.py`（仿 [IndustryMappingReader](packages/data/src/ditto_data/storage/metadata/industry.py)） | 内建，零外部依赖 | **T1** |
| **SEC EDGAR** | 10-K/10-Q/8-K/transcript | `sources/edgar/` 新 source，httpx 直调 SEC API | 免费 + 合规；抓取隔离外部 | T1 可选 |
| **舆情/X** | KOL 观点/情绪 | `sources/sentiment/` 只读外部 cron 产出的 parquet | 抓取隔离外部；Layer1+2 | T2/T3 可插拔 |

**Dataset 枚举**在 [dataset_registry.py](packages/application/src/ditto_application/processes/ingestion/dataset_registry.py) 新增 `US_STOCK_DAILY` / `NORTHBOUND_FLOW` / `MAINFORCE_FLOW` / `SUPPLY_CHAIN_MAPPING` 等。

### 5.2 tushare 积分评估（1 万分）

| 用途 | 接口 | 1 万分够吗 |
|------|------|-----------|
| S3 A 股主力资金流 | `moneyflow` | ✅ 2000 分即可，绰绰有余 |
| S3 北向资金 | `moneyflow_hsgt` / `hsgt_top10` | ✅ 2000 分即可 |
| 特色数据（盈利预测/筹码/机构持股） | 各特色接口 | ✅ 1 万分正是开通门槛 |
| **S1 美股日线** | `us_daily` | ⚠️ 不在积分内，需单独开通"港美股数据权限" |

**结论**：1 万分对 A 股侧（S3 资金流）全开、够用。因 `us_daily` 需单独开通且精度不如专业源，**美股主源改用 Tiingo**（见 5.3），tushare 专注 A 股（它的强项）。这实现了"每个市场用最强源"的更健康架构。

### 5.3 Tiingo 定价 + plan-agnostic adapter

| Plan | 价格 | Unique Symbols/月 | Requests/天 | Requests/小时 |
|------|------|------------------|------------|--------------|
| **Free** | **$0** | 500 | 1,000 | 50 |
| Power User | ~$10/月 | — | 50,000 | 5,000 |
| Individual | $30/月($300/年) | 1,000 | — | — |
| Commercial | $50/月($499/年) | 108,441 | 100,000 | 10,000 |

**v1 用量 vs 免费 tier**：监控 ~50 个映射龙头，每日 1 次 ≈ 50 requests/天（利用率 5%）+ 50 symbols（利用率 10%）→ **免费 tier 完全够用，零成本启动专业美股源**。

**plan-agnostic adapter 架构**（免费→收费平滑演进，代码零改动）：

```
packages/data/src/ditto_data/sources/tiingo/
├── source.py          TiingoSource: httpx client + plan 配置 + keyring(tiingo/token)
├── _client.py         REST 封装: token bucket(50/hr) + tenacity retry + JSON→polars
├── adapters/
│   ├── price.py          EOD 价格 (Free)           → USStockPriceReader
│   ├── fundamental.py    基本面 (Individual $30)   → USFundamentalReader
│   ├── news.py           财经新闻 (Individual $30) → NewsReader (S2 事件情绪)
│   └── actions.py        公司行为/复权因子          → CorporateActionReader
└── schema.py            polars schema (美股 EOD 统一)

config: tiingo.plan = free | power | individual | commercial   (ENVIRONMENT 驱动)
```

**五条设计原则**：
1. **plan-agnostic**：adapter 不硬编码 plan，由 `config.tiingo.plan` 决定可调 endpoint；升级只改配置，代码零改动。
2. **统一 Reader 接口**：实现 ditto 既有 Reader Protocol，下游 features 只依赖接口 → 未来换 Polygon 只换 adapter。
3. **内建限速**：token bucket（免费 50 req/hr）+ tenacity retry，自动分批 + 退避。
4. **增量缓存**：EOD 落 parquet，增量更新只拉新数据，省 req 配额、抗抖动。
5. **keyring**：token 存 `tiingo/token`（仿 `tushare/token`、`fred/api_key`）。

**收费层价值**：Tiingo **Individual $30/月**同时解锁 fundamentals（S1 增强）+ News API（S2 舆情事件维度，可部分替代纠结的 X）→ 一次升级同时增强两类信号。

### 5.4 美股数据准确度——业界观点

业界金句：*"Tushare Pro 的 500 元，是 A 股数据标准化的税；Polygon 的 $199+，是美股数据质量信仰的税。"*

- ✅ **tushare 强项是 A 股**（深度好、财务清洗质量高、复权准确）→ A 股主力正确。
- ⚠️ **tushare 美股是"附加能力"**，精度不如专业源（Polygon/Tiingo）。三个坑：①复权基准特殊（以 end_date 为基准前复权，须按 PIT 规范显式处理）；②ticker 重用/幸存者偏差；③稳定性（曾突发停运，需本地缓存）。
- **对发现机制用途够用**：S1 只需检测龙头的**日频相对突破趋势**，非 tick 级精度。但选 Tiingo（专业源）规避上述坑，更稳。

### 5.5 产业链映射表（S1 心脏，ditto 内建领域资产）

放 `data/metadata/supply_chain_mapping.py`（仿 `IndustryMappingReader`），**支持 regime 双轨**——处理"映射会切换"失效边界：

```python
MappingTable:
  segment: 光模块
  us_leaders: [NVDA, AVGO]              # 该环节风向标
  a_share:
    normal: [中际旭创, 新易盛, 天孚通信]    # 常规供货映射
    substitution: []                     # 国产替代映射
  linkage_strength: 强                   # 直接供货 vs 间接映射
  regime: normal | substitution          # 当前激活逻辑
```

**环节的 regime 敏感性不同**：
- **算力芯片**：normal 弱、substitution 强（寒武纪/海光/昇腾链）→ **高 regime 敏感**
- **光模块**：中国本就是全球主力 → **低 regime 敏感**（normal/substitution 标的重合）
- **PCB/散热/电源**：居中

### 5.6 舆情/X 可插拔（T2/T3）

X 大V 观点的可行路径（**非**昂贵官方全量 API）：锁定特定 KOL 的观点流。

| 手段 | 成本 | 合规 |
|------|------|------|
| KOL 跨平台同步（Substack/博客 RSS） | 免费 | ✅ 最合规 |
| 第三方 API（TwitterAPI.io $0.00015/read） | ~$2-10/月 | ⚠️ 灰色，供应商担风险 |
| RSSHub 自建 / twscrape / Playwright MCP | 免费 | ⚠️ 违反 ToS + 封号 |
| Apify/Bright Data MCP | 按次付费 | ⚠️ 灰色 |

**设计**：抓取隔离在 ditto 外部（独立 cron/服务产出 parquet），ditto 的 `sources/sentiment/` adapter 只 `read_parquet`，封号/ToS/不稳定风险不污染核心。v1 不强依赖，按 Layer 1（跨平台 RSS）+ Layer 2（第三方 API）预留接入位。

---

## 六、信号层

### 6.1 S1 产业链映射（主引擎）

**三段式信号流**：

```
[① 美股龙头突破] → [② 产业链映射表] → [③ 领先-滞后传导] → S1_signal(每个A股标的)
   breakout_score     mapping(regime)      lead-lag 窗口 K
```

**① breakout_score**（0-1 强度分，免费 EOD 可算）：

| 子信号 | 计算 |
|--------|------|
| 创新高程度 | `close / rolling_max(close, 120日)` 相对位置 |
| 放量程度 | `volume / rolling_mean(volume, 20日)` |
| 动量加速 | 复用 ditto 已有 `momentum_accel` |

v1 = 价格+量+动量；v2 加财报超预期（需 fundamentals）。

**③ lead-lag 传导**（"提前布局"的数学基础）：
- **滚动交叉相关**：对每个映射对（NVDA→中际旭创），算美股收益 vs A 股收益在滞后阶数 0,1,2…20 日的 cross-correlation，取峰值 → 典型领先天数 K。
- **S1 信号**：美股龙头今日 breakout 高 → A 股映射标的获 `S1_signal = breakout_score × linkage_strength × 衰减函数(K 窗口内)`。
- 本质：A 股标的还没启动的当下（美股刚突破），用历史 lead-lag 关系预判未来 K 天表现 → 提前布局。

**regime 切换**（失效边界）：
- v1 半自动：维护"出口管制事件时间线"，人工标记 regime 切换点 → 敏感环节（算力芯片）标的池整体替换 normal→substitution。
- v3 自动：监控 EDGAR/新闻关键词（export control / entity list / sanction）自动切 regime。

**ditto 落点**：

| 组件 | 落点 | 架构边界 |
|------|------|---------|
| breakout 计算 | `features/factors/us_breakout.py` | features 不依赖 data，美股 EOD 由 application 注入 |
| 映射表 | `data/metadata/supply_chain_mapping.py` | 领域资产 |
| lead-lag 分析 | `features/` 新增 lead_lag 模块 | cross-correlation 纯计算 |
| S1 信号验证 | 物化为 derived artifact → `FactorEvaluationFacade` | 独立 IC 验证 |

**独立验证**：S1_signal 物化后用 `FactorEvaluationFacade` 算 IC/ICIR/分层，回答"美股龙头突破对 A 股标的是否真有预测力、K 是否稳定"。IC 显著为正 → lead-lag 成立 → S1 有效 → 才进融合层。

### 6.2 S3 资金情绪（S1 的交叉验证，非替代）

| 信号 | alpha 来源 | 性质 |
|------|-----------|------|
| S1 产业链映射 | 基本面需求传导 | 基本面/慢变量 |
| S3 资金情绪 | 资金先于价格布局 | 资金面/快变量 |

两者 alpha 低相关 → 融合互验：S1+S3 共振 = 高置信；只 S1 = 中等；只 S3 = 可能资金炒作需谨慎。

**双维度**：
- **A 股内部资金流领先-滞后**：北向（`moneyflow_hsgt`）+ 主力（`moneyflow`）对个股/板块的领先性。需扩 tushare adapter（1 万分够）。
- **跨市场情绪**：美股 AI 板块相对强度（Tiingo EOD 算 SMH/半导体 ETF 动量）作为情绪代理。

v2 升级：Tiingo News API（$30）做事件情绪；X KOL 做观点情绪。

**ditto 落点**：扩 `tushare/adapters/capital_market.py`（moneyflow/hsgt）→ `features/factors/fund_flow_leadlag.py` + `features/` 美股板块相对强度。物化后独立 IC 验证。

### 6.3 S2 技术扩散（v3 预留，可插拔）

最前瞻但最难量化，v1/v2 预留接口不做实现（YAGNI）：
- 潜在信号源：专利（USPTO）、招聘、产能（公告）、KOL 讨论度
- 预留统一的 `SignalSource` Protocol（`produce_signal() → SignalFrame`），S2 slot 空实现但不阻塞融合层，未来即插即用。

| 维度 | S1 | S3 | S2 |
|------|----|----|----|
| 方法论成熟度 | ✅ 兴证框架 | ✅ 资金流经典 | ⚠️ 渗透率难定义 |
| 数据可得性 | ✅ Tiingo+tushare | ✅ 扩 moneyflow | ❌ 无现成源 |
| **v1 优先级** | **主引擎** | **交叉验证** | 预留 |

---

## 七、融合层（LeadIndex）

**公式**：

```
LeadIndex_i = w1·ẑ(S1_i) + w2·ẑ(S3_i) + w3·ẑ(S2_i)      # S2 预留 → w3=0
```

每信号融合前必须标准化（z-score / rank）。

**权重策略**：

| 阶段 | 策略 | 理由 |
|------|------|------|
| **T1** | **IC 加权** | 用各信号独立验证期已算出的 IC 作权重，零额外成本，比等权合理 |
| T2 | 滚动窗口 IC 加权 | 动态调整（风格切换自适应） |
| T3 | 横截面回归学习权重 | 复用 ditto `fama_macbeth.py` |

**正交化（数据驱动）**：融合前测 S1/S3 相关性——高则正交化（复用 [orthogonalization.py](packages/features/src/ditto_features/evaluation/metrics/orthogonalization.py)）避免双重计数；低则直接加权。

**可解释产出**：每个高分标的带触发原因 + 共振/单信号/背离标签：

```
标的：中际旭创  LeadIndex=0.82（光模块，排名 #2）
  ├─ S1=0.9  英伟达 breakout=0.95，linkage=强，lead-lag K=3日
  ├─ S3=0.6  北向资金连续3日净流入 ¥2.3亿
  └─ 触发原因：产业链突破 + 资金共振（高置信）
```

**融合纪律前提**：S1、S3 各自独立 IC 验证有效才融合。绝不融合两个无效信号指望奇迹。S1 有效 + S3 无效 → `LeadIndex = S1 only`（w2=0）。融合是"按有效性动态组合"，非机械加权。

**ditto 落点**：`features/lead_index.py`（复用 `alpha.py` composite 模式）+ `ic.py` + `orthogonalization.py`，几乎零新建。

---

## 八、产出层（CLI/报告）

**命令**（复刻 [factor-ic](packages/apps/src/ditto_apps/cli/commands/ops.py) 范式）：

```bash
ditto ops trend-discover [OPTIONS]
  --date DATE        发现日期（默认今日）
  --top N            榜单前 N 标的（默认 20）
  --regime TEXT      normal / substitution / auto（默认 auto）
  --signals TEXT     s1,s3 / all（默认 all）
  --explain BOOL     输出触发原因（默认开）
  --output PATH      输出文件（默认 stdout）
```

**报告 6 section**：

| Section | 作用 |
|---------|------|
| 执行摘要 | regime 状态 + 触发龙头 + 共振标的数 + 信号有效性 |
| 美股龙头仪表盘 | 监控龙头的 breakout_score + 触发标签 |
| A 股发现榜单 | Top N：标的/环节/LeadIndex/S1/S3 分项/共振/触发原因 |
| 环节热力图 | 各产业链环节信号强度 |
| 信号有效性 | S1/S3 近期 IC/ICIR（透明化"准不准"） |
| 失效边界提醒 | regime 切换监测 + 映射异常告警 |

**交互节奏**（human-in-the-loop）：每日/每周跑 → 看榜单 + 触发原因 → 人工筛选 → 深度研究。AI 出信号和原因，人做最终判断。

**ditto 落点**（严格分层）：

| 层 | 落点 | 职责 |
|----|------|------|
| apps | `cli/commands/ops.py` 加 `@app.command("trend-discover")` | 只编排 |
| application | `queries/trend_discovery.py`（`TrendDiscoveryFacade`） | 编排 S1/S3/融合 |
| application | `queries/trend_discovery_report.py` | `render_trend_discovery_markdown()` 纯函数 |
| application | `providers_market.py` | DI provider |

apps 是纯编排层；业务逻辑全在 application/queries；渲染纯函数，apps 导入它、不直接碰 features 类型。

---

## 九、验证与回测

**三层验证体系**：

| 层 | 验证什么 | 方法 | 复用 ditto |
|----|---------|------|-----------|
| **L1 单信号** | S1/S3 各自有无预测力 | IC/ICIR + 分层 + 多空 + sub-period IC（跨 regime） | ✅ `FactorEvaluationFacade` |
| **L2 融合增益** | LeadIndex 是否 > 最强单信号 | LeadIndex_IC vs max(S1,S3)_IC；**无增益则回退单信号** | ✅ 物化后同走 Facade |
| **L3 端到端** | "提前布局"是否赚钱 | 事件研究（突破→K 天 CAR）+ 分层选股回测 - 交易成本 | ✅ backtest + portfolio |

**最关键验证——lead-lag K 的样本外稳定性**（机制命门）：训练期估的 K，测试期是否还成立？滚动重估 K 看稳定性 + 样本外 IC 衰减。K 不稳定 → 承认该映射对不可靠，降权或剔除（绝不自造通过）。

**防泄漏 / 过拟合**：

| 风险 | 防御 |
|------|------|
| PIT 泄漏 | 所有 rolling `closed="left"`（[pit.md](.claude/rules/pit.md)）；lead-lag 严格时间对齐 |
| 前视偏置 | breakout 只用当日及之前数据；regime 切换点不事后标 |
| 样本内外 | 训练期估 K + 权重，测试期验证，严格分离 |
| 多重检验 | 测多个龙头/环节时，IC 显著性做多重检验校正 |
| 幸存者偏差 | 用 point-in-time 标的池，不用幸存者池 |

**验证精神**：继承 Phase 2 `PromotionEvidenceCollector` 精神——客观收集证据，**绝不自造通过**。IC 低就承认低，K 不稳就剔除，不为"机制有效"硬凑参数。

---

## 十、Roadmap（Phase T1/T2/T3，每阶段带验证门禁）

| Phase | 交付物 | 验证门禁 |
|-------|--------|---------|
| **T1 S1 主引擎闭环** | Tiingo adapter(price)+keyring · 扩 tushare moneyflow/hsgt · 产业链映射表(手工种子~6环节) · `us_breakout`+`lead_lag` · S1 物化+IC · `ditto ops trend-discover`(S1 only) | **S1 IC 显著 + lead-lag K 样本外稳定** |
| **T2 S3 + 融合** | `fund_flow_leadlag`+`us_sector_strength` · S3 物化+IC · 融合 `lead_index`(IC加权+正交化) · 报告升级(双信号+共振) | **L2 融合增益成立**（无增益回退 S1 only） |
| **T3 增强+自动化** | Tiingo 升级 $30(fundamentals+News) · X KOL(Layer1+2) · regime 自动切换 · S2 技术扩散探索 | 各增强信号独立 IC 验证 |

---

## 十一、ditto 集成边界

| 维度 | 决策 |
|------|------|
| **新依赖** | **无**——全 httpx（已有）+ polars，零 pandas，pixi 无新增 |
| **新数据源** | Tiingo + 扩 tushare + EDGAR + 舆情(v3) — 属 CLAUDE.md **Ask-first**，方向已授权，具体 PR 时批准 |
| **架构层级** | `data`(sources) → `features`(信号，不依赖 data) → `application`(编排) → `apps`(CLI) — 严守 .importlinter |
| **keyring** | `tiingo/token`（仿 `tushare/token`、`fred/api_key`） |
| **抓取隔离** | EDGAR HTML/X 采集在 ditto 外部产出 parquet，adapter 只 read_parquet |
| **测试** | 每信号 TDD，分支覆盖 ≥ 80%，37 架构合约不破，basedpyright/ruff 全过 |

---

## 十二、启动前前置验证（T1 开工前必须确认）

1. **tushare `moneyflow`/`hsgt` 可调性**（1 万分应够，常规数据范畴，实测确认）
2. **Tiingo 免费 tier EOD 历史深度**（实测是否够回测 lead-lag；不够则 $10/月 Power User）
3. **Tiingo token 注册获取**

---

## 十三、调研来源

**业界投研 / AI 最佳实践**：
- [CFA Institute — Agentic AI for Finance](https://rpc.cfainstitute.org/research/the-automation-ahead-content-series/agentic-ai-for-finance)
- [ACM — LLM Agents for Investment Management](https://dl.acm.org/doi/10.1145/3768292.3770387)
- [AlphaSense — Buy-Side vs Sell-Side Research](https://www.alpha-sense.com/blog/trends/sell-side-vs-buy-side-research/)
- [FinRobot（开源 AI agent 投研平台）](https://github.com/ai4finance-foundation/finrobot)

**全球映射框架 / A 股产业链**：
- [兴证策略 — 全球科技投资如何映射 A 股](https://finance.sina.com.cn/stock/roll/2026-05-08/doc-inhxerwc7618089.shtml)
- [东方财富研报 — 借助美股映射看 AI 主线](https://pdf.dfcfw.com/pdf/H3_AP202503131644348549_1.pdf)
- [财联社 — AI 投资向上游半导体设备扩散](https://www.cls.cn/detail/2404415)

**数据源选型**：
- [Tiingo 定价](https://www.tiingo.com/about/pricing) / [Tiingo EOD](https://www.tiingo.com/products/end-of-day-stock-price-data)
- [tushare 积分权限对应表](https://tushare.pro/document/1?doc_id=290) / [tushare us_daily](https://tushare.pro/wctapi/documents/254.md)
- [六大美股数据源对比（知乎）](https://zhuanlan.zhihu.com/p/2026261994466997841) / [tickdb 主流行情源测评](https://tickdb.ai/blog/us-stocks/)
- [量化数据源选型（同花顺）](https://quant.10jqka.com.cn/view/article/MA2FZYDI6Y157022HIFZC7WA1K)
- [SEC EDGAR](https://www.sec.gov/search-filings)

**X / 舆情数据**：
- [X API 定价 2026](https://api.sorsa.io/blog/twitter-api-pricing-2026)
- [Bright Data — 8 Best Twitter Scrapers 2026](https://brightdata.com/blog/web-data/best-twitter-scrapers)
- [RSSHub](https://github.com/diygod/rsshub) / [RSS for Twitter 2026 指南](https://stepper.io/blog/rss-for-twitter-feed)
- [TwitterAPI.io](https://twitterapi.io/) / [socialdata.tools](https://socialdata.tools/)
