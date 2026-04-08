# 文档全量更新计划

**日期**: 2026-04-04
**状态**: 待执行
**范围**: 全量更新所有过期 README.md / AGENTS.md 文件

---

## 审计结果摘要

| 严重程度 | 数量 | 说明 |
|---------|------|------|
| 严重过期（结构性错误） | 8 | 反映旧架构（ditto-core / apps/port / ditto-datahub） |
| 中度过期（内容过时） | 5 | 引用旧路径或旧 API |
| 轻微/索引更新 | 6 | 链接失效、状态陈旧 |
| 无需更新 | 8 | CLAUDE.md 全部准确、AGENTS.md 为副本、部分索引页准确 |

---

## 第一批：严重过期 — 核心包 README（结构性重写）

### 1.1 `README.md`（根目录）

**当前问题**:
- 架构图仍为旧三层（ditto-core / ditto-datahub / ditto-infra）
- 项目结构显示 `interfaces/` → 应为 `interfaces/`
- 引用 `packages/core/` → 应为 `packages/engine/`
- 引用 `packages/data/` → 应为 `packages/data/`
- 缺少 packages/app/、packages/analytics/、packages/kernel/ 的描述
- 相关文档链接指向不存在文件
- 版本停留在 v0.9.0 Phase 2

**更新内容**:
- 重写架构图为 6 层结构（interfaces → app → engine → data → infra / kernel）
- 更新项目结构树为实际目录
- 更新核心功能描述（反映 Phase 4+ 重构）
- 修正所有链接
- 更新版本号和变更记录

### 1.2 `packages/engine/README.md`

**当前问题**:
- 架构图显示 `apps/port`
- 模块仍写 `strategy/` → 实际为 `alpha/`
- 引用 `engine/` 子模块（Expression DSL）→ 已迁移到 analytics
- 引用 `quality/` → 已迁移到 data
- 依赖描述错误
- 变更日志中大量旧引用

**更新内容**:
- 重写架构图（engine → kernel + data.errors + data.provider）
- 更新模块结构：alpha / execution / backtest / portfolio / accounting / orchestrator / risk
- 移除已迁移模块（quality、expression DSL）
- 精简变更记录（保留最近 3 版本，旧版归档）

### 1.3 `interfaces/README.md`

**当前问题**:
- 标题为 "ditto-port" → 应为 "ditto-interfaces"
- 目录结构显示 `interfaces/src/ditto_interfaces/` → 应为 `interfaces/src/ditto_interfaces/`
- 架构图和服务描述全基于旧路径
- services 描述中业务逻辑已迁入 `ditto_app`

**更新内容**:
- 重写为 ditto-interfaces 定位
- 更新目录结构为实际路径
- 更新架构图反映当前分层
- 精简服务描述（业务逻辑引用 ditto_app）

### 1.4 `packages/kernel/README.md`

**当前问题**:
- 架构图显示 `apps/port`
- 模块结构只列 identity.py 和 enums.py，缺少 clock.py / events.py / specs.py
- 类型清单只有 5 个，实际 12+

**更新内容**:
- 更新架构图
- 补全模块结构
- 更新类型清单（从 CLAUDE.md 同步）

### 1.5 `packages/engine/src/ditto_engine/README.md`

**当前问题**:
- 标题为 "ditto-core"
- 模块列表严重过期（strategy → alpha，quality 已迁出）
- 使用示例引用旧 API

**更新内容**:
- 更新标题和模块结构
- 移除已迁出模块描述
- 更新使用示例

### 1.6 `packages/data/src/ditto_data/README.md`

**当前问题**:
- 架构图显示 `ditto-core`
- 引用 `accessors/` 目录（已不存在）
- DQ 引用指向 ditto_engine.quality（已迁到 ditto_data.quality）

**更新内容**:
- 更新架构图和模块结构
- 修正 DQ 引用
- 更新使用示例

### 1.7 `packages/data/src/ditto_data/storage/README.md`

**当前问题**:
- 引用不存在的 `domains/` 目录结构
- 所有使用示例路径错误

**更新内容**:
- 更新目录结构描述为实际的 stores/ + services/ 模式
- 修正所有导入示例

### 1.8 `packages/infra/tests/README.md` + `unit/README.md` + `integration/README.md`

**当前问题**:
- 所有路径引用 `packages/foundation/` → 应为 `packages/infra/`

**更新内容**:
- 全局替换路径引用

---

## 第二批：中度过期 — 导入路径和引用更新

### 2.1 `packages/data/README.md`（外层）

**当前问题**:
- 架构图显示 "Port Layer (apps/port)" → 应为 interfaces
- 非常冗长（1200+ 行）
- DQ 配置路径旧引用

**更新内容**:
- 修正架构图
- 更新 DQ 配置路径为 `packages/data/config/dq/`
- 归档旧变更记录（保留最近 3 版本）

### 2.2 `packages/infra/src/ditto_infra/foundation/util/README.md`

**当前问题**:
- 所有导入使用 `ditto_foundation` → 应为 `ditto_infra.foundation`

**更新内容**:
- 批量替换导入路径

### 2.3 `packages/infra/src/ditto_infra/foundation/observability/README.md`

**当前问题**:
- 所有导入使用 `ditto_foundation`
- 引用 "Port" 层 → 应为 interfaces

**更新内容**:
- 批量替换导入路径和层名引用

### 2.4 `packages/data/src/ditto_data/sources/README.md`

**当前问题**:
- 导入 `ditto_foundation.logger` → 应为 `ditto_infra.foundation`
- 旧 sprint 文档引用

**更新内容**:
- 更新导入路径
- 更新文档交叉引用

### 2.5 `packages/data/src/ditto_data/sources/tushare/README.md`

**当前问题**:
- Data hub 使用模式可能已过时
- 部分导入路径不确定

**更新内容**:
- 验证并更新 API 示例
- 修正导入路径

---

## 第三批：轻度过期 — 索引和状态更新

### 3.1 `docs/plans/README.md`

**当前问题**: 目录结构示例不匹配实际

**更新**: 更新目录结构描述

### 3.2 `docs/sprints/README.md`

**当前问题**: Sprint 2-4 状态陈旧

**更新**: 更新 sprint 状态

### 3.3 `deploy/docker/README.md`

**当前问题**: 链接到不存在的 `docs/plans/2026-02-18-docker-deployment-design.md`

**更新**: 移除或修正断链

### 3.4 `deploy/observability/README.md`

**当前问题**: 引用不存在的 PowerShell 脚本

**更新**: 移除断链引用

### 3.5 `.github/workflows/README.md`

**当前问题**: 大量描述不存在的 `deploy.yml`

**更新**: 标记为规划中或移除描述

### 3.6 `docs/design/unified-feature-factor-engine/README.md`

**当前问题**: 2 个断链（plan 文件不存在）

**更新**: 移除或标记断链

---

## 第四批：轻微更新

### 4.1 `packages/engine/src/ditto_engine/alpha/README.md`
- 标题使用旧 "strategy" 名称 → 更新为 "alpha"
- 补全策略模板列表（4 个）

### 4.2 `packages/engine/src/ditto_engine/portfolio/README.md`
- 补充 `InverseVolAllocator` 描述

### 4.3 `packages/data/src/ditto_data/helpers/README.md`
- 修正 `domains/market/` 交叉引用

### 4.4 `packages/data/src/ditto_data/runtime/README.md`
- 验证组件是否仍在 runtime/ 或已迁移到 infra

### 4.5 `packages/infra/README.md`（外层）
- 架构图补充 kernel 层

---

## 不需要更新的文件

| 文件 | 原因 |
|------|------|
| 所有 CLAUDE.md（8 个） | Phase 4 中已更新，全部准确 |
| 所有 AGENTS.md（6 个） | 与 CLAUDE.md 同步，作为 agent 副本 |
| `docs/adr/README.md` | 最近更新（2026-04-03），准确 |
| `docs/plans/archive/README.md` | 索引准确 |
| `docs/design/README.md` | 索引基本准确 |
| `docs/design/unified-feature-factor-engine/archive/README.md` | 准确 |
| `interfaces/tests/fixtures/golden_expected/` 下 4 个 README | 占位文件，无需更新 |
| `interfaces/tests/tdx_samples/` 下 2 个 README | 数据占位文件 |
| `.pytest_cache/README.md` | 自动生成 |

---

## 执行策略

### 优先级

1. **第一批**（8 个文件）：结构性重写，最高优先级
2. **第二批**（5 个文件）：路径替换，中等优先级
3. **第三批**（6 个文件）：断链修复
4. **第四批**（5 个文件）：小修补

### 原则

- CLAUDE.md 为权威来源，README 以 CLAUDE.md 内容为准
- 变更记录保留最近 3 版本，旧版移到 `archive/` 或删除
- 架构图统一使用 6 层结构
- 使用示例必须验证导入路径正确
- 所有 `apps/port` → `interfaces`，`ditto-core` → `ditto_engine`，`ditto-datahub` → `ditto_data`，`ditto_foundation` → `ditto_infra.foundation`

### 执行方式

使用并行 agent 分批执行，每批完成后运行 `pixi run -e dev check` 验证。
