# Ditto 交互与状态规范

> **版本**：v1.2
> **日期**：2026-11-08
> **状态**：当前任务与反馈要求已补订；历史布局示例不代表新版视觉签收
> **产品范围**：[PRODUCT](../../PRODUCT.md) 及其链接的已确认决议；新增 ML/Agent 能力后置
> **上游**：[02 核心页面蓝图](02_core_page_blueprints.md)、[03 对象页统一规范](03_object_hub_spec.md)
> **下游**：[13 Component Spec](13_ditto_component_spec.md)
> **适用范围**：本版传统工作台任务及既有安全状态；Agent 专节保留为已有能力参考，不新增本版任务
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

## 0. 当前任务与动作合同

每个主工作面应让用户理解当前对象、业务状态、影响范围和下一步。具体布局与主辅动作由[信息架构](https://github.com/cosmos-arc/ditto/issues/730)和[交互原型](https://github.com/cosmos-arc/ditto/issues/731)验证；不强制每页凑一个数字、固定数量的证据卡或右栏。

既有页面合同中的结构标记继续按机器约束维护，通过既有生成器调整；marker 存在只证明结构，不证明任务完成或视觉质量。原“5 秒”“1 primary + 2 context”作为历史设计意图参考，不独立构成本版本的时间门槛或布局签收。

### 动作兑现

- 保存、加入比较、固定、导出和完成提示都对应实际结果；失败或仍在提交时不能显示成功。临时会话状态与持久保存须明确区分。
- 保存后可重新打开同一对象；保存筛选条件与冻结一次候选结果是不同动作。比较入口指向真实比较集合，列表与详情保持一致。
- 链接进入有效页面并携带已有对象/版本/运行上下文。非核心未实现动作移除或明确禁用并说明原因，核心动作须补齐。
- 每项操作明确失败影响、是否已写入及下一步；账户重复提交/导入和更正按后端幂等与账本事实处理，UI 不猜测成功。

### 上下文与身份

- 证券通过名称/代码检索与已有身份解析进入任务；策略版本、运行和账户通过业务对象选择。内部 ID、hash、原始 JSON 不作为普通路径必填项，受控公式/业务规则可编辑。
- 复用已有 URL、保存对象和偏好机制，按任务补齐列表筛选/排序/选中行/返回位置、图表范围及比较集合；不为此先建设通用上下文平台。
- 对象、观察日期、信息截止、策略版本、运行及账户身份分别保存和传递。历史运行的冻结时间不被全局“今天”覆盖；需要对齐时显式说明日期与口径。
- 精确来源与时间身份由系统维护并可下钻，普通受限研究、严格历史资格与 Paper 资格分别表达，互不自动授予。

### 按任务留证

每条必选任务记录起始数据/版本、操作、可核结果、适用失败与恢复、截图或导出证据。保存以重开验证，账户以事件与余额对账，研究以版本、范围及结果口径核对。功能、数据表达、视觉质量、返回/恢复连续性分别判断；本人连续日用周期在逐任务验收后再定。

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
- selected 必须驱动已选方案中的关联详情或图表刷新，不预设详情必须位于右侧
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
请求终止失败或因证据不足被阻断时，必须退出 loading；提示影响对象/用途、原因和可执行下一步。仍合格的其他任务可继续，不能吞掉当前任务的缺证。

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
- sync jobs
- pipelines
- Paper 任务

已有 model training / agent run 的保护继续适用，但不作为本版本新增任务。

### 表达方式

- inline status
- progress bar
- queue item
- banner
- timeline node

### 原则

- running 不能只靠 toast
- 必须持续存在，直到结束
- 可离开页面后重新找到任务及其实际状态；页面刷新不应被表示为任务取消
- 进度与预计剩余时间仅在有可靠依据时显示，未知时明确正在处理

---

## 6. Stale / Warning / Critical 规范

### Stale

表示数据过时、状态未刷新、结果存在时效风险。
按源更新频率、交易日历和用途判定，详见 [DESIGN 的数据时效](../../DESIGN.md#data-freshness)。后端连接、最近完整交易日、指标公布日和任务资格分别表达，不用固定 LIVE/已连接/延迟替代。休市不等于数据为空，历史结果不会仅因时间流逝而失效。

现有工作面的连接栏显示 API 最近一次检查的本地日期与时间，支持重新检查；检查失败不能保留成功文案。样例模式明确标注未检查 API。连接检查通过不代表市场资料、某项研究或账户用途已就绪，局部阻断在对应工作面说明并提供可用的重试动作。没有实际测量不显示延迟。

首页的交易阶段只使用已提供的阶段事实，区分集合竞价、盘中、午间休市、收盘与盘后；未提供时显示不可用，不按浏览器时钟推断交易日。当前正式首页聚合尚未提供交易阶段与运行任务数，因此两者保持不可用；任务目录继续显示各任务实际状态。通知、帮助和全局命令尚未接通时须说明不可用，不显示未读红点、失效快捷键或成功提示。

### Warning

表示需要关注，但不一定立即处理。

### Critical

表示影响判断、交易、系统安全或审批链，必须优先处理。

### 原则

- stale 不是 failed
- warning 不是 critical
- critical 必须持续可见
- 不可把这三者都压成同一种黄色提醒
- stale 文案、业务 freshness、队列时间、执行时间戳、交易/风险表格 metadata 属于 operational 文本，必须满足 4.5:1；优先使用 `text-data-stale` 或 `text-secondary`
- 可选时间戳、装饰性 caption、图例标签、inactive tab 与 chip type 属于 metadata，可使用 `text-tertiary` 或 `text-quaternary`
- `text-tertiary` 与 `text-quaternary` 只能用于低风险 metadata 或装饰性说明，不得承载 stale / warning / critical 判断
- disabled affordance 可使用 `text-disabled`，但 disabled 文案不得替代 blocked / failed / stale 的原因说明
- critical、交易、审批、风险和错误状态不得只靠颜色表达，必须同时提供 icon、边界、文案或 `data-danger-marker` 等非颜色标记

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

成功反馈只能由相应动作结果触发。读到页面、弹层打开、复制 ID 或请求已受理不等于保存完成、已加入比较或任务执行完成。

---

## 8. Toast / Banner / Inline / Blocker 的分工

### Toast

只用于短平快动作反馈。
不能承载重要风险或长任务状态。

### Banner

用于页面级重要信息。例如：

- data stale
- backend unavailable
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
- 有选中行的页面必须暴露 `data-selected-object-region`，至少标记主列表与详情 / 证据 / 处置区域中的一个可联动区域
- 表格专家操作必须使用声明式 contract：`data-table-column-resize-ready`、`data-table-freeze-ready`、`data-row-context-menu-ready`
- 可批量操作的区域必须暴露 `data-bulk-action-bar`；当前筛选摘要必须暴露 `data-active-filters-summary`

### Expert Efficiency Contracts

- 可调面板的 separator 使用 `role="separator"`，方向键默认按 40px 调整，`Shift + Arrow` 按 8px 微调，双击恢复默认值
- 面板尺寸偏好按 route + CSS var 持久化：`ditto:prototype:layout:{pathname}:{varName}`，恢复时必须校验 min / max
- Header command trigger 必须暴露 `data-command-scope`
- 当页面存在当前选中对象时，必须在同一 contract 上暴露 `data-command-context-object` 与 `data-command-context-actions`，后者值为逗号分隔的上下文动作 id
- 原型 command surface 打开时只展示可见建议项，建议项使用 `data-command-suggestion` / `data-command-action`，并保持键盘可达；完整执行逻辑进入 React backlog
- 代表性上下文动作 id 必须保持稳定：
  - Home: `review-signal`, `open-risk`, `open-orders`, `explain-priority`
  - Watchlist: `generate-signal`, `open-instrument-hub`, `send-to-research`, `remove-watch`
  - Strategy List: `run-backtest`, `clone-strategy`, `view-recent-runs`, `pause-strategy`
  - Backtest List: `add-to-compare`, `view-curve`, `copy-params`, `generate-report`
  - Signals Inbox: `approve`, `reject`, `send-to-order`, `view-evidence`
  - Platform: `retry`, `view-logs`, `mute-alert`, `create-incident`
- 原型只声明 contract 与静态 affordance；列持久化、冻结列与对象联动状态进入 React 实现

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

## 12. 任务验收记录

对本批任务的适用状态留证，不把所有页面、状态与视口做笛卡尔积：

- [ ] 正常路径从入口到结果完整，保存/比较/导出兑现，可重新找到结果
- [ ] 首次使用、无结果、缺失/过期、运行中、失败/阻断及必要恢复按任务覆盖；不适用项说明理由
- [ ] 原始数值、单位、复权、费用、基准、时间与用途表达一致；不能靠零值或示例数据填补缺失
- [ ] 账户操作能对账、更正和追溯；Paper 与 Manual 分别完成任务验收
- [ ] 选中对象与返回状态连续，键盘可达、焦点可见、关键状态不只靠颜色
- [ ] 主用及较窄桌面上的真实工作面经维护者认可；固定样例与 live 复用正式呈现及状态合同，证据类型分开记录

固定样例用于可复现视觉/异常验证，真实 API 操作用于结果与恢复验证；两者不能互相冒充。现有 PIT、账本、契约与可访问性门保留，改动按影响范围验证。完整灾备与后续真人日用周期沿产品范围另行安排。

---

## 13. 页面状态映射示例

> 本章节展示如何将第 1 节的 15 种通用状态映射到具体页面组件。
> 完整的 Component × State Matrix 见 [02 核心页面蓝图](02_core_page_blueprints.md)。
> 此处选取 4 个代表性页面，覆盖"列表筛选 / 对象详情 / 结果展示 / 长任务审批"四种页面类型。

---

### 13.1 列表筛选型 — Markets Screener

| 组件 | default | hover | selected | loading | empty | failed | stale | bulk | compare |
|------|---------|-------|----------|---------|-------|--------|-------|------|---------|
| 筛选条件面板 | 展示当前条件 | 条件项 hover | — | 面板整体 loading | 无默认条件时展示"添加筛选条件" | 加载筛选预设失败 | 条件面板显示"条件可能过时" | — | — |
| 结果表格 | 展示筛选结果 | 行 hover 背景变深 | 行高亮 + 关联详情刷新 | skeleton 行 × N | "无符合条件的结果，调整筛选条件" + 清除筛选 CTA | "加载失败" + 重试按钮 | 标注数据截止、缺失范围及受影响操作 | 多选栏 + 批量操作 bar | 对比勾选 + 对比 bar |
| 右侧详情面板 | 无选中时 placeholder | — | 展示选中标的信息 | 面板 skeleton | — | "详情加载失败" | — | — | 展示对比结果 |
| 排序/分页 | 展示当前排序 | 排序项 hover | — | — | — | — | — | — | — |

**关键映射说明**：
- `bulk` 和 `compare` 是 Screener 特有的模式状态，需与 `selected` 区分（selected 是单选，bulk/compare 是多选后进入的特殊模式）
- `stale` 用日期、范围和用途说明；阻断哪些动作由实际资格决定，不能统一只提醒或一律阻断
- 筛选面板的 `empty` 不是"无数据"，而是"无筛选条件"的引导态

---

### 13.2 对象详情型 — Instrument Hub

| 组件 | default | loading | empty | failed | stale | selected |
|------|---------|---------|-------|--------|-------|----------|
| 行情 Tab — 价格面板 | 声明截止的价格 + K 线 | 价格区 skeleton + K 线骨架 | 无所选范围数据及下一步；休市仍显示已有行情 | "行情数据加载失败" + 重试 | 最新完整交易日/缺失范围及用途限制 | Tab 高亮 |
| 财务 Tab — 利润表 | 三年利润表数据 | 表格 skeleton 行 | "暂无财务数据" | "财务数据加载失败" | — | Tab 高亮 |
| 公告 Tab — 公告列表 | 公告时间线 | 列表 skeleton | "暂无公告" | — | "有 N 条新公告未展示" | Tab 高亮 |
| 关联 Tab — 关联模型 | 模型列表 + 收益 | 列表 skeleton | "暂无关联模型" | — | "模型评分已更新" | Tab 高亮 |
| Watchlist 按钮 | "+ 加入观察列表" | disabled | — | — | — | — |
| Paper 交接动作 | 进入资格核对与模拟任务 | disabled | — | 失败原因与下一步 | 资格失效时阻断 | 选中标的不足以授予执行资格 |

**关键映射说明**：
- Hub 类页面的 `selected` 主要体现在 Tab 切换上
- `stale` 用可读文案和日期表达，重要数据不靠闪烁或透明度降低可读性
- 休市是市场状态，与数据是否存在分别显示
- 数据未就绪时按动作分别说明限制；Paper 必须遵守其资格与审批边界，不存在真实券商下单

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
- 回测可同时需要 `running` + `partial`；只展示后端实际支持的中间结果，不虚构增量输出
- `partial` 在这里不是错误，而是"已完成部分可预览"的体验
- 概览的 `empty` 是"无选中回测"，不是"数据为空"
- 收益曲线的 `loading` 可以是增量式的（新数据逐段加入）

---

### 13.4 长任务/审批型 — Agent Console

本节为已有 Agent 界面参考，新增能力本版后置；既有审批保护保留。

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

### 13.5 研究探索型 — Alpha Explorer

本节为历史探索方案，不作为当前传统研究主线或本版新增能力要求。

| 组件 | default | loading | empty | failed | stale | running | partial | blocked | waiting-approval |
|------|---------|---------|-------|--------|-------|---------|---------|---------|-----------------|
| Search Space Config | 搜索空间表单 | 字段 skeleton | 默认模板 | 因子库加载失败 | 数据字段版本过旧 | disabled | — | 权限不足 | — |
| Exploration Stream | 候选因子卡片 | 卡片 skeleton | 配置后开始探索 | Agent 异常 + 重试 | 候选指标标记过时 | 新卡片流入 | 部分指标灰态 | 预算或权限阻断 | — |
| Pareto Frontier | 散点图 | 图表 skeleton | 空坐标 | 渲染失败 | 数据版本提示 | 实时点位加入 | 部分点位灰态 | — | — |
| Candidate Inspector | 候选详情 | 面板 skeleton | 未选中提示 | 加载失败 | 指标时间戳提示 | 指标刷新 | 部分诊断可见 | 采纳被阻断 | Approval Panel 展开 |
| Experiment Graph | lineage 图 | 节点 skeleton | 无实验 | 加载失败 | artifact 版本提示 | 节点增加 | artifact 待生成 | — | — |
| Adoption Queue | 待采纳 / 待补测 / 已拒绝 / 已入库 | 列表 skeleton | 暂无待处理 | 加载失败 | 队列状态过期 | 队列更新 | 待补测灰态 | 审批策略阻断 | 待审批置顶 |

**关键映射说明**：
- Alpha Explorer 是 `running` + `partial` + `waiting-approval` 同时出现的研究页，不能套用 Backtest 的单任务进度心智。
- `partial` 代表候选可先审阅但指标未齐，必须明确哪些指标待计算。
- `blocked` 多来自预算、工具权限、敏感字段或采纳审批策略，必须展示 Guardrail 详情入口。
- 采纳因子必须进入 `waiting-approval`，不能只用 disabled 按钮表达。

---

### 13.6 映射规则总结

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

> 此表为映射规则的模式总结，实际每个页面的 Component × State Matrix 见 [02 核心页面蓝图](02_core_page_blueprints.md)。

---

## 14. 折叠面板交互规范

### 14.1 适用场景

下列规则适用于采用单视窗布局的既有页面；新版是否使用固定右栏、底栏或内部滚动由原型任务验证，不据此锁定所有页面。面板内信息密度高时可通过折叠管理可见空间。

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

以下为历史展示映射。实际状态、转换及是否可执行以当前后端合同为准，UI 不自行回退、重新授权或产生订单；订单仅指 Paper。新增状态须通过既有契约流程更新。

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

---

## 17. 原型可访问性交互基线（Task 2）

本节定义 `prototype` 的最低交互合同。所有原型页面必须在不削弱语义的前提下通过交互契约测试与视觉 gates。

### 17.1 页面标题语义

- 每个 active page 必须且只能有一个语义 `<h1>`。
- 用于对比、风格标记、画廊标签的视觉 label 不得承担标题语义。
- 风格 label 必须设置 `aria-hidden="true"`，避免被辅助技术识别为页面标题或主内容。

### 17.2 `role="button"` 键盘激活

- 非原生按钮如果使用 `[role="button"]`，必须可通过键盘触发。
- 共享交互脚本负责为 `[role="button"]` 提供 Enter 与 Space 激活行为。
- Enter / Space 触发时必须调用目标元素的 click 行为，并阻止 Space 造成页面滚动。

### 17.3 Tabs 与 Tabpanel 合同

- 每个 tab 必须具备稳定 `id`。
- 每个 tab 必须维护 `aria-selected="true|false"`。
- 每个 tab 必须通过 `aria-controls` 指向受控面板。
- 受控面板必须具备 `role="tabpanel"`。
- 受控面板必须具备稳定 `id`。
- 受控面板必须通过 `aria-labelledby` 反向指回控制它的 tab。
- JS 驱动 tabs 必须在切换时同步维护 tab 的 `aria-selected` 与 panel 的 `aria-hidden`。
- 隐藏面板不得继续暴露为当前 active 内容；显示面板必须保持在对应 shell 的内容区域内，避免与 fixed / sticky 状态栏重叠。

### 17.4 Focus-visible 基线

- 任何移除原生 `outline` 的可交互元素，必须提供显式 `:focus-visible` ring。
- focus ring 必须同时满足键盘可见性与品牌克制度，不得弱到只依赖颜色差异。
- `hover`、`selected`、`active` 不得替代键盘 focus 表达。

### 17.5 Reduced Motion 实时合同

- 原型必须保留 `@media (prefers-reduced-motion: reduce)` 基线。
- 共享交互脚本必须监听 reduced-motion media query 变化。
- 当用户偏好变化时，`document.documentElement` 必须实时同步 `data-reduced-motion`。
- 动画、transition、reveal、状态脉动必须尊重该偏好；不得只在页面首次加载时读取一次。

### 17.6 Prototype 性能与 DOM 安全基线

- 共享交互脚本读取 CSS custom property 时必须缓存 `getComputedStyle(document.documentElement)` 结果；主题或密度变化时必须清除缓存，避免 stale token。
- 鼠标跟随类效果必须用 `requestAnimationFrame` 合并高频 pointer / mousemove 更新；每帧只读取一次 layout，并使用最后一次事件坐标。
- `data-mouse-glow` 离开后可以清除临时 inline 变量；再次进入时必须恢复 glow size / color 与背景，且继续尊重 reduced motion。
- 动态插入 compare / bulk / command 相关文本时，必须使用 `createElement` 与 `textContent`，不得用字符串拼接 `innerHTML`。
- resize 期间的 transition / animation suppression 只能限定在 shell / catalog / object 工作面内，不得使用 document-wide `html[data-resizing-panel] *`。

### 普通回测的版本与提交恢复（#736）

- 策略详情的「提交回测」复用回测列表中的普通表单，默认带入当前详情版本；版本选择、开始/结束日期、初始资金（人民币元）和实验数据许可均为本次提交的明确输入，无需协议 JSON。
- 明确版本贯穿 API、运行记录和后台执行；版本不存在时拒绝提交，不回退到最新版本。普通研究不会自动取得发布、信号或 Paper 资格。
- 提交前在当前浏览器标签页保存输入和提交身份。失败后保留输入；相同输入重试、刷新或返回后恢复同一身份，服务端回读同一持久化运行，后台执行只允许一次领取。
- 成功后保留「查看本次回测」，运行详情和回测列表从真实 API 读取状态；只有明确点击「开始另一回测」才允许以新身份再次提交。关闭标签页后通过回测列表查找。
- 浏览器无法保存提交记录时阻止新提交并说明原因。系统验收使用隔离数据和生产 UI/API 验证持久化与丢失响应恢复；不代替真实历史数据认证或人工可用性验收。

### 普通回测的会话对比集合（#737）

- 回测列表的勾选、详情的「加入对比 / 移出对比」及两处对比入口使用同一集合，以运行 ID 去重，按加入顺序保留最多 8 个运行。
- 集合保存在当前标签页的浏览器会话存储中，页面跳转和刷新后恢复；关闭标签页后结束，不是服务端保存的研究成果或跨设备收藏。每个入口都说明这个边界。
- 成功提示只在会话写入成功后出现；写入失败保留原集合并提示重试。无法恢复或内容损坏时明确提示重新选择，不把旧内容当作有效集合。
- 列表筛选、分页或刷新不自动删除所选运行。对比视图按精确 ID 读取真实 API；读取失败保留该项，允许重试或移出，等待所选运行全部读取成功后展示对比。
- 复用现有净值归一叠加、已发布报告指标及图例切换，不改变数值可比性或赋予策略资格，不依赖因子评价。日期、百分数及资金单位保持原报告口径。
- 系统验收通过正式列表与详情执行加入、移除、跳转、刷新回读、键盘打开和关闭，并读取隔离环境中真实引擎持久化的两次运行；该证据不代替真实历史数据验收或真人使用验收。
