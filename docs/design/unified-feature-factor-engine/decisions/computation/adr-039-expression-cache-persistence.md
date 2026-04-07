# ADR-039: 表达式缓存持久化策略

**状态**: ✅ 已决策（2026-03-12）

---

## 背景

表达式编译是因子计算的关键路径，每次编译涉及：
1. 词法/语法分析
2. AST 构建
3. 语义检查
4. Polars Expr 代码生成

当前 ADR-014 定义了内存缓存方案（Spec 级 + CSE 子表达式缓存），但缺少持久化层：
- 服务重启后需要重新编译所有表达式
- 无编译结果复用机制
- 热启动时间长

本 ADR 定义表达式缓存的两级持久化架构。

**关联 ADR**：
- 扩展 [ADR-014: 表达式引擎核心设计](adr-014-expression-engine-core.md)
- 依赖 [ADR-032: 统一派生语义模型](../core/adr-032-unified-derived-semantic-model.md)
- 关联 [ADR-043: Role/Profile Certification 与 Compatibility Manifest](../research/adr-043-role-profile-certification-compatibility-manifest.md)
- 历史前序见 [optimization-backlog](../archive/optimization-backlog.md)（该 backlog 已归档，仅保留设计演化记录）

---

## 决策记录

### D-1: 缓存架构

| 属性 | 值 |
|------|------|
| **L1 缓存** | 进程内内存缓存（DataCache） |
| **L2 缓存** | SQLite 持久化缓存 |
| **缓存对象** | 编译产物 artifact（非 Python Expr 实例） |
| **L2 范围** | 只缓存 spec-level compiled expression |
| **CSE 范围** | 仅 L1 内存，不持久化 |
| **存储路径** | `paths.cache_subdir("engine/expressions.db")` |

**架构图**：

```
┌─────────────────────────────────────────────────────────────┐
│              Two-Tier Expression Cache                       │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ L1: 内存缓存（热数据）                                    ││
│  │                                                          ││
│  │ ┌─────────────────────────────────────────────────────┐ ││
│  │ │ DataCache[CompiledExpression] (复用现有组件)         │ ││
│  │ │ - Spec 级缓存：cache_key → CompiledExpression       │ ││
│  │ │ - CSE 子表达式缓存：独立 dict，仅内存                │ ││
│  │ │ - TTL + LRU（由 cachebox 提供）                      │ ││
│  │ └─────────────────────────────────────────────────────┘ ││
│  └─────────────────────────────────────────────────────────┘│
│                           ↕                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ L2: 磁盘缓存（Versioned Compiled Artifact）              ││
│  │                                                          ││
│  │ 路径: paths.cache_subdir("engine/expressions.db")       ││
│  │                                                          ││
│  │ 主表: compiled_expression_cache                          ││
│  │ 副表: compiled_expression_operator                       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**决策理由**：
- **L1 复用现有组件**：`DataCache` 已支持 TTL + LRU + pattern invalidate，无需重复造轮
- **L2 用 SQLite**：单文件管理简单、支持 TTL 查询、元数据索引、与项目技术栈一致
- **CSE 不持久化**：跨 session 落盘子表达式缓存，复杂度高于收益
- **路径遵循 XDG**：使用 `cache_subdir` 体系，不混入 metadata 主库

---

### D-2: 缓存键设计（双键模型）

| 属性 | 值 |
|------|------|
| **键模型** | 双键模型（compile_input_hash + compiler_fingerprint） |
| **最终 cache_key** | `sha256(f"{compile_input_hash}:{compiler_fingerprint}")` |

**为什么拆分**：
- `spec_hash` 更接近"catalog 版本去重键"，包含 description 等人类可读字段
- 直接用 spec_hash 做编译缓存主键，改描述文本都会让缓存失效
- 拆分后："表达式语义变了"和"编译器实现变了"责任清晰

#### D-2.1: compile_input_hash（语义输入哈希）

**包含内容**：

| 字段 | 说明 |
|------|------|
| canonical expression | 规范化后的表达式 AST |
| entity_keys | 实体键（如 `["instrument_id"]`） |
| grain + effective_time_keys | 时间粒度和时间键 |
| calendar | 交易日历 |
| per-spec 语义开关 | 真正影响 codegen 的字段 |

**不包含**：
- `timezone`（由 calendar 推导）
- `description` / `owner` / `created_at` / `updated_at`
- catalog 层的 publication/version/run 信息

#### D-2.2: compiler_fingerprint（编译器指纹）

**包含内容**：

| 字段 | 说明 |
|------|------|
| compiler_schema_version | 缓存 schema 版本 |
| engine_codegen_version | 代码生成器版本 |
| analysis_version | 分析器版本（lookback/requires_full_day 传播规则） |
| polars_version | Polars 库版本 |
| expr_serialization_format | 序列化格式（如 `polars-binary-v1`） |
| operator_fingerprint | 算子指纹聚合 |
| global_compile_flags | 全局编译开关 |

**代码示例**：

```python
from pydantic import BaseModel

class CompilerRuntimeManifest(BaseModel):
    """编译器运行时环境清单"""
    compiler_schema_version: str
    engine_codegen_version: str
    analysis_version: str
    polars_version: str
    expr_serialization_format: str  # "polars-binary-v1"
    operator_fingerprint: str
    global_flags: dict[str, str | bool | int]


class CompileIdentity(BaseModel):
    """编译身份标识"""
    compile_input_hash: str
    compiler_fingerprint: str

    @property
    def cache_key(self) -> str:
        return sha256(f"{self.compile_input_hash}:{self.compiler_fingerprint}")
```

---

### D-3: 算子指纹

| 属性 | 值 |
|------|------|
| **Phase 1（本期）** | `sha256(sorted[(op_name, op_version)])` |
| **Phase 2（P1-2）** | `sha256(sorted[(op_name, op_version, op_semantic_hash)])` |
| **side table 存储** | operator_name + operator_version + operator_semantic_hash（预留） |

**Phase 1 约束**：
1. **所有算子注册必须强制声明 `version: str`**，不能为空，不能隐式默认
2. **算子语义改动但没单独 bump operator_version**，必须 bump `engine_codegen_version`

**决策理由**：
- Phase 1 已满足缓存正确性主路径
- Phase 2 的"代码哈希"落地成本高：hash 哪一层代码？边界不稳定
- 语义变更（如 `closed="left"`）更适合由 `operator_version` 或 `engine_codegen_version` 承担
- 当前 `engine/ops/registry.py` 尚未落地，先定低耦合协议更合适

---

### D-4: Schema 设计

#### 主表：compiled_expression_cache

```sql
CREATE TABLE compiled_expression_cache (
    cache_key TEXT PRIMARY KEY,
    compile_input_hash TEXT NOT NULL,
    compiler_fingerprint TEXT NOT NULL,
    expr_format TEXT NOT NULL,          -- "polars-binary-v1"
    expr_payload BLOB NOT NULL,         -- expr.meta.serialize()
    analysis_json BLOB NOT NULL,        -- deps/lookback/requires_full_day...
    created_at INTEGER NOT NULL,
    last_access_at INTEGER NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    artifact_size INTEGER NOT NULL
);

CREATE INDEX idx_cec_input_hash ON compiled_expression_cache(compile_input_hash);
CREATE INDEX idx_cec_last_access ON compiled_expression_cache(last_access_at);
```

#### 副表：compiled_expression_operator

```sql
CREATE TABLE compiled_expression_operator (
    cache_key TEXT NOT NULL,
    operator_name TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    operator_semantic_hash TEXT NULL,   -- Phase 2 预留
    PRIMARY KEY (cache_key, operator_name),
    FOREIGN KEY (cache_key) REFERENCES compiled_expression_cache(cache_key) ON DELETE CASCADE
);

CREATE INDEX idx_ceo_operator
ON compiled_expression_operator(operator_name, operator_version);
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `cache_key` | `sha256(compile_input_hash + compiler_fingerprint)` |
| `compile_input_hash` | 语义输入哈希（用于 trace） |
| `compiler_fingerprint` | 编译器指纹（用于正确性 miss） |
| `expr_format` | 序列化格式标识 |
| `expr_payload` | `expr.meta.serialize()` 二进制 |
| `analysis_json` | 分析结果 JSON |
| `operator_semantic_hash` | Phase 2 预留，本期 NULL |

---

### D-5: 失效规则

| 机制 | 说明 |
|------|------|
| **正确性** | `compiler_fingerprint` mismatch → 自然 miss |
| **清理** | TTL + size-based GC（后台） |
| **side table 用途** | 按算子版本做定点扫描和批量清理 |

**失效流程**：

```
1. 查询 L1 内存缓存
   ├─ 命中 → 直接返回
   └─ miss → 查 L2 SQLite

2. 查询 L2 SQLite
   ├─ cache_key 命中
   │   ├─ compiler_fingerprint 匹配 → 反序列化，回填 L1，更新 last_access_at/hit_count
   │   └─ compiler_fingerprint 不匹配 → miss（懒失效）
   └─ miss → 重新编译并写入 L1 + L2

3. 后台 GC（定期）
   ├─ last_access_at < now - 30d
   └─ 超出 max_entries / max_db_size_mb
```

**决策理由**：
- 不要求版本变更时立即全表删除
- 正确性由 fingerprint 保证，TTL 只负责回收垃圾
- 比"变更时主动全删"更稳，实现更简单

---

### D-6: 序列化格式

| 属性 | 值 |
|------|------|
| **优先格式** | Polars binary（`expr.meta.serialize()`） |
| **格式标识** | `polars-binary-v1` |
| **跨版本稳定** | ❌ 不保证（Polars 文档明确说明） |
| **版本兼容** | 通过 `polars_version` 在 fingerprint 中保证 |

**代码示例**：

```python
import polars as pl

# 序列化
expr: pl.Expr = pl.col("close").rolling_mean(window_size=20)
payload: bytes = expr.meta.serialize()

# 反序列化
restored: pl.Expr = pl.Expr.deserialize(payload)
```

**决策理由**：
- 二进制比 JSON 更小
- Polars 1.38.1 已验证支持序列化/反序列化
- 不保证跨版本稳定，所以 `polars_version` 必须在 fingerprint 中

---

### D-7: `compiler_fingerprint` 不等于发布级 `CompatibilityManifest`

| 维度 | `compiler_fingerprint` | `CompatibilityManifest` |
|------|------------------------|-------------------------|
| **职责** | 缓存正确性与自然 miss | 发布、回放、shadow compare 的环境可解释性 |
| **范围** | 尽量紧凑，只覆盖编译正确性必需字段 | 可更完整，允许记录 builder/time semantics 等扩展字段 |
| **使用位置** | L1/L2 缓存键 | artifact metadata / publication record / dataset snapshot |
| **变化后果** | mismatch → cache miss | 差异需显式可见、可审计，不必然阻断 compare/promote |

**约束**：

1. 不要把 `CompatibilityManifest` 直接当作缓存键，否则缓存失效面会被无关字段放大。
2. `CompatibilityManifest` 可以复用 `CompilerRuntimeManifest` 的子集，但必须补足发布/回放所需字段，如 `time_semantics_version`、`builder_version`。
3. 后续 artifact / publication / dataset snapshot 写出时，应从编译运行时清单派生 manifest，而不是反向从缓存层组装。

---

## 非目标

| 项目 | 原因 |
|------|------|
| 多实例共享缓存 | 本期各自独立，不需要分布式 |
| 分布式缓存 | 单实例场景无需 Redis 等 |
| 持久化 CSE | 复杂度高于收益 |
| SQLite 作为长期 ABI 仓库 | Polars 升级后自然 miss |

---

## 决策汇总

| 决策点 | 决策 |
|-------|------|
| **缓存架构** | L1 内存（DataCache） + L2 SQLite |
| **缓存对象** | 编译产物 artifact（非 Python Expr） |
| **CSE 范围** | 仅 L1，不持久化 |
| **缓存键** | 双键模型：`compile_input_hash` + `compiler_fingerprint` |
| **算子指纹** | Phase 1: `op_name + op_version` |
| **序列化格式** | Polars binary（`expr.meta.serialize()`） |
| **失效策略** | 懒失效（fingerprint mismatch）+ 后台 GC |
| **存储路径** | `paths.cache_subdir("engine/expressions.db")` |
| **职责边界** | `compiler_fingerprint` 仅服务缓存；发布兼容契约由 ADR-043 定义 |

---

## 与其他 ADR 的关系

| ADR | 关系 |
|-----|------|
| [ADR-014](adr-014-expression-engine-core.md) | 扩展：添加 L2 持久化层 |
| [ADR-032](../core/adr-032-unified-derived-semantic-model.md) | 依赖：`DerivedSpec` 字段定义 |
| [ADR-038](adr-038-operator-versioning.md) | 前置：算子版本管理（P1-2） |
| [ADR-043](../research/adr-043-role-profile-certification-compatibility-manifest.md) | 区分缓存指纹与发布级 compatibility manifest |

---

## 实现清单

### 新增文件

| 文件路径 | 用途 |
|---------|------|
| `packages/analytics/src/ditto_analytics/expression/cache/__init__.py` | 缓存模块入口 |
| `packages/analytics/src/ditto_analytics/expression/cache/expression_cache.py` | Two-Tier 缓存实现 |
| `packages/analytics/src/ditto_analytics/expression/cache/schema.py` | 缓存键模型定义 |
| `packages/analytics/src/ditto_analytics/expression/cache/persistence.py` | SQLite 持久化层 |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `packages/analytics/src/ditto_analytics/expression/ops/registry.py` | 强制算子声明 version |
| `packages/analytics/src/ditto_analytics/publish/manifest.py` | 后续从编译运行时清单派生 compatibility manifest |

---

## 更新记录

### 2026-03-12
- 初始版本，定义 Two-Tier 缓存架构
- 采用双键模型（compile_input_hash + compiler_fingerprint）
- 选定 Phase 1 算子指纹方案

### 2026-03-13
- 明确 `compiler_fingerprint` 只服务缓存正确性
- 与 ADR-043 对齐：发布与回放环境契约由 `CompatibilityManifest` 承担
