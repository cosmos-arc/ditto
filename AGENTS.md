# Ditto 项目 Agent 指南

## 定位

T1 全栈量化交易平台（全球全市场定位，初期能力重点为 A 股 ETF），12 包模块化架构。前端 ditto-app 为独立仓库。

## 核心模块

| 包 | 职责 |
|---|------|
| kernel | 共享内核（类型 + Protocol + 薄实现） |
| platform | 横切基础设施（缓存/日志/DB/存储基类） |
| data | 数据平台（获取/存储/查询/PIT 安全） |
| features | 因子/表达式/衍生数据 |
| strategy | 策略定义与信号生成（Pipeline + Stage） |
| portfolio | 组合构建/调仓/会计 |
| risk | 风控检查/约束/暴露度 |
| execution | 交易执行/券商网关/审计 |
| backtest | 回测引擎/绩效统计 |
| analysis | 研究分析（纯研究层） |
| application | CQRS 编排层 |
| apps | 入口 + Composition Root |

## 依赖规则

- 所有包 → kernel ✅
- application → 所有能力包 + data + platform ✅
- apps → application + platform + composition root wiring ✅
- strategy 不依赖 data/features/portfolio/risk/execution ❌
- 生产包不依赖 analysis ❌
- portfolio/risk/backtest 不依赖 platform ❌

## 关键约束

- Python ≥ 3.13，使用 polars（禁止 pandas），使用 pixi（禁止 pip/poetry/conda）
- 真实券商接入暂不处理：仅定义/验证 BrokerGateway Protocol、事件 contract、审计/对账 conformance seam，不实现真实 adapter
- apps 层只处理后端 FastAPI/CLI/jobs/composition root；产品 UI 属于独立前端项目 ditto-app
- 禁止跨包 re-export、禁止 TYPE_CHECKING 延迟导入解决循环依赖
- TDD：RED → GREEN → REFACTOR，分支覆盖率 ≥ 80%
- 验证命令：`pixi run -e dev check`

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
