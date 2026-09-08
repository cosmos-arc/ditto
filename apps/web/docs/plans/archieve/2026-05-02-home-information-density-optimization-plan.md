# 首页信息密度优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将首页从“清爽待办页”提升为专业投资工作台首屏，让用户一眼看清账户、风险、信号、执行、模型与数据约束。

**Architecture:** 保持现有静态 prototype 架构，只修改 `page-home.html` 与首页原型测试。通过 DOM contract 约束信息密度、决策影响预览和工作队列结构，避免后续视觉调整削弱产品功能。

**Tech Stack:** HTML prototype、CSS design tokens、Vitest、JSDOM、Playwright。

---

### Task 1: 首页密度合同测试

**Files:**
- Modify: `scripts/page-home-prototype.test.ts`

**Step 1: Write the failing test**

Add tests requiring:
- `data-operating-summary` exposes at least 8 compact metrics.
- Metrics cover account, risk, work, execution, model, and data categories.
- `data-decision-impact` exposes at least 3 before/after impact rows.
- `data-worklist-row` exposes at least 6 visible priority rows with impact and SLA.

**Step 2: Run test to verify it fails**

Run: `bun run test:run scripts/page-home-prototype.test.ts`

Expected: FAIL because current homepage has only 5 pulse items, no decision impact rows, and no dense worklist rows.

### Task 2: 首页首屏结构优化

**Files:**
- Modify: `prototype/page-home.html`

**Step 1: Implement minimal structure**

Update:
- Global Pulse to a two-row compact operating summary.
- Decision Card to include adoption impact preview.
- Priority panel to render a dense worklist with P1/P2/P3 rows.

**Step 2: Run targeted tests**

Run: `bun run test:run scripts/page-home-prototype.test.ts`

Expected: PASS.

### Task 3: Full Verification

**Files:**
- Verify repository.

**Step 1: Run full check**

Run: `bun run check`

Expected: Biome, TypeScript, and Vitest pass.
