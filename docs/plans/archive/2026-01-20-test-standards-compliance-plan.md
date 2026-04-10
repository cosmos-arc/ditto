# 测试规范遵循问题分析与改进计划

## 执行摘要

**当前状态**：
- **单元测试覆盖率**: 92.67% ✅ （已超过 80% 要求）
- **测试失败数**: 31 个 ❌ （主要因 Dishka 迁移导致的测试失效）
- **Marker 覆盖率**: 44.2% ❌ （55.8% 测试文件缺少 marker）

**核心问题**：测试覆盖率已达要求，但存在大量测试失效和规范遵循问题。

---

## 问题分析

### 1. 测试失效（31 个失败）

**位置**：
- `packages/data/tests/unit/test_hub_unit.py`: 28 个失败
- `packages/data/tests/unit/sources/test_accessor_unit.py`: 5 个失败

**根本原因**：Dishka 依赖注入迁移破坏了测试 Mock

```python
# ❌ 旧测试直接 Mock DataHub 类
mocker.patch("ditto_data.DataHub", return_value=mock_hub)

# ✅ 新架构使用 Dishka 容器
# 需要 Mock 容器中的 Provider，而非直接 Mock DataHub
```

**影响**：
- CI 会因测试失败而阻塞
- 开发者看到失败测试可能忽略新问题

---

### 2. Marker 覆盖率不足（55.8% 文件缺失）

**统计数据**：
- 有 Marker: 53 个文件（44.2%）
- 无 Marker: 67 个文件（55.8%）

**无 Marker 的主要文件**：
| 目录 | 无 Marker 文件数 |
|------|-----------------|
| `packages/data/tests/unit` | 44 个 |
| `packages/foundation/tests/unit` | 15 个 |
| `apps/port/tests/unit` | 0 个（100% 覆盖）✅ |

**后果**：
- `pytest -m unit` 会遗漏 55.8% 的单元测试
- CI 的 marker 过滤机制失效
- 无法选择性运行测试类型

---

### 3. 命名冲突（违反 python-test.md 第 40-50 行）

**冲突文件**：
1. `test_backfill_unit.py`:
   - `apps/port/tests/unit/ingestion/test_backfill_unit.py`
   - `apps/port/tests/unit/ingestion/flows/test_backfill_unit.py`

2. `test_base_unit.py`:
   - `packages/data/tests/unit/alerts/test_base_unit.py`
   - `packages/data/tests/unit/sources/test_base_unit.py`

**风险**：pytest 导入冲突（虽尚未触发，但存在隐患）

---

### 4. 假测试/宽泛断言

**问题位置**：
- `packages/data/tests/unit/models/test_common_unit.py:44`: `assert True`
- 约 130 处 `assert xxx is not None`（部分合理，部分过于宽泛）

---

### 5. unittest.mock 使用（违反 python-test.md 第 142-160 行）

**违规文件**：18 个文件使用了 `unittest.mock` 而非 `pytest-mock`

**示例**：
```python
# ❌ 错误（在 conftest.py 中）
from unittest.mock import MagicMock

# ✅ 正确
def test_something(mocker):
    mock_func = mocker.patch("module.function")
```

---

## 根本原因分析

### 为什么开发中不遵循测试规范？

| 原因 | 具体表现 | 解决方案 |
|------|----------|----------|
| **缺乏 Pre-commit 检查** | 新增测试文件没有自动检查 marker | 添加 pre-commit hook |
| **CI 配置不一致** | CI 直接运行 `pytest packages/...` 而非 `pytest -m unit` | 统一 CI 测试命令 |
| **测试模板缺失** | 开发者复制旧测试文件，继承错误模式 | 创建标准测试模板 |
| **Dishka 迁移未同步更新测试** | Mock 依赖注入容器的方式未更新 | 更新测试指南 |
| **无自动化检查脚本** | 假测试、命名冲突无法自动检测 | 添加检测脚本 |

---

## 改进计划（根据用户选择调整）

### 用户选择的优先级：
1. ✅ 立即修复 31 个失败的测试
2. ✅ 批量添加 Marker 到测试文件
3. ✅ 添加 Pre-commit 检查
4. ✅ 修复历史遗留问题

### 处理策略：
- **失败的测试**：重新评估测试需求（先分析哪些测试仍然有效，哪些需要重写）
- **CI 策略**：逐步迁移（先自动添加 marker，再逐步迁移到基于 marker 的测试策略）

---

## 重要决策：Dishka 单元测试策略

### 调研结论

**单元测试最佳实践：保持传统 pytest-mock 写法，不在单元测试中引入容器**

| 测试类型 | 使用容器 | 推荐方法 | 示例 |
|---------|---------|----------|------|
| **单元测试** | ❌ 不使用 | pytest-mock + fixtures | `def test_store(mock_client):` |
| **集成测试** | ✅ 可选 | make_container | `container = make_async_container(...)` |

### 决策依据

1. **项目设计文档已明确决策**：
   - [2026-01-20-dishka-di-design.md](2026-01-20-dishka-di-design.md) 第 18 行：
     > "测试策略：保持 pytest-mock"

2. **Mark Seemann 原则**（DI 权威）：
   > "单元测试不应使用 IoC 容器"

3. **Pytest fixtures 本身就是 DI 框架**：
   ```python
   @pytest.fixture
   def sqlite_client():
       # 这就是依赖注入
       return SQLiteClient(...)
   ```

4. **业界共识**：80-90% 单元测试用 mock，10-20% 集成测试用容器

### 单元测试修复策略

对于 31 个失败的测试（主要是 Dishka 相关）：

```python
# ❌ 错误：尝试 Mock DataHub 类
mocker.patch("ditto_data.DataHub", return_value=mock_hub)

# ✅ 正确：直接测试组件，传入 Mock 依赖
def test_calendar_accessor():
    mock_store = Mock(spec=CalendarStore)
    accessor = CalendarAccessor(mock_store)
    result = accessor.is_trading_day("2024-01-02")
    assert result is True
```

### 集成测试策略（可选）

如果需要验证 Dishka 容器配置：

```python
@pytest.mark.integration
async def test_dishka_container_integration():
    """验证 Dishka 容器正确组装组件"""
    container = make_async_container(
        AppProvider(),
        DataHubProvider(),
    )
    hub = await container.get(DataHub)
    assert hub is not None
    assert hub.calendar is not None
```

---

## Phase 1: 立即修复 31 个失败的测试（P0 - 优先）

### 1.1 分析失败测试的有效性

**问题文件**：
- [test_hub_unit.py](../packages/data/tests/unit/test_hub_unit.py) - 28 个失败
- [test_accessor_unit.py](../packages/data/tests/unit/sources/test_accessor_unit.py) - 5 个失败

**重新评估策略**（用户选择）：
1. 先检查 Dishka 迁移后，这些测试是否仍然有意义
2. 分析测试覆盖的功能是否已被其他测试覆盖
3. 对于仍然有效的测试，使用 pytest-mock 直接测试组件

**修复选项**：
| 选项 | 描述 | 适用场景 |
|------|------|----------|
| **重写** | 直接测试组件，传入 Mock 依赖 | 核心功能，必须测试 |
| **删除** | 标记为跳过/删除 | 被其他测试覆盖，或功能已变更 |
| **迁移** | 迁移到集成测试 | 需要完整容器环境的场景 |

---

### 1.2 批量添加 Marker 到缺失的测试文件（用户优先选择）

**目标**：为 67 个缺少 marker 的测试文件添加 `@pytest.mark.unit` 或 `@pytest.mark.integration`

**批量添加策略**：
1. 按目录自动添加：
   - `tests/unit/` → `@pytest.mark.unit`
   - `tests/integration/` → `@pytest.mark.integration`

2. 手动检查边界情况（位置不明确的测试）

**需要添加 Marker 的文件列表**：
| 目录 | 文件数 | Marker 类型 |
|------|--------|------------|
| `packages/data/tests/unit/` | 44 | `@pytest.mark.unit` |
| `packages/foundation/tests/unit/` | 15 | `@pytest.mark.unit` |
| `packages/data/tests/integration/` | 8 | `@pytest.mark.integration` |

---

## Phase 2: 添加 Pre-commit 检查（P1 - 用户优先选择）

### 2.1 创建检查脚本

**创建 `scripts/check_pytest_markers.py`**：
```python
#!/usr/bin/env python3
"""
检查测试文件是否包含 pytest marker。
"""
import ast
import sys
from pathlib import Path

def check_test_file_has_marker(file_path: Path) -> bool:
    """检查测试文件是否有 marker。"""
    with open(file_path) as f:
        tree = ast.parse(f.read(), filename=str(file_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if hasattr(node.func, 'attr') and node.func.attr == 'mark':
                # 检查是否是 pytest.mark.unit 或 pytest.mark.integration
                for keyword in node.keywords:
                    if keyword.arg == 'unit' or keyword.arg == 'integration':
                        return True
    return False

def main():
    """主函数。"""
    test_files = list(Path(".").rglob("test_*.py"))
    missing_markers = []

    for test_file in test_files:
        if not check_test_file_has_marker(test_file):
            missing_markers.append(test_file)

    if missing_markers:
        print(f"❌ 发现 {len(missing_markers)} 个测试文件缺少 marker:")
        for f in missing_markers:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("✅ 所有测试文件都有 marker")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 2.2 更新 .pre-commit-config.yaml

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-marker-check
        name: Check pytest markers
        entry: pixi run -e dev python scripts/check_pytest_markers.py
        language: system
        files: ^.*test_.*\.py$
        pass_filenames: false

      - id: fake-test-check
        name: Check for fake tests
        entry: grep -rn "assert True\|assert False" tests/ || exit 0
        language: system
        files: ^.*test_.*\.py$

      - id: unittest-mock-check
        name: Check for unittest.mock usage
        entry: grep -rn "from unittest.mock" tests/ || exit 0
        language: system
        files: ^.*test_.*\.py$
```

---

## Phase 3: 修复历史遗留问题（P2 - 用户优先选择）

### 3.1 解决命名冲突

**重命名方案**：
| 当前名称 | 新名称 | 位置 |
|---------|--------|------|
| `test_backfill_unit.py` | `test_backfill_manager_unit.py` | `apps/port/tests/unit/ingestion/` |
| `test_backfill_unit.py` | `test_backfill_flow_unit.py` | `apps/port/tests/unit/ingestion/flows/` |
| `test_base_unit.py` | `test_alert_models_unit.py` | `packages/data/tests/unit/alerts/` |
| `test_base_unit.py` | `test_source_base_unit.py` | `packages/data/tests/unit/sources/` |

### 3.2 迁移 unittest.mock 到 pytest-mock

**需要修改的文件**（18 个）：
- `apps/port/tests/conftest.py`
- `apps/port/tests/unit/conftest.py`
- `apps/port/tests/unit/cli/test_factory_unit.py`
- `apps/port/tests/unit/cli/commands/*.py` (6 个)
- `apps/port/tests/unit/jobs/flows/test_deploy_unit.py`
- `packages/data/tests/` (10 个)

### 3.3 修复假测试和宽泛断言

**需要修复的位置**：
- `packages/data/tests/unit/models/test_common_unit.py:44`: `assert True`
- 约 130 处 `assert xxx is not None`（需逐一评估）

---

## Phase 4: 逐步迁移 CI 测试命令（用户选择策略）

### 4.1 当前状态分析

**现有 CI 配置**：
- 使用目录过滤：`pytest packages/data/tests/unit/`
- 不检查 marker

**目标状态**：
- 使用 marker 过滤：`pytest -m "not integration and not e2e"`
- 自动检查 marker 覆盖

### 4.2 迁移步骤

**步骤 1**：确保所有测试都有 marker（Phase 1.2）
**步骤 2**：CI 添加 marker 检查步骤
**步骤 3**：CI 逐步切换到 marker 过滤
**步骤 4**：移除目录过滤，完全使用 marker

---

## Phase 5: 创建测试模板和文档（P3）

### 5.1 更新全局测试规范 `.claude/rules/python-test.md`

**重要**：将 Dishka 单元测试策略添加到全局测试规范

**新增章节内容**：
```markdown
## 依赖注入（Dishka）测试规范

### 核心原则

**单元测试不使用 IoC 容器**

> 本项目使用 Dishka 进行依赖注入，但单元测试遵循 Mark Seemann 原则：
> "单元测试不应使用 IoC 容器"

### 决策依据

1. **Pytest fixtures 本身就是 DI 框架**
2. **业界共识**：80-90% 单元测试用 mock，10-20% 集成测试用容器
3. **测试隔离性**：直接测试组件更简单、更快速
4. **Dishka 官方文档**："In many cases, you may not need an IoC container for testing"

---

### 单元测试（不使用容器）

#### 推荐模式

```python
# ✅ 正确：直接测试组件，传入 Mock 依赖
import pytest
from unittest.mock import Mock

@pytest.mark.unit
def test_calendar_accessor():
    """测试 CalendarAccessor 的单元测试。"""
    # Arrange: 准备 Mock 依赖
    mock_store = Mock(spec=CalendarStore)
    mock_store.get_first_trading_day.return_value = "2024-01-02"

    # Act: 创建被测组件
    accessor = CalendarAccessor(mock_store)

    # Assert: 验证行为
    result = accessor.get_first_trading_day()
    assert result == "2024-01-02"
    mock_store.get_first_trading_day.assert_called_once()
```

#### 禁止模式

```python
# ❌ 错误：单元测试中不要使用 make_container
def test_calendar_accessor():
    container = make_container(AppProvider(), DataHubProvider())
    hub = container.get(DataHub)
    # 这是集成测试，不是单元测试

# ❌ 错误：不要 Mock DataHub 类
mocker.patch("ditto_data.DataHub", return_value=mock_hub)
# 应该直接测试具体组件，而非整个容器
```

---

### 集成测试（可选使用容器）

#### 何时使用容器

- 验证 Dishka Provider 配置是否正确
- 测试多个组件协作
- 验证生命周期管理（init/destroy）

#### 推荐模式

```python
@pytest.mark.integration
async def test_dishka_container_integration():
    """验证 Dishka 容器正确组装组件。"""
    # 创建容器
    container = make_async_container(
        AppProvider(),
        DataHubProvider(),
    )

    try:
        # 验证组件正确组装
        hub = await container.get(DataHub)
        assert hub is not None
        assert hub.calendar is not None
        assert hub.bars_accessor is not None
    finally:
        # 清理
        await container.close()
```

---

### 测试策略对比

| 测试类型 | 使用容器 | 测试目标 | 示例 |
|---------|---------|----------|------|
| **单元测试** | ❌ 不使用 | 单个组件行为 | `test_calendar_accessor_get_first_day()` |
| **集成测试** | ✅ 可选 | 多个组件协作 | `test_dishka_container_integration()` |
| **端到端测试** | ✅ 使用 | 完整流程 | `test_ingestion_flow_e2e()` |

---

### Component 层级测试指南

#### 1. Store 层（数据存储）

```python
@pytest.mark.unit
def test_security_store_resolve_sid(sqlite_client):
    """测试 SecurityStore 解析 SID。"""
    store = SecurityStore(sqlite_client)
    sid = store.resolve_sid("600000.SH", "tushare", asof=None)
    assert sid == 100000001
```

#### 2. Accessor 层（业务逻辑）

```python
@pytest.mark.unit
def test_calendar_accessor_is_trading_day():
    """测试 CalendarAccessor 判断交易日。"""
    mock_store = Mock(spec=CalendarStore)
    mock_store.is_open.return_value = True

    accessor = CalendarAccessor(mock_store)
    result = accessor.is_trading_day("2024-01-02")
    assert result is True
```

#### 3. DataHub 层（组合层）

```python
@pytest.mark.integration
async def test_datahub_resolve_sid():
    """测试 DataHub 解析 SID（集成测试）。"""
    container = make_async_container(AppProvider(), DataHubProvider())
    hub = await container.get(DataHub)

    sid = hub.resolve_sid("600000.SH", "tushare")
    assert sid is not None

    await container.close()
```

---

### 常见陷阱

| 陷阱 | 问题 | 解决方案 |
|------|------|----------|
| **测试中创建容器** | 速度慢、复杂度高 | 使用 pytest fixtures + mock |
| **Mock Provider 类** | Provider 是配置，不应测试 | 测试具体组件，而非配置 |
| **过度测试 DI** | DI 是工具，不是业务逻辑 | 测试业务逻辑，而非依赖注入 |
| **忽略集成测试** | 单元测试无法发现配置错误 | 添加关键集成测试 |

---

### 参考资料

- [Dishka Testing Documentation](https://dishka.readthedocs.io/en/latest/advanced/testing/index.html)
- [Mark Seemann: Unit testing and IoC containers](https://stackoverflow.com/questions/1465849/using-ioc-for-unit-testing)
- [Composition Root - ploeh blog](https://blog.ploeh.dk/2011/07/28/CompositionRoot/)
```

---

## 验证计划

### 1. 本地验证（使用 pixi task）

```bash
# 1. 检查所有测试都有 marker
pixi run -e dev pytest --collect-only -q

# 2. 运行带 marker 检查的测试（使用 pixi task）
pixi run -e dev test --unit --cov

# 3. 检测假测试
grep -rn "assert True\|assert False" tests/

# 4. 检测命名冲突
python scripts/check_test_naming_conflicts.py

# 5. 运行 marker 检查脚本
pixi run -e dev python scripts/check_pytest_markers.py
```

### 2. CI 验证

- 确保 CI 使用 `pixi run -e dev test --unit` 而非直接运行目录
- 确保 `--cov-fail-under=80` 生效
- 添加 marker 检查作为 CI 步骤

---

## 关键文件清单

### 需要修改的文件

**紧急修复（P0）**：
1. [packages/data/tests/unit/test_hub_unit.py](../packages/data/tests/unit/test_hub_unit.py) - 28 个测试失败
2. [packages/data/tests/unit/sources/test_accessor_unit.py](../packages/data/tests/unit/sources/test_accessor_unit.py) - 5 个测试失败
3. [packages/data/tests/unit/models/test_common_unit.py](../packages/data/tests/unit/models/test_common_unit.py) - `assert True` 假测试
4. 所有 67 个缺少 marker 的测试文件

**规范强化（P1）**：
5. [.github/workflows/ci.yml](../.github/workflows/ci.yml) - 统一测试命令
6. [.pre-commit-config.yaml](../.pre-commit-config.yaml) - 添加检查 hook
7. [scripts/check_pytest_markers.py](../scripts/check_pytest_markers.py) - 新建检查脚本

**质量提升（P2）**：
8. 4 个命名冲突文件重命名
9. 18 个文件迁移 unittest.mock → pytest-mock
10. 约 130 处宽泛断言改进

---

## 时间估算（根据用户优先级调整）

| 阶段 | 任务 | 优先级 | 预估时间 |
|------|------|--------|----------|
| P0 | 修复 31 个失败的测试（重新评估） | 高 | 4-6 小时 |
| P0 | 添加 Marker 到 67 个文件 | 高 | 2-3 小时 |
| P1 | Pre-commit + CI 配置 | 中 | 2 小时 |
| P1 | 创建测试模板 | 中 | 1 小时 |
| P2 | 解决命名冲突 | 低 | 1 小时 |
| P2 | 迁移 unittest.mock → pytest-mock（18 个文件） | 低 | 4-6 小时 |
| P2 | 改进假测试和宽泛断言 | 低 | 8-10 小时 |
| P2 | 更新 Dishka 测试指南 | 低 | 2 小时 |
| **总计** | | | **24-30 小时** |

---

**文档版本**: v1.0
**创建日期**: 2026-01-20
**状态**: 待批准
