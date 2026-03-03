# Yahoo Finance 与 Alpha Vantage 数据调研报告

> 调研日期: 2026-02-27
> 目的: 调研 Yahoo Finance 和 Alpha Vantage 支持的大宗、金属、汇率数据及 API 限制

## 1. Yahoo Finance (yfinance)

### 1.1 数据支持

| 数据类型 | 支持情况 | 代码示例 |
|----------|----------|----------|
| **股票/ETF** | ✅ 完整支持 | `AAPL`, `SPY` |
| **外汇** | ✅ 支持 | `EURUSD=X`, `USDCNY=X` |
| **大宗商品期货** | ✅ 支持 | `GC=F`(黄金), `CL=F`(原油), `SI=F`(白银) |
| **美元指数 DXY** | ✅ 支持 | `DX-Y.NYB` |
| **加密货币** | ✅ 支持 | `BTC-USD` |
| **指数** | ✅ 支持 | `^GSPC`(标普500), `^DJI`(道琼斯) |
| **国际市场** | ✅ 支持 | `000001.SS`(上证), `AAPL`(美股) |

**关键数据代码：**

```
# 美元指数
DX-Y.NYB           # ICE US Dollar Index (DXY)

# 大宗商品期货
GC=F               # 黄金期货 (COMEX)
SI=F               # 白银期货 (COMEX)
CL=F               # WTI 原油期货 (NYMEX)
BZ=F               # 布伦特原油期货
HG=F               # 铜期货 (COMEX)

# 外汇
USDCNY=X           # 美元/人民币
EURUSD=X           # 欧元/美元
USDJPY=X           # 美元/日元
USDCAD=X           # 美元/加元
```

### 1.2 API 限制

| 限制项 | 详情 |
|--------|------|
| **请求频率** | 每小时约 2,000 次请求，每天约 48,000 次 |
| **数据延迟** | 实时数据有 15-20 分钟延迟 |
| **认证机制** | 无官方认证，依赖非公开接口 |
| **服务条款** | **仅供个人使用**，商业用途有合规风险 |
| **稳定性风险** | 反爬机制、IP 封禁、接口随时可能变更 |

### 1.3 主要风险

1. **非授权访问**：yfinance 绕过官方 API 直接抓取页面，存在法律和稳定性风险
2. **反爬机制**：需要 Crumb + Cookie 校验，国内直连经常被 RST
3. **服务中断**：2025年9月曾发生断供事故，证明了工业级场景下的脆弱性
4. **条款限制**：雅虎服务条款限制商业应用

### 1.4 使用建议

```python
# 安全使用模式
import yfinance as yf
import time
from yfinance.exceptions import YFRateLimitError

def safe_yfinance_request(ticker, max_retries=3, retry_delay=5):
    """带重试机制的安全请求"""
    for attempt in range(max_retries):
        try:
            data = yf.download(ticker, period="1mo")
            return data
        except YFRateLimitError:
            time.sleep(retry_delay * (attempt + 1))  # 指数退避
    return None

# 获取美元指数
dxy = yf.download("DX-Y.NYB", start="2024-01-01", end="2024-12-31")

# 获取黄金期货
gold = yf.download("GC=F", start="2024-01-01", end="2024-12-31")
```

---

## 2. Alpha Vantage

### 2.1 数据支持

| 数据类型 | API 函数 | 说明 |
|----------|----------|------|
| **股票** | `TIME_SERIES_DAILY` | 日线、周线、月线 |
| **外汇** | `FX_INTRADAY`, `FX_DAILY` | 实时和历史汇率 |
| **大宗商品** | `function=COMMODITY` | WTI、Brent、天然气、铜、铝等 |
| **贵金属** | `function=COMMODITY` | 黄金、白银、铂金、钯金 |
| **加密货币** | `CRYPTO_INTRADAY`, `DIGITAL_CURRENCY_DAILY` | 主流加密货币 |
| **经济指标** | `ECONOMIC_INDICATORS` | GDP、CPI、失业率等 |

**支持的贵金属和大宗商品代码：**

```
# 贵金属
GOLD              # 黄金
SILVER            # 白银
PLATINUM          # 铂金
PALLADIUM         # 钯金

# 能源
WTI               # WTI 原油
BRENT             # 布伦特原油
NATURAL_GAS       # 天然气

# 工业金属
COPPER            # 铜
ALUMINUM          # 铝

# 农产品
WHEAT             # 小麦
CORN              # 玉米
COTTON            # 棉花
SUGAR             # 糖
COFFEE            # 咖啡
```

### 2.2 API 限制

| 层级 | 价格 | 每日限额 | 每分钟限额 | 历史数据 |
|------|------|----------|------------|----------|
| **Free** | 免费 | 25 次/天 | 5 次/分钟 | 有限 |
| **Basic** | $24.99/月 | 4,000 次/天 | 20 次/分钟 | 1 年 |
| **Standard** | $100/月 | 20,000 次/天 | 80 次/分钟 | 5 年 |
| **Premium** | $500/月 | 120,000 次/天 | 300 次/分钟 | 20 年 |

### 2.3 API 调用示例

```python
import requests

API_KEY = "your_api_key"
BASE_URL = "https://www.alphavantage.co/query"

# 获取黄金价格
params = {
    "function": "COMMODITY",
    "symbol": "GOLD",
    "interval": "daily",
    "apikey": API_KEY
}
response = requests.get(BASE_URL, params=params)
data = response.json()

# 获取外汇汇率
params = {
    "function": "FX_DAILY",
    "from_symbol": "USD",
    "to_symbol": "CNY",
    "apikey": API_KEY
}
response = requests.get(BASE_URL, params=params)
fx_data = response.json()

# 获取 WTI 原油
params = {
    "function": "COMMODITY",
    "symbol": "WTI",
    "interval": "daily",
    "apikey": API_KEY
}
response = requests.get(BASE_URL, params=params)
wti_data = response.json()
```

### 2.4 注意事项

1. **需要注册 API Key**：免费层需要有效邮箱注册
2. **每日限额严格**：免费层 25 次/天，适合低频数据拉取
3. **实时数据付费**：实时和15分钟延迟的美国市场数据需付费
4. **正式 API 服务**：有服务条款和 SLA 保障

---

## 3. 数据源对比

### 3.1 功能对比

| 特性 | Yahoo Finance | Alpha Vantage | FRED | Tushare |
|------|---------------|---------------|------|---------|
| **美元指数 DXY** | ✅ | ❌ | ❌ (有DTWEXBGS) | ❌ |
| **黄金/白银** | ✅ 期货 | ✅ 现货 | ✅ 现货 | ❌ (通过fx_daily) |
| **WTI/Brent 原油** | ✅ 期货 | ✅ 现货 | ✅ 现货 | ❌ |
| **外汇** | ✅ | ✅ | ❌ | ✅ (fx_daily) |
| **VIX** | ✅ | ❌ | ✅ | ❌ |
| **国内期货** | ❌ | ❌ | ❌ | ✅ (fut_daily) |
| **宏观指标** | ❌ | ✅ 部分 | ✅ 完整 | ✅ 部分中国数据 |
| **免费额度** | 高（但有封禁风险） | 25次/天 | 无限制 | 需积分 |

### 3.2 稳定性对比

| 维度 | Yahoo Finance | Alpha Vantage | FRED | Tushare |
|------|---------------|---------------|------|---------|
| **服务稳定性** | 低（非官方） | 中（正式服务） | 高（官方） | 中（需积分） |
| **商业可用性** | ❌ 限个人 | ✅ 有条款 | ✅ 公开数据 | ⚠️ 需付费 |
| **国内访问** | ❌ 不稳定 | ✅ 可访问 | ✅ 可访问 | ✅ 国内服务 |
| **API 规范性** | ❌ 非官方 | ✅ 官方 API | ✅ 官方 API | ✅ 官方 API |

---

## 4. 推荐方案

### 4.1 当前数据源分配（保持现状）

| 数据类型 | 数据源 | 原因 |
|----------|--------|------|
| **汇率 (USDCNH)** | Tushare | 国内服务，稳定性好 |
| **黄金/白银现货** | FRED | 官方数据，免费无限制 |
| **WTI/Brent 原油** | FRED | 官方数据，免费无限制 |
| **VIX** | FRED | 官方数据，免费无限制 |
| **国内期货** | Tushare | 唯一数据源 |

### 4.2 美元指数 DXY 获取方案

**方案 A：yfinance（推荐用于非生产环境）**

```python
# 优点：免费、数据完整
# 缺点：不稳定、有封禁风险
import yfinance as yf
dxy = yf.download("DX-Y.NYB", start="2024-01-01")
```

**方案 B：FRED DTWEXBGS（推荐用于生产环境）**

```python
# 优点：官方数据、稳定可靠
# 缺点：不是真正的 DXY，是贸易加权指数
from fredapi import Fred
fred = Fred(api_key="your_key")
dtwexbgs = fred.get_series("DTWEXBGS")
```

**方案 C：Trading Economics API**

```
# 优点：官方 DXY 数据，稳定可靠
# 缺点：付费服务
# 覆盖：DXY + 80+ 外汇对
```

### 4.3 数据源扩展建议

| 优先级 | 数据 | 数据源 | 接口 |
|--------|------|--------|------|
| 1 | 美元指数 | yfinance | `DX-Y.NYB` |
| 2 | 贸易加权美元指数 | FRED | `DTWEXBGS` |
| 3 | 备用黄金/白银 | Alpha Vantage | `COMMODITY` 函数 |

---

## 5. 待确认事项

1. [ ] 确认是否需要美元指数 DXY 数据（仅 yfinance 支持）
2. [ ] 确认是否接受 yfinance 的稳定性风险
3. [ ] 确认 Alpha Vantage 免费层 25次/天 是否满足需求
4. [ ] 决定是否使用 FRED DTWEXBGS 替代 DXY

---

## 6. 参考资料

- [yfinance GitHub](https://github.com/ranaroussi/yfinance)
- [Alpha Vantage Documentation](https://www.alphavantage.co/documentation/)
- [FRED API Documentation](https://fred.stlouisfed.org/docs/api/fred/)
- [Tushare API Documentation](https://tushare.pro/document/2)
