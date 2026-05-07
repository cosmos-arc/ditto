# Risk Agent 指南

## 定位

风险管理平面 — 盘前风控检查、盘后风控审计、风险约束定义与验证、暴露度管理、回撤控制。

## 核心模块

| 模块 | 职责 |
|------|------|
| pre_trade.py | 盘前风控检查 |
| post_trade.py | 盘后风控审计 |
| constraints/ | 约束规则（checks/context） |
| exposure/ | 暴露度管理 |
| drawdown/ | 回撤控制 |
| contracts.py | 风控契约（PostTradeGuard/RiskSlice） |

## 依赖规则

### 允许

- risk → kernel ✅
- risk → portfolio ✅

### 禁止

- risk → data/features/strategy/execution/backtest/analysis/application/apps ❌
- risk → platform ❌

## 关键约束

- 风控是安全网，不承担交易决策
- 正常业务结果通过返回值表达，不通过异常（risk finding = return value）
- 只有配置失败和契约误用才使用异常
- 约束规则可组合、可配置

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
