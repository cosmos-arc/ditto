# 开发计划: 核心源码零 ignore 激进清理

## 概述
- Sprint: N/A | Phase: 代码质量提升
- 创建时间: 2026-01-15
- 目标: 核心源码零 `# noqa` 和 `# type: ignore`
- 约束: **无需考虑向后兼容**

## 当前状态

### 剩余问题统计
| 类型 | 数量 | 主要位置 |
|------|------|----------|
| `# noqa` | 14 | PLW0603 (10), PLC0415 (3), S108/S110 (1) |
| `# type: ignore` | 3 | testing.py, dates.py, tracing.py (注释) |
| `global` 语句 | 10 | Singleton 模式 |

### 已完成（批次 0）
- PLR0913/0911 复杂度问题 ✅
- SecurityMapper 移除 ✅
- 大量 type: ignore 清理 ✅

---

## 技术方案

### 核心策略：零容忍 + 架构重构

**原则**：
1. **拒绝技术债**：不保留任何"可接受"的 noqa/type: ignore
2. **架构优先**：通过重构消除根本原因（如循环依赖、全局状态）
3. **无向后兼容**：直接修改 API，无需保留旧接口

### TypeGuard 技术说明

**什么是 TypeGuard？**

TypeGuard 是 Python `typing` 模块提供的类型收窄功能。当一个函数返回 `TypeGuard[T]` 时，类型检查器会：
- 如果函数返回 `True`，将参数类型收窄为 `T`
- 比简单的 `isinstance()` 更精确，能区分子类

**应用场景**（dates.py:39）：
```python
# 问题：datetime 是 date 的子类，isinstance 无法区分
if isinstance(value, date):  # type: ignore[unnecessary-isinstance]
    return value.strftime("%Y-%m-%d")  # datetime.strftime 格式不同！

# 解决：TypeGuard 精确收窄
def is_pure_date(value: Any) -> TypeGuard[date]:
    """Type guard: 确保 value 是 date 但不是 datetime。"""
    return isinstance(value, date) and not isinstance(value, datetime)

if is_pure_date(value):  # 无需 type: ignore
    return value.strftime("%Y-%m-%d")
```

---

## Pyright 配置评估

### 当前配置分析

| 配置项 | 当前值 | 评估 | 建议 |
|--------|--------|------|------|
| `typeCheckingMode` | `standard` + `strict` for src | ✅ 合理 | 保持 |
| `reportUnusedImport` | `none` | ✅ 合理 | Ruff 已管理 |
| `reportUnusedVariable` | `none` | ✅ 合理 | Ruff 已管理 |
| `reportMissingTypeStubs` | `none` | ⚠️ 过于宽松 | 改为 `warning` |
| `stubPath` | `typings` | ✅ 合理 | 保持 |

### 需要调整的配置

```toml
# 建议修改
[tool.pyright]
# 强制第三方库类型完整性
reportMissingTypeStubs = "warning"  # 从 none 改为 warning

# 添加新的严格规则
reportImplicitStringConcatenation = "error"  # 禁止隐式字符串拼接
reportUninitializedInstanceVariable = "error"  # 未初始化实例变量
```

### Per-File-Ignores 评估

| 文件 | 当前豁免 | 评估 | 行动 |
|------|----------|------|------|
| `hub.py` | PLC0415 | 🟡 临时可接受 | 阶段 2 重构后移除 |
| `settings.py` | PLC0415, S104 | 🟡 临时可接受 | 阶段 1-2 重构后移除 |
| `deploy.py` | PLC0415 | 🔴 必须重构 | 阶段 2 重构后移除 |
| `freeze_manager.py` | S101 | 🟢 合理（类型收窄） | 保留并注释 |

---

## 任务清单

### Phase 1: Singleton 模式重构（消除 PLW0603）

- [x] **Task 1.1**: 创建 SettingsManager 类 `[M]`
  - 验收: 实现单例模式，无 global 语句，支持 reload
  - 文件: `packages/foundation/src/ditto_foundation/config/manager.py`

- [x] **Task 1.2**: 重构 settings.py 使用 Manager `[S]`
  - 验收: 移除 2 处 PLW0603，移除 pyproject.toml 中的 PLC0415 豁免
  - 文件: `packages/foundation/src/ditto_foundation/config/settings.py`, `pyproject.toml`
  - **注意**: SettingsManager 移至 settings.py 以避免循环依赖

- [ ] **Task 1.3**: 重构 paths.py 使用 Manager `[S]`
  - 验收: 移除 2 处 PLW0603，S108 添加详细注释
  - 文件: `packages/foundation/src/ditto_foundation/config/paths.py`

- [ ] **Task 1.4**: 重构 observability/metrics.py `[S]`
  - 验收: 移除 2 处 PLW0603
  - 文件: `packages/foundation/src/ditto_foundation/observability/metrics.py`

- [ ] **Task 1.5**: 重构 observability/__init__.py `[S]`
  - 验收: 移除 2 处 PLW0603，S110 添加详细注释
  - 文件: `packages/foundation/src/ditto_foundation/observability/__init__.py`

- [ ] **Task 1.6**: 重构 app_initializer.py `[S]`
  - 验收: 移除 1 处 PLW0603
  - 文件: `packages/foundation/src/ditto_foundation/app_initializer.py`

- [ ] **Task 1.7**: 重构 cli/context.py `[S]`
  - 验收: 移除 1 处 PLW0603
  - 文件: `apps/port/src/ditto_port/cli/context.py`

### Phase 2: 循环依赖解耦（消除 PLC0415）

- [ ] **Task 2.1**: 创建共享类型文件 `[M]`
  - 验收: 定义 WriteResult 等共享类型
  - 文件: `packages/data/src/ditto_data/types.py`

- [ ] **Task 2.2**: 重构 adj_factor.py `[S]`
  - 验收: 移除 1 处 PLC0415，使用 types.WriteResult
  - 文件: `packages/data/src/ditto_data/repositories/adj_factor.py`

- [ ] **Task 2.3**: 重构 bars.py 注入依赖 `[M]`
  - 验收: 移除 4 处 PLC0415，注入 QuarantineStore
  - 文件: `packages/data/src/ditto_data/repositories/bars.py`

- [ ] **Task 2.4**: 重构 sources/base.py `[S]`
  - 验收: 移除 1 处 PLC0415，优化延迟导入
  - 文件: `packages/data/src/ditto_data/sources/base.py`

- [ ] **Task 2.5**: 重构 tushare/client.py `[S]`
  - 验收: 移除 1 处 PLC0415，优化 keyring 导入
  - 文件: `packages/data/src/ditto_data/sources/tushare/client.py`

- [ ] **Task 2.6**: 重构 observability/logging.py `[S]`
  - 验收: 移除 1 处 PLC0415，注入 Paths 实例
  - 文件: `packages/foundation/src/ditto_foundation/observability/logging.py`

- [ ] **Task 2.7**: 重构 deploy.py `[M]`
  - 验收: 移除 PLC0415，通过重构避免循环依赖
  - 文件: `apps/port/src/ditto_port/jobs/flows/deploy.py`, `pyproject.toml`

- [ ] **Task 2.8**: 重构 hub.py `[M]`
  - 验收: 移除 PLC0415 豁免
  - 文件: `packages/data/src/ditto_data/hub.py`, `pyproject.toml`

### Phase 3: 类型忽略清理

- [ ] **Task 3.1**: 使用 TypeGuard 修复 dates.py `[M]`
  - 验收: 移除 `# type: ignore[unnecessary-isinstance]`，创建 is_pure_date TypeGuard 函数
  - 文件: `packages/foundation/src/ditto_foundation/util/dates.py`

- [ ] **Task 3.2**: 清理 testing.py `[S]`
  - 验收: 移除或添加详细注释说明 unused-import 原因
  - 文件: `packages/foundation/src/ditto_foundation/observability/testing.py`

- [ ] **Task 3.3**: 清理 tracing.py 注释 `[S]`
  - 验收: 移除注释中的 type: ignore 说明
  - 文件: `packages/foundation/src/ditto_foundation/observability/tracing.py`

### Phase 4: Pyright 配置优化

- [ ] **Task 4.1**: 更新 pyproject.toml 配置 `[S]`
  - 验收: reportMissingTypeStubs 改为 warning，添加新的严格规则
  - 文件: `pyproject.toml`

### Phase 5: 规则文档创建

- [ ] **Task 5.1**: 创建 noqa-ignore 规则文件 `[M]`
  - 验收: 创建 `.claude/rules/noqa-ignore.md`，定义严格的 noqa/type: ignore 使用规范
  - 文件: `.claude/rules/noqa-ignore.md`

- [ ] **Task 5.2**: 更新 CLAUDE.md 添加规则引用 `[S]`
  - 验收: 在核心约束中引用新规则文件
  - 文件: `.claude/CLAUDE.md`

### Phase 6: 最终验证

- [ ] **Task 6.1**: 完整代码质量检查 `[M]`
  - 验收:
    - `pixi run -e dev lint` 无错误（除配置的 S608/S108/S110）
    - `pixi run -e dev type --all` 无错误
  - 命令: `pixi run -e dev lint`, `pixi run -e dev type --all`

- [ ] **Task 6.2**: 完整测试套件 `[L]`
  - 验收: 所有测试通过，覆盖率 >= 80%
  - 命令: `pixi run -e dev test`, `pixi run -e dev test --coverage`

- [ ] **Task 6.3**: 统计验证 `[S]`
  - 验收:
    - `git grep "# noqa" packages/*/src apps/*/src | grep -v "S608\|S108\|S110"` 结果为 0
    - `git grep "# type: ignore" packages/*/src apps/*/src` 结果为 0
    - `git grep "^global " packages/*/src apps/*/src` 结果为 0
  - 命令: `git grep`

---

## 关键文件

### 新建文件
1. `packages/foundation/src/ditto_foundation/config/manager.py`
2. `packages/data/src/ditto_data/types.py`
3. `.claude/rules/noqa-ignore.md` ⭐ 新增

### 修改文件
1. `packages/foundation/src/ditto_foundation/config/settings.py`
2. `packages/foundation/src/ditto_foundation/config/paths.py`
3. `packages/foundation/src/ditto_foundation/observability/metrics.py`
4. `packages/foundation/src/ditto_foundation/observability/__init__.py`
5. `packages/foundation/src/ditto_foundation/observability/logging.py`
6. `packages/foundation/src/ditto_foundation/util/dates.py`
7. `packages/foundation/src/ditto_foundation/app_initializer.py`
8. `packages/data/src/ditto_data/repositories/adj_factor.py`
9. `packages/data/src/ditto_data/repositories/bars.py`
10. `packages/data/src/ditto_data/sources/base.py`
11. `packages/data/src/ditto_data/sources/tushare/client.py`
12. `packages/data/src/ditto_data/hub.py`
13. `apps/port/src/ditto_port/cli/context.py`
14. `apps/port/src/ditto_port/jobs/flows/deploy.py`
15. `pyproject.toml`
16. `.claude/CLAUDE.md`

---

## 规则文档草案：noqa-ignore.md

### 文件位置：`.claude/rules/noqa-ignore.md`

```markdown
---
paths: ./**/*.py
---

# noqa 和 type: ignore 使用规范

## 核心原则

**核心源码零容忍**：`packages/**/src` 和 `apps/port/**/src` 中不能有任何 `# noqa` 或 `# type: ignore`。

**测试代码有限豁免**：测试代码可以使用 `# noqa`，但必须遵循以下规范。

---

## 禁止规则

### 生产代码（src）完全禁止

| 规则 | 例外 | 说明 |
|------|------|------|
| `# noqa` | 无 | 所有 noqa 必须通过重构解决 |
| `# type: ignore` | 无 | 所有类型忽略必须通过类型修正解决 |
| `# pyright: ignore` | 无 | 使用 `# pyright: ignore` 替代 `# type: ignore` |
| `global` 语句 | 无 | 必须使用类属性单例模式 |
| 行内导入 | 无 | 必须通过重构解决循环依赖 |

### 允许的豁免（极少数情况）

#### 1. SQL 安全（S608）

```python
# ✅ 允许：必须带详细注释
query = f"SELECT * FROM {table}"  # noqa: S608 - table 已通过 ALLOWED_TABLES 白名单验证

# ❌ 禁止：无注释
query = f"SELECT * FROM {table}"  # noqa: S608
```

#### 2. 临时目录（S108）

```python
# ✅ 允许：必须带详细注释
temp = os.environ.get("TEMP", "/tmp")  # noqa: S108 - Windows TEMP fallback，仅用于 XDG 路径回退

# ❌ 禁止：无注释
temp = os.environ.get("TEMP", "/tmp")  # noqa: S108
```

#### 3. 优雅关闭（S110）

```python
# ✅ 允许：必须带详细注释
except Exception:  # noqa: S110 - 优雅关闭不应抛异常，错误已在 cleanup 中记录
    pass
```

---

## 测试代码规范

### 允许的规则

测试代码可以豁免以下规则（已在 pyproject.toml 中配置）：

- `PLR2004` - 魔法值
- `PLR0913` - 参数过多
- `S101` - assert 使用
- `ANN` - 类型注解
- `D` - 文档字符串
- `PLC0415` - 行内导入
- `C901` - 复杂度

### 禁止的行为

```python
# ❌ 禁止：滥用 noqa
def test_foo():
    x = 1  # noqa
    y = 2  # noqa

# ✅ 正确：测试代码应有清晰的意图
def test_foo():
    assert calculate(1, 2) == 3
```

---

## 违规检测

### CI 检查命令

```bash
# 检查生产代码中的 noqa（除允许的 S608/S108/S110）
git grep "# noqa" packages/*/src apps/*/src | grep -v "S608\|S108\|S110"

# 检查生产代码中的 type: ignore
git grep "# type: ignore" packages/*/src apps/*/src

# 检查 global 语句
git grep "^global " packages/*/src apps/*/src
```

### Pre-commit Hook

使用 `.claude/hooks/py_gate.py` 强制执行：
- 新增代码不得包含 noqa/type: ignore（除允许规则）
- 违规的提交将被拒绝

---

## TypeGuard 使用指南

### 何时使用 TypeGuard

当需要**区分子类**进行类型收窄时：

```python
from typing import TypeGuard, Any

def is_pure_date(value: Any) -> TypeGuard[date]:
    """Type guard: 确保 value 是 date 但不是 datetime。"""
    return isinstance(value, date) and not isinstance(value, datetime)

# 使用
if is_pure_date(value):
    # value 的类型被收窄为 date
    return value.strftime("%Y-%m-%d")
```

### 常见 TypeGuard 模式

```python
# 区分具体类型
def is_str(value: Any) -> TypeGuard[str]:
    return isinstance(value, str)

# 区分联合类型
def is_positive_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and value > 0

# 区分 TypedDict
def is_valid_config(obj: Any) -> TypeGuard[ValidConfig]:
    return isinstance(obj, dict) and "key" in obj
```

---

## 修复流程

### 发现 noqa/type: ignore 时的处理步骤

1. **理解原因**：为什么需要 noqa/type: ignore？
2. **评估方案**：
   - 能否通过重构消除？（优先）
   - 能否通过 TypeGuard/Protocol 解决？
   - 是否真的是必须的豁免？
3. **实施修复**：
   - 遵循 TDD 流程（RED → GREEN → REFACTOR）
   - 添加测试覆盖新代码
4. **验证**：
   - 移除 noqa/type: ignore
   - 运行 `pixi run -e dev check`

---

## 参考资源

- [Pyright Type Guards](https://github.com/microsoft/pyright/blob/main/docs/typed-calls.md#type-guards)
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)
- 项目架构规范：[core.md](.claude/rules/core.md)
```

---

## 验证标准

### 成功标准

- ✅ 核心源码 `# noqa` = 0（除 S608/S108/S110 且带详细注释）
- ✅ 核心源码 `# type: ignore` = 0
- ✅ 核心源码 `global` 语句 = 0
- ✅ 所有测试通过
- ✅ 分支覆盖率 ≥ 80%
- ✅ Pyright strict 检查通过
- ✅ Ruff lint 检查通过（除配置的豁免）
- ✅ 新规则文件已创建并引用

### 统计目标

```bash
# 执行这些命令，预期结果
git grep "# noqa" packages/*/src apps/*/src | grep -v "S608\|S108\|S110" | wc -l
# 预期: 0

git grep "# type: ignore" packages/*/src apps/*/src | wc -l
# 预期: 0

git grep "^global " packages/*/src apps/*/src | wc -l
# 预期: 0
```

---

## 临时豁免清单（已处理 ✅）

> **说明**: 以下 per-file-ignores 已在本次批次中处理完成（2026-01-15）。

### 复杂度相关（✅ 已完成）

| 文件 | 规则 | 原因 | 处理方式 | 状态 |
|------|------|------|----------|------|
| `backfill.py` | PLR0913 | Prefect flow 参数过多 (9 > 7) | 使用 BackfillFlowConfig 配置对象 | ✅ 完成 |
| `datasets.py` | PLR0913 | 配置工厂参数过多 (8 > 7) | 使用 T1ConfigParams 配置对象 + overload | ✅ 完成 |
| `coordinator.py` | PLR0911 | 多返回语句 (8 > 6) | 提取辅助方法减少返回语句 | ✅ 完成 |
| `pipeline_store.py` | C901 | `update_run` 过于复杂 (13 > 10) | 提取 3 个辅助方法降低复杂度 | ✅ 完成 |
| `pipeline_store.py` | PLR0913 | 参数过多 (9 > 7) | 使用 **kwargs 简化参数 | ✅ 完成 |
| `security.py` | PLR0913 | 参数过多 (9 > 7) | 使用 SecurityRegistration 配置对象 | ✅ 完成 |
| `paths.py` | PLR0913 | PathResolver 参数过多 (9 > 7) | 使用 PathResolverConfig dataclass | ✅ 完成 |

### SQL 相关（S608）✅ 已确认安全

| 文件 | 原因 | 安全措施 | 状态 |
|------|------|----------|------|
| `technical.py` | 动态查询引用表 | 白名单 + 正则验证 | ✅ 安全 |
| `pit_helper.py` | SQL 包装器 | 输入验证函数 | ✅ 安全 |
| `pipeline_store.py` | 动态 UPDATE 语句 | 白名单验证 | ✅ 安全 |
| `security_store.py` | 动态 WHERE IN 子句 | 参数化查询 | ✅ 安全 |
| `sqlite_client.py` | 动态表名 | 白名单验证 | ✅ 安全 |
| `sql_engine.py` | CREATE VIEW | 白名单验证 | ✅ 安全 |

### 其他（✅ 已完成）

| 文件 | 规则 | 原因 | 处理方式 | 状态 |
|------|------|------|----------|------|
| `models.py` | S112 | 忽略无效配置文件 | 细化异常类型 + 详细注释 | ✅ 完成 |
| `sql_engine.py` | S324 | MD5 用于缓存键（非安全用途） | 添加详细安全说明注释 | ✅ 完成 |

### 测试相关（保留）

| 文件 | 规则 | 原因 | 状态 |
|------|------|------|------|
| `test_conftest.py` | E402 | 延迟导入以设置路径 | ✅ 保留（测试豁免） |
| `test_sql_engine_injection_integration.py` | B017 | assert Exception 测试 | ✅ 保留（测试豁免） |

---

## 处理总结（批次 1）

### 完成时间
2026-01-15

### 处理文件清单

#### 新增配置对象/辅助类
1. `BackfillFlowConfig` - backfill.py 参数封装
2. `T1ConfigParams` - datasets.py 参数封装
3. `FetchResult` - coordinator.py 错误处理
4. `PipelineRunConfig` - pipeline_store.py insert_run 参数
5. `DQIssueConfig` - pipeline_store.py insert_dq_issue 参数
6. `PathResolverConfig` - paths.py 路径解析配置
7. `SecurityRegistration` - security.py 证券注册信息

#### 重构方法
1. `backfill_flow` - 9 参数 → 1 配置对象
2. `create_t1_config` - 8 参数 → 配置对象 + overload
3. `ingest_date` - 8 返回语句 → 6 返回语句
4. `update_run` - 9 参数 → **kwargs，复杂度 13 → < 10
5. `register` (security) - 9 参数 → 1 配置对象
6. `PathResolver.__init__` - 9 参数 → 1 配置对象

#### 安全注释完善
1. `models.py` - S112: 详细异常处理说明
2. `sql_engine.py` - S324: MD5 安全使用说明
3. 6 个 S608 文件 - 确认安全措施到位

### CI 验证结果

```bash
✅ pixi run -e dev lint        # All checks passed!
✅ pixi run -e dev type --all  # 0 errors, 0 warnings
✅ pixi run -e dev test --fast # 1373 passed in 106.22s
```

### 移除的豁免配置

从 `pyproject.toml` 中移除了以下豁免：
- `apps/port/src/ditto_port/jobs/flows/backfill.py` = ["PLR0913"]
- `apps/port/src/ditto_port/services/ingestion/config/datasets.py` = ["PLR0913"]
- `apps/port/src/ditto_port/services/ingestion/coordinator.py` = ["PLR0911"]
- `packages/data/src/ditto_data/repositories/security.py` = ["PLR0913"]
- `packages/foundation/src/ditto_foundation/config/paths.py` = ["PLR0913"]
- `packages/data/src/ditto_data/dq/models.py` = ["S112"]

### 保留的豁免配置（经安全评估）

以下豁免经评估后保留，已有完善的安全措施：

**S608（SQL 注入防护）：**
- 所有文件都有白名单验证或参数化查询
- 详见上方"SQL 相关（S608）"表格

**测试文件豁免：**
- 测试文件的豁免符合项目规范

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| Singleton 重构破坏现有行为 | 完整单元测试，RED-GREEN-REFACTOR，无向后兼容限制 |
| 循环依赖解耦引入新问题 | 依赖注入，Protocol 接口，严格测试 |
| TypeGuard 语义错误 | 详细边界测试，代码审查 |
| 配置调整导致 CI 失败 | 逐步调整，先 warning 后 error |
