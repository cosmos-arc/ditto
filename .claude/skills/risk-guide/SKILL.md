---
name: risk-guide
description: |
  【必读】风控指南。
  触发条件: Kill Switch、风控、回撤 drawdown、熔断、止损、仓位控制、风险管理、最大回撤、持仓限制。
  核心规则: 三级 Kill Switch (15%/18%/20%)、同步检查、禁止绕过、100% 测试覆盖。
globs:
  - "**/risk/**/*.py"
---

# 风控指南

## Kill Switch 三级机制

| 级别 | 触发条件 | 动作 | 日志级别 |
|------|----------|------|----------|
| L1 | 回撤 ≥ 15% | 停止新开仓 | WARNING |
| L2 | 回撤 ≥ 18% | 减仓 50% | CRITICAL |
| L3 | 回撤 ≥ 20% | 清仓止损 | CRITICAL |

---

## 实现模式

```python
class RiskEngine:
    def check_kill_switch(self, drawdown: float) -> int:
        if drawdown >= 0.20:
            logger.critical("Kill Switch L3",
                event="kill_switch_triggered", level=3)
            return 3
        elif drawdown >= 0.18:
            logger.critical("Kill Switch L2",
                event="kill_switch_triggered", level=2)
            return 2
        elif drawdown >= 0.15:
            logger.warning("Kill Switch L1",
                event="kill_switch_triggered", level=1)
            return 1
        return 0
```

---

## 交易前检查

```python
def execute_trade(order: Order) -> TradeResult:
    # 必须同步检查
    level = risk_engine.check_kill_switch()

    if level >= 3:
        raise KillSwitchError("L3 清仓")
    if level >= 2:
        order = reduce_position(order, 0.5)
    if level >= 1:
        if order.is_new_position:
            raise KillSwitchError("L1 禁止新开仓")

    return broker.execute(order)
```

---

## 持仓限制

| 限制 | 值 |
|------|---|
| 单标的上限 | 20% |
| 行业上限 | 30% |
| 最大持仓数 | 10 |

---

## 必须测试

```python
def test_kill_switch_l1():
    result = risk_engine.check(drawdown=0.15)
    assert result.level == 1
    assert result.action == "stop_new_positions"

def test_kill_switch_l3():
    result = risk_engine.check(drawdown=0.20)
    assert result.level == 3
    assert result.action == "liquidate_all"
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| 异步风控检查 | 同步检查 |
| 吞掉风控异常 | 上抛异常 |
| 跳过风控 | 始终检查 |
