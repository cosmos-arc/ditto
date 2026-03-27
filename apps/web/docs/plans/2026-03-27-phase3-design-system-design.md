# Phase 3 — Design System 基础设施建设

> 日期：2026-03-27
> 状态：设计稿
> 依赖：Phase 2a Stitch 原型探索（已完成）、Design Token v2（已完成）

---

## 1. 背景与动机

### 现状

- **Design Token v2** 已完成：四层架构（Primitive → Semantic Core → Domain Semantic → Component），OKLCH 色彩空间，完整的暗色/亮色双主题
- **4 个 Stitch 原型**已生成：Home、Market、Research、Trading 页面
- **问题**：原型基于 Token 参考生成，但与 Token v2 存在数值和命名差异

### 目标

建立完整的 Design System 基础设施，使 Phase 4（页面转换）可以高效进行。

### 核心决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 转换策略 | 基础设施先行 | 前期投入大但长期回报最高，避免逐页重复搭建 |
| 页面转换时机 | Phase 3 完整完成后 | 组件库完整，页面转换可批量推进 |
| Token Pipeline | Style Dictionary | 业界标准，单一数据源，多平台输出 |
| 原型 vs Token 冲突处理 | 全面审计先行，逐项裁决 | 4 原型规模可控，一次性搞清差异比后期反复裁决高效 |
| Source of Truth | 原型视觉结果优先，Token 数值可修正 | 用户认可的视觉效果是最终交付物 |

---

## 2. Phase 3 产出物总览

```
Phase 3 产出物
├── 0. Token 全面审计报告
│   └── 4 原型 vs Token v2 完整 diff + 逐项裁决
├── 1. Token Pipeline（Style Dictionary）
│   ├── token/ 目录：单一数据源（JSON）
│   └── 构建输出：CSS 变量 + Tailwind @theme + JSON
├── 2. 布局组件
│   ├── Panel / Card / Toolbar
│   └── Sidebar / Topbar / Page Layout
├── 3. 数据表格
│   ├── DittoGrid（AG Grid 封装）
│   ├── 列定义类型系统
│   └── 密度控制（compact/comfortable/ultra-compact）
├── 4. 状态展示组件
│   ├── Badge / StatusIndicator
│   ├── KPI / Progress
│   └── 各域状态组件（Market/Risk/Execution 等）
├── 5. 基础交互组件（shadcn 扩展）
│   ├── Button / Input / Tabs（已有，需扩展）
│   ├── Toast / Modal / CommandPalette（新增）
│   └── 所有组件接入 Ditto Component Tokens
└── 6. 质量保障
    ├── Token 使用率自动化检查
    ├── 组件验证页面（Dashboard Shell 扩展）
    └── 组件单元测试（覆盖率 ≥ 80%）
```

---

## 3. Step 0：Token 全面审计

### 3.1 审计范围

对每个原型提取所有设计值，与 Token v2 逐项对比：

| 审计维度 | 提取内容 | 对比目标 |
|----------|---------|---------|
| 颜色 | 所有 hex/rgba/oklch 值 | Primitive + Semantic + Domain Token |
| 字体 | font-family、font-size、font-weight | Typography Token |
| 间距 | padding/margin/gap 值 | Spacing Token |
| 圆角 | border-radius 值 | Radius Token |
| 阴影 | box-shadow 值 | Shadow Token |
| 动效 | transition/animation 值 | Motion Token |

### 3.2 审计流程

```
1. 自动提取：脚本扫描 4 个 HTML，提取所有设计值
2. 自动对比：生成 diff 报告（原型值 vs Token v2 值）
3. 人工裁决：逐项对比截图视觉效果
   - 原型值更好 → 更新 Token
   - Token 值更好 → 标记"原型需对齐"
   - 原型有 Token 缺失 → 补充 Token
4. 输出：裁决文档 + Token 修正清单
```

### 3.3 裁决规则

| 差异类型 | 处理方式 | 理由 |
|----------|---------|------|
| 色值微调（视觉差异小） | 以截图视觉为准，更新 Token | 用户认可的视觉效果是最终交付物 |
| 命名体系冲突（如 MD3 vs Ditto） | Token 命名为准，代码转换时对齐 | 命名是架构决策 |
| 原型有 Token 缺失的值 | 补充到 Token 体系 | 原型验证了需求 |
| Locale 错误（如涨跌色用错） | Token 为准 | 业务规则不应由原型决定 |
| 原型引入 Token 不存在的概念 | 评估是否纳入体系 | 按需决策 |

### 3.4 已知差异（基于前期分析）

**Home Overview（质量最高，~80% 对齐）：**
- 命名使用 `--ditto-*` 前缀，需统一到 Token v2 的点路径命名
- 覆盖了 Market/Risk/Model 域，缺少 Execution/System/Data 域
- 无障碍和语义化已做好，是质量标杆

**Trading Overview（~20% 对齐）：**
- 使用 Material Design 3 命名，与 Ditto Token 完全不同
- 零 CSS 变量，全部硬编码 hex
- 执行状态使用通用颜色（Tailwind green/blue/red），未使用 Execution Domain Token
- 字体使用 Inter 单一字体，未使用完整的 font stack

**Research Overview（~40% 对齐）：**
- Tailwind config 中有部分 Ditto Primitive Token overlay
- 因子健康状态使用通用颜色，未使用 Model Domain Token
- 同样零 CSS 变量

**Market Overview（~30% 对齐）：**
- 有 Ditto-like 命名但数值不匹配
- Market locale 错误（用了 global 模式的绿涨红跌）
- 硬编码 hex 最多（~40+ 处）

---

## 4. Step 1：Token Pipeline（Style Dictionary）

### 4.1 目录结构

```
token/
├── source/
│   ├── primitives.json
│   ├── semantic-core.json
│   ├── semantic-market.json
│   ├── semantic-risk.json
│   ├── semantic-execution.json
│   ├── semantic-system.json
│   ├── semantic-data.json
│   ├── semantic-model.json
│   ├── components.json
│   ├── charts.json
│   ├── grid.json
│   ├── typography.json
│   └── motion.json
├── build/
│   ├── css.js          # 输出 CSS 变量文件
│   ├── tailwind.js     # 输出 Tailwind @theme 配置
│   └── json.js         # 输出原始 JSON
├── output/
│   ├── tokens.css
│   ├── tailwind-theme.css
│   └── tokens.json
└── config.js
```

### 4.2 迁移策略

1. 从现有 CSS 文件提取所有 token 到 JSON（自动化脚本）
2. 按审计裁决结果修正 JSON 中的数值
3. 配置 Style Dictionary 构建管道
4. 构建输出替换现有 CSS 变量文件
5. 验证：现有测试 + Dashboard Shell 视觉验证

### 4.3 质量检查

- 构建后自动运行 token 完整性测试
- 确保 CSS 输出与当前 primitives.css / semantic-*.css 完全等价
- 确保所有 token 使用 OKLCH 色彩空间

---

## 5. Step 2-4：组件开发（三波推进）

### Wave 1 — 页面骨架依赖

| 组件 | 说明 | Token 依赖 |
|------|------|-----------|
| Panel | 容器组件，可折叠/展开 | Component: Panel Token |
| Card | 信息卡片，支持 size 变体 | Component: Card Token |
| Toolbar | 工具栏，左/中/右三段式 | Component: Toolbar Token |
| Sidebar | 侧边导航栏 | Component: Sidebar Token |
| Topbar | 顶部导航栏 | Component: Topbar Token |
| Badge | 状态徽章 | Component: Badge Token |
| StatusIndicator | 圆点/条形状态指示器 | Domain: All Token |
| KPI | 关键指标卡片 | Component: KPI Token |

### Wave 2 — 数据交互依赖

| 组件 | 说明 | Token 依赖 |
|------|------|-----------|
| DittoGrid | AG Grid 封装 | Component: Grid Token |
| Tabs | 选项卡（扩展现有） | Component: Tabs Token |
| Input | 输入框（扩展现有） | Component: Input Token |
| Select | 下拉选择 | Component: Input Token |
| Toast | 反馈提示 | Component: Toast Token |
| DataTable | 数据表格（DittoGrid 上的业务封装） | Domain + Grid Token |

### Wave 3 — 完整体验依赖

| 组件 | 说明 | Token 依赖 |
|------|------|-----------|
| Modal | 模态框 | Component: Modal Token |
| Drawer | 抽屉面板 | Component: Drawer Token |
| CommandPalette | 命令面板 | Component: CommandPalette Token |
| Progress | 进度条 | Component: Progress Token |
| Tooltip | 工具提示 | Component: Tooltip Token |
| Popover | 弹出层 | Component: Popover Token |
| ChartContainer | 图表容器封装 | Chart Token |

### 组件开发规范

- **TDD 流程**：RED → GREEN → REFACTOR
- **Token 使用率**：100%，零硬编码值
- **双主题**：暗色 + 亮色完整支持
- **密度支持**：布局组件支持 compact/comfortable/ultra-compact
- **状态覆盖**：至少 default + hover + focus + disabled
- **无障碍**：基础键盘导航 + ARIA 属性
- **测试覆盖率**：分支覆盖率 ≥ 80%

---

## 6. Step 5：质量保障

### 6.1 Token 使用率检查

- Biome 自定义规则或 ESLint 插件：检测 TSX/CSS 中是否有硬编码颜色/间距值
- CI 集成：token 使用率低于 100% 时构建失败

### 6.2 组件验证

- 扩展现有 Dashboard Shell 验证页面，展示所有新组件
- 每个组件展示所有变体、状态、主题、密度组合

### 6.3 测试

- 单元测试：Vitest + RTL，覆盖率 ≥ 80%
- Token 完整性测试：确保所有 Token 层级完整、无循环引用
- 视觉验证：截图对比（可选，后期引入）

---

## 7. Phase 4 展望（页面转换）

Phase 3 完成后，Phase 4 的页面转换将变得高效：

```
Phase 4 流程（Phase 3 完成后）
├── 每个页面转换工作量预估：~1-2 天/页面
├── 主要工作：
│   ├── 组件组合（80% 已有组件）
│   ├── 业务逻辑接入（TanStack Query + Zustand）
│   ├── 状态处理（loading/error/empty）
│   └── 响应式适配
└── Token 对齐工作量：≈ 0（Phase 3 已解决）
```

**对比**：如果不做 Phase 3 直接转换页面，预估每个页面 3-5 天（含组件搭建 + Token 对齐），且 4 个页面会有大量重复工作。

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Style Dictionary 迁移破坏现有测试 | 高 | 迁移后输出必须与当前 CSS 等价，先跑测试再替换 |
| 审计裁决耗时过长 | 中 | 设置裁决超时规则：5 分钟内无法决定的以 Token v2 为准 |
| AG Grid 封装复杂度超预期 | 中 | 先实现最小可行版本（基础列 + 密度），后续迭代 |
| 组件 API 设计不满足页面需求 | 中 | Wave 1 完成后做一次对照原型的设计 review |
| Phase 3 耗时过长延迟页面开发 | 低 | 可在 Wave 1 完成后提前启动 Home Overview 页面转换 |

---

## 附录：参考资料

- [Design Token v2 架构文档](../designs/2026-03-26-ditto-app-design-token-v2.md)
- [视觉原则文档](../designs/2026-03-26-ditto-visual-principles.md)
- [Stitch 原型目录](../designs/stitch/)
- [产品需求文档](../designs/2026-03-24-ditto-app-product-design.md)
- [技术栈文档](../designs/2026-03-25-ditto-app-techstack.md)
