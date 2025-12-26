# 启动日常开发

> **用法**: `/start-dev [任务名称或编号]`
>
> 示例：
> - `/start-dev` - 交互式选择任务
> - `/start-dev Task 4` - 直接指定任务
> - `/start-dev datahub-facade` - 按关键词搜索

---

## 执行流程

### 1. 环境检查

检查 Git 状态：
```bash
git status
git branch --show-current
```

**判断逻辑**：
- 如果在功能分支且有未提交工作 → 询问是否继续当前任务
- 如果在 main 分支 → 进入任务选择/创建分支

---

### 2. 任务选择

#### 2.1 用户提供了任务名

直接使用提供的任务名，跳过交互选择。

#### 2.2 用户未提供任务名（交互模式）

读取并显示当前 Sprint 状态：

1. 读取 `docs/sprints/README.md` 获取当前进度
2. 读取当前活跃的 `docs/sprints/sprint-*.md`
3. 列出所有待完成的 P0/P1 任务，格式如下：

```
📋 当前 Sprint: [Sprint 名称]

P0 任务：
- [ ] Task 4: DataHub（Facade）
  依赖: Runtime Layer, Store Layer, Repositories ✅

P1 任务：
- [ ] Task 5: 数据写入管道
  依赖: Task 4

请输入任务编号/名称，或描述新任务：
```

---

### 3. 上下文准备

选择任务后：

1. **搜索相关文档**：
   - Plan 文件：`docs/plans/sprint-*/task*-[关键词].md`
   - 设计文档：`docs/design/*.md`
   - 领域规范：`.claude/rules/domain/*.md`

2. **展示找到的相关上下文**

---

### 4. 分支准备

```bash
# 确保在最新 main
git checkout main
git pull origin main

# 创建功能分支
git checkout -b feat/[任务名称-kebab-case]
```

**分支命名规范**：
- 功能: `feat/datahub-facade`
- 修复: `fix/import-error`
- 重构: `refactor/engine-cleanup`

---

### 5. 🎯 Superpowers 工作流启动

> **重要**: 严格遵循以下技能激活顺序

#### 5.1 设计阶段 (MANDATORY)

```
使用 Skill 工具调用: superpowers:brainstorming
```

- 交互式设计细化
- 边界条件讨论
- 方案确认

**检查点**：
- [ ] 需求已充分讨论
- [ ] 设计方案已确认
- [ ] 边界条件已明确

#### 5.2 计划阶段 (MANDATORY)

```
使用 Skill 工具调用: superpowers:writing-plans
```

- 生成详细实施计划
- 强调 TDD/YAGNI/DRY
- 复杂任务保存到 `docs/plans/`

**检查点**：
- [ ] 计划已生成
- [ ] 用户已确认计划

#### 5.3 执行阶段 (MANDATORY)

```
使用 Skill 工具调用: superpowers:executing-plans
```

每个子任务遵循 TDD：
- RED: 写测试，观察失败
- GREEN: 写最少代码通过
- REFACTOR: 优化重构
- **COMMIT: 每个循环独立提交**

#### 5.4 Git 提交粒度提醒

**❌ 禁止**: 单个大提交包含整个功能
**✅ 正确**: 每个 TDD 循环独立提交

```bash
# 正确的提交序列
git commit -m "test(sql_engine): add test skeleton"              # RED
git commit -m "feat(sql_engine): implement __init__"             # GREEN
git commit -m "feat(sql_engine): implement _register_views"      # GREEN
git commit -m "refactor(sql_engine): extract view method"        # REFACTOR
```

#### 5.5 审查阶段 (任务间隙)

```
使用 Skill 工具调用: superpowers:requesting-code-review
```

- 对照计划审查实现
- 按严重性报告问题

#### 5.6 完成阶段 (MANDATORY)

```
使用 Skill 工具调用: superpowers:finishing-a-development-branch
```

- verification-before-completion
- 提供选项: PR / 本地合并 / 保留 / 丢弃

---

### 6. 输出确认

```
✅ 开发环境已就绪

📌 任务: [任务名称]
🌿 分支: feat/[branch-name]
📄 Plan: [如有]
📋 Sprint: [Sprint 名称]

🎯 Superpowers 工作流:
  1. brainstorming    → 设计确认
  2. writing-plans    → 生成计划
  3. executing-plans  → TDD 执行
  4. code-review      → 质量检查
  5. finishing        → 完成分支

⚠️  Git 提交粒度: 每个 TDD 循环独立提交

准备好后输入 "开始" 进入开发...
```

---

## 快速参考

### TDD 循环

```bash
# RED
git commit -m "test(scope): add test for xxx"

# GREEN
git commit -m "feat(scope): implement xxx"

# REFACTOR
git commit -m "refactor(scope): improve xxx"
```

### 质量检查

```bash
# 开发过程中定期运行
pixi run -e dev lint
pixi run -e dev typecheck
pixi run -e dev test-unit

# 提交前必须全部通过
pixi run -e dev ci-check
```

---

## 常见问题

### Q: 任务需要跨多个 Session 怎么办？

A: 将详细计划保存到 `docs/plans/sprint-XX/task-name.md`，下次恢复上下文。

### Q: 如何确保提交粒度合理？

A: 每个 TDD 循环（RED→GREEN→REFACTOR）独立提交，不要批量提交。

### Q: 什么时候使用 brainstorming？

A: 用户描述需求时自动激活，或主动使用 Skill 工具调用。

---

**核心原则**：
1. **TDD 强制执行**: 先写测试，再实现
2. **小步提交**: 每个 TDD 循环独立提交
3. **技能驱动**: Superpowers 自动激活，确保流程遵循
4. **质量第一**: ci-check 全部通过才能合入
