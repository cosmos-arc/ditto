# Tushare 外汇与大宗商品数据调研报告

> 调研日期: 2026-02-27
> 目的: 确定哪些大宗商品可以使用 Tushare 替代 FRED，并排查 fx_daily FETCH_ERROR 问题

## 1. Tushare 数据源分析

### 1.1 外汇数据 (fx_daily)

**接口信息:**
- 接口: `fx_daily`
- 数据源: FXCM（福汇）交易商
- 积分要求: ≥2000（5000+ 频次更高）
- 单次限制: 最大 1000 行记录

**关键字段:**
| 字段 | 类型 | 说明 |
|------|------|------|
| ts_code | str | 外汇代码（如 USDCNH.FXCM）|
| trade_date | str | 交易日期（**GMT 时间**，比北京时间晚一天）|
| bid_open | float | 买入开盘价 |
| bid_close | float | 买入收盘价 |
| bid_high | float | 买入最高价 |
| bid_low | float | 买入最低价 |
| ask_open | float | 卖出开盘价 |
| ask_close | float | 卖出收盘价 |
| ask_high | float | 卖出最高价 |
| ask_low | float | 卖出最低价 |
| tick_qty | int | 报价笔数 |

**数据分类 (fx_obasic):**
| 分类代码 | 分类名称 | 示例 |
|----------|----------|------|
| FX | 外汇货币对 | USDCNH, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD |
| INDEX | 指数 | US30(道琼斯), NAS100(纳斯达克100), SPX500(标普500), GER30(德国DAX) |
| COMMODITY | 大宗商品 | SOYF(**大豆**) |
| METAL | 金属 | XAUUSD(**黄金**), XAGUSD(**白银**) |
| BUND | 国库债券 | Bund(长期欧元债券) |
| CRYPTO | 加密货币 | BTCUSD(比特币) |
| FX_BASKET | 外汇篮子 | USDOLLAR(美元指数) |

### 1.2 期货数据 (fut_daily)

**国内期货交易所:**
| 交易所 | 代码后缀 | 主要品种 |
|--------|----------|----------|
| 上海期货交易所 (SHFE) | .SHF | 铜(CU)、铝(AL)、锌(ZN)、铅(PB)、镍(NI)、锡(SN)、黄金(AU)、白银(AG)、原油(SC)、燃油(FU)、螺纹钢(RB)、热卷(HC) |
| 大连商品交易所 (DCE) | .DCE | **大豆(A)**、豆粕(M)、豆油(Y)、玉米(C)、棕榈油(P)、铁矿石(I)、焦炭(J)、焦煤(JM)、聚乙烯(L)、聚丙烯(PP)、PVC(V) |
| 郑州商品交易所 (CZCE) | .ZCE | 棉花(CF)、白糖(SR)、PTA(TA)、甲醇(MA)、菜油(OI)、菜粕(RM)、玻璃(FG)、纯碱(SA)、尿素(UR)、锰硅(SM)、硅铁(SF) |
| 广州期货交易所 (GFEX) | .GFE | 工业硅(SI)、碳酸锂(LC) |
| 中国金融期货交易所 (CFFEX) | .CFX | 沪深300(IF)、中证500(IC)、中证1000(IM)、上证50(IH)、10年国债(T)、5年国债(TF)、2年国债(TS) |
| 上海国际能源交易所 (INE) | .INE | 原油(SC)、20号胶(NR) |

**数据要求:**
- 积分要求: ≥2000
- 数据起始: 1996年1月
- 每日盘后更新

## 2. 问题分析: fx_daily FETCH_ERROR

### 2.1 代码与文档的差异

**当前代码 (`fx.py:88`):**
```python
fields="ts_code,trade_date,open,high,low,close"
```

**Tushare 实际字段:**
```
ts_code, trade_date, bid_open, bid_high, bid_low, bid_close, ask_open, ask_high, ask_low, ask_close, tick_qty
```

**问题:** 代码请求了 `open, high, low, close`，但 Tushare 返回的是 `bid_open, bid_high, bid_low, bid_close` 等字段。

### 2.2 时区问题

**文档说明:**
> 交易日期（GMT，日期是格林尼治时间，比北京时间晚一天）

**当前代码:**
```python
.dt.replace_time_zone("Asia/Shanghai", ambiguous="earliest")
```

**问题:** 应该使用 `GMT/UTC` 时区，而非 `Asia/Shanghai`。

### 2.3 其他可能原因

1. **积分不足**: fx_daily 需要 2000 积分
2. **权限问题**: 需要确认账号是否有 FX 数据权限
3. **流量限制**: 5000 积分以下有频率限制

## 3. 数据源对比

| 数据类型 | Tushare | FRED | 建议 |
|----------|---------|------|------|
| **汇率 (USDCNH)** | ✅ fx_daily | ❌ 无 | Tushare |
| **黄金 (XAUUSD)** | ✅ METAL | ✅ GOLD | Tushare (实时性更好) |
| **白银 (XAGUSD)** | ✅ METAL | ✅ SILVER | Tushare |
| **原油 (WTI)** | ❌ 无 CFD | ✅ DCOILWTI | FRED |
| **原油 (Brent)** | ❌ 无 CFD | ✅ DCOILBRENTEU | FRED |
| **大豆 (SOYF)** | ✅ COMMODITY | ❌ 无 | Tushare |
| **VIX** | ❌ 无 | ✅ VIXCLS/VIX9D | FRED |
| **国内期货** | ✅ fut_daily | ❌ 无 | Tushare |
| **有色(铜铝锌)** | ✅ SHFE 期货 | ❌ 无 | Tushare |

### 3.1 推荐方案

| 优先级 | 数据 | 数据源 | 接口 |
|--------|------|--------|------|
| 1 | USDCNH 汇率 | Tushare | fx_daily |
| 2 | 黄金/白银 | Tushare | fx_daily (METAL) |
| 3 | 大豆 | Tushare | fx_daily (COMMODITY) |
| 4 | WTI/Brent 原油 | FRED | fred_adapter |
| 5 | VIX | FRED | fred_adapter |
| 6 | 铜/铝/锌 | Tushare | fut_daily (SHFE) |

## 4. 修复建议

### 4.1 fx.py 修复

1. **字段名称**: `open,high,low,close` → `bid_open,bid_high,bid_low,bid_close`
2. **时区处理**: `Asia/Shanghai` → `UTC` (GMT)
3. **日期偏移**: 考虑 GMT 比北京时间晚一天的影响

### 4.2 新增支持

1. **大宗商品 CFD**: 添加大豆 (SOYF.FXCM) 支持
2. **金属 CFD**: 添加黄金 (XAUUSD.FXCM)、白银 (XAGUSD.FXCM) 支持
3. **国内期货**: 考虑使用 `fut_daily` 获取铜、铝、锌等有色金属数据

## 5. 国债收益率数据

### 5.1 中国国债收益率 (Tushare yc_cb)

**接口信息:**
- 接口: `yc_cb`
- 数据源: 中债国债收益率曲线
- 积分要求: ≥5000
- 数据频率: 日频

**关键字段:**
| 字段 | 类型 | 说明 |
|------|------|------|
| ts_code | str | 曲线代码（1001.CB = 中债国债收益率曲线）|
| trade_date | str | 交易日期 |
| curve_type | str | 曲线类型（0=到期收益率，1=即期收益率）|
| y1 | float | 1年期收益率（%）|
| y2 | float | 2年期收益率（%）|
| y5 | float | 5年期收益率（%）|
| y10 | float | 10年期收益率（%）|

**口径说明:**
- 使用 `curve_type=0`（到期收益率，YTM）
- 与美国国债收益率（FRED DGS系列）口径一致
- 便于中美债券收益率比较分析

**已实现指标:**
| 指标代码 | 名称 | 字段 |
|----------|------|------|
| CN_BOND_YIELD_1Y | 中国1年期国债收益率 | y1 |
| CN_BOND_YIELD_2Y | 中国2年期国债收益率 | y2 |
| CN_BOND_YIELD_5Y | 中国5年期国债收益率 | y5 |
| CN_BOND_YIELD_10Y | 中国10年期国债收益率 | y10 |

### 5.2 美国国债收益率 (FRED)

**数据源:** FRED DGS系列
**口径:** 到期收益率（YTM）

| 指标代码 | 名称 | Series ID |
|----------|------|-----------|
| US_BOND_YIELD_1Y | 美国1年期国债收益率 | DGS1 |
| US_BOND_YIELD_2Y | 美国2年期国债收益率 | DGS2 |
| US_BOND_YIELD_5Y | 美国5年期国债收益率 | DGS5 |
| US_BOND_YIELD_10Y | 美国10年期国债收益率 | DGS10 |
| US_BOND_YIELD_30Y | 美国30年期国债收益率 | DGS30 |
| US_BOND_SPREAD_10Y2Y | 美国10Y-2Y国债利差 | T10Y2Y |

## 6. 美元指数数据

### 6.1 贸易加权美元指数 (FRED DTWEXBGS)

**接口信息:**
- Series ID: DTWEXBGS
- 数据源: Federal Reserve Board
- 频率: 日频
- 特点: 包含26种货币的贸易加权指数

**已实现指标:**
| 指标代码 | 名称 | 说明 |
|----------|------|------|
| US_DOLLAR_INDEX_BROAD | 美国贸易加权美元指数(广义) | Trade Weighted U.S. Dollar Index: Broad |

**vs. DXY (ICE美元指数):**
| 对比项 | DTWEXBGS | DXY |
|--------|----------|-----|
| 数据源 | FRED (官方) | ICE (商业) |
| 货币数量 | 26种 | 6种 |
| 稳定性 | 高 | 一般 |
| 获取方式 | FRED API | Yahoo Finance |
| 推荐度 | ⭐⭐⭐ | ⭐⭐ |

## 7. 待确认事项

1. [ ] 确认 Tushare 账号积分是否 ≥2000
2. [ ] 确认 fx_daily 接口权限是否已开通
3. [ ] 决定是否使用国内期货数据 (fut_daily) 替代 FRED
4. [ ] 确定大豆数据使用 SOYF (CFD) 还是国内期货 A (大豆)
5. [x] ~~确认 yc_cb 接口权限~~ (需要 5000 积分)
