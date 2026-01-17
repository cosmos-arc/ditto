# 模型类与 DTO 规范重构设计文档

## 概述

本文档详细描述了模型类与数据传输对象（DTO）规范重构的四阶段执行计划，旨在统一项目中 dataclass 与 Pydantic 的使用边界，规范包结构，并提升代码可维护性。

## 背景

### 现状问题

1. **工具混用不一致**：`IngestionResult` 用 dataclass，`BackfillResult` 用 Pydantic
2. **包结构分散**：结果模型散落在各自模块中
3. **缺乏明确规范**：没有文档说明何时用 dataclass vs Pydantic
4. **命名混淆**：`types.py` 与 `config` 命名不够清晰

### 核心设计原则

```
┌─────────────────────────────────────────────────────────────────┐
│  决策标准：数据的来源和流向                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  外部 ────────────────────────────────────────────► 内部        │
│         (Pydantic: 验证 + 转换 + 清洗)              │
│                                                                 │
│  内部 ────────────────────────────────────────────► 内部        │
│         (dataclass: 轻量传输)                     │
│                                                                 │
│  内部 ────────────────────────────────────────────► 外部        │
│         (可选 Pydantic: 序列化成 JSON)            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**简化规则**：
- `Pydantic = 外部边界的数据守门员`
- `dataclass = 内部世界的数据载体`

---

## 第一阶段：更新规约文档

### 目标

在 `.claude/rules/core.md` 中添加"模型类与 DTO 规范"章节。

### 规范内容

#### 1. dataclass vs Pydantic 使用边界

| 场景 | 使用类型 | 示例 | 理由 |
|------|----------|------|------|
| **内部运行时数据传输** | frozen dataclass | `WriteResult`, `IngestionResult` | 可信数据，追求性能 |
| **不可变数据结构** | frozen dataclass | `FreezeManifest`, `IngestionCursor` | 使用 `frozen=True` 确保安全 |
| **简单数据容器** | frozen dataclass | `CacheStats`, `ResultCounts` | 无需验证逻辑 |
| **接收外部输入** | Pydantic | API 请求体、用户输入 | 需要验证和类型转换 |
| **环境变量配置** | Pydantic BaseSettings | `Settings`, `DatabaseSettings` | BaseSettings 自动加载 |
| **配置文件解析** | Pydantic | `DQSpec`, `DatasetSpec` (YAML/JSON) | 复杂验证、默认值、别名 |
| **API 响应** | Pydantic | FastAPI 响应模型 | FastAPI 集成、JSON Schema |

#### 2. 命名规范

| 用途 | 命名后缀 | 示例 |
|------|---------|------|
| **系统配置** | `Settings` | `DatabaseSettings`, `APISettings` |
| **数据集规格** | `Spec` | `DQSpec`, `DatasetSpec` |
| **功能选项** | `Options` | `WriteOptions`, `ParserOptions` |
| **运行参数** | `Params` | `BackfillParams`, `QueryParams` |
| **运行时结果** | `Result` | `WriteResult`, `IngestionResult` |
| **统计数据** | `Stats` | `CacheStats` |
| **元数据** | `Info` | `VersionInfo` |

#### 3. 包结构规范

- **取消顶层 `types.py`**：避免与 Python 内置 `types` 模块混淆
- **统一使用 `models/` 包**：所有模型类集中管理
- **按域分组**：在 `models/` 下按业务域分文件

#### 4. 强制约束

**dataclass 约束**：
- 所有 dataclass 必须使用 `frozen=True`（除非有明确理由）
- 禁止混用：不要同时继承 `BaseModel` 和使用 `@dataclass`

**Pydantic 约束**：
- Pydantic 模型配置 `strict=True`（Python 3.12+）
- 只在数据边界使用，内部数据传输优先 dataclass

### 验收标准

- [ ] `.claude/rules/core.md` 新增"模型类与 DTO 规范"章节
- [ ] 章节包含上述四部分内容
- [ ] 文档描述清晰、无歧义

---

## 第二阶段：重组包结构

### 目标

创建新的 `models/` 目录并迁移模型类。

### 变更清单

#### DataHub 层（packages/datahub）

| 操作 | 源位置 | 目标位置 | 说明 |
|------|--------|----------|------|
| 创建目录 | - | `packages/datahub/src/ditto_datahub/models/` | 新建 models 包 |
| 迁移枚举 | `types.py` | `models/common.py` | `OnDuplicate`, `DQSeverity`, `SidRange` |
| 迁移存储模型 | `types.py` | `models/storage.py` | `WriteResult`, `WriteResultStore`, `FreezeManifest` |
| 迁移 DQ 配置 | `dq/models.py` | `models/quality.py` | `DQConfig` → `DQSpec`, `DQResult`, `DQIssue` |
| 创建导出 | `models/__init__.py` | - | 统一导出所有公共类 |
| 过渡兼容 | 保留 `types.py` | - | 添加 DeprecationWarning |

#### Port 层（apps/port）

| 操作 | 源位置 | 目标位置 | 说明 |
|------|--------|----------|------|
| 创建目录 | - | `apps/port/src/ditto_port/models/` | 新建 models 包 |
| 迁移结果类 | `common/types.py` | `models/ingestion.py` | `IngestionResult`, `ResultCounts` |
| 迁移配置类 | `config/datasets.py` | `models/config.py` | `DatasetConfig` → `DatasetSpec` |
| 创建导出 | `models/__init__.py` | - | 统一导出所有公共类 |
| 过渡兼容 | 保留 `common/types.py` | - | 添加 DeprecationWarning |

### 目录结构

```
packages/datahub/src/ditto_datahub/
├── models/                      # 新建
│   ├── __init__.py             # 统一导出
│   ├── common.py               # 枚举、NamedTuple
│   ├── storage.py              # WriteResult, FreezeManifest
│   ├── quality.py              # DQSpec, DQResult, DQIssue
│   └── ingestion.py            # IngestionLog, IngestionCursor（如有）
├── types.py                    # 保留，添加 DeprecationWarning
└── dq/
    └── models.py               # 保留或迁移后删除

apps/port/src/ditto_port/
├── models/                      # 新建
│   ├── __init__.py             # 统一导出
│   ├── ingestion.py            # IngestionResult, ResultCounts
│   ├── backfill.py             # BackfillResult（Pydantic → dataclass）
│   ├── retry.py                # RetryResult（Pydantic → dataclass）
│   └── config.py               # DatasetSpec
├── common/
│   └── types.py                # 保留，添加 DeprecationWarning
```

### 验收标准

- [ ] 新建 `models/` 目录并创建 `__init__.py`
- [ ] 模型类正确迁移到新位置
- [ ] 原文件添加 DeprecationWarning 兼容层
- [ ] 所有现有测试通过
- [ ] 通过 pyright、ruff 检查

---

## 第三阶段：代码重构

### 目标

Pydantic → dataclass 转换 + 重命名。

### 变更清单

#### 重命名

| 原类名 | 新类名 | 原类型 | 新类型 | 原位置 | 新位置 |
|--------|--------|--------|--------|--------|--------|
| `DQConfig` | `DQSpec` | Pydantic | Pydantic | `dq/models.py` | `models/quality.py` |
| `DatasetConfig` | `DatasetSpec` | Pydantic | Pydantic | `config/datasets.py` | `models/config.py` |
| `T1ConfigParams` | `T1BackfillParams` | 待确认 | 待确认 | 待查找 | 待查找 |

#### 类型转换

| 原类名 | 原类型 | 新类型 | 新位置 | 说明 |
|--------|--------|--------|--------|------|
| `BackfillResult` | Pydantic BaseModel | frozen dataclass | `models/ingestion.py` | 内部结果无需 Pydantic |
| `RetryResult` | Pydantic BaseModel | frozen dataclass | `models/ingestion.py` | 内部结果无需 Pydantic |

### 转换示例

```python
# 原代码（Pydantic）
class BackfillResult(BaseModel):
    """回补结果统计。"""
    dataset: str
    total_dates: int
    success_count: int
    skipped_count: int
    failed_count: int
    results: list[IngestionResult]

# 新代码（frozen dataclass）
@dataclass(frozen=True)
class BackfillResult:
    """回补结果统计。"""
    dataset: str
    total_dates: int
    success_count: int
    skipped_count: int
    failed_count: int
    results: tuple[IngestionResult, ...]  # 不可变容器
```

### 更新导入

需要更新所有引用这些类的文件：

1. `backfill.py` - 更新 `BackfillResult` 导入
2. `retry.py` - 更新 `RetryResult` 导入
3. 所有使用 `DQConfig` 的文件 → `DQSpec`
4. 所有使用 `DatasetConfig` 的文件 → `DatasetSpec`

### 验收标准

- [ ] `BackfillResult` 和 `RetryResult` 转换为 frozen dataclass
- [ ] `DQConfig` 重命名为 `DQSpec`
- [ ] `DatasetConfig` 重命名为 `DatasetSpec`
- [ ] 所有导入语句更新
- [ ] 所有现有测试通过
- [ ] 通过 pyright、ruff 检查

---

## 第四阶段：清理废弃代码

### 目标

移除过渡期兼容代码和旧文件。

### 操作清单

1. **移除 DeprecationWarning 兼容层**
   - `packages/datahub/src/ditto_datahub/types.py`
   - `apps/port/src/ditto_port/common/types.py`

2. **删除空的旧文件**（如适用）
   - `packages/datahub/src/ditto_datahub/dq/models.py`（如果已迁移）

3. **验证导入**
   - 确保所有文件从 `models/` 导入
   - 无遗留的旧路径导入

### 验收标准

- [ ] 移除所有 DeprecationWarning 兼容代码
- [ ] 删除已迁移的旧文件
- [ ] 所有导入统一使用 `from xxx.models import`
- [ ] 所有测试通过
- [ ] 通过 pyright、ruff、ci-check

---

## 总体验证标准

1. ✅ 所有模型类从 `models/` 包统一导入
2. ✅ Pydantic 只用于外部数据边界
3. ✅ 内部数据传输统一使用 frozen dataclass
4. ✅ 命名符合规范（Settings/Spec/Options/Params/Result）
5. ✅ 通过 pyright、ruff 检查
6. ✅ 所有测试通过

---

## 执行方式

**推荐方式**：`superpowers:subagent-driven-development`

**理由**：
- 任务存在**顺序依赖**：文档 → 包结构 → 代码重构 → 清理
- 修改涉及**共享状态**：导入语句需要协调更新
- **不适合并行**：迁移函数签名 + 更新调用方是强依赖关系

## 参考资料

- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [Structuring a FastAPI Project: Best Practices](https://dev.to/mohammad222pr/structuring-a-fastapi-project-best-practices-53l6)
- [Pydantic vs Data Classes: Which Should You Use?](https://zakforster.com/posts/pydantic-vs-dataclasses/)
- [Keep Pydantic out of your Domain Layer](https://news.ycombinator.com/item?id=44656419)
