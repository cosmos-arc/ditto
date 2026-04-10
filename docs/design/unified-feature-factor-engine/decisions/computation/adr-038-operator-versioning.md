# ADR-038: 算子版本管理

**状态**: ✅ 已决策（2026-03-12）

---

## 背景

算子是表达式引擎的核心组件，当前存在以下问题：
1. 52 个算子无版本标识
2. 算子实现变更后无法追踪影响范围
3. 依赖该算子的因子可能产生不一致结果
4. 缓存失效缺乏可靠的触发机制

本 ADR 定义算子版本管理的完整方案，与 [ADR-039: 表达式缓存持久化](adr-039-expression-cache-persistence.md) 配合实现缓存正确性。

---

## 决策记录

### D-1: 版本号格式

| 属性 | 值 |
|------|------|
| **格式** | SemVer（严格三段式） |
| **存储格式** | `"1.2.3"`（不带 `v` 前缀） |
| **展示格式** | `v1.2.3` |
| **初始版本** | `1.0.0` |
| **校验规则** | 正则 `^\d+\.\d+\.\d+$` |

**决策理由**：
- SemVer 的 MAJOR/MINOR/PATCH 与现有文档的 Breaking/Additive/Data-only 变更分类天然契合
- 项目整体已偏向语义化版本（如 `v0.x.y`）
- 简单整数只够"变了"，不够表达"怎么变"
- 日期版本更适合发布节奏，不适合表达语义兼容性

**算子语境下的 SemVer 含义**：

| 段位 | 含义 | 示例 |
|------|------|------|
| **MAJOR** | 结果语义或契约变了 | 参数类型/默认值变化、null 传播变化、lookback/scope 变化 |
| **MINOR** | 向后兼容扩展 | 新增可选参数，旧调用结果不变 |
| **PATCH** | 向后兼容修复 | Bug 修复，接口不变，结果可能在异常边界上被纠正 |

---

### D-2: 版本升级规则（四分法）

| 升级级别 | 触发条件 | 缓存影响 |
|---------|---------|---------|
| **MAJOR** | 语义/契约不兼容变化 | 失效 |
| **MINOR** | 向后兼容扩展 | 失效 |
| **PATCH** | Bug 修复（契约不变，结果可能变） | 失效 |
| **NO BUMP** | 文档/注释/重构/性能优化（结果不变） | 不失效 |

#### MAJOR 触发条件

- 参数类型变化
- 参数含义变化
- 默认值变化且会影响旧调用结果
- 输出列/输出 shape/输出 dtype 变化
- `null_propagation` 规则变化
- `scope` / `lookback` / `requires_full_day` 传播语义变化
- PIT 相关语义变化（如窗口边界规则）
- **关键**：`closed="left"`、PIT 安全窗口、lookback 传播规则变化，至少 MAJOR

#### MINOR 触发条件

- 新增可选参数，且旧调用结果完全不变
- 新增等价别名或更友好的调用入口
- 新增可选优化模式，默认关闭

#### PATCH 触发条件

- 修复 bug，旧接口不变
- 修复边界条件错误、空值处理 bug、极端窗口 bug
- 修复 codegen 实现错误，但契约不变

#### NO BUMP 触发条件

- 注释、文档、日志
- 内部重构但产出 Expr 与 analysis 完全一致
- 纯性能优化且结果、analysis、默认行为都不变

**重要约束**：
- "修 bug 但结果会变"记为 **PATCH**，不是 NO BUMP
- PATCH 不等于结果完全不变，它表示"契约没变，但实现被纠正了"

---

### D-3: 变更日志

| 属性 | 值 |
|------|------|
| **存储方式** | 结构化注册表元数据 |
| **记录模型** | `ChangeRecord` |
| **存储特性** | append-only |

**ChangeRecord 模型**：

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class ChangeRecord(BaseModel):
    """算子变更记录"""
    version: str                  # "1.2.0"
    change_level: Literal["MAJOR", "MINOR", "PATCH"]
    summary: str                  # 人类可读摘要
    reason: str | None = None     # 可选，为什么要改
    breaking: bool
    affects_analysis: bool        # lookback/scope/requires_full_day 变化
    affects_codegen: bool         # Expr/codegen 变化
    git_commit: str | None = None
    created_at: datetime
    created_by: str | None = None
```

**决策理由**：
- 结构化记录最适合做查询和自动化
- 项目偏向"结构化元数据/manifest"治理模式
- 不依赖 Git commit message（squash/rebase 后不稳定）
- 如需人类友好文档，可从 `ChangeRecord` 自动生成

---

### D-4: 依赖提取与存储

#### 提取时机

```
Pratt Parser → AST → Analyzer(operator_refs/deps/lookback/scope)
                       ↓
                  resolve operator versions
                       ↓
                    Codegen(pl.Expr)
```

**决策**：在 **Analyzer 阶段** 提取算子依赖，不是 codegen 阶段。

**理由**：
1. 算子依赖是 DSL 语义，不是后端实现细节
2. Analyzer 本来就产出 deps/lookback/scope/requires_full_day
3. codegen 可能将一个 DSL 算子展开成多个 Polars 片段，但我们想版本化的是 DSL operator

#### Analysis 模型扩展

```python
class Analysis(BaseModel):
    """表达式分析结果"""
    dependencies: list[str]
    operator_names: list[str]      # 新增：使用的算子名称列表
    lookback: int
    requires_full_day: bool
    scope: str
```

#### 三层存储架构

| 层级 | 存储 | 用途 |
|------|------|------|
| **运行时** | `Analysis.operator_names` | 编译时真相源 |
| **Spec 级** | `DerivedSpec.operator_versions` + `derived_spec_operator` | 治理视图 |
| **Cache 级** | `compiled_expression_operator` | 缓存失效 |

#### 双存储策略（Spec 级）

| 存储 | 职责 | 用途 |
|------|------|------|
| `DerivedSpec.operator_versions` | 完整快照 | 自描述、可复现、可序列化 |
| `derived_spec_operator` 副表 | 反向索引 | operator → affected specs 查询 |

**决策理由**：
- 参考现有 `dependencies` JSON + `derived_dependency` 副表模式
- SQLite 查 JSON 不适合做长期治理主查询路径
- side table 擅长 operator_name + operator_version 过滤、统计、join

---

### D-5: Schema 设计

#### 算子注册表扩展

```python
@dataclass
class OperatorMeta:
    """算子元数据"""
    name: str
    version: str                              # 新增：必须声明
    category: str
    description: str
    parameters: list[ParameterSpec]
    returns: ReturnSpec
    analysis: AnalysisSpec
    changelog: list[ChangeRecord] = field(default_factory=list)
```

#### derived_spec_operator 副表

```sql
CREATE TABLE derived_spec_operator (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    operator_name TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    operator_semantic_hash TEXT NULL,   -- Phase 2 预留
    PRIMARY KEY (entity_type, entity_id, version, operator_name),
    FOREIGN KEY (entity_type, entity_id, version)
        REFERENCES derived_spec(entity_type, entity_id, version)
        ON DELETE CASCADE
);

CREATE INDEX idx_dso_operator
ON derived_spec_operator(operator_name, operator_version);

CREATE INDEX idx_dso_spec
ON derived_spec_operator(entity_type, entity_id, version);
```

#### compiled_expression_operator（来自 ADR-039）

```sql
CREATE TABLE compiled_expression_operator (
    cache_key TEXT NOT NULL,
    operator_name TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    operator_semantic_hash TEXT NULL,
    PRIMARY KEY (cache_key, operator_name),
    FOREIGN KEY (cache_key) REFERENCES compiled_expression_cache(cache_key) ON DELETE CASCADE
);

CREATE INDEX idx_ceo_operator
ON compiled_expression_operator(operator_name, operator_version);
```

---

### D-6: 算子指纹计算

| 属性 | 值 |
|------|------|
| **Phase 1（本期）** | `sha256(sorted[(op_name, op_version)])` |
| **Phase 2（未来）** | `sha256(sorted[(op_name, op_version, op_semantic_hash)])` |

**Phase 1 约束**：
1. 所有算子注册必须强制声明 `version: str`，不能为空，不能隐式默认
2. 算子语义改动但没单独 bump operator_version，必须 bump `engine_codegen_version`

---

### D-7: 算子升级影响分析流程

```
1. 算子版本变更（如 ts_mean: 1.0.0 → 1.1.0）

2. 查询受影响的 Spec
   SELECT DISTINCT entity_type, entity_id, version
   FROM derived_spec_operator
   WHERE operator_name = 'ts_mean' AND operator_version = '1.0.0';

3. 对于每个受影响的 Spec
   a. 重新编译（触发 operator_fingerprint 变化）
   b. 新编译产物自动使用新算子版本
   c. 旧缓存因 fingerprint mismatch 自然 miss

4. 后台 GC 清理旧缓存
```

---

## 与其他 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-039](adr-039-expression-cache-persistence.md) | 被依赖：算子版本进入 `operator_fingerprint` |
| [ADR-014](adr-014-expression-engine-core.md) | 扩展：Analyzer 增加 `operator_names` |
| [ADR-010](../adr-010-catalog-schema.md) | 参考：`derived_dependency` 副表模式 |
| [ADR-032](../core/adr-032-unified-derived-semantic-model.md) | 扩展：`DerivedSpec.operator_versions` |

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **版本号格式** | SemVer（严格三段式 `1.0.0`） |
| **升级规则** | 四分法：MAJOR / MINOR / PATCH / NO BUMP |
| **变更日志** | 结构化 `ChangeRecord`，append-only |
| **依赖提取** | Analyzer 阶段，产出 `operator_names` |
| **Spec 级存储** | `operator_versions` 快照 + `derived_spec_operator` 副表 |
| **Cache 级存储** | `compiled_expression_operator` side table |
| **算子指纹** | Phase 1: `sha256(sorted[(op_name, op_version)])` |

---

## 实现清单

### 新增文件

| 文件路径 | 用途 |
|---------|------|
| `packages/analytics/src/ditto_analytics/expression/ops/versioning.py` | 版本号校验与比较 |
| `packages/analytics/src/ditto_analytics/expression/ops/changelog.py` | ChangeRecord 模型与存储 |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `packages/analytics/src/ditto_analytics/expression/ops/registry.py` | 强制 `version` 声明，增加 `changelog` |
| `packages/kernel/src/ditto_kernel/specs.py` | 增加 `operator_versions` 字段 |
| `packages/analytics/src/ditto_analytics/expression/analyzer.py` | 产出 `operator_names` |
| `packages/data/src/ditto_data/stores/catalog/schema.py` | 增加 `derived_spec_operator` 表 |

---

## 更新记录

### 2026-03-12
- 初始版本
- 定义 SemVer 四分法升级规则
- 定义三层存储架构（运行时 → Spec → Cache）
- 定义 `derived_spec_operator` 副表 Schema
