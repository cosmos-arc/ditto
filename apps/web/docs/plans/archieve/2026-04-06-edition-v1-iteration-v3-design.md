# Edition v1 Iteration v3 — 混合介质突破

> **目标**: 在 HTML+CSS 原型中注入 Vanilla JS，突破 9.0-9.5 天花板，每页向 10.0 推进
> **日期**: 2026-04-06
> **前置**: Edition v1 Iteration v2（17/17 页面 ≥9.0，已完成）

---

## 约束

| 约束 | 值 |
|------|-----|
| 介质 | HTML + CSS + Vanilla JS（零外部依赖） |
| 强调色 | 保持 V1 indigo (hue 255, chroma 0.165) 不变 |
| 原型形态 | 单文件 HTML，JS 提取到 `shared/` |
| JS 能力 | 交互态切换、SVG 图表渲染、滚动动画、鼠标跟随效果 |
| Round 预算 | 30 轮 |

---

## Phase 划分

按 pre-v2 基线分数低分优先排序：

### P0 — 共享 JS 工具库（Round 0, 1 轮）

### P1 — Tier B 页面（Round 1-11, 基线 6.0-7.0）

| 页面 | Pre-v2 基线 | 目标 |
|------|------------|------|
| markets-intelligence | 6.0 | ≥9.5 |
| trading-overview | 7.0 | ≥9.5 |
| signals-inbox | 7.0 | ≥9.5 |
| orders-ledger | 7.0 | ≥9.5 |
| token-showcase | 7.0 | ≥9.5 |

### P2 — Tier A 页面（Round 12-20, 基线 7.5）

| 页面 | Pre-v2 基线 | 目标 |
|------|------------|------|
| cross-market | 7.5 | ≥9.5 |
| risk-center | 7.5 | ≥9.5 |
| ai-overview | 7.5 | ≥9.5 |
| ai-copilot | 7.5 | ≥9.5 |
| agent-console | 7.5 | ≥9.5 |

### P3 — Tier S 页面（Round 21-30, 基线 8.5-9.5）

| 页面 | Pre-v2 基线 | 目标 |
|------|------------|------|
| home | 8.5 | ≥9.5 |
| platform | 8.5 | ≥9.5 |
| research | 8.5 | ≥9.5 |
| markets-screener | 8.5 | ≥9.5 |
| strategy-studio | 8.5 | ≥9.5 |
| regime-monitor | 8.8 | ≥9.5 |
| instrument-hub | 9.5 | ≥10 |

---

## P0 — 共享 JS 工具库

**文件**: `prototype/shared/prototype-interactions.js`

### 模块设计（ES Module，零依赖）

| 模块 | 用途 | 调用方式 |
|------|------|---------|
| Tabs | 通用 Tab/抽屉/overlay 切换 | `data-tabs="group-name"` |
| Sparkline | SVG sparkline 渲染器 | `data-sparkline='{"data":[...],"stroke":"..."}'` |
| DonutGauge | SVG 环形仪表盘 | `data-donut='{"value":0.85,"label":"85%"}'` |
| HeatGrid | SVG 热力网格 | `data-heatgrid='{"rows":5,"cols":8}'` |
| NumberTicker | RAF 数字动画 | `data-ticker="12345.67"` |
| ScrollReveal | IntersectionObserver 入场动画 | `data-reveal="fade-up"` |
| MouseGlow | 鼠标跟随光晕效果 | `data-mouse-glow="true"` |
| ConfidenceBar | 动态置信度条 | `data-confidence="0.92"` |
| FlowBar | 流向条动画 | `data-flow='{"from":"待报","to":"已成"}'` |

### 设计原则

- **声明式**: HTML 中用 `data-` 属性标记，JS 自动初始化
- **渐进增强**: JS 未加载时，静态 CSS 仍然正常显示（≥9.0 基线）
- **共享数据**: 图表数据从现有 `shared/mock-data.js` 读取
- **单文件引用**: 17 个页面都引用同一个 JS 文件

### API 示例

```html
<!-- Tabs -->
<div data-tabs="views">
  <button data-tab-target="panel-1">Tab 1</button>
  <div data-tab-panel="panel-1">...</div>
</div>

<!-- Sparkline -->
<svg data-sparkline='{"data":[12,15,13,18,21],"stroke":"oklch(0.7 0.085 265)"}'></svg>

<!-- NumberTicker -->
<span data-ticker="12345.67" data-decimals="2"></span>

<!-- ScrollReveal -->
<div data-reveal="fade-up" data-reveal-delay="100"></div>

<!-- MouseGlow -->
<div data-mouse-glow="true"></div>

<!-- DonutGauge -->
<svg data-donut='{"value":0.85,"label":"85%","color":"oklch(0.65 0.15 160)"}'></svg>

<!-- ConfidenceBar -->
<div data-confidence="0.92" data-confidence-label="High"></div>

<!-- FlowBar -->
<div data-flow='{"segments":[{"label":"待报","value":3},{"label":"已报","value":5},{"label":"已成","value":12}]}'></div>
```

---

## P1 — 低分页面增强方案

### markets-intelligence（6.0 → ≥9.5）

**短板**: 信息密度最低，可视化深度不足，硬编码静态表格

**JS 增强**:
- HeatGrid: 板块热力图，数据驱动 SVG 渲染，hover 显示详情
- Sparkline: 每个板块/标的附带迷你走势线
- Tabs: 快讯/研报/公告 三栏实时切换
- ScrollReveal: 情报卡片瀑布流入场
- MouseGlow: 卡片区域微光跟随
- NumberTicker: 核心数据跳动效果

### trading-overview（7.0 → ≥9.5）

**短板**: P&L 数字静态，权益曲线硬编码

**JS 增强**:
- NumberTicker: 总 P&L / 日 P&L / 胜率等核心数字动画
- Sparkline: 权益曲线 JS 渲染（替代硬编码 SVG path）
- FlowBar: 资金流向条动画
- Tabs: 持仓/委托/成交 三态切换
- ScrollReveal: 面板分级入场

### signals-inbox（7.0 → ≥9.5）

**短板**: 信号卡片无交互，置信度静态

**JS 增强**:
- ConfidenceBar: 信号置信度动态条
- Tabs: 全部/买入/卖出/持有 分类过滤
- ScrollReveal: 信号卡片交错入场
- MouseGlow: 卡片悬停光晕
- NumberTicker: 收益率数字跳动

### orders-ledger（7.0 → ≥9.5）

**短板**: 订单状态静态，KPI 无动态

**JS 增强**:
- FlowBar: 订单状态流向（待报→已报→已成→全成）
- Tabs: 全部/待处理/已成/撤单 状态过滤
- NumberTicker: 成交金额/笔数等 KPI 滚动
- ScrollReveal: 订单行分级入场

### token-showcase（7.0 → ≥9.5）

**短板**: Token 展示为纯静态表格

**JS 增强**:
- Tabs: Token 分类切换（颜色/间距/字号/圆角...）
- ScrollReveal: Token 区块入场
- MouseGlow: 色块区域交互光效
- NumberTicker: 数值动画展示

---

## P2 — 中分页面增强方案

### cross-market（7.5 → ≥9.5）

- HeatGrid: 相关性矩阵 JS 渲染（hover 显示相关系数）
- FlowBar: 资金流向条
- Tabs: 关联矩阵/资金流向/板块联动 三视图切换
- MouseGlow: 矩阵区域光晕
- ScrollReveal: 面板入场

### risk-center（7.5 → ≥9.5）

- DonutGauge: 风险评级环形图 JS 渲染
- NumberTicker: VaR/最大回撤等核心指标动画
- Sparkline: 压力测试柱状图动态渲染
- Tabs: 概览/敞口/压力测试 切换
- ScrollReveal: 风险卡片入场

### ai-overview（7.5 → ≥9.5）

- ConfidenceBar: AI 置信度动态条
- NumberTicker: 信号准确率/响应时间指标动画
- Tabs: 概览/模型/信号 切换
- ScrollReveal: 模型卡片交错入场
- MouseGlow: AI 专属光晕效果

### ai-copilot（7.5 → ≥9.5）

- Tabs: 对话/分析/推荐 视图切换
- ScrollReveal: 思维链时间线逐步展开
- MouseGlow: 对话区微光跟随
- ConfidenceBar: 推荐置信度动态条
- FlowBar: 信息流向可视化

### agent-console（7.5 → ≥9.5）

- DonutGauge: 资源占用环形图
- NumberTicker: 任务数/成功率 动态计数
- Tabs: 全部/运行中/已完成 状态过滤
- ScrollReveal: Agent 卡片入场
- MouseGlow: 状态指示灯发光效果

---

## P3 — 高分页面增强方案

**策略**: CSS 基础已好，JS 增强以微交互 + 高级感为主

| 页面 | 核心 JS 增强 |
|------|-------------|
| home | NumberTicker（市场概览）、Sparkline（迷你走势）、MouseGlow（Banner 区） |
| platform | NumberTicker（系统指标）、Tabs（服务/性能/日志切换）、ScrollReveal |
| research | Tabs（研报/因子/回测）、ScrollReveal（研报卡片）、Sparkline（因子表现） |
| markets-screener | Tabs（筛选/排序/对比）、Sparkline（迷你走势列）、HeatGrid（板块热力） |
| strategy-studio | Sparkline（权益曲线）、NumberTicker（策略指标）、Tabs（策略/参数/绩效） |
| regime-monitor | HeatGrid（市场状态矩阵）、DonutGauge（状态概率）、ScrollReveal |
| instrument-hub | MouseGlow + ScrollReveal 精磨冲击 10.0 |

**P3 核心逻辑**: instrument-hub 已证明 9.5 天花板位置。P3 用 JS 消除「因为是静态所以扣分」的维度：
- **信息效率**: 交互态切换让同一面积承载 2-3 倍数据
- **高级感**: 数字动画 + 鼠标跟随 + 入场动画
- **品牌方向**: 交互品质感强化专业工具定位

---

## 评分标准

### 维度调整（JS 时代）

| 维度 | 原 CSS 标准 | 新 JS 标准 |
|------|------------|-----------|
| 克制度 | 装饰 ≤8 种变体 | JS 动画 ≤3 种类型/page，过度动效扣分 |
| 一致性 | 间距偏差 ≤4px | 交互行为跨页面一致（Tab 切换体验统一） |
| 高级感 | 材质/光影/微动画 CSS-only | +数字动画流畅度、鼠标跟随自然感、入场时机 |
| 品牌方向 | Bloomberg/量化 DNA | +交互品质感：专业工具感而非消费级 app |
| 信息效率 | 数据密度 ≥12 chars/Kpx | +交互态切换让同面积承载 2-3 倍数据 |

### 10 分门槛新增

- 至少 3 种 JS 交互类型协同工作
- 交互态切换后信息架构仍然清晰
- 所有动效尊重 `prefers-reduced-motion`
- 零 JS 降级时页面仍 ≥9.0 CSS 基线

---

## 迭代循环

```
每轮（Round）:
  ┌─ 1. SELECT  — 按 Phase/分数选择下一个页面
  ├─ 2. AUDIT   — 6 角色评审当前状态，定位短板
  ├─ 3. ENHANCE — 注入 JS 交互 + 微调 CSS
  ├─ 4. REVIEW  — 6 角色重新评分
  ├─ 5. SCORE   — 5 维度复合评分记录
  └─ 6. REFLECT — 记录什么有效/无效/死胡同
```

### 6 角色评审

1. UI Designer — Token 合规、视觉层级、色彩
2. UX Reviewer — 可访问性、交互、viewport 完整性
3. PM — Spec 合规、功能层级、产品边界
4. IA Specialist — 信息分组、导航、标签
5. Copy Editor — 标签、文案、数字格式
6. Art Director — 高级感、品牌方向、整体气质

---

## Git 工作流

| 操作 | 值 |
|------|-----|
| Branch | `feat/prototype-three-zone-architecture`（继续） |
| Commits | `feat(prototypes): v1-iter-v3 P0 shared JS utilities` |
| Tag | `edition-v1-iter-v3`（全部完成后打） |
| Manifest | 更新 `.edition-manifest.json` 的 `iterationV3` 字段 |

---

## 验收标准

- [ ] 17/17 页面 ≥9.5 分
- [ ] instrument-hub 冲击 ≥10 分
- [ ] 共享 JS 库被所有页面引用
- [ ] `prefers-reduced-motion` 全覆盖
- [ ] JS 禁用时页面仍 ≥9.0 CSS 基线
- [ ] 内联样式不反弹（≤450 总量）
- [ ] Manifest `iterationV3` 字段完整记录
