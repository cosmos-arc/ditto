# Core 层架构规范

## 定位

Core 层是 **Domain Layer（领域层）**，包含量化系统的核心业务逻辑、领域知识和算法。

**核心原则**：
- 纯业务逻辑，无 I/O 操作
- 无状态计算，可独立测试
- 依赖 DataHub 获取数据，依赖 Infra 获取基础设施

## 模块结构

```
ditto_core/
├── quality/           # 数据质量引擎（已实现）
│   ├── checkers/      # DQ 检查器
│   │   ├── technical.py    # L1 技术检查
│   │   ├── business.py     # L2 业务检查
│   │   ├── statistical.py  # L3 统计检查
│   │   └── cross_source.py # 跨源检查
│   ├── engine.py      # DQ 引擎
│   ├── spec.py        # 规则配置模型
│   ├── config.py      # DQ 配置
│   ├── report.py      # 检查报告
│   └── severity.py    # 严重程度
├── engine/            # 核心引擎（待实现）
├── portfolio/         # 组合管理（待实现）
└── strategy/          # 策略框架（待实现）
```

## 子领域规范

### Quality（数据质量）

**职责**：检查规则算法（OHLC、涨跌停、成交量异常）

| 检查层级 | 职责 | 示例 |
|---------|------|------|
| L1 Technical | 技术校验 | 非空、唯一、外键 |
| L2 Business | 业务规则 | OHLC 一致性、涨跌幅限制 |
| L3 Statistical | 统计异常 | Z-score、完整性 |
| Cross Source | 跨源校验 | 价格与指数对齐 |

**关键点**：
- DQ 是量化业务规则，不是通用技术约束
- 配置文件（YAML）定义业务规则
- 检查逻辑在 Core，编排流程在 Port，结果存储在 DataHub

### Factor（因子计算）

**职责**：因子计算算法（RS、动量、波动率）

**关键点**：
- 计算逻辑在 Core（纯函数、无状态）
- 编排流程在 Application（获取数据、调用计算、保存结果）
- 存储在 DataHub（parquet 文件）

### Strategy（策略）

**职责**：策略逻辑、信号生成

**关键点**：
- 策略基类在 Core
- 信号生成逻辑在 Core
- 交易执行编排在 Port

### Risk（风险管理）

**职责**：风险模型（回撤检测、风险度量）

**关键点**：
- 风险计算逻辑在 Core
- 告警编排在 Port
- 指标存储在 DataHub

## 依赖规则

```
┌─────────────────────────────────────┐
│  Core 可依赖                        │
│  core → datahub ✅                  │
│  core → infra ✅                    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Core 禁止依赖                      │
│  core → port ❌                     │
└─────────────────────────────────────┘
```

## 代码规范

### 纯函数优先

```python
# ✅ 正确：纯函数，无副作用
def calculate_momentum(prices: pl.DataFrame, window: int) -> pl.Series:
    return prices["close"].pct_change(window)

# ❌ 错误：包含 I/O 操作
def calculate_momentum_and_save(prices: pl.DataFrame) -> None:
    result = prices["close"].pct_change(20)
    save_to_parquet(result, "momentum.parquet")  # 不应在 Core 层
```

### 无状态设计

```python
# ✅ 正确：无状态，依赖注入
class QualityEngine:
    def __init__(self, checkers: list[Checker]):
        self._checkers = checkers

    def check(self, data: pl.DataFrame) -> list[CheckResult]:
        return [c.check(data) for c in self._checkers]

# ❌ 错误：有状态，持有数据源
class QualityEngine:
    def __init__(self):
        self._store = BarsStore(...)  # 不应持有 Store
```

## 测试规范

### 测试文件位置

```
packages/core/
├── src/ditto_core/
└── tests/
    ├── unit/           # 单元测试
    │   └── quality/
    └── integration/    # 集成测试
```

### 运行测试

```bash
pixi run -e dev pytest packages/core/tests/
```

## 判断决策树

```
问题：这个组件应该放在 Core 层吗？

1. 是否是业务逻辑/规则？
   YES → Core 层 ✅

2. 是否是纯计算/算法？
   YES → Core 层 ✅

3. 是否需要访问数据库/文件？
   YES → DataHub 层 ❌

4. 是否是流程编排？
   YES → Port 层 ❌
```
