---
alwaysApply: true
---

# PIT 安全核心规则

## 必须遵守

1. **knowledge_date 字段**：所有数据表必须包含
2. **closed="left"**：所有 rolling 函数必须显式指定
3. **T日信号→T+1执行**：信号生成日不能执行

## Rolling 函数

```python
# ✅ 正确
pl.col("close").rolling_mean(20, closed="left")

# ❌ 错误
pl.col("close").rolling_mean(20)  # 默认包含当日
```

## 数据查询

```python
# ✅ 正确：使用 knowledge_date
data.filter(pl.col("knowledge_date") <= decision_date)

# ❌ 错误：使用 trade_date
data.filter(pl.col("trade_date") <= decision_date)
```

## 详细指南

涉及 PIT 相关工作时，读取 `.claude/skills/pit-guide/SKILL.md`
