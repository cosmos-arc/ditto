# Phase 0 前置约束调优设计

**日期**: 2026-03-30
**状态**: 待实施
**关联设计**: [hybrid-plane-design](2026-03-30-architecture-hybrid-plane-design.md) | [phase0-1-plan](2026-03-30-phase0-1-implementation-plan.md)

---

## 1. 背景

Phase 0（Kernel 扩展）计划向 Kernel 包新增 4 个模块（clock.py、provider.py、pipeline.py、events.py），从 6 个公共符号扩展到 17 个。这些新增内容包括 Protocol 抽象和薄实现类。

**问题**：当前项目约束文件与 Phase 0 目标存在 3 处冲突，不解决则 CI/CLAUDE.md 规则会在开发过程中反复报错。

---

## 2. 冲突清单

### 冲突 1：[严重] Kernel 准入标准 — "不含方法" vs Protocol + 薄实现

- **当前约束**：`packages/kernel/CLAUDE.md` 准入标准要求"零业务行为：纯值对象/枚举/NewType，不含方法"
- **Phase 0 需要**：Clock、DataProvider、EventBus、Stage 等 Protocol 均包含方法签名；SimulatedClock、SimpleEventBus 是带方法实现的类
- **解决**：增量扩展准入标准，新增 Protocol/薄实现准入条款

### 冲突 2：[中等] Kernel 类型数量上限 — 20 vs 17（余量不足）

- **当前约束**：kernel 类型数量不超过 20 个
- **Phase 0 后**：17 个公共符号，只剩 3 个余量
- **解决**：去掉硬性数量上限，改为理由说明机制

### 冲突 3：[中等] Core 依赖声明不一致

- **architecture.md**：`ditto_core → ditto_kernel`（单依赖）
- **core/CLAUDE.md**：`core → kernel, datahub, infra`（三依赖）
- **Phase 1 目标**：Core 通过 DataProvider Protocol 消费数据，依赖收拢到 `core → kernel only`
- **解决**：Phase 1 完成后统一为 `core → kernel only`

---

## 3. 变更方案

### 3.1 `packages/kernel/CLAUDE.md` — 增量扩展

#### 3.1.1 新增「Protocol / 薄实现」准入标准

在现有「值对象准入标准」之后，新增并列条款：

```markdown
### Protocol / 薄实现准入标准

适用于 Clock、DataProvider、EventBus、Stage/Pipeline 等 Protocol 及其薄实现类
（SimulatedClock、RealtimeClock、SimpleEventBus）。

1. **预期跨层使用**：至少被 2 个业务包消费
   - Phase 0 定义阶段允许"预期"（在 PR 描述中声明）
   - Phase 1 完成后验证实际消费关系
2. **零业务逻辑**：Protocol 定义纯接口签名；薄实现不含领域逻辑
3. **无外部依赖**：仅依赖 Python 标准库
4. **实现体 < 30 行**：每个薄实现类的方法体总计不超过 30 行
5. **无 I/O**：不进行文件读写、网络请求、数据库操作

**薄实现豁免**：SimulatedClock / RealtimeClock / SimpleEventBus 属于系统级基础设施，
不受"不含方法"限制，但必须满足上述 5 条。
```

#### 3.1.2 去掉类型数量硬上限

将现有红线"kernel 类型数量超过 20 个"替换为：

```markdown
### 增长控制

- 不设硬性数量上限
- 每个新增类型必须在 PR 描述中包含 **2 行理由说明**：
  1. 为什么这个类型属于 kernel 而非业务包
  2. 预期被哪些业务包消费
```

#### 3.1.3 更新定位描述

将 Kernel 定位从"Shared Kernel（共享内核）"更新为"Shared Kernel — 类型 + Protocol 抽象 + 薄实现"。

### 3.2 `packages/core/CLAUDE.md` — 依赖规则统一

Phase 1 完成后（非 Phase 0 前置），更新 Core 依赖规则：

```markdown
## 依赖规则

- Core 可依赖: kernel
- Core 禁止依赖: datahub, port, infra

> **注**：Phase 1 前 Core 存在少量 datahub/infra 依赖（已在 importlinter ignore 列表中）。
> Phase 1 DataProvider 改造完成后，所有数据访问通过 kernel.DataProvider Protocol，
> Core 依赖收拢为 kernel only。
```

### 3.3 `.claude/rules/architecture.md` — 术语修正

将所有 `Server` / `Server Service` / `Server Flow` 替换为 `Port` / `Port Service` / `Port Flow`，与实际包名 `ditto_port` 对齐。

---

## 4. 执行计划

| 步骤 | 文件 | 变更 | 时机 |
|------|------|------|------|
| **Step -1a** | `packages/kernel/CLAUDE.md` | 增量扩展准入标准 + 去掉类型上限 + 更新定位 | Phase 0 前 |
| **Step -1b** | `.claude/rules/architecture.md` | 术语修正 Server → Port | Phase 0 前 |
| **Step +1** | `packages/core/CLAUDE.md` | 依赖规则统一为 kernel only | Phase 1 完成后 |
| **Step +2** | `packages/datahub/CLAUDE.md` | 新增 query/ 子模块描述 | Phase 1 Task 1a 时 |

### 验证

Step -1a 和 -1b 完成后运行：

```bash
pixi run -e dev check    # 确保规则文件修改不引入 CI 问题
pixi run -e dev arch-check  # 确保架构边界检查不受影响
```

---

## 5. 不需要修改的文件

| 文件 | 原因 |
|------|------|
| `.importlinter` | Phase 0/1 无新依赖方向，现有规则已覆盖 |
| `packages/kernel/pyproject.toml` | 零依赖，Phase 0 新增模块仅用标准库 |
| `packages/datahub/pyproject.toml` | 已声明 ditto-kernel 依赖 |
| `packages/core/pyproject.toml` | 已声明 ditto-kernel 依赖 |
| `.claude/rules/core.md` | 代码风格规则，与架构变更无冲突 |
| `.claude/rules/polars.md` | DataFrame 使用规范，无冲突 |
| `.claude/rules/python-test.md` | 测试规范，无冲突 |
| `.claude/rules/noqa-ignore.md` | noqa 使用规范，无冲突 |
| `.claude/rules/pit.md` | PIT 安全规范，无冲突 |
| `.claude/rules/workflow.md` | 开发流程规范，无冲突 |

---

## 6. 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| CLAUDE.md 修改引入歧义 | 低 | 增量扩展保持向后兼容，已有条款不变 |
| architecture.md 术语修正遗漏 | 低 | 全文搜索 Server 替换 |
| 去掉类型上限导致 Kernel 膨胀 | 低 | 通过 PR 描述理由说明机制 + 准入标准双重控制 |
