# Phase 10: METRIC — 度量读取与提取 [sonnet]

> 优先从 contract JSON 读取已有 baseline，避免重复 Playwright 提取。

**输入**：`docs/contracts/pages/<page>.contract.json`

**前置检查**：

```
1. 检查 docs/contracts/pages/<page>.contract.json 是否存在？
   ├─ 否 → STOP，提示用户先运行 /ditto-page-contract --create <page>
   └─ 是 → 继续

2. 检查 metrics.baseline 是否非空？
   ├─ 非空 → 读取 baseline，输出度量摘要，跳到 Phase 11
   └─ 空 → 提示用户运行 /ditto-page-contract --refresh-metrics <page>
```

**回退流程**（baseline 为空时）：

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
