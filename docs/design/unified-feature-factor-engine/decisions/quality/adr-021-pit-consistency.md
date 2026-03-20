# ADR-021: PIT 一致性与因子引擎集成

**状态**: 已决策（2026-03-05）

---

## 背景

因子计算必须保证 PIT（Point-in-Time）一致性，防止前瞻偏差。当前项目已有 PIT 基础设施，需要确定因子引擎如何集成。

---

## 决策要点

| 决策项 | 决策 | 理由 |
|--------|------|------|
| FactorSpec PIT 声明 | 不需要显式声明，默认支持 PIT | 简化因子定义，由引擎自动处理 |
| pit_columns 位置 | 从 SourceSchema 迁移到 StoreSchema | PIT 列是存储层概念，数据源不产生 |
| PIT 查询策略 | 引擎根据 StoreSchema.pit_columns 自动生成过滤 | 统一处理，避免遗漏 |

---

## pit_columns 类型

| pit_columns 值 | PIT 类型 | 查询条件 |
|----------------|----------|----------|
| `("effective_from", "effective_to")` | 双时间戳版本化 | `effective_from <= as_of AND (effective_to IS NULL OR effective_to > as_of)` |
| `("knowledge_date",)` | 知识日期 | `knowledge_date <= as_of` |
| `()` | 无需 PIT | 直接用 `trade_date` |

---

## 引擎执行流程

```
1. 解析表达式 → 提取数据集引用
2. 查找 StoreSchema → 获取 pit_columns
3. 根据 pit_columns → 自动生成 PIT 过滤条件
4. 执行查询 → 返回 PIT 安全的数据
```

---

## 待办事项

- [ ] 迁移 `pit_columns` 从 `SourceSchema` 到 `StoreSchema`
- [ ] 更新所有现有 Schema 定义
- [ ] 因子引擎集成 PIT 自动过滤逻辑
- [ ] 添加 PIT 验证测试

---

## 示例

```python
# StoreSchema 定义
BALANCE_SHEET_STORE_SCHEMA = StoreSchema(
    dataset="fundamental/balance_sheet",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={...},
    pit_columns=("effective_from", "effective_to"),  # 迁移后
)

# FactorSpec - 无需显式 PIT 声明
FactorSpec(
    name="pe_ratio",
    expr="market.close * shares / fundamental.net_income",
    # 引擎自动根据数据集 pit_columns 处理
)
```
