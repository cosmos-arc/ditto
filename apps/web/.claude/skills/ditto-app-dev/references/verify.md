# Phase 14: VERIFY — 三层验证 [sonnet]

> 自动化 L1/L2/L3，失败触发定向回退，不盲目重试。

**浏览器配置**：必须与 Phase 10 一致
```js
const browser = await chromium.launch({ channel: 'chromium' });
// 同一 viewport、同一 channel、同一渲染引擎
```

---

## Step 0: 0 容忍项预检

- 从 contract JSON 读取 `visualThresholds`：
  - `consoleErrors`、`pageErrors`、`missingSelectors`、`targetMismatch` 必须为 0
- 任何非 0 值 → STOP，报告具体违规项

## Step 0.5: 工程质量审计（使用 impeccable:audit）

在 L1/L2/L3 视觉验证之前，先运行 impeccable:audit 的 5 维诊断：

| 维度 | 检查内容 | 通过标准 |
|------|---------|---------|
| Accessibility | WCAG AA 对比度、aria-label、keyboard nav、focus management | 0 个 P0/P1 |
| Performance | 图片优化、CLS < 0.1、LCP < 2.5s、INP < 200ms | 0 个 P0 |
| Theming | Design token 使用合规、dark/light 一致性 | 0 个 P0 |
| Responsive | Container queries、touch targets ≥ 44x44px、无水平滚动 | 0 个 P0 |
| Anti-Patterns | AI slop 检测（通用卡片网格、无意义装饰、字体滥用） | 0 个 P0 |

- P0/P1 项必须修复后才能继续 L1/L2/L3
- P2/P3 项记录但不阻断

## Step 1: L1 Token 合规

```bash
bun run test --run src/features/shell/design-system-compliance.test.ts
```

- 通过标准：0 违规
- 失败处理：自动修复（替换硬编码值 → design token）→ 重新验证

## Step 2: L2 Layout 度量对比

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

## Step 3: L3 像素截图对比

- L2 验证通过后，使用 `visual-audit.mjs` 生成的截图（`docs/review/visual-audit/<page>/prototype.png` + `react.png`）
- 运行独立 L3 脚本：
  ```bash
  bun .claude/skills/ditto-app-dev/scripts/l3-pixel-diff.mjs \
    docs/review/visual-audit/<page>/prototype.png \
    docs/review/visual-audit/<page>/react.png \
    --threshold 0.2
  ```
- 脚本输出：
  - `diff.png`：红点 + 暗化背景的 diff 可视化
  - 垂直 band 分析：定位差异集中区域
  - 通过标准：`maxDiffPixelRatio < 0.02`（2%）
- 关键：`l3-pixel-diff.mjs` 使用 `pixelmatch` + `diffMask: true`，仅标记真实差异像素
- 失败处理：查看 `diff.png` → 分类根因（AA 伪影 / 布局偏差 / 内容差异 / 颜色偏差）

**L3 分数解读**：详见 [visual-verification.md 陷阱 10](../../../rules/visual-verification.md)

## Step 4: Gap 分析与分类

L2/L3 任一失败时，对每个差距项判断根因：

```
├── 实现偏差 → 标记修复方案 → 回退对应 Phase
├── 原型缺陷 → 记录 [proto-deviation] → 在实现层补偿
├── Token 缺失 → 补充 token → 回退 Phase 12
└── 架构问题 → 回退 Phase 11
```

## Step 5: 综合评分

```
Audit 通过(20%) + L1 通过(30%) + L2 通过(25%) + L3 通过(25%) = 实现对齐分
```
