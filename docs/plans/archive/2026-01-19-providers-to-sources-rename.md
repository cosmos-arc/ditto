# Providers → Sources 统一重命名计划

## 任务概述

将 `providers/` 目录、类名、异常类统一重命名为 `sources/` 相关命名，使语义表达更一致。

**重命名映射**：

| 类型 | 当前名称 | 新名称 |
|------|---------|--------|
| 目录 | `providers/` | `sources/` |
| 文件 | `provider.py` | `source.py` |
| 抽象基类 | `DataSource` | `DataSource` |
| 访问器类 | `DataSources` | `DataSources` |
| 基础异常 | `DataSourceError` | `DataSourceError` |
| 配置异常 | `ProviderConfigurationError` | `SourceConfigurationError` |
| 认证异常 | `ProviderAuthenticationError` | `SourceAuthenticationError` |
| 限流异常 | `ProviderRateLimitError` | `SourceRateLimitError` |
| 获取异常 | `ProviderFetchError` | `SourceFetchError` |
| 转换异常 | `ProviderTransformationError` | `SourceTransformationError` |
| 实现类 | `TushareSource` | `TushareSource` |
| DataHub 属性 | `hub.sources` | `hub.sources` |

---

## 分阶段实施

### Phase 0: 准备工作

1. 确认当前所有测试通过
2. 运行类型检查确认无错误

```bash
pixi run -e dev test --fast
pixi run -e dev type
```

---

### Phase 1: 核心定义重命名

**文件**: `packages/data/src/ditto_data/providers/provider.py`

**操作**: 使用 Edit 工具批量重命名

**类名替换**（按顺序，避免冲突）：
1. `ProviderTransformationError` → `SourceTransformationError`
2. `ProviderFetchError` → `SourceFetchError`
3. `ProviderRateLimitError` → `SourceRateLimitError`
4. `ProviderAuthenticationError` → `SourceAuthenticationError`
5. `ProviderConfigurationError` → `SourceConfigurationError`
6. `DataSourceError` → `DataSourceError`
7. `DataSource` → `DataSource`
8. `DataSources` → `DataSources`

**导入路径**：保持在 `providers/`（Phase 2 再修改路径）

**验证**：
```bash
pixi run -e dev type packages/data/src/ditto_data/providers/provider.py
```

---

### Phase 2: 目录和文件重命名

**2.1 文件重命名**（使用 git mv）:
```bash
cd packages/data/src/ditto_data
git mv providers/provider.py providers/source.py
```

**2.2 目录重命名**:
```bash
# 源代码
git mv providers sources

# 测试目录
cd ../../tests/unit
git mv providers sources

cd ../../integration
git mv providers sources
```

**2.3 更新内部导入**（约 7 个文件）:

**源代码**：
- `packages/data/src/ditto_data/sources/__init__.py`
- `packages/data/src/ditto_data/sources/source.py`
- `packages/data/src/ditto_data/sources/tushare/tushare_source.py`
- `packages/data/src/ditto_data/sources/tushare/client.py`
- `packages/data/src/ditto_data/sources/tushare/http_utils.py`
- `packages/data/src/ditto_data/sources/tushare/__init__.py`
- `packages/data/src/ditto_data/hub.py`

**导入替换模式**：
```python
# 旧
from ditto_data.sources.provider import DataSource

# 新
from ditto_data.sources.source import DataSource
```

**延迟导入需要更新**（`# noqa: PLC0415`）：
```python
# sources/source.py
from ditto_data.sources.tushare.tushare_source import (  # noqa: PLC0415
    TushareSource,
)
```

**验证**：
```bash
pixi run -e dev pytest packages/data/tests/unit/ -v
pixi run -e dev type
```

---

### Phase 3: Apps 层更新

**3.1 更新导入**（约 4 个文件）：

- `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- `apps/port/src/ditto_port/jobs/tasks/t0_meta.py`
- `apps/port/src/ditto_port/jobs/flows/helpers.py`
- `apps/port/src/ditto_port/cli/context.py`

**导入替换**：
```python
# 旧
from ditto_data.sources.provider import DataSource, SourceFetchError

# 新
from ditto_data.sources.source import DataSource, SourceFetchError
```

**3.2 更新 hub 属性访问**：
```python
# 旧
hub.sources.get("tushare")
hub.sources.tushare

# 新
hub.sources.get("tushare")
hub.sources.tushare
```

**验证**：
```bash
pixi run -e dev pytest apps/port/tests/ -v -m "not external"
```

---

### Phase 4: 测试文件更新

**4.1 更新测试导入**（约 12 个文件）：

**单元测试**：
- `packages/data/tests/unit/sources/test_accessor_unit.py`
- `packages/data/tests/unit/sources/test_base_unit.py`
- `packages/data/tests/unit/sources/tushare/test_client_unit.py`
- `packages/data/tests/unit/sources/tushare/test_transformer_unit.py`
- `packages/data/tests/unit/sources/tushare/test_rate_limiter_unit.py`
- `packages/data/tests/unit/sources/tushare/test_source_unit.py`
- `packages/data/tests/unit/sources/tushare/test_http_utils_unit.py`

**集成测试**：
- `packages/data/tests/integration/sources/tushare/test_end_to_end_integration.py`

**Apps 测试**：
- `apps/port/tests/unit/ingestion/test_coordinator_unit.py`
- `apps/port/tests/unit/jobs/flows/test_helpers_unit.py`
- `apps/port/tests/unit/jobs/flows/test_helpers_integration.py`
- `apps/port/tests/unit/jobs/tasks/test_task_factory_unit.py`
- `apps/port/tests/unit/jobs/tasks/test_backfill_unit.py`

**4.2 更新测试 mock 和断言**：

**Mock 路径更新**：
```python
# 旧
mocker.patch("ditto_data.sources.tushare.client._get_tushare_token")
mock_hub.sources.get.return_value = mock_source

# 新
mocker.patch("ditto_data.sources.tushare.client._get_tushare_token")
mock_hub.sources.get.return_value = mock_source
```

**异常断言更新**：
```python
# 旧
assert exc_info.value.details.get("provider") == "tushare"

# 新
assert exc_info.value.details.get("source") == "tushare"
```

**4.3 更新 fixture**：
```python
# apps/port/tests/conftest.py
@pytest.fixture
def mock_datahub() -> MagicMock:
    mock = MagicMock()
    # ...
    mock.sources.get.return_value = MagicMock()  # 改为 sources
    return mock
```

**验证**：
```bash
pixi run -e dev pytest packages/data/tests/ -v -m "not external"
pixi run -e dev pytest apps/port/tests/ -v -m "not external"
```

---

### Phase 5: 文档更新

**5.1 设计文档**（约 4 个文件）：

- `docs/design/01_system_design.md` - 更新架构表、依赖关系图
- `docs/design/02_data_design.md` - 更新代码示例
- `docs/design/05_observability.md` - 如有引用

**5.2 规范文档**（约 3 个文件）：

- `.claude/rules/architecture.md` - 更新层级访问规则
- `.claude/rules/datahub.md` - 更新分层职责表
- `.claude/commands/architecture-audit.py` - 更新审计逻辑

**5.3 README 和示例**（约 5 个文件）：

- `packages/data/README.md`
- `packages/data/src/ditto_data/sources/README.md`
- `packages/data/src/ditto_data/sources/tushare/README.md`
- `packages/data/tests/unit/sources/README.md`
- `packages/data/tests/integration/sources/README.md`

**5.4 计划文档**（标记为历史记录）：

- `docs/plans/2026-01-19-sources-to-providers-rename.md` - 添加说明此计划已撤销

**内容替换模式**：
```markdown
# 旧
providers/、DataSource、hub.sources

# 新
sources/、DataSource、hub.sources
```

---

### Phase 6: 异常 details 字段更新

**重要**: 所有异常类的 `details` 字典中，`"provider"` key 需要改为 `"source"`。

**需要更新的文件**：
- `packages/data/src/ditto_data/sources/source.py` - 异常定义
- `packages/data/src/ditto_data/sources/tushare/http_utils.py` - 异常构造

**更新模式**：
```python
# 旧
details["provider"] = "tushare"

# 新
details["source"] = "tushare"
```

**测试断言同步更新**（已在 Phase 4 中处理）。

---

### Phase 7: 最终验证

**7.1 类型检查**：
```bash
pixi run -e dev type --all
```

**7.2 完整测试**：
```bash
pixi run -e dev test --fast
```

**7.3 代码检查**：
```bash
pixi run -e dev lint
pixi run -e dev fmt --check
```

**7.4 残留检查**：
```bash
# 检查残留的 providers 导入
grep -r "from ditto_data\\.providers" packages/ apps/ --include="*.py"

# 检查残留的 DataSource
grep -r "DataSource" packages/ apps/ --include="*.py"

# 检查文档中的残留引用
grep -r "providers/" docs/ --include="*.md" | grep -v "data_providers"
```

**7.5 Git 状态确认**：
```bash
git status
git diff --stat
```

---

### Phase 8: 残留修复（2026-01-19）

**背景**：Phase 1-7 完成后，发现仍有大量残留未修复，包括：
- 参数名 `provider` 未改为 `source`
- 文档字符串中 "data provider" 未改为 "data source"
- 测试断言中 `error.details["provider"]` 未改为 `error.details["source"]`
- 设计文档中的 `providers/` 路径引用

**批次 1：核心源代码修复**（commit: fbd90f1）
- `packages/data/src/ditto_data/sources/source.py` - 参数名、文档字符串（约 30 处）
- `packages/data/src/ditto_data/sources/tushare/http_utils.py` - 参数 `provider="tushare"` → `source="tushare"`（13 处）
- `packages/data/src/ditto_data/sources/tushare/tushare_source.py` - 文档、日志、参数（6 处）
- `packages/data/src/ditto_data/sources/__init__.py` - 模块文档（1 处）

**批次 2：单元测试修复**（commit: bdbe3ed）
- `packages/data/tests/unit/sources/test_base_unit.py` - 参数、断言、方法名（6 处）
- `packages/data/tests/unit/sources/tushare/test_http_utils_unit.py` - 断言 `error.details["provider"]` → `error.details["source"]`（7 处）
- `packages/data/tests/unit/sources/test_accessor_unit.py` - 变量命名、错误消息（6 处）

**批次 3：设计文档修复**（commit: 3e3e3cb）
- `docs/design/01_system_design.md` - 架构表、目录结构、依赖图（3 处）
- `docs/design/02_data_design.md` - 目录名、导出函数、文件名（4 处）

**验证**：
```bash
pixi run -e dev type
pixi run -e dev pytest packages/data/tests/unit/sources/ -v
```

---

## 关键文件清单

### 需要重命名的文件（3 个）
- `providers/provider.py` → `sources/source.py`
- `providers/tushare/tushare_provider.py` → `sources/tushare/tushare_source.py`
- 测试目录：`providers/` → `sources/`（3 处）

### 需要类名重命名的文件（1 个核心 + 1 个实现）
- `packages/data/src/ditto_data/providers/provider.py`（核心）
- `packages/data/src/ditto_data/providers/tushare/tushare_provider.py`（实现）

### 需要更新导入的文件（约 20+ 个）
**源代码**：7 个
**测试**：12 个
**Apps**：4 个
**文档**：15+ 个

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| **导入错误** | 每个 Phase 后运行测试验证 |
| **类名冲突** | 按顺序重命名（先子类后基类） |
| **文档不一致** | 代码和文档同步更新 |
| **Git 历史丢失** | 使用 `git mv` 保留文件历史 |
| **异常字段变更** | 同步更新测试断言 |

---

## 成功标准

- [x] 所有类名已重命名（DataSource → DataSource）
- [x] 所有目录已重命名（providers/ → sources/）
- [x] 所有测试通过（100%+）
- [x] pyright 类型检查通过（0 errors）
- [x] ruff 代码检查通过
- [x] 无残留的 `from ditto_data.sources.` 引用
- [x] 无残留的 `DataSource` 类名引用
- [x] 异常 details 字段使用 "source" 而非 "provider"
- [x] `hub.sources` 属性正常工作

**完成日期**：2026-01-19（Phase 8 残留修复完成）

---

## 提交策略

每个 Phase 完成后独立提交：

1. `Phase 1: rename core classes (DataSource → DataSource)`
2. `Phase 2: rename directories and files (providers → sources)`
3. `Phase 3: update Apps layer imports and hub.sources`
4. `Phase 4: update all test files`
5. `Phase 5: update documentation`
6. `Phase 6: update exception details field (provider → source)`
7. `Phase 7: final verification and cleanup`
8. `Phase 8: 残留修复（2026-01-19）`
   - 批次 1: `fbd90f1` - 修复核心源代码中的 provider 残留
   - 批次 2: `bdbe3ed` - 修复单元测试中的 provider 残留
   - 批次 3: `3e3e3cb` - 修复设计文档中的 providers 残留

最终合并到 `main` 前创建 PR 进行代码审查。
