# Ditto Sprint 开发文档

## 概述

本文档目录包含Ditto量化交易系统的Sprint开发计划和跟踪文档。

## Sprint 划分

### Phase 0.5: 数据层与验证（Sprint 1）
- **时间**: Week 1-2
- **目标**: 按照官方设计文档实现数据层（DataHub + Repository + Store + Runtime）
- **文档**: [sprint-01-data-layer.md](./sprint-01-data-layer.md)
- **状态**: ✅ 已规划（基于官方02_data_design.md）

### Phase 1.1: 核心引擎实现（Sprint 2）
- **时间**: Week 3-4
- **目标**: 实现核心业务引擎
- **文档**: [sprint-02-core-engines.md](./sprint-02-core-engines.md)
- **状态**: ❌ 未开始

### Phase 1.2: 回测与风控（Sprint 3）
- **时间**: Week 5-6
- **目标**: 完成回测引擎和风控系统
- **文档**: [sprint-03-backtest-risk.md](./sprint-03-backtest-risk.md)
- **状态**: ❌ 未开始

## 任务跟踪

每个Sprint文档包含：
- Sprint目标
- 任务分解（P0/P1优先级）
- 验收标准
- 关键里程碑
- 交付清单

## 进度更新

请使用以下状态标记：
- ✅ 已完成
- 🔄 进行中
- ❌ 未开始
- 🚧 阻塞中

## 开发原则

1. **数据层优先**: Golden Dataset是成功的基石
2. **严格TDD**: 先写测试，再实现功能
3. **质量第一**: 代码覆盖率>90%，对齐测试误差<0.1%
4. **渐进交付**: 每个Sprint都有可演示的成果
