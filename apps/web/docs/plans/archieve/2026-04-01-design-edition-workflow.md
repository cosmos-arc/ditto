# Design Edition 工作流设计

> **日期**：2026-04-01
> **状态**：Approved
> **上游**：[ditto-design-cycle.md](../../.claude/commands/ditto-design-cycle.md)
> **目标**：为 ditto-design-cycle 引入 Edition 机制，解决跨页风格不一致、布局 bug 遗漏、缺乏整体关联三个核心问题

---

## 问题诊断

### 现状

当前 `ditto-design-cycle` 的 `--create` 模式逐页独立生成 HTML 原型，审查也逐页独立进行。虽然已有 8 层 Design Token 架构和共享 CSS 体系，但存在三个系统性问题：

1. **页面间风格/规范差异**：每页的 inline `<style>` 块引入一次性值，两次生成之间的隐性不一致（如 `gap: 12px` vs `gap: var(--space-3)` 但两者恰好相等）无法被 token 审计发现
2. **布局 bug/遮挡未识别**：审查依赖 Chrome MCP 的 `take_snapshot`（a11y 文本树），而遮挡、溢出、错位是纯视觉问题——文本树看不到元素重叠或截断
3. **缺乏整体关联**：逐页独立审查无法检测微观层面的不一致（如两个页面的 table header 高度差 2px，或 card padding 不一致）

### 业界对照

| 机制 | Figma 做法 | 当前做法 | 差距 |
|------|-----------|---------|------|
| 共享组件 | Component + Instance | 共享 CSS token | 接近，但 HTML 无「实例」概念 |
| 视觉基准 | 所有页面同一文件并排可见 | 各页面独立 HTML 文件 | **关键差距** |
| 全局审查 | Zoom out 看全览 | 逐页 snapshot | **关键差距** |
| 变更传播 | 改 Component → 全部实例更新 | 改 shared CSS → 需手动验证 | token 层已解决，inline 层未解决 |

---

## 设计方案

### 核心概念

**Edition** = 一个产品 UI 版本的全部页面原型，以 manifest 清单跟踪状态，以 git tag 管理版本。

不引入 git worktree 或文件夹隔离。Edition 在当前分支上操作，通过 manifest + git tag 管理版本。

### 文件结构变更

去掉 `style-b-graphite-studio/` 文件夹层级，原型直接放在 `prototypes/` 下：

```
docs/designs/specs/prototypes/
├── .edition-manifest.json        # Edition 元数据
├── page-home.html
├── page-markets.html
├── page-cross-market.html
├── page-platform.html
├── page-trading.html
├── page-research.html
├── page-markets-screener.html
├── signals.html
├── risk.html
├── ...
└── shared/
    ├── tokens-base.css
    ├── tokens-semantic.css
    ├── tokens-shell.css
    ├── tokens-data-viz.css
    ├── tokens-component.css
    ├── tokens-interaction.css
    ├── tokens-domain.css
    ├── tokens-density.css
    ├── layout-base.css
    └── mock-data.js
```

风格标识由 manifest 的 `style` 字段记录，不再靠文件夹区分。

---

## Edition Manifest 格式

文件路径：`docs/designs/specs/prototypes/.edition-manifest.json`

```json
{
  "edition": "v1",
  "style": "style-b-graphite-studio",
  "created": "2026-04-01",
  "status": "in-progress",
  "pages": [
    {
      "id": "home",
      "file": "page-home.html",
      "status": "created",
      "score": null,
      "styleAnchor": null,
      "rounds": 0,
      "createdAt": "2026-04-01"
    },
    {
      "id": "markets",
      "file": "page-markets.html",
      "status": "done",
      "score": 8.5,
      "styleAnchor": "home",
      "rounds": 3,
      "createdAt": "2026-04-01"
    }
  ],
  "crossPageAudit": {
    "lastRun": null,
    "issues": 0,
    "fixed": 0
  }
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `edition` | Edition 版本标识 |
| `style` | 风格标识（如 `style-b-graphite-studio`） |
| `status` | Edition 状态：`creating` / `in-progress` / `reviewing` / `done` |
| `pages[].id` | 页面标识，从文件名映射（去 `page-` 前缀和 `.html` 后缀） |
| `pages[].status` | `created` → `audit-passed` → `reviewed` → `needs-refinement` → `done` |
| `pages[].styleAnchor` | 创建时参考的「最佳已完成页面」id，null 表示首个页面 |
| `pages[].score` | 最终气质评分 |
| `pages[].rounds` | 审查轮次 |

### styleAnchor 链路

创建顺序是隐含的质量梯度：
- 第一个页面（Home）无 anchor，是整个 Edition 的风格基准
- 后续页面以上一个最高分的已完成页面为 anchor
- 风格漂移被限制在可追踪的链路内

---

## Edition 生命周期

```
Step 1: /ditto-design-cycle --create-all
  │
  ├── 读取 02_core_page_blueprints.md → 提取所有页面
  ├── 按优先级排序 → 逐页创建（style anchor chain）
  ├── 全部完成后 commit + tag edition/v1/created
  └── manifest 状态：所有页面 = "created"

Step 2: 逐页审查（现有流程，Phase 1 已增强跨页感知）
  │
  ├── /ditto-design-cycle page-home.html --iterate --goal 8.0
  ├── /ditto-design-cycle page-markets.html --iterate --goal 8.0
  ├── ...（每页独立审查，但 Phase 1 自动对比其他已完成页面）
  └── 每页完成后 manifest 状态更新

Step 3: Edition 级验收（可选）
  │
  ├── /ditto-design-cycle --edition-review
  │   （打开所有页面，最终 screenshot 走查一遍）
  ├── 修复遗留的跨页不一致
  └── commit + tag edition/v1/final

后续维护：
  │
  ├── 单页调整：直接改文件，再跑一次审查
  │   Phase 1 自动检测是否引入新的跨页偏差
  └── manifest 实时更新状态
```

---

## 新增模式

### `--create-all` 批量创建

```bash
# 完整 Edition 创建
/ditto-design-cycle --create-all

# 指定 Edition 名称（默认 "v1"）
/ditto-design-cycle --create-all --edition v1

# 只创建特定页面（跳过已完成的）
/ditto-design-cycle --create-all --only markets,trading,research
```

#### 执行逻辑

1. **读取页面蓝图**：从 `02_core_page_blueprints.md` 提取所有需要 HTML 原型的页面
2. **确定创建顺序**：按蓝图中的页面优先级排序（Home 第一）
3. **读取/创建 manifest**：如不存在则初始化，如已存在则跳过 `status: "done"` 的页面
4. **逐页创建**，每页调用 impeccable:frontend-design，传入：
   - 蓝图中该页的模块清单和信息优先级
   - 产品规格的密度/字号/间距标准
   - 品牌 DNA（Graphite Studio）
   - styleAnchor 页面的 HTML 作为 style reference（首次无 reference）
5. **创建后立即写入 manifest**，记录 styleAnchor 链路
6. **不做审查**——批量创建阶段只产出初始原型

#### 与现有 `--create` 的关系

`--create-all` 内部循环调用现有 `--create` 逻辑，增加 `--reference` 参数传递 style anchor。现有 `--create` 单页模式不受影响。

### `--reference <file>` 参数（`--create` 的扩展）

```bash
# 带参考页面的单页创建
/ditto-design-cycle page-markets.html --create --page markets --reference page-home.html
```

impeccable:frontend-design 在生成时读取参考页面的 HTML，确保风格对齐。

### `--edition-review` Edition 级验收

```bash
# 对整个 Edition 做最终走查
/ditto-design-cycle --edition-review

# 指定 Edition
/ditto-design-cycle --edition-review --edition v1
```

#### 执行逻辑

1. 读取 manifest，获取所有 `status: "done"` 的页面
2. Chrome MCP 逐页打开 → `take_screenshot` 截取全页面截图
3. 对每张截图用 image analysis（`mcp__zai-mcp-server__analyze_image`）检测：
   - 布局 bug（溢出、截断、元素重叠）
   - 风格偏差（与 Edition 整体风格不一致的元素）
   - 排版问题（字号层级混乱、间距异常）
4. 生成 Edition 级验收报告
5. 只标记 P0/P1 问题，不跑完整的六角色审查

---

## 现有流程增强

### Phase 1: BASELINE 增强（跨页一致性基线）

现有 Step 10 「跨页视觉指纹采集」扩展为结构化 metrics 提取：

```
Phase 1 Step 10（增强版）：
  1. 遍历 prototypes/ 下所有 .html 文件（排除 index.html / token-showcase.html 等非应用页面）
  2. 逐页打开 → emulate(VP-STANDARD) → evaluate_script 提取：
     {
       shell: {
         railWidth:    ".rail" computed width,
         headerHeight: ".app-header" computed height,
         mainPadding:  ".main-content" computed padding
       },
       components: {
         tableHeaderHeight: 所有 "table th" 的 height/padding,
         cardPadding:       所有 "[class*=card]" 的 padding/border-radius,
         badgeSize:         所有 "[class*=badge]" 的 height/padding/font-size,
         buttonHeight:      所有 "button" 的 height/padding
       },
       typography: {
         h1: { size, weight, lineHeight },
         h2: { size, weight, lineHeight },
         body: { size, weight, lineHeight },
         isUsingTokens: font-size 值是否匹配 --text-* 变量
       },
       colors: {
         brandAccentCount:    品牌色出现次数,
         surfaceElevations:   所有 surface 背景色值,
         functionalColorSet:  使用的功能色种类
       }
     }
  3. 比对所有页面的 metrics，标记偏离值
     （如：page-markets 的 tableHeaderHeight=40px，page-cross-market 的为 36px → 标记）
  4. 生成「跨页一致性基线报告」（结构化 JSON，存入内存）
  5. 将报告作为 Phase 3 各角色的审查输入
```

### Phase 3: PARALLEL REVIEW 增强（跨页输入）

每个角色 Agent 的 prompt 增加一段：

```
## 跨页一致性基线

以下是本 Edition 所有已完成页面的结构化 metrics 对比。请特别关注：
- 与其他页面不一致的组件尺寸
- 偏离 token 体系的硬编码值
- 与整体排版层级不符的字号选择

{跨页一致性基线报告}
```

**各角色新增关注点：**

| 角色 | 跨页关注 |
|------|---------|
| UI Designer | 组件尺寸是否与基线一致；是否有硬编码值绕过 token |
| UX Reviewer | 交互模式是否与同类型页面一致 |
| Art Director | 视觉节奏、留白比例是否与整体 Edition 协调 |

### Phase 8: FINAL 增强（screenshot 验证）

现有 lighthouse + token 审计基础上，新增：

```
Phase 8 新增步骤：
  1. take_screenshot（VP-STANDARD，full page）
  2. analyze_image 检测布局问题：
     - 内容溢出/截断
     - 元素重叠/遮挡
     - 对齐偏移
     - 留白异常
  3. evaluate_script 数据验证（交叉验证 image analysis 结果）：
     - scrollHeight > clientHeight → 内容溢出确认
     - getBoundingClientRect() → 对齐偏移量化
  4. 最终跨页 metrics 比对（确保本轮修改没引入新的偏差）
```

---

## 改动汇总

| 改动项 | 类型 | 文件 | 影响 |
|--------|------|------|------|
| `.edition-manifest.json` | 新文件 | `docs/designs/specs/prototypes/` | Edition 状态跟踪 |
| `--create-all` 模式 | 新增 | `ditto-design-cycle.md` | Phase 0.5 循环调用 |
| `--reference <file>` 参数 | 新增 | `ditto-design-cycle.md` | `--create` 可指定 style anchor |
| `--edition-review` 模式 | 新增 | `ditto-design-cycle.md` | Edition 级验收走查 |
| Phase 1 Step 10 | 修改 | `ditto-design-cycle.md` | 结构化 metrics 提取 |
| Phase 3 输入 | 修改 | `ditto-design-cycle.md` | 跨页基线报告作为输入 |
| Phase 8 布局检测 | 修改 | `ditto-design-cycle.md` | screenshot + image analysis |
| 文件结构迁移 | 操作 | `prototypes/` 目录 | `style-b-graphite-studio/` 内容上移一级 |

### 不变的部分

- 现有 `--create` 单页模式（增加可选 `--reference` 参数，向后兼容）
- 现有 `--iterate` 自主迭代模式
- 现有六角色审查流程
- 现有 git tag 版本管理
- 现有 `--sync` 反向同步
- 现有单角色审查（`--ui` / `--ux` 等）
- 现有 impeccable skills 调用链

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| `--create-all` 批量创建成本高（多个 API 调用） | `--only` 参数支持分批创建 |
| Phase 1 遍历所有页面增加审查时间 | 只遍历 manifest 中 status != "done" 的页面 |
| screenshot 分析增加 Phase 8 时间 | 仅在 --iterate 最后一轮和 --edition-review 时执行完整 screenshot 分析 |
| 文件结构迁移影响现有 git tag | 保留旧 tag，新 tag 使用新路径；旧 `review/<task>/round-*` tag 兼容 |
