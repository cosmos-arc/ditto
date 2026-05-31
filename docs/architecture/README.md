# Ditto 架构规范索引

> 本目录记录跨包架构规则、命名词典、抽象层级和扩展放置标准。它面向后续 agent 与个人开发者，回答"新代码应该放哪里、叫什么、依赖谁、不能做什么"。

## 12 包依赖图速查

```
                    ┌──────────┐
                    │  kernel  │  ← 依赖图最底层，零外部依赖
                    └────┬─────┘
                         │
                    ┌────┴─────┐
                    │ platform │  ← 横切基础设施（仅 exceptions 继承 kernel.DittoError）
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────┴────┐   ┌────┴─────┐  ┌────┴─────┐
     │  data   │   │ features │  │ analysis │
     └────┬────┘   └──────────┘  └──────────┘
          │
    ┌─────┼──────────────────────────────┐
    │     │                              │
┌───┴──┐ ┌┴────────┐ ┌──────┐ ┌────────┐
│strategy│ │portfolio│ │ risk │ │execution│
└───┬──┘ └────┬────┘ └──┬───┘ └───┬────┘
    │         │         │         │
    └─────────┼─────────┼─────────┘
              │         │
         ┌────┴─────────┴────┐
         │     backtest      │
         └────────┬──────────┘
                  │
         ┌────────┴──────────┐
         │   application     │  ← CQRS 编排层
         └────────┬──────────┘
                  │
         ┌────────┴──────────┐
         │      apps         │  ← Composition Root + 入口
         └───────────────────┘
```

## 包放置决策树

```
新增代码应该放哪个包？

1. 是纯值类型/枚举/Protocol（跨 2+ 包使用、零 I/O）？
   → kernel ✅

2. 是横切基础设施（缓存/日志/DB/存储基类）？
   → platform ✅

3. 是市场/基本面/宏观数据获取或存储？
   → data ✅

4. 是因子/表达式/衍生数据计算？
   → features ✅

5. 是策略定义/信号生成/alpha pipeline？
   → strategy ✅

6. 是组合构建/调仓/会计？
   → portfolio ✅

7. 是风控检查/约束/暴露度？
   → risk ✅

8. 是订单管理/券商网关/成交处理？
   → execution ✅

9. 是回测引擎/绩效统计/模拟？
   → backtest ✅

10. 是研究分析/数据集契约？
    → analysis ✅

11. 是 Use Case 编排（CQRS）？
    → application ✅

12. 是 HTTP API / CLI / Prefect Job / DI 注册？
    → apps ✅
```

## 关键约束速查

| 约束 | 说明 |
|------|------|
| 生产包禁止依赖 analysis | data/features/strategy/portfolio/risk/execution/backtest → analysis ❌ |
| strategy 禁止依赖 execution | strategy → execution ❌ |
| execution 禁止依赖 backtest | execution → backtest ❌ |
| backtest 禁止导入真实券商网关 | 只使用模拟执行 |
| 禁止跨包 re-export | 消费者直接引用源头包 |
| 禁止 TYPE_CHECKING 延迟导入 | 重构解决循环依赖 |
| portfolio/risk/backtest 禁止 platform | 需要时先更新包契约 |
| strategy 不依赖 data/features | 市场数据通过 Protocol 注入 |
| 使用 polars（禁止 pandas） | 使用 orjson（禁止 json） |
| 使用 pixi（禁止 pip/poetry/conda） | Python ≥ 3.13 |

## 架构文档

| 文档 | 状态 | 用途 |
|---|---|---|
| [agent-context-pack.md](agent-context-pack.md) | Active | Agent 快速参考：依赖图、边界规则、关键路径 |
| [boundaries-and-abstraction-standards.md](boundaries-and-abstraction-standards.md) | Active | 分层、模块化、命名、抽象层级一致性与扩展方式规范 |
| [2026-05-31-current-architecture-review.md](2026-05-31-current-architecture-review.md) | Active | 当前源码全局及分模块架构 review、评分、产品差距与逐模块攻克路线 |

## 各包规范索引

| 包 | CLAUDE.md | 定位 |
|---|---|---|
| kernel | [packages/kernel/CLAUDE.md](../../packages/kernel/CLAUDE.md) | 共享内核（类型 + Protocol） |
| platform | [packages/platform/CLAUDE.md](../../packages/platform/CLAUDE.md) | 横切基础设施 |
| data | [packages/data/CLAUDE.md](../../packages/data/CLAUDE.md) | 数据平台 |
| features | [packages/features/CLAUDE.md](../../packages/features/CLAUDE.md) | 因子与表达式 |
| strategy | [packages/strategy/CLAUDE.md](../../packages/strategy/CLAUDE.md) | 策略定义与信号 |
| portfolio | [packages/portfolio/CLAUDE.md](../../packages/portfolio/CLAUDE.md) | 组合构建与管理 |
| risk | [packages/risk/CLAUDE.md](../../packages/risk/CLAUDE.md) | 风险管理 |
| execution | [packages/execution/CLAUDE.md](../../packages/execution/CLAUDE.md) | 交易执行 |
| backtest | [packages/backtest/CLAUDE.md](../../packages/backtest/CLAUDE.md) | 回测引擎 |
| analysis | [packages/analysis/CLAUDE.md](../../packages/analysis/CLAUDE.md) | 研究分析 |
| application | [packages/application/CLAUDE.md](../../packages/application/CLAUDE.md) | 应用编排（CQRS） |
| apps | [packages/apps/CLAUDE.md](../../packages/apps/CLAUDE.md) | 应用入口 |

## 使用方式

开发或审查前先阅读对应包的 `CLAUDE.md`，再用本目录文档判断跨包边界和抽象层级。若两者出现冲突，以当前代码门禁和最新 `CLAUDE.md` 为执行约束，并补充 ADR 或修订本文档。
