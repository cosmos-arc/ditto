# Contract Create Phases — AI 执行详情

> `--create` 流程中由 AI 执行的 phases 具体操作步骤。

---

## Phase R: RESOLVE

1. 读取 `docs/designs/specs/.arch-manifest.json`（如不存在，检查 `docs/plans/` 下的 product-arch 产出物）
2. 定位 `edition-manifest.json` → 确认目标页面的 `status === "reviewed"` 或 `"done"`
3. 如果不是 → STOP，报告错误：`页面 "<page>" 状态为 "<status>"，需要先完成 design-cycle 审查`
4. 定位 blueprint section 文件（`02_core_page_blueprints.md`）
5. 定位 prototype HTML（`docs/designs/specs/prototypes/page-<page>.html`）
6. 定位 state spec（`04_interaction_state_spec.md`）
7. 读取 `DESIGN.md` 的 Components 章节作为 token 映射参考

---

## Phase B: BLUEPRINT EXTRACT

从 `02_core_page_blueprints.md` 的对应页面 section 中提取：

1. **页面目标**：一句话描述页面核心目的
2. **主/辅工作面**：哪些区域是主要工作区、哪些是辅助
3. **核心区块列表**：按蓝图优先级排序的模块名
4. **Tab Content Sections**：蓝图定义的 tab 面板及其内容
5. **Component × State Matrix** → 提取 `states.pageSpecific`
6. **Overlay 注册表** → 提取 `interactions`（如果有 overlay trigger）

**产出**：模块清单 + 状态清单 + 交互清单。

---

## Phase P+S+M: PROBE + SELECTOR MAP + METRIC CAPTURE（自动化）

运行 `create.mjs`（详见 contract-cli.md），产出：
- `sections[]` — DOM 探测结果（data-contract-slot 匹配 + fallback class 匹配）
- `metrics.baseline` — 各区域的 width/height/strategy

---

## Phase S: SELECTOR MAP（AI 辅助）

1. 将 Phase B 的模块清单与 Phase P 的 `sections[]` 做匹配
2. 每个 blueprint 模块 → `prototypeSelector`（从 sections 中找对应 DOM 选择器）
3. 每个 blueprint 模块 → `reactSelector`（从 shell family 预设 merge，格式 `[data-slot='xxx']`）
4. Shell 级 required slot 找不到 → **WARNING**，记录原因
5. 页面级 subSlot 找不到 → 允许，标记为 optional

**Selector 格式规则**：
- Prototype: CSS 选择器（`.shell-pulse`, `.decision-banner`）
- React: `[data-slot='xxx']` 或 `[data-testid='xxx']`

**a11y 推断**（V2 新增）：
- Shell 级 slot → 推断 `a11yRole`（rail → `"navigation"`, main → `"main"`, sidebar → `"complementary"`）
- 有明确语义的 subSlot → 推断 `a11yLabel`

**responsive 推断**（V2 新增）：
- 如果 viewports 包含 compact role → 检查哪些 slot 在 compact 下有行为变化
- 有变化 → 添加 `responsiveBehavior: { compact: "hidden" | "collapsed" | "overlay" | "reflow" }`

**产出**：`slots[]` + `subSlots[]`（含 a11y + responsive 字段）。

---

## Phase T: THRESHOLD POLICY

使用模板默认值（`threshold-policy.ts.mjs`）：

| 类型 | 默认阈值 |
|------|---------|
| Shell slot | `{x:4, y:4, widthRatio:0.03, heightRatio:0.05}` |
| Content subSlot | `{widthRatio:0.05, heightRatio:0.05}` |
| L0/L1 infoLevel | `null`（仅存在性/token 检查） |
| L3 infoLevel | 上述 + `pixelDiffRatio: 0.02` |

零容忍项：`consoleErrors: 0, pageErrors: 0, missingSelectors: 0, targetMismatch: 0`

**产出**：`visualThresholds` + 每个 slot/subSlot 的 `threshold`。

---

## Phase W: WRITE

1. 组装完整 JSON 对象（所有字段见 schema）
2. 确认 `status: "draft"`
3. 写入 `docs/contracts/pages/<page>.contract.json`
4. 运行 `bun run generate-contracts` → 更新 `.generated.ts` + `.generated.mjs`
5. 生成创建报告到 `docs/contracts/reports/<page>-contract-report.md`

**注意**：如果合同文件已存在，提示用户确认覆盖。
