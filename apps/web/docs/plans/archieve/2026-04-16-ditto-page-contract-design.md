# ditto-page-contract 设计文档

> **版本**：v1.0
> **日期**：2026-04-16
> **状态**：Approved
> **上游**：ditto-product-arch (blueprint-approved) + ditto-design-cycle (prototype-approved)
> **下游**：ditto-app-dev (contract-ready → implemented)

---

## 1. 问题定义

当前管线存在三个核心断裂：

1. **page-contracts.ts 和 visual-audit.config.mjs 漂移** — 两份文件独立维护 21 条页面的 selector 映射，已出现 shell family 语义不一致（如 trading/signals 一边是 ops-console 另一边用 catalog targets）
2. **design-cycle 的 done 被误当成实现 ready** — prototype-approved 只意味着"原型视觉合格"，不代表"布局度量已提取、selector 已映射、阈值已定义"
3. **app-dev 每次从原型重新解释布局** — Phase 10 METRIC 和 Phase 14 VERIFY 各自猜测 prototype selector，导致不对版

**根本原因**：缺少一个机器可读、可失败、可被 app-dev 直接消费的合同层。

---

## 2. 定位与边界

### 2.1 职责

`/ditto-page-contract` 回答一个问题：**这个页面如果要落到 React，什么叫"对版"？**

它不做产品判断，不改 React，不做审美迭代。它像编译器一样无情：缺 selector、缺状态、prototype 404、metric 无法提取，就不能进入 contract-ready。

### 2.2 管线位置

```
ditto-product-arch → blueprint-approved
ditto-design-cycle → prototype-approved
ditto-page-contract → contract-ready       ← 新增
ditto-app-dev      → implemented / ship-ready
```

### 2.3 边界

| 它做 | 它不做 |
|------|--------|
| 从 blueprint/spec 提取页面级声明 | 修改 blueprint/spec |
| 用 Playwright 探测 prototype DOM | 修改 prototype HTML |
| 建立 selector 映射表 | 修改 React 组件 |
| 提取布局度量 baseline | 判断布局是否"好看" |
| 验证合同完整性 | 实现合同 |

---

## 3. Contract JSON Schema

### 3.1 设计原则

**精简合同 + 生成器模板**（业界标准：Chromatic/Storybook、Prisma、OpenAPI Generator）：

- JSON 只存页面级差异（route、slots、selectors、states、thresholds、metrics）
- 框架级共享知识（normalize CSS、shell family target 预设、viewport 默认值）在生成器模板层
- 生成器负责合并页面级差异 + 框架级预设 → 完整的 TS 和 mjs

### 3.2 Schema 定义

```jsonc
{
  // === 元信息 ===
  "id": "home",                           // 页面 ID，与 edition-manifest pages[].id 对应
  "version": 1,                           // 合同版本号，每次 --refresh-metrics 递增
  "status": "draft" | "contract-ready",   // 状态门禁
  "createdAt": "2026-04-16",
  "updatedAt": "2026-04-16",

  // === 页面身份 ===
  "route": "/",                           // 路由路径
  "pagePattern": "global-command-center", // 来自 spec §11
  "shellFamily": "command-center",        // 来自 spec §10
  "prototypeRef": "docs/designs/specs/prototypes/page-home.html",
  "blueprintRefs": ["02_core_page_blueprints.md#home-command-center"],

  // === 视口配置 ===
  "viewports": [
    { "width": 1536, "height": 900, "role": "primary" },
    { "width": 1366, "height": 768, "role": "compact" }
  ],

  // === Slot 映射（shell 级布局区域） ===
  "slots": [
    {
      "name": "pulse",                    // slot name，对应 SHELL_SLOT_MAP
      "required": true,                   // 必须存在
      "infoLevel": "l0",                  // 验证层级
      "prototypeSelector": ".shell-pulse",// prototype CSS selector
      "reactSelector": "[data-slot='pulse-strip']", // React data-slot
      "layoutStrategy": "content-driven", // 从度量推导，不是人工填写
      "threshold": {                      // L2 验证阈值
        "x": 4, "y": 4,
        "widthRatio": 0.03, "heightRatio": 0.05
      }
    }
  ],

  // === SubSlot 映射（页面级内容区块） ===
  "subSlots": [
    {
      "name": "decision-banner",
      "parentSlot": "main",               // 所属 shell slot
      "infoLevel": "l2",
      "prototypeSelector": ".decision-banner",
      "reactSelector": "[data-slot='decision-banner']",
      "threshold": { "widthRatio": 0.05, "heightRatio": 0.05 }
    }
  ],

  // === 状态矩阵 ===
  "states": {
    "universal": ["loading", "empty", "error", "stale"],
    "pageSpecific": ["no-alerts", "has-critical"]
  },

  // === 交互契约 ===
  "interactions": [
    {
      "id": "sidebar-collapse",
      "trigger": "sidebar-toggle",
      "affectedSlots": ["sidebar", "main"],
      "expectedBehavior": "sidebar width changes and main area expands"
    }
  ],

  // === 页面标志 ===
  "flags": {
    "hasStatusBar": false,
    "sidebarCollapsible": true
  },

  // === 度量基准线 ===
  "metrics": {
    "capturedAt": "2026-04-16",
    "viewport": "1536x900",
    "baseline": {
      "pulse": { "width": 1536, "height": 0, "strategy": "content-driven" },
      "main": { "width": 1200, "height": 0, "strategy": "content-driven" },
      "sidebar": { "width": 260, "height": 900, "strategy": "fixed-width" }
    }
  },

  // === 视觉阈值 ===
  "visualThresholds": {
    "consoleErrors": 0,
    "pageErrors": 0,
    "missingSelectors": 0,
    "targetMismatch": 0,
    "pixelDiffRatio": 0.02
  }
}
```

### 3.3 关键概念

| 概念 | 说明 |
|------|------|
| **slots** | Shell 级布局区域，来自 `SHELL_SLOT_MAP`（如 command-center 的 pulse/main/sidebar） |
| **subSlots** | 页面级内容区块，嵌套在 slot 内（如 main 下的 decision-banner、priority-queue） |
| **layoutStrategy** | 从 prototype 度量推导：`content-driven` / `fixed-width` / `flex` |
| **infoLevel** | 验证层级：l0（存在性）→ l1（token）→ l2（布局）→ l2.5（微观样式）→ l3（像素） |
| **threshold** | L2 验证的容差。shell slot 严（3%），content subSlot 宽（5-8%） |

---

## 4. 生成器架构

### 4.1 目录结构

```
scripts/contract-generator/
├── generate.mjs              # 入口：读取所有 JSON → 产出 TS + mjs
├── templates/
│   ├── shell-presets.ts      # Shell family 级别的 React target 预设
│   ├── normalize-css.ts      # PROTOTYPE_NORMALIZE_CSS 常量
│   └── threshold-policy.ts   # 根据 pagePattern/shellFamily 计算默认阈值
├── schema/
│   └── contract.schema.json  # JSON Schema 验证（ajv）
└── validators/
    └── contract-validator.mjs # 合同完整性验证逻辑
```

### 4.2 产出物

**`src/features/shell/page-contracts.generated.ts`**（类型安全，IDE 补全）：

```typescript
// AUTO-GENERATED — do not edit manually
// Run: bun run generate-contracts

export interface SlotContract { /* ... */ }
export interface PageContractData { /* ... */ }
export const PAGE_CONTRACTS: readonly PageContractData[] = [ /* ... */ ] as const;
```

**`scripts/visual-audit.config.generated.mjs`**（审计运行器消费）：

```javascript
// AUTO-GENERATED — do not edit manually
export const PROTOTYPE_NORMALIZE_CSS = `...`;
export const VISUAL_AUDIT_PAGES = [ /* ... */ ];
```

### 4.3 自动触发

```json
// package.json
{
  "scripts": {
    "generate-contracts": "bun scripts/contract-generator/generate.mjs",
    "predev": "bun run generate-contracts",
    "prebuild": "bun run generate-contracts"
  }
}
```

### 4.4 .gitignore

```
src/features/shell/page-contracts.generated.ts
scripts/visual-audit.config.generated.mjs
```

生成物不提交 git，每次 dev/build/check 自动重新生成。与 Prisma/tRPC 模式一致。

---

## 5. 命令设计

### 5.1 命令接口

```bash
/ditto-page-contract --create home              # 从蓝图+原型生成草稿合同
/ditto-page-contract --validate home            # 验证合同完整性（不改合同）
/ditto-page-contract --refresh-metrics home     # 重放 Playwright 度量
/ditto-page-contract --diff home                # 对比 blueprint/prototype/contract 漂移
/ditto-page-contract --audit --all              # 全部页面合同健康度报告
/ditto-page-contract --promote home             # 验证全绿 → status: contract-ready
```

### 5.2 --create 执行流程

```
Phase R: RESOLVE
├─ 读取 edition-manifest.json → 确认 page.status === "reviewed"
├─ 如果不是 → STOP
└─ 定位 blueprint section、prototype HTML、state spec

Phase B: BLUEPRINT EXTRACT
├─ 解析 blueprint 对应 section
├─ 提取：页面目标、主/辅工作面、核心区块列表
├─ 提取：Tab Content Sections
├─ 提取：Component × State Matrix → states
└─ 产出：模块清单 + 状态清单

Phase P: PROTOTYPE PROBE
├─ 启动 HTTP server（从 repo root）
├─ Playwright 打开 prototype HTML（channel: 'chromium'）
├─ 注入 PROTOTYPE_NORMALIZE_CSS
├─ 探测 #default-view 内 DOM 结构
└─ 产出：prototype DOM 树摘要

Phase S: SELECTOR MAP
├─ blueprint 模块 → prototype selector（DOM 匹配）
├─ blueprint 模块 → react selector（shell family 预设 merge）
├─ required slot 找不到 → WARNING
└─ 产出：slots[] + subSlots[]

Phase M: METRIC CAPTURE
├─ primary viewport → page.evaluate() → getBoundingClientRect + getComputedStyle
├─ 推导 layoutStrategy
├─ compact viewport → 重复
└─ 产出：metrics.baseline

Phase T: THRESHOLD POLICY
├─ shell slot → 严阈值（3%）
├─ content subSlot → 宽阈值（5-8%）
├─ consoleErrors/pageErrors/missingSelectors → 0 容忍
└─ 产出：visualThresholds + slot.threshold

Phase W: WRITE
├─ 组装 JSON → docs/contracts/pages/home.contract.json
├─ 生成报告 → docs/contracts/reports/home-contract-report.md
├─ 触发 generate-contracts
└─ status: "draft"
```

### 5.3 --validate 检查项

| # | 检查项 | 级别 |
|---|--------|------|
| 1 | JSON Schema 验证（ajv） | BLOCK |
| 2 | prototype 文件存在且非空 | BLOCK |
| 3 | blueprint section 可解析 | BLOCK |
| 4 | 每个 required slot 的 prototypeSelector 在 DOM 中存在 | BLOCK |
| 5 | 每个 required slot 的 reactSelector 格式合法 | BLOCK |
| 6 | metrics.baseline 不为空 | BLOCK |
| 7 | states.universal 包含 loading/empty/error/stale | BLOCK |
| 8 | visualThresholds 中 0 容忍项实际值为 0 | BLOCK |
| 9 | shellFamily 在枚举中 | BLOCK |
| 10 | pagePattern 在枚举中 | BLOCK |

### 5.4 --promote 条件

```
✓ --validate 全部通过
✓ edition-manifest 中页面 status === "reviewed"
✓ prototype HTML 无 console errors（Playwright page.on('console')）
✓ metrics.baseline 已捕获
→ status: "draft" → "contract-ready"
→ 重新触发 generate-contracts
```

---

## 6. 上下游衔接

### 6.1 对 ditto-product-arch 的影响

- 建议增加约束：blueprint 中每个核心区块必须有稳定 `moduleId`
- **不阻塞当前实施**，POC 阶段用手动映射

### 6.2 对 ditto-design-cycle 的影响

- 建议增加约束：prototype HTML 生成时写 `data-contract-slot` 稳定属性
- **不阻塞 POC**，home 的现有 selector 已足够验证链路

### 6.3 对 ditto-app-dev 的影响（正面）

| Phase | 当前 | 合同后 |
|-------|------|--------|
| 10 METRIC | 自己启动 Playwright 提取度量 | 读取 contract.metrics.baseline |
| 11 ARCHIT | 自己推断组件树 | 从 contract.slots/subSlots 推导 |
| 14 VERIFY | 从 visual-audit.config.mjs 读 selector | 从 contract 读 selector + threshold |
| 15 SHIP | 手动推进 manifest | 读取 contract.status |

### 6.4 现有文件处理

| 文件 | 处理方式 |
|------|---------|
| `src/features/shell/page-contracts.ts` | 重命名为 `.ts.bak`，实际消费 `.generated.ts` |
| `scripts/visual-audit.config.mjs` | 保留 `PROTOTYPE_NORMALIZE_CSS`（移到模板层），`VISUAL_AUDIT_PAGES` 由 `.generated.mjs` 替代 |
| `src/features/shell/page-contracts.test.ts` | 改为验证 `.generated.ts` 的结构完整性 |

---

## 7. POC 计划（仅 home）

### 7.1 目标

用 home 页面验证整条链路：`--create` → JSON → generate → `--validate` → `--promote` → app-dev 消费。

### 7.2 范围

1. 创建 `docs/contracts/pages/home.contract.json`
2. 实现 `scripts/contract-generator/generate.mjs`
3. 实现 `/ditto-page-contract --create home`
4. 验证产出物：
   - JSON 合同结构完整
   - `.generated.ts` 类型安全
   - `.generated.mjs` 与当前 `visual-audit.config.mjs` 的 home 部分对齐
5. 实现 `--validate home`
6. 实现 `--promote home`
7. 验证 `ditto-app-dev --implement home` 能消费新合同

### 7.3 不在 POC 范围内

- 其余 20 条页面的合同迁移
- prototype HTML 注入 `data-contract-slot`
- ditto-product-arch 的 moduleId 约束
- `--diff` 和 `--audit --all` 命令

---

## 8. 业界参考

| 实践 | 来源 | 对应设计决策 |
|------|------|-------------|
| Snapshot + threshold + baseline approval | [Chromatic/Storybook](https://www.chromatic.com/storybook) | metrics.baseline + visualThresholds |
| 消费者驱动合同验证 | [JSON Schema Contract Testing](https://json-schema.org/) | React（消费者）定义它需要的 selector/threshold |
| Spec 文件是唯一真源，代码自动生成 | [GitHub Spec-to-Code](https://hicronsoftware.com/blog/what-is-spec-to-code) | JSON → .generated.ts/.generated.mjs |
| 生成物不提交，构建时自动生成 | [Prisma](https://www.prisma.io/), [tRPC](https://trpc.io/) | predev/prebuild 自动触发 + .gitignore |
| 页面级配置 + 框架级预设分离 | [Storybook decorators](https://storybook.js.org/) | JSON 只存页面差异，shell 预设在生成器模板层 |
