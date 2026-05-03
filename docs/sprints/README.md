> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto Sprint 开发文档

**版本**: v1.0.0
**最后更新**: 2026-04-27
**状态**: V1 RC 已完成

## 概要

Ditto 项目已完成 V1 Sprint 全部阶段，进入增强迭代期。

| 阶段 | 时间 | 进度 | 状态 |
|------|------|------|------|
| Phase 0-0.5 | 2026-01 ~ 2026-02 | ██████████ 100% | 数据层基础架构 |
| Phase 1 (Sprint 1-2) | 2026-02 ~ 2026-03 | ██████████ 100% | 回测闭环 + 策略引擎 |
| Phase 2-4 | 2026-03 ~ 2026-04 | ██████████ 100% | 架构改进 + 代码审查修复 |
| V1 Sprint (Phase 5-9) | 2026-04 | ██████████ 100% | V1 RC Closeout（39 项审查修复） |
| V1.1 增强 | 2026-04 ~ | — | 计划中（详见 `docs/plans/`） |

## 当前阶段

项目处于 **V1 RC 已完成** 状态，当前分支 `feat/v1-sprint` 包含 V1 全部改进。

### V1 Sprint 完成情况

V1 Sprint 包含 9 个 Phase，共 39 项代码审查修复任务，已全部完成：

1. **Phase 1-3**: 门禁问题修复（P0 优先级）
2. **Phase 4**: 全库架构审计（异常迁移 + 存储隔离 + 简化）
3. **Phase 5**: 编码规约修复（frozen dataclass + 命名规范化）
4. **Phase 6**: 架构改进（artifact_utils 重命名 + re-export 清理）
5. **Phase 7**: PIT 改进（flush 日志 + execution_delay 文档 + 断言）
6. **Phase 8**: 测试与文档改进
7. **Phase 9**: 文档打磨（计划归档 + ADR/boundaries 状态更新）

### V1.1 增强计划

详见 `docs/plans/` 中的 V1 增强设计文档：
- `2026-04-10-v1-version-design.md`
- `2026-04-11-v1-enhancement-design.md`
- `2026-04-17-v1-remaining-delivery-and-v11-enhancement.md`

---

## 历史阶段

### Phase 0.5: 数据层与验证

- **Sprint 1**: 数据层基础架构
  - Runtime Layer → Store Layer → Repositories → DataHub Facade
  - 数据摄取基础（Tushare 适配器）

- **Sprint 2**: 数据层完善与验证
  - DQ 三层架构、DataHub 完整实现、黄金数据集验证

### Phase 1: 核心引擎与回测

- **Sprint 3**: 核心引擎实现（Regime/Factor/策略框架）
- **Sprint 4**: 回测与风控（FastBacktester/RiskEngine/Walk-Forward）

---

## Git 提交粒度规范

| 场景 | 示例 Commit Message |
|------|---------------------|
| 完成一个功能 | `feat(engine): implement alpha pipeline stage` |
| 完成测试 | `test(data): add PIT safety assertions for rolling windows` |
| RED → GREEN | `feat(data): make pit query tests pass` |
| 重构 | `refactor(app): simplify CQRS command handler` |
| 修复 Bug | `fix(kernel): resolve identity allocation race condition` |
| 类型修复 | `fix(types): add proper type hints to query method` |
| 文档 | `docs: update architecture boundary standards` |

---

## 状态图例

- ✅ 已完成
- 🔄 进行中
- 📝 规划中

---

## Sprint 任务文件（历史）

| Sprint | 文件 | 状态 |
|--------|------|------|
| 1 | [sprint-01-data-foundation.md](./sprint-01-data-foundation.md) | ✅ 100% |
| 2 | [sprint-02-data-quality.md](./sprint-02-data-quality.md) | ✅ 完成 |
| 3 | [sprint-03-core-engines.md](./sprint-03-core-engines.md) | ✅ 完成 |
| 4 | [sprint-04-backtest-risk.md](./sprint-04-backtest-risk.md) | ✅ 完成 |
| - | [backlog.md](./backlog.md) | 📝 想法池 |

## 参考文档

- [架构决策记录 (ADR)](../adr/README.md) - 10 条已接受决策
- [架构边界标准](../architecture/boundaries-and-abstraction-standards.md) - 最新规范
- [设计文档](../design/README.md) - 系统设计参考
- [计划文档](../plans/README.md) - 实施计划模板
