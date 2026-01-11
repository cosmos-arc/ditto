---
paths: packages/datahub/**/*.py
---

# 数据层 & PIT 安全

## PIT 核心原则

**时间点 T 只能用 T 之前已知的数据**

## knowledge_date 规则

| 数据类型 | knowledge_date |
|----------|----------------|
| 日行情 | trade_date + 1 |
| 财报 | 公告日期 |
| 指数成分 | 生效日期 |

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

## Rolling 安全

```python
# ✅ 正确 - 不包含当日
pl.col("close").rolling_mean(20, closed="left")

# ❌ 错误 - 包含当日（未来泄露）
pl.col("close").rolling_mean(20)
```

| closed | 窗口 | 安全 |
|--------|------|------|
| "left" | [T-20, T-1] | ✅ |
| "right" | [T-19, T] | ❌ |

## 信号规则

**T日信号 → T+1执行**

```python
Signal(
    generated_at=decision_date,
    execute_at=decision_date + timedelta(days=1),
)
```

## 禁止

| 禁止 | 替代 |
|------|------|
| 用 trade_date 查询 | 用 knowledge_date |
| T日信号T日执行 | T+1执行 |
| rolling 不指定 closed | closed="left" |

## 知识日期

| ✅ 正确 | ❌ 错误 |
|---------|---------|
| hub.bars.get(auto_knowledge_date=True) | 手动计算 trade_date + 1 |
| @traced("data.read") | 无追踪装饰器 |

## 测试标记

| 测试类型 | 标记 | 运行命令 |
|----------|------|----------|
| PIT 验证 | @pytest.mark.pit | pytest -m pit |
| 数据摄入 | @pytest.mark.ingestion | pytest -m ingestion |
| 集成测试 | @pytest.mark.integration | pytest -m integration |
