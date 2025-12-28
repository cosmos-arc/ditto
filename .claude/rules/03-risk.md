---
alwaysApply: true
---

# 风控核心规则

## Kill Switch 三级机制

| 级别 | 触发条件 | 动作 |
|------|----------|------|
| L1 | 回撤 ≥ 15% | 停止新开仓 |
| L2 | 回撤 ≥ 18% | 减仓 50% |
| L3 | 回撤 ≥ 20% | 清仓止损 |

## 必须遵守

1. **同步检查**：交易前必须检查 Kill Switch
2. **不可绕过**：禁止跳过风控检查
3. **100% 测试覆盖**：每个级别都要测试

## 代码模式

```python
# 交易前必须检查
def execute_trade(order: Order) -> TradeResult:
    # 1. 风控检查（必须同步）
    kill_switch_level = risk_engine.check_kill_switch()
    if kill_switch_level >= 3:
        raise KillSwitchError("L3: 清仓止损")
    if kill_switch_level >= 1:
        order = risk_engine.apply_restrictions(order, kill_switch_level)
    
    # 2. 执行交易
    return broker.execute(order)
```

## 详细指南

涉及风控工作时，读取 `.claude/skills/risk-guide/SKILL.md`
