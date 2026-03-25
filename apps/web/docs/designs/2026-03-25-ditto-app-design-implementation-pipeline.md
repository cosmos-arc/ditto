# Ditto App 前端设计实施流水线

> 基于 [AI 设计工作流调研](../research/2026-03-22-ai-design-workflow-for-solo-developers.md) Workflow C（Claude Code-centric），
> 结合 [产品设计方案](2026-03-24-ditto-app-product-design.md)、[技术选型](2026-03-24-ditto-app-techstack.md)、
> [Design Token 架构](2026-03-25-ditto-app-design-token-architecture.md) 制定。
>
> 状态：Phase 1 已完成 ✅
> 决策日期：2026-03-25
> Phase 1 完成日期：2026-03-25

---

## 1. 背景与决策

### 1.1 当前状态

| 阶段 | 状态 |
|------|------|
| Phase 1: 信息架构 & Sitemap | 已完成（产品设计文档） |
| Design Token 架构设计 | 已完成（Primitive + Semantic 两层） |
| 技术选型 | 已冻结（React 19 + Vite 8 + Tailwind 4 + shadcn/ui v4） |
| `ditto-app` 仓库 | 待创建 |
| 页面视觉设计 | 未开始 |

### 1.2 关键决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 页面范围 | 全部 10 页 | 完整产品体验，不分期 |
| 探索策略 | Stitch 全量探索 → Pencil 精化 | 充分探索视觉方向；Token 架构文档足够详细，可编码为高质量 Stitch 提示词 |
| 执行顺序 | 先脚手架 + Tokens → 再 Stitch | 验证视觉基线后再写提示词，减少 Stitch 返工 |
| Impeccable 时机 | Phase 4 生产阶段再安装 | Impeccable 是代码质量门禁（20 个设计命令 + 反模式检查），不是设计探索工具；Stitch 生成独立 HTML/CSS 不涉及；脚手架/Token 阶段不需要 |

---

## 2. 完整流水线

```
Phase 1: 脚手架 + Design Tokens 实现
    ↓
Phase 2a: Stitch 全量探索（10 页面 × 3-5 风格方向）
    ↓
Phase 2b: Pencil 精确设计
    ↓
Phase 3: Design System 完善
    ↓
Phase 4: 生产代码 + Impeccable 质量门禁
```

---

## 3. Phase 1: 脚手架 + Design Tokens 实现

### 3.1 目标

搭建 `ditto-app` 项目骨架，实现 Design Token CSS 变量，渲染基础 Dashboard 空壳并在浏览器中验证视觉基线。

### 3.2 任务清单

- [x] Vite 8 + React 19 项目初始化（Bun 包管理）
- [x] Tailwind CSS 4.x 配置（CSS-first，`@theme inline`）
- [x] shadcn/ui v4 CLI 初始化
- [x] Design Token CSS 变量实现
  - [x] Primitive Token：6 色相 × 6 级色阶 + 12 级中性灰 + 8 色图表系列
  - [x] Semantic Token：四色域（Market / Risk / System / Signal）× fg/bg/stroke
  - [x] `:root`（light）+ `.dark`（dark-first）完整映射
  - [x] Typography：Inter（UI）+ JetBrains Mono（技术字段）
  - [x] Density 三级：comfortable(40px) / compact(32px) / ultra-compact(26px)
  - [x] Motion 约束：token 级别开关（`--motion-flash-enabled`）
- [x] shadcn/ui Token 桥接表映射（保留 shadcn 原生 token 名，值指向 Ditto Semantic）
- [x] 渲染 Dashboard 空壳页面（侧边栏 + 顶栏 + 内容区骨架）
- [x] 浏览器验证：色彩对比度、字体层级、间距节奏、暗色/亮色切换

### 3.3 验证标准

- dark 主题下四色域颜色在 Dashboard 骨架中视觉可辨
- light 主题同样完整可用（非事后补丁）
- shadcn/ui 默认组件（Button、Card、Input）使用 Ditto Token 后样式正确
- Density 切换可实时生效

### 3.4 上游依赖

- [Design Token 架构设计](2026-03-25-ditto-app-design-token-architecture.md)（已完成）
- [技术选型清单](2026-03-24-ditto-app-techstack.md)（已冻结）

---

## 4. Phase 2a: Stitch 全量探索

### 4.1 目标

基于 Phase 1 验证过的视觉基线，为全部 10 个页面生成多风格方向的视觉原型。

### 4.2 页面清单

1. Dashboard（首页概览）
2. 行情数据（K线、实时数据）
3. 因子研究
4. 策略中心
5. 回测中心
6. 体制分析
7. 风控中心
8. 实验管理
9. 报告中心
10. 设置

### 4.3 Stitch 提示词策略

将 Design Token 架构中的约束编码为 Stitch 提示词：
- 色彩域约束：Market(up/down/flat)、Risk(四档)、System(四态)、Signal(buy/sell/hold 蓝紫灰)
- 暗色优先：默认 dark theme
- 字体：Inter UI + JetBrains Mono 技术字段
- 密度：默认 compact(32px)
- 动效约束：无数字滚动、无价格闪烁、无骨架屏闪光
- 图表：独立 8 色系列，不复用市场红绿
- 布局参考：TradingView / Bloomberg Terminal 量化产品风格

### 4.4 产出

- 每个页面 3-5 种风格方向（HTML/CSS 导出）
- 选定最终视觉方向（1 套统一风格）

---

## 5. Phase 2b: Pencil 精确设计

### 5.1 目标

在 Claude Code + Pencil MCP 中，基于选定风格方向做精确设计，产出可用于生产的设计稿。

### 5.2 工作方式

- Pencil.dev MCP 协议，在 VS Code / Cursor 内操作
- Claude 直接读取/写入 `.pen` 设计文件
- 可导入 Stitch 导出的 HTML/CSS 作为起始素材
- 6+ AI Agent 并行生成完整用户流程

### 5.3 产出

- 完整用户流程设计稿（`.pen` 格式）
- 交互细节、响应式适配方案
- 组件级精确规格

---

## 6. Phase 3: Design System 完善

### 6.1 目标

基于 Token 架构 + Pencil 设计稿，完善 Design System 实现。

### 6.2 任务清单

- [ ] Style Dictionary Token 分发（如需跨平台消费）
- [ ] shadcn/ui 组件定制（CVA 变体 + Ditto Token）
- [ ] DittoGrid 封装（AG Grid themeQuartz.withParams() 桥接）
- [ ] 图表组件封装（Lightweight Charts + ECharts CSS 变量消费）

---

## 7. Phase 4: 生产代码 + Impeccable 质量门禁

### 7.1 目标

基于 Pencil 设计稿 + Design System，用 Claude Code + shadcn/ui 实现全部 10 个页面的生产代码。

### 7.2 Impeccable 集成

- 安装时机：Phase 4 启动时
- 初始化：`/teach-impeccable` 收集 Ditto 设计上下文
  - 量化产品、dark-first、OKLCH 色彩
  - 四色域分离（Market / Risk / System / Signal）
  - 动效约束（禁止数字滚动、价格闪烁、骨架屏闪光）
  - Inter + JetBrains Mono 字体组合
  - 三级密度系统
- 质量门禁流程：
  - `/audit` — 综合审计（可访问性、性能、主题、响应式）
  - `/critique` — UX 评估（视觉层级、信息架构）
  - `/polish` — 上线前精修（对齐、间距、一致性）
  - `/normalize` — 设计系统一致性检查

### 7.3 验证标准

- 全部 10 页面功能完整
- Impeccable `/audit` 无严重问题
- dark / light 主题完整可用
- 三级密度切换正常
- AG Grid / Lightweight Charts / ECharts 与 Ditto Token 集成正确
