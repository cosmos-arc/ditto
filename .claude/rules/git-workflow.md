# Git 工作流规范

> Claude Code 必须遵循的 Git 最佳实践

---

## 分支策略

### 分支创建

```bash
# 始终从最新 main 创建
git checkout main
git pull origin main
git checkout -b feat/task-name
```

### 分支命名

```
feat/xxx     # 新功能
fix/xxx      # Bug 修复
refactor/xxx # 重构
docs/xxx     # 文档
test/xxx     # 测试
ci/xxx       # CI/CD
```

### 分支生命周期

```
创建 → 开发 → PR → 合并 → 删除

分支存活时间不超过 3 天（理想情况）
```

---

## Commit 规范

### Commit 粒度

| 何时 Commit | 说明 |
|-------------|------|
| ✅ 完成一个独立功能点 | 如：完成一个函数实现 |
| ✅ 测试通过后 | 红→绿→重构 的每个阶段 |
| ✅ 重构完成后 | 行为不变但代码改善 |
| ✅ 修复一个 Bug | 一个 Bug 一个 Commit |
| ❌ 写到一半 | 不完整的代码不 commit |
| ❌ 批量修改 | 不要把多个不相关改动混在一起 |

### Commit Message 格式

```bash
# 格式
<type>(<scope>): <description>

# 示例
feat(factor): implement momentum factor calculation
fix(datahub): resolve SID allocation race condition
test(risk): add kill switch boundary tests
refactor(engine): extract common validation logic
docs(readme): update API documentation
```

### Type 清单

| Type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `test` | 测试相关 |
| `refactor` | 重构（不改变行为） |
| `docs` | 文档 |
| `chore` | 杂项（依赖更新等） |
| `ci` | CI/CD 相关 |

### Commit 前检查

```bash
# 每次 commit 前运行
pixi run -e dev lint
pixi run -e dev typecheck

# 提交
git add .
git commit -m "feat(scope): description"
```

---

## Push 策略

### 何时 Push

| 场景 | 策略 |
|------|------|
| 完成一个子任务 | ✅ 推荐 Push |
| 一天工作结束 | ✅ 必须 Push（备份） |
| 需要 CI 验证 | ✅ Push 触发 CI |
| WIP 代码 | ⚠️ 可以 Push，但标记 Draft PR |

### Push 命令

```bash
# 首次推送
git push -u origin feat/task-name

# 后续推送
git push
```

---

## PR 规范

### PR 大小控制

| 大小 | 行数 | 建议 |
|------|------|------|
| ✅ Small | < 200 行 | 理想大小 |
| ⚠️ Medium | 200-400 行 | 可接受 |
| ❌ Large | > 400 行 | 考虑拆分 |

### PR 创建时机

```
功能开发中（WIP）→ Draft PR
功能完成 + CI 通过 → Ready for Review
```

### PR 描述模板

```markdown
## 变更类型
- [x] feat: 新功能

## 变更描述
简要描述

## DoD 检查
- [x] ci-check 通过
- [x] 测试覆盖达标
```

---

## 分支同步

### 当 main 有更新时

```bash
# 方式1：Rebase（推荐，保持线性历史）
git fetch origin
git rebase origin/main

# 如果有冲突
git status                    # 查看冲突文件
# 手动解决冲突
git add .
git rebase --continue

# 方式2：Merge（简单但历史复杂）
git fetch origin
git merge origin/main
```

### 冲突处理原则

1. **理解冲突原因**：先看两边改了什么
2. **保守处理**：不确定时询问用户
3. **测试验证**：解决后必须运行测试
4. **记录说明**：commit message 说明冲突解决

```bash
# 冲突解决后
git add .
git rebase --continue  # 或 git commit
pixi run -e dev test-unit  # 验证
```

---

## 特殊场景

### 撤销未提交的更改

```bash
# 撤销单个文件
git checkout -- path/to/file

# 撤销所有更改
git checkout -- .

# 保留更改但取消暂存
git reset HEAD
```

### 修改最近的 Commit

```bash
# 修改 message
git commit --amend -m "new message"

# 添加遗漏的文件
git add forgotten_file
git commit --amend --no-edit
```

### 在错误分支上开发了

```bash
# 保存当前更改
git stash

# 切换到正确分支（或创建新分支）
git checkout -b feat/correct-branch

# 恢复更改
git stash pop
```

### 需要临时切换任务

```bash
# 保存当前工作
git stash save "WIP: feature description"

# 切换分支处理其他事情
git checkout other-branch
# ... 工作 ...

# 回来继续
git checkout original-branch
git stash pop
```

---

## 禁止操作

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| `git push --force` 到 main | 破坏历史 | 永远不要 |
| `git push --force` 到功能分支（已有 PR） | 影响 Review | 用 `--force-with-lease` |
| 直接 commit 到 main | 绕过 CI/Review | 通过 PR |
| `--no-verify` | 跳过 hooks | 修复问题 |
| 提交敏感信息 | 安全风险 | 用 .env + .gitignore |

---

## 检查清单

### 开始开发前
- [ ] `git checkout main && git pull`
- [ ] `git checkout -b feat/task-name`
- [ ] 确认不在 main 分支

### 每次 Commit 前
- [ ] `pixi run -e dev lint` 通过
- [ ] `git diff --staged` 检查改动
- [ ] Commit message 符合规范

### 创建 PR 前
- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 分支已同步最新 main
- [ ] PR 大小合理（< 400 行）

### 合并后
- [ ] `git checkout main && git pull`
- [ ] `git branch -d feat/task-name`
