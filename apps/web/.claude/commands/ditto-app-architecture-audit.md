---
name: ditto-app-architecture-audit
description: 全库架构审计 - 检查分层、组件依赖、状态管理、Design Token 使用
---

# /ditto-app-architecture-audit 命令

运行全库架构审计，生成完整的审计报告。

## 审计范围

- `src/features/` - 业务功能模块
- `src/components/` - 共享组件
- `src/lib/` - 工具函数 + API 层
- `src/styles/` - Design Tokens

## 执行步骤

### 1. 运行代码质量检查

```bash
bunx biome check .
bunx tsc --noEmit
bun run test --coverage
```

### 2. 加载规则和配置

- 读取 `CLAUDE.md` - 项目核心约束
- 读取 `.claude/rules/*.md` - 具体规范
- 读取 `biome.json` - Biome 配置
- 读取 `tsconfig.json` - TypeScript 配置

### 3. 架构约束检查

- 使用 `Grep` 检测跨 Feature 直接导入
- 使用 `Grep` 追踪依赖链，检测循环依赖
- 使用 `Read` 分析组件规模和结构
- 检查 Feature 边界是否清晰

**Feature 边界检查**：
- ❌ Feature A → Feature B 内部组件（直接导入）
- ✅ Feature A → Feature B barrel export
- ❌ `components/ui/` → Feature
- ❌ `lib/` → Feature

### 4. 工程实践检查

- 使用 `Grep` 识别组件规模（>200行）
- 使用 `Grep` 检测 `any` 类型滥用
- 使用 `Grep` 检测 `@ts-ignore` / `@ts-expect-error`
- 使用 `Grep` 检测 inline styles
- 检查 shadcn/ui 组件是否被复用

### 5. 状态管理检查

- API 数据是否走 TanStack Query
- 全局状态是否走 Zustand
- 是否存在 prop drilling（深层传递）

### 6. Design Token 合规检查

- 是否使用了 OKLCH 色彩空间
- Semantic Token 命名是否遵循规范
- 暗色/亮色映射是否完整
- 是否存在硬编码颜色值

### 7. 生成报告

输出到 `docs/reviews/YYYY-MM-DD-architecture-audit.md`

**报告结构**：
- Executive Summary（关键统计、Top 3 问题）
- Findings（详细发现，带证据和修复建议）
- Refactor Plan（按 P0/P1/P2 分组）

## 检查项清单

### 架构约束
- [ ] Feature 边界检查
- [ ] 循环依赖检查
- [ ] 依赖方向检查
- [ ] barrel export 合规

### 组件质量
- [ ] 组件规模检查（>200行）
- [ ] shadcn/ui 复用检查
- [ ] CVA 变体模式检查
- [ ] Props 类型完整性

### 类型安全
- [ ] `any` 类型使用
- [ ] `@ts-ignore` / `@ts-expect-error`
- [ ] tsc 错误数

### 样式合规
- [ ] inline styles 检测
- [ ] Design Token 使用
- [ ] OKLCH 色彩空间
- [ ] 暗色/亮色映射

### 测试覆盖
- [ ] 测试可运行性
- [ ] 测试成功率
- [ ] 分支覆盖率 ≥ 80%

## 示例输出

```
🔍 Architecture Audit Report

📊 Summary:
  Blocker: 0 | High: 3 | Medium: 8 | Low: 5

🔴 Top 3 Issues:
  1. [ARCH-001] Feature dashboard 直接导入 Feature chart 内部组件
  2. [TYPE-001] 5 处 any 类型未收敛
  3. [STYLE-001] 3 处 inline styles

📄 Full report: docs/reviews/2026-03-25-architecture-audit.md
```
