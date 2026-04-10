# 规则与文档漂移清理计划

**版本**: v1.0
**日期**: 2026-02-17
**状态**: ✅ 已确认

---

## 背景

项目经历了多次架构重构（Foundation 合并到 Infra、V5 架构重构等），导致规则文件、文档与代码之间存在漂移。本计划按优先级分四个阶段进行全面清理。

## 漂移总览

| 类别 | 严重程度 | 影响 |
|------|---------|------|
| 规则文件引用不存在文件 | 🔴 严重 | CLAUDE.md 引用 foundation.md、datahub.md 但文件不存在 |
| 术语不一致 | 🟡 中等 | 文档用 "Foundation" 但代码是 "infra" |
| 设计文档冗余 | 🟢 轻微 | docs/designs/ 与 docs/design/ 重复 |
| 缺失文档 | 🟢 轻微 | 部分包缺少 README 或 CLAUDE.md |

---

## P0：规则文件紧急修复

**目标**: 确保所有规则文件引用有效，分层规范去中心化

### 当前状态

| 包/应用 | CLAUDE.md 状态 | 需要操作 |
|---------|---------------|---------|
| `packages/data/` | ✅ 已存在，内容完善 | 保持 |
| `packages/infra/` | ❌ 不存在 | 新建 |
| `packages/core/` | ❌ 不存在 | 新建 |
| `apps/port/` | ❌ 不存在 | 新建 |

### 执行步骤

#### 步骤 1：创建 `packages/infra/CLAUDE.md`

**内容来源**：
- `architecture.md` 第 59-79 行（横切层定义）
- `config.md` 中的配置规范（部分）

**包含模块**：
- `config` - 配置管理
- `observability` - 可观测性
- `util` - 通用工具
- `cache` - 缓存
- `concurrency` - 并发控制
- `db` - 数据库连接

#### 步骤 2：创建 `packages/core/CLAUDE.md`

**内容来源**：
- `architecture.md` 中的子领域分层规范（Domain Layer）
- `core.md` 中的 Python 规范（部分通用内容保留在根目录）

**包含领域**：
- `quality` - 数据质量引擎
- `factor` - 因子计算
- `ml` - 机器学习
- `risk` - 风险管理
- `strategy` - 策略逻辑

#### 步骤 3：创建 `apps/port/CLAUDE.md`

**内容来源**：
- `server.md` 全部内容（FastAPI、Prefect、数据摄入任务）

**包含内容**：
- FastAPI 规范
- Prefect 规范
- 数据摄入 T0/T1/T2/T3
- 导入规范

#### 步骤 4：更新根目录 `CLAUDE.md`

修改分层规范引用：

```diff
-详细分层规范：
-- Foundation → [foundation.md](.claude/rules/foundation.md)
-- DataHub → [datahub.md](.claude/rules/datahub.md) | [pit.md](.claude/rules/pit.md)
-- Core → [core.md](.claude/rules/core.md)
-- Server → [server.md](.claude/rules/server.md)
+详细分层规范：
+- Infra → [packages/infra/CLAUDE.md](packages/infra/CLAUDE.md)
+- DataHub → [packages/data/CLAUDE.md](packages/data/CLAUDE.md) | [pit.md](.claude/rules/pit.md)
+- Core → [packages/core/CLAUDE.md](packages/core/CLAUDE.md)
+- Port → [apps/port/CLAUDE.md](apps/port/CLAUDE.md)
```

#### 步骤 5：清理 `architecture.md`

- 移除已迁移到各包的详细分层规范
- 保留通用架构原则和依赖图
- 修复代码示例中的导入路径错误

#### 步骤 6：删除 `server.md`

- 内容已迁移到 `apps/port/CLAUDE.md`
- 删除原文件

### P0 验收标准

- [ ] `packages/infra/CLAUDE.md` 和 `AGENTS.md` 存在且内容正确
- [ ] `packages/core/CLAUDE.md` 和 `AGENTS.md` 存在且内容正确
- [ ] `apps/port/CLAUDE.md` 和 `AGENTS.md` 存在且内容正确
- [ ] 根目录 `CLAUDE.md` 引用全部有效
- [ ] `.claude/rules/server.md` 已删除

> **注意**: 各层级的 `AGENTS.md` 与 `CLAUDE.md` 内容保持一致。`CLAUDE.md` 供 Claude Code 使用，`AGENTS.md` 供其他 AI Agent 使用。

---

## P1：架构规则同步

**目标**: 统一术语和路径，确保文档与代码一致

### 需要修复的文件

| 文件 | 问题数量 | 主要问题 |
|------|---------|---------|
| `architecture.md` | 6 处 | `packages/foundation` → `packages/infra`，导入路径错误 |
| `config.md` | 3 处 | 路径格式不规范 |
| `python-test.md` | 8+ 处 | `packages/foundation` 路径引用 |
| `core.md` | 3 处 | 导入路径需验证 |

### 修复规则

| 错误 | 正确 |
|------|------|
| `packages/foundation` | `packages/infra` |
| `ditto_infra.observability` | `ditto_infra.foundation.observability` |
| `ditto_infra.config` | `ditto_infra.foundation.config` |
| `infra/foundation/config/...` | `packages/infra/src/ditto_infra/foundation/config/...` |

### 执行步骤

1. **修复 architecture.md**
   - 更新依赖图中的 `packages/foundation` → `packages/infra`
   - 修复代码示例导入路径
   - 更新 "Foundation Layer" 为 "Infra Layer (含 Foundation 子模块)"

2. **修复 config.md**
   - 统一路径格式为完整模块路径

3. **修复 python-test.md**
   - 更新 `packages/foundation` → `packages/infra`
   - 更新测试路径示例

4. **修复 core.md**
   - 验证并修复导入路径

### P1 验收标准

- [ ] 所有规则文件中无 `packages/foundation` 引用
- [ ] 导入路径与实际代码结构一致
- [ ] `pixi run -e dev check` 通过

---

## P2：设计文档审计

**目标**: 清理冗余文档，确保设计文档与架构一致

### 发现的问题

| 文件/目录 | 问题 | 建议操作 |
|-----------|------|---------|
| `docs/designs/` | 与 `docs/design/` 重复，只有一个文件 | 合并到 `docs/design/` 或归档 |
| `docs/design/README.md` | 引用 "Runtime Layer 基础设施" | 检查是否与当前架构一致 |
| `docs/design/02_data_design.md` | 引用 "Runtime Layer" | 检查术语是否需要更新 |

### 执行步骤

1. **清理重复目录**
   - 将 `docs/designs/quant-architecture-alignment.md` 移到 `docs/design/` 或归档
   - 删除空的 `docs/designs/` 目录

2. **审计设计文档术语**
   - 检查并更新 "Runtime Layer" 术语
   - 更新 `docs/design/README.md` 索引

3. **检查 `docs/sprints/` 和 `docs/reviews/`**
   - 确认是否需要归档旧内容

### P2 验收标准

- [ ] `docs/designs/` 目录已清理
- [ ] 设计文档术语与代码一致
- [ ] 文档索引准确

---

## P3：补充缺失文档

**目标**: 确保每个包都有完整的 README 和 CLAUDE.md

### 当前文档状态

| 包/应用 | README.md | CLAUDE.md | 说明 |
|---------|-----------|-----------|------|
| `packages/infra/` | ❌ | ❌ → P0 创建 | 需要新建 |
| `packages/data/` | ✅ | ✅ | 已完善 |
| `packages/core/` | ✅（有术语漂移） | ❌ → P0 创建 | README 中引用 `ditto-foundation` |
| `apps/port/` | ✅ | ❌ → P0 创建 | 需要从 server.md 迁移 |
| `apps/web/` | ✅ | ❌ | 暂无实际代码，低优先级 |

### 执行步骤

1. **创建 `packages/infra/README.md`**
   - 概述 Infra 包职责
   - 列出子模块
   - 说明 Foundation 合并历史

2. **更新 `packages/core/README.md`**
   - 修复架构图中的 `ditto-foundation` → `ditto-infra`
   - 修复依赖说明

3. **审计 `docs/design/11_port_architecture.md`**
   - 检查与当前 Port 层实现是否一致

### P3 验收标准

- [ ] `packages/infra/README.md` 存在
- [ ] `packages/core/README.md` 术语正确
- [ ] Port 架构文档与实现一致

---

## 执行计划

| 阶段 | 预计工作量 | 依赖 |
|------|-----------|------|
| P0 | 中 | 无 |
| P1 | 小 | P0 完成 |
| P2 | 小 | P1 完成 |
| P3 | 小 | P0 完成 |

**建议执行顺序**: P0 → P1 → P2 → P3

---

## 相关文档

- [CLAUDE.md](/.claude/CLAUDE.md) - 项目指南
- [architecture.md](/.claude/rules/architecture.md) - 架构规范
- [packages/data/CLAUDE.md](/packages/data/CLAUDE.md) - DataHub 规范
