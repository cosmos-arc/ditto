> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-004: 表达式语法与数据引用设计

**状态**: 已决策（2026-03-04）

---

## 背景

表达式引擎需要统一的语法来引用：
1. 原始数据列（市场行情、基本面、资金流向等）
2. 已计算的特征（技术指标如 RSI、MACD）
3. 已计算的因子（标准化 Alpha 信号）

核心挑战是避免列名冲突、保持可读性、与业界实践一致。

---

## 决策

### 1. 原始数据列：数据集限定语法

```python
# 格式: {dataset}.{column}
market.close           # 行情收盘价
market.volume          # 成交量
fund.pe_ttm            # 基金PE
balance.total_assets   # 资产负债表总资产
income.net_profit      # 利润表净利润
```

**理由**：
- 明确消除歧义，避免多数据集列名冲突
- 符合 SQL `table.column` 习惯
- 支持编译期列存在性校验

### 2. 特征/因子引用：统一 `@` 前缀 + 命名约定

```python
# 特征引用（技术指标、基础特征）
@rsi_14                # RSI(14)
@macd_dif              # MACD DIF 线
@boll_upper_20         # 布林上轨(20)
@volatility_20         # 20日波动率

# 因子引用（Alpha信号，带 alpha_ 前缀）
@alpha_momentum_12m    # 12月动量因子
@alpha_value_pe        # 价值因子
@alpha_001             # WorldQuant Alpha001
@alpha_reversal_5d     # 5日反转因子
```

**命名约定**：

| 类型 | 命名规则 | 示例 |
|------|---------|------|
| 技术指标 | `{indicator}_{params}` | `rsi_14`, `macd_dif`, `atr_14` |
| 基础特征 | `{domain}_{metric}` | `fund_size`, `liquidity_20d` |
| 因子 | `alpha_{style}_{window}` 或 `alpha_{seq}` | `alpha_momentum_12m`, `alpha_001` |

### 3. 字面量与运算符

```python
# 数值字面量
42                     # 整数
3.14                   # 浮点数
-0.5                   # 负数

# 算术运算符
market.close * 1.02    # 乘法
market.close + market.high  # 加法
(market.high - market.low) / market.close  # 除法

# 比较运算符
market.close > market.open  # 大于
market.volume >= 1000000    # 大于等于

# 逻辑运算符
and  or  not           # 逻辑与、或、非
```

---

## 完整表达式示例

```python
# 简单因子
ts_rank(market.close, 20)

# 复合表达式
cs_rank(ts_delta(market.close, 5)) + @rsi_14

# 带特征依赖的因子
cs_zscore(@alpha_momentum_12m + @alpha_value_pe)

# Alpha101 风格
cs_rank(ts_argmax(power(if_else(market.returns < 0, market.stddev, market.close), 2), 5)) - 0.5
```

---

## 语法定义（EBNF）

```ebnf
expression     = term (("+" | "-") term)*
term           = factor (("*" | "/") factor)*
factor         = unary | primary
unary          = ("-" | "not") factor
primary        = literal
               | column_ref
               | feature_ref
               | call_expr
               | "(" expression ")"

column_ref     = identifier "." identifier    # dataset.column
feature_ref    = "@" identifier                # @feature_id
call_expr      = identifier "(" arg_list? ")"
arg_list       = expression ("," expression)*
identifier     = [a-zA-Z_][a-zA-Z0-9_]*
literal        = NUMBER | STRING
```

---

## 编译期校验

1. 列引用存在性检查（基于 Catalog schema）
2. 特征/因子存在性检查（基于 derived_spec 表）
3. 算子签名匹配
4. 类型兼容性检查

---

## 业界对标

| 平台 | 列引用 | 特征引用 | Ditto 选择 |
|------|--------|---------|-----------|
| WorldQuant Brain | `close` | 不支持 | ✗ 列名冲突风险 |
| Qlib | `$close` | 不支持 | ⚠️ 符号负担 |
| BigQuant | `close` | `factor_xxx` | ✓ 类似 |
| Feathr | `entity.feature` | `@feature` | ✓ 类似 |
