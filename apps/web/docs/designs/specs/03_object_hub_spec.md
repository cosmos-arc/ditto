# Ditto 对象页统一规范

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[02 核心页面蓝图](./02_core_page_blueprints.md)
> **下游**：[12 Data Views 规范](./12_ditto_data_views_spec.md)、[13 Component Spec](./13_ditto_component_spec.md)
> **适用页面**：Instrument Hub、Factor Analysis、Backtest Result、Strategy Studio（对象视角）
> **职责**：统一资产、因子、策略、回测、实验等所有对象页的语法、骨架、信息层级和交互约定

---

## 文档目标

Ditto 中的对象页包括：

- 资产
- 因子
- 策略
- 回测结果
- 实验
- 后续可能还有模型、Agent、数据源

这些页面不应该分别设计成不同风格的详情页，而应该共享统一的对象页语法。

本规范的目标，是定义对象页的统一结构、信息层级、区块规则和交互约定。

---

## 1. 对象页的角色定义

对象页不是"资料展示页"，而是围绕一个对象的工作中心。

用户进入对象页后，应该能快速回答：

- 这个对象当前状态怎样
- 这个对象最值得先看什么
- 最近发生了什么
- 我可以对它做什么
- 它与哪些对象相关

---

## 2. 对象页统一骨架

所有对象页默认采用以下骨架：

1. Object Header
2. Object Meta / KPI Strip
3. Tab Navigation
4. Main Panels
5. Related / History / Notes
6. Timeline / Diagnostics / Linked Artifacts

### 标准结构

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Object Header                                                │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Meta / KPI Strip                                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Tab Navigation                                               │
│      ├───────────────────────────────┬───────────────────────────────┤
│      │ Main Panels                   │ Related / History / Notes     │
│      ├───────────────────────────────┴───────────────────────────────┤
│      │ Timeline / Diagnostics / Artifacts                           │
└──────┴───────────────────────────────────────────────────────────────┘
```

---

## 3. Object Header 规范

### 角色

说明这个对象是谁、现在怎样、可以做什么。

### 必含元素

- 对象名称
- 对象类型
- 核心状态
- 关键身份信息
- 2-4 个高价值动作

### 允许出现的内容

- 名称 / 代码 / 版本 / family / strategy type
- 当前价格 / 当前状态 / 当前版本
- 标签
- 当前所属范围
- 高价值 CTA

### 不建议出现的内容

- 大量元信息堆在 header
- 长表单
- 太多平权按钮
- 解释性长段落

### 示例

资产：名称、代码、行业、价格、涨跌、状态

因子：名称、family、状态、版本、coverage

策略：名称、类型、版本、状态、当前 mode

回测：Run ID、策略、版本、区间、状态

---

## 4. Meta / KPI Strip 规范

### 角色

在 header 之后，用一行低高度高信息密度区域，补充对象的当前关键指标和元信息。

### 适合放的内容

- 关键 KPI
- 更新时点
- 当前状态 tags
- 关联对象数量
- owner / environment / market
- active signals / linked runs / coverage

### 不适合放的内容

- 太大数字卡
- 很强视觉卡片
- 多行复杂说明

### 原则

- 这一层要"轻但有用"
- 优先像 strip，不优先像 KPI 卡墙

---

## 5. Tab Navigation 规范

### 角色

承接对象的主要视角切换。

### 规则

- 4-8 个 tab 为宜
- 顺序从"最常看"到"更细节"
- 不把很少用的视图放在前面
- tab 名称要专业、简短、稳定

### 通用排序原则

概览类在前，深入分析居中，历史与诊断靠后。

### 示例

资产：概览 → 行情 → 资金面 → 基本面 → 新闻 → 网络 → 公告

因子：IC → 收益 → 分布相关 → 换手

策略：运行历史 → 因子依赖 → 笔记 → 实盘表现 → 风控 → 版本

回测：概览 → 收益 → 风险 → 交易 → 归因 → 诊断

---

## 6. Main Panels 规范

### 角色

对象页的主判断区。这里必须明确主次，不允许很多面板平权竞争。

### 规则

- 同屏默认 1-3 个主 panel
- 允许 2x2，但只能在分析型对象页使用
- 主 panel 必须说明"当前对象最重要的判断是什么"

### 典型组合

#### 资产对象页

主 panel：主行情 / 结构视图

辅 panel：资金面 / 基本面摘要

#### 因子分析页

主 panel：IC / IR 相关诊断

辅 panel：decay / corr / dist

#### 策略页

主 panel：performance / linked results

辅 panel：risk / regime fit / active signals

#### 回测页

主 panel：NAV / drawdown

辅 panel：attribution / trades / diagnostics

---

## 7. Related / History / Notes 区规范

### 角色

右侧承接与当前对象相关但不应抢主区的信息。

### 适合内容

- linked entities
- recent signals
- recent runs
- related strategies
- owner notes
- AI notes
- version history
- recent events

### 不适合内容

- 再来一张大图
- 再放一个重表
- 做成 activity stack 拼贴墙

### 原则

- 围绕对象强相关
- 支持 drill-down
- 强调"关系"和"最近发生了什么"

---

## 8. Timeline / Diagnostics / Artifacts 规范

### 角色

放在对象页底部，承接历史、日志、事件、诊断和产物。

### 适合内容

- 事件时间线
- 版本变更
- 诊断日志
- 关联文件 / 报告 / 输出
- 工具运行结果
- 相关审批 / findings

### 原则

- 默认弱于主 panel
- 但必须是对象理解的重要延伸
- 不应做成"杂项收纳区"

---

## 9. 对象页动作分层

### 一级动作

2-4 个即可，放在 Object Header 右侧。

### 二级动作

放在 more menu 或右侧 related 区。

### 常见一级动作

资产：加入观察、加入标的池、打开 Chart Lab、发送到研究

因子：加入回测、加入实验、固定到研究台

策略：打开 Studio、运行回测、克隆

回测：加入对比、导出报告、克隆为实验

---

## 10. 对象页交互约定

- tab 切换不改变对象上下文
- related item 点击可以切换当前对象或打开新对象页
- timeline 点击应能打开 detail 或高亮相关 panel
- 右侧 notes / history 应随对象刷新
- URL 必须稳定指向对象，不依赖菜单入口

---

## 11. 验收标准

一个合格的对象页，必须满足：

- 进入后能一眼认出对象是谁
- 主 panel 非常清楚
- tab 排序合理
- 右侧 related / history 有用但不抢主区
- 底部 timeline / diagnostics 真正帮助理解对象
- 对象动作简洁高价值
- 与列表页、Studio、Trading、AI 之间跳转顺畅
