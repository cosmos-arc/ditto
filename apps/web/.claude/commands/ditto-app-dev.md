---
name: ditto-app-dev
description: >
  原型落地 + 交互打磨 + 三层验证。支持 --implement（单页面）、
  --implement-batch（批量）、--iterate（自主迭代循环）、--polish-only（纯打磨）、
  --verify-only（纯验证）。从 design-cycle 的 done 状态接手，到 Ship 完成。
disable-model-invocation: true
---

# /ditto-app-dev 命令

从 Prototype 到 Production 的完整实现管线。
与 ditto-design-cycle 通过 page contract + edition manifest 衔接。

## 规范参考

- **流程规范**: [workflow.md](../rules/workflow.md)
- **架构规范**: [architecture.md](../rules/architecture.md)
- **视觉验证**: [visual-verification.md](../rules/visual-verification.md)
- **页面合同**: [page-contracts.generated.ts](../../src/features/shell/page-contracts.generated.ts)（自动生成，源文件在 `docs/contracts/pages/`）
- **合同管理**: `/ditto-page-contract` — 创建/验证/提升页面合同

---

## 输入参数

`$ARGUMENTS` — 计划文件路径或页面名（可选）

```bash
# === 实现模式（单页面）===
/ditto-app-dev --implement home                  # 实现单个页面（度量→架构→TDD→打磨→验证→完成）
/ditto-app-dev --implement trading --from-prototype page-trading-overview.html

# === 批量实现 ===
/ditto-app-dev --implement-batch home,markets,ai  # 批量实现，按 shell family 并行

# === 自主迭代 ===
/ditto-app-dev --implement trading --iterate                # 迭代直到达标（默认 8.5）
/ditto-app-dev --implement trading --iterate --iterate-goal 9.0 --iterate-max 5

# === 特殊模式 ===
/ditto-app-dev --polish-only trading          # 跳过实现，直接交互打磨
/ditto-app-dev --verify-only trading          # 跳过实现和打磨，仅三层验证
/ditto-app-dev --implement home --phase 14    # 跳转到指定 Phase

# === 兼容旧模式（无参数）===
/ditto-app-dev                                # 最新计划（退化为简化 TDD 流程）
/ditto-app-dev docs/plans/2026-01-19-xxx.md   # 指定计划
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--implement <page>` | 实现单个页面（度量→TDD→打磨→验证→完成） |
| `--implement-batch <pages>` | 批量实现，逗号分隔，可按 shell family 并行 |
| `--iterate` | 自主迭代模式（实现→验证→分析差距→优化，直到达标或 max-rounds） |
| `--iterate-goal <score>` | 迭代目标分数，默认 8.5 |
| `--iterate-max <N>` | 最大迭代轮数，默认 3 |
| `--polish-only` | 跳过实现，直接进入交互打磨（Phase 13） |
| `--verify-only` | 跳过实现和打磨，仅运行三层验证（Phase 14） |
| `--phase <10\|11\|12\|13\|14\|15>` | 跳转到指定 Phase 执行 |
| `--from-prototype <path>` | 指定 prototype HTML 路径（覆盖 page contract 默认值） |
| `--viewport <WxH>` | 验证视口，默认 1536x900 |
| `--max-diff-pixel-ratio <0-1>` | L3 像素阈值，默认 0.02（2%） |
| `--force-metric` | 强制启动 Playwright 重放度量提取，忽略已有 contract baseline |

---

## Agent 分工与 Model Routing

### 五 Agent 体系

| Phase | Agent | Model | 职责 | 可用 Skills |
|-------|-------|-------|------|------------|
| 10 METRIC | Metric Reader | sonnet | 读取 contract.metrics.baseline（已有则跳过提取，--force-metric 强制重放） | 无 |
| 11 ARCHITECT | Component Architect | opus | 设计组件树、状态管理、shadcn 映射、复用策略 | brainstorming |
| 12 IMPLEMENT | TDD Developer | sonnet × N | 红→绿→重构，按组件可并行拆分子 agent | test-driven-development, subagent-driven-development |
| 13 POLISH | Interaction Polisher | opus | CSS transitions 基线 + Motion 按需 + hover/focus/active 状态审计 | impeccable:animate, impeccable:polish, impeccable:colorize |
| 14 VERIFY | Visual QA | sonnet | L1 Token → L2 Layout → L3 Pixel，失败触发回退 | verification-before-completion, systematic-debugging |
| 15 SHIP | Final Review | sonnet | 代码简化、文档更新、manifest 状态推进 | code-simplifier:code-simplifier |

### Model Routing 策略

| 场景 | Model | 理由 |
|------|-------|------|
| 组件架构决策、交互打磨审美判断 | opus | 需要创意/审美/深度推理 |
| TDD 编码、度量提取、验证对比、文档 | sonnet | 结构化操作，效率优先 |
| 迭代循环中的突破判断（连续 2 轮无进展） | opus | 需要跳出局部最优 |

**实现方式**：Agent 工具调用时传入 `model` 参数，如 `Agent(prompt="...", model="opus")`。

---

## 执行流程

### 完整执行流

```
/ditto-app-dev --implement <page>
│
▼
Phase 10: METRIC [sonnet]
│  读取 contract.metrics.baseline（已有则跳过提取）→ 推导布局策略
│
▼
Phase 11: ARCHITECT [opus]
│  组件树 + 状态管理 + shadcn 映射 → 用户确认架构方案
│
▼
Phase 12: IMPLEMENT [sonnet × N]
│  RED → GREEN → CHECK(度量) → SIMPLIFY → REFACTOR
│  └─ 按组件并行（subagent-driven-development）
│
▼
Phase 13: POLISH [opus]
│  交互状态审计 → CSS transitions 基线 → Motion 按需 → 状态矩阵报告
│
▼
Phase 14: VERIFY [sonnet]
│  L1 Token → L2 Layout → L3 Pixel → Gap 分析 + 评分
│  └─ 失败 → 定向回退对应 Phase
│
▼
Phase 15: SHIP [sonnet]
│  代码简化 → bun run check → 文档更新 → manifest 推进 → 实现报告
│
▼
完成（--iterate 未指定）
│
└─ 或进入迭代循环（--iterate）→ Phase 12/13/14 循环直到达标
```

### Phase 依赖关系

```
Phase 10 ← Phase 14（同一 Playwright 配置，同一度量基准）
Phase 11 ← Phase 12（架构文档是实现的输入）
Phase 12 ← Phase 13（实现的组件是打磨的输入）
Phase 12 ← Phase 14（实现的组件是验证的输入）
Phase 10 ← Phase 11（度量数据是架构设计的输入）

可并行的 Phase：
- Phase 10（度量提取）与 Phase 11 的「步骤 5 复用策略」可并行
- Phase 12 中独立组件的 TDD 循环可并行
- Phase 14 L1 与 L2 可并行（L3 依赖 L2 截图）
- Phase 15 的「代码简化」与「文档更新」可并行
```

---

### Phase 10: METRIC — 度量读取与提取 [sonnet]

> 优先从 contract JSON 读取已有 baseline，避免重复 Playwright 提取。

**输入**：`docs/contracts/pages/<page>.contract.json` + `--viewport` 参数

**前置检查**：

```
1. 检查 docs/contracts/pages/<page>.contract.json 是否存在？
   ├─ 否 → STOP，提示用户先运行 /ditto-page-contract --create <page>
   │        或使用 --force-metric 强制执行度量提取
   └─ 是 → 继续

2. 检查 metrics.baseline 是否非空？
   ├─ 非空 → 读取 baseline，输出度量摘要，跳到 Phase 11
   └─ 空 或 --force-metric → 启动 Playwright 提取（回退流程）
```

**回退流程**（baseline 为空或 `--force-metric`）：

1. **启动 Playwright**
   ```js
   const browser = await chromium.launch({ channel: 'chromium' });
   const page = await browser.newPage({ viewport: { width: 1536, height: 900 } });
   ```
   - 必须使用 `channel: 'chromium'`（新 headless = 真实 Chrome 渲染引擎）
   - 与 Phase 14 VERIFY 使用完全相同的浏览器配置

2. **加载 prototype + 注入标准化 CSS**
   - 启动 prototype HTTP 服务（复用 `visual-audit.config.generated.mjs` 中的 `PROTOTYPE_NORMALIZE_CSS`）
   - 隐藏 `.proto-nav`，强制 `#default-view` 100vh
   - 等待 `networkidle` + 字体加载完成（`document.fonts.ready`）

3. **提取布局度量**（`page.evaluate()`）
   ```
   对每个 prototype section 执行：
   - getBoundingClientRect() → x, y, width, height
   - getComputedStyle() → display, position, gridTemplateColumns,
     gridTemplateRows, flex, padding, gap, fontSize, lineHeight
   - 父级容器的 grid/flex 分配策略
   ```

4. **推导布局策略**
   ```
   原型 1fr / auto  → React flex-1（内容驱动，不设高度约束）
   原型固定 px      → React 对应 token 或固定值
   原型无百分比      → React 禁止引入百分比
   ```

5. **更新 contract JSON 度量字段**
   - 将提取的度量写入 `docs/contracts/pages/<page>.contract.json` 的 `metrics.baseline`
   - `version` 递增，`updatedAt` 设为今天
   - 运行 `bun run generate-contracts` 重新生成 `.generated.ts` + `.generated.mjs`

6. **关闭 browser，输出度量摘要**

**禁止**：
- ❌ 使用 Chrome DevTools 手动提取度量（已废弃，统一到 Playwright）
- ❌ 使用无 prototype 依据的百分比高度/宽度
- ❌ 猜测布局策略（必须从度量数据推导）

---

### Phase 11: ARCHITECT — 组件架构设计 [opus]

> 将度量数据转化为组件实现方案。这是最关键的决策环节。

**输入**：contract JSON（slots/subSlots/states/metrics.baseline/interactions/thresholds）+ 现有组件库

**执行步骤**：

1. **分析原型结构**
   - 将 prototype 的 DOM 结构映射到 React 组件树
   - 每个 prototype section → 一个 React 组件/子组件
   - 使用 contract 的 `subSlots[]` 识别页面级内容区块（如 main 下的 decision-banner、priority-queue）
   - 标记哪些 section 共享状态（如 Tab 切换、联动筛选）

2. **设计组件树**
   ```
   输出格式（示例 — analytical layout）：
   <AnalyticalLayout>
     <Strip />           ← 映射 [data-slot='strip']
     <Banner />          ← 映射 [data-slot='banner']
     <Main>
       <SectionA />      ← 映射 prototype .panel-xxx
       <SectionB />
       <SectionC />
     </Main>
     <Analysis />        ← 映射 [data-slot='analysis']
   </AnalyticalLayout>
   ```

3. **shadcn 组件映射**
   - 扫描组件需求 → 匹配 shadcn/ui 组件清单
   - 标记需要自定义的组件（prototype 中无直接对应）
   - 标记需要扩展的组件（在 shadcn 基础上添加功能）

4. **状态管理策略**
   - 服务端状态 → TanStack Query
   - 客户端 UI 状态 → 组件内 useState / Zustand（仅跨组件共享时）
   - 列出每个组件的输入 props 和状态

5. **复用策略**
   - Grep 现有 features/ 目录，识别可复用的组件/hooks
   - 标记需要新建 vs 复用 vs 扩展

6. **输出架构文档**
   - 组件树、状态管理方案、shadcn 映射、复用清单
   - 交给 Phase 12 的 TDD Developer 作为实现蓝图

**交互式确认**：Phase 11 完成后必须向用户展示架构方案并获取确认，再进入 Phase 12。

---

### Phase 12: IMPLEMENT — TDD 实现 [sonnet × N]

> 严格 RED → GREEN → REFACTOR，可按组件并行拆分。

**输入**：Phase 11 架构文档 + Phase 10 度量数据 + contract JSON states 列表

**执行策略**：

1. **组件粒度拆分**
   - 根据架构文档的组件树，将独立组件拆分为并行子任务
   - 使用 `subagent-driven-development` skill 管理并行
   - 共享组件（如 Layout、shell）由单个 agent 负责，不并行

2. **TDD 循环（每个组件）**
   ```
   RED    → 写失败测试（渲染结构 + slots + 关键 props）
   GREEN  → 最少代码让测试通过
   CHECK  → 度量对齐（对比 Phase 10 数据，偏差 < 3%）
   SIMPLIFY → code-simplifier 简化代码
   REFACTOR → 消除重复，提取复用
   ```

3. **布局实现铁律**
   - 每个 `[data-slot]` 区域的尺寸必须与 Phase 10 度量一致
   - grid-template / flex 分配值从度量数据精确复制
   - 禁止猜测：无法从度量推导的值 → 回退 Phase 11 询问
   - content-driven 区域不设高度约束

4. **状态覆盖实现**
   - 按 contract JSON 的 `states.universal` + `states.pageSpecific` 逐个实现：
     - `loading` — skeleton / spinner
     - `empty` — 空状态 UI
     - `error` — 错误边界 + fallback
     - `stale` — 数据过期指示
     - + domain-specific states（来自 `states.pageSpecific`）
   - 实现 contract 中定义的 `interactions[]`（如 sidebar-toggle 交互）
   - 每个状态至少一个测试用例

5. **Slot 一致性验证**
   - 每个组件渲染的 `data-slot` 属性必须与 contract 的 `slots[]`（required=true）完全匹配
   - 同时验证 `subSlots[].reactSelector` 在 React 中存在对应组件
   - 多余或缺失的 slot 视为 P0 阻断项

**并行规则**：
- 独立组件（无共享状态的 leaf 组件）→ 并行
- 共享 Layout / 父组件 → 串行优先
- 依赖组件（需要另一个组件的 props 类型）→ 按拓扑排序

---

### Phase 13: POLISH — 交互打磨 [opus]

> CSS transitions 基线 + Motion 按需 + 交互状态全覆盖审计。

**输入**：Phase 12 实现的组件 + 原型中的交互暗示（hover 区域、按钮、可点击元素）

**执行步骤**：

1. **交互状态审计（Interaction Audit）**
   - 扫描页面所有可交互元素：Button、Link、Input、Tab、Card、可点击行
   - 对每个元素建立状态清单：

   | 元素类型 | 必需状态 | 默认行为 |
   |---------|---------|---------|
   | Button | default, hover, focus-visible, active, disabled | CSS transition |
   | Card (可点击) | default, hover, focus-visible | 背景色 + 阴影过渡 |
   | Tab | default, hover, active (selected) | 下划线/背景滑动 |
   | Input | default, focus, error, disabled | focus ring 过渡 |
   | 数据行 (可点击) | default, hover, selected | 行背景过渡 |
   | 面板 (可展开) | collapsed, expanded, transitioning | Motion AnimatePresence |
   | Modal/Drawer | hidden, entering, visible, exiting | Motion AnimatePresence |
   | Tooltip | hidden, visible | CSS opacity + transform |

2. **CSS Transitions 基线（零成本覆盖 ~80% 场景）**
   - 所有可交互元素必须添加 `transition-colors` 或 `transition-all`
   - 时长使用 Tailwind token：`duration-150`（快速）、`duration-200`（标准）、`duration-300`（慢速）
   - focus-visible ring 使用 `ring-offset` + `ring-2` + design token 颜色
   - 禁止 `transition-all` 的无限滥用（仅在有多个属性需要过渡时使用）

3. **Motion 按需引入（仅以下场景）**
   ```
   引入 Motion 的判断标准（满足任一即引入）：
   ├── 元素需要退出动画（CSS 无法做到 DOM 卸载动画）
   ├── 布局位移需要补间（面板 resize、列表排序）
   ├── 需要 stagger 编排（列表项依次进入）
   └── 需要手势响应（drag, pinch）
   ```
   - 使用 `impeccable:animate` skill 生成动画代码
   - 动画参数使用项目 token（--duration-fast/normal/slow, --ease-default/spring）
   - 每个动画组件必须 `export` 动画 variant 常量，禁止 inline magic numbers

4. **Micro-interactions（使用 impeccable:polish）**
   - 按钮 hover 微位移（translate-y -0.5px）
   - 选中态的视觉权重变化
   - 数据加载时的 skeleton shimmer
   - 状态切换的即时反馈（颜色闪变、图标旋转）

5. **交互状态测试**
   - 每个交互状态至少一个测试：`fireEvent.hover()`, `fireEvent.focus()`
   - `:focus-visible` 键盘导航测试
   - Motion 动画的 `act()` 包裹测试

**输出**：交互状态覆盖报告（元素类型 × 状态矩阵，标注已实现/已跳过及原因）

---

### Phase 14: VERIFY — 三层验证 [sonnet]

> 自动化 L1/L2/L3，失败触发定向回退，不盲目重试。

**浏览器配置**：必须与 Phase 10 一致
```js
const browser = await chromium.launch({ channel: 'chromium' });
// 同一 viewport、同一 channel、同一渲染引擎
```

**执行步骤**：

0. **0 容忍项预检**
   - 从 contract JSON 读取 `visualThresholds`：
     - `consoleErrors`、`pageErrors`、`missingSelectors`、`targetMismatch` 必须为 0
   - 任何非 0 值 → STOP，报告具体违规项

1. **L1 Token 合规**
   ```bash
   bun run test --run src/features/shell/design-system-compliance.test.ts
   ```
   - 通过标准：0 违规
   - 失败处理：自动修复（替换硬编码值 → design token）→ 重新验证

2. **L2 Layout 度量对比**
   - 启动 prototype HTTP 服务 + React dev server
   - 用 Playwright 对两侧执行 `page.evaluate()` 提取 `getBoundingClientRect()`
   - **selector 来源**：从 contract JSON 的 `slots[].prototypeSelector/reactSelector` + `subSlots[]` 读取配对
   - **验证阈值**：从 contract JSON 的 `slots[].threshold` 和 `subSlots[].threshold` 读取
   - `PROTOTYPE_NORMALIZE_CSS` 来源：`visual-audit.config.generated.mjs`
   ```
   通过标准（默认值，contract 可覆盖）：
   - shell slot：宽度偏差 < 3%，高度偏差 < 5%，x/y 偏移 < 4px
   - content subSlot：宽度偏差 < 5%，高度偏差 < 5%
   ```
   - 输出逐区域偏差报告表格
   - 失败处理：
     - 偏差 < 10% → 调整 CSS → 重验（最多 2 次）
     - 偏差 10-30% → 回退 Phase 12 修复
     - 偏差 > 30% → 回退 Phase 11 重新评估布局策略

3. **L3 像素截图对比**
   - L2 验证通过后，使用 `visual-audit.mjs` 生成的截图（`docs/review/visual-audit/<page>/prototype.png` + `react.png`）
   - 运行独立 L3 脚本：
     ```bash
     bun scripts/l3-pixel-diff.mjs \
       docs/review/visual-audit/<page>/prototype.png \
       docs/review/visual-audit/<page>/react.png \
       --threshold 0.2
     ```
   - 脚本输出：
     - `diff.png`：红点 + 暗化背景的 diff 可视化
     - 垂直 band 分析：定位差异集中区域
     - 通过标准：`maxDiffPixelRatio < 0.02`（2%）
   - **分数解读**（详见 visual-verification.md 陷阱 10）：
     - < 2% @ threshold 0.2：优秀
     - 2-4% @ threshold 0.2，< 2% @ threshold 0.3：良好（差异为文字 AA 伪影）
     - > 6% @ threshold 0.3：需排查实现问题
   - 关键：`l3-pixel-diff.mjs` 使用 `pixelmatch` + `diffMask: true`，仅标记真实差异像素
   - 失败处理：查看 `diff.png` → 分类根因（AA 伪影 / 布局偏差 / 内容差异 / 颜色偏差）

4. **Gap 分析与分类**（L2/L3 任一失败时）
   ```
   对每个差距项判断根因：
   ├── 实现偏差 → 标记修复方案 → 回退对应 Phase
   ├── 原型缺陷 → 记录 [proto-deviation] → 在实现层补偿
   ├── Token 缺失 → 补充 token → 回退 Phase 12
   └── 架构问题 → 回退 Phase 11
   ```

5. **综合评分**
   ```
   L1 通过(40%) + L2 通过(30%) + L3 通过(30%) = 实现对齐分
   ```

---

### Phase 15: SHIP — 收尾 [sonnet]

> 代码简化 + 文档同步 + 状态推进。

**前置条件**：`docs/contracts/pages/<page>.contract.json` 的 `status === "contract-ready"`

```
检查 contract.status：
├─ "contract-ready" → 继续执行
└─ "draft" → STOP，提示用户先运行 /ditto-page-contract --promote <page>
```

**执行步骤**：

1. **代码简化** — 调用 `code-simplifier:code-simplifier`
2. **全量验证** — `bun run check`（lint + type + test）
3. **文档更新**
   - 更新实现计划文档，标记任务完成状态
   - 如有 `[proto-deviation]` 记录，同步到原型反馈清单
4. **Edition manifest 推进**
   - 更新 `.edition-manifest.json` 中对应页面的实现状态
   - `done`（原型审查通过）→ `implemented`（实现完成）
5. **输出实现报告**
   ```
   实现报告（per page）：
   ├── L1/L2/L3 验证结果
   ├── 交互状态覆盖矩阵
   ├── [proto-deviation] 列表（如有）
   ├── 新增/复用/扩展的组件清单
   └── 测试覆盖率
   ```

---

## 迭代协议（--iterate 模式）

### 触发条件

```
用户指定 --iterate
或 Phase 14 综合评分 < --iterate-goal（默认 8.5）
```

### 迭代循环体

```
Round N:
  1. 分析上一轮 Gap 报告，按影响排序
  2. 判断最大 Gap 类型：
     ├── 布局偏差 → Phase 12 修复
     ├── 交互缺失 → Phase 13 补充
     ├── 原型缺陷 → 实现层补偿（不计入迭代轮次）
     └── 架构问题 → Phase 11 重新设计
  3. 执行修复
  4. 重新运行 Phase 14 验证
  5. 计算新的综合评分
```

### 终止条件

| 条件 | 行为 |
|------|------|
| 综合评分 ≥ goal | 进入 Phase 15 SHIP |
| 连续 2 轮评分无提升（浮动 < 0.3） | 升级到 opus 做突破判断 |
| 达到 max-rounds | 输出当前状态报告 + 未解决项建议 |

### 突破协议（连续停滞时）

升级到 opus agent 执行：
1. 审视全部 Gap 报告，寻找系统性根因
2. 判断是否需要：架构重构 / 原型修正 / 工具链调整
3. 如需原型修正 → 提出具体修改建议供用户决策（不自动修改原型）
4. 输出突破方案 + 预期提升幅度

---

## 原型缺陷处理协议

在 Phase 14 VERIFY 中发现差距时，必须先判断根因：

| 根因类型 | 判断方式 | 处理 |
|---------|---------|------|
| **实现问题** | prototype 度量正确，React 偏差 | 回退 Phase 12/13 修复 |
| **原型缺陷** | prototype 自身布局/间距/层级不合理 | 在实现层优化（需记录 rationale），不回退修改原型 |
| **架构问题** | 组件拆分/状态管理导致布局偏差 | 回退 Phase 11 重新设计 |
| **Token 缺失** | design tokens 无法覆盖某个视觉需求 | 先补充 token 到 token 层，再修复实现 |

**原型缺陷记录格式**（写入实现页面的 doc comment）：
```
/* [proto-deviation] 原型使用固定高度 200px，但内容驱动更合理。
   原因：原型未考虑动态数据长度。
   决策：使用 min-h + content-driven，记录人：AI, 日期：2026-04-12 */
```

---

## 特殊模式

### --polish-only
跳过 Phase 10-12，直接进入 Phase 13 交互打磨。
适用：已实现但未打磨的页面。

### --verify-only
跳过 Phase 10-13，直接进入 Phase 14 三层验证。
适用：快速检查已有实现的对齐度。

### --phase <N>
跳转到指定 Phase 执行（需该 Phase 的前置数据已存在）。
适用：修复验证失败后的定向重跑。

### --implement-batch <pages>
批量实现多个页面，按 shell family 分组并行。
- 同一 shell family 的页面共享 Phase 11 架构方案
- Phase 12 按页面并行，Phase 14 按页面并行验证
- 每个页面独立评分，全部通过后统一 SHIP

### 旧模式（无 --implement 参数）
当 `$ARGUMENTS` 是计划文件路径或无参数时，退化为简化 TDD 流程：
```
读取计划 → 确认任务 → RED → GREEN → SIMPLIFIER → REFACTOR → 验证完成 → 文档更新
```
调用 skills：brainstorming → test-driven-development → subagent-driven-development → code-simplifier:code-simplifier → verification-before-completion

---

## 与 ditto-design-cycle 的衔接

```
ditto-design-cycle Phase 8 FINAL（标记 done）
    │
    │  edition manifest: page.state = "done"
    │  git tag: review/<task>/done
    │
    ▼
ditto-page-contract --create <page>       ← 新增
    │  产出: docs/contracts/pages/<page>.contract.json (status: draft)
    │  自动生成: .generated.ts + .generated.mjs
    │
    ▼
ditto-page-contract --validate <page>     ← 新增
    │  10 项 BLOCK 检查
    │
    ▼
ditto-page-contract --promote <page>      ← 新增
    │  status: draft → contract-ready
    │  重新生成 .generated.ts + .generated.mjs
    │
    ▼
ditto-app-dev --implement <page>
    │
    │  Phase 10: 读取 contract.metrics.baseline（已有则跳过提取）
    │  Phase 11: 读取 contract slots/subSlots/states/metrics/interactions
    │  Phase 12: 从 contract 读取 states + 验证 subSlots
    │  Phase 14: 从 contract 读取 selector + threshold → 精确验证
    │  Phase 15: 检查 contract.status === "contract-ready"
    │
    ▼
Phase 15 SHIP
    │
    │  edition manifest: page.state = "implemented"
    │  如有 [proto-deviation] → 写入原型反馈清单
    │
    ▼
ditto-design-cycle --edition-review（可选，跨页审计时参考）
```

---

## 禁止事项

| ❌ 禁止 | 原因 |
|---------|------|
| 跳过 Phase 10 直接实现 | 无度量数据 = 猜测布局，偏差必然 > 20% |
| 跳过 Phase 11 直接写代码 | 无架构方案 = 组件混乱，返工成本 3-5x |
| Phase 12 跳过 RED 直接 GREEN | 违反 TDD 铁律，CLAUDE.md 强制要求 |
| 使用 Chrome DevTools 提取度量 | 已统一到 Playwright，混合环境产生虚假偏差 |
| 无 prototype 依据的百分比高度 | 必须从度量数据推导布局策略 |
| 原型缺陷时不记录直接修改实现 | 所有 proto-deviation 必须有 rationale 记录 |
| L3 截图使用默认 old headless | 必须使用 `channel: 'chromium'` 确保像素准确 |
| Phase 13 盲目引入 Motion | 必须满足判断标准（退出动画/布局补间/stagger/手势） |
| `transition-all` 滥用 | 仅在多属性过渡时使用，默认 `transition-colors` |
| 迭代循环中跳过 Gap 分析直接重试 | 每次失败必须分类根因，定向修复 |
| 连续 Edit（Read/Edit 比 < 2.0） | CLAUDE.md 强制要求 |
| 不调用 systematic-debugging 就重试 | CLAUDE.md 强制要求 |
| 跳过 verification-before-completion | CLAUDE.md 强制要求 |
