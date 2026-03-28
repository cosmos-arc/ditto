# Ditto 交互与状态规范

> **版本**：v1.0
> **日期**：2026-03-28
> **状态**：Final
> **上游**：[02 核心页面蓝图](./02_core_page_blueprints.md)、[03 对象页统一规范](./03_object_hub_spec.md)
> **下游**：[13 Component Spec](./13_ditto_component_spec.md)
> **适用范围**：全站所有页面、组件、Studio、Agent、Ops Console
> **职责**：selected、loading、empty、running、stale、critical、approval、trace、bulk、compare 等统一状态与反馈层级

---

## 文档目标

大多数产品文档只讲页面和组件，不讲状态。

但 Ditto 这种专业工作台，真正决定体验的是状态是否完整：

- 选中了什么
- 正在运行什么
- 什么 stale 了
- 什么异常了
- 哪些动作会阻断
- 哪些反馈需要持续存在

本规范定义 Ditto 的统一交互状态与反馈层级。

---

## 1. 统一状态层级

Ditto 全站统一采用以下状态语义：

- **default** — 初始 / 正常
- **hover** — 可交互提示
- **focus** — 键盘焦点
- **selected** — 当前选中对象
- **active** — 动作进行中
- **loading** — 数据加载中
- **running** — 长任务执行中
- **success** — 操作成功
- **partial** — 部分完成 / 部分数据
- **stale** — 数据过时 / 未刷新
- **warning** — 需关注但不紧急
- **critical** — 影响判断 / 交易 / 系统安全
- **empty** — 无数据
- **failed** — 操作失败
- **blocked** — 阻断，无法继续

这些状态必须在表、图、右侧面板、Studio、Agent、Ops 中保持一致逻辑。

---

## 2. Selected 规范

### 角色

Selected 是 Ditto 最重要的交互状态之一。
因为很多页面都依赖"选中一个对象后，右侧和底部一起变"。

### 规则

- 列表页必须支持 selected row，而不是只有 hover
- selected 必须驱动右侧上下文刷新
- selected 与 active action 不是一回事
- selected 应持续存在，直到用户选中别的对象或清除选择

### 适用场景

- Screener 结果表
- Research 主表
- Signals 表
- Orders 表
- Universe 成员表
- Object Hub 内部子表

---

## 3. Hover 与 Focus 规范

### Hover

用于表达"可进一步操作或查看"，不能承担重要业务状态。

### Focus

用于键盘导航、输入和 command surface 场景。
必须统一可见，不可过度微弱。

### 原则

- hover 轻
- focus 清楚
- selected 强于 hover
- critical 强于 selected

---

## 4. Loading / Empty / Partial / Failed 规范

### Loading

- 页面骨架要稳定
- 优先 skeleton，不要全页闪烁
- 主工作面优先加载，辅区可稍后

### Empty

必须说明"为什么没有内容"，而不是只写没有数据。

### Partial

当只有部分数据拿到时，必须明确告诉用户哪些是 partial。

### Failed

失败态应尽量局部化，同时提供 retry 或 detail。

### 示例

- No matching candidates in current filter
- Partial data: flow view unavailable
- Failed to load recent runs

---

## 5. Running / Progress 规范

### 角色

承接长任务状态。

### 适用场景

- backtest
- experiment
- model training
- sync jobs
- pipelines
- agent runs
- signal to order conversion

### 表达方式

- inline status
- progress bar
- queue item
- banner
- timeline node

### 原则

- running 不能只靠 toast
- 必须持续存在，直到结束
- 能 drill-down 看 detail 更好

---

## 6. Stale / Warning / Critical 规范

### Stale

表示数据过时、状态未刷新、结果存在时效风险。

### Warning

表示需要关注，但不一定立即处理。

### Critical

表示影响判断、交易、系统安全或审批链，必须优先处理。

### 原则

- stale 不是 failed
- warning 不是 critical
- critical 必须持续可见
- 不可把这三者都压成同一种黄色提醒

---

## 7. Feedback 分级

| 层级 | 类型 | 示例 | 持续性 |
|------|------|------|--------|
| L1 | Micro Feedback | hover、selected、copy、small success | 瞬时 |
| L2 | Action Feedback | save success、export success、view saved | 短暂 |
| L3 | Running Feedback | backtest started、sync in progress、agent running | 持续到完成 |
| L4 | Risk / Alert Feedback | threshold near breach、data quality issue、model degrading | 持续到解决 |
| L5 | Blocker Feedback | order rejected、route disabled、system down、approval required | 持续到解除 |

**原则：事件越严重，反馈越不能短暂消失。**

---

## 8. Toast / Banner / Inline / Blocker 的分工

### Toast

只用于短平快动作反馈。
不能承载重要风险或长任务状态。

### Banner

用于页面级重要信息。例如：

- data stale
- broker disconnected
- validation failed

### Inline Status

用于行、panel、chart、queue item 内的局部状态。

### Blocker

用于阻断继续操作的高危情况。例如：

- order cannot be submitted
- route unavailable
- config invalid
- approval required

---

## 9. Compare / Bulk / Review 模式状态

### Compare Mode

- 明确显示当前 compare objects
- 显示退出 compare 的入口
- 所有被 compare 对象有明显但克制的标记

### Bulk Selection

- 一旦多选，出现 bulk action bar
- 清楚展示选中数量
- 提供 clear selection

### Review Mode

- 在 Signals、Approvals、Risk Review 这类场景中，review 状态必须显式，而不是只是一个普通 status

---

## 10. Timeline 与 Trace 状态

时间线中的节点必须至少区分：

- pending
- running
- success
- partial
- failed
- skipped
- cancelled

并支持：

- 当前节点高亮
- 展开 detail
- 查看 logs / raw output

---

## 11. Agent 与审批状态

### Agent Run

- idle
- queued
- running
- blocked
- waiting-approval
- partial
- failed
- completed

### Approval

- pending review
- approved
- rejected
- expired

这些状态不能混在普通聊天文本里，必须组件化表达。

---

## 12. 页面验收 Checklist

每个页面上线前，必须检查：

- [ ] 有没有 selected state
- [ ] loading / empty / failed 是否齐全
- [ ] 长任务有没有持续状态
- [ ] stale / warning / critical 是否有区分
- [ ] toast 是否被滥用
- [ ] 是否存在 blocker 场景但未被表达
- [ ] compare / bulk / review 模式是否完整
- [ ] 右侧 detail 是否能承接状态 drill-down
