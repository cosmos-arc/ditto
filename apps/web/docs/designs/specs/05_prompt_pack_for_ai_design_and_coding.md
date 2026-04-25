# Ditto AI 设计与 AICoding Prompt Pack

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[00 视觉宪章](./00_ditto_visual_constitution.md)、[02 核心页面蓝图](./02_core_page_blueprints.md)
> **用途**：Stitch / Claude Code / UI skills / Agent 流程的统一输入约束
> **职责**：给 Stitch、Claude Code、skills、review agents 的统一提示词和硬约束

---

## 文档目标

这份文档不是产品规范，而是"给 AI 用的工作约束包"。

它的目标是让你在 Stitch、Claude Code、各类 UI/UX skills、后续 agent 流程里，都有一套稳定输入，避免 AI 每次重新理解 Ditto。

本文件包含：

- 通用产品上下文
- 视觉与交互硬约束
- 页面设计 prompt 模板
- 代码实现 prompt 模板
- review prompt 模板
- 禁止项

---

## 1. 通用产品上下文

以下内容建议作为所有 AI 设计和 AICoding 的基础上下文：

Ditto 是一个面向个人量化研究与实盘闭环的专业工作台。
它覆盖 Home、Markets、Research、Trading、AI、Platform 六个域。

产品目标不是做成普通金融 SaaS，也不是营销感强的仪表盘，而是一个可被长期高频使用的 terminal-style workspace。

Ditto 的基本原则：

- 视觉优先服务判断、操作和长期使用
- 导航退后，上下文靠前
- 一页一个主工作面，允许一个辅工作面
- 高级感来自灰阶秩序和克制，不来自渐变、光效、卡片墙
- 颜色必须按业务语义分域
- 表、图、上下文面板都是数据工作面，不是装饰组件
- AI / Agent 也必须服从 Ditto 同一工作台语法

---

## 2. 统一硬约束

下面这些约束建议所有 AI 工具共享。

### 布局约束

- 默认暗色专业工作台
- 全局极窄 rail
- header 强于导航
- 主工作面优先，不做卡片墙
- 右侧区受控，不能抢主区
- analytical 页面允许 bottom band
- studio 页面不默认做 bottom band

### 视觉约束

- 不使用炫光、渐变背景、科技纹理
- 不使用满屏高饱和色
- 不使用 SaaS 风格大圆角大阴影卡片
- 不做聊天气泡式 AI 主界面
- 不做 marketing hero 风格标题区

### 交互约束

- 列表必须支持 selected row
- 表、右侧、底部要能联动
- 重要状态不能只靠颜色
- critical 反馈不能只用 toast
- 每页主 CTA 不超过 1 个强 primary

### 工程约束

- 先复用 shell / panel / table / action 体系
- 不擅自发明新页面模式
- 不直接写死一堆私有视觉变量
- 新组件必须说明属于哪一类角色

---

## 3. 给 Stitch / 设计探索工具的 Prompt 模板

### 3.1 页面探索模板

把下面这段作为基础模板：

> 请为 Ditto 设计一个专业量化 terminal-style workspace 页面。
> 目标用户是高频研究和交易的个人量化开发者。
> 页面必须优先服务判断、操作和长期使用，不是 SaaS 卡片墙，也不是营销首页。
> 布局要求：极窄左 rail、强 header、清楚的主工作面、受控的右侧辅助区、必要时的底部分析带。
> 视觉要求：暗色、低噪声、灰阶秩序、克制强调色、专业终端气质。
> 不要使用大面积渐变、光效、科幻纹理、强卡片边界、聊天气泡。
> 输出重点是布局、信息层级、主辅关系和 terminal 感，而不是装饰细节。

### 3.2 针对具体页面时再补充

例如 Research Workspace：

> 主工作面是因子监控主表，右侧是 recent runs 和 review queue，底部是 IC trend / breadth / diagnostics。
> 页面目标是让研究者先看到哪些因子退化、哪些 run 刚完成、下一步该点哪里。

例如 Orders Ledger：

> 主工作面是订单流水表，右侧是 order trace，包括状态时间线、失败原因、费用与 route 日志。
> 这不是普通列表页，而是 ledger / execution console，不适合使用 research 风格 activity stack。

---

## 4. 给 Claude Code 的页面实现 Prompt 模板

### 4.1 页面骨架实现模板

> 基于 Ditto 既有 shell family 和 component spec，实现一个页面骨架，不发明新页面模式。
> 先输出 layout 结构和组件装配关系，不要先补视觉细节。
> 明确说明：header、strip、main、right、bottom 各自放什么。
> 优先复用已有 panel、table、context、visual 容器。
> 如果某处需要新组件，必须先说明它属于哪个组件角色家族。

### 4.2 组件实现模板

> 实现 Ditto 的组件时，先说明该组件属于哪一类角色：panel、action、badge、context、overlay、agent。
> 不要把所有 panel 做成 card，不要把所有标签做成 badge。
> 实现时优先引用语义 token，不要直接写色值。

### 4.3 页面装配模板

> 把该页面装配为 Ditto 风格的工作台页面。
> 要求：主工作面明确，辅工作面受控，右侧不抢主区，状态完整，selected row 可联动。
> 只做页面级真实布局和组件组合，不要额外扩展产品功能。

---

## 5. 给 Reviewer Agent 的评审 Prompt 模板

### 5.1 视觉评审模板

> 请从 Ditto terminal workspace 的标准审查该页面。
> 重点检查：
> 1. 是否像专业工作台，而不是卡片墙
> 2. 主工作面是否清楚
> 3. 右侧区是否抢主区
> 4. 状态是否完整
> 5. 是否出现 SaaS 化、营销化、聊天化倾向
> 6. 是否有多余装饰而非工作流增强

### 5.2 产品评审模板

> 请只从产品工作流角度评审该页面：
> 是否真的服务该页面目标，是否和上下游页面跳转顺畅，是否把多个任务混在一页，是否存在可以合并或降级的区块。

### 5.3 工程评审模板

> 请从设计系统和代码复用角度评审该页面：
> 是否复用了既有 shell、panel、table、actions、tokens；是否擅自创造新模式；是否存在写死样式或私有视觉逻辑。

---

## 6. 给 AI 产图 / UI Skill 的禁止项清单

所有 AI 设计探索时，默认禁止：

- hero landing page 风格
- dashboard card wall
- 大面积 gradient
- 发光边框
- 赛博 HUD 线条
- 过多彩色胶囊标签
- 普通聊天产品气泡 UI
- 白底企业后台风
- 每个区块都像独立完整组件
- 右侧栏做得和主区一样重
- 为了"完成度"增加无意义 summary cards

---

## 7. Claude Code 子代理建议

建议你在 Claude Code 中建立这些角色。

### product-page-architect

职责：

- 把页面蓝图翻译成代码级布局骨架
- 不做视觉发明

### design-system-implementer

职责：

- 实现 shell、panel、table、action、badge、token 映射
- 不做产品决策

### workspace-ui-builder

职责：

- 用既有组件装配某个页面模板
- 不发明新模式

### reviewer-terminal-ux

职责：

- 检查是否退回后台风、卡片墙、聊天风

### reviewer-product-flow

职责：

- 检查页面是否破坏闭环工作流

---

## 8. 推荐工作流

### 第一步

先用本包 + 页面蓝图去做视觉探索。只探索核心 6 页。

### 第二步

选定方向后写 token alpha。

### 第三步

进入 Claude Code。先做 shell 和基础组件，再做 3 个 coded pages。

### 第四步

基于 coded pages 修 token beta 和 component spec。

### 第五步

扩展到剩余核心页面。

---

## 9. 一句话使用说明

任何 AI 参与 Ditto 设计或编码前，都先给它：

1. `DESIGN.md`（设计系统描述 — 先读这个）
2. Ditto Visual Constitution
3. Shell Family / Page Pattern / Data Views / Component / Token 规范
4. 本 Prompt Pack
5. 当前目标页面的 blueprint

这样 AI 才是在"翻译你的系统"，而不是"替你发明一个新产品"。
