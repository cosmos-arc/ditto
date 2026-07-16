# Home 页面像素级还原 — Mock 数据 + 组件样式全面对齐

## Context

L3 像素对比 diff ratio 7.69%，根因不仅是 CSS 视觉效果，更核心的是：
1. **Mock 数据完全不同** — React 用的测试数据和 prototype 静态数据不一致
2. **导航图标完全不同** — 6 个 domain icon 的 SVG 路径和风格（outline vs filled）全部不同
3. **Header 内容不同** — "Command Center" vs "首页"，搜索栏/主题切换/Help 按钮都不同
4. **组件细节差异** — StatusDot、Sparkline、RegimeTag、QueueTag 等尺寸/样式不同
5. **Market Pulse sidebar 结构不同** — prototype 显示"沪深300/波动率/涨跌比/北向资金"，React 显示指数列表

## 修改范围

### Phase 1: Mock 数据对齐（最高像素影响）

**文件**: `src/mocks/fixtures/home.ts`

将所有 mock 数据改为与 prototype HTML 完全一致：

#### 1.1 HomePulseResponse
```ts
{
  date: "2026-03-28",           // prototype: "2026-03-28"
  session: "continuous",        // prototype: "盘中交易"
  pendingActions: 2,            // prototype: "2 项待处理，含 1 项 P1"
  criticalAlerts: 0,            // not rendered but keep
  runningJobs: 3,               // prototype: "3 个后台任务运行中"
  pnlToday: 86472.50,           // prototype: "+¥86,472.50"
  pnlPercent: 0.34,             // prototype: "+0.34%"
}
```

#### 1.2 DecisionBannerResponse
```ts
{
  totalEquity: 25432180,        // prototype: "总权益 ¥25,432,180"
  dailyPnl: 86472.50,           // prototype: "+¥86,472.50"
  dailyPnlPercent: 0.34,        // prototype: "+0.34%"
  riskUtilization: 0,           // not used
  leverage: 1.2,                // prototype: "杠杆率 1.2x"
  maxDrawdown: -3.8,            // prototype: "回撤 -3.8%"
  ivix: 18.52,                 // prototype: "IVIX 18.52"
  northboundFlow: 12.4,         // prototype: "北向资金 +12.4 亿"
  equitySparkline: [20.1, 19.8, 19.5, 19.2, 18.9, 18.7, 18.52], // prototype IVIX sparkline
  marketRegime: "mixed",        // prototype: "温和风险偏好" = moderate = mixed
  regimeType: "温和风险偏好",    // prototype text
  suggestion: "波动回落，北向转暖，但局部拥挤。", // prototype text
}
```

#### 1.3 PendingAction[] — 5 项完全匹配 prototype
| priority | title | badge | domain | meta | time |
|----------|-------|-------|--------|------|------|
| critical | 贵州茅台（600519）出现卖出信号 | 交易 + P1 | trading | RSI 背离叠加放量，Alpha v3 置信度 87%，建议查看卖出上下文。 | 3分钟前 |
| critical | 行业集中度超限 — 科技板块 > 35% | 风控 + P1 | trading | 当前占比 37.2%，超过规则上限，需评估是否降集中度。 | 12分钟前 |
| high | 价值因子 2026 Q1 回测完成 | 研究 + P2 | research | Sharpe 1.42，最大回撤 -8.3%，建议审阅后决定是否部署。 | 1小时前 |
| medium | Tushare API 频率接近上限 | 平台 | platform | 今日已用 4,820 / 5,000 次，3 小时后重置。 | 2小时前 |
| medium | 沪深300 1 分钟 K线缺失 | 数据 | platform | 14:32–14:33 数据缺失，正在自动补全，建议关注修复结果。 | 42分钟前 |

需要扩展 `PendingAction` 类型：`badge` 改为数组支持多个标签（交易+P1, 风控+P1 等）。

#### 1.4 AgentFinding[] — 3 项匹配 prototype "研究进展"
| icon | text | source | time |
|------|------|--------|------|
| insight | 情绪 Alpha v2 模型漂移检测 — 近 5 日 IC 从 0.041 降至 0.028，需关注。 | 模型监控 · 2小时前 | 需加 time 字段 |
| warning | 新因子「北向持仓变化率」验证中 — 初步 IC 0.055，待 3 个月滚动验证。 | 因子研究 · 4小时前 | |
| info | 行业轮动策略参数优化完成 — 新参数组 Sharpe 提升 0.15，待人工复核。 | 优化引擎 · 6小时前 | |

需要给 `AgentFinding` 类型添加 `summary` 字段（副标题）和 `time` 字段。

#### 1.5 HomeAlert[] — 4 项匹配 prototype "全局预警"
| severity | title | time |
|----------|-------|------|
| critical | 组合 VaR 突破 95% 分位 | 8分钟前 |
| critical | 券商连接中断 — 中信证券 | 15分钟前 |
| warning | 模型漂移 — 情绪 Alpha v2 | 1小时前 |
| info | 财报数据延迟 | 2小时前 |

#### 1.6 DataHealthProvider[] — 5 项匹配 prototype "数据健康"
| label | status | statusText |
|------|--------|------------|
| 行情数据 | healthy | 正常 |
| 期权链 | healthy | 正常 |
| 财报数据 | degraded | 延迟 |
| 新闻资讯 | healthy | 正常 |
| 另类数据 | degraded | 陈旧（3天） |

#### 1.7 Market Pulse Sidebar — 结构变化
prototype 的市场脉搏不是指数列表，而是 4 个特定指标：
- 沪深300: 3,432 · +0.82%（带 sparkline）
- 波动率: IVIX 18.52 · -3.1%（带 sparkline）
- 涨跌比: 2.1:1 · 偏多
- 北向资金: +12.4 亿（带 sparkline）

新增 mock 数据类型 `MarketPulseMetric`，修改 `market-pulse-section.tsx` 消费新数据。

### Phase 2: 导航图标替换（rail 全部 56x900px 区域）

**文件**: `src/features/navigation/components/domain-icon.tsx`

将 6 个 domain icon 的 SVG 路径替换为 prototype 的 outline 版本（viewBox="0 0 20 20", stroke="currentColor", strokeWidth=1.5）：

| Domain | Prototype SVG path |
|--------|-------------------|
| home | `M3 10.5V17a1 1 0 001 1h4v-5h4v5h4a1 1 0 001-1v-6.5L10 3 3 10.5z` |
| markets | `M3 17l4-4 3 2 7-8` + circle cx=17 cy=7 r=1.5 fill=currentColor |
| research | circle cx=9 cy=9 r=5.5 + `M13 13l4 4` |
| trading | `rect x=3 y=6 w=14 h=10 rx=1` + `M3 10h14M7 6v10M13 6v10` |
| ai | `M10 2l2.5 5.5L18 9l-4 4 1 6-5-2.5L5 19l1-6-4-4 5.5-1.5L10 2z` |
| platform | 4 个 `rect` (3,3 / 11,3 / 3,11 / 11,11) 各 6x6 rx=1 |

Settings icon（rail 底部）也需对齐。

### Phase 3: Header 对齐

**文件**: `src/features/shell/components/header.tsx`, `src/features/shell/components/theme-switcher.tsx`

1. 页面标题: 确认 route handle title 是 "首页"（不是 "Command Center"）
2. 搜索栏: 添加 "搜索..." placeholder 文本
3. 主题切换: 从 SVG 图标改为文字按钮 "暗"/"亮"
4. 添加 Help 按钮（圆圈 + "?" icon）
5. 通知按钮 SVG viewBox 对齐（prototype 用 20x20）

### Phase 4: 组件细节修复

#### 4.1 StatusDot — `src/components/status/status-dot/status-dot.tsx`
- 默认尺寸: 8px → 6px
- 动画: 移除 `scale(1.4)` 变换，只保留 opacity 1→0.6
- 动画时长: 2s → 3s

#### 4.2 Sparkline — `src/components/data/sparkline/sparkline.tsx`
- 曲线插值: Catmull-Rom → 直线段（匹配 prototype 的 polyline）
- 面积渐变透明度: 0.3 → 0.2
- 确保 banner PnL sparkline width=64, sidebar sparkline width=48

#### 4.3 Regime Tag — `src/features/home/components/pulse-section.tsx`
- border-radius: `--radius-sm` → 10px (pill)
- padding: 对齐 prototype 的 `1px 8px`
- font-size: 对齐 prototype 的 `--font-size-10`
- letter-spacing: 添加 `0.02em`

#### 4.4 Queue Item Tags — `src/features/home/components/priority-queue-section.tsx`
- border-radius: 对齐 prototype `--radius-2`
- font-size: 对齐 prototype `--font-size-10`
- 支持多个标签（P1/P2/P3 + domain 标签）

#### 4.5 Panel Count Badge — `src/features/shell/components/panel.tsx`
- 添加 `border-radius: var(--radius-sm)`

#### 4.6 Banner 主指标格式
- 当前: `¥158.0万`（除以 10000）
- 改为: `+¥86,472.50`（原始值，带千分位格式化）
- metric label: "总权益" → "今日盈亏"
- sub 格式: 对齐 prototype "较昨日 +¥21,400"

#### 4.7 Scrollbar Track
- `globals.css` scrollbar-track: `transparent` → `var(--color-surface-0)`

### Phase 5: 结构性修复

#### 5.1 Market Pulse Sidebar
- 组件需重写以显示 prototype 的 4 个特定指标（而非指数列表）
- 每个指标需支持 sparkline 内联渲染

#### 5.2 Noise Layer Ambient Rail
- 将 right ambient bar 从 NoiseLayer（全屏覆盖）移到 Rail 导航内部

#### 5.3 Agent Findings 组件数据源对齐
- prototype 的 "Agent 洞察" 显示 3 条关联分析文本
- 需新增 mock 数据替换现有 `RecentSignal` 数据源

## 执行顺序

1. **Phase 1**（mock 数据） — 最大像素影响，优先
2. **Phase 2**（导航图标） — rail 区域完全不同
3. **Phase 4.6**（banner 格式） — banner 区域核心差异
4. **Phase 4.1-4.5**（组件细节） — 累积影响
5. **Phase 3**（header） — header 区域差异
6. **Phase 5**（结构性修复） — 复杂度最高，最后做

## 验证

1. `bun run check` 通过
2. 启动 dev server (`bun run dev`) + prototype server (`python3 -m http.server 8888 --directory /home/chevy/projects/ditto-app`)
3. 运行 L3 像素对比，目标 diff ratio < 3%
4. 人眼 side-by-side 确认无显著差异
