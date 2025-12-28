---
name: docs-guide
description: |
  【必读】文档规范指南。
  触发条件: README、Sprint、ADR、Plan、文档、进度更新、架构决策、任务状态、模块文档。
  核心规则: 模块README必须更新、Sprint状态同步、复杂任务需Plan、架构决策需ADR。
globs:
  - "**/*.md"
  - "**/docs/**/*"
---

# 文档规范指南

## 文档类型速查

| 类型 | 路径 | 触发条件 |
|------|------|----------|
| 模块 README | `packages/xxx/README.md` | 新建/修改模块 |
| Sprint 进度 | `docs/sprints/sprint-XX.md` | 任务状态变更 |
| Plan 文档 | `docs/plans/YYYY-MM-DD-name.md` | 复杂任务开始 |
| ADR | `docs/adr/NNNN-title.md` | 架构决策 |

---

## 1. 模块 README 模板

```markdown
# 模块名称

## 功能概述
1-2 句话描述模块功能

## 核心接口
| 类/函数 | 描述 |
|---------|------|
| ClassName | 类功能描述 |
| function_name() | 函数功能描述 |

## 使用示例
\`\`\`python
# 简洁的使用示例
\`\`\`

## 设计决策
- 引用相关的 ADR

## 相关文档
- 链接到相关设计文档
```

---

## 2. Sprint 进度模板

### 状态标记

```
🔄 进行中  ← 任务开始时
✅ 完成    ← 任务完成时
🚧 阻塞中  ← 发现问题时
⏳ 待开始  ← 默认状态
```

### 更新示例

```markdown
| Task | 描述 | 状态 |
|------|------|------|
| 1.1 | 实现数据质量引擎 | 🔄 进行中 |
| 1.2 | 添加 PIT 验证 | ✅ 完成 |
| 1.3 | 集成 Prefect | 🚧 阻塞中 |
```

---

## 3. Plan 文档模板

### 命名规范

```
docs/plans/YYYY-MM-DD-sprintN-taskM-name.md

示例：
docs/plans/2025-01-15-sprint2-task1-dq-engine.md
```

### 模板

```markdown
# 任务名称

## 目标
1-2 句话描述

## 涉及文件
- `packages/core/src/xxx.py`
- `packages/core/tests/test_xxx.py`

## TDD 计划

### Cycle 1: 基础功能
1. RED: 写 `test_xxx_basic` 测试
2. GREEN: 实现最小功能
3. REFACTOR: 提取公共逻辑

### Cycle 2: 边界处理
1. RED: 写边界测试
2. GREEN: 添加边界处理
3. REFACTOR: 优化错误消息

## 验收标准
- [ ] 所有测试通过
- [ ] 类型检查通过
- [ ] 文档已更新

## 涉及 Skills
- polars-guide
- pit-guide
- engine-template
```

---

## 4. ADR 模板

### 命名规范

```
docs/adr/NNNN-title.md

示例：
docs/adr/0004-dq-three-tier-architecture.md
```

### 模板

```markdown
# NNNN - 标题

**状态**：Accepted

**日期**：YYYY-MM-DD

## 背景
为什么要做这个决策？问题是什么？

## 决策
我们选择什么方案？

## 后果

**积极面**：
- 好处 1
- 好处 2

**消极面**：
- 代价 1
- 代价 2

## 考虑的替代方案

### 方案 A
描述及拒绝原因

### 方案 B
描述及拒绝原因

## 相关决策
- [ADR 0001 - ...](0001-xxx.md)
```

---

## 检查清单

功能开发完成后：

```markdown
- [ ] 模块 README 更新？
- [ ] Sprint 状态更新？
- [ ] Plan 文档创建？（复杂任务）
- [ ] ADR 记录？（架构决策）
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| 只有代码没有说明 | 添加功能描述 |
| 状态未更新 | 及时更新 Sprint 状态 |
| 示例代码过时 | 同步更新示例 |
| 链接指向不存在 | 检查所有链接 |
