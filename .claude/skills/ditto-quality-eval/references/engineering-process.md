# 维度④：工程流程评估

> 基于 DORA 四+一指标 (2024)、SPACE 框架 (2021)、Google/Microsoft 代码审查标准

---

## DORA 指标（2024 版）

| # | 指标 | 🟢 精英 | 🟡 高 | 🟠 中 | 🔴 低 |
|---|------|---------|-------|-------|-------|
| P1 | **部署频率** | 按需（多次/天） | 周→月 | 月→半年 | > 半年 |
| P2 | **变更前置时间** | < 1 天 | 1天→1周 | 1周→1月 | 1-6月 |
| P3 | **变更失败率** | 0-15% | 16-30% | 31-45% | 46-60% |
| P4 | **恢复时间** | < 1 小时 | < 1 天 | 1天→1周 | 1-6周 |
| P5 | **返工率** (2024 新增) | < 15% | 15-25% | 25-35% | > 35% |

> **注意**：DORA 2024 阈值是聚类分析结果，非固定基准。
> 对量化平台应更关注**变更失败率**和**恢复时间**，而非部署频率。

## 代码审查标准

| # | 评价项 | 权重 | 评价标准 | 检查方法 |
|---|--------|------|---------|---------|
| P6 | **审查覆盖率** | ★★★ | 所有 PR 必须经过审查 | GitHub 规则 |
| P7 | **PR 大小控制** | ★★☆ | 单个 PR < 400 LOC | Git 统计 |
| P8 | **审查响应时间** | ★★☆ | 首次审查 < 24 小时 | GitHub 统计 |
| P9 | **审查质量** | ★★★ | 关注设计/功能/复杂度/测试 | 审查记录 |
| P10 | **审查清单** | ★★☆ | 有结构化审查清单 | CLAUDE.md |

## CI/CD 门禁完整性

| # | 评价项 | 评价标准 |
|---|--------|---------|
| P11 | **Lint 门禁** | ruff 检查通过为硬性要求 |
| P12 | **类型检查门禁** | basedpyright strict 通过 |
| P13 | **测试门禁** | 测试通过 + 覆盖率 ≥ 80% |
| P14 | **架构门禁** | `.importlinter` 通过 |
| P15 | **格式化门禁** | ruff format 检查 |

## 检查命令

```bash
# 最近提交历史
git log --oneline -30 --format="%h %s (%cr)"

# 合并频率（代理部署频率）
git log --oneline --merges --since="1 month ago" | wc -l

# 平均 PR 大小（最近 20 个 merge commit）
git log --oneline -20 --merges --format="%H" | while read h; do
  git diff-tree --no-commit-id --shortstat -r $h 2>/dev/null
done

# CI 配置检查
cat .github/workflows/*.yml 2>/dev/null | grep -E "ruff|pyright|pytest|import-linter" | head -20

# pre-commit 钩子检查
cat .pre-commit-config.yaml | grep -E "id:|name:" | head -20

# 分支策略检查
git branch -r | head -10
```

## 评分规则

- P11-P15（CI 门禁）为硬性项：任一 fail → 整个维度最高 2★
- DORA 指标基于最近 30 天数据估算
- 总分映射到 1-5 星
