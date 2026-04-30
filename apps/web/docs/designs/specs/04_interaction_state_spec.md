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

---

## 13. 页面状态映射示例

> 本章节展示如何将第 1 节的 15 种通用状态映射到具体页面组件。
> 完整的 Component × State Matrix 见 [02 核心页面蓝图](./02_core_page_blueprints.md)。
> 此处选取 4 个代表性页面，覆盖"列表筛选 / 对象详情 / 结果展示 / 长任务审批"四种页面类型。

---

### 13.1 列表筛选型 — Markets Screener

| 组件 | default | hover | selected | loading | empty | failed | stale | bulk | compare |
|------|---------|-------|----------|---------|-------|--------|-------|------|---------|
| 筛选条件面板 | 展示当前条件 | 条件项 hover | — | 面板整体 loading | 无默认条件时展示"添加筛选条件" | 加载筛选预设失败 | 条件面板显示"条件可能过时" | — | — |
| 结果表格 | 展示筛选结果 | 行 hover 背景变深 | 行高亮 + 右侧面板刷新 | skeleton 行 × N | "无符合条件的结果，调整筛选条件" + 清除筛选 CTA | "加载失败" + 重试按钮 | 整表黄色边框 + "数据已 X 分钟未刷新" | 多选栏 + 批量操作 bar | 对比勾选 + 对比 bar |
| 右侧详情面板 | 无选中时 placeholder | — | 展示选中标的信息 | 面板 skeleton | — | "详情加载失败" | — | — | 展示对比结果 |
| 排序/分页 | 展示当前排序 | 排序项 hover | — | — | — | — | — | — | — |

**关键映射说明**：
- `bulk` 和 `compare` 是 Screener 特有的模式状态，需与 `selected` 区分（selected 是单选，bulk/compare 是多选后进入的特殊模式）
- `stale` 用黄色边框 + 时间戳提示，不阻止操作但提醒用户
- 筛选面板的 `empty` 不是"无数据"，而是"无筛选条件"的引导态

---

### 13.2 对象详情型 — Instrument Hub

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| 行情 Tab — 价格面板 | 实时价格 + K 线 | 价格区 skeleton + K 线骨架 | 非交易时段显示"休市中" | "行情数据加载失败" + 重试 | 黄色闪烁 + "数据延迟 Xs" | Tab 高亮 |
| 财务 Tab — 利润表 | 三年利润表数据 | 表格 skeleton 行 | "暂无财务数据" | "财务数据加载失败" | — | Tab 高亮 |
| 公告 Tab — 公告列表 | 公告时间线 | 列表 skeleton | "暂无公告" | — | "有 N 条新公告未展示" | Tab 高亮 |
| 关联 Tab — 关联模型 | 模型列表 + 收益 | 列表 skeleton | "暂无关联模型" | — | "模型评分已更新" | Tab 高亮 |
| Watchlist 按钮 | "+ 加入观察列表" | disabled | — | — | — | — |
| 快速下单按钮 | 可点击下单 | disabled | — | — | — | 选中标的后 enabled |

**关键映射说明**：
- Hub 类页面的 `selected` 主要体现在 Tab 切换上
- `stale` 在行情类组件中用闪烁效果强化，与其他页面的黄色边框不同
- 交易时段外的 `empty` 是业务语义的空（休市），不是错误
- Watchlist / 下单按钮在数据未就绪时为 `disabled`（blocked 的轻量形式）

---

### 13.3 结果展示型 — Backtest Result

| 组件 | default | loading | empty | failed | stale | running | partial |
|------|---------|---------|-------|--------|-------|---------|---------|
| 概览 Tab — 指标卡片 | 收益/风险/回撤等 KPI | 卡片 skeleton | "选择一次回测查看结果" | — | — | — | — |
| 收益曲线 Tab — 图表 | 净值曲线 + 基准对比 | 图表骨架 | "无收益数据" | "图表渲染失败" | — | 进度指示（增量加载） | 部分日期数据可用时显示已有部分 + 灰色占位 |
| 交易记录 Tab — 表格 | 全部交易记录 | 表格 skeleton | "回测期间无交易" | — | — | 显示已生成的交易 | "仅显示前 X 笔，完整数据生成中" |
| 风险分析 Tab | VaR / 最大回撤 / 蒙特卡洛 | 分析骨架 | "风险数据不足" | — | — | — | "部分风险指标计算中" |
| 因子暴露 Tab | 因子载荷热力图 | 热力图骨架 | "无因子暴露数据" | — | — | — | — |
| 回测任务状态 | completed / failed | queued → running | — | failed + 错误详情 | — | progress bar + ETA | — |

**关键映射说明**：
- Backtest 是唯一需要 `running` + `partial` 组合的页面（回测进行中，部分结果已可用）
- `partial` 在这里不是错误，而是"已完成部分可预览"的体验
- 概览的 `empty` 是"无选中回测"，不是"数据为空"
- 收益曲线的 `loading` 可以是增量式的（新数据逐段加入）

---

### 13.4 长任务/审批型 — Agent Console

| 组件 | default | loading | empty | failed | stale | running | blocked | waiting-approval |
|------|---------|---------|-------|--------|-------|---------|---------|-----------------|
| Agent 列表 | Agent 状态卡片 | 列表 skeleton | "暂无配置的 Agent" | "Agent 列表加载失败" | Agent 状态标记过时 | 绿色脉动 + "运行中" | 红色 + "已阻断" | 黄色 + "等待审批" |
| Agent 详情 — 输出流 | 展示执行输出 | 首次加载 skeleton | "Agent 尚未运行" | "输出加载失败" | "输出最后更新于 XX" | 流式输出（逐行追加） | 阻断原因展示 + 重新排队按钮 | 审批操作面板 |
| 审批操作面板 | 隐藏 | — | — | — | — | — | — | 显示 Approve / Reject / Comment |
| Pipeline 时间线 | 历史 Pipeline | 时间线 skeleton | "暂无 Pipeline 记录" | — | — | 当前节点高亮 + 脉动 | 红色节点 + 错误信息 | 黄色节点 + "等待审批" |
| Agent 置信度 | 显示置信度评分 | 评分区 skeleton | — | — | "置信度模型已过期" | 动态更新 | — | — |

**关键映射说明**：
- Agent Console 是 `blocked` + `waiting-approval` 两种状态的核心使用场景
- `running` 在 Agent 场景中是长时间持续的，需要脉动动画而非进度条
- Pipeline 时间线的每个节点都有独立状态（pending/running/success/failed/blocked）
- 审批面板的显隐由 `waiting-approval` 状态驱动，不是由用户主动打开
- `stale` 在 Agent 场域中可能意味着底层模型版本过旧，风险更高

---

### 13.5 映射规则总结

| 通用状态 | 列表筛选型 | 对象详情型 | 结果展示型 | 长任务/审批型 |
|---------|-----------|-----------|-----------|-------------|
| default | 结果行展示 | Tab 默认内容 | KPI 卡片 | Agent 状态卡片 |
| hover | 行背景变深 | Tab hover | 卡片 hover | 卡片 hover |
| selected | 行高亮+面板联动 | Tab 高亮 | — | Agent 选中 |
| loading | 表格 skeleton | 面板 skeleton | 图表/表格 skeleton | 列表 skeleton |
| empty | "无结果"+CTA | 业务语义空 | "无选中回测" | "暂无 Agent" |
| failed | 错误+重试 | 错误+重试 | — | 错误详情 |
| stale | 黄色边框 | 闪烁+延迟提示 | — | "模型已过期" |
| running | — | — | 进度指示 | 脉动+流式输出 |
| partial | — | — | 部分可预览 | — |
| blocked | — | 按钮 disabled | — | 红色+阻断原因 |
| waiting-approval | — | — | — | 审批面板 |
| bulk | 批量操作 bar | — | — | — |
| compare | 对比 bar | — | — | — |

> 此表为映射规则的模式总结，实际每个页面的 Component × State Matrix 见 [02 核心页面蓝图](./02_core_page_blueprints.md)。

---

## 14. 折叠面板交互规范

### 14.1 适用场景

Ditto 采用单视窗锁定布局（`body { overflow: hidden }`），面板内信息密度高时需通过折叠管理可见空间。

适用于所有含多 section 的右侧面板/侧栏：
- Catalog Detail（Screener）
- Hub Sidebar（Instrument Hub）
- Ops Detail（Platform）
- Activity Stack（Trading Overview, Cross-Market）

### 14.2 折叠状态定义

| 状态 | 视觉 | 可见内容 |
|------|------|---------|
| **expanded** | 标题 + 完整内容 | 全部子元素 |
| **collapsed** | 标题 + 计数 badge | 仅 header 行 |

### 14.3 交互规则

- **触发**: 点击 section header 任意位置
- **指示器**: header 左侧 `▶`（collapsed）/ `▼`（expanded），8px，0.15s rotation transition
- **计数 badge**: collapsed 时在 header 右侧显示内容计数（如 `3`、`5 条`）
- **动画**: body 区域 `max-height` transition 或 `display: none`（原型用 `<details>/<summary>`）

### 14.4 默认展开/折叠规则

| 优先级 | 默认状态 | 判断依据 |
|--------|---------|---------|
| 高频核心 | **展开** | 当前任务必需的信息（信号、评分、备注） |
| 低频补充 | **折叠** | 偶尔查看的信息（筛选预设、关联研究、历史） |
| 空状态 | **折叠** | 无内容时折叠以节省空间 |

### 14.5 空间预算约束

1080px viewport 下的目标：
- 面板总可见内容 ≤ 500px（含 sticky 顶栏）
- 核心任务信息在不滚动情况下可见 ≥ 80%
- 低频信息通过 1 次点击可达

### 14.6 上下文感知联动

Object Hub 的 sidebar section 可根据当前 tab 联动展开/折叠：

- 与当前 tab 内容相关的 section → 自动展开
- 不相关的 section → 自动折叠
- 用户手动操作优先（如果用户手动展开过，tab 切换时不自动折叠）

> 原型阶段：使用 CSS `:has()` + checkbox 实现基础联动。
> 生产阶段：通过前端框架状态管理实现完整的用户偏好持久化。

---

## 15. Signal 专属状态

### 状态定义

| 状态 | 说明 | UI 表现 |
|------|------|---------|
| pending | 等待处理 | 灰色标签 |
| reviewing | 用户正在复核 | 蓝色标签 + 详情面板展开 |
| approved | 已确认 | 绿色标签 |
| signal-generated | 已生成信号 | 青色标签 |
| order-submitted | 已提交订单 | 橙色标签 + 关联订单号 |
| completed | 订单已完成 | 绿色标签 + 成交确认 |
| expired | 信号已过期 | 灰色删除线 |
| failed | 失败 | 红色标签 + 失败原因 |

### 状态回退

- `order-submitted → reviewing`: 订单失败时自动回退，展示失败原因
- `approved → reviewing`: 用户取消已确认信号时回退，需二次确认
- `pending → expired`: 超过有效期自动过期
- `reviewing → expired`: 复核中超时自动过期
- `approved → expired`: 已确认但未及时执行时过期
- `signal-generated → expired`: 已生成信号但超时未提交订单时过期

### 与通用状态的关系

Signal 专属状态映射到通用状态（§1）：
- `pending` / `expired` → `default`
- `reviewing` → `active`
- `failed` → `failed`
- 订单生成中 → `running`

---

## 16. Bottom Tray 与高风险确认合同（2026-04-29）

### 16.1 Bottom Tray 状态

Bottom Tray 只用于日志、验证结果、执行状态和运行追踪，不用于承载主工作面内容。

| 状态 | 可见内容 | 默认场景 |
|------|----------|----------|
| `collapsed` | 状态摘要、关键计数、展开入口 | Ops / Trading 的低风险常态 |
| `peek` | 一行最新状态、当前错误、展开入口 | Studio、紧凑视口、存在活跃任务 |
| `expanded` | 完整日志、验证、dry run、trace | 用户主动排查或复盘 |

实现合同：

- 容器暴露 `data-bottom-tray`。
- 当前状态写入 `data-bottom-tray-state="collapsed|peek|expanded"`。
- 切换控件暴露 `data-bottom-tray-toggle` 与 `aria-controls`。
- 内容区域暴露 `data-bottom-tray-content`。
- 默认态必须在文档流内，不得用 fixed overlay 遮挡主工作面。

### 16.2 高风险动作确认

以下动作必须进入确认链路：交易提交 / 暂停 / 批量撤单、配置保存 / 回滚 / diff apply、Catalog 删除 universe / strategy / watchlist 批量删除。

确认链路必须包含：

- 影响摘要：`data-impact-summary`。
- 明确确认：`data-confirm-control`。
- 明确取消：`data-cancel-control`。
- 恢复或回滚提示：`data-recovery-hint`。
- 非颜色危险标记：`data-danger-marker` 或等价 icon / 边界 / 文案。

危险态不能只靠红色表达；必须同时使用文字、符号或边界强化。
