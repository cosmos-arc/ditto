# 归档规划文档索引

本目录包含已完成的历史计划文档，供回顾和参考。

## 目录说明

`docs/plans/` 目录采用以下组织结构：

```
docs/plans/
├── archive/              # 本目录：已完成的归档计划
│   ├── YYYY-MM-DD-*.md  # 按日期命名的归档文档
└── README.md            # 当前活跃计划索引
```

## 归档规则

### 何时归档

计划文档在以下情况下归档到本目录：

1. **任务完成**：计划中列出的所有任务已完成
2. **过时废弃**：计划已被新计划取代或不再适用
3. **长期未更新**：计划超过 6 个月未更新且未完成

### 归档流程

```bash
# 1. 将完成的计划移动到 archive 目录
git mv docs/plans/2025-12-22-sprint1-task1-runtime-layer.md docs/plans/archive/

# 2. 更新文档中的状态标记为 "已完成" 或 "已归档"

# 3. 提交变更
git commit -m "docs(plans): 归档已完成计划 - Sprint 1 Task 1"

# 4. 更新本索引文件（archive/README.md）
```

## 归档计划列表

### Sprint 1 相关计划

| 文档 | 完成日期 | 概要 |
|------|----------|------|
| [2025-12-22-sprint1-task1-runtime-layer.md](2025-12-22-sprint1-task1-runtime-layer.md) | - | Runtime Layer 基础组件实现（SID 分配器、SQLite 连接池、文件锁、DQ 检查器） |
| [2025-12-22-sprint1-task2-store-layer.md](2025-12-22-sprint1-task2-store-layer.md) | ✅ | Store Layer 实现（Security/Calendar/Pipeline/Bars/AdjFactor Stores） |
| [2025-12-27-server-layer-design.md](2025-12-27-server-layer-design.md) | ✅ | Server 层设计（Prefect 调度 + 数据摄取 Flow） |

### 代码质量修复

| 文档 | 完成日期 | 概要 |
|------|----------|------|
| [2025-12-26-datahub-code-quality-fixes.md](2025-12-26-datahub-code-quality-fixes.md) | ❌ | DataHub 代码质量修复（14 个问题，包括混合资产查询、QFQ 排序、复权因子缺失等） |

### Sprint 2 相关计划

| 文档 | 完成日期 | 概要 |
|------|----------|------|
| [2025-12-28-sprint2-phase0-tech-debt.md](2025-12-28-sprint2-phase0-tech-debt.md) | - | Sprint 2 Phase 0：技术债务清理（补充测试、代码重构、文档更新） |
| [2025-12-28-sprint2-phase1-dq-three-tier.md](2025-12-28-sprint2-phase1-dq-three-tier.md) | - | Sprint 2 Phase 1：DQ 三层架构实施（YAML 配置、L1/L2/L3 检查器、隔离区） |

## 计划状态说明

| 状态 | 说明 |
|------|------|
| ✅ | 已完成 |
| 🔄 | 进行中 |
| ⏸️ | 暂停/延后 |
| ❌ | 未开始/已取消 |
| 📋 | 计划中 |

## 相关文档

- [当前活跃计划](../README.md) - 正在进行的计划
- [设计文档](../design/README.md) - 系统设计文档
- [Sprint 规划](../sprints/README.md) - Sprint 总体规划
- [架构决策记录](../adr/README.md) - 重要架构决策

## 访问归档计划

如需查看具体的归档计划内容，请点击上方表格中的文档链接。

归档文档保留原始内容和格式，但会更新状态标记以反映完成情况。这些文档可作为：
- 历史参考
- 类似任务的模板
- 项目演进记录
