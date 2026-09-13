# Prototype Alignment Design Cycle

> 日期: 2026-04-12
> 分支: feat/prototype-three-zone-architecture
> 目标: 所有 16 个原型页面 React 实现与 HTML 原型视觉对齐（偏差 < 3%，像素匹配 > 95%）

---

## 当前状态

| 匹配度 | 页面 | 路由 |
|--------|------|------|
| ~98-99% | home, platform | `/`, `/platform` |
| ~85-90% | ai, trading-signals, trading-orders | `/ai`, `/trading/signals`, `/trading/orders` |
| ~50-75% | trading-risk, strategy-studio, trading, ai-copilot, instrument-hub | 5 页 |
| ~20-40% | markets, markets-screener, markets-intelligence, research-regime, ai-agents, research | 6 页 |

## 系统性障碍诊断

### 障碍 1: StatusBar 架构不统一
- 原型: `position: fixed; bottom: 0; left: var(--shell-rail-width); right: 0; height: 24px`
- 原型中 status bar 从不是 grid 的一部分，始终悬浮在 grid 外
- React: 无统一处理方式，某些布局有 slot 某些没有
- 影响: 14/16 页面

### 障碍 2: StudioLayout 缺 modes 行
- 原型 (copilot/agents): `grid-rows-[68px auto 1fr]`（header + modes + content）
- React StudioLayout: `grid-rows-[1fr auto]`（content + logs，无 modes 行）
- 影响: strategy-studio, ai-copilot, ai-agents

### 障碍 3: cross-market 用错布局
- 原型: `.shell-radar`（flex + sticky，页面可滚动）
- React: 使用 AnalyticalLayout（固定 grid）
- 影响: /markets/

---

## 执行计划

### Phase 1: 系统性基础设施修复（3 个 fix）

#### Fix 1: StatusBar → Fixed Floating

**决策**: StatusBar 改为 `position: fixed` 悬浮在 AppShell grid 外，每个页面自己决定是否渲染。

**实施步骤**:
1. 修改 `StatusBar` 组件：添加 `position: fixed; bottom: 0; left: var(--width-rail); right: 0; height: 24px; z-index: 50`
2. 更新 `PAGE_CONTRACTS`：为每个页面标记 `hasStatusBar: boolean`
3. 在 AppShell 或各页面中条件渲染 StatusBar
4. 需要 status bar 的页面添加 `padding-bottom: 24px` 补偿

#### Fix 2: StudioLayout → 添加 modes 行

**实施步骤**:
1. 添加可选 `modes` slot 到 StudioLayoutProps
2. 更新 grid rows: `grid-rows-[auto_1fr_auto]`
3. 更新 grid areas: `"modes_modes_modes" "sources_main_inspector" "logs_logs_logs"`
4. 更新 strategy-studio、ai-copilot、ai-agents 页面传入 modes slot

#### Fix 3: cross-market → RadarLayout

**实施步骤**:
1. 确认 RadarLayout 的 flex+sticky 实现匹配原型 `.shell-radar`
2. 将 `/markets/` 路由从 AnalyticalLayout 切换到 RadarLayout
3. 补齐 context-bar、scope-strip、right-rail slot 内容

### Phase 2: 页面级修复（7 批次，按家族分组）

#### 每页标准化流程
1. 读取原型 HTML → 提取精确布局度量（bounding rect）
2. 读取 React 页面组件 → 对比差距
3. 修复布局组件 → 验证 grid rows/cols 匹配
4. 修复/补齐内容组件 → 验证 section 存在且高度对齐
5. 运行 L1 token 检查 + L2 布局对比 + L3 截图对比
6. 确认偏差 < 3%、像素匹配 > 95%

#### B1: Command Center 家族（home, ai-overview）
- **home** (~99%): 微调即可
- **ai-overview** (~90%): 补齐 queue、inspector slot 内容

#### B2: Ops Console 家族（platform, signals, orders）
- **platform** (~98%): 补齐 status bar
- **signals** (~85%): 修复列宽 1100/380 → 匹配原型，补齐 toolbar/filter
- **orders** (~85%): 修复 strip 高度，补齐 table/status

#### B3: Analytical 家族（trading, research, risk, regime, intelligence）
- **trading** (~50%): 补齐 banner、session strip、analysis band；修复 orders panel 偏移
- **research** (~65%): 修复 analysis band 高度，补齐 main slot
- **risk** (~70%): 补齐 tabs、alerts、banner、analysis band
- **regime** (~40%): 补齐 strip、tabs、banner、analysis
- **intelligence** (~40%): 补齐 tabs、workspace 结构

#### B4: Studio 家族（strategy-studio, ai-copilot, ai-agents）
- **strategy-studio** (~75%): 修复 modes 行缺失（-193px height）
- **ai-copilot** (~50%): 实现 4 列布局，补齐 modes bar、sessions panel
- **ai-agents** (~20%): 整体重构——补齐 tabs、plans、正确 3 列布局

#### B5: Radar 家族（cross-market）
- **cross-market** (~30%): 整体切换到 RadarLayout，实现 flex+sticky 滚动页

#### B6: Catalog 家族（markets-screener）
- **screener** (~30%): 修复 prototype 截断问题，补齐 toolbar、table

#### B7: Object Hub 家族（instrument-hub）
- **instrument-hub** (~50%): 修复 header 偏移，补齐 tabs、bottom panel

---

## 验证标准

- **L1 Token**: 0 违规（`bun run test --run src/features/shell/design-system-compliance.test.ts`）
- **L2 布局**: 每个命名区域宽高偏差 < 3%
- **L3 像素**: UI diff 截图匹配 > 95%
- **工程**: `bun run check` 全部通过

## 原型参考

原型服务: `cd prototype && python3 -m http.server 8766 --bind 127.0.0.1`
React 服务: `bun run dev --host 127.0.0.1`
审计工具: `node scripts/visual-audit.mjs --prototype-base http://127.0.0.1:8766`
