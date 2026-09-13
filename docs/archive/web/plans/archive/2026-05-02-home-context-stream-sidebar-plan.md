# 首页上下文流与侧栏优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 合并首页活动流与 AI 洞察，补强右侧上下文栏的信息密度，并让侧栏折叠按钮成为可用交互。

**Architecture:** 保持静态 prototype 结构，首页使用一个统一 intelligence stream 承载事件与洞察；右侧栏增加决策约束 section；侧栏折叠作为共享交互模块写入 `prototype-interactions.js`，由 `data-sidebar-shell` / `data-sidebar-toggle` 驱动。

**Tech Stack:** HTML prototype、CSS design tokens、vanilla JS、Vitest、JSDOM、Playwright。

---

### Task 1: Write Failing Tests

**Files:**
- Modify: `scripts/page-home-prototype.test.ts`

**Steps:**
1. Assert `[data-intelligence-stream]` exists and includes both activity and insight entries.
2. Assert no standalone `[data-contract-slot="agent-findings"]` panel remains in the default view.
3. Assert `[data-contract-slot="decision-constraints"]` has at least 3 constraint rows.
4. Use Playwright to click `[data-sidebar-toggle]` and verify shell state, `aria-expanded`, and collapsed icon strip.

### Task 2: Implement Homepage Structure

**Files:**
- Modify: `prototype/page-home.html`

**Steps:**
1. Merge Activity Feed and AI Insights into one panel.
2. Add mixed rows marked `data-stream-entry="activity"` and `data-stream-entry="insight"`.
3. Add Decision Constraints to the sidebar.
4. Add sidebar shell attributes and collapsed icon strip.

### Task 3: Implement Shared Sidebar Toggle

**Files:**
- Modify: `prototype/shared/prototype-interactions.js`

**Steps:**
1. Add `SidebarToggle` module.
2. Bind `[data-sidebar-toggle]` inside `[data-sidebar-shell]`.
3. Sync `data-sidebar-state`, `aria-expanded`, labels, and button glyph.
4. Initialize it in the shared `init()` sequence.

### Task 4: Verify

Run:
- `bun run test:run scripts/page-home-prototype.test.ts`
- `bun run test:run scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts`
- `bun scripts/run-prototype-gates.ts --prototype prototype/page-home.html`
- `bun run check`
