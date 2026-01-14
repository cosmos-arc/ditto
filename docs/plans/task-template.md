# [Sprint X] Task Y: 任务名称

**日期**: YYYY-MM-DD
**状态**: ❌ 未开始 | 🔄 进行中 | ✅ 已完成
**分支**: `feat/task-name`

---

## 🎯 技能使用计划

> 本任务的 Superpowers 工作流：

| 阶段 | 触发条件 | 使用 Skill | 产出 |
|------|----------|-----------|------|
| 设计 | 用户描述需求 | `brainstorming` | 交互式设计确认 |
| 计划 | 设计确认后 | `writing-plans` | 详细实施计划 |
| 执行 | 开始实施 | `executing-plans` + `test-driven-development` | 代码实现 |
| 审查 | 任务间隙 | `requesting-code-review` | 代码质量检查 |
| 完成 | 任务完成 | `finishing-a-development-branch` | PR/合并决策 |

---

## 一、任务概述

### 目标
简要描述这个任务要实现什么

### 依赖
- 前置任务：[依赖的其他任务]
- 需要的数据/接口：[...]

### 复杂度评估
- **任务规模**: S (简单) / M (中等) / L (复杂)
- **是否需要 Plan 文件**: 是/否
- **预估子任务数**: ___ 个

---

## 二、设计阶段 (brainstorming)

### 2.1 需求讨论

> **使用 Skill**: `brainstorming`

**用户确认项**:
- [ ] 功能边界已明确
- [ ] 接口设计已确认
- [ ] 数据结构已定义
- [ ] 边界条件已讨论

**关键设计决策**:
1. 决策1 → 理由
2. 决策2 → 理由

---

## 三、实施计划 (writing-plans)

> **使用 Skill**: `executing-plans` + `test-driven-development`

> **TDD 原则**: 红色测试 → 绿色实现 → 重构优化

### Phase 1: xxx

**1.1 子任务名称** (RED → GREEN → REFACTOR)
- 文件：`packages/xxx/src/xxx.py`
- 测试：`tests/xxx/test_xxx.py`
- Commit: `feat(scope): implement xxx`
- 状态：[ ] 未完成 / [x] 已完成

**1.2 子任务名称**
- ...

### Phase 2: xxx

**2.1 子任务名称**
- ...

---

## 四、Git 提交策略

### 提交粒度原则

| 何时 Commit | 说明 |
|-------------|------|
| ✅ 完成一个独立函数 | 如：SqlEngine._register_views |
| ✅ 完成一个测试类 | 如：TestSqlEngine 基础测试 |
| ✅ 测试通过后 | RED → GREEN 的完整循环 |
| ✅ 重构完成后 | 行为不变但代码改善 |
| ❌ 写到一半 | 不完整的代码不 commit |

### 预期提交序列

```bash
# 1. 测试骨架 (RED)
git commit -m "test(sql_engine): add test skeleton for SqlEngine"

# 2. 基础实现 (GREEN)
git commit -m "feat(sql_engine): implement SqlEngine.__init__ and _setup"

# 3. View 注册
git commit -m "feat(sql_engine): implement _register_views for Parquet datasets"

# 4. 宏注册
git commit -m "feat(sql_engine): implement adjustment macros (qfq, qfq_now, market_hfq)"

# 5. SQLite ATTACH
git commit -m "feat(sql_engine): implement SQLite ATTACH on demand"

# 6. DataHub Facade
git commit -m "feat(datahub): implement DataHub facade with lazy loading"

# 7. 包导出
git commit -m "chore(datahub): export DataHub from __init__.py"
```

---

## 五、验收标准

### 功能
- [ ] 功能点 1
- [ ] 功能点 2

### 质量
- [ ] 单元测试通过
- [ ] 覆盖率达标 (≥80%)
- [ ] Ruff/Pyright 检查通过

### 性能（如适用）
- [ ] 性能指标 1

---

## 六、文件清单

```
packages/xxx/src/xxx/
├── module.py           # 描述
└── tests/
    └── test_module.py  # 测试
```

---

## 七、完成阶段 (finishing-a-development-branch)

> **使用 Skill**: `finishing-a-development-branch`

### 7.1 完成前验证 (verification-before-completion)

- [ ] `pixi run -e dev ci-check` 全部通过
- [ ] 所有测试通过
- [ ] 代码已 Polishing
- [ ] DoD 全部勾选

### 7.2 决策点

**选项**:
- [ ] 创建 PR → 继续下一步
- [ ] 本地合并 → 适用于小型工具函数
- [ ] 保留分支 → 适用于未完成的工作
- [ ] 丢弃分支 → 适用于实验性代码

### 7.3 创建 PR（如选择）

```bash
git push -u origin feat/task-name
gh pr create --base main --title "feat: description"
```

---

## 八、完成总结

<!-- 任务完成后填写 -->

### 已实现
- ✅ ...
- ✅ ...

### 遗留问题
- [ ] ...

### 经验教训
- ...

---

**最后更新**: YYYY-MM-DD
