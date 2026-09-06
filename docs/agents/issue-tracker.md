# Issue tracker: GitHub

本仓库的 issue 和 spec 记录在 [cosmos-arc/ditto 的 GitHub Issues](https://github.com/cosmos-arc/ditto/issues)，使用 `gh` CLI 操作。

## Conventions

在此仓库的 worktree 内运行 `gh`，由 Git remote 确定目标仓库；在其他目录运行时显式指定 `--repo cosmos-arc/ditto`。

- 创建：`gh issue create --title "..." --body-file <body.md>`。
- 读取：`gh issue view <number> --json number,title,body,labels,comments`。
- 列表：`gh issue list --state open --json number,title,body,labels,comments`，按需添加 `--label` 或调整 `--state`；完整扫描时处理分页或显式设置足够的 `--limit`。
- 评论：`gh issue comment <number> --body-file <comment.md>`。
- 添加或移除标签：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`，标签映射见 [triage-labels.md](triage-labels.md)。
- 关闭：`gh issue close <number>`；需要说明时先发布评论。
- 多行正文先写入文件，再通过 `--body-file` 传入，保留实际换行。

skill 要求 “publish to the issue tracker” 时，创建 GitHub issue；要求 “fetch the relevant ticket” 时，读取该 issue 的正文、标签与评论。

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub 的 issue 与 PR 共用编号。引用只给出 `#number` 且类型不明时，先确认资源类型；PR 使用 `gh pr view <number> --comments` 和 `gh pr diff <number>` 读取。

## Wayfinding operations

供 `wayfinder` 使用：

- **Map**：一个标记为 `wayfinder:map` 的 issue，正文包含 Notes、Decisions-so-far 与 Fog。
- **Child ticket**：每个 ticket 单独建立 issue，标签为 `wayfinder:<type>`，type 为 `research`、`prototype`、`grilling` 或 `task`。用 `gh issue edit <child> --parent <map>` 关联为 GitHub sub-issue；不可用时在 map 中维护 task list，并在 child 正文顶部写 `Part of #<map>`。
- **Blocking**：优先使用 GitHub 原生 issue dependencies。添加阻塞关系用 `gh issue edit <child> --add-blocked-by <blocker-number>`。不可用时在 child 正文顶部写 `Blocked by: #<n>, #<n>`。
- **Frontier**：按 map 顺序遍历其开放 child，选第一个未分配且无开放 blocker 的 ticket；通过 `gh issue view <number> --json state,assignees,subIssues,blockedBy` 读取关系，逐一确认 blocker 已关闭；文本关系同样检查引用的 blocker。
- **Claim**：开始工作前运行 `gh issue edit <number> --add-assignee @me`。
- **Resolve**：评论记录结果，关闭 child，再用 `gh issue edit <map> --body-file <updated-map.md>` 更新 map 的 Decisions-so-far，保留原正文并追加摘要和链接。
