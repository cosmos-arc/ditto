# 启动日常开发

执行以下开发启动流程：

## 1. 环境检查

检查 Git 状态：
```bash
git status
git branch --show-current
```

- 如果在功能分支且有未完成工作 → 询问是否继续当前任务
- 如果在 main 分支 → 进入任务选择

## 2. 任务选择

读取并显示当前 Sprint 状态：

1. 读取 `docs/sprints/README.md` 获取当前进度
2. 读取当前活跃的 `docs/sprints/sprint-*.md`
3. 列出所有待完成的 P0/P1 任务，格式如下：

```
📋 当前 Sprint: [Sprint 名称]

P0 任务：
1. [状态] 任务名称 (依赖情况)
2. ...

P1 任务：
3. [状态] 任务名称
...

请选择任务编号，或描述新任务：
```

## 3. 上下文准备

选择任务后：

1. 搜索相关 Plan 文件：`docs/plans/sprint-*/task*-[关键词].md`
2. 搜索相关设计文档：`docs/design/*.md`
3. 展示找到的相关上下文

## 4. 分支准备

```bash
git checkout main
git pull origin main
git checkout -b feat/[任务名称简写]
```

## 5. 开发模式

根据任务情况选择：

**有 Plan 文件或任务清晰**：
- 直接进入 TDD 开发模式
- 先写测试，再实现

**需要设计讨论**：
- 进入 brainstorming 模式
- 分块确认设计
- 生成实施计划

## 6. 输出确认

```
✅ 开发环境已就绪

📌 任务: [任务名称]
🌿 分支: feat/[branch-name]
📄 Plan: [如有]
📋 Sprint: [Sprint 名称]

准备好后输入 "开始" 进入开发...
```

---

**注意**：
- 始终遵循 TDD：先写测试再实现
- 每个功能点完成后运行 `pixi run -e dev ci-check`
- 任务完成后使用 finishing-a-development-branch 流程
