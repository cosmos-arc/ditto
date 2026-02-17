# 黄金数据集功能实现计划

**Sprint**: 数据质量增强 | **Phase**: 黄金数据集
**创建**: 2026-02-17
**状态**: ✅ 已完成

---

## 概述

实现黄金数据集功能，为对账服务提供精选标的子集，减少对账时间、专注核心标的、提高问题发现效率。

### 技术方案

- **配置来源**: YAML 配置文件
- **使用场景**: 每日对账（Tushare vs TDX）
- **配置粒度**: 全局配置（一个黄金数据集适用于所有对账）
- **标的数量**: 25 个（覆盖流动性分层、市场板块、资产类型、特殊场景）

### 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│ Port 层                                            │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ GoldenDatasetProvider                                       │ │
│ │ - 加载 YAML 配置                                            │ │
│ │ - 注入 GoldenDatasetSpec 到 DI 容器                         │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ QualityReconciliationService (修改)                         │ │
│ │ - 接收 GoldenDatasetSpec                                    │ │
│ │ - 应用 _apply_golden_dataset_filter()                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ DI
┌─────────────────────────────────────────────────────────────────┐
│ Core 层                                          │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ golden.py (新建)                                            │ │
│ │ - GoldenDatasetSpec: Pydantic 模型                          │ │
│ │ - GoldenDatasetOptions: 选项配置                            │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 任务清单

### Step 1: 创建 Pydantic 模型 `[S]`

- [x] 验收: GoldenDatasetSpec 模型定义完成，通过类型检查
- 文件: `packages/core/src/ditto_core/quality/golden.py`
- 文件: `packages/core/src/ditto_core/quality/__init__.py`

### Step 2: 添加路径发现函数 `[S]`

- [x] 验收: get_default_golden_dataset_path 函数可用
- 文件: `packages/infra/src/ditto_infra/foundation/config/project_root.py`
- 文件: `packages/infra/src/ditto_infra/foundation/config/__init__.py`

### Step 3: 创建 DI Provider `[M]`

- [x] 验收: GoldenDatasetProvider 注册到 DI 容器
- 文件: `apps/port/src/ditto_port/registry/core/golden.py`
- 文件: `apps/port/src/ditto_port/registry/core/__init__.py`

### Step 4: 创建配置文件 `[S]`

- [x] 验收: YAML 配置包含 25 个标的
- 文件: `config/default/golden_dataset.yml`

### Step 5: 集成对账服务 `[M]`

- [x] 验收: 对账服务支持黄金数据集过滤
- 文件: `apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py`

### Step 6: 编写测试 `[M]`

- [x] 验收: 单元测试覆盖核心场景
- 文件: `apps/port/tests/unit/services/ingestion/quality/test_golden_unit.py`

---

## 验证命令

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
```

---

## 相关文档

- [黄金数据集设计文档](../design/13_golden_dataset_design.md)
- [数据质量跨源对比架构设计](../plans/archive/2026-01-24-quality-reconciliation-design.md)
