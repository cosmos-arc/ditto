# 报告模板与雷达图

> 最终报告输出到 `docs/reviews/YYYY-MM-DD-quality-eval.md`

---

## ASCII 雷达图

```
              测试质量
               {t}★
                 |
    代码 {c}★ ──┼── {o}★ 运维
                 |
    架构 {a}★ ──┼── {d}★ 领域
                 |
              工程流程
               {e}★

    综合评分: {total} / 5.0 ★
```

## 加权评分公式

```
weights = {
    "code":   0.20,   # 代码质量 20%
    "arch":   0.25,   # 架构质量 25%
    "test":   0.15,   # 测试质量 15%
    "eng":    0.10,   # 工程流程 10%
    "ops":    0.15,   # 运维质量 15%
    "domain": 0.15,   # 领域特有 15%
}

weighted_score = Σ(results[dim].score × weights[dim])
```

## 报告 Markdown 模板

```markdown
# Ditto 质量评估报告 {date}

> 评估模式: {mode} | 评估时间: {timestamp}

## 综合评分

{radar_chart}

**综合评分: {total_score} / 5.0 ★** (加权)

| 维度 | 评分 | 评级 | 变化 |
|------|------|------|------|
| ① 代码质量 | {c}/5.0 ★ | {c_label} | {c_delta} |
| ② 架构质量 | {a}/5.0 ★ | {a_label} | {a_delta} |
| ③ 测试质量 | {t}/5.0 ★ | {t_label} | {t_delta} |
| ④ 工程流程 | {e}/5.0 ★ | {e_label} | {e_delta} |
| ⑤ 运维质量 | {o}/5.0 ★ | {o_label} | {o_delta} |
| ⑥ 领域特有 | {d}/5.0 ★ | {d_label} | {d_delta} |

## 各维度详情

### ① 代码质量 — {code_rating} ({code_score}★)

| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
{code_findings_table}

### ② 架构质量 — {arch_rating} ({arch_score}★)
{arch_findings_table}

### ③ 测试质量 — {test_rating} ({test_score}★)
{test_findings_table}

### ④ 工程流程 — {eng_rating} ({eng_score}★)
{eng_findings_table}

### ⑤ 运维质量 — {ops_rating} ({ops_score}★)
{ops_findings_table}

### ⑥ 领域特有 — {domain_rating} ({domain_score}★)
{domain_findings_table}

## Top 10 改进项

| # | 维度 | 评价项 | 优先级 | 建议 |
|---|------|--------|--------|------|
{top_10_table}

## 与上次评估对比

| 维度 | 上次 ({prev_date}) | 本次 | 变化 |
|------|-------------------|------|------|
{comparison_table}

## 附录

- 评价框架: docs/plans/2026-06-02-software-quality-evaluation-framework.md
- 基线数据: pixi run -e dev check 结果
```

## 星级 → 标签映射

| 分数范围 | 标签 | 图标 |
|---------|------|------|
| 4.0-5.0 | 优秀 | 🟢 |
| 3.0-3.9 | 合格 | 🟡 |
| 2.0-2.9 | 待改进 | 🟠 |
| 1.0-1.9 | 需改进 | 🔴 |
