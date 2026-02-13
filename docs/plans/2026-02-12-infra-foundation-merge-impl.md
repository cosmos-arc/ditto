# Infra 与 Foundation 合并实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `packages/foundation/` 重构为 `packages/infra/`，区分技术基础设施与应用级服务

**Architecture:** 创建 `infra` 包，包含 `foundation/`（技术基础设施）和 `services/`（应用级服务）两个子模块。合并 foundation 和 port 的 notification 到统一位置。原子性迁移，全量更新导入路径。

**Tech Stack:** Python 3.12, setuptools, pixi

---

## Task 1: 创建 infra 包结构

**Files:**
- Create: `packages/infra/pyproject.toml`
- Create: `packages/infra/src/ditto_infra/__init__.py`
- Create: `packages/infra/src/ditto_infra/foundation/__init__.py`
- Create: `packages/infra/src/ditto_infra/services/__init__.py`
- Create: `packages/infra/src/ditto_infra/services/notification/__init__.py`

**Step 1: 创建目录结构**

```bash
mkdir -p packages/infra/src/ditto_infra/{foundation,services/notification}
mkdir -p packages/infra/tests
```

**Step 2: 创建 pyproject.toml**

```toml
# packages/infra/pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ditto-infra"
requires-python = ">= 3.12"
version = "0.1.0"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"
```

**Step 3: 创建顶层 __init__.py**

```python
# packages/infra/src/ditto_infra/__init__.py
"""Ditto 统一基础设施层.

包含:
- foundation: 技术基础设施（完全业务无关）
- services: 应用级基础设施服务
"""
__all__ = ["foundation", "services"]
```

```python
# packages/infra/src/ditto_infra/foundation/__init__.py
"""技术基础设施 - 完全业务无关的底层能力."""
```

```python
# packages/infra/src/ditto_infra/services/__init__.py
"""应用级基础设施服务."""
```

```python
# packages/infra/src/ditto_infra/services/notification/__init__.py
"""通知服务 - 可含业务上下文的基础服务."""
```

**Step 4: 验证结构**

```bash
ls -la packages/infra/src/ditto_infra/
# 应显示: foundation/  services/  __init__.py
```

**Step 5: Commit**

```bash
git add packages/infra/
git commit -m "feat(infra): 创建 infra 包结构

- 添加 pyproject.toml 构建配置
- 创建 foundation/ 和 services/ 子模块目录
- 初始化 notification 服务目录"
```

---

## Task 2: 迁移 foundation 模块到 infra/foundation

**Files:**
- Move: `packages/foundation/src/ditto_foundation/*` → `packages/infra/src/ditto_infra/foundation/`
- Move: `packages/foundation/tests/*` → `packages/infra/tests/`
- Exclude: `notification/` 目录（将在 Task 3 处理）

**Step 1: 迁移源码（排除 notification）**

```bash
# 迁移所有模块
for dir in cache checksum concurrency config db observability pit quality util; do
  cp -r packages/foundation/src/ditto_foundation/$dir packages/infra/src/ditto_infra/foundation/
done

# 复制顶层文件
cp packages/foundation/src/ditto_foundation/__init__.py packages/infra/src/ditto_infra/foundation/
cp packages/foundation/src/ditto_foundation/py.typed packages/infra/src/ditto_infra/foundation/
cp packages/foundation/src/ditto_foundation/README.md packages/infra/src/ditto_infra/foundation/
```

**Step 2: 迁移测试**

```bash
cp -r packages/foundation/tests/* packages/infra/tests/
```

**Step 3: 验证文件数量**

```bash
# 源文件（不含 notification）
find packages/infra/src/ditto_infra/foundation -name "*.py" | wc -l
# 预期: ~30

# 测试文件
find packages/infra/tests -name "*.py" | wc -l
# 预期: ~39
```

**Step 4: Commit**

```bash
git add packages/infra/
git commit -m "feat(infra): 迁移 foundation 模块到 infra/foundation

- 迁移 cache, checksum, concurrency, config, db, observability, pit, quality, util
- 迁移所有单元测试和集成测试
- notification 模块将在后续任务处理"
```

---

## Task 3: 合并 notification 模块

**Files:**
- Move: `packages/foundation/src/ditto_foundation/notification/*` → `packages/infra/src/ditto_infra/services/notification/`
- Move: `apps/port/src/ditto_port/notifications/*` → `packages/infra/src/ditto_infra/services/notification/`

**Step 1: 迁移 foundation notification 基础能力**

```bash
# 迁移 channels, templates 目录和核心文件
cp -r packages/foundation/src/ditto_foundation/notification/channels packages/infra/src/ditto_infra/services/notification/
cp -r packages/foundation/src/ditto_foundation/notification/templates packages/infra/src/ditto_infra/services/notification/
cp packages/foundation/src/ditto_foundation/notification/*.py packages/infra/src/ditto_infra/services/notification/
```

**Step 2: 合并 port notification 业务层**

```bash
# 合并 manager.py 和 business.py
cp apps/port/src/ditto_port/notifications/manager.py packages/infra/src/ditto_infra/services/notification/
cp apps/port/src/ditto_port/notifications/business.py packages/infra/src/ditto_infra/services/notification/

# 合并业务模板
cp -r apps/port/src/ditto_port/notifications/templates/* packages/infra/src/ditto_infra/services/notification/templates/
```

**Step 3: 更新 notification __init__.py**

```python
# packages/infra/src/ditto_infra/services/notification/__init__.py
"""通知服务 - 可含业务上下文的基础服务.

包含:
- 通用发送能力: NotificationSender, EmailSender, WebhookSender, TelegramSender
- 消息模型: Notification, NotificationLevel
- 模板引擎: TemplateEngine
- 业务告警: AlertManager, alert_dq_failure
"""
from ditto_infra.services.notification.message import Notification, NotificationLevel
from ditto_infra.services.notification.sender import NotificationSender
from ditto_infra.services.notification.template import TemplateEngine
from ditto_infra.services.notification.channels.email import EmailSender
from ditto_infra.services.notification.channels.webhook import WebhookSender
from ditto_infra.services.notification.channels.telegram import TelegramSender
from ditto_infra.services.notification.manager import AlertManager
from ditto_infra.services.notification.business import alert_dq_failure

__all__ = [
    # 消息模型
    "Notification",
    "NotificationLevel",
    # 发送能力
    "NotificationSender",
    "EmailSender",
    "WebhookSender",
    "TelegramSender",
    # 模板
    "TemplateEngine",
    # 业务告警
    "AlertManager",
    "alert_dq_failure",
]
```

**Step 4: Commit**

```bash
git add packages/infra/src/ditto_infra/services/notification/
git commit -m "feat(infra): 合并 notification 服务

- 从 foundation/notification 迁移通用发送能力
- 从 port/notifications 合并业务告警逻辑
- 统一导出接口"
```

---

## Task 4: 批量更新导入路径 - 源码

**Files:**
- Modify: 所有 `from ditto_foundation` → `from ditto_infra.foundation`
- Modify: 所有 `from ditto_port.notifications` → `from ditto_infra.services.notification`

**Step 1: 更新 foundation 内部导入**

```bash
# 在 packages/infra 内部更新 foundation 自引用
find packages/infra/src -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find packages/infra/src -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 2: 更新 datahub 导入**

```bash
find packages/datahub/src -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find packages/datahub/src -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 3: 更新 core 导入**

```bash
find packages/core/src -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find packages/core/src -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 4: 更新 port 导入（foundation 部分）**

```bash
find apps/port/src -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find apps/port/src -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 5: 更新 port 导入（notification 部分）**

```bash
# 更新 port 内部对 notifications 的引用
find apps/port/src -name "*.py" -exec sed -i \
  's/from ditto_port\.notifications\./from ditto_infra.services.notification./g' {} \;

find apps/port/src -name "*.py" -exec sed -i \
  's/import ditto_port\.notifications/import ditto_infra.services.notification/g' {} \;
```

**Step 6: Commit**

```bash
git add packages/ apps/port/src/
git commit -m "refactor: 更新所有源码导入路径

- ditto_foundation.* → ditto_infra.foundation.*
- ditto_port.notifications.* → ditto_infra.services.notification.*"
```

---

## Task 5: 批量更新导入路径 - 测试

**Files:**
- Modify: 所有测试文件中的导入路径

**Step 1: 更新 infra 测试导入**

```bash
find packages/infra/tests -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find packages/infra/tests -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 2: 更新 datahub 测试导入**

```bash
find packages/datahub/tests -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find packages/datahub/tests -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 3: 更新 core 测试导入**

```bash
find packages/core/tests -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find packages/core/tests -name "*.py" -exec sed -i \
  's/import ditto_foundation\./import ditto_infra.foundation./g' {} \;
```

**Step 4: 更新 port 测试导入**

```bash
find apps/port/tests -name "*.py" -exec sed -i \
  's/from ditto_foundation\./from ditto_infra.foundation./g' {} \;

find apps/port/tests -name "*.py" -exec sed -i \
  's/from ditto_port\.notifications\./from ditto_infra.services.notification./g' {} \;

find apps/port/tests -name "*.py" -exec sed -i \
  's/import ditto_port\.notifications/import ditto_infra.services.notification/g' {} \;
```

**Step 5: Commit**

```bash
git add packages/*/tests apps/port/tests/
git commit -m "refactor: 更新所有测试导入路径

- ditto_foundation.* → ditto_infra.foundation.*
- ditto_port.notifications.* → ditto_infra.services.notification.*"
```

---

## Task 6: 更新配置文件

**Files:**
- Modify: `pixi.toml`
- Modify: `apps/port/pyproject.toml`（如有 foundation 依赖）

**Step 1: 更新 pixi.toml**

```bash
# 替换 ditto-foundation 为 ditto-infra
sed -i 's|ditto-foundation = { path = "packages/foundation"|ditto-infra = { path = "packages/infra"|' pixi.toml
```

**Step 2: 检查 apps/port/pyproject.toml**

```bash
# 查看是否有 foundation 依赖声明
cat apps/port/pyproject.toml
# 如有，更新为 ditto-infra
```

**Step 3: Commit**

```bash
git add pixi.toml apps/port/pyproject.toml
git commit -m "chore: 更新 pixi.toml 包依赖

- ditto-foundation → ditto-infra"
```

---

## Task 7: 更新架构约束配置

**Files:**
- Modify: `.importlinter`（如有）

**Step 1: 检查 import-linter 配置**

```bash
cat .importlinter 2>/dev/null || cat importlinter.cfg 2>/dev/null || echo "未找到配置"
```

**Step 2: 更新模块名称引用**

```bash
# 如有配置，更新 ditto_foundation 为 ditto_infra
sed -i 's/ditto_foundation/ditto_infra/g' .importlinter 2>/dev/null
```

**Step 3: Commit**

```bash
git add .importlinter importlinter.cfg 2>/dev/null
git commit -m "chore: 更新 import-linter 配置

- ditto_foundation → ditto_infra"
```

---

## Task 8: 删除旧目录

**Files:**
- Delete: `packages/foundation/`
- Delete: `apps/port/src/ditto_port/notifications/`

**Step 1: 确认迁移完成**

```bash
# 确认新位置文件完整
find packages/infra/src -name "*.py" | wc -l
# 预期: ~45（foundation ~30 + notification ~10 + init files）

find packages/infra/tests -name "*.py" | wc -l
# 预期: ~42（原有 39 + notification tests）
```

**Step 2: 删除旧 foundation 包**

```bash
rm -rf packages/foundation/
```

**Step 3: 删除旧 port notifications**

```bash
rm -rf apps/port/src/ditto_port/notifications/
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 删除旧的 foundation 包和 port notifications

- 删除 packages/foundation/（已迁移到 packages/infra/）
- 删除 apps/port/src/ditto_port/notifications/（已合并到 infra/services/notification/）"
```

---

## Task 9: 运行完整验证

**Step 1: 重新安装依赖**

```bash
pixi install
```

**Step 2: 运行类型检查**

```bash
pixi run -e dev type
# 预期: 通过，无错误
```

**Step 3: 运行 lint 检查**

```bash
pixi run -e dev lint
# 预期: 通过
```

**Step 4: 运行测试**

```bash
pixi run -e dev test
# 预期: 全部通过
```

**Step 5: 运行架构检查**

```bash
pixi run -e dev arch-check
# 预期: 通过，无循环依赖
```

**Step 6: 运行完整 check**

```bash
pixi run -e dev check
# 预期: 全部通过
```

**Step 7: Commit 验证结果**

```bash
git add -A
git commit -m "chore: 验证 infra-foundation 合并完成

- 类型检查通过
- lint 检查通过
- 全部测试通过
- 架构约束检查通过"
```

---

## Task 10: 更新设计文档

**Files:**
- Modify: `docs/plans/2026-02-12-infra-foundation-merge-design.md`

**Step 1: 更新设计文档状态**

在设计文档顶部添加：

```markdown
> 状态：✅ 已完成
> 完成日期：2026-02-XX
> 实施计划：[2026-02-12-infra-foundation-merge-impl.md](2026-02-12-infra-foundation-merge-impl.md)
```

**Step 2: Commit**

```bash
git add docs/plans/2026-02-12-infra-foundation-merge-design.md
git commit -m "docs: 标记 infra-foundation 合并设计为已完成"
```

---

## 风险与回滚

**风险点：**
1. 导入路径更新遗漏 → 全局搜索验证
2. 测试 fixture 路径问题 → 单独检查 conftest.py
3. DI registry 类型引用 → 检查 registry/*.py

**回滚方案：**
```bash
# 如需回滚整个重构
git revert HEAD~10  # 根据实际 commit 数量调整
```

---

## 验收清单

- [ ] `pixi run -e dev type` 通过
- [ ] `pixi run -e dev lint` 通过
- [ ] `pixi run -e dev test` 全部通过
- [ ] `pixi run -e dev arch-check` 通过
- [ ] `pixi run -e dev check` 完整通过
- [ ] 分支覆盖率 ≥ 80%
- [ ] 无残留的 `ditto_foundation` 导入
- [ ] 无残留的 `ditto_port.notifications` 导入
