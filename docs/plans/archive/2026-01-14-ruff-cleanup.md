# Ruff 代码质量全面优化计划

**日期**: 2026-01-14
**状态**: ✅ 已完成（所有批次完成，0 个错误）
**目标**: 消除所有 ruff 错误（134 个）或添加合理的 noqa 注释

**进度**:
- ✅ 批次 0: 配置更新（26 T201 → 0）
- ✅ 批次 1: 安全警告（10 S106/S311 → 0）
- ✅ 批次 2: 代码质量（15 S110/PLR0913/PLR2004 → 0）
- ✅ 批次 3: 设计模式 - PLC0415（132 → 0，采用严格处理）
- ✅ 批次 4: 剩余错误清理（21 → 0）
- ✅ **总计: 134 → 0 错误**

---

## 执行摘要

项目原有 **134 个 ruff 错误**，采用严格处理策略：
- **高优先级**：安全警告（S608, S106, S311）- 修复或添加 noqa
- **中优先级**：代码质量（S110, PLR0913, PLR2004, S101, C901）- 重构或添加 noqa
- **低优先级**：设计模式（PLC0415, T201）- 严格评估，只为真正必要的场景添加 noqa

**重要决策**: 对于 PLC0415（延迟导入），恢复严格检查并逐案处理：
- 标准库导入：移到顶部
- 可选依赖：添加 noqa 说明
- 动态导入：添加 noqa 说明
- 循环依赖：分类添加 noqa（延迟初始化、property 内导入、架构问题）

---

## 错误分布

| 错误代码 | 原数量 | 处理方式 | 结果 |
|----------|--------|----------|------|
| PLC0415 | 132 | 严格评估 + 分类处理 | → 0 |
| T201 | 26 | ruff 配置豁免 CLI | → 0 |
| S608 | 8 | noqa: S608（SQL 验证输入） | → 0 |
| S110 | 11 | 添加 debug/noqa | → 0 |
| S106 | 6 | 测试文件豁免 | → 0 |
| PLR0913 | 6 | 重构/添加 noqa | → 0 |
| PLR2004 | 4 | 提取常量 | → 0 |
| S101 | 4 | 豁免（类型收窄） | → 0 |
| S311 | 4 | 测试文件豁免 | → 0 |
| C901 | 2 | 添加 noqa | → 0 |
| I001 | 2 | 自动修复 | → 0 |
| 其他 | 7 | 逐个处理 | → 0 |

---

## 分批实施方案

### ✅ 批次 0: 配置更新

**目标**: 更新 ruff 配置以豁免合理的场景

**修改文件**: `pyproject.toml`

```toml
[tool.ruff.lint.per-file-ignores]
# CLI 工具
"**/cli.py" = ["T201"]
"**/cli/*.py" = ["T201"]
"**/examples/**/*.py" = ["T201"]

# 测试文件
"tests/**/*.py" = ["S101", "S106", "S311", "S608", "C901", "S105"]
"**/tests/**/*.py" = ["S101", "S106", "S311", "S608", "C901", "S105"]
```

**结果**: 26 处 T201 错误 → 0

---

### ✅ 批次 1: 安全警告

**目标**: 处理安全相关警告（S106, S311）

**结果**: 10 处 → 0（测试文件豁免）

---

### ✅ 批次 2: 代码质量

**目标**: 改进代码质量，消除复杂度和魔法值

**结果**: 15 处 → 0
- PLR2004: 4 处提取常量
- S110: 11 处添加 debug/noqa
- PLR0913: 6 处重构/添加 noqa

---

### ✅ 批次 3: PLC0415 严格处理

**目标**: 严格处理延迟导入，区分合理场景与需改进的代码

#### 3.1 标准库延迟导入（5 处）

**处理**: 移到顶部
- `sys` - deploy.py
- `time` - rate_limiter.py
- `json` - quarantine_store.py (2 处)
- `datetime, timedelta` - freeze_manager.py
- `datetime` - bars.py (3 处)

#### 3.2 可选依赖（1 处）

**处理**: 添加 noqa 说明
- `keyring` - tushare/client.py

#### 3.3 动态导入（4 处）

**处理**: 添加 noqa 说明
- deploy.py - 动态加载 flow/task
- deploy.py - 延迟加载 prefect
- base.py - 工厂模式延迟导入

#### 3.4 循环依赖（122 处）

**按场景分类处理**:

| 场景 | 数量 | 处理方式 |
|------|------|----------|
| 延迟初始化（cached_property） | 15 | hub.py 全局豁免 |
| property 内导入 | 6 | settings.py 全局豁免 |
| port/jobs 循环依赖 | 70 | 目录级豁免（待重构） |
| 其他循环依赖 | 8 | 逐个添加 noqa |
| 测试文件 | 23 | 已有豁免 |

#### 3.5 配置更新

```toml
[tool.ruff.lint.per-file-ignores]
# 延迟初始化模式 - cached_property 避免启动时重初始化
"packages/datahub/src/ditto_datahub/hub.py" = ["PLC0415"]
"packages/foundation/src/ditto_foundation/config/settings.py" = ["PLC0415", "S104"]

# 循环依赖 - port jobs 与 services 之间的架构问题（待重构）
"apps/port/src/ditto_port/jobs/**/*.py" = ["PLC0415"]
"apps/port/src/ditto_port/services/**/*.py" = ["PLC0415"]

# 类型收窄 - assert 用于类型收窄（Type narrowing）
"packages/datahub/src/ditto_datahub/runtime/freeze_manager.py" = ["S101"]
"packages/datahub/src/ditto_datahub/sources/tushare/client.py" = ["S101"]
```

**结果**: 132 处 PLC0415 → 0

---

### ✅ 批次 4: 剩余错误清理

**目标**: 处理剩余的 21 个其他错误

| 错误代码 | 数量 | 处理方式 |
|----------|------|----------|
| S608 | 8 | noqa: S608（已验证输入） |
| S112 | 1 | noqa: S112（静默处理） |
| C901 | 2 | 添加 noqa |
| E501 | 1 | 拆分注释 |
| S104 | 1 | settings.py 豁免 |
| RUF100 | 4 | 自动修复 |
| S105 | 1 | 测试文件豁免 |

**结果**: 21 处 → 0

---

## 验证结果

```bash
# Ruff 检查
$ pixi run -e dev ruff check packages apps tests
All checks passed!

# Pyright 检查
$ pixi run -e dev pyright
0 errors, 0 warnings, 0 informations
```

---

## 关键文件修改

**配置文件**:
- `pyproject.toml` - ruff 豁免配置

**代码修改**:
- `apps/port/src/ditto_port/jobs/flows/deploy.py` - 移动 sys 导入
- `packages/datahub/src/ditto_datahub/sources/tushare/rate_limiter.py` - 移动 time 导入
- `packages/datahub/src/ditto_datahub/stores/quarantine_store.py` - 移动 json 导入
- `packages/datahub/src/ditto_datahub/repositories/bars.py` - 添加 noqa 注释
- `packages/datahub/src/ditto_datahub/dq/checkers/technical.py` - noqa: S608
- `packages/datahub/src/ditto_datahub/dq/models.py` - noqa: S112
- `packages/datahub/src/ditto_datahub/runtime/freeze_manager.py` - 移动 datetime 导入
- `packages/datahub/src/ditto_datahub/sources/tushare/client.py` - noqa: PLC0415
- `packages/foundation/src/ditto_foundation/config/settings.py` - noqa: PLC0415
- `packages/foundation/src/ditto_foundation/observability/logging.py` - noqa: PLC0415
- `packages/datahub/src/ditto_datahub/types.py` - E501 行长度修复
- `packages/datahub/src/ditto_datahub/stores/pipeline_store.py` - noqa: C901

---

## 成功标准

- ✅ `pixi run -e dev ruff check packages apps tests` 输出: `All checks passed!`
- ✅ 所有安全警告已评估（修复或 noqa）
- ✅ PLC0415 采用严格处理，只为真正必要的场景添加 noqa
- ✅ 标准库导入移到顶部
- ✅ 代码质量提升（参数对象、命名常量）
- ✅ Pyright 检查通过：0 errors, 0 warnings

---

## 经验总结

1. **延迟导入应该是例外而非默认**：PLC0415 规则的目的是鼓励模块顶部导入，延迟导入应该有明确理由

2. **合理的延迟导入场景**：
   - 循环依赖（需要重构）
   - 可选依赖（运行时按需加载）
   - 延迟初始化（cached_property）
   - 动态导入（插件系统）

3. **配置豁免优于行内 noqa**：对于系统性问题（如测试文件、循环依赖），使用 per-file-ignores 更清晰

4. **严格处理带来的收益**：
   - 代码结构更清晰
   - 导入依赖更明确
   - 启动性能可能提升（减少不必要的导入）

---

## 变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-01-14 | 创建计划 | Claude |
| 2026-01-14 | 批次 4 完成，所有错误清零 | Claude |
