---
name: ditto-design-cycle
description: Use when creating UI prototypes from blueprints, reviewing HTML prototypes or UI pages for visual quality, UX interaction, feature completeness, copy clarity, brand temperament, or information architecture. Supports --create mode (from blueprint to prototype), --create-all (batch Edition creation with style anchoring), --edition-review (Edition-level acceptance), --strict (contract failures block done), 6-role parallel review, autonomous iteration, and doc sync.
disable-model-invocation: false
---

# /ditto-design-cycle

UI 创建与设计审查编排。支持两种模式：**创建模式**（`--create`，基于产品架构产出物生成 UI 原型）和**审查模式**（对已有原型进行六角色并行审查）。聚焦设计交付物质量——UI 视觉、交互体验、功能可用性、界面语言、品牌气质、**信息效率**、**信息架构**，通过六角色并行审查识别冲突与共识，协商优化达成一致。支持 `--iterate` 自主迭代模式，设定评分目标后自动循环优化直到达标。

> **审查标准必须与产品定位匹配**，不使用通用 UI 准则。详见 [00_ditto_product_criteria.md](../../docs/designs/specs/00_ditto_product_criteria.md) 和 [review-scoring.md](../design-review/review-scoring.md)。
> 评分从 4 维度扩展为 5 维度（克制度/一致性/高级感/品牌方向/**信息效率**）。

## 核心理念

> **不是"对照 spec 打分"，而是"多角色专家讨论，共同优化设计"。**

- Design Spec 是**参考起点**，不是刚性约束
- 各角色可能给出**相互冲突的建议**（如 UI 想加大间距 vs 产品想增加信息密度）
- Claude 负责呈现冲突 + 分析权衡 + 推荐折中方案
- **用户是最终决策者**，选择采纳哪些建议
- 审查可能产生**新的设计决策**，自动记录到 `docs/designs/decisions/`
- 如果信息架构或交互流程有重大调整，同步更新 spec 文档

## --strict 模式

> **`--strict` 仅影响合同相关的 done 门禁（Step 12a/12c），不影响审查流程本身。**

| 行为 | 默认模式 | `--strict` |
|------|---------|------------|
| 合同创建失败（Step 12a） | WARNING，记录原因，不阻断 done | **BLOCK**，立即停止，不设置 status="done" |
| 合同验证失败（Step 12c） | 输出失败项，不阻断 done | **BLOCK**，立即停止，不设置 status="done" |

**使用场景**：
- `--create` / `--create-all`（exploration）：默认模式，合同失败不阻断，适合快速迭代
- `--create --strict` / `--create-all --strict`（acceptance）：合同失败阻断 done，适合正式交付前的验收

## Edition 机制

> **Edition** = 一个产品 UI 版本的全部页面原型集合，以 manifest 清单跟踪状态。

- **Manifest 文件**: `docs/designs/specs/prototypes/.edition-manifest.json`
- **版本标识**: manifest 中 `edition` 字段 + git tag `edition/<ver>/*`
- **页面状态**: `created` → `audit-passed` → `reviewed` → `needs-refinement` → `done`
- **风格锚点 (styleAnchor)**: 首个页面是基准，后续页面以上一个最高分 done 页面为参考
- **不引入 git worktree**：在当前分支操作，通过 manifest + tag 管理

---

## 规范参考

- **设计规范**: [docs/designs/specs/](../../docs/designs/specs/)（参考起点，非刚性约束）
- **Design Token**: [docs/designs/specs/prototypes/shared/tokens-base.css](../../docs/designs/specs/prototypes/shared/tokens-base.css) 及其 9 层体系
- **原型三区架构**: [docs/designs/specs/prototypes/shared/prototype-toggles.css](../../docs/designs/specs/prototypes/shared/prototype-toggles.css)（三区导航 / tab 面板 / gallery grid / state patterns）
- **设计决策**: [docs/designs/decisions/](../../docs/designs/decisions/)（**Art Director 刚性锚点** — 9 项关键决策定义了 Graphite Studio 的审美方向）
- **品牌 DNA**: Style B Graphite Studio — Linear/Vercel/Raycast 的克制感 + Bloomberg/quant desk 的专业终端感
- **架构规范**: [architecture.md](../rules/architecture.md)
- **零 Inline Style**: [no-inline-style.md](../rules/no-inline-style.md)（**P0 门禁** — `style="..."` 属性必须为零）

---

## 输入

`$ARGUMENTS` — 目标 + 可选参数

```bash
# === 创建模式（基于蓝图生成 UI 原型）===

# 从页面蓝图创建页面并审查迭代
/ditto-design-cycle page-markets.html --create --page markets

# 创建 + 自主迭代直到达标
/ditto-design-cycle page-markets.html --create --page markets --iterate --goal 8.0

# 创建 + strict 模式（合同失败阻断 done）
/ditto-design-cycle page-markets.html --create --page markets --strict

# === 审查模式（已有原型）===

# 全流程审查
/ditto-design-cycle docs/designs/specs/prototypes/page-cross-market.html

# 指定质量等级（默认 polished）
/ditto-design-cycle page-cross-market.html --level best

# 仅运行特定角色
/ditto-design-cycle page-cross-market.html --ui
/ditto-design-cycle page-cross-market.html --ux
/ditto-design-cycle page-cross-market.html --product
/ditto-design-cycle page-cross-market.html --ia
/ditto-design-cycle page-cross-market.html --copy
/ditto-design-cycle page-cross-market.html --ad

# 仅精修（跳过审查，直接应用 impeccable skills）
/ditto-design-cycle page-cross-market.html --polish

# 指定审查基准（对照某个原型版本）
/ditto-design-cycle page-cross-market.html --baseline prototype-v2.html

# 反向同步（验收后，将 review 变更写回设计文档）
/ditto-design-cycle page-cross-market.html --sync

# 自主迭代优化（目标气质 8.5，最多 3 轮，无需人工介入）
/ditto-design-cycle page-cross-market.html --iterate --goal 8.5 --max-rounds 3 --level best

# 自主迭代优化（使用默认值：目标 8.0，最多 3 轮）
/ditto-design-cycle page-cross-market.html --iterate

# 指定任务名（覆盖文件名自动映射）
/ditto-design-cycle page-cross-market.html --task cross-market-v2 --iterate

# 清理已完成任务的历史 tag
/ditto-design-cycle --cleanup cross-market

# === Edition 模式 ===

# 批量创建所有页面（基于蓝图，带 style anchoring）
/ditto-design-cycle --create-all

# 创建指定 Edition（默认 v1）
/ditto-design-cycle --create-all --edition v1

# 只创建特定页面（跳过已完成的）
/ditto-design-cycle --create-all --only markets,trading,research

# 带参考页面的单页创建（--create 的扩展，向后兼容）
/ditto-design-cycle page-markets.html --create --page markets --reference page-cross-market.html

# Edition 级验收（所有 done 页面的最终走查）
/ditto-design-cycle --edition-review

# 指定 Edition 验收
/ditto-design-cycle --edition-review --edition v1
```

---

## 原型版本管理（git tag）

> **每次 review 前，通过 git tag 快照当前状态。回退和对比均依赖 git 原生能力。**
> **Tag 按任务名分组，已完成任务可安全清理，不同任务互不干扰。**

### 任务名与 Tag 命名

- **Tag 格式**：`review/<task>/round-{N}`（按任务名分组，各任务独立递增）
- **完成标记**：`review/<task>/done`（达标后创建，含最终分数的 annotated tag）
- **任务名来源**：优先 `--task` 参数，否则从文件名自动映射
  - `page-cross-market.html` → `cross-market`
  - `page-home.html` → `home`
  - `page-market-pulse.html` → `market-pulse`

```
示例：
review/cross-market/round-1
review/cross-market/round-2
review/cross-market/done          ← 已达标
review/home/round-1               ← 不同任务，独立轮次
review/home/round-2
```

### 工作流

```
Phase 0: VERSION（在所有审查之前）

  1. 确定任务名
     ├─ 有 --task 参数 → 用参数值
     └─ 无 --task → 从文件名映射（去 page- 前缀和 .html 后缀）

  2. 检查任务状态
     ├─ git tag -l 'review/<task>/done' 存在 → 已完成任务
     │   ├─ [人工模式] 提示用户：任务已达标，是否重新迭代？
     │   └─ [--iterate] 自动提示选择：续接 / 新任务名 / 退出
     └─ 不存在 → 进行中或新任务

  3. 确定轮次号
     ├─ git tag -l 'review/<task>/round-*' 有结果
     │   └─ N = max(round-N) + 1
     └─ 无结果 → N = 1（新任务）

  4. git add 目标文件 → git commit -m "docs(review): <task> round-{N} pre-review snapshot"
  5. git tag review/<task>/round-{N}
  6. 后续所有修改直接在原文件上进行
```

### 回退操作

```bash
# 回退 cross-market 任务 round-2 的状态
git checkout review/cross-market/round-2 -- page-cross-market.html
```

### 版本对比

```bash
# 查看 cross-market 任务 round-1 → round-2 的变更
git diff review/cross-market/round-1..review/cross-market/round-2 -- page-cross-market.html

# 查看变更摘要
git log review/cross-market/round-1..review/cross-market/round-2 --oneline -- page-cross-market.html
```

### 任务完成与清理

```bash
# 达标后自动创建 done 标记（Phase 8 中执行）
git tag -a review/cross-market/done -m "task completed: score 8.8/10, 4 rounds"

# 手动清理已完成任务的所有 tag
git tag -l 'review/cross-market/*' | xargs git tag -d

# 或使用 --cleanup 参数
/ditto-design-cycle --cleanup cross-market
```

### 约束

- Tag 命名：`review/<task>/round-{N}`（按任务分组，各任务独立递增）
- 旧格式 `review/round-{N}` 视为 legacy，Phase 0 忽略，保留不动
- 活跃文件是唯一被 review 修改的文件
- 审查报告标注对应 tag，如 `Tag: review/cross-market/round-2`
- 不保存 HTML 副本、不自动截图到磁盘

---

## 多视口检测

> **所有涉及 HTML 原型的 review 必须在目标视口下验证内容完整性。** 默认审查视口 VP-STANDARD (1536x1080)，最小支持 VP-COMPACT (1366x768)。
>
> 详细视口矩阵、检测脚本、UX P0 规则见 [viewport.md](../design-review/viewport.md)。

---

## 六个审查角色

| 角色 | model | 核心关注 | 详情 |
|------|-------|---------|------|
| UI Designer | opus | Token 一致性、视觉层次、色彩排版 | [roles.md](../design-review/roles.md#ui-designer) |
| UX Reviewer | sonnet | 可用性、可访问性、交互流程 | [roles.md](../design-review/roles.md#ux-reviewer) |
| Product Mgr | sonnet | Spec 落地合规、重要性层级、交互意图、产品边界守卫 | [roles.md](../design-review/roles.md#product-manager) |
| IA Specialist | sonnet | 信息架构、用户流程、页面蓝图、标签体系 | [roles.md](../design-review/roles.md#ia-specialist) |
| Copy Editor | sonnet | 文案清晰度、语气一致、中文表达 | [roles.md](../design-review/roles.md#copy-editor) |
| Art Director | opus | 克制度、高级感、品牌方向锚定 | [roles.md](../design-review/roles.md#art-director) |

---

## 模型路由策略

> **质量优先**：审美判断和创意综合使用 Opus，结构化分析和机械操作使用 Sonnet。

| 阶段 | 模型 | 理由 |
|------|------|------|
| Phase 0: VERSION | sonnet | git 操作，纯机械 |
| Phase 0.5: CREATE [--create] | sonnet | 基于蓝图生成 UI 原型 |
| Phase 0.5: CREATE [--create-all] | sonnet | 循环调用单页 --create，带 style anchoring |
| Phase 1: BASELINE | sonnet | 数据采集 + 脚本执行 |
| Phase 2: CREATIVE DIRECTION | **opus** | 创意方向判断，策略选择和蓝图定义 |
| Phase 3: Art Director | **opus** | 审美判断核心，气质评分 |
| Phase 3: UI Designer | **opus** | 视觉品质需要审美理解 |
| Phase 3: UX Reviewer | sonnet | 交互分析偏结构化 |
| Phase 3: Product Mgr | sonnet | 功能可用性偏结构化 |
| Phase 3: IA Specialist | sonnet | 信息架构偏结构化 |
| Phase 3: Copy Editor | sonnet | 文案审查最结构化 |
| Phase 4: CONFLICT RES. | **opus** | 多角色冲突权衡取舍 |
| Phase 5: DECISION | sonnet | 呈现选项，不涉及判断 |
| Phase 6: FIX | sonnet | 按已定方案执行 |
| Phase 7: AD 预审/复审 | **opus** | 审美把关 |
| Phase 7: impeccable skills | sonnet | 按规范执行 |
| Phase 7: REFLECT [--iterate] | **opus** | 定性反思，洞察提取 |
| Phase 8: 自动化检测 | sonnet | Lighthouse/Token/视口 |
| Phase 8: 最终气质评分 | **opus** | 最终审美裁决 |
| Phase 9: SYNC | sonnet | 文档同步 |
| Edition Review [--edition-review] | sonnet | 截图采集 + image analysis，无创意判断 |

**实现方式**：Agent 工具调用时传入 `model` 参数，如 `Agent(prompt="...", model="opus")`。

---

## 质量等级

| 等级 | 标准 | 对应 impeccable skills |
|------|------|----------------------|
| **functional** | 正确渲染、可交互、无明显 bug、基本可访问 | — |
| **good** | Token 一致、响应式、布局合理、文案准确 | `normalize`, `arrange`, `clarify` |
| **polished** | 视觉层次清晰、节奏感、微交互、令人舒适 | + `colorize`, `typeset`, `animate` |
| **best** | 高级感、令人印象深刻、记忆点、业界领先 | + `bolder`, `delight`, `overdrive` |

默认等级：`polished`

---

## 自主迭代模式（`--iterate`）

> 自动循环**创意方向→审查→修复→评分→反思**，直到达标或达到上限。参数：`--goal`（默认 8.0）、`--max-rounds`（默认 3）。
> 每轮开始前 Art Director 定义创意蓝图（CREATIVE DIRECTION），每轮结束后输出结构化反思（REFLECT）。
> 循环架构、退出条件、AUTO-DECISION 规则、防震荡机制、**突破机制**详见 [iterate.md](../design-review/iterate.md)。
> **创意流程借鉴**：CREATIVE DIRECTION 从 [CREA 框架](https://crea-diffusion.github.io/)借鉴、REFLECT 从 [Reflexion 模式](https://arxiv.org/abs/2303.11366)借鉴、常态化标杆调研从 Design Harness 的 [Inspiration 层](https://agenticux.substack.com/p/between-uicrit-and-autoresearch-what)借鉴。

> **突破机制**: 当连续多轮收益递减（diminishing returns）时，不直接退出，而是触发「瓶颈诊断 → 策略转向 → 标杆调研 → 突破执行」流程。核心原则：**分数卡住的根源往往是优化维度本身已耗尽，需要换一个维度思考**。详见 [iterate.md §突破机制](../design-review/iterate.md#突破机制breakthrough-protocol)。

---

## 执行流程

### 全流程（默认，人工模式）

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: VERSION（git tag 快照）                    [sonnet] │
│                                                         │
│   1. 确定任务名（--task 参数 or 文件名映射）                │
│   2. 检查 review/<task>/done 是否存在 → 已完成则提示      │
│   3. git tag -l 'review/<task>/round-*' → 确定轮次号      │
│   4. git add 目标文件 → git commit                      │
│   5. git tag review/<task>/round-{N}                    │
│   6. 后续修改直接在原文件上进行                           │
├─────────────────────────────────────────────────────────┤
│ Phase 0.5: CREATE（全状态 UI 原型生成）      [--create] [sonnet] │
│                                                         │
│   仅在 --create 模式下执行。基于 product-arch 产出物     │
│   生成全状态 HTML 原型，然后进入正常审查流程。           │
│                                                         │
│   ⚠️ 核心原则：原型不是只渲染"默认态"，必须覆盖所有     │
│   可见 UI 状态（tab 面板、overlay、empty/loading/error）。│
│   CSS 切换系统：prototype-toggles.css（radio/checkbox/   │
│   details），详见 shared/prototype-toggles.css。          │
│                                                         │
│   1. 读取 product-arch 产出物                           │
│      ├─ 01_product_information_architecture.md           │
│      │   （页面角色、导航上下文、术语表）                  │
│      ├─ 02_core_page_blueprints.md                      │
│      │   （--page 指定页面：模块清单、优先级、交互设计、   │
│      │    tab 面板内容、overlay 注册表、组件×状态矩阵）   │
│      ├─ 04_interaction_state_spec.md                     │
│      │   （通用状态定义 + 页面状态映射，如有）            │
│      └─ 00_ditto_product_criteria.md                     │
│          （密度准则、字号映射、间距梯度）                  │
│   2. 读取 Design Token（tokens-style.css）               │
│   3. 读取设计决策（docs/designs/decisions/）             │
│   4. 读取 prototype-toggles.css（共享 CSS 切换系统）      │
│   5. [如 --reference <file>] 读取参考页面 HTML            │
│      ├─ 提取参考页面的视觉指纹和组件模式                  │
│      └─ 作为 impeccable:frontend-design 的 style reference│
│   6. 调用 impeccable:frontend-design 生成 HTML 原型      │
│      ├─ 传入蓝图中的模块清单和信息优先级                  │
│      ├─ 传入产品规格中的密度/字号/间距标准                 │
│      ├─ 传入品牌 DNA（Graphite Studio 风格）             │
│      └─ [如 --reference] 传入参考页面确保风格对齐         │
│                                                         │
│   ── 6b. [合同对接] data-contract-slot 注入 ──            │
│                                                         │
│   生成 HTML 时，必须为 #default-view 内主要布局区块       │
│   添加 data-contract-slot 属性，供 ditto-page-contract    │
│   --create 做确定性 selector 映射（避免 AI 猜测）。      │
│                                                         │
│   Shell 级区块（slots）—— 按页面 shellFamily 映射：      │
│   ├─ command-center: pulse / main / sidebar              │
│   ├─ analytical: strip / main / activity / analysis      │
│   ├─ catalog: toolbar / main / detail                    │
│   ├─ object-hub: meta / tabs / main / bottom             │
│   ├─ studio: source / main / inspector / logs / modes    │
│   ├─ ops-console: health / main / detail                 │
│   └─ radar: strip / main / right-rail / tab-band         │
│                                                         │
│   页面级区块（subSlots）—— 从蓝图核心模块清单推导：       │
│   ├─ 每个蓝图核心模块对应一个 data-contract-slot         │
│   ├─ 命名规则：kebab-case 英文名                          │
│   │   （如 decision-banner, priority-queue, scope-strip） │
│   └─ 与 data-component（gallery 分组用）不冲突            │
│                                                         │
│   示例（home 页面 #default-view）：                      │
│   <div class="shell-pulse" data-contract-slot="pulse">   │
│   <div class="shell-main" data-contract-slot="main">     │
│   <div class="shell-sidebar" data-contract-slot="sidebar">│
│   <div class="decision-banner"                           │
│        data-contract-slot="decision-banner">             │
│   <div class="panel-grow" data-contract-slot="priority-queue">│
│                                                         │
│   ⚠️ 注意：                                              │
│   - data-contract-slot 只加在 #default-view 内            │
│   - states-gallery 和 overlays-gallery 内不添加           │
│   - 不替代现有 class 名，是额外属性                       │
│                                                         │
│   ── 6a. 三区结构生成（CREATE 核心扩展）──                │
│                                                         │
│   原型采用三区 Hash 导航架构（借鉴 Figma frame +          │
│   Storybook 导航 + Design System 文档画廊）：             │
│   - Zone 1: default-view（纯净默认视图）                 │
│   - Zone 2: states-gallery（状态变体画廊）               │
│   - Zone 3: overlays-gallery（弹层设计画廊）             │
│                                                         │
│   HTML 骨架：                                           │
│   <input type="radio" id="view-default" name="proto-view" │
│          checked class="sr-only">                        │
│   <input type="radio" id="view-states" name="proto-view" │
│          class="sr-only">                                │
│   <input type="radio" id="view-overlays"                 │
│          name="proto-view" class="sr-only">              │
│   <nav class="proto-nav">...</nav>                       │
│   <section id="default-view" class="proto-section">...   │
│   <section id="states-gallery" class="proto-section">... │
│   <section id="overlays-gallery" class="proto-section">..│
│                                                         │
│   A. Zone 1: Default View（主视图）：                    │
│      ├─ 完整渲染页面默认状态，与生产环境一致              │
│      ├─ 不包含任何 state variant 或 overlay              │
│      ├─ Tab 面板（radio 切换）保留在此 zone：            │
│      │   ├─ 为蓝图定义的每个 tab 生成面板内容             │
│      │   ├─ 在 <style> 中添加 :has() 激活规则            │
│      │   └─ 蓝图内容不足时分级处理：                      │
│      │       ├─ 有子模块清单 → 按清单生成 mock 数据面板   │
│      │       ├─ 有标签名+上下文可推断 → 推理生成合理内容  │
│      │       └─ 仅有标签名无法推断 → 骨架占位             │
│      │           + 标注 <!-- ⚠️ 待 PM 定义 -->            │
│      └─ Tab 是页面功能导航，不是组件生命周期状态          │
│                                                         │
│   B. Zone 3: Overlays Gallery（弹层设计画廊）：          │
│      ├─ 所有弹层直接渲染在 .gallery-card 中              │
│      ├─ 无需 checkbox toggle，直接可见                   │
│      ├─ 蓝图有明确交互设计的（如 Order Confirmation）    │
│      │   → 全量渲染在 .gallery-card__preview--overlay 中  │
│      ├─ 表格行"查看详情"操作                             │
│      │   → 渲染通用 detail drawer，标注 [示意]            │
│      ├─ 破坏性操作（删除/取消）                          │
│      │   → 渲染通用 confirm dialog 模板                   │
│      └─ 每个 overlay card 含 label + trigger 描述        │
│                                                         │
│   C. Zone 2: States Gallery（状态变体画廊）：            │
│      ├─ 每个数据区块生成 empty/loading/error 三态         │
│      ├─ 按 .gallery-group[data-component] 分组           │
│      ├─ 每个状态用 .gallery-card 包裹：                  │
│      │   .gallery-card__label + .gallery-card__preview   │
│      └─ 使用 prototype-toggles.css 预设样式               │
│          （.state-empty / .state-loading / .state-error） │
│                                                         │
│   D. State Coverage Index 注入：                         │
│      ├─ 在 HTML 顶部注入机器可读注释块                   │
│      ├─ 列出所有 tab / overlay / state variant           │
│      ├─ [✓] 已渲染 / [ ] 未定义                          │
│      └─ Tab 面板必须全部 [✓]，不允许空壳                  │
│                                                         │
│   E. 三区 CSS 引用：                                     │
│      ├─ 在 <head> 中加载 prototype-toggles.css           │
│      ├─ View-level radio + proto-nav（zone 切换）        │
│      ├─ default-view 内保留 tab 切换（如蓝图有 tab）     │
│      └─ states-gallery / overlays-gallery 使用           │
│          gallery grid 样式                               │
│                                                         │
│   7. 写入目标文件                                        │
│   7a. [关键] 三区结构验证（CREATE 后必须执行 — 9 项）      │
│      ├─ 检查 1: section 标签平衡（open == close）          │
│      ├─ 检查 2: 无 HTML 实体转义（`&lt;` 不在标签位置）   │
│      ├─ 检查 3: overlay trigger 在 section 外（body 直系） │
│      ├─ 检查 4: overlay-backdrop 在 overlays-gallery 内    │
│      ├─ 检查 5: .gallery-grid 直接子元素只能是             │
│      │   .gallery-group 或 .gallery-card                  │
│      │   （禁止 main-content / activity-stack 等非 gallery │
│      │    元素嵌套在 gallery-grid 内）                     │
│      ├─ 检查 6: overlays-gallery 每个 card 含可渲染弹层    │
│      │   HTML（.overlay-sheet / .overlay-drawer 等），     │
│      │   不允许空预览区或纯占位文本                        │
│      ├─ 检查 7: states-gallery card 数量 ≥                 │
│      │   迁移前 state-variant 总数（迁移场景）             │
│      ├─ 检查 8: .overlay-backdrop computed display         │
│      │   必须为 none（页面样式不得覆盖隐藏规则）           │
│      └─ 检查 9: 全部用 DOM 解析器 / Playwright page.evaluate()
│          （禁止正则做 HTML 结构验证）                      │
│      ├─ 检查 10: #default-view 内 shell 级区块            │
│      │   （.shell-pulse / .shell-main / .shell-sidebar /  │
│      │   .shell-rail / .shell-header 等）必须有            │
│      │   data-contract-slot 属性                           │
│      │   （用 page.evaluate() 遍历 .shell-* 元素检查）     │
│   8. git add → commit → tag review/<task>/round-0        │
│                                                         │
│   ── --create-all 批量创建（Phase 0.5 循环变体）──       │
│                                                         │
│   触发条件: $ARGUMENTS 包含 --create-all                  │
│                                                         │
│   1. 读取页面蓝图（02_core_page_blueprints.md）           │
│      └─ 提取所有需要 HTML 原型的页面 + 优先级            │
│   2. 读取/创建 manifest（.edition-manifest.json）        │
│      ├─ 不存在 → 初始化 edition v1，status="creating"     │
│      └─ 已存在 → 跳过 status="done" 的页面               │
│   3. 按 --only 参数过滤（如有），否则按蓝图优先级排序     │
│   4. 逐页调用 impeccable:frontend-design：               │
│      ├─ 第一个页面：无 reference，是 Edition 风格基准      │
│      ├─ 后续页面：以 manifest 中最高分 done 页面为 anchor│
│      │   └─ 传入 anchor 页面 HTML 作为 --reference        │
│      ├─ 传入蓝图模块清单 + 产品规格 + 品牌 DNA           │
│      ├─ 执行步骤 6a 全状态生成（tab/overlay/state）      │
│      │   （详见上方 Phase 0.5 步骤 6a）                   │
│      ├─ 执行步骤 6b（data-contract-slot 注入）            │
│      │   （详见上方 Phase 0.5 步骤 6b）                   │
│      ├─ 写入目标文件 → 更新 manifest pages[]             │
│      └─ [门禁] 每页创建后立即执行步骤 7a（9 项检查）     │
│          ├─ 全部通过 → 继续下一页                        │
│          └─ 任一失败 → 阻断：记录失败页 + 失败项         │
│              → 修复后重新验证该页 → 通过后继续           │
│              → 3 次修复仍失败 → 暂停，输出诊断报告       │
│   5. [门禁] 批量后检查（所有页面创建完成后）：           │
│      ├─ A. 状态覆盖完整性审计：                          │
│      │   ├─ 每页 overlays-gallery 中 gallery-card 数量   │
│      │   │   vs 蓝图 overlay 注册表数量                   │
│      │   └─ states-gallery card 数量 vs 迁移前数量       │
│      ├─ B. CSS Token 存在性检查：                        │
│      │   ├─ 用 page.evaluate() 收集页面 var(--xxx) 引用│
│      │   └─ 对比 tokens-base.css 已定义变量              │
│      │       未定义 token → P0 阻断项                    │
│      ├─ C. 浏览器抽检（3-5 页：首 + 尾 + 随机中间页）：  │
│      │   ├─ navigate → 截图 default-view                │
│      │   ├─ 切 states-gallery → 截图                    │
│      │   └─ 切 overlays-gallery → 截图                  │
│      │   确认三区可切换、无白屏、无布局崩溃               │
│      └─ D. 阻断判定：                                   │
│          ├─ 0 阻断项 → 进入步骤 6                       │
│          └─ 有阻断 → 逐项修复 → 重跑 B+C               │
│              → 3 次仍存在 → 暂停，要求人工介入           │
│   6. 全部通过后：                                        │
│      ├─ manifest.status = "in-progress"                  │
│      ├─ git add → commit → tag edition/v1/created        │
│      └─ 输出创建摘要（页面数、anchor 链路、跳过列表、   │
│         批量后检查结果摘要）                              │
│   不做六角色审查——批量创建阶段只产出初始原型，            │
│   但必须通过步骤 4 per-page gate 和步骤 5 批量后检查。   │
├─────────────────────────────────────────────────────────┤
│ Phase 1: BASELINE（基线采集 + 跨页视觉指纹）        [sonnet] │
│                                                         │
│   1. 读取目标文件（HTML 原型或 React 组件）               │
│   2. 读取相关 spec 文档（作为参考）                        │
│   3. 读取 Design Token 定义                              │
│   4. 读取设计决策文档（Art Director 刚性锚点）            │
│   4a. 读取信息架构文档（IA Specialist 参考锚点）          │
│      ├─ 01_product_information_architecture.md           │
│      └─ 02_core_page_blueprints.md                        │
│   4b. [新增] 解析 State Coverage Index                   │
│      ├─ 提取 HTML 顶部的状态覆盖索引注释块               │
│      ├─ 统计 tab 面板覆盖数 / 总数                        │
│      ├─ 统计 overlay 覆盖数 / 总数                       │
│      ├─ 统计 state variant (empty/loading/error) 覆盖数   │
│      ├─ [三区格式] 检查 states-gallery 中 .gallery-card   │
│      │   数量和 label 是否匹配 State Coverage Index       │
│      ├─ 生成「状态覆盖率报告」作为 Phase 3 审查输入       │
│      └─ [旧格式] 标记为「旧格式原型，需迁移到三区结构」  │
│   5. Playwright: 启动浏览器（channel: 'chromium'）       │
│      └─ page.setViewportSize({ width: 1536, height: 1080})│
│   6. 三区截图策略（每个 zone 独立截图）：                 │
│      ├─ page.evaluate() → view-default radio checked      │
│      │   → 截图（默认 tab）                               │
│      ├─ 对 default-view 中每个 tab group:                 │
│      │   page.evaluate() → 点击 tab label → 截图         │
│      ├─ page.evaluate() → view-states radio checked       │
│      │   → 截图（状态画廊）                               │
│      └─ page.evaluate() → view-overlays radio checked     │
│          → 截图（弹层画廊）                               │
│   7. page.evaluate()（提取关键元素 computed styles）       │
│   8. [多视口] VP-STANDARD 内容溢出检测（详见 viewport.md） │
│   9. [多视口] VP-COMPACT (1366x768) 抽检                 │
│  10. [多视口] 恢复 VP-STANDARD，记录基线视口报告          │
│  10. [跨页] 结构化 metrics 提取 + 一致性基线：            │
│      ├─ 读取 manifest，确定需要采集的页面列表             │
│      │   └─ 遍历 manifest 中 status != "done" 的页面      │
│      │      （排除当前审查页）                             │
│      ├─ 对每个页面执行：                                  │
│      │   ├─ Playwright: setViewport(VP-STANDARD)          │
│      │   │   → navigate → page.evaluate()                │
│      │   └─ 提取结构化 metrics：                          │
│      │       shell: { railWidth, headerHeight,           │
│      │               mainPadding }                       │
│      │       components: { tableHeaderHeight[],           │
│      │       cardPadding[], badgeSize[], buttonHeight[] } │
│      │       typography: { h1:{size,weight}, h2:{...},    │
│      │       body:{...}, isUsingTokens:bool }             │
│      │       colors: { brandAccentCount,                  │
│      │       surfaceElevations[], functionalColorSet }    │
│      ├─ 比对所有页面 metrics，标记偏离值                  │
│      └─ 生成「跨页一致性基线报告」（结构化 JSON）         │
│         作为 Phase 3 各角色的审查输入                     │
├─────────────────────────────────────────────────────────┤
│ Phase 2: CREATIVE DIRECTION（创意蓝图）              [opus]  │
│                                                         │
│   ⚠️ 产品边界约束：                                      │
│   - 不得发明 spec 未定义的功能内容/模块/组件             │
│   - 视觉策略（间距、材质、动画、色彩）可自由提案         │
│   - 产品级变更（增删功能、调整模块内容/数据）必须标记    │
│     "⚠️ 需 PM 确认"并在 Phase 5 交由 PM 深度分析流程    │
│     裁定（低/中分歧自动裁决，高分歧 ESCALATE 给用户）    │
│                                                         │
│   1. 读取前轮评分快照和反思记录（首轮跳过）              │
│   2. 识别当前最低分维度和天花板维度                     │
│   3. 从策略矩阵选择本轮创意策略                        │
│   4. 轻量标杆调研（WebSearch 1-2 个参考）              │
│   5. 输出本轮创意蓝图（策略/区域/参考/预期/约束）      │
│      └─ 如含产品级变更 → 明确标注并附 spec 依据（如有）│
├─────────────────────────────────────────────────────────┤
│ Phase 3: PARALLEL REVIEW（并行审查）                      │
│                                                         │
│   启动 6 个并行 Agent，每个扮演一个角色：                   │
│   ├─ Art Director Agent  → opus  → 气质问题清单 + 评分卡 │
│   ├─ UI Designer Agent   → opus  → UI 问题清单           │
│   ├─ UX Reviewer Agent   → sonnet → UX 问题清单          │
│   ├─ Product Mgr Agent   → sonnet → spec 合规/层级验证/  │
│   │                               边界守卫/产品问题清单   │
│   ├─ IA Specialist Agent → sonnet → 信息架构 + 流程问题  │
│   └─ Copy Editor Agent   → sonnet → 文案问题清单         │
│                                                         │
│   每个角色的输出格式：                                    │
│   - 🔴 P0: 必须修复（阻断性问题）                         │
│   - 🟡 P1: 建议修复（影响体验）                           │
│   - 🟢 P2: 可选优化（锦上添花）                           │
│   - 💡 建议：对设计/信息架构的调整建议                     │
│                                                         │
│   ── Edition 增强：跨页一致性输入 ──                     │
│                                                         │
│   每个 Agent 的 prompt 追加（当 manifest 存在时）：       │
│   "## 跨页一致性基线                                     │
│    以下是本 Edition 已完成页面的结构化 metrics 对比。     │
│    请特别关注：与其他页面不一致的组件尺寸、               │
│    偏离 token 体系的硬编码值、与整体排版层级不符的字号。   │
│    {跨页一致性基线报告（Phase 1 Step 10 生成）}"           │
│                                                         │
│   ── 三区审查指引（当原型使用三区架构时）──              │
│                                                         │
│   各角色按 zone 分工审查：                               │
│   ├─ Zone 1 (default-view):                              │
│   │   ├─ UI Designer: 视觉品质主战场                     │
│   │   ├─ UX Reviewer: 交互流程主战场                     │
│   │   ├─ Product Mgr: 产品规格合规主战场                 │
│   │   ├─ IA Specialist: 信息架构主战场                   │
│   │   ├─ Copy Editor: 文案审查主战场                     │
│   │   └─ Art Director: 气质评分主战场                    │
│   ├─ Zone 2 (states-gallery):                            │
│   │   ├─ UI Designer: 卡片样式一致性                     │
│   │   ├─ UX Reviewer: empty state CTA / error 恢复路径   │
│   │   └─ Product Mgr: 状态覆盖完整性                     │
│   └─ Zone 3 (overlays-gallery):                          │
│       ├─ UX Reviewer: 弹层可用性                         │
│       ├─ Product Mgr: overlay 与蓝图定义一致性            │
│       └─ Art Director: 三区整体协调性                    │
│                                                         │
│   ── 状态覆盖完整度输入（Phase 4b 生成）──               │
│                                                         │
│   每个 Agent 的 prompt 追加（当状态覆盖率报告存在时）：   │
│   "## 状态覆盖完整度                                     │
│    以下是本原型的状态覆盖率报告（来自 Phase 1 Step 4b）。  │
│    三区架构：gallery-card 数量与 State Coverage Index 匹配。│
│    请在审查中额外关注：                                   │
│    - [ ] tab 面板是否全部渲染（不允许空壳 tab）           │
│    - [ ] overlay 画廊是否覆盖蓝图定义的所有弹层           │
│    - [ ] 状态画廊每个组件组是否包含完整的三态卡片          │
│    - [ ] State Coverage Index 标注 [✓] 的内容是否质量合格 │
│    - [ ] 标注 [⚠️ 待 PM 定义] 的内容是否需要产品确认      │
│    {状态覆盖率报告（Phase 1 Step 4b 生成）}"              │
├─────────────────────────────────────────────────────────┤
│ Phase 4: CONFLICT RESOLUTION（冲突协调）            [opus]  │
│                                                         │
│   1. 汇总 6 个角色的问题清单                              │
│   2. 去重合并相似问题                                     │
│   3. 识别角色间的冲突点                                   │
│   4. 为每个冲突提供分析 + 折中方案                        │
│   5. 识别所有角色的共识点                                 │
│   6. [--iterate] Art Director 为每个 P1 标注「预期提分」  │
│      用于后续 AUTO-DECISION 阶段的优先级排序              │
│   7. [--iterate] 标注每个变更与创意蓝图的方向对齐度      │
│                                                         │
│   双轨权威制冲突优先级规则：                              │
│                                                         │
│   ── 视觉决策轨（AD 最高）──                            │
│   ├─ AD vs UI（装饰 vs Token）→ AD 优先                  │
│   ├─ AD vs UX（affordance vs 高级感）→ UX 优先           │
│   │  （可访问性不妥协）                                  │
│   ├─ AD vs IA（信息密度 vs 克制留白）→ 协商，参考       │
│   │  00_ditto_product_criteria.md 的 L1/L2/L3 分层     │
│   └─ AD vs 所有（整体气质 vs 局部优化）→ AD 整体视角     │
│     优先                                                │
│                                                         │
│   ── 产品决策轨（PM 最高）──                            │
│   ├─ PM vs AD（产品内容 vs 视觉表达）→ PM 定义内容边界，  │
│   │  AD 决定视觉实现方式                                │
│   ├─ PM vs IA（功能范围 vs 信息结构）→ PM 定范围，      │
│   │  IA 定组织结构                                      │
│   ├─ PM vs UX（功能完整 vs 交互简化）→ PM 裁定功能必要性│
│   ├─ 任何角色 vs PM（涉及产品功能/内容）→ PM 一票否决    │
│   └─ 高分歧 C 类变更 → PM 深度分析流程                  │
│      ├─ 低/中分歧 → PM 自行裁决                        │
│      └─ 高分歧 → 先执行 PM 推荐（待确认）+ ESCALATE     │
│                                                         │
│   ── 信息架构决策轨（IA 最高）──                        │
│   ├─ IA vs UX（信息分组 vs 交互路径）→ 先 IA 定结构，   │
│   │  再 UX 审交互                                      │
│   └─ IA vs AD（信息架构 vs 视觉留白）→ 协商            │
├─────────────────────────────────────────────────────────┤
│ Phase 5: DECISION（用户决策 / AUTO-DECISION）      [sonnet] │
│                                                         │
│   产品边界分类（每个变更必须归类）：                       │
│   ├─ A 类：视觉微调（间距/材质/动画/色彩调整）           │
│   │  → AUTO by AD（Art Director 自动裁定）               │
│   ├─ B 类：spec 内产品微调（调整优先级/布局/交互方式，    │
│   │  spec 有明确定义）→ AUTO by PM（需 Phase 3 PM        │
│   │  Agent 确认在 spec 范围内）                          │
│   └─ C 类：超出 spec / 重大战略变更                      │
│      ├─ 新增 spec 未定义的功能/模块/内容                 │
│      ├─ 删除 spec 中定义的功能                           │
│      └─ PM 无法权衡的大方向产品决策                      │
│      → PM 深度分析流程（详见 iterate.md）                │
│                                                         │
│   PM 深度分析流程（C 类处理）：                           │
│   ├─ Step 1: 分歧评估 → 低/中/高                       │
│   ├─ Step 2: 业界调研（WebSearch 2-3 标杆）             │
│   ├─ Step 3: 调研能解决 → PM 自动裁决                  │
│   └─ Step 4: 分歧等级裁决                               │
│       ├─ 低/中分歧 → PM 裁决 + 记录分析                │
│       └─ 高分歧 → 先执行 PM 推荐（标记待确认）           │
│                + ESCALATE 结构化分析给用户               │
│                                                         │
│   [--iterate] AUTO-DECISION：                            │
│   ├─ A/B 类变更 → 按权威轨自动裁决（AD/PM）              │
│   ├─ C 类变更 → PM 深度分析（见上）                      │
│   └─ 详见 iterate.md AUTO-DECISION 规则                  │
│                                                         │
│   [--人工] 使用 AskUserQuestion 呈现：                   │
│   ├─ 共识点（所有角色一致认同，建议直接采纳）               │
│   ├─ 冲突点（角色意见不一致，附分析 + 折中方案）            │
│   ├─ 各角色独立建议（可选择性采纳）                         │
│   ├─ 信息架构/交互流程的重大调整建议                        │
│   └─ [如有 ESCALATE] 结构化分歧分析（见 templates.md）     │
│   [--人工] 用户选择：采纳 / 否决 / 替代方案               │
├─────────────────────────────────────────────────────────┤
│ Phase 6: FIX（执行修改）                            [sonnet] │
│                                                         │
│   1. 按优先级执行采纳的修改                               │
│   2. 需要验证时用 Playwright page.evaluate() 提取关键 computed styles
│      或直接在浏览器肉眼确认（不保存截图到磁盘）            │
│   3. 如有信息架构调整，更新 spec 文档                     │
│   4. 如有新的设计决策，记录到 decisions/                   │
├─────────────────────────────────────────────────────────┤
│ Phase 7: POLISH（质量提升 + Art Director 审批）     [混合]   │
│                                                         │
│   Step 1: Art Director 预审 FIX 结果              [opus]  │
│   ├─ 气质评分 ≥ 7.5 → 允许进入 POLISH                   │
│   └─ 气质评分 < 7.5 → 先修正气质问题，再进入 POLISH      │
│                                                         │
│   Step 2: 应用 impeccable skills                  [sonnet] │
│   - good:     normalize → arrange → clarify              │
│   - polished: + colorize → typeset → animate             │
│   - best:     + bolder → delight → overdrive             │
│                                                         │
│   Step 3: Art Director 复审 POLISH 结果           [opus]  │
│   ├─ 可降级过度的 bolder/delight/overdrive 效果          │
│   ├─ 可移除违反克制度的装饰元素                           │
│   ├─ 使用 impeccable: quieter 处理过度装饰                │
│   └─ 输出气质评分卡                                     │
│                                                         │
│   [--iterate] Step 4: REFLECT 反思记录            [opus]  │
│   ├─ 记录本轮创意策略与实际执行的偏差                    │
│   ├─ 记录关键洞察（什么起作用/什么没起作用）             │
│   └─ 标记死胡同 + 可探索方向                            │
├─────────────────────────────────────────────────────────┤
│ Phase 8: FINAL（最终验证 + 气质评分）               [混合]   │
│                                                         │
│   1. [门禁] 零 Inline Style 验证：                     │
│      ├─ grep 所有 style="..." 属性（排除 CSS 注释）     │
│      ├─ 命中数 > 0 → P0 级阻断，不进入后续步骤         │
│      └─ 修复方式：替换为 CSS class（详见 no-inline-style.md）│
│   2. Playwright: lighthouse_audit（质量评分）    [sonnet] │
│   3. Playwright: page.evaluate()（最终 Token 审计）[sonnet]│
│   3a. [门禁] 三区结构完整性验证（复用步骤 7a 的 9 项检查）│
│       ├─ section 平衡 / grid 直接子元素 / overlay 完整性  │
│       ├─ state-variant 覆盖率对比蓝图                    │
│       └─ 任一检查失败 → P0 级阻断，不进入 AD 气质评分    │
│   3. [多视口] VP-STANDARD 完整性验证              [sonnet] │
│      ├─ 内容无截断，底部元素完全可见                     │
│      └─ sticky 元素（rail/header/context-bar）正常工作    │
│   4. [多视口] VP-COMPACT (1366x768) 完整性验证   [sonnet] │
│      ├─ 可滚动到底部，底部内容完全可见                   │
│      └─ 布局无破坏                                       │
│   5. [多视口] 输出视口验证报告                   [sonnet] │
│   6. Art Director 最终气质评估：                   [opus]  │
│      ├─ 重新提取视觉指纹，对比 Phase 1 基线               │
│      ├─ 输出气质评分卡（克制度/一致性/高级感/品牌方向/信息效率）│
│      └─ 跨页一致性验证（对比其他页面视觉指纹）            │
│  11. [--iterate] 汇总所有轮次反思记录到最终报告          │
│   7. git commit 最终状态                                 │
│   8. [--iterate 达标] 创建 done 标记：                      │
│      git tag -a review/<task>/done -m                      │
│        "task completed: score {X}/10, {N} rounds"          │
│   9. 生成审查报告 → docs/reviews/（含 tag 引用）          │
│  10. 更新 design decisions（如有架构调整）                 │
│  11. 生成待同步清单（嵌入报告末尾）                       │
│  12. [Edition 增强] 如 manifest 存在：                   │
│                                                         │
│  12a. [合同桥接] 在设置 status="done" 之前，先触发       │
│       页面合同创建：                                     │
│      ├─ 确认 manifest 中该页面当前 status === "reviewed"  │
│      ├─ 调用 /ditto-page-contract --create <page-id>      │
│      │   （此时 status 仍为 "reviewed"，满足前置条件）    │
│      ├─ 合同创建成功 → 继续步骤 12b                      │
│      ├─ 合同创建失败 →                                   │
│      │   ├─ 默认模式：WARNING，记录原因，不阻断 done       │
│      │   └─ --strict 模式：BLOCK，立即停止，不设置 done   │
│      │   ├─ 缺少 Page Contract Mapping（蓝图未更新）     │
│      │   │   → 提示运行 ditto-product-arch --iterate      │
│      │   │     blueprint --page <page-id>                 │
│      │   └─ prototype 探测失败 → 记录详情                 │
│      └─ 如 docs/contracts/pages/<page>.contract.json     │
│          已存在 → 提示确认覆盖                            │
│                                                         │
│  12b. [状态推进] 设置页面完成状态：                      │
│      ├─ 更新对应 page 的 {status:"done", score, rounds}  │
│      ├─ 如所有页面 status="done"                          │
│      │   → manifest.status = "reviewing"                 │
│      └─ 写入 .edition-manifest.json → git add             │
│                                                         │
│  12c. [合同验证] 合同创建成功后自动验证：                 │
│      ├─ 调用 /ditto-page-contract --validate <page-id>    │
│      ├─ 验证全绿 → 输出 "Contract draft ready"           │
│      └─ 验证失败 →                                       │
│          ├─ 默认模式：输出失败项，不阻断 done 流程        │
│          │   （用户可后续手动 --validate + --promote）     │
│          └─ --strict 模式：BLOCK，立即停止，不设置 done   │
│  13. [布局 bug 检测 — 仅 iterate 最后一轮或              │
│      edition-review 时执行完整分析]                       │
│      ├─ take_screenshot（VP-STANDARD, fullPage）          │
│      ├─ analyze_image 检测：                             │
│      │   内容溢出/截断 / 元素重叠/遮挡                   │
│      │   对齐偏移 / 留白异常                              │
│      └─ page.evaluate() 交叉验证：                       │
│          ├─ scrollHeight > clientHeight → 溢出确认        │
│          └─ getBoundingClientRect() → 偏移量化             │
├─────────────────────────────────────────────────────────┤
│ Phase 9: SYNC（反向同步，独立触发）                 [sonnet] │
│                                                         │
│   触发: /ditto-design-cycle <file> --sync              │
│   详情见 [sync.md](../design-review/sync.md)             │
└─────────────────────────────────────────────────────────┘
```

### Edition 级验收

```
┌─────────────────────────────────────────────────────────┐
│ Edition Review                              [--edition-review] [混合] │
│                                                         │
│   1. 读取 manifest，获取所有 status="done" 的页面       │
│   2. 逐页使用 Playwright 打开：                        │
│      ├─ page.setViewportSize(1536x1080)                │
│      ├─ navigate → page.screenshot({ fullPage: true }) │
│      └─ analyze_image 检测：                          │
│          ├─ 布局 bug（溢出、截断、重叠）               │
│          ├─ 风格偏差（与 Edition 整体不一致的元素）     │
│          └─ 排版问题（字号层级混乱、间距异常）          │
│   3. 生成 Edition 级验收报告                           │
│      ├─ 逐页截图 + 问题标记                            │
│      ├─ 跨页一致性摘要                                │
│      └─ 只标记 P0/P1 问题，不跑完整六角色审查          │
│   4. 更新 manifest：                                   │
│      ├─ crossPageAudit.lastRun / issues                │
│      └─ 如无 P0 → manifest.status = "reviewed"        │
│   5. git commit + tag edition/v1/reviewed             │
│   6. 如有 P0 问题 → 逐页运行审查修复                   │
│   7. 修复后 tag edition/v1/final                      │
└─────────────────────────────────────────────────────────┘
```

### 单角色审查

使用 `--ui` / `--ux` / `--product` / `--ia` / `--copy` / `--ad` 参数时，只运行对应角色的审查，跳过冲突协调和全流程。

```
BASELINE [sonnet] → 单角色审查 [按角色分配] → DECISION [sonnet] → FIX [sonnet] → VERIFY [sonnet]
```

**单角色模型分配：**
| 参数 | 角色 | model | 理由 |
|------|------|-------|------|
| `--ui` | UI Designer | opus | 视觉品质需要审美判断 |
| `--ux` | UX Reviewer | sonnet | 交互分析偏结构化 |
| `--product` | Product Mgr | sonnet | 功能可用性偏结构化 |
| `--ia` | IA Specialist | sonnet | 信息架构偏结构化 |
| `--copy` | Copy Editor | sonnet | 文案审查最结构化 |
| `--ad` | Art Director | opus | 审美判断核心 |

### 仅精修模式

使用 `--polish` 参数时，跳过审查，直接按质量等级应用 impeccable skills。

```
BASELINE [sonnet] → POLISH [混合] → VERIFY [sonnet] → FINAL [混合]
```

---

## 输出模板

> Agent 输出格式、冲突协调格式、最终报告模板见 [templates.md](../design-review/templates.md)。
