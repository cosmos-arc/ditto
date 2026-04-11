# Milestone 4：高保真收尾 — 详细执行设计

> **日期**：2026-04-10
> **父文档**：[prototype-recovery-design.md](./2026-04-10-prototype-recovery-design.md)
> **前置**：Milestone 1 ✅ / Milestone 2 ✅ / Milestone 3 ✅
> **目标**：在结构稳定后，集中处理视觉与交互细节，消除设计系统漂移

---

## 1. 当前基线

| 维度 | 状态 | 数量 |
|------|------|------|
| 占位文案 | 已清零 | 0 |
| 硬编码颜色 | 已清零 | 0 |
| 未定义 token | 已清零 | 0 |
| 旧式 token 引用 | 需迁移 | ~92 处 / 42 文件 |
| 原始 Tailwind spacing | 需收敛 | 242 处 / 50 文件 |
| 任意字号值 `text-[Npx]` | 需替换 | ~35 处 / 15 文件 |
| 动画/过渡 | 良好 | 11 keyframes + 75 transitions |
| inline styles | 合理 | 11 处（全部为动态值） |

---

## 2. 执行任务

### Task 1：旧式 token 迁移（92 处）

**策略**：将所有兼容别名引用替换为规范 token，然后移除兼容别名定义。

**迁移映射表**：

| 旧 token | 规范 token | 影响范围 |
|----------|-----------|---------|
| `--color-surface-hover` | `--color-interaction-hover-subtle-bg` | 44 处 / 33 文件 |
| `--color-foreground-primary` | `--color-foreground` | 11 处 / 19 文件 |
| `--color-status-success` | `--color-system-healthy` | 8 处 / 8 文件 |
| `--color-status-error` | `--color-system-down` | 5 处 / 8 文件 |
| `--color-status-warning` | `--color-risk-warning` | 3 处 / 8 文件 |
| `--color-surface-base` | `--color-surface-1` | 4 处 / 4 文件 |
| `--color-brand-accent` | `--color-accent` | 4 处 / 19 文件 |
| `--color-brand-primary` | `--color-brand-500` | 2 处 / 2 文件 |
| `--color-surface-elevated` | `--color-surface-2` | 2 处 / 2 文件 |
| `--color-border-default` | `--color-border` | 1 处 / 1 文件 |

**执行方式**：逐 token 全局替换（`replace_all`），每个替换后验证 `bun run check`。

**验证**：编写测试断言旧式 token 在组件代码中不再出现。

---

### Task 2：Typography 清理（~35 处）

**策略**：将任意像素值字号替换为 Tailwind 语义 utility 或 token 引用。

**迁移映射表**：

| 当前写法 | 替换为 | 处数 |
|---------|--------|------|
| `text-[10px]` | `text-xs`（= --text-xs = 10px） | ~28 |
| `text-[13px]` | `text-base`（= --text-base = 13px） | ~2 |
| `text-[24px]` | `text-3xl`（= --text-3xl = 24px） | ~2 |
| `text-[var(--text-xs)]` | `text-xs` | ~3 |
| `text-[var(--text-sm)]` | `text-sm` | ~2 |
| `text-[8px]` | 保留（低于 token 最小值，微标签专用） | ~1 |

**验证**：grep 确认 `text-[` 仅剩余合理例外。

---

### Task 3：Spacing token 收敛

**策略**：区分 density-响应式（必须迁移）和固定间距（可保留原始值）。

**迁移原则**：
- **页面级容器间距** → 必须使用 token：`p-[var(--density-panel-padding)]`、`gap-[var(--section-gap)]`、`gap-[var(--density-gutter)]`
- **组件内部微间距**（`px-1`、`py-0.5`、`gap-0.5`）→ 可保留原始 Tailwind
- **固定尺寸**（`h-8`、`w-56` 等）→ 可保留原始 Tailwind
- **Recharts fontSize** → 保留（第三方组件 API，非 CSS）

**关键文件**（page 级 spacing 偏差）：

| 文件 | 问题 |
|------|------|
| `a-shares-page.tsx` | `p-4` → `p-[var(--density-panel-padding)]` |
| `intelligence-page.tsx` | `gap-4` → `gap-[var(--density-gutter)]` |
| `regime-page.tsx` | `gap-4` → `gap-[var(--density-gutter)]` |

**验证**：页面级间距 token 覆盖率达到 100%。

---

### Task 4：Prototype 截图对比审查

**策略**：对 16 个 prototype-backed 页面进行视觉对比，确认关键视觉元素对齐。

**方法**：
1. 在浏览器中打开 prototype HTML 和 React 实现
2. 对比 spacing、color、typography、surface、border 等维度
3. 记录偏差并修复

**审查清单**（每个 prototype-backed 页面）：
- [ ] Surface 层级正确（app / panel / elevated / strip）
- [ ] Spacing 节奏与 prototype 一致
- [ ] Typography 字号/字重正确
- [ ] Border 样式（subtle/default/strong）正确
- [ ] Hover/交互状态正确
- [ ] 状态色（market/risk/system/signal）正确
- [ ] 动画效果存在且节奏正确

---

## 3. 完成标准

- [x] 旧式 token 引用数 = 0（兼容别名可保留但不再被引用）
- [x] `text-[Npx]` 仅剩合理例外（< 5 处）
- [x] 页面级 spacing 100% 使用 density 响应式 token
- [x] `bun run check` 通过
- [ ] **prototype-backed 页面通过视觉审查**（布局偏差 < 3%，像素匹配 > 95%）

> **⚠️ 关键发现（2026-04-10）**：Token 迁移已正确完成（55 文件、101 处替换），但视觉审查发现 React 实现与 prototype 存在结构性布局偏差。Home 页 main-primary 区域 React 553px vs prototype 270px（2x），Priority Queue 367px vs 120px（3x）。根因：`max-h-[66%]` 等布局策略是开发者猜测，无 prototype 依据。
>
> **下一步**：需要按 [visual-verification.md](../../.claude/rules/visual-verification.md) 规范，逐个 prototype-backed 页面度量 prototype 布局尺寸，然后修正 React 实现的布局策略。

---

## 4. 验证方法反思

### 为什么视觉验证失败

| 缺陷 | 描述 |
|------|------|
| Token 正确 ≠ 视觉正确 | 只检查 token 引用合规，不检查布局比例 |
| AI vision 泛化描述无效 | "深色金融仪表盘"适用任何同类 UI，无法区分差异 |
| 无 prototype 度量 | 开发时未从 prototype 提取实际尺寸作为依据 |
| `bun run check` 虚假安全 | 919/919 测试全绿，但 0 个视觉断言 |

### 已建立的新规范

- [visual-verification.md](../../.claude/rules/visual-verification.md) — 三层验证模型（L1 Token + L2 布局 + L3 像素）
- [workflow.md](../../.claude/rules/workflow.md) — 新增 prototype-backed 页面度量流程

---

## 4. 风险控制

| 风险 | 控制 |
|------|------|
| 全局替换引入 bug | 每个 token 替换后运行 `bun run check` |
| spacing 迁移破坏布局 | 先迁移页面级，再迁移组件级；逐步验证 |
| 视觉偏差大量发现 | Task 1-3 先消除系统性漂移，再做截图审查 |
