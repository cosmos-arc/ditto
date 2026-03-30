# Claude Code 前端开发工作流设计

> 日期：2026-03-29
> 状态：已确认

## 概述

基于对 Claude Code 官方文档、社区最佳实践、Blog 文章的全面调研，结合 Ditto App 项目现状，设计从 UI 设计意图到前端代码落地的完整工作流。

**核心决策：**
- 设计到代码：**强化 Spec 驱动**（不引入 Figma MCP）
- 端到端验证：**渐进式**（先用好 Chrome DevTools MCP，后续再考虑 Playwright）
- 原型工具：**继续 HTML 原型**（当前阶段不引入 Storybook）

---

## 全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Ditto App — Claude Code 工作流 v1                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ① 设计意图          ② Design Spec          ③ HTML 原型              │
│  ┌──────────────┐   ┌──────────────┐      ┌──────────────┐         │
│  │ brainstorming│ → │ 信息架构      │  →   │ HTML + Token │         │
│  │ impeccable:  │   │ 页面蓝图      │      │ 原型生成      │         │
│  │ critique     │   │ 组件规范      │      │              │         │
│  │ ui-ux-pro-max│   │ Design Token │      │              │         │
│  └──────────────┘   └──────────────┘      └──────┬───────┘         │
│                                                 │                  │
│                           ┌─────────────────────┘                  │
│                           ▼                                        │
│  ⑥ 部署          ⑤ 代码审查       ④ 原型精修 → 编码实现              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐       │
│  │ finishing a  │←│ requesting   │←│ Chrome MCP 自动截图    │       │
│  │ dev branch   │ │ code review  │ │ evaluate_script 审计  │       │
│  │ PR → merge   │ │ impeccable:  │ │ TDD: test → impl     │       │
│  │              │ │ normalize    │ │ impeccable: polish   │       │
│  └──────────────┘ └──────────────┘ └──────────────────────┘       │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  基础设施                                                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
│  │ CLAUDE.md  │ │ Hooks      │ │ Skills     │ │ MCPs       │      │
│  │ + rules/   │ │ fe_gate.sh │ │ superpowers│ │ Chrome     │      │
│  │ 三条铁律    │ │ fe_after_  │ │ impeccable │ │ DevTools   │      │
│  │            │ │ write.sh   │ │ ui-ux-pro  │ │ Web Search │      │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 阶段详解

### 阶段 ①：设计意图（Brainstorming）

**目标：** 把模糊的想法变成清晰的设计方向

**使用的 Skills：**

| Skill | 作用 | 触发时机 |
|-------|------|---------|
| `superpowers:brainstorming` | 协作式需求探索，逐步细化 | 新功能/创意性工作开始时 |
| `impeccable:critique` | 从 UX 角度评估设计方向 | 设计方案初稿完成后 |
| `ui-ux-pro-max` | UI/UX 设计智能（50+ 风格、161 色板、57 字体配对） | 需要设计灵感时 |

**产出物：**
- `docs/designs/decisions/YYYY-MM-DD-*.md` — 关键设计决策记录

---

### 阶段 ②：Design Spec（设计规范）

**目标：** 把设计方向转化为 Claude 可执行的结构化规范

**使用的 Skills：**

| Skill | 作用 | 触发时机 |
|-------|------|---------|
| `superpowers:writing-plans` | 将 spec 转化为实施计划 | spec 编写完成后 |
| `impeccable:normalize` | 审计 UI 一致性，对齐 design system | spec 审查时 |
| `impeccable:typeset` | 优化字体/排版规范 | 涉及文字排版时 |

**Spec 格式增强建议：** 在组件描述中加入可机器读取的结构化映射：

```markdown
### HeroBanner 组件
- **布局**: 全宽，max-width 1280px 居中
- **背景**: 渐变 from-ditto-bg-gradient-start to-ditto-bg-gradient-end
- **Token 映射**: bg → ditto-bg-surface, text → ditto-fg-primary
- **组件依赖**: Button(shadcn), Container
- **响应式断点**: sm: 单列, md+: 双列
- **动画**: entrance fadeInUp 300ms
- **可访问性**: h1 标题, aria-label for CTA
```

**产出物：**
```
docs/designs/specs/
├── 01_product_information_architecture.md
├── 02_core_page_blueprints.md
├── 10_ditto_shell_family_spec.md
├── 11_ditto_page_pattern_library.md
└── 13_ditto_component_spec.md
```

---

### 阶段 ③：HTML 原型（Prototyping）

**目标：** 快速验证设计方向，低成本试错

**使用的 Skills/MCP：**

| 工具 | 作用 |
|------|------|
| `frontend-design` / `impeccable:frontend-design` | 确保视觉品质 |
| `impeccable:arrange` | 优化布局/间距/视觉节奏 |
| `impeccable:colorize` | 添加策略性色彩 |
| `impeccable:bolder` | 增强视觉冲击（如果原型太保守） |
| Chrome DevTools MCP `take_screenshot` | 实时预览原型效果 |
| Chrome DevTools MCP `evaluate_script` | 提取 computed styles 对比 spec |

**当前原型架构（已验证可行）：**
```
docs/designs/specs/prototypes/
├── shared/
│   ├── tokens-base.css          # Layer 1: 物理原语
│   ├── tokens-semantic.css      # Layer 2: 语义映射
│   ├── tokens-domain.css        # Layer 3: 领域语义
│   ├── tokens-interaction.css   # Layer 4: 交互状态
│   ├── tokens-density.css       # Layer 5: 密度变体
│   ├── layout-base.css          # 基础布局
│   └── mock-data.js             # 模拟数据
└── style-b-graphite-studio/
    ├── tokens-style.css         # Style B 特定 token
    ├── index.html               # 密度对比导航
    ├── prototype-dense.html     # Dense 变体
    ├── prototype-compact.html   # Compact 变体
    ├── prototype-comfortable.html # Comfortable 变体
    └── page-*.html              # 各页面原型
```

**关于 Storybook 的决策：** 当前阶段不引入。理由：
- HTML 原型 + 分层 Token 系统已接近 Storybook 核心理念
- 当前在做页面级设计探索，非组件库建设
- 最佳引入时机：从原型转为生产代码时，在 React + shadcn 体系中引入

---

### 阶段 ④：原型精修 → 编码实现

**目标：** 将验证过的原型转化为生产级 React 组件

**核心改进：建立"原型自审循环"**

```
改完原型 HTML 后，自动执行：
  ① take_screenshot → 看整体布局
  ② evaluate_script → 提取关键元素的 computed styles
  ③ 对比 tokens-style.css 中的设计规范
  ④ 自动报告不一致的地方
  ⑤ 只把"需要人工判断"的决策交给用户
```

**使用的 Skills（按顺序）：**

| 顺序 | Skill | 作用 |
|------|-------|------|
| 1 | `superpowers:writing-plans` | 将 spec + 原型转化为分步实施计划 |
| 2 | `superpowers:test-driven-development` | TDD 流程：先写测试再写实现 |
| 3 | `superpowers:executing-plans` | 按计划逐步执行 |
| 4 | `frontend-design` / `impeccable:frontend-design` | 确保视觉品质不降级 |
| 5 | Chrome DevTools MCP | 实时验证编码结果 |

**TDD 子流程：**
```
1. RED：根据 spec 写组件测试（渲染、交互、响应式）
2. GREEN：写最小实现让测试通过
3. REFACTOR：优化代码结构
4. VISUAL CHECK：Chrome DevTools MCP 截图 → 对比原型
5. TOKEN CHECK：evaluate_script 提取样式 → 对比 Design Token
6. REPEAT：下一个组件
```

---

### 阶段 ⑤：代码审查（Code Review）

**目标：** 确保代码质量和一致性

**使用的 Skills：**

| Skill | 作用 |
|-------|------|
| `superpowers:requesting-code-review` | 生成结构化审查请求 |
| `code-review` | PR 级别代码审查 |
| `impeccable:normalize` | 检查 UI 与 design system 的一致性 |

---

### 阶段 ⑥：验证与部署（Verify & Ship）

**目标：** 确保质量后交付

**验证分层（渐进式引入）：**

```
现在（Phase 1）：
  ✅ Vitest + RTL（单元/集成测试）
  ✅ Chrome DevTools MCP（实时视觉反馈）
  ✅ Lighthouse audit（质量评分）
  ✅ fe_gate.sh Hook（门禁）

后续（Phase 2，按需引入）：
  🔲 Playwright（关键路径 E2E 测试）
  🔲 Chromatic（视觉回归测试）
```

**使用的 Skills：**

| Skill | 作用 |
|-------|------|
| `superpowers:verification-before-completion` | 完成前强制验证 |
| `impeccable:audit` | 技术质量检查（a11y、performance、theming） |
| `superpowers:finishing-a-development-branch` | 分支完成流程 |

---

## 基础设施

### 当前已配置

| 类别 | 工具 | 状态 |
|------|------|------|
| 项目规范 | CLAUDE.md + .claude/rules/ | ✅ 已配置 |
| Hooks | fe_gate.sh（Stop 门禁）+ fe_after_write.sh（Write/Edit 后） | ✅ 已配置 |
| Skills | superpowers + impeccable + ui-ux-pro-max + code-review + frontend-design | ✅ 已启用 |
| MCP | Chrome DevTools + Web Search + 4.5v Vision | ✅ 已连接 |

### 待建设

| 类别 | 工具 | 优先级 |
|------|------|--------|
| 原型自审 | Chrome MCP 自动截图 + evaluate_script Token 审计 | 高 |
| Spec 增强 | 结构化组件描述格式（Token 映射） | 中 |
| E2E 测试 | Playwright（关键路径） | 低（Phase 2） |

---

## 核心编排 Skill: /ditto-design-review

**新增机制：** 多角色产品级审查编排 Skill，覆盖设计 → 原型 → 审计 → 精修 → 完成。

详细设计见 [ditto-design-review.md](../../.claude/commands/ditto-design-review.md)

### 四个审查角色

| 角色 | 关注维度 | 关键工具 |
|------|---------|---------|
| UI Designer | 视觉品质 / Token 一致性 / 布局节奏 / 色彩 / 字体 | Chrome MCP 截图 + evaluate_script + impeccable:normalize |
| UX Reviewer | 可用性 / 可访问性 / 交互流程 / 信息架构 | impeccable:critique + impeccable:audit + lighthouse_audit |
| Product Manager | 功能完整性 / 用户场景 / 优先级 / 信息密度 | ui-ux-pro-max + spec 文档对比 |
| Copy Editor | 文案清晰度 / 语气一致性 / 标签准确性 | impeccable:clarify |

### 核心理念

> 不是"对照 spec 打分"，而是"多角色专家讨论，共同优化设计"。
> Spec 是参考起点，不是刚性约束。各方可能给出冲突建议，通过协商达成一致。

### 四个质量等级

| 等级 | 标准 |
|------|------|
| functional | 正确渲染、可交互、无 bug |
| good | Token 一致、响应式、布局合理 |
| polished | 视觉层次清晰、节奏感、微交互（默认） |
| best | 高级感、令人印象深刻、业界领先 |

### 用法

```bash
/ditto-design-review <target>                    # 全流程审查
/ditto-design-review <target> --ui --ux          # 指定角色
/ditto-design-review <target> --polish           # 仅精修
/ditto-design-review <target> --level best       # 指定质量等级
```

---

## Skill/MCP 矩阵

| 阶段 | Skills | MCP | 产出物 |
|------|--------|-----|--------|
| 设计意图 | brainstorming, impeccable:critique, ui-ux-pro-max | — | decisions/*.md |
| Design Spec | writing-plans, impeccable:normalize, impeccable:typeset | — | specs/*.md |
| HTML 原型 | frontend-design, impeccable:arrange, impeccable:colorize | Chrome DevTools | prototypes/**/*.html |
| 原型精修 | impeccable:polish, impeccable:bolder | Chrome DevTools + evaluate_script | 精修后的原型 |
| 编码实现 | test-driven-development, executing-plans | Chrome DevTools | src/features/**/*.tsx |
| 验证 | verification-before-completion, impeccable:audit | Chrome DevTools + Lighthouse | 通过的测试 |
| 代码审查 | requesting-code-review, code-review | — | 审查报告 |
| 部署 | finishing-a-development-branch | — | PR → merge |

---

## 参考资料

- [Anthropic Blog: Improving Frontend Design Through Skills](https://claude.com/blog/improving-frontend-design-through-skills)
- [Claude Code Docs: Skills](https://code.claude.com/docs/en/skills)
- [Claude Code Docs: Common Workflows](https://code.claude.com/docs/en/common-workflows)
- [Figma MCP + Claude Code](https://www.figma.com/blog/introducing-claude-code-to-figma/)
- [Builder.io: Claude Code + Figma MCP Server](https://www.builder.io/blog/claude-code-figma-mcp-server)
- [Tailkits: How Claude Skills Improve Your Frontend Workflow](https://tailkits.com/blog/claude-skills-ui-design-web-development/)
- [Reddit: Best practices on Claude Code frontend workflow](https://www.reddit.com/r/ClaudeCode/comments/1m97vuu/best_practices_on_claude_code_frontend_workflow/)
- [aiorg.dev: Claude Code Best Practices 2026](https://aiorg.dev/blog/claude-code-best-practices)
- [PixelMojo: Claude Code Hooks Reference 2026](https://www.pixelmojo.io/blogs/claude-code-hooks-production-quality-ci-cd-patterns)
- [Snyk: Top 8 Claude Skills for Developers](https://snyk.io/articles/top-claude-skills-developers/)
