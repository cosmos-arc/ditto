# 执行流程（Phase 1-8）

> 全流程审查的详细步骤。每个 Phase 的模型分配见 [agent-protocol.md](agent-protocol.md)。

---

## Phase 1: BASELINE（基线采集 + 跨页视觉指纹） [sonnet]

### 步骤

1. 读取目标文件（HTML 原型或 React 组件）
2. 读取相关 spec 文档（作为参考）
3. 读取 Design Token 定义
4. 读取设计决策文档（Art Director 刚性锚点）
5. 读取信息架构文档（IA Specialist 参考锚点）
   - 01_product_information_architecture.md
   - 02_core_page_blueprints.md
6. 解析 State Coverage Index
   - 提取 HTML 顶部的状态覆盖索引注释块
   - 统计 tab 面板 / overlay / state variant 覆盖数
   - 检查 states-gallery 中 .gallery-card 数量和 label 是否匹配
   - 生成「状态覆盖率报告」作为 Phase 3 审查输入
7. Playwright: 启动浏览器（channel: 'chromium'），setViewportSize(1536x1080)
8. 三区截图策略（每个 zone 独立截图）：
   - view-default radio checked → 截图（默认 tab）
   - default-view 中每个 tab group → 点击 tab label → 截图
   - view-states radio checked → 截图（状态画廊）
   - view-overlays radio checked → 截图（弹层画廊）
9. page.evaluate() 提取关键元素 computed styles
10. **交互元素自动发现**（供 Phase 8 Gate 4 消费）：
    - 扫描所有 `<input type="radio">` / `<input type="checkbox">` + 关联 `<label>`
    - 扫描所有 tab group（`.tab-group` 内的 tab label + tab panel）
    - 扫描所有 overlay 触发器（`onclick` 引用 overlay radio / `[data-overlay]` 属性）
    - 扫描所有可 hover 交互元素（`[tabindex="0"]`、`.treemap-cell-iv`、`.queue-item` 等）
    - 输出「交互元素清单」JSON（元素选择器 + 类型 + 预期行为 + 关联 radio id）
11. 多视口检测（详见 [viewport.md](viewport.md)）
12. 跨页结构化 metrics 提取 + 一致性基线：
    - 读取 manifest，遍历 status != "done" 的页面
    - 提取 shell / components / typography / colors metrics
    - 比对所有页面 metrics，标记偏离值
    - 生成「跨页一致性基线报告」作为 Phase 3 审查输入

---

## Phase 2: CREATIVE DIRECTION（创意蓝图） [opus]

> 详见 [iterate.md](iterate.md) §CREATIVE DIRECTION。

### 产品边界约束

- 不得发明 spec 未定义的功能内容/模块/组件
- 视觉策略（间距、材质、动画、色彩）可自由提案
- 产品级变更必须标记 "⚠️ 需 PM 确认" 并在 Phase 5 交由 PM 裁定

### 步骤

1. 读取前轮评分快照和反思记录（首轮跳过）
2. 识别当前最低分维度和天花板维度
3. 从策略矩阵选择本轮创意策略
4. 轻量标杆调研（WebSearch 1-2 个参考）
5. 输出本轮创意蓝图（策略/区域/参考/预期/约束）

---

## Phase 3: PARALLEL REVIEW（并行审查）

启动 7 个并行 Agent（见 [roles.md](roles.md)）：

| 角色 | model | 产出 |
|------|-------|------|
| Art Director | opus | 气质问题清单 + 评分卡 |
| UI Designer | opus | UI 问题清单 |
| UX Reviewer | sonnet | UX 问题清单 |
| Product Mgr | sonnet | spec 合规/层级验证/边界守卫 |
| IA Specialist | sonnet | 信息架构 + 流程问题 |
| Copy Editor | sonnet | 文案问题清单 |
| Data Viz Specialist | sonnet | 数据可视化 + 色觉无障碍 |

### 输出格式

- 🔴 P0: 必须修复（阻断性问题）
- 🟡 P1: 建议修复（影响体验）
- 🟢 P2: 可选优化（锦上添花）
- 💡 建议：对设计/信息架构的调整建议

### Edition 增强：跨页一致性输入

当 manifest 存在时，每个 Agent 的 prompt 追加跨页一致性基线报告。

### 三区审查指引

各角色按 zone 分工审查（详见 [roles.md](roles.md) 各角色的「三区审查指引」）。

### 状态覆盖完整度输入

当状态覆盖率报告存在时，每个 Agent 追加覆盖检查清单。

---

## Phase 4: CONFLICT RESOLUTION（冲突协调） [opus]

### 步骤

1. 汇总 7 个角色的问题清单
2. 去重合并相似问题
3. 识别角色间的冲突点
4. 为每个冲突提供分析 + 折中方案
5. 识别所有角色的共识点
6. [--iterate] Art Director 为每个 P1 标注「预期提分」
7. [--iterate] 标注每个变更与创意蓝图的方向对齐度

### 双轨权威制冲突优先级规则

**视觉决策轨（AD 最高）**：
- AD vs UI（装饰 vs Token）→ AD 优先
- AD vs UX（affordance vs 高级感）→ UX 优先（可访问性不妥协）
- AD vs IA（信息密度 vs 克制留白）→ 协商，参考 00_ditto_product_criteria.md 的 L1/L2/L3 分层
- AD vs 所有（整体气质 vs 局部优化）→ AD 整体视角优先

**产品决策轨（PM 最高）**：
- PM vs AD（产品内容 vs 视觉表达）→ PM 定义内容边界，AD 决定视觉实现方式
- PM vs IA（功能范围 vs 信息结构）→ PM 定范围，IA 定组织结构
- PM vs UX（功能完整 vs 交互简化）→ PM 裁定功能必要性
- 任何角色 vs PM（涉及产品功能/内容）→ PM 一票否决
- 高分歧 C 类变更 → PM 深度分析流程

**信息架构决策轨（IA 最高）**：
- IA vs UX（信息分组 vs 交互路径）→ 先 IA 定结构，再 UX 审交互
- IA vs AD（信息架构 vs 视觉留白）→ 协商

---

## Phase 5: DECISION（用户决策 / AUTO-DECISION） [sonnet]

### 产品边界分类

| 类型 | 定义 | 裁决 |
|------|------|------|
| A 类 | 视觉微调（间距/材质/动画/色彩） | AUTO by AD |
| B 类 | spec 内产品微调（优先级/布局/交互方式） | AUTO by PM |
| C 类 | 超出 spec / 重大战略变更 | PM 深度分析流程 |

### PM 深度分析流程（C 类）

详见 [iterate.md](iterate.md) §AUTO-DECISION 规则。

### [--人工] AskUserQuestion 呈现

- 共识点（建议直接采纳）
- 冲突点（附分析 + 折中方案）
- 各角色独立建议（可选择性采纳）
- 信息架构/交互流程的重大调整建议
- [如有 ESCALATE] 结构化分歧分析

### [--iterate] AUTO-DECISION

详见 [iterate.md](iterate.md) §AUTO-DECISION 规则。

---

## Phase 6: FIX（执行修改） [sonnet]

1. 按优先级执行采纳的修改
2. 需要验证时用 Playwright page.evaluate() 提取关键 computed styles
3. 如有信息架构调整，更新 spec 文档
4. 如有新的设计决策，记录到 decisions/

---

## Phase 7: POLISH（质量提升 + Art Director 审批） [混合]

### Step 7.1: Art Director 预审 [opus]

- 气质评分 ≥ 7.5 → 允许进入 POLISH
- 气质评分 < 7.5 → 先修正气质问题，再进入 POLISH

### Step 7.2: 应用 impeccable skills [sonnet]

质量等级对应的 skills 见 [quality-levels.md](quality-levels.md)。

### Step 7.3: Art Director 复审 [opus]

- 可降级过度的 bolder/delight/overdrive 效果
- 可移除违反克制度的装饰元素
- 使用 impeccable: quieter 处理过度装饰
- 输出气质评分卡

### Step 7.4: REFLECT [--iterate] [opus]

详见 [iterate.md](iterate.md) §每轮反思记录。

---

## Phase 8: FINAL（最终验证 + 气质评分） [混合]

### Step 8.0: PRE-SCORE GATES（评分前置门禁） [sonnet]

> **以下门禁全部通过后才能进行五维度评分。任何一项不通过 = 布局错误，必须先修复。**
>
> **必须先运行脚本化门禁**：
>
> ```bash
> bun run prototype:gates -- --prototype docs/designs/specs/prototypes/<page>.html
> ```
>
> 命令 exit code 非 0 时，STOP 修复，不进入评分。输出截图和报告在 `test-results/ditto-design-cycle-gates/`。

#### Gate 0: 原型工具 UI 隔离
- `.proto-nav` 不可见（`getBoundingClientRect().height === 0` 或不在 default-view 中）
- `.style-label` 不可见
- `.skip-link` 默认不可见

#### Gate 1: CSS 资源完整加载
- 所有 token CSS `sheet.cssRules.length > 0`
- Console 无 `Failed to load resource`（404）
- 关键 token 变量有值（如 `--font-size-12`、`--text-primary`）

#### Gate 2: Shell 网格结构
- Shell display 为 grid
- Grid 列数 ≥ 2
- rail / header / main / sidebar 高度 > 0

#### Gate 3: 浏览器视觉验证
- 脚本必须生成 VP-STANDARD / VP-COMPACT fullPage 截图
- **必须基于脚本输出截图继续进行人工/AI 视觉检查**
- 检查页面整体布局是否符合预期
- 检查无元素错位/重叠/溢出
- 检查原型工具 UI 未污染产品视图

#### Gate 4: 交互功能完整性
- 读取 Phase 1 步骤 10 产出的「交互元素清单」
- 对清单中每个交互元素执行 Playwright 验证（详见 [review-scoring.md](review-scoring.md) Gate 4）
- Tab 切换、Overlay 开闭、Toggle 切换、三区切换、Hover 反馈逐一验证
- ≥ 50% 通过 → 降分（扣 1-2 分）；< 50% → STOP 修复

**失败处理**：Gate 0-2 不通过 → STOP 修复。Gate 3 不通过 → 视觉问题严重程度扣除 1-3 分。Gate 4 不通过（< 50%）→ STOP 修复。Gate 4 不通过（≥ 50%）→ 扣除 1-2 分。

### Step 8.1: 零 Inline Style 门禁 [sonnet]

- grep 所有 style="..." 属性（排除 CSS 注释）
- 命中数 > 0 → P0 级阻断，不进入后续步骤

### Step 8.2: Lighthouse 审计 [sonnet]

### Step 8.3: Token 审计 [sonnet]

### Step 8.4: 三区结构完整性验证 [sonnet]

复用 create-mode.md 的 10 项检查。任一失败 → P0 级阻断。

### Step 8.5: VP-STANDARD 完整性验证 [sonnet]

- 内容无截断，底部元素完全可见
- sticky 元素（rail/header/context-bar）正常工作

### Step 8.6: VP-COMPACT 完整性验证 [sonnet]

- 可滚动到底部，底部内容完全可见
- 布局无破坏

### Step 8.7: 视口验证报告 [sonnet]

### Step 8.8: Art Director 最终气质评估 [opus]

- **浏览器截图**：`browser_take_screenshot` 全页面截图，作为评分依据
- 重新提取视觉指纹，对比 Phase 1 基线
- 五维度评分必须结合截图视觉效果，不能仅凭 `getComputedStyle()` 数据
- 输出 5 维气质评分卡（克制度/一致性/高级感/品牌方向/信息效率）
- 跨页一致性验证

### Step 8.9: 迭代反思汇总 [--iterate]

汇总所有轮次反思记录到最终报告。

### Step 8.10: git commit 最终状态

### Step 8.11: done 标记 [--iterate 达标]

`git tag -a review/<task>/done -m "task completed: score {X}/10, {N} rounds"`

### Step 8.12: 审查报告生成

输出到 docs/reviews/（含 tag 引用），格式见 [templates.md](templates.md)。

### Step 8.13: design decisions 更新

### Step 8.14: 待同步清单

嵌入报告末尾，供 --sync 使用。

### Step 8.15: Edition 状态推进 [--edition]

详见 [edition.md](edition.md)。

### Step 8.16: 合同桥接

**Step 8.16a**: 调用 `/ditto-page-contract --create <page-id>`
- 确认 manifest 中该页面 status === "reviewed"
- 合同创建成功 → 继续 8.16b
- 合同创建失败 → 默认 WARNING / --strict BLOCK
> **注意**：此步骤为快速建档，产出 draft 状态合同。如需 app-dev 消费（contract-ready），必须显式执行 `/ditto-page-contract --validate <page> --promote`。

**Step 8.16b**: 设置 status="done"，更新 manifest

**Step 8.16c**: 调用 `/ditto-page-contract --validate <page-id>`
- 验证全绿 → "Contract draft ready"
- 验证失败 → 默认输出失败项 / --strict BLOCK

**Step 8.16d**: 合同 promote 提示
```
✅ 合同已建档（draft）
⚠️ 如需 app-dev 消费，请先执行:
   /ditto-page-contract --validate <page> --promote
```

### Step 8.17: 布局 bug 检测 [--iterate 最后一轮 或 edition-review]

- take_screenshot（VP-STANDARD, fullPage）
- analyze_image 检测：内容溢出/截断 / 元素重叠/遮挡 / 对齐偏移 / 留白异常
- page.evaluate() 交叉验证：scrollHeight vs clientHeight、getBoundingClientRect()

---

## --review-feedback 模式执行流程

> 触发条件: `/ditto-design-cycle <prototype> --review-feedback <page>`

**前置条件**: `docs/contracts/feedback/<page>.md` 存在（由 app-dev Phase 15 SHIP 产出）

```
Phase 1:   BASELINE       → 基线采集（同全流程）
Phase RF1: 读取反馈        → 解析 feedback/<page>.md
                              ├─ 分类: 原型缺陷 / 设计改进
                              ├─ 提取: 模块名 + 描述 + 建议
                              └─ 优先级排序: 原型缺陷 > 设计改进
Phase RF2: 针对性审查      → 只审查反馈中列出的区域/模块
                              ├─ 原型缺陷: 七角色审查（聚焦问题区域）
                              └─ 设计改进: AD + PM 评估（聚焦可行性与影响）
Phase RF3: DECISION       → 用户确认修复范围
Phase RF4: FIX            → 执行修改（只处理反馈项，不做全量审查）
Phase RF5: VERIFY         → 验证修复效果（对比修复前后截图）
Phase RF6: FINAL          → 门禁 + 更新反馈文件状态
                              └─ 标记已修复项，输出剩余项
```

**与全流程的区别**:
- 不执行 CREATIVE DIRECTION（Phase 2）—— 反馈已明确问题
- 不执行全量 PARALLEL REVIEW（Phase 3）—— 只审查反馈区域
- 不执行 POLISH（Phase 7）—— 聚焦修复而非精修
- 反馈文件中每项 MUST 有明确处理状态（fixed / deferred / rejected）
