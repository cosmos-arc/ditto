# App 层架构规范

## 定位

App 层是 **Application Layer（应用层）**，负责 Use Case 编排，采用 CQRS 模式组织。

**核心原则**：
- 纯编排层，不包含核心业务逻辑
- 通过 CQRS 模式分离读写职责
- 协调 Engine（领域计算）+ Data（数据服务）

## 依赖

```
ditto_app → ditto_kernel ✅
ditto_app → ditto_data ✅
ditto_app → ditto_engine ✅
ditto_app → ditto_analytics ✅
ditto_app → ditto_infra ✅
ditto_app 禁止 → ditto_interfaces ❌
```

## CQRS 模块结构

```
ditto_app/
├── query/              # 只读查询（零写入）
│   ├── metadata.py    # 元数据查询
│   ├── market.py      # 行情查询
│   ├── capital.py     # 资金查询
│   ├── fundamental.py # 基本面查询
│   ├── macro.py       # 宏观查询
│   ├── fx.py          # 外汇查询
│   ├── commodity.py   # 商品查询
│   ├── source.py      # 数据源查询
│   ├── derived.py     # 衍生数据查询
│   ├── evaluation.py  # 评估查询
│   ├── research.py    # 研究数据集查询
│   ├── forward_return_service.py  # 前向收益率服务
│   └── _utils.py      # 查询工具
├── process/            # 编排流程（可调用 query）
│   ├── ingestion.py   # 数据摄取流程
│   ├── materialization.py  # 衍生物化流程
│   ├── quality.py     # 质量校验流程
│   └── strategy.py    # 策略运行流程
├── command/            # CQRS Command（纯写入）
│   ├── ingestion.py   # 摄取命令
│   └── strategy.py    # 策略命令
├── builders/           # 运行时装配（DI 构造）
│   └── strategy.py    # 策略构建器
├── providers.py        # DI Provider 注册
├── config.py           # 数据集配置
└── types.py            # 共享类型 re-export
```

## R8 互斥规则（importlinter 强制）

| 方向 | 规则 |
|------|------|
| query → process | r8-query-no-process ❌ |
| query → builders | r8-query-no-builders ❌ |
| query → command | r8-query-no-command ❌ |
| builders → query | r8-builders-no-query ❌ |
| command → query | r8-command-no-query ❌ |
| command → builders | r8-command-no-builders ❌ |
| process → query | ✅ 允许（编排可调用查询） |
| process ↔ builders | ✅ 允许（双向） |
| command → process | ✅ 允许（委托执行） |

## 测试规范

```
packages/app/
├── src/ditto_app/
└── tests/
    ├── unit/
    └── integration/
```

### 运行测试

```bash
pixi run -e dev pytest packages/app/tests/
```
