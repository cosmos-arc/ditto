# Ditto Sprint 开发文档

## 当前状态

| Sprint | 阶段 | 进度 | 状态 |
|--------|------|------|------|
| Sprint 1 | 数据层与验证 | ████████░░ 80% | 🔄 进行中 |
| Sprint 2 | 核心引擎 | ░░░░░░░░░░ 0% | ❌ 未开始 |
| Sprint 3 | 回测与风控 | ░░░░░░░░░░ 0% | ❌ 未开始 |

## 当前进行中

<!-- 从 Sprint 文件同步当前正在进行的任务 -->

### Sprint 1 - 任务 4: DataHub Facade
- **分支**: `feat/datahub-facade`
- **状态**: ✅ 已完成
- **完成**: 2024-12-26

**子任务**:
- [x] SqlEngine 实现
- [x] DataHub Facade 实现
- [x] 测试完成 (20 tests)
- [x] PR 创建

---

## 🎯 Superpowers 工作流

> **Claude Code 必须遵循的工作流程**

### 技能激活流程图

```
用户启动 /start-dev
         ↓
┌─────────────────────────────────────────────────────┐
│ 1. 选择任务 (从 Sprint 文件)                          │
│    - 确认优先级 (P0/P1)                               │
│    - 确认依赖已满足                                   │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 2. 创建开发分支                                        │
│    git checkout -b feat/task-name                    │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 3. 设计阶段  → 自动激活                              │
│    - 交互式设计细化                                    │
│    - 边界条件讨论                                      │
│    - 方案确认                                         │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 4. 计划阶段  → 自动激活                              │
│    - 生成详细实施计划                                  │
│    - 强调 TDD/YAGNI/DRY                              │
│    - 复杂任务保存到 docs/plans/                       │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 5. 执行阶段  → 自动激活                             │
│    批量执行任务，每任务遵循：                           │
│    ┌──────────────────────────────────────┐         │
│    │ test-driven-development (TDD)        │         │
│    │  - RED: 写测试，观察失败               │         │
│    │  - GREEN: 写最少代码通过               │         │
│    │  - REFACTOR: 重构优化                  │         │
│    │  - COMMIT: 每个循环结束提交           │         │
│    └──────────────────────────────────────┘         │
│    ↓                                                  │
│    requesting-code-review (任务间隙)                 │
│    - 对照计划审查                                      │
│    - 按严重性报告问题                                  │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 6. 完成阶段  → 自动激活                              │
│    - verification-before-completion                  │
│    - 提供选项: PR / 本地合并 / 保留 / 丢弃            │
└─────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────┐
│ 7. 合并后清理                                          │
│    - 更新 Sprint 文件状态                              │
│    - 删除本地分支                                      │
└─────────────────────────────────────────────────────┘
```

### 技能使用检查清单

**开始任务前**:
- [ ] 确认任务在当前 Sprint 中
- [ ] 创建功能分支（不在 main）
- [ ] 更新 Sprint 文件状态为进行中

**设计阶段** (brainstorming):
- [ ] 需求边界已明确
- [ ] 接口设计已确认
- [ ] 数据结构已定义
- [ ] 边界条件已讨论

**执行阶段** (executing-plans + test-driven-development):
- [ ] 先写测试 (RED)
- [ ] 写最少代码通过 (GREEN)
- [ ] 重构优化 (REFACTOR)
- [ ] 每个循环结束提交
- [ ] 间隙进行 code review

**完成阶段** (finishing-a-development-branch):
- [ ] ci-check 全部通过
- [ ] 代码已 Polishing
- [ ] DoD 全部勾选
- [ ] 创建 PR 或合并决策

---

## Sprint 规划

### Phase 0.5: 数据层与验证
- **Sprint 1**: [数据层实现](./sprint-01-data-layer.md)
  - Week 1-2
  - Runtime Layer ✅ → Store Layer ✅ → Repositories ✅ → DataHub ✅

### Phase 1.1: 核心引擎
- **Sprint 2**: [核心引擎实现](./sprint-02-core-engines.md)
  - Week 3-4
  - RegimeEngine → FactorEngine → 策略框架

### Phase 1.2: 回测与风控
- **Sprint 3**: [回测与风控](./sprint-03-backtest-risk.md)
  - Week 5-6
  - FastBacktester → RiskEngine → Walk-Forward

---

## 开发原则

1. **数据层优先**: Golden Dataset 是成功的基石
2. **严格 TDD**: 先写测试，再实现功能
3. **质量第一**: 代码覆盖率 >90%，对齐测试误差 <0.1%
4. **渐进交付**: 每个 Sprint 都有可演示的成果
5. **小步提交**: 每个红绿重构循环独立提交
6. **技能驱动**: Superpowers 自动激活，确保流程遵循

---

## Git 提交粒度规范

### ✅ 推荐的提交粒度

| 场景 | 示例 Commit Message |
|------|---------------------|
| 完成一个函数 | `feat(sql_engine): implement _register_views` |
| 完成一个测试类 | `test(sql_engine): add test skeleton for SqlEngine` |
| RED→GREEN 完成 | `feat(sql): make sql query tests pass` |
| 重构完成 | `refactor(hub): simplify dependency injection` |
| 修复 Bug | `fix(datahub): resolve SID allocation race condition` |
| 类型修复 | `fix(types): add proper type hints to sql method` |

### ❌ 避免的提交方式

| 错误示例 | 问题 |
|----------|------|
| 单个提交包含整个功能 | 粒度过粗，难以 review，无法回滚特定步骤 |
| "WIP" 或 "fix tests" 提交 | 信息不明确，无法理解改动目的 |
| 跳过测试直接实现 | 违反 TDD 原则 |
| 大量文件混合在一起 | 违反单一职责原则 |

### 理想提交序列示例

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

## 状态图例

- ✅ 已完成
- 🔄 进行中
- ❌ 未开始
- 🚧 阻塞中
- 📝 规划中

---

## Sprint 任务文件

| Sprint | 文件 | 状态 |
|--------|------|------|
| 1 | [sprint-01-data-layer.md](./sprint-01-data-layer.md) | 🔄 80% |
| 2 | [sprint-02-core-engines.md](./sprint-02-core-engines.md) | ❌ 未开始 |
| 3 | [sprint-03-backtest-risk.md](./sprint-03-backtest-risk.md) | ❌ 未开始 |
| - | [backlog.md](./backlog.md) | 📝 想法池 |
