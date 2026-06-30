# 能力包架构后续优化设计

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 修复能力包架构重构遗留的基础设施问题，推进 Strategy/Portfolio 解耦至业界最佳实践。

**背景：** Task 0-18 完成后，包结构已迁移到位（arch-check/type 通过），但存在测试基础设施问题、依赖设计耦合和覆盖率不足。

**参考：** LEAN Algorithm Framework、Backtrader Cerebro、Clean Architecture、Hexagonal Architecture

---

## 一、测试基础设施修复

### 问题 1.1：`tests/unit/` 包名冲突

**根因：** 12 个包都有 `tests/unit/__init__.py`，使 `unit` 成为 Python 包。pytest 并行收集时产生 `ModuleNotFoundError: No module named 'unit.conftest'`，导致 60 个 collection error。

**方案：** 删除所有 `packages/*/tests/unit/__init__.py`，以及子目录中未被显式 import 的 `__init__.py`。

**验证：**
```bash
pixi run -e dev test --fast   # 60 errors → 0 errors
pixi run -e dev type          # 仍然通过
```

### 问题 1.2：Application 旧 `command/` 测试目录

**现状：** `packages/application/tests/unit/command/`（7 个测试文件）已经 import `ditto_application.commands.*`（复数），但目录名是旧的单数。

**方案：** `git mv` 重命名为 `commands/`。

---

## 二、Strategy → Portfolio 解耦

### 2.1 设计原则（业界共识）

参考 LEAN Algorithm Framework 的 Alpha → PortfolioConstruction 模式：

1. **Strategy 只产信号**：Alpha pipeline 产出 `Signal`（方向 + 置信度 + 建议权重），不知道分配算法
2. **Portfolio 独立决定分配**：WeightAllocator（EqualWeight/RiskParity/ScoreWeight）由 application 层注入
3. **约束是 Portfolio 关注点**：MaxWeightConstraint/MaxPositionsConstraint 等由 application 层编排，不在 StrategySpec 中
4. **OrderType 是共享原语**：放入 kernel，被 execution/portfolio/strategy 共同消费

**依赖方向：**

```
              kernel (Signal, OrderType, WeightAllocator Protocol)
              /         \
         strategy      portfolio
              \         /
              application (编排: Template + Allocator + Constraints = Recipe)
```

### 2.2 具体改动

#### Step 1: OrderType 移入 kernel

- **从** `ditto_portfolio.accounting.order_book.OrderType`
- **到** `ditto_kernel.order.OrderType`
- portfolio 中的 `OrderType` 改为 `from ditto_kernel.order import OrderType`
- strategy/specs.py 的 import 改为 `from ditto_kernel.order import OrderType`

kernel 准入验证：
- ✅ 跨 2+ 包（portfolio、execution、strategy 均消费）
- ✅ 零业务行为（4 值 StrEnum）
- ✅ 稳定（订单类型极少变更）
- ✅ 零外部依赖
- ✅ 纯值语义

#### Step 2: 从 StrategySpec 分离 ConstraintSpec

- `ConstraintSpec` 从 `ditto_strategy.alpha.specs` 移到 `ditto_application.execution_dto`（或新的 `recipe.py`）
- `StrategySpec.constraints` 字段删除
- application 层的 Recipe 定义为 `(StrategySpec, AllocatorConfig, Constraints)`

#### Step 3: Strategy Templates 移除 allocation/constraints 导入

模板只定义 alpha pipeline stages：
- UniverseStage → SignalStage → ScoringStage → SelectionStage → FilteringStage → RegimeStage

分配和约束由 application 在运行时注入：
```python
# application 层编排
recipe = StrategyRecipe(
    template=build_etf_rotation_pipeline(),
    allocator=EqualWeightAllocator(),
    constraints=[MaxWeightConstraint(max_weight=0.25)],
    cost_model=CostModelSpec(commission_rate=0.0003),
)
```

#### Step 4: WeightAllocator Protocol 考虑放入 kernel

如果 strategy templates 需要引用 allocator Protocol（而非具体实现），将 `WeightAllocator` Protocol 移入 kernel。策略模板通过 Protocol 消费，不依赖 portfolio 的具体实现类。

条件：
- 如果模板在构建 TargetPortfolio 时需要调用 allocator → 放入 kernel
- 如果分配完全由 application 层在 pipeline 外部完成 → 不需要放入 kernel

**判断依据：** 在 LEAN 中，PortfolioConstructionModel 接口定义在 Common 中。对标到 Ditto，WeightAllocator Protocol 应在 kernel 中。

### 2.3 阶段划分

| Phase | 改动 | 影响范围 |
|-------|------|---------|
| **P1** | OrderType → kernel | kernel, portfolio, strategy, execution, specs |
| **P2** | WeightAllocator Protocol → kernel | kernel, portfolio, strategy templates |
| **P3** | ConstraintSpec 从 StrategySpec 分离 | strategy, application, specs, templates |
| **P4** | Templates 移除 allocation/constraints 硬编码 | strategy/templates, application/recipes |

P1 是独立的，可以先行。P2-P4 有依赖关系，需要一起设计。

---

## 三、Strategy → Data 存储层解耦

### 3.1 现状

`strategy/storage/sqlite/services/instrument_rule_provider.py` 直接导入：
- `ditto_data.storage.metadata.fee_schedule_reader.FeeScheduleReader`
- `ditto_data.storage.metadata.fee_schedule_writer.FeeScheduleWriter`
- `ditto_data.storage.metadata.trading_rule_reader.TradingRuleReader`
- `ditto_data.storage.metadata.trading_rule_writer.TradingRuleWriter`

同时，kernel 中已有：
- `InstrumentRuleProvider` Protocol（`kernel.trading`）
- `FeeSchedule`、`TradingRuleSet`、`InstrumentDefinition` 值对象

### 3.2 方案：Port/Adapter 模式

1. **Data 包提供 Adapter**：在 `ditto_data` 中创建 `DataBackedInstrumentRuleProvider`，实现 kernel 的 `InstrumentRuleProvider` Protocol
2. **Application 层组装**：通过 DI 将 Data adapter 注入到需要 rule_provider 的 consumer
3. **删除 Strategy 中的旧实现**：`strategy/storage/sqlite/services/instrument_rule_provider.py` 删除，其功能由 Data 的 adapter 承担

### 3.3 注意事项

- strategy 中的 `DefinitionRecord` 是 kernel `InstrumentDefinition` 的重复，应删除
- FeeScheduleRecord → FeeSchedule 的映射逻辑移入 Data adapter
- 检查 `strategy/storage/sqlite/` 中其他服务是否有类似的 Data 存储层直接导入

---

## 四、覆盖率提升

### 4.1 当前状态

| 包 | 覆盖率 | 主要缺口 |
|----|--------|---------|
| platform | 53% | observability（logging/metrics/tracing） |
| features | 51% | expression engine / materialization |
| portfolio | 55% | accounting.order_book / rebalancing |
| risk | 50% | pre_trade / post_trade |

### 4.2 策略

配合 Strategy→Portfolio 解耦重构一起补充：
- P1（OrderType 迁移）不需要额外测试
- P2-P4 重构时，被改动的模板/portfolio/application 测试顺带补覆盖率
- 独立补充 risk 和 platform 的测试

---

## 五、执行优先级

```
Phase 1: 测试基础设施修复
  1.1 删除 tests/unit/__init__.py
  1.2 重命名 command/ → commands/
  → 验证: pixi run -e dev check 全绿

Phase 2: OrderType → kernel
  2.1 OrderType 移入 kernel.order
  2.2 更新所有 consumer imports
  → 验证: type + arch-check + test

Phase 3: Strategy → Data 存储解耦
  3.1 Data 包创建 DataBackedInstrumentRuleProvider
  3.2 Application 层组装
  3.3 删除 Strategy 旧实现
  → 验证: arch-check + test

Phase 4: Strategy → Portfolio 解耦（P2-P4）
  4.1 WeightAllocator Protocol → kernel
  4.2 ConstraintSpec 从 StrategySpec 分离
  4.3 Templates 移除硬编码 allocation/constraints
  4.4 Application 层创建 StrategyRecipe 编排
  → 验证: full CI gate

Phase 5: 覆盖率提升
  5.1 补 portfolio 测试
  5.2 补 risk 测试
  5.3 补 features 测试
  → 验证: 覆盖率 ≥ 80%
```
