# ADR: Kernel trading.py 类型归属决策

> 日期：2026-05-18
> 状态：Accepted
> 范围：`ditto_kernel.trading`

## 背景

`ditto_kernel/trading.py` 包含 A 股交易领域的常量、值对象和 Protocol 定义：

- **常量**：`DEFAULT_COMMISSION_RATE`、`DEFAULT_MIN_COMMISSION`、`DEFAULT_LOT_SIZE`、`DEFAULT_SLIPPAGE_BPS`
- **值对象**：`MarketSnapshot`、`InstrumentDefinition`、`TradingRuleSet`、`FeeSchedule`
- **Protocol**：`FeeModel`、`InstrumentRuleProvider`
- **类型别名**：`InstrumentRules`、`RulesGetter`

当前消费者为 `execution` 和 `backtest` 两个包。部分字段（`is_suspended`、`limit_up`、`limit_down`、`lot_size`）具有 A 股市场特异性。

核心问题：这些类型应该留在 kernel，还是应该下沉到更具体的业务包（如 execution）或抽离为独立的市场微结构包？

## 决策

这些类型保留在 `ditto_kernel.trading`，理由如下：

### 1. 跨包消费

execution 和 backtest 两个包直接消费 `trading.py` 的类型。按照 kernel 准入标准（至少被 2 个业务包消费），满足跨层使用条件。

### 2. 零业务行为

所有值对象均为 `frozen=True` 的 dataclass，不含方法、不含 I/O、不含副作用。Protocol（`FeeModel`、`InstrumentRuleProvider`）仅定义纯接口签名。满足 kernel 零业务行为要求。

### 3. 高稳定性

交易规则（`TradingRuleSet`）、费率结构（`FeeSchedule`）、标的定义（`InstrumentDefinition`）由交易所和监管机构定义，变更频率极低。佣金费率、最低佣金等常量由券商体系决定，不会随业务迭代频繁变更。

### 4. 无外部依赖

仅依赖 `ditto_kernel.identity.InstrumentId` 和 Python 标准库（`dataclasses`、`typing`、`collections.abc`），满足零外部依赖要求。

### 5. 纯值语义

所有数据结构为纯内存值对象，不涉及序列化、持久化或 I/O 操作。

### A 股特定类型的处理

具有 A 股市场特异性的字段（价格涨跌停、停牌标志、最小交易单位）通过 maturity annotation 标注：

```python
# Initial focus: A-share (XSHE/XSHG) market microstructure.
# Fields like is_suspended, limit_up, limit_down are A-share specific.
# Global market extension: subclasses or Protocol-based snapshots for
# markets without price limits or suspension rules.
```

未来扩展到全球市场时，不修改现有 A 股字段，而是通过 Protocol-based snapshot 实现多市场支持。

## 后果

### 正面

- execution 和 backtest 可以直接从 kernel 导入共享类型，无需引入额外依赖
- 值对象和 Protocol 的纯语义确保 kernel 保持薄层定位
- A 股常量集中管理，避免跨包重复定义

### 负面

- 随着新市场（港交所、纽交所等）的加入，kernel 将积累更多市场微结构类型，可能导致 `trading.py` 膨胀
- A 股特有字段（`is_suspended`、`limit_up` 等）对非 A 股市场消费者存在语义冗余

### 缓解措施

当满足以下任一条件时，应将市场微结构类型重组为 kernel 内部的子模块结构：

1. `trading.py` 超过 300 行
2. 新增 2 个以上市场的微结构类型
3. 值对象之间存在市场级多态需求

建议的未来结构：

```
ditto_kernel/
├── markets/
│   ├── _snapshot.py      # MarketSnapshot Protocol + 基础实现
│   ├── _rules.py         # TradingRuleSet / FeeSchedule 基础定义
│   ├── ashare.py         # A 股特有字段和常量
│   └── __init__.py       # barrel
```

## 参考

- `packages/kernel/src/ditto_kernel/trading.py` — 当前实现
- `packages/kernel/AGENTS.md` — Kernel 准入标准和增长控制规则
- `docs/architecture/adr-runtime-spine.md` — Runtime Spine ADR（trading.py 过渡性质相关讨论）
