---
alwaysApply: true
---

# 文档规范

## 必须更新的文档

| 触发条件 | 必须更新 |
|----------|----------|
| 新建/修改模块 | `packages/xxx/README.md` |
| 任务状态变更 | `docs/sprints/sprint-XX.md` |
| 复杂任务（L）开始 | `docs/plans/YYYY-MM-DD-name.md` |
| 重大架构决策 | `docs/adr/NNNN-title.md` |

## 状态标记

```
🔄 进行中 → 任务开始时
✅ 完成   → 任务完成时
🚧 阻塞中 → 发现问题时
```

## 完成检查

任何功能开发完成后，必须检查：

- [ ] 模块 README 是否需要更新？
- [ ] Sprint 任务状态是否更新？
- [ ] 是否需要 Plan 文档？
- [ ] 是否有 ADR 需要记录？

## 详细指南

涉及文档编写时，读取 `.claude/skills/docs-guide/SKILL.md`
