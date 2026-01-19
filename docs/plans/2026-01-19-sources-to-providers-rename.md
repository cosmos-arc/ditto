# Sources → Providers 目录重命名计划

## 任务概述

Phase 9 完成了 `DataSource` → `DataProvider` 的类名重命名，但遗漏了：
1. **sources 目录本身** 未重命名为 providers
2. **文档和注释** 中的 sources 路径引用未更新
3. **架构分层违反**：`stores/ingestion_log.py` 导入 `sources/metadata.py`

**关键约束**：不允许使用延迟导入解决循环依赖，必须通过架构解决。

本计划先解决架构问题（Phase 0），再完成目录重命名（Phase 1-6）。

---

## 架构问题分析

### 当前问题

```
stores/ingestion_log.py ──import──> sources/metadata.py
     ↑                                      ↓
   (低层)                                (高层)
```

**违反分层原则**：stores 层不应导入 sources 层。

### 解决方案：创建 models 模块

```
                    models/ingestion.py
                          ↑        ↑
                         /          \
                        /            \
stores/ingestion_log.py    sources/metadata.py
     (低层)                    (高层)
```

将 `IngestionLog`、`IngestionStatus` 等共享数据模型移至独立的 `models/` 模块。

---

## 重命名映射

| 类型 | 旧名称 | 新名称 |
|------|--------|--------|
| 目录 | `sources/` | `providers/` |
| 模块 | `ditto_datahub.sources.*` | `ditto_datahub.providers.*` |
| 文档引用 | `sources/` | `providers/` |
| 共享模型 | `sources/metadata.py` | `models/ingestion.py` |

---

## 分阶段实施

### Phase 0: 架构重构 - 创建 models 模块

**目标**：解决 stores → sources 的架构分层违反问题

#### 0.1 创建 models 模块

```bash
mkdir -p packages/datahub/src/ditto_datahub/models
```

#### 0.2 移动 metadata.py → models/ingestion.py

```bash
cd packages/datahub/src/ditto_datahub
git mv sources/metadata.py models/ingestion.py
```

#### 0.3 创建 models/__init__.py

```python
"""Shared data models for DataHub."""

from ditto_datahub.models.ingestion import (
    IngestionCursor,
    IngestionLog,
    IngestionStatus,
)

__all__ = [
    "IngestionLog",
    "IngestionStatus",
    "IngestionCursor",
]
```

#### 0.4 更新导入语句（约15个文件）

**源代码**：
- `packages/datahub/src/ditto_datahub/sources/provider.py`（延迟导入）
- `packages/datahub/src/ditto_datahub/sources/__init__.py`
- `packages/datahub/src/ditto_datahub/stores/ingestion_log.py`

**Apps 层**：
- `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- `apps/port/src/ditto_port/services/ingestion/metadata.py`

**测试文件**（约10个）：
- `packages/datahub/tests/unit/sources/test_accessor_unit.py`
- `packages/datahub/tests/unit/stores/test_ingestion_log_store_unit.py`
- `packages/datahub/tests/integration/stores/test_ingestion_log_concurrent_integration.py`
- 其他相关测试文件

**导入替换模式**：
```python
# 旧
from ditto_datahub.sources.metadata import IngestionLog, IngestionStatus

# 新
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
```

#### 0.5 更新 sources 层的导入

由于 `sources/metadata.py` 已移至 `models/`，sources 层需要更新：

**`sources/__init__.py`**：
```python
# 添加
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus, IngestionCursor
```

#### 验证步骤

```bash
# 1. 确认无循环依赖
pixi run -e dev python -c "from ditto_datahub import DataHub; print('OK')"

# 2. 运行测试
pixi run -e dev pytest packages/datahub/tests/unit/ -v

# 3. 类型检查
pixi run -e dev type
```

---

### Phase 1: 源代码目录重命名

**目录重命名**（使用 `git mv`）：
```bash
cd packages/datahub/src/ditto_datahub
git mv sources providers
```

**更新导入**（7个文件）：
- `packages/datahub/src/ditto_datahub/providers/__init__.py`
- `packages/datahub/src/ditto_datahub/providers/provider.py`
- `packages/datahub/src/ditto_datahub/providers/tushare/tushare_provider.py`
- `packages/datahub/src/ditto_datahub/providers/tushare/client.py`
- `packages/datahub/src/ditto_datahub/providers/tushare/http_utils.py`
- `packages/datahub/src/ditto_datahub/providers/tushare/__init__.py`
- `packages/datahub/src/ditto_datahub/hub.py`

**导入替换模式**：`from ditto_datahub.sources.*` → `from ditto_datahub.providers.*`

**验证**：
```bash
pixi run -e dev pytest packages/datahub/tests/unit/ -v
pixi run -e dev type
```

---

### Phase 2: 测试目录重命名

**目录重命名**：
```bash
cd packages/datahub/tests/unit
git mv sources providers

cd packages/datahub/tests/integration
git mv sources providers
```

**更新测试导入**（10个文件）：
- `packages/datahub/tests/unit/providers/test_accessor_unit.py`
- `packages/datahub/tests/unit/providers/test_base_unit.py`
- `packages/datahub/tests/unit/providers/tushare/test_client_unit.py`
- `packages/datahub/tests/unit/providers/tushare/test_transformer_unit.py`
- `packages/datahub/tests/unit/providers/tushare/test_rate_limiter_unit.py`
- `packages/datahub/tests/unit/providers/tushare/test_source_unit.py`
- `packages/datahub/tests/unit/providers/tushare/test_http_utils_unit.py`
- `packages/datahub/tests/integration/providers/tushare/test_end_to_end_integration.py`
- `packages/datahub/tests/unit/stores/test_ingestion_log_store_unit.py`
- `packages/datahub/tests/integration/stores/test_ingestion_log_concurrent_integration.py`

**更新测试 README**（2个）：
- `packages/datahub/tests/unit/providers/README.md`
- `packages/datahub/tests/integration/providers/README.md`

**验证**：
```bash
pixi run -e dev pytest packages/datahub/tests/ -v -m "not external"
```

---

### Phase 3: Apps 层更新

**更新导入**（3个文件）：
- `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- `apps/port/src/ditto_port/services/ingestion/metadata.py`
- `apps/port/tests/integration/ingestion/test_coordinator_dq_blocking_integration.py`

**更新 README**：
- `apps/port/README.md`

**验证**：
```bash
pixi run -e dev pytest apps/port/tests/ -v -m "not external"
```

---

### Phase 4: 文档更新

**设计文档**（2个）：
- `docs/design/01_system_design.md`
- `docs/design/02_data_design.md`

**Sprint 文档**（2个）：
- `docs/sprints/sprint-01-data-foundation.md`
- `docs/sprints/sprint-02-data-quality.md`

**计划文档**（3个）：
- `docs/plans/2026-01-17-architecture-refactor-plan.md`
- `docs/plans/2026-01-18-repository-accessor-completion.md`
- `docs/reviews/2026-01-18-architecture-audit.md`

**README 文件**（5个）：
- `packages/datahub/src/ditto_datahub/providers/README.md`
- `packages/datahub/README.md`
- `packages/datahub/tests/unit/providers/README.md`
- `packages/datahub/tests/integration/providers/README.md`
- `packages/datahub/tests/README.md`

---

### Phase 5: 代码注释更新

**源代码文件**：
- `packages/datahub/src/ditto_datahub/hub.py`（第53、223行）

**Providers 文件**：
- `packages/datahub/src/ditto_datahub/providers/provider.py`
- `packages/datahub/src/ditto_datahub/providers/tushare/*.py`

---

### Phase 6: 最终验证

```bash
# 1. 完整测试
pixi run -e dev test --fast

# 2. 类型检查
pixi run -e dev type --all

# 3. 代码检查
pixi run -e dev lint

# 4. 残留检查
grep -r "from ditto_datahub\.sources" packages/ apps/ --include="*.py"
grep -r "sources/" docs/ packages/ --include="*.md" | grep -v "providers/"
```

---

## 关键文件清单

### Phase 0: 创建 models 模块
- **新建**：`packages/datahub/src/ditto_datahub/models/__init__.py`
- **移动**：`sources/metadata.py` → `models/ingestion.py`
- **更新导入**：约15个文件（源代码 + Apps + 测试）

### Phase 1-6: 目录重命名
**需要重命名的目录（3个）**：
- `packages/datahub/src/ditto_datahub/sources/`
- `packages/datahub/tests/unit/sources/`
- `packages/datahub/tests/integration/sources/`

**需要更新导入的文件（约20个）**：
- 源代码：7个
- 测试：10个
- Apps：3个

**需要更新的文档（约15个）**：
- 设计文档：2个
- Sprint 文档：2个
- 计划文档：3个
- README：5个

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| **循环依赖** | **Phase 0 创建 models 模块解决架构分层违反** |
| 导入错误 | 每个 Phase 后运行测试验证 |
| 文档不一致 | 代码和文档同步更新 |
| Git 历史丢失 | 使用 `git mv` 保留文件历史 |

---

## 成功标准

- [x] **架构健康**：无循环依赖，stores 不导入 providers
- [ ] 所有测试通过（100%）
- [ ] pyright 类型检查通过（0 errors）
- [ ] ruff 代码检查通过
- [ ] 无残留的 `from ditto_datahub.sources.` 引用（代码中）
- [ ] 无残留的 `sources/` 路径引用（文档中，排除 `data_sources/` 等合法词）
- [ ] `models/` 模块正确创建并导出共享数据模型
