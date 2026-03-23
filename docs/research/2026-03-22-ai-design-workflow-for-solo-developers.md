# AI Design Workflow for Solo Developers — 业界调研报告

> 调研时间：2026-03-22
> 目标受众：个人开发者，追求设计专业度，倾向免费/低成本方案
> 核心诉求：Vibe Design + 完整前端落地能力 + 设计系统一致性

---

## 一、工具生态全景（2026 年 3 月）

2026 年 AI 设计工具形成**四层架构**：

### 第零层：AI 设计语言 / Skills

| 工具 | 定位 | 核心能力 | 成本 |
|------|------|---------|------|
| [Impeccable](https://impeccable.style/) | 开源 AI 设计语言（CLAUDE.md skill） | 在 Anthropic `frontend-design` 基础上提供 20 个设计命令 + 反模式清单，让 Claude 生成的 UI 告别"AI 味" | 开源免费 |

**本质**：不是独立设计工具，而是给 AI 编码代理装上"设计师的词汇表"——通过 slash commands 和反模式约束，让 vibe coding 产出有意为之的 UI。

GitHub: https://github.com/pbakaus/impeccable

### 第一层：Vibe Design（灵感 → 高保真原型）

| 工具 | 定位 | 核心能力 | 成本 | 局限 |
|------|------|---------|------|------|
| [Google Stitch](https://stitch.withgoogle.com/) | AI 原生设计画布 | 自然语言/语音生成 UI，多 Agent 协作，HTML/CSS/Tailwind/JSX 导出，一键 Figma 导出 | 完全免费（Google Labs） | React app 导出预计 Google I/O 2026；实验性产品，月生成限额 |
| [Motiff](https://motiff.com/)（字节跳动） | AI-native UI 设计工具 | 类 Figma 界面 + 更深 AI 集成，AI UI 生成/布局/样式，一键导出 React/HTML | 免费 + $16/月 | 生态还在追赶 Figma |
| [Relume](https://www.relume.io/) | AI 信息架构 + 线框图 | 描述 → sitemap → wireframe → style guide | 免费档 | 偏网站场景 |
| [Magic Patterns](https://www.magicpatterns.com/) | Text-to-UI 原型 | 文本生成高保真原型，多变体对比 | 免费档 | 非生产代码 |

### 第二层：Design-to-Code（原型 → 可运行代码）

| 工具 | 定位 | 核心能力 | 成本 | 局限 |
|------|------|---------|------|------|
| [Pencil.dev](https://pencil.dev/) | IDE 内原生设计画布 | MCP 协议驱动无限画布，`.pen` 开放格式，6+ AI Agent 并行生成 flow，直接在 Cursor/VS Code 中设计→代码零切换 | 完全免费（需 Claude Code） | 生态较新，文档还在成长 |
| [v0 (Vercel)](https://v0.app/) | AI 组件/页面生成 | 6M+ 用户，React+Tailwind+shadcn/ui，内置 Design System，MCP Server | 免费档 | 绑定 Vercel 生态 |
| [Lovable](https://lovable.dev/) | AI 全栈应用构建器 | Prompt → 全栈 TS/React 应用，原生 Supabase 集成 | 免费档 | UI 精细控制有限 |
| [Bolt.new](https://bolt.new/) | 浏览器全栈 IDE | text/image/Figma/GitHub 输入，内置 hosting + DB | 免费档（1M tokens/月） | 框架灵活但设计一致性需额外维护 |

### 第三层：AI-Native IDE（代码打磨 → 生产就绪）

| 工具 | 定位 | 核心能力 | 成本 |
|------|------|---------|------|
| [Cursor](https://cursor.com/) | AI 原生代码编辑器 | VS Code fork，全代码库索引，上下文感知编辑 | 免费+$20/月 |
| [Claude Code](https://claude.ai/claude-code) | AI 编程 CLI | 终端原生，深度代码理解，Agent 模式，天然支持 Impeccable skill | $20/月起 |

### 关键趋势

> **从"设计工具 + 编码工具分离"走向"设计能力嵌入编码流程"**。
>
> - Pencil.dev 把设计画布直接搬进 IDE
> - Impeccable 把设计语言教给 AI 编码代理
> - 2026 年核心叙事已从"AI 能不能做设计"转向"如何让 AI 生成的 UI 保持设计一致性"

---

## 二、推荐工作流：Claude Code 为中心的设计-开发一体化

核心理念：**Claude Code 作为统一中枢**，上游连接灵感采集和站点规划，中游驱动设计系统和原型迭代，下游直接产出生产代码。

### 全链路概览

```
Phase 0: 灵感采集与需求定义
Phase 1: 信息架构 & 站点地图
Phase 2: 交互设计 & 原型（Stitch 发散 → Pencil 收敛）
Phase 3: 设计系统 & Design Token
Phase 4: 生产落地
```

### Phase 0：灵感采集与需求定义

**目标**：确定"要做什么"和"参考什么"。

| 步骤 | 工具 | 成本 | 说明 |
|------|------|------|------|
| 0a 收集竞品/灵感截图 | [Mobbin](https://mobbin.com/) | 免费 | 40 万+ 真实 App UI 截图库，按模式/类别搜索 |
| 0b 学习 UX 交互模式 | [UI-Patterns.com](https://ui-patterns.com/) | 免费 | 经典 UI 设计模式参考库 |
| 0c 浏览最新设计趋势 | [Figma Resource Library](https://www.figma.com/resource-library/) | 免费 | 2026 Web 设计趋势 |
| 0d 看真实 UX flow | [UXArchive](https://uxarchive.com/) | 免费 | 真实 App 的完整用户流程截图 |

**关键动作**：遇到喜欢的界面，截图保存。这些截图会在 Phase 2-3 直接喂给 Claude Code。

### Phase 1：信息架构 & 站点地图

**目标**：确定"有哪些页面、页面之间什么关系"。

| 步骤 | 工具 | 成本 | 说明 |
|------|------|------|------|
| 1a 产品描述 → AI 生成站点结构 | Claude Code | 免费 | 告诉 Claude 产品定位、目标用户、核心功能，输出站点地图（JSON/Markdown） |
| 1b 可视化站点地图（可选） | [MockFlow](https://mockflow.com/ai/generate-sitemaps-with-ai/) 或 [FlowMapp](https://www.flowmapp.com/sitemap-generator) | 免费档 | AI 生成可编辑的视觉站点地图 |
| 1c 用户流程梳理 | Claude Code + Mermaid | 免费 | 生成 Mermaid flowchart，直接渲染用户旅程图 |

**实践建议**：个人开发者 1a + 1c 通常就够了。只有需要跟非技术人员沟通时才需要 MockFlow/FlowMapp 做可视化。

### Phase 2：交互设计 & 原型

**目标**：确定"每个页面长什么样、交互怎么走"。

分两个子阶段：Stitch 发散 → Pencil 收敛。

#### Phase 2a：发散探索 — Google Stitch

| 动作 | 说明 |
|------|------|
| 用自然语言/语音描述页面风格 | "vibe design" 核心能力，如 *"深色主题量化交易 Dashboard，左侧持仓列表，右侧 K 线图"* |
| 快速生成多版本文案 | 多 Agent 协作，几分钟出多个风格变体 |
| 导出 HTML/CSS/Tailwind/JSX | Stitch 2.0 导出质量不错，可直接作为参考或起手代码 |
| 一键导出到 Figma | 如需 Penpot/Figma 精修可走这条路 |

**Stitch 的价值**：零成本的快速发散工具，适合"这个页面应该长什么样"的探索阶段。

#### Phase 2b：精确设计与并行生成 — Pencil.dev

| 动作 | 说明 |
|------|------|
| 在 Cursor/VS Code 内打开 Pencil 画布 | 无需切换工具，设计就在代码旁边 |
| 6+ AI Agent 并行生成完整 flow | 一次出整个用户流程，不是逐屏设计 |
| MCP 协议让 Claude 直接读写 `.pen` 设计文件 | AI 理解设计意图，不是猜测 |
| 基于 Stitch 导出的 HTML/CSS 作为起手素材 | Stitch 发散 → Pencil 收敛 |
| Impeccable skill 约束设计质量 | 20 个设计命令在 Claude Code 内直接调优 |
| 截图分析提取 design token | MCP Market skills 从 UI 截图提取 token 和布局结构 |

**Pencil 的价值**：IDE 内的精确设计画布，消除 design handoff，design → code 零切换。

#### Phase 2 完整流程

```
产品需求 + 灵感截图
      │
      ▼
  Google Stitch ──→ 快速探索 3-5 个风格方向
      │                │
      │                ├─ 选定方向 A（导出 HTML/CSS/Tailwind）
      │                └─ 选定方向 B（导出到 Penpot 精修）
      │
      ▼
  Pencil.dev ──→ IDE 内精确设计
      │            │
      │            ├─ 6+ Agent 并行生成完整 user flow
      │            ├─ Claude Code 通过 MCP 直接操作设计
      │            └─ Impeccable 命令调优设计细节
      │
      ▼
  可运行的 HTML/React 原型 ──→ 浏览器验证
```

### Phase 3：设计系统 & Design Token

**目标**：建立单一事实来源，确保所有页面风格一致。

| 步骤 | 工具 | 成本 | 说明 |
|------|------|------|------|
| 3a 定义 design token（色彩、字体、间距、圆角、阴影…） | Claude Code | 免费 | 基于前几阶段积累的 token，输出结构化 JSON（W3C DTCG 格式） |
| 3b Token → 代码转换 | [Style Dictionary](https://github.com/style-dictionary/style-dictionary) | 开源免费 | 从 JSON token 自动生成 CSS variables、Tailwind config、任意平台代码 |
| 3b 备选：v0 Design System | [v0.app](https://v0.app/) | 免费档 | 可视化定义色彩/字体/样式，后续组件基于此生成 |
| 3c 注入 Claude Code 设计能力 | [Impeccable](https://impeccable.style/) | 开源免费 | CLAUDE.md skill，20 个设计命令 + 反模式 |
| 3d 可选：可视化设计工具 | [Penpot](https://penpot.app/) | 完全免费 | 开源 Figma 替代，SVG/HTML/CSS 原生格式，可自托管 |

#### Design Token 流转

```
Phase 2 截图提取的 token
        │
        ▼
  ┌─ tokens.json (W3C DTCG 格式，单一事实来源)
  │
  ├──→ Style Dictionary ──→ CSS custom properties
  ├──→ Style Dictionary ──→ Tailwind theme config
  ├──→ Style Dictionary ──→ React component props
  └──→ Impeccable skill ──→ Claude Code 设计约束
```

#### Pencil 补充价值

Pencil 的 `.pen` 开放格式天然就是设计文件，MCP 协议让 Claude 可以直接从中提取 design token，无需额外转换步骤。

### Phase 4：生产落地

**目标**：从原型到可部署的生产代码。

| 步骤 | 工具 | 成本 |
|------|------|------|
| 4a 组件库搭建 | Claude Code + shadcn/ui | 免费 |
| 4b 页面组装 | Claude Code（基于 Pencil 设计 + token） | 免费 |
| 4c 交互实现 | Claude Code | 免费 |
| 4d 响应式适配 | Claude Code | 免费 |
| 4e 可选：代码 → Figma | [Figma MCP Server](https://www.figma.com/blog/introducing-claude-code-to-figma/) | 免费 |

---

## 三、Claude Code Skills 生态补充

MCP Market (https://mcpmarket.com) 提供了丰富的 Claude Code skills，在链路中直接可用：

| Skill | 功能 | 链路位置 |
|-------|------|---------|
| [Screenshot Design Analyzer](https://mcpmarket.com/tools/skills/screenshot-design-analyzer) | 8 阶段系统化分析，从 UI 截图提取精确 design token、组件清单、布局结构 | Phase 2 |
| [Design System Architect](https://mcpmarket.com/tools/skills/design-system-architect-3) | 从截图自动生成 style guide + Tailwind token + React showcase app | Phase 2-3 |
| [Design Spec Extraction](https://mcpmarket.com/tools/skills/design-spec-extraction) | 从截图/Figma 导出生成 W3C DTCG 合规 JSON spec | Phase 3 |
| [UI Designer](https://mcpmarket.com/tools/skills/ui-designer-design-system-extractor) | UI 截图 → design system 提取 + PRD 生成 + React 组件实现 | Phase 2-4 |
| [UI Analyzer](https://mcpmarket.com/zh/tools/skills/ui-analyzer) | UI 截图 → production-ready React 组件 + Tailwind CSS | Phase 4 |
| [Screenshot to Task List](https://mcpmarket.com/tools/skills/screenshot-analyzer) | UI 截图 → 功能清单 + 开发 checklist | Phase 1 |

---

## 四、成本汇总

| 工具 | 成本 | 链路角色 |
|------|------|---------|
| Claude Code | 已有（$20/月） | 全链路核心 |
| Google Stitch | 完全免费 | Phase 2a 发散探索 |
| Pencil.dev | 完全免费 | Phase 2b IDE 内精确设计 |
| Impeccable | 开源免费 | 设计质量约束（全链路） |
| Style Dictionary | 开源免费 | Token 构建（Phase 3） |
| Mobbin | 免费 | 灵感参考（Phase 0） |
| UI-Patterns.com | 免费 | 交互模式参考（Phase 0） |
| UXArchive | 免费 | UX flow 参考（Phase 0） |
| Penpot | 完全免费 | 可选可视化设计（Phase 2d/3d） |
| v0 | 免费档 | 可选 Design System + 组件（Phase 3/4） |
| MockFlow | 免费档 | 可选可视化站点地图（Phase 1） |
| MCP Market Skills | 免费 | 截图分析（Phase 2-4） |

**全链路总成本：$0/月**（Claude Code 订阅除外）

---

## 五、补充工作流方案

### 工作流 A：「轻量级 Vibe Coding」— 快速验证、内部工具、MVP

```
构思 ──→ Lovable/Bolt.new ──→ 导出代码 ──→ Cursor 打磨 ──→ 部署
```

- 月费 $0-20，最快出活
- 适合内部管理后台、快速 MVP、简单数据看板
- 缺点：UI 容易"AI 味"重，设计一致性弱

### 工作流 B：「设计系统驱动 Vibe Coding」— 有品质要求的产品项目

```
构思 ──→ v0 定义 Design System ──→ v0 生成组件/页面 ──→ Cursor + Impeccable 打磨 ──→ 生产
```

- 月费 $20（v0），基于 shadcn/ui，代码所有权高
- 适合 C 端 SaaS、需要 brand consistency 的多页面应用
- 缺点：绑定 Vercel 生态

### 工作流 C（推荐）：「Claude Code 为中心的设计-开发一体化」

即本文档第二节的完整链路。Stitch 发散 + Pencil 收敛 + Impeccable 约束 + Style Dictionary 构建。全部免费。

---

## 六、参考来源

### 工具官网
- Google Stitch: https://stitch.withgoogle.com/
- Pencil.dev: https://pencil.dev/
- v0 (Vercel): https://v0.app/
- Lovable: https://lovable.dev/
- Bolt.new: https://bolt.new/
- Motiff: https://motiff.com/
- Impeccable: https://impeccable.style/
- Style Dictionary: https://github.com/style-dictionary/style-dictionary
- Penpot: https://penpot.app/
- Relume: https://www.relume.io/
- Magic Patterns: https://www.magicpatterns.com/
- Mobbin: https://mobbin.com/
- UI-Patterns: https://ui-patterns.com/
- UXArchive: https://uxarchive.com/
- Cursor: https://cursor.com/

### 深度文章
- [Lovable vs Bolt vs v0: AI App Builder Comparison](https://lovable.dev/guides/lovable-vs-bolt-vs-v0)
- [Best AI App Builder 2026: Lovable vs Bolt vs v0 vs Mocha](https://getmocha.com/blog/best-ai-app-builder-2026/)
- [Google Stitch vs v0 vs Lovable 2026](https://www.nxcode.io/resources/news/google-stitch-vs-v0-vs-lovable-ai-app-builder-2026)
- [Pencil.dev: The Missing Bridge Between Design and Code](https://pub.towardsai.net/pencil-dev-the-missing-bridge-between-design-and-code-that-developers-have-always-needed-760758438ca9)
- [Google Stitch Review 2026](https://www.index.dev/blog/google-stitch-ai-review-for-ui-designers)
- [Vibe Design, Voice Canvas & Free AI UI Tool (2026)](https://www.nxcode.io/resources/news/google-stitch-complete-guide-vibe-design-2026)
- [Vibe Coding: The Complete Guide 2026](https://www.rapidnative.com/blogs/vibe-coding-complete-guide)
- [Stitch and Pencil: Making "Design → Development" Actually Connect](https://medium.com/@keeponfirst/stitch-and-pencil-making-design-development-actually-connect-f174a4d38cd9)
- [Ultimate Design Workflow in 2026](https://medium.com/design-bootcamp/ultimate-design-workflow-in-2026-edbfd727ebbf)

### Claude Code Skills
- MCP Market: https://mcpmarket.com/
- Awesome Claude Skills: https://github.com/ComposioHQ/awesome-claude-skills
- Impeccable GitHub: https://github.com/pbakaus/impeccable
