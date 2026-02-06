# ditto-datahub 简化重构计划

**创建日期**: 2026-02-06
**状态**: 待审批
**相关问题**: Accessors 和 Stores 遗留代码清理、Domains 层实现不一致问题

## 评估摘要

### 当前架构状态

| 层级 | 状态 | 主要问题 |
|------|------|----------|
| **Accessors** | ✅ 已精简 | 文档严重过时 |
| **Stores** | ⚠️ 基础设施 | UniverseStore 定位模糊、Parquet 实现重复 |
| **Domains** | ⚠️ 实现不一致 | Service 模式不统一、命名冲突、职责边界模糊 |

### 核心发现

1. **Accessors 层**：已成功重构为 Domain Services 架构，只需更新文档
2. **Stores 层**：大部分代码是基础设施被广泛使用，但存在结构问题
3. **Domains 层**：功能完整但实现不一致，需要统一模式

## 重构方案

### 方案概述

采用 **渐进式重构**，分为三个阶段：

| 阶段 | 目标 | 风险 | 预计影响 |
|------|------|------|----------|
| **阶段 1** | 清理文档和临时文件 | 极低 | 文档更新 |
| **阶段 2** | 统一 Domains 层实现模式 | 中等 | 代码重构 |
| **阶段 3** | 优化 Stores 层结构 | 中高 | 代码迁移 |

---

## 阶段 1：清理文档和临时文件（低风险）

### 1.1 更新 Accessors 文档

**文件**：`packages/datahub/src/ditto_datahub/accessors/README.md`

**操作**：完全重写文档，只保留：
- InstrumentsAccessor 的功能说明
- internal/ 模块的纯函数工具说明
- 与 Domain Services 的关系说明

**删除内容**：
- BarsAccessor、SecurityAccessor、AdjFactorAccessor 等已移除组件的文档

### 1.2 清理测试覆盖率临时文件

**文件**：
- `packages/datahub/src/ditto_datahub/stores/*.cover`
- `packages/datahub/src/ditto_datahub/stores/__init__.py,cover`

**操作**：删除所有 `.cover` 文件（pytest-cov 临时生成的覆盖率文件）

### 1.3 更新 Stores 文档

**文件**：`packages/datahub/src/ditto_datahub/stores/README.md`

**操作**：更新文档说明：
- stores/ 层作为基础设施的定位
- 删除已迁移到 domains 层的 stores 引用

---

## 阶段 2：统一 Domains 层实现模式（中风险）

### 2.1 统一 Service 层职责边界

**问题**：当前 Service 层职责不一致
- MarketService：既有查询又有写入
- MetadataService：查询 + 注册
- CapitalService/FundamentalService：纯 thin wrapper

**方案**：采用 **统一模式**

```
Service 层：只提供查询接口
├── 简单查询（thin wrapper）：CapitalService, FundamentalService
├── 查询 + 元数据增强：FeatureService, FactorService, MacroService
└── 复杂编排：MarketService（复权、状态增强）

写入操作：统一通过 DataHub 的 write_xxx 方法
├── hub.write_bars()
├── hub.write_adj_factor()
└── hub.securities.register_batch()
```

### 2.2 解决命名冲突

**问题**：Features 和 Macro 域都使用 `IndicatorStore`

**方案**：重命名 Features 域的 Store

```
domains/features/technical/
├── technical_indicator_store.py      # 原 indicator_store.py
└── technical_indicator_metadata_store.py  # 原 indicator_metadata_store.py
```

### 2.3 移除 InstrumentsAccessor，功能合并到 MetadataService ✅ **用户确认**

**问题**：InstrumentsAccessor 与 MetadataService 功能重叠

**方案**：
1. 将 InstrumentsAccessor 的证券注册功能合并到 MetadataService
2. 更新 DataHub 依赖注入配置
3. 删除 `accessors/` 目录

**迁移映射**：
```
InstrumentsAccessor.register_batch()         → MetadataService.register_securities()
InstrumentsAccessor.enrich_dataframe_with_sid() → MetadataService.enrich_with_sid()
InstrumentsAccessor.resolve_or_create_batch() → MetadataService.resolve_or_create_batch()
```

### 2.4 迁移 UniverseStore

**问题**：UniverseStore 位于 stores/ 但提供业务功能

**方案**：迁移到 domains 层

```
domains/metadata/universe/
├── __init__.py
├── universe_store.py      # 从 stores/ 迁移
└── universe_service.py    # 新建，封装 UniverseStore
```

---

## 阶段 3：优化 Stores 层结构（中高风险）

### 3.1 合并 Parquet 存储实现

**问题**：`parquet_store_base.py` 与 `base/parquet_store.py` 功能重叠

**方案**：合并为统一实现

```
stores/base/
├── __init__.py
├── base_store.py                    # 抽象基类
├── parquet_store.py                 # 合并后的统一实现
│   ├── 原 parquet_store_base.py 的模板方法模式
│   └── 原 base/parquet_store.py 的功能
└── sqlite_store.py
```

**影响范围**：
- 需要更新所有继承 ParquetStoreBase 的 domains 层 stores
- 更新导入路径

### 3.2 重新组织 Stores 层结构

**目标结构**：

```
stores/
├── __init__.py           # 只导出基础设施
├── README.md             # 更新后的文档
├── sqlite_client.py      # SQLite 客户端封装
└── base/
    ├── __init__.py
    ├── base_store.py           # 存储抽象
    ├── parquet_store.py        # 统一 Parquet 实现
    └── sqlite_store.py         # SQLite 实现
```

**删除内容**：
- `parquet_store_base.py`（功能合并到 base/parquet_store.py）
- `universe_store.py`（迁移到 domains/metadata/universe/）

---

## 关键文件清单

### 需要修改的文件

#### 阶段 1（文档清理）
- [ ] `packages/datahub/src/ditto_datahub/accessors/README.md` - 完全重写
- [ ] `packages/datahub/src/ditto_datahub/stores/README.md` - 更新
- [ ] 删除所有 `.cover` 文件

#### 阶段 2（统一 Domains）
- [ ] `packages/datahub/src/ditto_datahub/domains/features/technical/indicator_store.py` → `technical_indicator_store.py`
- [ ] `packages/datahub/src/ditto_datahub/domains/metadata/metadata_service.py` - 合并 InstrumentsAccessor 功能
- [ ] `packages/datahub/src/ditto_datahub/domains/metadata/universe/` - 新建目录，迁移 UniverseStore
- [ ] `packages/datahub/src/ditto_datahub/hub.py` - 更新依赖注入
- [ ] `packages/datahub/src/ditto_datahub/registry/datahub.py` - 更新 Provider 配置

#### 阶段 3（优化 Stores）
- [ ] `packages/datahub/src/ditto_datahub/stores/base/parquet_store.py` - 合并 parquet_store_base 功能
- [ ] `packages/datahub/src/ditto_datahub/stores/parquet_store_base.py` - 删除
- [ ] `packages/datahub/src/ditto_datahub/stores/universe_store.py` - 删除（已迁移）
- [ ] 更新所有继承 ParquetStoreBase 的 domains 层 stores

### 测试文件更新

需要同步更新的测试文件：
- [ ] `tests/unit/domains/features/technical/test_indicator_store_unit.py` - 重命名
- [ ] `tests/unit/stores/test_universe_store_unit.py` - 迁移到 domains/metadata/
- [ ] `tests/integration/stores/test_universe_store_integration.py` - 迁移
- [ ] 所有引用 ParquetStoreBase 的测试文件

---

## 实施顺序

### 第一步：清理文档（1-2 小时）
1. 更新 accessors/README.md
2. 更新 stores/README.md
3. 删除 .cover 文件
4. 运行测试验证

### 第二步：统一 Domains（4-6 小时）
1. 重命名 Features 域的 IndicatorStore
2. 迁移 UniverseStore
3. 合并 InstrumentsAccessor 到 MetadataService
4. 更新 DataHub 依赖注入
5. 更新所有测试
6. 运行完整测试套件

### 第三步：优化 Stores（3-4 小时）
1. 合并 parquet_store_base.py 到 base/parquet_store.py
2. 更新所有导入
3. 删除 parquet_store_base.py
4. 运行完整测试套件

---

## 验证计划

### 每个阶段完成后运行：

```bash
# 类型检查
pixi run -e dev type

# 代码检查
pixi run -e dev lint

# 单元测试
pixi run -e dev test --unit

# 集成测试
pixi run -e dev test --integration

# 完整 CI
pixi run -e dev ci
```

### 最终验证：
- [ ] 所有测试通过
- [ ] 类型检查无错误
- [ ] 代码检查通过
- [ ] 文档更新完成
- [ ] 无遗留 TODO 注释

---

## 风险评估

| 阶段 | 风险等级 | 主要风险 | 缓解措施 |
|------|----------|----------|----------|
| 阶段 1 | 极低 | 无 | 文档更新不影响代码 |
| 阶段 2 | 中等 | 依赖注入配置错误 | 逐个测试验证，保留回滚点 |
| 阶段 3 | 中高 | 导入路径破坏 | 全量测试覆盖，分步提交 |

## 回滚计划

每个阶段完成后创建 git commit，方便回滚：
- `阶段1完成：清理文档和临时文件`
- `阶段2完成：统一Domains层实现模式`
- `阶段3完成：优化Stores层结构`

---

## 相关文档

- [之前的 stores 清理计划](./2026-02-05-stores-cleanup-refactor-plan.md)
- [DataHub 架构设计](../design/02_data_design.md)
- [PIT 查询设计](../design/07_pit_query_design.md)
