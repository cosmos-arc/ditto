# Ditto Shell Family 规范

> **版本**：v1.4
> **日期**：2026-04-19
> **状态**：Final
>
> **v1.4 变更（审计修复）**
> - Radar 从 Analytical 子变体升级为第 7 个独立 Shell Family（§4.7 Radar Workspace Shell）
> - `/markets`、`/markets/a-shares` 从 Analytical Workspace 迁移至 Radar Workspace
> - `/trading/orders` 从 Catalog Workspace 迁移至 Operations Console（P1-2）
> - Shell 总数从 6 类扩展为 7 类
>
> **v1.3 变更（IA v2.0 同步）**
> - 全局 Rail 从 6 项缩减为 5 项（移除 AI，Copilot 升级为全局 Sidecar）
> - §11.2 Markets：移除 `/markets/universes`（迁至 Research）、`/markets/chart-lab`（降级为 Instrument Hub tab）；标记 `/markets/hk`、`/markets/us` 延后
> - §11.4 Trading：`/trading/positions` + `/trading/trades` 合并为 `/trading/portfolio`
> - §11.5 AI Section 整体标记 deprecated（Copilot → 全局 Sidecar，Agent Console → `/platform/agents`）
> - §11.6 Platform：新增 `/platform/agents`（Studio Shell）
> - §4.2 Shell 定位同步更新
>
> **上游**：[00 视觉宪章](./00_ditto_visual_constitution.md)、[01 产品信息架构](./01_product_information_architecture.md)
> **下游**：[11 Page Pattern Library](./11_ditto_page_pattern_library.md)、[13 Component Spec](./13_ditto_component_spec.md)、[19 Shell Chrome Contract](./19_ditto_shell_chrome_contract.md)
> **职责**：定义全站 7 类壳层与页面骨架家族
>
> 适用范围：Ditto 全站一级工作区与对象页
> 目标：建立完整量化平台级的页面壳层体系，而不是单一 Research 页模板

## 1. 文档目标

Ditto 不是单一用途的研究工具，而是覆盖首页总览、全市场观察、研究与机器学习、组合与交易、风控、AI Agent、平台运维的完整量化平台。

因此，Ditto 不能只有一种页面骨架。

如果所有页面都套用同一种"主表 + 右栏 + 底部分析带"的终端布局，最终会出现两个问题：

第一，分析页会比较合理，但首页、Studio、平台配置、AI 工作台会很别扭。

第二，系统整体会看起来像"同一张页面反复换内容"，而不是一个成熟的多角色专业平台。

这份规范的目标，是把 Ditto 的页面壳层拆成一组有明确分工的 Shell Family，让整个系统同时具备：

- 终端级专业感
- 跨模块一致性
- 页面角色清晰度
- 可维护的前端 layout 体系
- 可扩展的设计系统骨架

---

## 2. 总体原则

Ditto 的 Shell Family 必须遵循下面 6 条总原则。

### 原则 1：壳层先服务页面角色，再服务统一感

统一感很重要，但不能为了统一而牺牲页面任务。不同页面承担的任务不同，壳层必须先匹配任务角色，再通过节奏、语法、组件体系实现全站统一。

### 原则 2：导航是背景，工作区是主角

无论使用哪一类 Shell，导航都不应成为页面第一视觉中心。用户进入页面后，应先理解自己当前在哪个 workspace、正在操作什么对象，而不是先面对菜单树。

### 原则 3：同一类壳层要高度一致，不同壳层要边界清楚

Command Center 不应长得像 Strategy Editor。Studio 不应长得像 Orders Ledger。但同属 Studio 的 Agent Workspace 与 Strategy Builder，仍然应该共享相似语法。

### 原则 4：专业平台不是"卡片堆"，而是"工作面"

Ditto 的页面骨架应由 workspace、panel、table、chart、queue、editor、inspector 这些工作面组成，而不是由大量独立 card 拼接而成。

### 原则 5：页面骨架必须支持长期使用

Ditto 的核心页面会被长时间盯盘、研究、回顾、配置、监控。壳层设计必须优先考虑稳定感、可记忆性和低噪声，而不是首次打开时的"完成度"或"丰富感"。

### 原则 6：跨模块的一致性来自语法，不来自强行长一样

真正的统一，不是所有页面都一模一样，而是它们都遵循类似的结构语法：

- 上下文先于菜单
- 主仪表先于次级信息
- 连续 panel 先于碎片卡片
- drill-down 优先局部展开，不优先整页跳转

---

## 3. Shell Family 总览

Ditto 全站建议固定为 **7 类基础壳层**：

| # | Shell 名称 | 一句话定位 |
|---|-----------|-----------|
| 1 | **Command Center Shell** | 全局指挥台，跨域状态聚合与工作起点 |
| 2 | **Analytical Workspace Shell** | 分析终端，研究/监控/判断为主 |
| 3 | **Catalog Workspace Shell** | 对象目录，集合管理与检索 |
| 4 | **Object Hub Shell** | 对象中心，单一对象的综合操作面 |
| 5 | **Studio Shell** | 构建工坊，编辑/对话/编排/调试 |
| 6 | **Operations Console Shell** | 运维控制台，系统管理与配置 |
| 7 | **Radar Workspace Shell** | 雷达扫描全景布局 |

这 7 类壳层已经足以覆盖当前 sitemap 里的绝大多数页面，并且能支撑后续扩展。

### 3.1 Primary Answer 承载面

所有 Shell 都必须暴露一个 Primary Answer 承载面，用于在 5 秒内回答当前页面的核心判断。Primary Answer = 一句话判断 + 1 个关键数字 + 2-3 个证据 + 1 个主动作 + 明确影响范围。

| Shell | Primary Answer 对应面 |
|---|---|
| Command Center | decision card |
| Analytical | main instrument readout 或 context strip |
| Catalog | task-specific summary strip |
| Object Hub | object status header |
| Studio | current build / run status |
| Operations Console | incident / service health priority |
| Radar | market scope strip + selected map summary |

实现时每页只能有一个 `data-primary-answer` 或 `data-primary-answer-equivalent`，已有成熟主区域优先补充语义属性，不新增重复卡片。

---

## 4. 七类 Shell 的定位

### 4.1 Command Center Shell

**适用场景**

用于全局总览、待处理事项、跨域状态聚合、今日重点工作等页面。

**对应页面**

- `/`
- 未来若有全局 "morning brief / daily prep / global command" 页面，也走这一类

**任务特征**

- 跨模块信息汇总
- 待处理事项优先
- 快速进入下一步工作流
- 更像"指挥台"而不是"分析台"

**不适合的场景**

- 深度研究单对象
- 高密度筛选与多列比较
- 策略构建与参数编辑
- 复杂配置表单

---

### 4.2 Analytical Workspace Shell

**适用场景**

用于研究、市场、组合、信号、风险这类以分析、监控和判断为核心的页面。

**对应页面**

- `/markets/intelligence`
- `/research`
- `/research/regime`
- `/trading`
- `/trading/portfolio` **[v1.3 合并：原 `/trading/positions` + `/trading/trades`]**
- `/trading/risk`

<!-- 已修正: `/trading/signals` → Operations Console（核心动词是 review/confirm/reject） -->
<!-- v1.4: `/markets`、`/markets/a-shares` 已迁移至 Radar Workspace Shell（§4.7） -->
<!-- v1.4: `/markets/watchlist` 迁移至 Catalog Workspace（浏览+下钻+批量操作模式更匹配 catalog） -->

**任务特征**

- 主表 / 主图是页面主仪表
- 右侧有持续辅助区
- 底部有分析带
- 非常适合 terminal 风格

**不适合的场景**

- 纯配置台
- 纯目录页
- 复杂编辑器
- 运维表单页

---

### 4.2.1 Analytical / Radar 子变体

> **注意**：Radar 子变体已在 v1.4 中独立为第 7 类壳层 Radar Workspace Shell（§4.7）。
> 以下内容保留作为设计演进历史参考。
>
> **详细设计**：[全市场总览设计文档](../../plans/2026-03-29-cross-market-overview-design.md)

**适用场景**

> ~~用于跨市场扫描和单市场结构扫描——以"扫 → 比 → 选"为核心动词的页面。~~
> 已由 §4.7 Radar Workspace Shell 承载。

**对应页面**

> 以下页面已迁移至 §4.7 Radar Workspace Shell：
> - `/markets` — 全市场总览
> - `/markets/a-shares` — 中国 A 股总览
> - 后续 `/markets/hk`、`/markets/us`、`/markets/fx`、`/markets/rates`、`/markets/commodities`

<!-- v1.3: `/markets/hk` 和 `/markets/us` 延后至 v1.5/v2，当前不列入对应页面 -->

**任务特征**

- 双层 Context：Context Bar（客观变量） + Scope Strip（解读摘要）
- 主工作面 70%，Right Rail 30%
- 主工作面不是单一主表/主图，而是 Market Cards / Matrix / Drivers 组合
- Right Rail 聚焦风险、事件和下钻推荐，不是信息堆叠
- 底部 Tab Band（资金轮动 / 事件日历 / AI 解读）
- 页面核心动词是 scan / compare / drill down，不是深度分析

**与 Analytical 原版的差异**

| 维度 | Analytical 原版 | Radar 子变体 |
|------|----------------|-------------|
| Context 层 | 单层 Pulse Strip | 双层（Context Bar + Scope Strip） |
| 主工作面比例 | 65-70% | 固定 70% |
| 右侧 | Activity Stack | Right Rail（风险 + 事件 + 下钻） |
| 底部 | Analysis Band | Tab Band（资金轮动 / 事件日历 / AI 解读） |
| 页面动词 | 分析 / 监控 / 判断 | 扫描 / 比较 / 下钻 |

**推荐骨架**

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Workspace Header                                              │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Context Bar（全局环境条 — 客观变量）                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope Strip（今日解读条 — 人话摘要）                             │
│      ├───────────────────────────────────┬───────────────────────────┤
│      │ Main Stage (70%)                  │ Right Rail (30%)          │
│      │                                   │                           │
│      │ Market Cards / Matrix / Drivers   │ 脉搏 / 风险 / 事件 / 下钻   │
│      │                                   │                           │
│      ├───────────────────────────────────┴───────────────────────────┤
│      │ Bottom Tab Band                                               │
└──────┴───────────────────────────────────────────────────────────────┘
```

**CSS Grid 定义**

```css
.shell-radar {
  display: grid;
  grid-template-columns: var(--shell-rail-width) 1fr var(--shell-rail-radar-width);
  grid-template-rows: var(--shell-header-height) var(--context-bar-height) var(--scope-strip-height) 1fr var(--tab-band-height);
  grid-template-areas:
    "rail    header   header"
    "rail    context  context"
    "rail    scope    scope"
    "rail    main     right-rail"
    "rail    tabs     tabs";
}
```

**不适合的场景**

- 深度单对象分析（应使用 Analytical 原版或 Object Hub）
- 纯配置台
- 纯目录页
- 复杂编辑器

---

### 4.3 Catalog Workspace Shell

**适用场景**

用于目录、列表、对象库、筛选器、资产池、订单流水等以"对象集合管理"为核心的页面。

**对应页面**

- `/markets/watchlist` **[v1.4: 从 Analytical Workspace 迁入（浏览+下钻+批量操作模式更匹配 catalog）]**
- `/markets/screener`
- `/markets/calendar`
- `/research/factors`
- `/research/strategies`
- `/research/backtest`
- `/research/experiments`

<!-- v1.3: `/markets/universes` 已移至 Research 域 -->
<!-- v1.4: `/trading/orders` 已迁移至 Operations Console（核心动词是 review/track/reconcile） -->
<!-- v1.3: `/trading/trades` 已合并入 `/trading/portfolio`（Analytical Workspace） -->

<!-- 已降级: `/platform/brokers` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/data-providers` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/pipelines` → `/platform` 的 tab -->

**任务特征**

- 主角是目录表 / 对象表 / 流水表
- 更强调 scope、筛选、列管理、批量动作
- 底部分析带通常不是必需
- 右侧更适合 preview / inspector，而不一定是 activity stack

**不适合的场景**

- 复杂分析仪表页
- 对象级 hub
- Studio / Builder
- Settings 级表单页

---

### 4.4 Object Hub Shell

**适用场景**

用于围绕单一对象形成的操作中心。

**对应页面**

- `/instruments/[id]`
- `/research/factors/[id]`
- `/research/backtest/[id]`

**任务特征**

- 页面围绕一个对象组织
- Header 中对象上下文极强
- 主区可分为多个对象仪表
- 右侧可放 recent events / related entities / notes / version history
- 底部可承载 logs、timeline、diagnostics

**不适合的场景**

- 对象列表
- 批量管理
- 策略画布式编辑
- 平台设置

---

### 4.5 Studio Shell

**适用场景**

用于构建、编辑、对话、编排、调试等创作型页面。

**对应页面**

- `/research/strategies/[id]/studio`
- `/platform/agents` **[v1.3: 从 `/ai/agent` 迁入]**

<!-- v1.3: `/markets/chart-lab` 已降级为 `/instruments/[id]` 的 tab，不再独立使用 Studio Shell -->
<!-- v1.3: `/ai/copilot` 已升级为全局 Sidecar，不再作为独立路由 -->
<!-- v1.3: `/ai/agent` 已迁入 `/platform/agents` -->

**任务特征**

- 中间往往是 editor / canvas / notebook / chat / builder
- 左右两侧是 source / config / inspector / preview
- 主任务是构建与交互，而不是扫表

**不适合的场景**

- 单纯目录页
- 主表分析页
- 平台配置台
- 纯运营队列页

---

### 4.6 Operations Console Shell

**适用场景**

用于平台运维、告警处置、系统设置、任务流水、集成配置等页面。

**对应页面**

- `/platform`
- `/platform/settings`
- `/trading/orders` **[v1.4: 从 Catalog Workspace 迁入，核心动词是 review/track/reconcile]**
- 未来可能的 `/platform/logs`、`/platform/jobs`、`/platform/audit`

<!-- 已降级: `/platform/accounts` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/data-quality` → `/platform` 的 tab -->
<!-- 已降级: `/platform/pipelines` → `/platform` 的 tab -->

**任务特征**

- 更强调系统状态、日志、队列、依赖、配置、处置
- 页面可以专业，但不必过度金融终端化
- 主表、队列和 detail panel 很重要
- analysis band 重要性通常低于 analytical shell

**不适合的场景**

- 强对象分析页
- 策略编辑页
- 研究仪表页

---

### 4.7 Radar Workspace Shell

**适用场景**

用于跨市场/单市场雷达扫描全景布局——以"扫 → 比 → 选"为核心动词的页面。从 Analytical Workspace Shell 的 Radar 子变体（§4.2.1）独立为第 7 类壳层，因其布局结构、比例和交互模式与 Analytical 原版差异显著。

**对应页面**

- `/markets` — 全市场总览
- `/markets/a-shares` — 中国 A 股总览
- 后续 `/markets/hk`、`/markets/us`、`/markets/fx`、`/markets/rates`、`/markets/commodities`

<!-- v1.3: `/markets/hk` 和 `/markets/us` 延后至 v1.5/v2，当前不列入对应页面 -->

**任务特征**

- 双层 Context：Context Bar（客观变量） + Scope Strip（解读摘要）
- 主工作面 70%，Right Rail 30%（固定比例）
- 主工作面不是单一主表/主图，而是 Market Cards / Matrix / Drivers 组合
- Right Rail 聚焦风险、事件和下钻推荐，不是信息堆叠
- 底部 Tab Band（资金轮动 / 事件日历 / AI 解读）
- 页面核心动词是 scan / compare / drill down，不是深度分析

**与 Analytical Workspace Shell 的差异**

| 维度 | Analytical Workspace | Radar Workspace |
|------|----------------------|-----------------|
| Context 层 | 单层 Pulse Strip | 双层（Context Bar + Scope Strip） |
| 主工作面比例 | 65-70% | 固定 70% |
| 右侧 | Activity Stack | Right Rail（风险 + 事件 + 下钻） |
| 底部 | Analysis Band | Tab Band（资金轮动 / 事件日历 / AI 解读） |
| 页面动词 | 分析 / 监控 / 判断 | 扫描 / 比较 / 下钻 |
| CSS Grid | 标准三栏 | 独立 grid（含 scope-strip 行） |

**推荐骨架**

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Workspace Header                                              │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Context Bar（全局环境条 — 客观变量）                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope Strip（今日解读条 — 人话摘要）                             │
│      ├───────────────────────────────────┬───────────────────────────┤
│      │ Main Stage (70%)                  │ Right Rail (30%)          │
│      │                                   │                           │
│      │ Market Cards / Matrix / Drivers   │ 脉搏 / 风险 / 事件 / 下钻   │
│      │                                   │                           │
│      ├───────────────────────────────────┴───────────────────────────┤
│      │ Bottom Tab Band                                               │
└──────┴───────────────────────────────────────────────────────────────┘
```

**CSS Grid 定义**

```css
.shell-radar {
  display: grid;
  grid-template-columns: var(--shell-rail-width) 1fr var(--shell-rail-radar-width);
  grid-template-rows: var(--shell-header-height) var(--context-bar-height) var(--scope-strip-height) 1fr var(--tab-band-height);
  grid-template-areas:
    "rail    header   header"
    "rail    context  context"
    "rail    scope    scope"
    "rail    main     right-rail"
    "rail    tabs     tabs";
}
```

**不适合的场景**

- 深度单对象分析（应使用 Object Hub）
- 纯配置台（应使用 Operations Console）
- 纯目录页（应使用 Catalog Workspace）
- 复杂编辑器（应使用 Studio）

---

## 5. 全站统一壳层元素

虽然 Ditto 有 7 类 Shell，但它们仍共享一套顶层语法。

### 5.0 Shell Chrome Contract

所有 Shell Family 都继承 [19 Shell Chrome Contract](./19_ditto_shell_chrome_contract.md) 中定义的全局 chrome 规则。
Shell Family 差异从全局 Rail、Header Utility Bar 与视图偏好层之下开始。

### 5.1 全局 Rail

全站默认保留极窄 rail 作为一级模块切换器。

**它承担：**

- Home
- Markets
- Research
- Trading
- Platform

<!-- v1.3: AI 已从全局 Rail 移除。Copilot 升级为全局 Sidecar（跨域可用），Agent Console 迁入 Platform 域。 -->

**它不承担：**

- 二级菜单树
- 工作区内部导航
- 对象级切换
- 重操作

### 5.2 Workspace Header

所有壳层都应有自己的 header 语法。但不同 Shell 的 header 重心不同：

| Shell | Header 重心 |
|-------|-----------|
| Command Center | 全局状态与今日工作 |
| Analytical | workspace 上下文 + command + 主动作 |
| Catalog | scope + filters + table actions |
| Object Hub | 对象身份 + meta + actions |
| Studio | session / object + run state + save/publish |
| Operations | system scope + environment + action / logs / filters |
| Radar | workspace 上下文 + 市场环境 + 主动作（scan/compare/drill down） |

### 5.3 上下文条或状态条

不是每个 Shell 都要叫 Pulse，但大多数都需要一层轻量 strip，表达：

- 当前 scope
- 状态摘要
- 数据新鲜度
- 数量与范围
- 当前任务状态

### 5.4 主工作面

每类 Shell 都必须有一个主工作面。这是 Ditto 高级感的核心。

> 页面不是"若干块内容"，而是"一个主工作面 + 若干辅助工作面"。

### 5.5 局部 drill-down 优先

Ditto 的壳层应优先支持：

- drawer
- side sheet
- inspector
- inline detail
- overlay compare

而不是一切都整页跳走。

---

## 6. 七类 Shell 的结构规范

### 6.1 Command Center Shell 规范

#### 6.1.1 角色定义

Command Center 是 Ditto 的全局指挥台。它不是某一模块的首页，而是跨模块工作起点。

它必须回答：

- 今天最重要的事是什么
- 当前有哪些系统/策略/市场状态值得看
- 哪些事项需要立即处理
- 用户接下来该进入哪个工作区

#### 6.1.2 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Global Header                                                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Global Pulse                                                 │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Focus Area               │ Global Alerts / Live Queue    │
│      │                               │                               │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Quick Actions / Today Boards / Cross-Domain Summary           │
└──────┴───────────────────────────────────────────────────────────────┘
```

#### 6.1.3 核心区块

**Global Header** — 应包含：

- Ditto
- 今日日期 / session 状态
- 全局 command search
- 关键全局动作

**Global Pulse** — 应包含：

- 待处理事项数
- 风险告警数
- 运行中 jobs
- 数据延迟 / 系统异常摘要
- 今日重点变化

**Main Focus Area** — 这是首页主角，应优先展示：

- 唯一 `decision-card`，回答今日主决策、原因、风险/机会与下一步动作
- Priority queue 的 P1/P2 默认可见项
- P3+ 低优先级事项进入折叠区或二级入口
- Activity stream 作为后续辅助记录，不抢占首屏主答案

**右侧辅助区** — 适合放：

- Global alerts
- Running jobs
- Incidents
- Live broker / data / agent issues

**底部带** — 适合放：

- Quick actions
- Cross-domain snapshots
- Shortcuts into key workspaces

#### 6.1.4 不建议

- 首页做成普通 dashboard 卡片墙
- 首页做成某个模块的缩略版
- 首页放大量静态图表占空间
- 首页抢走真正工作区的功能

---

### 6.2 Analytical Workspace Shell 规范

#### 6.2.1 角色定义

这是 Ditto 中最接近专业终端的骨架。适用于"分析、判断、监控"为主任务的页面。

#### 6.2.2 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Workspace Header                                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Pulse / Context Strip                                        │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Instrument Area          │ Activity Stack               │
│      │                               │                               │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Analysis Band                                                │
└──────┴───────────────────────────────────────────────────────────────┘
```

#### 6.2.3 核心规则

- 主仪表必须是页面绝对主角
- Activity Stack 必须连续，不可碎片卡片化
- Analysis Band 必须解释主仪表，而不是做第二主舞台
- 表、图、筛选、对象联动要围绕同一上下文展开

#### 6.2.4 适用主仪表

- Factor monitor
- Holdings / positions
- Risk utilization
- Signal monitor
- Regime dashboard

#### 6.2.5 可变体

**Table-first** — 主区以主表为核心。适合：Research overview、Positions、Signals

**Chart-first** — 主区以主图为核心。适合：Markets overview、Risk dashboard、Regime lab

**Mixed** — 主区表图并存，但主次必须明确。适合：Trading overview

---

### 6.3 Catalog Workspace Shell 规范

#### 6.3.1 角色定义

Catalog Shell 用于"对象集合管理与检索"。重点是管理、筛选、浏览、批量动作，不一定强调深度分析。

#### 6.3.2 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Catalog Header                                               │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope / Filter Strip                                         │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Table / Grid             │ Preview / Inspector Panel     │
│      │                               │ (optional)                    │
│      └───────────────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────────┘
```

#### 6.3.3 核心规则

- 主角是目录表、列表、网格，不是图表
- scope 和 filter 很重要
- 右侧 panel 更适合 preview / details / ops，而不是 full activity stack
- 底部 analysis band 通常不作为默认结构

#### 6.3.4 适用对象

Factors、Strategies、Experiments、Accounts、Portfolios、Orders、Trades、Pipelines、Data providers

#### 6.3.5 子变体

| 子变体 | 偏向 | 示例 |
|--------|------|------|
| **Library Catalog** | 偏对象库 | factors、strategies、universes |
| **Ledger Catalog** | 偏流水 | orders、trades、fills |
| **Queue Catalog** | 偏任务 / 队列 | experiments、pipelines、review items |

---

### 6.4 Object Hub Shell 规范

#### 6.4.1 角色定义

Object Hub 用来承载"单一对象的完整工作面"。它不是简单详情页，而是围绕一个对象的综合操作中心。

#### 6.4.2 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Object Header                                                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Object Meta Strip                                            │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Object Panels            │ Related / History / Notes     │
│      │                               │                               │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Timeline / Diagnostics / Logs / Linked Views                 │
└──────┴───────────────────────────────────────────────────────────────┘
```

#### 6.4.3 Object Header 应包含

- 对象名称
- 对象类型
- 关键状态
- 关键操作
- 当前版本 / 当前运行态（如适用）

例如：Instrument、Factor、Strategy、Backtest、Experiment

#### 6.4.4 主区组织方式

主区一般使用 2 到 3 个高价值 panel，而不是一长串模块。

- Strategy hub：Performance / Exposure & turnover / Related runs & signals
- Factor analysis：IC & IR / Decay / Correlation & coverage

#### 6.4.5 右侧区适合放

- recent events
- linked entities
- owner / notes
- version history
- incidents / issues

#### 6.4.6 底部区适合放

- timeline
- diagnostics
- logs
- change history
- artifacts
- linked outputs

---

### 6.5 Studio Shell 规范

#### 6.5.1 角色定义

Studio Shell 是 Ditto 的构建型工作区。适用于策略构建、图表实验、AI 协作、agent 调度、回测配置等页面。

#### 6.5.2 推荐骨架

**双栏 Studio：**

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Studio Header                                                │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Canvas / Editor / Chat   │ Inspector / Config / Preview  │
│      │                               │                                │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

**三栏 Studio：**

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Studio Header                                                │
│      ├───────────────┬───────────────────────────────┬──────────────┤
│      │ Sources       │ Main Canvas / Editor / Chat   │ Inspector    │
│      │ / Outline     │                               │ / Run State   │
└──────┴───────────────┴───────────────────────────────┴──────────────┘
```

#### 6.5.3 核心规则

- 中间工作面必须最大
- 左右两侧承担 source / config / inspector
- 不适合强行塞入底部 analysis band
- drill-down 更适合侧板 / inspector / overlay
- action 更偏 save、run、publish、approve、compare

#### 6.5.4 适用页面

Strategy Builder、Agent Console（`/platform/agents`）

<!-- v1.3: Chart Lab 降级为 Instrument Hub tab；AI Copilot 升级为全局 Sidecar；AI Agent Workspace 迁入 `/platform/agents` -->

#### 6.5.5 Studio 内部常见面板

| 位置 | 常见面板 |
|------|---------|
| **左侧** | object tree、node list、template list、context sources、research references |
| **中间** | editor、canvas、notebook、chat、flow builder |
| **右侧** | inspector、run state、tool output、config、preview、approval |

---

### 6.6 Operations Console Shell 规范

#### 6.6.1 角色定义

Operations Console 用于平台管理、系统配置、任务流水、质量监控和告警处置。它不需要像 Analytical Workspace 那样强金融终端感，但仍应保持专业、冷静、低噪声。

#### 6.6.2 推荐骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Ops Header                                                   │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope / Status Strip                                         │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Queue / Table / Forms    │ Detail / Logs / Actions       │
│      │                               │                                │
└──────┴───────────────────────────────┴───────────────────────────────┘
```

#### 6.6.3 核心规则

- 主区更偏队列、表格、配置表单
- 右侧更适合 detail panel / logs / actions
- 底部分析带不是默认配置
- 更强调状态、trace、依赖、权限、版本、异常

#### 6.6.4 适用页面

Platform overview、Accounts [Shell 扩展]、Brokers、Data providers、Data quality、Pipelines、Settings

#### 6.6.5 Ops Detail Panel 适合放

- event log
- retry / resolve / assign
- dependency info
- last sync
- audit trail
- raw payload / detail
- config diff

---

## 7. 全站壳层尺寸基准

以下为 Ditto 桌面端基准。

| 元素 | 尺寸 |
|------|------|
| **全局 Rail** | 宽度 56px |
| **Command Center Header** | 68px |
| **Analytical Header** | 64px |
| **Catalog Header** | 60px |
| **Object Hub Header** | 68px |
| **Studio Header** | 60px |
| **Operations Header** | 60px |
| **Radar Header** | 64px |
| **状态条 / Context Strip** | 36px–44px |
| **Radar Scope Strip** | 36px |
| **Analytical Activity Stack（右侧）** | 300px |
| **Catalog Preview / Inspector（右侧）** | 320px |
| **Object Hub Side Context（右侧）** | 300px |
| **Studio Inspector（右侧）** | 320px–360px |
| **Operations Detail Panel（右侧）** | 320px–380px |
| **Radar Right Rail（右侧）** | 300px |
| **底部 Analysis Band** | 220px–280px（仅推荐用于 Analytical 和部分 Object Hub） |
| **底部 Tab Band** | 200px–240px（Radar Workspace 专用） |

---

## 8. 壳层与右侧栏的对应关系

> 这里非常重要，不同壳层的右侧不是一回事。

| Shell | 右侧区角色 |
|-------|-----------|
| **Command Center** | Global Alerts / Running Jobs / Cross-domain Issues |
| **Analytical Workspace** | Activity Stack |
| **Catalog Workspace** | Preview Panel / Inspector Panel / Queue Summary |
| **Object Hub** | Related / Notes / History / Versions |
| **Studio** | Inspector / Config / Run State / AI Suggestions / Tool Output |
| **Operations Console** | Detail / Logs / Incident Trace / Actions |
| **Radar Workspace** | Right Rail（风险 + 事件 + 下钻推荐） |

> 不能把这七类右侧面板都当作 Activity Stack。

---

## 9. 壳层与底部区的对应关系

| Shell | 底部区定位 |
|-------|-----------|
| **Command Center** | 可有 quick boards，但不宜过重 |
| **Analytical Workspace** | 最重要，默认启用 Analysis Band |
| **Catalog Workspace** | 非必需，通常不启用 |
| **Object Hub** | 常有 timeline / diagnostics / logs，重要性中高 |
| **Studio** | 不是默认结构，优先侧向展开 |
| **Operations Console** | 通常弱于右侧 detail，不建议常规使用 analysis band |
| **Radar Workspace** | Tab Band（资金轮动 / 事件日历 / AI 解读），默认启用 |

---

## 10. 视窗与面板空间管理

### 10.1 视窗锁定原则

Ditto 所有一级工作区采用**单视窗锁定**布局：

```
body { height: 100%; overflow: hidden }
.shell-xxx { height: 100dvh; overflow: hidden }
```

**理由：**

- 与 Bloomberg Terminal / Wind / TradingView 等专业量化平台一致
- Rail、Header、Status Bar 始终可见，不随内容滚动
- 用户形成空间记忆，知道信息在哪
- 多面板并行可见（主区 + sidebar + detail），适合长时间盯盘/研究

**反模式：**

- 页面级滚动（body scroll）— 会让导航和辅助面板消失
- 所有面板平铺不折叠 — 信息密度过高时导致拥挤

### 10.1.1 响应式降级策略

专业桌面优先的降级目标是**保留主任务面板与全局导航的空间记忆**，优先收窄、折叠或摘要化辅助面板；不在当前阶段定义手机形态。

| Shell | 窄视口策略 |
|-------|-----------|
| **Command Center** | Pulse 保持单行，Context Rail 先折叠为摘要 rail，主决策区不降级为页面滚动 |
| **Analytical Workspace** | 右侧 Activity Stack 收窄，Analysis Band 保持可访问；必要时 Activity Stack 折叠为事件摘要 |
| **Catalog Workspace** | Inspector / Preview Panel 可折叠为 summary rail，表格列优先保留排序、选择、主标识与关键指标 |
| **Object Hub** | 底部 timeline / diagnostics 转为 tabbed strip，详情主区保留稳定宽度 |
| **Studio** | Source Panel 与 Inspector 可独立折叠，编辑 / 画布主区优先占用剩余空间 |
| **Operations Console** | Detail Panel 先于主 Queue 折叠，队列、状态与高风险操作保持常驻 |
| **Radar Workspace** | Right Rail 折叠为 event / risk summary，资金轮动与主要监控面板保持同屏 |

### 10.1.2 面板内滚动 vs 折叠

单视窗锁定下，面板内容超出时采用**内部滚动**（`overflow-y: auto`）。
但内部滚动不应是唯一手段。推荐三层策略：

| 层级 | 策略 | 适用场景 |
|------|------|---------|
| L1 常驻 | 固定可见，不滚动 | 快捷操作栏、标的名称、选中状态 |
| L2 核心上下文 | 默认展开，可折叠 | 信号、评分、备注 — 与当前任务相关的信息 |
| L3 补充信息 | 默认折叠，可展开 | 筛选预设、关联研究、历史记录 — 低频信息 |

### 10.1.3 折叠式 Section 规范

**交互模式：** 点击 section header 折叠/展开 body 内容。

**视觉规格：**

- Header：12px semibold，`text-transform: uppercase`，带折叠指示器（▶ / ▼）
- 展开：body 正常显示
- 折叠：body 隐藏，header 保留 + 右侧显示计数 badge
- 过渡：`max-height` transition 或 `display: none`（原型阶段用 `<details>/<summary>`）

**默认展开/折叠规则：**

| 优先级 | 默认状态 | 判断依据 |
|--------|---------|---------|
| 高频核心 | 展开 | 当前任务必需的信息（信号、评分、备注） |
| 低频补充 | 折叠 | 偶尔查看的信息（预设、研究、历史） |
| 空状态 | 折叠 | 无内容时折叠以节省空间 |

**实现方式（纯 CSS）：**

原型阶段使用 `<details open>` / `<details>`（无 `open`）实现，无需 JavaScript。
生产阶段可升级为 checkbox + `:has()` 模式以支持上下文联动。

### 10.1.4 面板空间预算

1080px viewport 下的典型预算分配：

```
Viewport:          1080px
  Header:          -60px
  Toolbar/Strip:   -35px
  Status Bar:      -24px
  ─────────────────────
  Available:       ~961px

  Sidebar (320px):
    L1 Sticky:      48px
    L2 Expanded:   ~300px (1-2 sections)
    L3 Collapsed:   32px × N (headers only)
    ─────────────────────
    Total visible: ~380-480px ← 无需滚动
```

### 10.1.5 上下文感知联动（Hub 专属）

Object Hub 的 sidebar 跨所有 tab 共享。Section 的展开/折叠状态可随 tab 切换联动：

| 当前 Tab | 信号 | 研究 | 备注 |
|----------|------|------|------|
| 概览 | 展开 | 展开 | 展开 |
| 图表 | 折叠 | 折叠 | 展开 |
| 资金流 | 展开 | 折叠 | 展开 |
| 基本面 | 折叠 | 展开 | 展开 |
| 新闻 | 展开 | 展开 | 展开 |

实现思路：tab radio 的 `:has()` + sidebar section checkbox 联动。

---

## 11. 页面与 Shell 映射

### 11.1 Home

| 路径 | Shell |
|------|-------|
| `/` | Command Center |

Home 的 Command Center 首屏必须先给出一个轻量 `global-pulse` 状态条，再给出唯一 `decision-card` primary answer。`decision-card` 是首屏主角：回答今天最该处理什么、为什么、风险/机会多大、下一步动作是什么。Priority queue 默认只露出 P1/P2 项；普通 activity stream 不得排在 decision card 之前。右侧 `data-health` 只列异常数据源，正常数据源以折叠摘要呈现。

<!-- 已降级/合并: `/home/pending` — Home 角色 orient 型，非 execute，降级移除 -->
<!-- 已降级/合并: `/home/quick-actions` — Home 角色 orient 型，非 execute，降级移除 -->
<!-- 已降级/合并: `/home/alerts-summary` — Home 角色 orient 型，非 execute，降级移除 -->

### 11.2 Markets & Intelligence

| 路径 | Shell |
|------|-------|
| `/markets` | Radar Workspace **[v1.4: 从 Analytical Workspace 独立为 Radar Shell]** |
| `/markets/a-shares` | Radar Workspace **[v1.4: 从 Analytical Workspace 独立为 Radar Shell]** |
| `/markets/screener` | Catalog Workspace |
| `/markets/watchlist` | Catalog Workspace **[v1.4: 从 Analytical Workspace 迁入]** |
| `/markets/intelligence` | Analytical Workspace |
| `/markets/calendar` | Catalog Workspace |
| `/instruments/[id]` | Object Hub |

<!-- v1.3: `/markets/universes` 已移至 Research 域（§11.3） -->
<!-- v1.3: `/markets/chart-lab` 已降级为 `/instruments/[id]` 的 tab（Instrument Hub 内置） -->
<!-- v1.3 延后: `/markets/hk` — 港股总览延后至 v1.5 -->
<!-- v1.3 延后: `/markets/us` — 美股总览延后至 v2 -->

<!-- 已降级/合并: `/markets/catalog` — IA 无此路由，screener 已承担目录职能 -->
<!-- 已降级/合并: `/markets/map` — 并入 `/markets` 视图模式 -->
<!-- 已降级/合并: `/markets/intelligence/*` → `/markets/intelligence` — 收敛为 tab 视图 -->

### 11.3 Research

| 路径 | Shell |
|------|-------|
| `/research` | Analytical Workspace |
| `/research/factors` | Catalog Workspace |
| `/research/factors/[id]` | Object Hub |
| `/research/strategies` | Catalog Workspace |
| `/research/strategies/[id]` | Object Hub |
| `/research/strategies/[id]/studio` | Studio |
| `/research/backtest` | Catalog Workspace |
| `/research/backtest/[id]` | Object Hub |
| `/research/experiments` | Catalog Workspace |
| `/research/regime` | Analytical Workspace |
| `/research/universes` | Catalog Workspace |

<!-- 已降级/合并: `/research/factors/[id]/analysis` → `/research/factors/[id]` — 路由简化 -->
<!-- 已降级/合并: `/research/strategies/new` — 统一为 `/research/strategies/[id]/studio` -->
<!-- 已降级/合并: `/research/strategies/[id]/editor` — 统一为 `/research/strategies/[id]/studio` -->
<!-- v1.4: `/research/strategies/[id]` 新增路由（Strategy Detail 查看态），使用 Object Hub -->
<!-- 已降级/合并: `/research/backtest/new` — IA 无此路由 -->
<!-- 已降级/合并: `/research/backtest/compare` — IA 无此路由 -->
<!-- 已降级/合并: `/research/experiments/[id]` — IA 无此路由 -->
<!-- 已降级/合并: `/research/ml` — 降级为 Research 子域 -->
<!-- 已降级/合并: `/research/output` — IA 无此路由 -->

### 11.4 Trading

| 路径 | Shell |
|------|-------|
| `/trading` | Analytical Workspace |
| `/trading/signals` | Operations Console **[v1.1 审计修正：核心动词是 review/confirm/reject，归属 Ops Console]** |
| `/trading/orders` | Operations Console **[v1.4: 从 Catalog Workspace 迁入，核心动词是 review/track/reconcile]** |
| `/trading/portfolio` | Analytical Workspace **[v1.3 合并：原 `/trading/positions` + `/trading/trades` 合并为 portfolio]** |
| `/trading/risk` | Analytical Workspace |

<!-- v1.3 合并: `/trading/positions` + `/trading/trades` → `/trading/portfolio` — 持仓与成交统一视图 -->
<!-- 已降级/合并: `/trading/risk/dashboard` → `/trading/risk` — 路由简化 -->
<!-- 已降级/合并: `/trading/risk/stress-test` — IA 无此路由 -->
<!-- 已降级/合并: `/trading/accounts` — IA 无此路由 -->
<!-- 已降级/合并: `/trading/portfolios` — IA 无此路由 -->
<!-- 已降级/合并: `/trading/alerts` — IA 无此路由 -->

### 11.5 AI

> **v1.3 DEPRECATED — AI 域整体废弃**
>
> AI 域已在 v2.0 中拆散：
> - **Copilot**（`/ai/copilot`）升级为全局 Sidecar，不再作为独立一级路由存在，而是跨域浮层
> - **Agent Console**（`/ai/agent`）迁入 `/platform/agents`，Shell 类型为 Studio
> - **AI 概览**（`/ai`）职能由全局 Sidecar + 各域内 AI 功能承担，不再需要独立入口
>
> 以下路由保留仅供历史参考：

| 路径 | Shell | 状态 |
|------|-------|------|
| `/ai` | Command Center（轻量变体） | ~~Deprecated~~ — 职能由全局 Sidecar 承担 |
| `/ai/copilot` | Studio | ~~Deprecated~~ — 升级为全局 Sidecar |
| `/ai/agent` | Studio | ~~迁移~~ → `/platform/agents` |

<!-- 已降级/合并: `/ai/market-analysis` — 合并为 `/ai/copilot` 内部模式 -->
<!-- 已降级/合并: `/ai/stock-screener` — 合并为 `/ai/copilot` 内部模式 -->
<!-- 已降级/合并: `/ai/strategy-assistant` — 合并为 `/ai/copilot` 内部模式 -->

### 11.6 Platform

| 路径 | Shell |
|------|-------|
| `/platform` | Operations Console |
| `/platform/settings` | Operations Console **[Config 变体]** |
| `/platform/agents` | Studio **[v1.3 新增：Agent Console 从 `/ai/agent` 迁入]** |

> **v1.3 扩展说明**：`/platform/agents`（Agent Console）从 AI 域迁入 Platform 域，使用 Studio Shell。
> 详见 IA v2.0 及 AI 域拆散决策。
>
> **v1 收敛说明**：Platform 域在 v1 仅保留 2 条路由（`/platform` + `/platform/settings`）。
> data-quality / pipelines 收敛为 `/platform` 的 tab；
> accounts / data-providers / brokers 收敛为 `/platform/settings` 的 tab。
> 详见 01 IA §7.6 及 [Platform 域收敛决策](../../docs/designs/decisions/2026-03-31-product-arch-audit-fixes.md)。

<!-- 已降级: `/platform/accounts` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/data-quality` → `/platform` 的 tab -->
<!-- 已降级: `/platform/pipelines` → `/platform` 的 tab -->
<!-- 已降级: `/platform/data-providers` → `/platform/settings` 的 tab -->
<!-- 已降级: `/platform/brokers` → `/platform/settings` 的 tab -->

---

## 12. 前端实现建议

为了让这份规范真正可落地，前端上建议不要做一个巨型通用 layout，而是做一组 shell layouts。

建议目录层面按类似方式组织：

```
AppShell
├── CommandCenterShell
├── AnalyticalWorkspaceShell
├── CatalogWorkspaceShell
├── ObjectHubShell
├── StudioShell
├── OperationsConsoleShell
└── RadarWorkspaceShell
```

每个 Shell 再暴露以下插槽：

| 插槽 | 用途 |
|------|------|
| `header` | Workspace Header |
| `strip` | 上下文条 / 状态条 |
| `main` | 主工作面 |
| `right` | 右侧辅助区 |
| `bottom` | 底部区（如 Analysis Band） |
| `overlay` | 全局覆盖层（drawer / modal） |

这样每个模块页面只关心内容，不需要重复拼壳。

---

## 13. 设计评审时的壳层判断标准

当你评审一个页面时，先别问"好不好看"，先问：

**第一步** — 这页属于哪一种 Shell？
> 如果答不出来，说明页面角色没定。

**第二步** — 这个 Shell 的主工作面是什么？
> 如果没有清晰主工作面，说明布局还不成立。

**第三步** — 右侧面板属于哪一类？
> 如果只是"右边空着，塞点东西"，说明结构不清。

**第四步** — 底部区是否真的有存在必要？
> 如果只是为了完整感而放，应该删。

**第五步** — 导航是否退后了？上下文是否靠前了？
> 如果页面第一眼仍是菜单和功能分区，而不是当前工作区与对象，就还不够 terminal。

---

## 14. 壳层反模式清单

以下情况出现任意 **3 条以上**，通常说明壳层选错了或壳层被污染了：

- [ ] 首页长得像 Research 页面
- [ ] Strategy Editor 长得像目录页
- [ ] Platform settings 长得像交易终端
- [ ] Object Hub 退化成普通详情页
- [ ] 所有页面都保留底部 analysis band
- [ ] 所有页面右侧都硬塞 activity stack
- [ ] Catalog 页被图表挤压，反而表格不是主角
- [ ] Studio 页中间工作面不够大
- [ ] Command Center 变成卡片墙
- [ ] Operations Console 过度"金融大屏化"

---

## 15. 验收标准

一套合格的 Ditto Shell Family，必须满足：

- [ ] 任意页面都能清楚归类到某种 Shell
- [ ] 同类页面骨架一致，不同类页面边界清楚
- [ ] 全站导航始终弱于工作区上下文
- [ ] 页面主工作面始终明确
- [ ] 页面右侧区的角色不混乱
- [ ] 分析带、详情区、配置区、日志区各归其位
- [ ] 从首页到 AI Agent 到平台运维，整体仍然像同一个产品
- [ ] 既有 terminal 的专业感，也有复杂平台应有的角色区分
