# 原型版本管理（git tag）

> **每次 review 前，通过 git tag 快照当前状态。回退和对比均依赖 git 原生能力。**
> **Tag 按任务名分组，已完成任务可安全清理，不同任务互不干扰。**

---

## 任务名与 Tag 命名

- **Tag 格式**: `review/<task>/round-{N}`（按任务名分组，各任务独立递增）
- **完成标记**: `review/<task>/done`（达标后创建，含最终分数的 annotated tag）
- **任务名来源**: 优先 `--task` 参数，否则从文件名自动映射
  - `page-cross-market.html` → `cross-market`
  - `page-home.html` → `home`
  - `page-market-pulse.html` → `market-pulse`

```
示例：
review/cross-market/round-1
review/cross-market/round-2
review/cross-market/done          ← 已达标
review/home/round-1               ← 不同任务，独立轮次
review/home/round-2
```

---

## Phase 0: VERSION 工作流

1. **确定任务名**
   - 有 --task 参数 → 用参数值
   - 无 --task → 从文件名映射（去 page- 前缀和 .html 后缀）

2. **检查任务状态**
   - `git tag -l 'review/<task>/done'` 存在 → 已完成任务
     - [人工模式] 提示用户：任务已达标，是否重新迭代？
     - [--iterate] 自动提示选择：续接 / 新任务名 / 退出
   - 不存在 → 进行中或新任务

3. **确定轮次号**
   - `git tag -l 'review/<task>/round-*'` 有结果 → N = max(round-N) + 1
   - 无结果 → N = 1（新任务）

4. `git add` 目标文件 → `git commit -m "docs(review): <task> round-{N} pre-review snapshot"`
5. `git tag review/<task>/round-{N}`
6. 后续所有修改直接在原文件上进行

---

## 回退操作

```bash
# 回退 cross-market 任务 round-2 的状态
git checkout review/cross-market/round-2 -- page-cross-market.html
```

---

## 版本对比

```bash
# 查看 cross-market 任务 round-1 → round-2 的变更
git diff review/cross-market/round-1..review/cross-market/round-2 -- page-cross-market.html

# 查看变更摘要
git log review/cross-market/round-1..review/cross-market/round-2 --oneline -- page-cross-market.html
```

---

## 任务完成与清理

```bash
# 达标后自动创建 done 标记（Phase 8 中执行）
git tag -a review/cross-market/done -m "task completed: score 8.8/10, 4 rounds"

# 手动清理已完成任务的所有 tag
git tag -l 'review/cross-market/*' | xargs git tag -d

# 或使用 --cleanup 参数
/ditto-design-cycle --cleanup cross-market
```

---

## 约束

- Tag 命名：`review/<task>/round-{N}`（按任务分组，各任务独立递增）
- 旧格式 `review/round-{N}` 视为 legacy，Phase 0 忽略，保留不动
- 活跃文件是唯一被 review 修改的文件
- 审查报告标注对应 tag，如 `Tag: review/cross-market/round-2`
- 不保存 HTML 副本、不自动截图到磁盘
