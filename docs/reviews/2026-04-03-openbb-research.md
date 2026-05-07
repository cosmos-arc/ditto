> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# OpenBB 深度调研报告

> 调研日期：2026-04-03
> 调研对象：[OpenBB](https://github.com/OpenBB-finance/OpenBB)（GitHub 51.5k stars）
> 调研目标：评估 OpenBB 在数据源层、数据处理、AI 层面是否有可借鉴之处

---

## 一、OpenBB 项目概览

**定位**：开源金融数据平台，目标是"Connect Once, Consume Everywhere"——一次集成数据源，通过 REST API / Python SDK / Jupyter / Excel / MCP / Workspace 等多前端统一消费。

**技术栈**：Python 3.10-3.13，FastAPI，Pydantic v2，Pandas（非 Polars），Poetry

**核心架构**：三层分离——Core → Router → Provider

```
┌──────────────────────────────────────────────────────┐
│  Frontend (Workspace / Excel / Python SDK / REST API) │
└──────────────────────┬───────────────────────────────┘
┌──────────────────────▼───────────────────────────────┐
│                  openbb-core                          │
│  Router (FastAPI) + ProviderInterface (Singleton)    │
│  + Standardization Framework                         │
└──────────────────────┬───────────────────────────────┘
┌──────────────────────▼───────────────────────────────┐
│  Provider Extensions (30+ 独立 pip 包)                │
│  yfinance / polygon / fmp / fred / binance / ...     │
└──────────────────────────────────────────────────────┘
```

---

## 二、核心架构亮点（值得借鉴）

### 2.1 TET 管道（Transform-Extract-Transform）

每个数据获取器是泛型类 `Fetcher[QueryParams, DataType]`，内含三阶段管道：

```
用户输入 → [Transform Query] → [Extract Data] → [Transform Data] → 标准化输出
              参数验证/映射       调用外部 API       字段映射/类型校验
```

**优势**：
- 错误隔离：精确定位是参数错误、网络错误还是数据错误
- 可测试性：每个阶段可独立单元测试
- 标准化：不同 Provider 的差异被封装在前后 Transform 中

**与 Ditto 对比**：

| 维度 | Ditto 现状 | OpenBB |
|------|-----------|--------|
| 抽象基类 | `DataSource` ABC，~30 个抽象方法 | `Fetcher[Q, D]` 泛型，3 个静态方法 |
| 粒度 | 一个 Source 类承载所有数据类型 | 一个 Fetcher 对应一种数据类型 |
| 管道 | 无明确阶段分离 | TET 三阶段 |
| 数据模型 | 方法级 docstring 约定 | Pydantic BaseModel 强类型 |

### 2.2 Provider 注册机制

```python
# Provider 注册类
polygon_provider = Provider(
    name="polygon",
    credentials=["api_key"],
    fetcher_dict={"EquityHistorical": PolygonEquityHistoricalFetcher},
)
```

通过 Poetry 插件入口点实现自动发现，安装新包后 `openbb-build` 即可注册。

**Ditto 对比**：Ditto 的 `DataSources` 类是手动构造函数注入，扩展性有限。可用 Dishka DI 容器实现类似效果。

### 2.3 标准化框架

```python
# 标准模型
class EquityHistoricalData(Data):
    date: datetime
    open: PositiveFloat
    close: PositiveFloat

# Provider 特化（Polygon）
class PolygonEquityHistoricalData(EquityHistoricalData):
    __alias_dict__ = {"date": "t", "open": "o", "close": "c", "volume": "v"}
    transactions: Optional[PositiveInt] = None  # Polygon 独有
```

切换数据源只需改 `provider=` 参数，返回格式完全一致。

---

## 三、数据源全资产调研

### 3.1 宏观经济数据

| 数据源 | 费用 | 中国数据 | 核心指标 | 限流 | Ditto 价值 |
|--------|------|---------|---------|------|-----------|
| **FRED** | 完全免费 | 部分中国指标 | 84 万+时间序列 | 120 次/分 | **已集成** |
| **OECD** | 完全免费 | 含中国（伙伴国） | GDP/PMI/贸易/就业/领先指标 | 60 下载/小时 | **高** |
| **IMF** | 完全免费 | 含中国（成员国） | WEO/BOP/COFER/贸易 | 无硬性限制 | **高** |
| **TradingEconomics** | $199/mo 起 | **完整中国覆盖** | 30 万+指标 + 预测值 | 按计划等级 | 中-高 |
| **BLS** | 免费（注册） | 无 | 美国就业/CPI/PPI | 注册后 500 次/天 | 低 |

### 3.2 外汇/汇率

| 数据源 | 费用 | 货币对 | 频率 | 限流 | Ditto 价值 |
|--------|------|--------|------|------|-----------|
| **yfinance** | 完全免费 | 全货币对（含 USDCNY=X） | 日/分钟 | ~360 次/小时 | **高** |
| **ECB API** | 完全免费 | 30+ 货币（EUR 基准） | 日频 | 无限制 | **高** |
| **FRED** | 完全免费 | USDCNY、主要交叉 | 日频 | 120 次/分 | **已集成** |
| **FMP** | 免费 250 次/天 | 10+ 主要货币对 | 分钟级 | 免费 250 次/天 | **高** |
| **Polygon** (Currencies) | 免费 5 次/分；$29/mo | 全外汇对 | Tick 级 | 免费 5 次/分 | 中 |
| **Tiingo** | 免费 5 次/分；$30/mo | 机构级外汇 | 分钟级 | — | 中 |

### 3.3 大宗商品

| 数据源 | 费用 | 覆盖品种 | 频率 | Ditto 价值 |
|--------|------|---------|------|-----------|
| **yfinance** | 完全免费 | CL=F(原油)、HG=F(铜)、ZS=F(大豆) 等 | 日频 | **高** |
| **EIA**（能源署） | 完全免费 | WTI/Brent/天然气/全部能源 | 日/周/月 | **高** — 能源 |
| **FMP** | 免费 250 次/天；$14/mo | 原油/天然气/金属/农产品 | 分钟级 | **高** |
| **Nasdaq Data Link** | 大量免费集 | 多样化数据集 | 日频 | 中 |

**关键品种获取方案**：

| 品种 | 免费方案 | 备注 |
|------|---------|------|
| WTI 原油 | yfinance `CL=F` | 日频够用 |
| Brent 原油 | yfinance `BZ=F` | 日频 |
| 铜 | yfinance `HG=F` | 日频 |
| 铁矿石 | 需 Tushare/DCE | Ditto Tushare 已有 |
| 大豆/玉米 | yfinance `ZS=F` / `ZC=F` | 日频 |
| 螺纹钢 | Tushare | Ditto Tushare 已有 |
| 天然气 | yfinance `NG=F` + EIA | 日频 |

### 3.4 贵金属

| 数据源 | 费用 | 覆盖 | 频率 | Ditto 价值 |
|--------|------|------|------|-----------|
| **yfinance** | 完全免费 | GC=F(黄金)、SI=F(白银)、PL=F(铂)、PA=F(钯) | 日频 | **最高** |
| **FMP** | 免费 250 次/天 | XAU/USD、XAG/USD 等 | 分钟级 | **高** |
| **Metals-API** | 免费 1K 次/月；$15/mo | 70+ 金属 | 实时 | 中 |

**注意**：上海金交所（SGE）数据需 Tushare 国内源补充。

### 3.5 加密货币

#### 行情数据

| 数据源 | 费用 | 覆盖 | 频率 | 特色 | Ditto 价值 |
|--------|------|------|------|------|-----------|
| **Binance API** | **完全免费** | 300+ 币种、Spot/Futures/Options | 实时/Tick | K线/资金费率/持仓量/深度 | **最高** |
| **CoinGecko** | 免费 1 万次/月；$35/mo | 2M+ 币种 | 分钟级 | DEX 数据、全市场覆盖 | **高** |
| **CryptoCompare** | 免费 10 万次/月；$79/mo | 6000+ 币种 | 分钟级 | 社交/交易信号 | 中 |
| **yfinance** | 完全免费 | BTC-USD、ETH-USD 等 | 日频 | 简单直接 | 中 |

#### Binance API 详情（重点推荐）

| 能力 | 说明 |
|------|------|
| Spot K线 | `GET /api/v3/klines` — 1s/1m/5m/15m/1h/4h/1d/1w/1M |
| Futures K线 | `GET /fapi/v1/klines` — USDT-M 永续/交割 |
| 资金费率 | `GET /fapi/v1/fundingRate` |
| 持仓量 | `GET /fapi/v1/openInterest` |
| 深度 | `GET /api/v3/depth` — L2 订单簿 |
| 限流 | 6000 请求权重/分钟（非常慷慨） |
| WebSocket | 实时推送 tick/kline/depth |
| 费用 | **完全免费**，仅需注册获取 API Key |

#### 链上/另类数据

| 数据源 | 数据类型 | 费用 | Ditto 价值 |
|--------|---------|------|-----------|
| **Glassnode** | 链上指标（NUPL/SOPR/活跃地址/交易所流出入） | 免费（有限）；Advanced $29/mo | **高** — 链上因子 |
| **CoinMetrics** | 链上 + 市场数据 | 免费（社区版）；Pro $99/mo | 中 |
| **Dune Analytics** | 自定义链上 SQL 查询 | 免费 2500 credits；Plus $99/mo | 中 |
| **Alternative.me** | 恐惧贪婪指数 | **完全免费** | **高** — 情绪因子 |

### 3.6 A 股相关数据源

| 数据源 | 费用 | A 股覆盖 | 数据类型 | Ditto 价值 |
|--------|------|---------|---------|-----------|
| **Tushare**（已集成） | 积分制 | **完整** | 日线/分钟线/基本面/宏观 | **核心源** |
| **yfinance** | 完全免费 | `.SS`/`.SZ` 后缀 | OHLCV/基本面/分红 | **高** — 备用验证 |
| **FMP** | 免费 250 次/天；$14/mo | 基础覆盖 | ETF 持仓/权重/财报 | **高** — ETF 分析 |
| **Finnhub** | 免费 60 次/分；Pro $39/mo | 全球（含中国） | **新闻情感分析**、实时行情 | **高** — 情绪因子 |
| **通达信**（已集成） | 免费 | 完整 | 本地数据 | 辅助源 |

### 3.7 Finnhub 情感分析详情

| 维度 | 详情 |
|------|------|
| 免费层 | 60 次/分钟（慷慨） |
| Pro 层 | $39/mo — 完整新闻 + 情感分析 + 公司基本面 |
| 情感分析 | 自动对新闻打情感分（-1 到 1），支持 6000+ 公司 |
| 覆盖 | 全球 60+ 交易所，含上海/深圳 |
| 其他数据 | 实时行情、SEC 财报、社交情绪、ESG 评分 |
| Ditto 场景 | **新闻驱动情绪因子**、跨市场情绪指标 |

---

## 四、OpenBB AI 功能

### 4.1 Copilot（内置 AI 助手）

- 自然语言查询数据，自动选择 Provider 和参数
- 上下文感知分析（基于 Dashboard Widget）
- 多轮对话 + 自动可视化

**上下文优先级（7 级）**：
```
1. 用户手动选定的 Widget  ← 最高
2. MCP 工具
3. 用户上传的文件（PDF/Excel/CSV）
4. 当前 Dashboard 所有 Widget
5. 对话历史
6. 全局 Workspace Widget
7. 网络搜索（后备）
```

### 4.2 MCP 集成

- 支持 6000+ MCP Server（通过 Smithery.ai）
- 每个工具可单独启用/禁用
- Copilot 自动决定调用哪些工具，支持顺序链式调用
- MCP 输出可映射为 Dashboard Widget

### 4.3 自定义 Agent SDK

```python
from openbb_ai import message_chunk, reasoning_step, table, chart
from openbb_ai.models import QueryRequest

async def query(request: QueryRequest):
    yield reasoning_step(event_type="INFO", message="分析中...").model_dump()
    yield message_chunk("分析结果...").model_dump()
    yield table(data=[...], name="结果").model_dump()
```

- Agent **无状态**，基于 SSE 流式响应
- 工具调用在**客户端执行**
- 支持 OpenAI / Azure OpenAI 后端

### 4.4 定价

| 功能 | 开源版 | Pro 版 |
|------|--------|--------|
| Python SDK + REST API | 免费 | 免费 |
| MCP Server | 免费 | 免费 |
| Copilot AI | 需自备 LLM API | 内置 OpenAI |
| 自定义 Agent SDK | 免费 | 免费 |
| Workspace 协作 | 有限 | 完整 |

---

## 五、对 Ditto 的借鉴建议

### 5.1 值得借鉴

| OpenBB 模式 | 价值 | Ditto 适用场景 | 优先级 |
|-------------|------|---------------|--------|
| **TET 管道** | 错误隔离 + 可测试性 | DataSource Fetcher 标准化 | **高** |
| **Fetcher 粒度** | 每个 Fetcher 对应一种数据类型 | 替代巨大的 DataSource ABC | **高** |
| **强类型 Data 模型** | Pydantic BaseModel 定义返回结构 | 替代 docstring 约定 | 中 |
| **`__alias_dict__` 字段映射** | 简洁处理不同源字段名差异 | Tushare/东财/同花顺差异 | 中 |
| **MCP 协议** | AI 工具调用标准化 | 远期 AI 辅助分析 | 低 |
| **Copilot 上下文优先级** | 上下文感知查询设计 | AI 分析场景参考 | 低 |

### 5.2 不适合 Ditto

| OpenBB 做法 | 原因 |
|-------------|------|
| Pandas 作为 Data 基础 | Ditto 已选 Polars |
| 继承链式标准模型 | Ditto 规模较小，Protocol/ABC 更简洁 |
| 静态构建步骤（`openbb-build`） | Ditto 用 DI 容器动态组装 |
| Poetry 插件入口点 | Ditto 用 pixi + Dishka DI |

### 5.3 数据源优先级建议

#### 零成本方案（覆盖所有资产类别）

| 资产类别 | 数据源 | 数据质量 |
|----------|--------|---------|
| 中国 A 股 | Tushare（已有） | 高 |
| 美国宏观 | FRED（已有） | 权威 |
| 国际宏观 | OECD + IMF | 权威 |
| 汇率 | yfinance + FRED + ECB | 日频够用 |
| 大宗商品 | yfinance + EIA | 日频够用 |
| 贵金属 | yfinance | 日频够用 |
| 加密货币 | **Binance API** | 实时/Tick 级 |
| 加密情绪 | Alternative.me | 日频 |
| 新闻情感 | **Finnhub**（免费 60 次/分） | 实时 |

#### 低成本增强

| 数据源 | 费用 | 增强能力 |
|--------|------|---------|
| FMP Starter | $14/mo | 全资产分钟级行情 + ETF 持仓 |
| CoinGecko Analyst | $35/mo | 1M+ 币种 + DEX 数据 |
| Glassnode Advanced | $29/mo | 链上因子（加密策略） |
| Finnhub Pro | $39/mo | 完整情感分析 + 全球基本面 |

---

## 六、参考资料

- [OpenBB GitHub](https://github.com/OpenBB-finance/OpenBB)
- [OpenBB Docs](https://docs.openbb.co)
- [OpenBB Architecture Overview](https://docs.openbb.co/odp/python/developer/architecture_overview)
- [OpenBB Provider Extension](https://docs.openbb.co/odp/python/developer/extension_types/provider)
- [TET 管道详解](https://openbb.co/blog/the-openbb-platform-data-pipeline/)
- [OpenBB AI SDK](https://docs.openbb.co/workspace/developers/openbb-ai-sdk)
- [OpenBB MCP Tools](https://docs.openbb.co/workspace/analysts/ai-features/mcp-tools)
- [Polygon.io Pricing](https://polygon.io/pricing)
- [FMP Pricing](https://site.financialmodelingprep.com/pricing-plans)
- [Finnhub Pricing](https://finnhub.io/pricing)
- [CoinGecko API Pricing](https://www.coingecko.com/en/api/pricing)
- [Binance API Docs](https://developers.binance.com/)
- [EIA API](https://www.eia.gov/opendata/)
- [ECB Data Portal API](https://data.ecb.europa.eu/help/api/overview)
- [Alternative.me Crypto API](https://alternative.me/crypto/api/)
- [Glassnode](https://glassnode.com/)
- [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
- [OECD API](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html)
- [IMF Data API](https://data.imf.org/en/Resource-Pages/IMF-API)
