> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-001: TS/CS 嵌套策略

**状态**: 已决策（2026-03-04）

---

## 背景

表达式引擎需要支持时间序列（TS）和横截面（CS）算子的嵌套组合。WorldQuant Alpha101 中约 80% 的因子需要 TS/CS 混合嵌套表达，如：
- `ts_rank(rank(low), 9)` — TS(CS(x))
- `rank(ts_delta(close, 20))` — CS(TS(x))
- `correlation(rank(open), rank(volume), 10)` — TS(CS(x), CS(y))

---

## 决策

采用**自动分层执行 + 语义向上传播**策略：

1. **支持任意嵌套**：允许 `TS(CS(x))`、`CS(TS(x))`、`TS(CS(x), CS(y))` 等任意合法嵌套组合
2. **自动推导属性**：编译期自动计算每个子表达式的 `lookback`、`requires_full_day`、`scope`
3. **向上传播约束**：若子表达式 `requires_full_day=True`，则父表达式继承该约束
4. **分层执行**：引擎自动划分执行阶段，先执行纯 TS 阶段，再执行 CS 阶段

---

## 算子分类

```python
class OperatorCategory(Enum):
    TS = "time_series"      # 时间序列操作，group by instrument
    CS = "cross_sectional"  # 截面操作，group by date
    SCALAR = "scalar"       # 标量操作（abs, log, +, -, *, /）
```

---

## 编译期规则

| 规则 | 处理方式 | 说明 |
|------|---------|------|
| CS(CS(x)) | 警告 | 冗余但无害，如 `rank(rank(x))` |
| TS(CS(x)) | 正常 | requires_full_day=True 向上传播 |
| CS(TS(x)) | 正常 | requires_full_day=True |
| DAG 深度 > 10 | 警告 | 避免过于复杂的表达式 |

---

## 增量计算影响

- 若表达式任意子表达式 `requires_full_day=True`，则增量重算时需整日完整数据
- lookback 计算考虑所有 TS 算子的窗口需求

---

## 业界对标

| 平台 | 策略 | Ditto 选择 |
|------|------|-----------|
| DolphinDB | 显式 `context by` 分组 | 类似，但自动推导 |
| Qlib | 仅 TS，CS 后处理 | ✗ 表达能力不足 |
| BigQuant | 自动分层执行 | ✓ 采用此方案 |
| WorldQuant Brain | 任意嵌套 | ✓ 兼容 |

---

## 实现路径

- **Phase 0**：支持自由嵌套 + 编译期属性推导
- **Phase 1**：引入显式阶段划分优化
- **Phase 2**：阶段间并行执行
