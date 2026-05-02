# Prototype UI/UX Pro Max Best Review

> 日期：2026-04-30  
> 审核范围：`docs/designs/specs/prototypes/` 当前 27 个活跃原型  
> 审核模式：`/audit /ui-ux-pro-max /frontend-design /brainstorming /ditto-design-cycle --edition-review --level best`  
> 审核目标：以最严格标准评估当前原型设计，并给出交互设计、色彩系统、信息布局的系统提升建议。  
> 说明：用户提到的 `specs/prototypes` 在当前仓库中对应实际目录 `docs/designs/specs/prototypes/`。

---

## 1. 结论

当前原型已经通过多数工程化门禁，具备明确的 Shell Family、Page Pattern、共享交互合同和跨页一致性基础。它已经不是低保真草图，也不是普通后台系统，而是一套接近可落地的专业金融终端原型。

但按 Best 级标准，它还不应冻结为最终设计系统。主要短板不在“能不能用”，而在“是否足够适合专业交易员、研究员、平台运维人员长期高频使用”。当前问题集中在：

- 色彩可访问性仍有硬伤，尤其是低层级文字和部分状态文字。
- Light Mode 的数据可视化质量低于 Dark Mode，A 股结构图尤其明显。
- Catalog 家族页面语法过于接近，业务任务差异表达不足。
- 首页首屏信息较完整，但“5 秒主答案”仍被多模块竞争。
- 交互合同已建立，但真实专家效率还缺布局持久化、命令面板上下文动作、表格高级操作等能力。

### 综合评分

| 维度 | 分数 | 判断 |
|---|:---:|---|
| 结构一致性 | 9.1 / 10 | Shell / Pattern / 合同覆盖成熟，跨页语法稳定。 |
| 交互效率 | 8.0 / 10 | 合同过关，但还偏演示型，专家级操作闭环不足。 |
| 信息布局 | 8.1 / 10 | 主结构清晰，但部分页面空白节奏与任务差异不够精确。 |
| 色彩系统 | 7.2 / 10 | Dark Mode 气质好，Light Mode 和 contrast 仍拖后腿。 |
| 专业高级感 | 8.4 / 10 | 克制、终端感已成型，但局部还有“组件模板感”。 |
| **综合** | **8.2 / 10** | **可继续迭代，不建议作为最终冻结版。** |

---

## 2. 验证证据

本次审查先跑机器门禁，再进行截图人工评审。

| 命令 | 结果 |
|---|---|
| `bun run prototype:interaction` | PASS：1 test file，9 tests。 |
| `bun test scripts/prototype-design-consistency.test.ts scripts/prototype-view-preferences.test.ts scripts/prototype-expert-efficiency.test.ts` | PASS：48 tests。 |
| `bun run prototype:gates` | PASS：27/27 active prototypes，blocking 0，non-blocking 0。 |
| `bun run audit:routes` | PASS：27 IA routes covered。 |
| `bun run build:tokens:check` | PASS：354 tokens validation passed。 |
| `bun run audit:tokens:contrast` | FAIL：9 failed pairs，8 warnings。 |
| `bun run check` | PASS：Biome + TypeScript + 140 test files / 1560 tests。 |

关键截图证据：

- `test-results/ditto-design-cycle-gates/edition-v1-2026-04-27/edition-v1-vp-standard-contact-sheet.png`
- `test-results/ditto-design-cycle-gates/home/page-home.html-VP-STANDARD.png`
- `test-results/ditto-design-cycle-gates/markets-screener/page-markets-screener.html-VP-STANDARD.png`
- `test-results/ditto-design-cycle-gates/strategy-studio/page-strategy-studio.html-VP-STANDARD.png`
- `test-results/edition-review/visual-matrix/a-shares/light-compact.png`
- `test-results/edition-review/visual-matrix/watchlist/light-compact.png`
- `test-results/edition-review/visual-matrix/risk-center/light-compact.png`

---

## 3. P0 / P1 关键问题

### P0-1：色彩对比仍不达 Best 级

`bun run audit:tokens:contrast` 发现 9 个低于 3:1 的 token 组合，8 个只达到大字号可用区间。问题集中在：

- `surface-modal` + `text-disabled`
- `surface-modal` + `text-quaternary`
- `surface-overlay` + `text-disabled`
- `surface-overlay` + `text-quaternary`
- `surface-strip` + `text-disabled`
- `surface-muted` + `text-disabled`
- `surface-modal` + `text-data-stale`

涉及 token 位置：

- `src/styles/design-tokens/tokens-semantic.css` 中 `--surface-strip`、`--surface-overlay`、`--surface-modal`、`--surface-muted`
- `src/styles/design-tokens/tokens-semantic.css` 中 `--text-tertiary`、`--text-quaternary`、`--text-disabled`、`--text-data-stale`

判断：如果 `text-disabled` 只用于真正不可交互内容，可以接受较低对比。但 `text-quaternary`、`text-data-stale` 会承载状态、时间、数据新鲜度等真实业务信息，不能按“装饰文字”处理。

建议：

- 将 `text-data-stale` 升级到至少 4.5:1，可用低 chroma amber/neutral，不要只靠暗棕灰。
- `text-quaternary` 只允许用于纯装饰元信息；如用于表格、状态、时间戳，必须替换为 `text-tertiary` 或新建 `text-muted-readable`。
- 给 token contrast audit 增加用途分级：decorative / metadata / operational / data-critical。
- 对 operational 和 data-critical 文本执行 4.5:1 门槛。

参考标准：

- W3C WCAG Contrast Minimum 1.4.3: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum
- W3C WCAG Use of Color 1.4.1: https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html

### P0-2：Light Mode 数据可视化质量明显低于 Dark Mode

代表问题：A 股结构图在 Light Compact 下仍沿用偏深色热力图基底，形成“浅色界面里嵌入一块深色红绿热区”的割裂感。截图见：

- `test-results/edition-review/visual-matrix/a-shares/light-compact.png`

相关实现：

- `docs/designs/specs/prototypes/page-a-shares.html` 中 `.map-container` 定义热力图颜色基底。
- 小格标签存在 `font-size: 9px` 的特例。

风险：

- Light Mode 不像一等公民，更像 Dark Mode 的反相补丁。
- 红绿块面积过大时，视觉重量压过页面结构。
- 小格内文字在复杂背景上可读性不稳定。

建议：

- 为 data visualization 单独建立 `dark` / `light` scale，不要直接复用同一套热力图底色。
- Light Mode 下减少 fill saturation，增强边框、符号、数值标签，而不是靠大面积色块表达强弱。
- A 股可以保留红涨绿跌，但必须叠加非颜色编码：方向符号、边框强弱、pattern 或 sign marker。
- 图内文字最小不低于 10px；可交互或扫视定位文字不低于 12px。
- 对热力图增加自动文字色计算或分级 class：深块用浅字，浅块用深字。

### P1-1：Catalog 家族信息布局同质化，业务任务差异不足

代表页面：

- `page-strategy-list.html`
- `page-backtest-list.html`
- `page-experiment-list.html`
- `page-factor-list.html`
- `page-watchlist.html`

当前优点：这些页面的 Catalog Shell 合同稳定，右侧详情、批量动作、sticky summary、选中反馈都已补齐。

当前不足：页面首屏很容易读成“表格 + 右详情 + CTA”的同一模板。Strategy / Backtest / Experiment 的任务心智不同，但视觉组织差异偏弱。

建议改法：

- Strategy List：主答案应是“哪些策略可运行 / 哪些需要处理 / 哪个策略健康度最高”，右栏突出策略健康、最近运行、风险约束。
- Backtest List：主答案应是“哪次回测值得比较 / 哪次失败或异常 / 哪条曲线代表当前基线”，右栏突出净值曲线、诊断、加入对比。
- Experiment List：主答案应是“实验结果矩阵、胜出参数、失败原因”，不要只做列表详情。
- Factor List：主答案应是“因子是否仍有效、衰减、覆盖范围、可用策略”，右栏应偏质量诊断。
- Watchlist：主答案应是“哪个标的触发下一动作”，右栏应偏信号结构和动作建议。

布局建议：

- Catalog 页不要都平均使用同一个 summary strip。每个业务页应有一个任务专属 summary:
  - Strategy：运行态 / Sharpe / MDD / 最近回测
  - Backtest：完成 / 失败 / 中位 MDD / 最佳 Sharpe
  - Experiment：胜出率 / 参数稳定性 / 显著性 / 待复核
  - Factor：IC / IR / 衰减 / 覆盖率
- 空白较大的页面下半区应引入“轻量工作台”，例如 compare tray、recent activity、selected object timeline，而不是只留空。

### P1-2：首页首屏主答案还不够强

首页已经具备 `data-primary-answer`，并且“今日优先事项”“活动流”“AI 洞察”“市场脉搏”“全局预警”“数据健康”都比较完整。

但 Best 级首页需要 5 秒内回答：

1. 今天最该处理什么？
2. 为什么？
3. 风险或机会有多大？
4. 下一步动作是什么？

当前首屏模块过多，主答案被多个区域竞争。建议把首页首屏重组为：

- 顶部状态卡压缩为单行 Global Pulse，不再像 5 张同权重卡片。
- `data-primary-answer` 升级为“今日决策卡”：一句判断 + 三条证据 + 主动作 + 次动作。
- 今日优先事项只展示 P1/P2，不展示普通事件。
- 活动流降低视觉权重，避免抢主判断。
- 右栏只保留异常和实时状态；普通数据健康默认折叠。

推荐首屏结构：

```text
Global Pulse
Decision Card: 当前最重要判断 + 证据 + 动作
Priority Queue: 仅 P1/P2
Context Rail: 异常 / 市场脉搏 / 数据健康折叠
```

### P1-3：交互合同已通过，但专家效率还缺关键闭环

当前已经建立：

- Rail 统一为 5 个顶级域。
- Header utilities 统一。
- Bottom Tray 三态合同。
- Catalog / Studio 可调整面板合同。
- L2/L3 折叠语义。

但专业终端还需要更强的“连续工作”能力：

- 面板 resize 持久化：每个用户、每个 route 保存布局。
- 表格列宽、列排序、冻结列、密度偏好持久化。
- Command Palette 具备上下文动作，不只是全局入口。
- 选中对象驱动多区域联动：表格行、右栏、bottom tray、command suggestions 同步。
- Escape / Enter / Space / Arrow key / Cmd+K / Ctrl+K 全部形成可记忆快捷键体系。

建议新增 Command Palette 上下文动作：

| 页面 | 当前对象 | 建议动作 |
|---|---|---|
| Watchlist | 股票 | 生成信号、打开 Instrument Hub、发送到研究、移除观察 |
| Strategy List | 策略 | 运行回测、克隆策略、查看最近回测、暂停策略 |
| Backtest List | 回测 | 加入对比、查看曲线、复制参数、生成报告 |
| Signals Inbox | 信号 | 批准、拒绝、发送到订单、查看证据 |
| Platform | 数据源 / 任务 | 重试、查看日志、静默告警、创建 incident |

---

## 4. 色彩系统提升方案

### 4.1 建立三层颜色职责

当前颜色已经有 domain、market、system、data-viz 多层 token，但使用审查需要更严格：

| 层级 | 用途 | 要求 |
|---|---|---|
| Brand / Domain | 域识别和产品气质 | 低频、克制，不抢数据。 |
| Semantic / System | 状态、警告、成功、错误 | 必须非颜色冗余表达。 |
| Data Viz | 图表、热力图、矩阵 | light/dark 独立 scale，保证文字可读。 |

### 4.2 CTA 蓝色收敛

当前不少页面的主按钮使用高亮蓝，能保证可见性，但跨页看会让蓝色从“品牌动作”退化为“所有按钮都重要”。

建议：

- 每页只保留一个高亮主 CTA。
- 次动作使用 outline 或 quiet button。
- 危险动作不使用蓝色，只用 danger semantic + 文案确认 + 非颜色标记。
- Header command 的蓝色提示保持低占比，不与页面主 CTA 竞争。

### 4.3 Light Mode 不应只是反相

Light Mode 最明显的问题不是布局，而是视觉权重。建议：

- Surface 层级增加更清晰的灰阶差异。
- Border 在 Light Mode 下比 Dark Mode 稍强，替代大面积深色背景。
- 数据可视化减少色块面积，强化线、边界、符号。
- 不在 Light Mode 内嵌 Dark Mode 风格的 chart island，除非这是明确的 terminal viewport。

---

## 5. 信息布局提升方案

### 5.1 统一“主答案”合同

建议给每页新增或强化 `data-primary-answer` 的内容标准：

- 一句话判断。
- 1 个关键数字。
- 2-3 个证据。
- 1 个主动作。
- 明确影响范围。

页面进入 5 秒内，用户应该不用扫完全屏就能知道当前页面的核心结论。

### 5.2 右栏按 L1 / L2 / L3 收敛

当前右栏折叠合同已经建立，下一步应进一步规范内容优先级：

| 级别 | 默认 | 内容 |
|---|---|---|
| L1 | 常驻 | 选中对象身份、关键状态、主动作。 |
| L2 | 展开 | 当前任务需要的指标、诊断、证据。 |
| L3 | 折叠 | 历史、低频关联、普通队列、附加解释。 |

折叠后不能只剩标题，必须保留：

- count
- mini summary
- stale / warning / changed marker

### 5.3 避免“卡片堆”，强化工作面

Ditto 的定位是金融终端，不是 SaaS dashboard。信息布局应优先使用：

- table
- matrix
- chart surface
- queue
- inspector
- editor
- timeline
- compare tray

减少无任务含义的独立 card。卡片只用于对象摘要、状态样本、overlay specimen，不应成为页面主要组织方式。

---

## 6. 交互设计提升方案

### 6.1 Resize 从合同升级为体验

当前 prototype-only resize separator 合同已经是正确方向。后续建议：

- Catalog detail panel 默认 320px，允许 220-520px。
- Studio inspector 默认 320-368px，允许折叠到 48px summary rail。
- Bottom Tray 支持拖拽高度，而不只是 collapsed / peek / expanded。
- 双击 separator 恢复默认。
- 方向键调整，Shift + 方向键微调。
- 每个 route 保存用户最后布局。

### 6.2 表格操作升级

专业用户长时间使用 Catalog / Ledger / Ops 页面，表格必须更像工具：

- 冻结首列与操作列。
- 列宽拖拽。
- 批量选择后出现 action bar。
- 行 hover 显示次级动作，主动作常驻。
- 空白区域显示“已过滤 / 已选 / 下一步建议”，而不是纯空。
- 表格底部提供 active filters summary 与结果计数。

### 6.3 Overlay 与 Sidecar 的层级规则

建议建立：

| 场景 | 容器 |
|---|---|
| 快速确认 | Modal |
| 详情阅读 / 编辑 | Drawer |
| 对比 / 多步骤 | Sheet 或 Bottom Tray |
| Copilot | Global Sidecar |
| 审批 / 高风险动作 | Modal + Impact Summary |

不要把所有详情都塞进右栏，也不要把所有动作都弹 modal。

---

## 7. 优先级路线图

### P0：先修设计系统底线

- 修复 token contrast failed pairs。
- 给 `text-data-stale`、`text-quaternary` 建立用途限制。
- A 股 Light Mode 热力图单独设计 light scale。
- 清理小于 10px 的真实信息文字。

### P1：提升专家效率

- Command Palette 上下文动作。
- Resize 布局持久化。
- Catalog 家族按任务重做 summary strip。
- 首页主答案重组。
- 表格列宽 / 冻结 / 批量动作规范。

### P2：提升高级感与长期使用舒适度

- 角色化密度预设：Research-heavy / Trading-heavy / Platform-heavy。
- Motion Spec 收敛：hover、tray、drawer、resize、tab、tooltip。
- Light Mode 全量视觉矩阵从 7 页代表扩展到 27 页。
- 数据可视化加入色弱模拟检查。

### P3：规范同步

- 更新 `04_interaction_state_spec.md`：键盘、resize、Command Palette、折叠摘要。
- 更新 `10_ditto_shell_family_spec.md`：各 Shell 的 responsive / resize 行为。
- 更新 `11_ditto_page_pattern_library.md`：Catalog 子类型差异。
- 更新 token 文档：contrast usage tiers。

---

## 8. 建议验收门槛

下一轮原型设计如果要达到 Best，可采用以下门槛：

- `bun run prototype:gates` 27/27 pass。
- `bun run prototype:interaction` pass。
- `bun run audit:tokens:contrast` operational/data-critical 0 fail。
- Light / Dark + Compact / Comfortable 视觉矩阵覆盖 27 页。
- 每页有明确 `data-primary-answer` 或等价主答案区域。
- Catalog 页不再出现大面积无语义空白。
- Command Palette 至少覆盖每类 Shell 3 个上下文动作。
- 所有 data viz 有非颜色编码和 light/dark 双 scale。

---

## 9. 参考标准

- W3C WCAG 2.1 Contrast Minimum 1.4.3  
  https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum
- W3C WCAG 2.1 Use of Color 1.4.1  
  https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html
- W3C WCAG 2.2 Target Size 2.5.8  
  https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- Ditto Product Criteria  
  `docs/designs/specs/00_ditto_product_criteria.md`
- Ditto Shell Family Spec  
  `docs/designs/specs/10_ditto_shell_family_spec.md`
- Ditto Page Pattern Library  
  `docs/designs/specs/11_ditto_page_pattern_library.md`
- Interaction UX Audit  
  `docs/designs/specs/20_interaction_ux_audit.md`
