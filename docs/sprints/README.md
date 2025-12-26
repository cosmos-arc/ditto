# Ditto Sprint 开发文档

## 当前状态

| Sprint | 阶段 | 进度 | 状态 |
|--------|------|------|------|
| Sprint 1 | 数据层与验证 | ████████░░ 80% | 🔄 进行中 |
| Sprint 2 | 核心引擎 | ░░░░░░░░░░ 0% | ❌ 未开始 |
| Sprint 3 | 回测与风控 | ░░░░░░░░░░ 0% | ❌ 未开始 |

## 当前进行中

<!-- 从 Sprint 文件同步当前正在进行的任务 -->

### Sprint 1 - 任务 3: Domain Repositories
- **分支**: `feat/domain-repositories`
- **状态**: 🔄 开发中
- **开始**: 2024-12-26

**子任务**:
- [ ] SecurityRepository
- [ ] BarsRepository
- [ ] CalendarRepository

---

## Sprint 规划

### Phase 0.5: 数据层与验证
- **Sprint 1**: [数据层实现](./sprint-01-data-layer.md)
  - Week 1-2
  - Runtime Layer ✅ → Store Layer ✅ → Repositories → DataHub

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

## 状态图例

- ✅ 已完成
- 🔄 进行中
- ❌ 未开始
- 🚧 阻塞中
