# 设计审查版本管理：从 .versions/ 迁移到 git tag

**日期**: 2026-03-30
**状态**: 已采纳

## 背景

审查流程中的 `.versions/` 快照系统存在以下问题：
1. HTML 快照脱离原目录结构后样式丢失（依赖 `../shared/tokens-base.css` 等相对路径）
2. Chrome MCP 截图不稳定（有时截的状态不对、样式不完整）
3. `.versions/` 目录膨胀（单页 2.5MB，含大量命名混乱的中间截图）
4. CHANGELOG.md 与 git log 功能重复

## 决策

**用 git tag 替代 `.versions/` 快照系统。**

### 版本管理

- 每轮审查前：`git add` → `git commit` → `git tag review/round-{N}`
- 回退：`git checkout review/round-{N} -- <file>`
- 对比：`git diff review/round-1..review/round-2 -- <file>`
- CHANGELOG：用 `git log tag1..tag2` 替代

### 截图

- 从审查流程中移除自动截图
- 需要视觉对比时在浏览器实时查看，不存盘

### 审查报告

- 保留在 `docs/reviews/`（决策上下文有价值，git log 无法重建）
- 报告内标注对应 tag，如 `Tag: review/round-2`
- 去掉 `.versions/` 路径引用

### 清理

- 删除 `prototype/style-b-graphite-studio/.versions/` 整个目录
- 修改 `ditto-design-review.md` 的版本管理章节和 Phase 0/5/7

## 受影响文件

| 文件 | 变更 |
|------|------|
| `.claude/commands/ditto-design-review.md` | 重写版本管理章节 + Phase 0/5/7 |
| `prototype/style-b-graphite-studio/.versions/` | 删除整个目录 |
| `docs/reviews/2026-03-29-product-review-cross-market.md` | 更新版本信息引用 |
| `docs/reviews/2026-03-30-product-review-cross-market.md` | 更新版本信息引用 |
