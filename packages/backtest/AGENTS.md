# Backtest Agent 指南

## 定位

回测引擎平面 — 回测主循环（Engine Loop）、Step chain 编排、数据回放、绩效统计、报告渲染。

## 核心模块

| 模块 | 职责 |
|------|------|
| engine.py | 回测主循环（EngineLoop） |
| steps/ | Step chain（data_fetch/strategy/risk/pre_trade/execution/audit） |
| simulation/ | 模拟模型（brokerage/fill/settlement/slippage） |
| data_feed.py | 数据回放接口 |
| replay.py | 回放控制器 |
| statistics.py | 绩效统计计算 |
| report_renderer.py | 报告渲染 |

## 依赖规则

### 允许

- backtest → kernel ✅
- backtest → data/strategy/portfolio/risk/execution ✅

### 禁止

- backtest → features/analysis/application/apps/platform ❌
- backtest 导入真实券商网关（ditto_execution.broker.gateways）❌

## 关键约束

- 回测是最高层模拟 runtime，可以依赖所有能力包
- 只使用模拟执行，禁止导入真实券商网关
- Step chain 模式保证每步职责单一、可测试
- 统计指标计算独立于主循环

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
