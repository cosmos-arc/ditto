# DataHub Macro、Features、Factors 域重构实施计划

> **注意:** 本阶段不在三域重构范围内。
>
> **三域重构范围:** Metadata、Market、Capital 三个域。
>
> **最新实施计划:** 参见 [2026-01-29-datahub-three-domain-refactor-implementation.md](./2026-01-29-datahub-three-domain-refactor-implementation.md)
>
> **说明:** Macro、Features、Factors 域属于更高级的功能模块，不在本次三域重构范围内。本计划文档保留用于未来实施参考。

---

## 原始计划（保留用于参考）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

本文档包含三个域的重构计划：
- Phase 6: Macro 域
- Phase 7: Features 域
- Phase 8: Factors 域

---

## Phase 6: Macro 域重构

**目标:** 实现完整的 Macro 域，支持宏观数据查询

### 目录结构

```
packages/datahub/src/ditto_datahub/domains/macro/
├── __init__.py
├── indicator/
│   ├── indicator_store.py
│   └── metadata_store.py
└── macro_query_service.py
```

### 任务清单

1. 创建 Macro 域目录结构
2. 实现 IndicatorStore (支持 PIT 查询)
3. 实现 IndicatorMetadataStore
4. 实现 MacroQueryService
5. 更新 DataHub 集成
6. 创建 Git Tag

**预计时间: 3-4 个工作日**

---

## Phase 7: Features 域重构

**目标:** 实现完整的 Features 域，支持特征数据的存储和查询

### 目录结构

```
packages/datahub/src/ditto_datahub/domains/features/
├── __init__.py
├── technical/
│   ├── price/
│   │   ├── ma_features_store.py
│   │   ├── momentum_features_store.py
│   │   └── volatility_features_store.py
│   ├── volume/
│   │   └── volume_features_store.py
│   └── fundamental/
│       └── fundamental_features_store.py
├── features_query_service.py
└── post_processor.py
```

### 任务清单

1. 创建 Features 域目录结构
2. 实现 Price 特征 Store (MA、RSI、MACD 等)
3. 实现 Volume 特征 Store
4. 实现 Fundamental 特征 Store
5. 实现窄表 + 宽表存储策略
6. 实现 FeaturesQueryService
7. 更新 DataHub 集成
8. 创建 Git Tag

**预计时间: 6-8 个工作日**

---

## Phase 8: Factors 域重构

**目标:** 实现完整的 Factors 域，支持风格因子的存储和查询

### 目录结构

```
packages/datahub/src/ditto_datahub/domains/factors/
├── __init__.py
├── style/
│   ├── value/
│   │   ├── value_pe_store.py
│   │   ├── value_pb_store.py
│   │   └── value_composite_store.py
│   ├── momentum/
│   │   └── momentum_store.py
│   ├── quality/
│   │   ├── quality_roe_store.py
│   │   └── quality_financial_health_store.py
│   └── volatility/
│       └── volatility_store.py
├── post_processing/
│   ├── winsorizer.py
│   ├── standardizer.py
│   └── neutralizer.py
├── factors_query_service.py
└── post_processor.py
```

### 任务清单

1. 创建 Factors 域目录结构
2. 实现 Value 因子 Store
3. 实现 Momentum 因子 Store
4. 实现 Quality 因子 Store
5. 实现后处理模块 (去极值、标准化、中性化)
6. 实现窄表 + 宽表存储策略
7. 实现 FactorsQueryService
8. 更新 DataHub 集成
9. 创建 Git Tag

**预计时间: 8-10 个工作日**

---

## 总验收标准

### Macro 域

- [ ] domains/macro/ 目录结构完整
- [ ] IndicatorStore 实现 PIT 查询
- [ ] MacroQueryService 实现所有查询接口
- [ ] 测试覆盖率 ≥ 80%

### Features 域

- [ ] domains/features/ 目录结构完整
- [ ] 所有 Technical 特征 Store 实现完整
- [ ] 窄表 + 宽表存储策略实现
- [ ] FeaturesQueryService 实现所有查询接口
- [ ] 测试覆盖率 ≥ 80%

### Factors 域

- [ ] domains/factors/ 目录结构完整
- [ ] 所有 Style 因子 Store 实现完整
- [ ] 后处理模块实现完整
- [ ] 窄表 + 宽表存储策略实现
- [ ] FactorsQueryService 实现所有查询接口
- [ ] 测试覆盖率 ≥ 80%

---

## 总预计时间

- Macro 域: 3-4 天
- Features 域: 6-8 天
- Factors 域: 8-10 天

**总计: 约 17-22 个工作日**
