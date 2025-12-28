---
name: backtest-guide
description: |
  【必读】回测开发指南。
  触发条件: Backtest、回测、T+1、涨跌停、净值曲线、夏普比率、最大回撤、收益率、策略验证、历史回测。
  核心规则: 双引擎架构、A股规则(T+1/涨跌停)、误差<0.5%、交易成本。
globs:
  - "**/backtest/**/*.py"
---

# 回测开发指南

## 双引擎架构

```
┌─────────────────┐  ┌─────────────────┐
│  VectorBacktest │  │  EventBacktest  │
│  (研究模式)      │  │  (生产模式)      │
├─────────────────┤  ├─────────────────┤
│ • 快速迭代      │  │ • 精确模拟      │
│ • 粗略估计      │  │ • 完整订单簿    │
│ • 策略研发      │  │ • 最终验证      │
└─────────────────┘  └─────────────────┘
         │                   │
         └───────┬───────────┘
                 ↓
        结果误差 < 0.5%
```

---

## 配置

```python
@dataclass
class BacktestConfig:
    start_date: date
    end_date: date
    initial_capital: float = 1_000_000

    # 成本
    commission_rate: float = 0.0003  # 万三
    stamp_duty: float = 0.001        # 千一（卖出）
    slippage: float = 0.001          # 千一

    # A股约束
    t_plus_1: bool = True
    price_limit: float = 0.10        # 涨跌停 10%
```

---

## A股规则

### T+1

```python
def apply_t1(signals: list[Signal], date: date) -> list[Signal]:
    valid = []
    for s in signals:
        if s.direction == "sell":
            pos = positions.get(s.code)
            if pos and pos.buy_date >= date:
                continue  # 今日买入不能卖
        valid.append(s)
    return valid
```

### 涨跌停

```python
def is_limit(price_data, direction: str) -> bool:
    change = (price_data.close - price_data.prev_close) / price_data.prev_close
    if direction == "buy" and change >= 0.10:
        return True   # 涨停买不进
    if direction == "sell" and change <= -0.10:
        return True   # 跌停卖不出
    return False
```

---

## 指标计算

```python
# 夏普比率
sharpe = (annual_return - 0.03) / volatility

# 最大回撤
max_drawdown = (nav / nav.cum_max() - 1).min()

# 卡玛比率
calmar = annual_return / abs(max_drawdown)
```

---

## 必须测试

```python
def test_vector_vs_event_alignment():
    """两种模式误差 < 0.5%"""
    ...

def test_t_plus_1():
    """T+1 约束生效"""
    ...

def test_price_limit():
    """涨跌停处理正确"""
    ...
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| 使用未来数据 | 严格按日期过滤 |
| 忽略 T+1 | 配置开启 |
| 忽略涨跌停 | 检查并拒绝 |
| 不计交易成本 | 包含佣金滑点 |
