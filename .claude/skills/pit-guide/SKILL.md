---
name: pit-guide
description: |
  【必读】Point-in-Time 数据安全指南。
  触发条件: PIT、knowledge_date、回测数据、as-of join、时点数据、未来数据泄露、look-ahead bias、数据查询、历史数据。
  核心规则: knowledge_date 字段必须、closed="left"、T日信号T+1执行、join_asof。
globs:
  - "**/*.py"
---

# PIT 数据安全指南

## 核心概念

**PIT 安全** = 时间点 T 只能用 T 之前已知的数据

---

## knowledge_date

| 数据类型 | knowledge_date |
|----------|----------------|
| 日行情 | trade_date + 1 |
| 财报 | 公告日期 |
| 指数成分 | 生效日期 |

---

## As-Of Join

```python
result = signals.join_asof(
    prices,
    left_on="decision_date",
    right_on="knowledge_date",
    by="code",
    strategy="backward",
)
```

---

## Rolling 安全

```python
# ✅ 正确
pl.col("close").rolling_mean(20, closed="left")

# ❌ 错误（包含当日）
pl.col("close").rolling_mean(20)
```

| closed | 窗口 | 安全 |
|--------|------|------|
| "left" | [T-20, T-1] | ✅ |
| "right" | [T-19, T] | ❌ |

---

## 信号规则

**T日信号 → T+1执行**

```python
Signal(
    generated_at=decision_date,
    execute_at=decision_date + timedelta(days=1),
)
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| rolling 不指定 closed | closed="left" |
| 用 trade_date 查询 | 用 knowledge_date |
| T日信号T日执行 | T+1执行 |
