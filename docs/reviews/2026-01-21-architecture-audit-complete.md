# 架构审计报告（完整版）

**审计日期**: 2026-01-21
**审计范围**: `packages/`, `apps/port/`, `tests/`
**审计方法**: LSP 语义分析 + 依赖关系图 + 规则验证
**审计版本**: v2.0 (补充严重架构问题)

---

## Executive Summary

### 关键发现

| 指标 | 状态 | 详情 |
|------|------|------|
| **代码质量检查** | ✅ 通过 | lint, type 检查通过 |
| **架构约束** | ⚠️ 违规 | **发现反向依赖** (datahub → core) |
| **依赖合规性** | ✅ 通过 | 无禁止的类库 |
| **工程实践** | ⚠️ 需改进 | 潜在循环依赖 |

### 问题分布

| 严重度 | 数量 | 说明 |
|--------|------|------|
| **Blocker** | 1 | **架构违规：datahub 依赖 core** |
| **High** | 1 | **循环依赖：core/quality ↔ foundation/config** |
| **Medium** | 2 | 空导出、参数过多 |
| **Low** | 2 | 可选优化 |

### Top 3 最严重问题

1. 🚨 **[ARCH-001] datahub → core 反向依赖** - 违背分层架构
2. ⚠️ **[ARCH-002] 潜在循环依赖** - core/quality 延迟导入 foundation
3. ⚠️ **[ENG-001] 空导出模块** - core 包多个模块无公共 API

---

## Inferred Architecture（推断架构）

### 设计文档中的架构

```
┌─────────────────────────────────────────────────────────┐
│              apps/port (应用层 - Server)                 │
└─────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   datahub    │  │    core      │  │  foundation  │
│  (数据层)    │  │  (核心层)    │  │  (基础设施)  │
└──────────────┘  └──────────────┘  └──────────────┘
      ▲                │
      │                │
      └────────────────┘
       **违规依赖方向**
```

### 依赖规则（设计文档）

| 规则 | 正确方向 | 违规方向 |
|------|----------|----------|
| Apps → datahub | ✅ | - |
| Apps → core | ✅ | - |
| Apps → foundation | ✅ | - |
| **core → datahub** | ✅ | ❌ |
| datahub → foundation | ✅ | - |
| core → foundation | ✅ | - |
| **datahub → core** | ❌ | ❌ **已发现违规** |

---

## Findings（详细发现）

### [ARCH-001] 反向依赖：datahub 依赖 core 🚨

**严重度**: Blocker

**位置**: `packages/datahub/src/ditto_datahub/models/__init__.py:4`

**证据**:
```python
# packages/datahub/src/ditto_datahub/models/__init__.py:3-28
"""DataHub models for data transfer objects."""

# Re-export DQ models from Core Layer for backward compatibility
from ditto_core.quality.spec import (
    ColumnRule,
    CompletenessRule,
    ConsistencyRule,
    DatasetRules,
    DQIssue,
    DQLevel,
    DQResult,
    DQSeverity,
    DQSpec,
    # ... 23 个类型
)
```

**为什么重要**:
- **违背分层架构**: datahub (数据层) 不应依赖 core (业务层)
- **破坏可维护性**: core 的变更会迫使 datahub 重新发布
- **违背设计文档**: `02_data_design.md` 明确禁止此依赖方向
- **技术债**: 注释说"for backward compatibility"，表明这是已知问题

**修复方案 A（推荐）- 移动 DQ 模型到 datahub**:

```
移动文件:
  packages/core/src/ditto_core/quality/spec.py
  → packages/datahub/src/ditto_datahub/models/dq_spec.py

影响范围:
  - ditto_core.quality.spec (移动)
  - ditto_core.quality (重导出)
  - ditto_datahub.models (直接导出)
  - datahub/models/__init__.py (删除反向导入)
```

**修复方案 B - 创建共享类型层**:

```
新建: packages/shared/src/ditto_shared/quality_types.py
  - DQIssue, DQResult, DQSpec 等共享模型
  - foundation 依赖 (共享层无依赖)
  - core 和 datahub 都依赖 shared

优点: 类型定义集中
缺点: 新增一层，复杂度增加
```

**工作量**: M (2-3 天，含测试)

**回滚策略**: 保留 core 层的重导出作为兼容层

---

### [ARCH-002] 潜在循环依赖 ⚠️

**严重度**: High

**位置**: `packages/core/src/ditto_core/quality/config.py:70`

**证据**:
```python
# packages/core/src/ditto_core/quality/config.py:66-73
def get_rules_paths(self, dataset: str, env: str | None = None) -> list[Path]:
    """
    Get rule file loading paths (priority from high to low).
    """
    if env is None:
        # Import here to avoid circular dependency
        from ditto_foundation.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        env = settings.system.ditto_env.value
```

**为什么重要**:
- **延迟导入是架构坏味道**: 表明存在循环依赖
- **依赖方向混乱**: core 不应在运行时依赖 foundation 的配置
- **违反 DIP**: 应该通过依赖注入传递 env，而不是内部获取

**依赖链分析**:
```
core/quality/config.py
  → 延迟导入 → foundation/config
  → 正常导入 ← foundation (可能通过其他路径)
```

**修复方案 A - 依赖注入**:

```python
# 修改 DQSettings 方法签名
def get_rules_paths(
    self,
    dataset: str,
    env: str,  # 必需参数，而非 None 默认值
) -> list[Path]:
    # 移除延迟导入
    paths: list[Path] = []
    env_rules = Path(f"config/{env}/dq_rules/{dataset}.yml")
    # ...
```

**修复方案 B - 配置对象传递**:

```python
# 在应用初始化时传递配置
class DQChecker:
    def __init__(self, config: DQConfig):
        self._config = config
        self._env = config.env  # 预先获取
```

**工作量**: M (1-2 天)

**回滚策略**: Git revert

---

### [ENG-001] 空导出模块 ⚠️

**严重度**: Medium

**位置**:
- `packages/core/src/ditto_core/__init__.py:7`
- `packages/core/src/ditto_core/engine/__init__.py`
- `packages/core/src/ditto_core/strategy/__init__.py`
- `packages/core/src/ditto_core/portfolio/__init__.py`

**证据**:
```python
# packages/core/src/ditto_core/__init__.py:7
"""Ditto 核心模块.

包含量化系统的核心业务逻辑
"""

__all__: list[str] = []
```

**为什么重要**:
- **API 不完整**: 表明核心模块仍在开发中
- **导入混乱**: 用户不知道应该从哪里导入
- **违背文档驱动**: README 提到的核心功能未通过公共 API 暴露

**受影响模块**:
| 模块 | 状态 | 应暴露内容 |
|------|------|-----------|
| `ditto_core` | 空 | QualityEngine, 策略类等 |
| `ditto_core.engine` | 空 | RegimeEngine, FactorEngine |
| `ditto_core.strategy` | 空 | 策略基类和实现 |
| `ditto_core.portfolio` | 空 | PortfolioManager |

**修复方案**:

```python
# packages/core/src/ditto_core/__init__.py
from ditto_core.quality import QualityEngine
from ditto_core.engine import RegimeEngine, FactorEngine
# ... 其他公共 API

__all__ = [
    "QualityEngine",
    "RegimeEngine",
    "FactorEngine",
    # ...
]
```

**工作量**: L (1 天，主要是文档更新)

**回滚策略**: 不需要回滚

---

### [ENG-002] 函数签名复杂度过高 ⚠️

**严重度**: Medium

**位置**:
- `packages/datahub/src/ditto_datahub/hub.py:44`
- `packages/foundation/src/dditto_foundation/observability/__init__.py:86`

**证据**:
```python
# packages/datahub/src/ditto_datahub/hub.py:44
def __init__(  # noqa: PLR0913
    self,
    data_root: Path,
    ...
    # 参数过多
```

**为什么重要**:
- **可维护性差**: 参数列表难以理解和维护
- **测试困难**: Mock 和 fixture 构建复杂
- **违背 SRP**: DataHub 承担过多职责

**修复方案 - 配置对象模式**:

```python
@dataclass(frozen=True)
class DataHubConfig:
    """DataHub 配置."""
    data_root: Path
    sqlite_pool: SQLitePool | None = None
    file_lock_manager: FileLockManager | None = None
    # ... 其他配置

class DataHub:
    def __init__(self, config: DataHubConfig) -> None:
        self._config = config
        # ... 初始化
```

**工作量**: M (1-2 天)

**回滚策略**: Git revert

---

### [ENG-003] 类型注解抑制过多 ℹ️

**严重度**: Low

**位置**:
- `packages/foundation/src/ditto_foundation/observability/config.py:122-139`

**证据**:
```python
# 8 处 # type: ignore[arg-type]
tracing_enabled=_resolve(  # type: ignore[arg-type]
tracing_sample_rate=_resolve(  # type: ignore[arg-type]
# ...
```

**为什么重要**:
- **降低类型安全性**: 抑制检查会隐藏潜在 bug
- **维护负担**: 后续开发者需要理解为何抑制

**修复方案 - 改进类型定义**:

```python
def _resolve[T](
    value: T | Callable[[], T],
    default: T,
) -> T:
    """改进类型推导，避免 type: ignore"""
    if isinstance(value, Callable):
        return value()
    return value
```

**工作量**: S (0.5 天)

**回滚策略**: 不需要回滚

---

## Refactor Plan（重构计划）

### P0 - 必须修复（会导致架构坍塌）

#### PR-1: 移除 datahub → core 反向依赖

**目标**: 消除架构违规

**改动范围**:
1. 移动 DQ 类型定义
   - `packages/core/src/ditto_core/quality/spec.py`
   - → `packages/datahub/src/ditto_datahub/models/dq_spec.py`

2. 更新导入路径
   - `ditto_core.quality` 重导出新位置
   - `ditto_datahub.models` 直接导出
   - 更新所有引用

3. 更新测试
   - 单元测试导入路径
   - 集成测试依赖注入

**风险**: 中等（影响公共 API）

**回滚策略**: 保留 `ditto_core.quality.spec` 作为兼容层，标记 deprecated

**验证命令**:
```bash
# 验证无 datahub → core 导入
grep -r "from ditto_core" packages/datahub/src --include="*.py"

# 验证类型检查通过
pixi run -e dev type

# 验证测试通过
pixi run -e dev test
```

---

### P1 - 应该修复（明显改善可维护性）

#### PR-2: 消除 core/quality 循环依赖

**目标**: 移除延迟导入

**改动范围**:
1. 修改 `DQSettings.get_rules_paths()` 签名
   - 添加 `env: str` 必需参数
   - 移除延迟导入

2. 更新调用方
   - DI 容器配置传递 env
   - 测试文件显式传递 env

**风险**: 低（内部 API 变更）

**回滚策略**: Git revert

---

### P2 - 可优化（风格与一致性）

#### PR-3: 暴露核心模块公共 API

**目标**: 完善 `__init__.py` 导出

**改动范围**:
1. 添加 `ditto_core` 公共 API
2. 添加 `ditto_core.engine` 公共 API
3. 更新文档

**风险**: 极低

**回滚策略**: 不需要回滚

#### PR-4: 配置对象重构

**目标**: 简化 `DataHub.__init__()` 签名

**改动范围**:
1. 创建 `DataHubConfig` dataclass
2. 更新 `DataHub.__init__()` 接受配置对象
3. 更新 DI 容器配置

**风险**: 低（可渐进式迁移）

**回滚策略**: Git revert

---

## 自动化检查脚本

### 架构合规检查

```bash
#!/bin/bash
# scripts/check_architecture.sh

echo "=== 架构合规检查 ==="

# 1. 检查 datahub → core 依赖
echo "检查 datahub → core 依赖..."
if grep -r "from ditto_core" packages/datahub/src --include="*.py" | grep -v "__pycache__"; then
    echo "❌ 发现违规依赖"
    exit 1
else
    echo "✅ 无违规依赖"
fi

# 2. 检查延迟导入（循环依赖指标）
echo "检查延迟导入..."
if grep -r "# noqa: PLC0415" packages/*/src --include="*.py"; then
    echo "⚠️ 发现潜在循环依赖"
else
    echo "✅ 无循环依赖"
fi

# 3. 检查空导出模块
echo "检查空导出模块..."
for file in packages/core/src/ditto_core/__init__.py; do
    if grep -q '__all__: list\[str\] = \[\]' "$file"; then
        echo "⚠️ 发现空导出: $file"
    fi
done

echo "=== 检查完成 ==="
```

### 类型安全检查

```bash
#!/bin/bash
# scripts/check_type_safety.sh

echo "=== 类型安全检查 ==="

# 1. 统计 type:ignore 使用
echo "统计 type:ignore 使用..."
grep -r "# type: ignore" packages/*/src --include="*.py" | wc -l

# 2. 检查裸 Any 类型
echo "检查裸 Any 类型..."
grep -r": Any" packages/*/src --include="*.py" | grep -v "list\[Any\]" | grep -v "dict\[str, Any\]"

# 3. 运行完整类型检查
pixi run -e dev type --all
```

---

## 验证命令

### 完整验证流程

```bash
# 1. 架构合规检查
pixi run scripts/check_architecture.sh

# 2. 类型安全检查
pixi run scripts/check_type_safety.sh

# 3. 完整 CI 检查
pixi run -e dev ci

# 4. 依赖关系可视化（可选）
pip install pydeps
pydeps packages/datahub/src --max-bacon=3 --cluster
```

### LSP 深度分析

```bash
# 分析 datahub 模块依赖
pixi run -e dev python .claude/scripts/lsp_pyright.py symbols \
  packages/datahub/src/ditto_datahub/__init__.py

# 查找 DQSpec 所有引用
pixi run -e dev python .claude/scripts/lsp_pyright.py refs \
  packages/core/src/ditto_core/quality/spec.py 345 8
```

---

## 附录

### A. 相关文档

- [数据层设计](../design/02_data_design.md)
- [项目架构规范](../../.claude/CLAUDE.md#项目架构)
- [Foundation 规范](../../.claude/rules/foundation.md)
- [DataHub 规范](../../.claude/rules/datahub.md)

### B. 审计历史

| 日期 | 版本 | 主要发现 |
|------|------|----------|
| 2026-01-21 | v1.0 | 初始审计，发现基础问题 |
| 2026-01-21 | v2.0 | **发现严重架构违规** |

### C. 问题追踪

建议创建 GitHub Issues 追踪修复进度：

- `ARCH-001`: [移除 datahub → core 反向依赖](https://github.com/xxx/issues/1)
- `ARCH-002`: [消除 core/quality 循环依赖](https://github.com/xxx/issues/2)
- `ENG-001`: [暴露核心模块公共 API](https://github.com/xxx/issues/3)
- `ENG-002`: [配置对象重构](https://github.com/xxx/issues/4)

---

**审计结论**: 🟡 **发现严重架构违规，建议立即修复 PR-1**

**审计人**: Claude Code (Ditto Architecture Audit - Complete)
**审计时间**: 2026-01-21
**下次审计**: PR-1 完成后
