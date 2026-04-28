# Phase 0.5: CREATE（全状态 UI 原型生成）

> **核心原则**: 原型不是只渲染"默认态"，必须覆盖所有可见 UI 状态（tab 面板、overlay、empty/loading/error）。
> CSS 切换系统：prototype-toggles.css（radio/checkbox/details），详见 shared/prototype-toggles.css。

---

## 触发条件

`$ARGUMENTS` 包含 `--create` 参数。

---

## 步骤

### 1. 读取上游产出物

| 文件 | 内容 |
|------|------|
| 01_product_information_architecture.md | 页面角色、导航上下文、术语表 |
| 02_core_page_blueprints.md | --page 指定页面：模块清单、优先级、交互设计、tab 面板内容、overlay 注册表、组件×状态矩阵 |
| 04_interaction_state_spec.md | 通用状态定义 + 页面状态映射（如有） |
| 00_ditto_product_criteria.md | 密度准则、字号映射、间距梯度 |

### 2. 读取 Design Token

| 文件 | 内容 |
|------|------|
| `DESIGN.md` | AI 设计系统描述（结构化 YAML + 设计原则） |
| `src/styles/design-tokens/tokens-*.css` | Token SSOT（9 个文件） |

### 3. 读取设计决策（docs/designs/decisions/）

### 4. 读取 prototype-toggles.css（共享 CSS 切换系统）

### 5. [如 --reference <file>] 读取参考页面 HTML

- 提取参考页面的视觉指纹和组件模式
- 作为 impeccable:frontend-design 的 style reference

### 6. 调用 impeccable:frontend-design 生成 HTML 原型

传入蓝图中的模块清单和信息优先级、产品规格中的密度/字号/间距标准、品牌 DNA（Graphite Studio 风格）、[如 --reference] 参考页面确保风格对齐。

### 6a. 三区结构生成（CREATE 核心扩展）

原型采用三区 Hash 导航架构（借鉴 Figma frame + Storybook 导航 + Design System 文档画廊）：

- Zone 1: default-view（纯净默认视图）
- Zone 2: states-gallery（状态变体画廊）
- Zone 3: overlays-gallery（弹层设计画廊）

HTML 骨架：

```html
<input type="radio" id="view-default" name="proto-view" checked class="sr-only">
<input type="radio" id="view-states" name="proto-view" class="sr-only">
<input type="radio" id="view-overlays" name="proto-view" class="sr-only">
<nav class="proto-nav">...</nav>
<section id="default-view" class="proto-section">...</section>
<section id="states-gallery" class="proto-section">...</section>
<section id="overlays-gallery" class="proto-section">...</section>
```

**A. Zone 1: Default View（主视图）**

- 完整渲染页面默认状态，与生产环境一致
- 不包含任何 state variant 或 overlay
- Tab 面板（radio 切换）保留在此 zone：
  - 为蓝图定义的每个 tab 生成面板内容
  - 在 `<style>` 中添加 `:has()` 激活规则
  - 蓝图内容不足时分级处理：
    - 有子模块清单 → 按清单生成 mock 数据面板
    - 有标签名+上下文可推断 → 推理生成合理内容
    - 仅有标签名无法推断 → 骨架占位 + `<!-- ⚠️ 待 PM 定义 -->`
  - Tab 是页面功能导航，不是组件生命周期状态

**B. Zone 3: Overlays Gallery（弹层设计画廊）**

- 所有弹层直接渲染在 `.gallery-card` 中
- 无需 checkbox toggle，直接可见
- 蓝图有明确交互设计的 → 全量渲染在 `.gallery-card__preview--overlay` 中
- 表格行"查看详情"操作 → 渲染通用 detail drawer，标注 `[示意]`
- 破坏性操作 → 渲染通用 confirm dialog 模板
- 每个 overlay card 含 label + trigger 描述

**C. Zone 2: States Gallery（状态变体画廊）**

- 每个数据区块生成 empty/loading/error 三态
- 按 `.gallery-group[data-component]` 分组
- 每个状态用 `.gallery-card` 包裹（`.gallery-card__label` + `.gallery-card__preview`）
- 使用 prototype-toggles.css 预设样式（`.state-empty` / `.state-loading` / `.state-error`）

**D. State Coverage Index 注入**

- 在 HTML 顶部注入机器可读注释块
- 列出所有 tab / overlay / state variant
- `[✓]` 已渲染 / `[ ]` 未定义
- Tab 面板必须全部 `[✓]`，不允许空壳

**E. 三区 CSS 引用**

- `<head>` 中加载 prototype-toggles.css
- View-level radio + proto-nav（zone 切换）
- default-view 内保留 tab 切换（如蓝图有 tab）
- states-gallery / overlays-gallery 使用 gallery grid 样式

### 6b. data-contract-slot 注入（合同对接）

生成 HTML 时，必须为 `#default-view` 内主要布局区块添加 `data-contract-slot` 属性，供 ditto-page-contract --create 做确定性 selector 映射。

**Shell 级区块（slots）**—— 按页面 shellFamily 映射：

| shellFamily | slots |
|------------|-------|
| command-center | pulse / main / sidebar |
| analytical | strip / main / activity / analysis |
| catalog | toolbar / main / detail |
| object-hub | meta / tabs / main / bottom |
| studio | source / main / inspector / logs / modes |
| ops-console | health / main / detail |
| radar | strip / main / right-rail / tab-band |

**页面级区块（subSlots）**—— 从蓝图核心模块清单推导：

- 每个蓝图核心模块对应一个 data-contract-slot
- 命名规则：kebab-case 英文名（如 decision-banner, priority-queue, scope-strip）
- 与 data-component（gallery 分组用）不冲突

示例（home 页面 #default-view）：

```html
<div class="shell-pulse" data-contract-slot="pulse">
<div class="shell-main" data-contract-slot="main">
<div class="shell-sidebar" data-contract-slot="sidebar">
<div class="decision-banner" data-contract-slot="decision-banner">
<div class="panel-grow" data-contract-slot="priority-queue">
```

**注意**：
- data-contract-slot 只加在 #default-view 内
- states-gallery 和 overlays-gallery 内不添加
- 不替代现有 class 名，是额外属性

### 7. 写入目标文件

### 7a. 三区结构验证（CREATE 后必须执行 — 10 项）

| # | 检查项 | 方法 |
|---|--------|------|
| 1 | section 标签平衡（open == close） | DOM 解析器 |
| 2 | 无 HTML 实体转义（`&lt;` 不在标签位置） | DOM 解析器 |
| 3 | overlay trigger 在 section 外（body 直系） | DOM 解析器 |
| 4 | overlay-backdrop 在 overlays-gallery 内 | DOM 解析器 |
| 5 | .gallery-grid 直接子元素只能是 .gallery-group 或 .gallery-card | DOM 解析器 |
| 6 | overlays-gallery 每个 card 含可渲染弹层 HTML | DOM 解析器 |
| 7 | states-gallery card 数量 ≥ 迁移前 state-variant 总数 | DOM 解析器（迁移场景） |
| 8 | .overlay-backdrop computed display 必须为 none | page.evaluate() |
| 9 | 全部用 DOM 解析器 / Playwright（禁止正则） | — |
| 10 | #default-view 内 shell 级区块必须有 data-contract-slot | page.evaluate() |

**注意**: 全部 10 项检查必须用 DOM 解析器或 Playwright page.evaluate()，禁止正则做 HTML 结构验证。

### 7b. PRE-SCORE GATES 脚本化验证（CREATE 后必须执行）

生成或修复原型后，必须运行：

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/<page>.html
```

该命令验证原型工具 UI 隔离、CSS/token 资源加载、shell 结构、视口完整性、fixed/sticky 遮挡，并输出 fullPage 截图作为 Phase 8 评分证据。exit code 非 0 时不得 commit/tag `round-0`。

### 8. git add → commit → tag review/<task>/round-0

---

## --create-all 批量创建

触发条件: $ARGUMENTS 包含 --create-all

### 1. 读取页面蓝图

读取 02_core_page_blueprints.md，提取所有需要 HTML 原型的页面 + 优先级。

### 2. 读取/创建 manifest

- 不存在 → 初始化 edition v1，status="creating"
- 已存在 → 跳过 status="done" 的页面

### 3. 按 --only 参数过滤（如有），否则按蓝图优先级排序

### 4. 逐页创建

- 第一个页面：无 reference，是 Edition 风格基准
- 后续页面：以 manifest 中最高分 done 页面为 anchor，传入 anchor 页面 HTML 作为 --reference
- 传入蓝图模块清单 + 产品规格 + 品牌 DNA
- 执行步骤 6a 全状态生成 + 步骤 6b 合同注入
- 写入目标文件 → 更新 manifest pages[]
- **门禁**: 每页创建后立即执行步骤 7a（10 项检查）
  - 全部通过 → 继续下一页
  - 任一失败 → 阻断：记录失败页 + 失败项 → 修复后重新验证 → 3 次仍失败 → 暂停

### 5. 批量后检查（所有页面创建完成后）

| 检查项 | 说明 |
|--------|------|
| A. 状态覆盖完整性 | overlays-gallery card 数 vs 蓝图 overlay 注册表 |
| B. CSS Token 存在性 | page.evaluate() 收集 var(--xxx) 对比 tokens-base.css |
| C. 浏览器抽检 | 3-5 页 Playwright 截图，确认三区可切换 |
| D. 阻断判定 | 0 阻断项 → 继续；有阻断 → 修复重跑（3 次仍存在 → 人工介入） |

### 6. 全部通过后

- manifest.status = "in-progress"
- git add → commit → tag edition/v1/created
- 输出创建摘要（页面数、anchor 链路、跳过列表、检查结果）

**不做六角色审查**——批量创建阶段只产出初始原型，但必须通过 per-page gate 和批量后检查。
