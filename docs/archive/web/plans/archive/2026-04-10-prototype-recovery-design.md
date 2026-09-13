# 原型恢复设计 — Contract-first Recovery

> **日期**：2026-04-10
> **状态**：已确认设计，待进入实现
> **范围**：`design/specs/*` + `prototype/*` 与 `src/` 当前实现的收敛恢复
> **目标**：解决“页面能跑但整体不一致”的系统性问题，建立后续原型落地的唯一真源

## 1. 背景与判断

当前仓库不是“什么都没做完”，而是出现了典型的 **骨架完成、页面分叉、验收失真** 的状态：

- 路由、数据、MSW、hooks、测试体系已经完整搭起
- 大多数页面已经可访问
- `bun run check` 可通过，说明工程健康度较高
- 但页面模式、视觉 token、slot 装配、原型对应关系没有收口

这会导致一个非常危险的假象：代码健康，但产品完成度被高估。

### 1.1 当前完成度评估

以 `prototype` + specs 为落地标准，当前估算如下：

| 维度 | 估算完成度 | 判断 |
|---|---:|---|
| 路由 / 数据 / 测试基础设施 | 85%+ | 主骨架基本齐全 |
| 页面内容完成度 | 60% 左右 | 多页可用，但仍有明显缺块 |
| 壳层 / 模式一致性 | 40%-50% | 是当前最主要问题 |
| 视觉 / token 收敛度 | 40%-50% | 存在系统性漂移 |
| 综合原型落地度 | 55%-60% | 不能视为“完整落地” |

### 1.2 量化证据

本次审计得到的关键事实：

- `bun run check` 通过：`75` 个测试文件、`840` 个测试全绿
- 共有 `21` 个 `*page.tsx`
- 其中至少 `9` 个页面基本只使用 `main` 槽位，属于“壳层已选、工作面未成型”
- 代码中仍存在 `9` 处明确的“待实现 / 待图表增强 / 占位”文案
- 常见硬编码间距类名仍有 `92` 处
- `inline style` 使用仍有 `14` 处
- 旧式 surface token 引用 `53` 次，语义 surface token 仅 `20` 次，说明视觉层尚未完全收敛到语义命名
- 存在一批未定义或非规范 token 引用，其中最典型的是：
  - `--color-surface-hover`：`31` 处
  - `--color-surface-base`：`4` 处
  - `--color-status-success` / `--color-status-error` / `--color-status-warning`：`16` 处
  - `--color-brand-primary`：`2` 处
  - `--color-surface-elevated`：`2` 处

### 1.3 结论

当前最重要的结论不是“多做几个页面”，而是：

**Ditto 已经具备继续高质量落地的工程基础，但缺少一套页面合同与验收体系，导致完成定义漂移、页面模式错位、视觉语言发散。**

换句话说，现在最需要修复的不是单页，而是“系统如何定义完成”。

---

## 2. 核心问题与根因

### 2.1 完成定义漂移

仓库内至少存在 4 套隐含“完成”定义：

1. 路由存在即可算完成
2. 数据接上即可算完成
3. 测试通过即可算完成
4. 页面看起来差不多即可算完成

这四者不等价，最终导致：

- 文档可写成“已完成”
- 页面中仍残留“待实现”
- 核心 slot 未填满也未被拦截
- `bun run check` 通过被误解成“原型已落地”

### 2.2 页面合同缺失

当前没有一份统一的 route-to-pattern-to-prototype-to-slots 合同表。

缺失合同表的直接后果：

- 同一页面今天按 prototype 修，明天按 spec 推
- 同一类页面由不同人各自理解 shell 角色
- 页面是否“做完”只能靠主观感受

### 2.3 Page Pattern / Shell 角色错位

部分页面当前实现与规范明确冲突：

- `/trading/signals` 按规范应属于 `Queue / Ops Console`，实现却走 `CatalogLayout`
- `/trading/orders` 按规范应属于 `Ledger / Execution Console`，实现却走 `CatalogLayout`
- `/ai/agents` 按规范应属于 `Studio / Builder`，实现却走 `CatalogLayout`

这种错位不仅影响页面本身，还会持续污染共享组件抽象方式。

### 2.4 设计系统漂移

token 层已经拆分完成，但运行时仍存在两套命名并存、别名不全、引用失真的问题：

- 一部分组件使用语义 token
- 一部分组件继续引用旧 token
- 一部分组件直接引用不存在的 token，导致样式静默失效

结果是：

- hover、surface、状态色、图表色、边框色在页面间不稳定
- 同类组件看上去像不同批次产物
- 视觉一致性无法靠局部 patch 恢复

### 2.5 上游输入并不单一

`prototypes` 并不是 21 页完整高保真覆盖。

当前上游实际上分为两类：

- **HTML 高保真原型**：可做强对齐
- **spec / blueprint only**：只能做规范推导实现

如果不先显式区分这两类页面，团队就会默认“所有页面都应该 1:1 对齐 HTML”，从而造成错误预期。

### 2.6 验收机制缺位

当前缺少页面级产品验收，只保留了工程级验收。

因此系统能保证：

- 类型正确
- 测试通过
- lint 通过

却不能保证：

- 页面模式正确
- slot 完整
- 无 placeholder
- token 合法
- 与 prototype/spec 一致

---

## 3. 恢复目标与非目标

### 3.1 恢复目标

本轮恢复不以“再补几页”为目标，而以建立一套可持续落地机制为目标。

核心目标有 4 个：

1. 建立 React 实现对 specs/prototypes 的唯一收敛面
2. 修复 page pattern、shell role、slot usage 的系统性偏差
3. 收敛 token 层，消除设计系统漂移
4. 用统一验收标准替代“感觉差不多”

### 3.2 非目标

本轮不追求：

- 重写整个数据层
- 推翻已有测试体系
- 重新设计信息架构
- 在没有规范输入的情况下“脑补创新页面”
- 以一次大重构解决所有 UI 细节

---

## 4. 总体策略：Contract-first Recovery

推荐采用 **Contract-first Recovery**，而不是继续逐页 patch。

### 4.1 三种可选路径

| 路径 | 描述 | 优点 | 风险 |
|---|---|---|---|
| A. 逐页 patch | 看到哪里不对修哪里 | 短期见效快 | 持续制造模式债 / token 债 |
| B. Contract-first Recovery | 先建合同，再收敛模式和页面 | 最稳、最适合当前状态 | 前期需要多做一次梳理 |
| C. 直接搬运 HTML prototype | 高保真硬对齐 | 视觉恢复快 | 会把 prototype 的一次性结构带入正式工程 |

### 4.2 推荐结论

选择 **B. Contract-first Recovery**。

理由：

- 当前最大的损耗点不是“不会做”，而是“没有统一约束”
- 数据层和测试层已经足够稳定，不值得推翻
- 页面数量已经大于人工记忆可稳定维护的范围，必须引入合同化机制

---

## 5. 页面合同模型

### 5.1 合同表定义

为每个页面建立合同条目，至少包含 6 个字段：

| 字段 | 说明 |
|---|---|
| `route` | 页面路由 |
| `pagePattern` | 对应 Page Pattern |
| `shellFamily` | 对应 Shell Family |
| `prototypeSource` | `prototype-backed` 或 `spec-only` |
| `requiredSlots` | 页面必须填充的 slot 列表 |
| `requiredStates` | 页面必须覆盖的 UI 状态列表 |

建议后续实现为：

`src/features/shell/page-contracts.ts`

### 5.2 合同示例

```ts
{
  route: "/trading/signals",
  pagePattern: "queue-ops-console",
  shellFamily: "ops-console",
  prototypeSource: "prototype-backed",
  prototypeRef: "prototype/page-signals-inbox.html",
  requiredSlots: ["health", "main", "detail"],
  requiredStates: ["loading", "empty", "error", "stale", "selected-row", "sheet-open"]
}
```

### 5.3 新的完成定义

从本轮恢复开始，页面“完成”必须同时满足以下 4 条：

1. **无占位内容**
   - 不允许出现“待实现 / 占位 / coming soon / 待图表增强”
2. **slot 装配完整**
   - 页面合同里的 required slots 必须全部有内容
3. **token 合规**
   - 不允许引用未定义 token
   - 不允许继续扩散旧式非语义 token 命名
4. **状态覆盖完整**
   - 至少覆盖 loading / empty / error / stale
   - 页面特有状态按合同补齐

`bun run check` 仅代表工程健康，不代表页面已完成原型落地。

---

## 6. 页面分组策略

后续实现不按“模块”修，而按“输入类型 + 模式风险”分组推进。

### 6.1 Group A：高保真原型直译组

这组页面必须严格受 `prototype + page pattern` 双约束。

包含：

- `/`
- `/markets`
- `/research`
- `/trading`
- `/platform`
- `/ai`
- `/ai/copilot`
- `/trading/signals`
- `/trading/orders`
- `/trading/risk`
- `/instruments/$id`
- `/research/strategy-studio`
- `/research/regime`
- `/markets/intelligence`

目标：

- 工作面语法与 prototype 一致
- slot 结构完整
- 视觉和交互以 prototype 为直接参照

### 6.2 Group B：Spec 推导组

这组页面没有完整 HTML 高保真原型，需按 specs 与同家族页面语法实现。

包含：

- `/markets/a-shares`
- `/markets/calendar`
- `/research/backtest/$id`
- `/research/factors/$id`
- `/strategies/$id`

目标：

- 与对应 family 页面保持一致语法
- 与 specs/blueprints 对齐
- 不追求“硬对齐不存在的 HTML”

### 6.3 Group C：模式纠偏组

这组页面优先级最高，因为当前 page pattern 已经错位：

- `/trading/signals`
- `/trading/orders`
- `/ai/agents`

这 3 页必须优先纠正，否则后续共享组件抽象会持续跑偏。

---

## 7. 架构收敛方案

### 7.1 三层收敛模型

后续实现应明确拆成三层：

1. **Contract Layer**
   - 页面应该长成什么
   - 对应哪个 pattern / shell / prototype / states
2. **Shell / Pattern Layer**
   - 页面使用哪一种工作面语法
   - 哪些 slot 是该类页面的标配
3. **Page Assembly Layer**
   - 实际把业务组件装配到 slot 中

当前问题正是三层混用：

- page 组件自己决定 layout
- layout 不知道页面合同
- prototype/spec 对应关系不落地

### 7.2 推荐改造原则

- page 组件不再“发明布局”，而是“按合同装配”
- layout 组件保持通用，但 slot 语义必须稳定
- prototype-backed 页面优先复用同家族的成熟区块，而不是重新写一套视觉语法
- spec-only 页面必须先找 family reference，再做推导实现

### 7.3 Token 层治理原则

本轮 token 治理不做“大清洗式重写”，而做收敛式治理：

- 先补齐必须的兼容别名
- 再消灭未定义 token
- 最后把页面引用逐步收拢到语义 token

优先处理的 token 问题：

- `surface-*` 的混用
- `status-*` 与 `system / risk / market` 语义混用
- 图表色与 surface 色的旧命名漂移
- density token 命名不一致

### 7.4 页面装配原则

页面装配需要从“内容能显示”升级到“工作面成立”。

具体要求：

- 只要页面选择了某个 shell，就要尽量填满该 shell 的关键 slot
- `main-only` 页面必须重新判断是：
  - 本来就应该是极简页
  - 还是当前只是缺少 activity / detail / inspector / analysis
- 对象页不能只做一个 `meta + tabs + 占位主区`
- Studio 页不能只剩一个大块空白 main

---

## 8. 优先级与里程碑

### Milestone 1：基线收口 ✅ 已完成

> **完成日期**：2026-04-10
> **产出报告**：[milestone1-baseline-report.md](./2026-04-10-milestone1-baseline-report.md)
> **运行时源**：`src/features/shell/page-contracts.ts`（21 页合同 + 26 个测试）

**目标**：建立统一完成标准，停止继续制造结构债。

**产出**：

- ✅ 页面合同表（TypeScript 运行时 + 文档）
- ✅ 路由分组清单（Group A/B/C）
- ✅ prototype-backed / spec-only 清单（16/5）
- ✅ token 问题扫描清单（8 个未定义 → 0 个）
- ✅ 页面验收清单

**已完成**：

- ✅ 明确每条 route 的 pattern / shell / source / slots / states
- ✅ 扫描并消灭未定义 token（64 处引用全部通过兼容别名修复）
- ✅ 明确哪些页面不允许再用 `main-only`（合同表中的 requiredSlots 即约束）

**完成标准**：

- ✅ 合同表覆盖全部 21 个页面
- ✅ 未定义 token 清单清零
- ✅ `bun run check` 通过

### Milestone 2：模式纠偏

**目标**：修正最核心的 page pattern 偏差。

**优先页面**：

- `/trading/signals`
- `/trading/orders`
- `/ai/agents`
- `/`、`/markets`、`/research`、`/trading`、`/platform`

**重点动作**：

- 纠正 shell family
- 统一 slot 语法
- 让核心工作台都具备完整工作面

**完成标准**：

- 核心 pattern 不再错位
- 5 个主工作台的 shell 角色稳定
- 页面不再依赖“单 main 区兜底”

### Milestone 3：未完成页补齐

**目标**：彻底消灭显式未完成内容。

**优先页面**：

- `/research/backtest/$id`
- `/research/factors/$id`
- `/instruments/$id`
- `/research/strategy-studio`
- `/strategies/$id`

**重点动作**：

- 去掉所有“待实现 / 待图表增强”
- 用 family-consistent 工作面替代占位内容
- 对 spec-only 页面建立最低一致性标准

**完成标准**：

- 仓库内不再出现产品级占位文案
- 每个对象页 / Studio 页具备完整主工作面

### Milestone 4：高保真收尾

**目标**：在结构稳定后，集中处理视觉与交互细节。

**范围**：

- spacing / density
- typography
- surface / border / hover
- 状态色
- 动画与微交互
- prototype 截图对比

**完成标准**：

- prototype-backed 页面通过截图审查
- spec-only 页面通过 family consistency 审查

---

## 9. 验收机制升级

### 9.1 双轨验收

后续验收必须拆成双轨：

#### 工程轨

- `bun run check`
- 类型正确
- 测试通过
- lint 通过

#### 产品轨

每页至少要过以下 6 条：

1. page pattern 正确
2. required slots 填满
3. 无 placeholder / 待实现
4. token 引用合法
5. 核心状态完整
6. 与 prototype/spec 一致

### 9.2 页面级验收模板

建议为每页建立统一验收模板：

| 检查项 | 结果 |
|---|---|
| route 与合同一致 |  |
| page pattern 正确 |  |
| shell family 正确 |  |
| required slots 已填满 |  |
| loading / empty / error / stale 已覆盖 |  |
| 无未定义 token |  |
| 无待实现文案 |  |
| 与 prototype/spec 对齐 |  |

### 9.3 prototype-backed 与 spec-only 的不同验收

#### prototype-backed 页面

除双轨验收外，追加：

- 截图人工审查
- 关键结构与 prototype 一致
- 关键状态与 prototype 对应

#### spec-only 页面

除双轨验收外，追加：

- 与 family reference 一致
- 与 blueprint / shell family / page pattern 三者不冲突

---

## 10. 风险与控制

### 10.1 Token 修复波及面大

风险：

- token 修复会影响大量组件
- 局部修复可能引发多页回归

控制方式：

- 先建立问题清单，再分批收口
- 优先引入兼容别名，避免一次性大规模改名
- 每完成一批都跑 `bun run check`

### 10.2 Spec-only 页面容易再次“脑补过度”

风险：

- 在没有 HTML prototype 的情况下过度创作
- 最终脱离 family consistency

控制方式：

- 先找同 family 页面做参考
- 以 specs 和 family grammar 为第一约束
- 不做无来源创新

### 10.3 文档状态与代码状态再次脱节

风险：

- 设计文档继续写“已完成”
- 实现端仍有残留占位

控制方式：

- 以合同表和验收表为更新依据
- 每个里程碑完成后再更新文档状态
- 禁止先写“完成”再补实现

---

## 11. 推荐的下一步

如果进入实现阶段，建议顺序如下：

1. 新建页面合同文档或运行时合同配置
2. 修 token 基线与未定义 token
3. 修 3 个模式错位页
4. 修 5 个核心工作台页的 slot 完整性
5. 补齐未完成对象页 / Studio 页
6. 做高保真视觉收尾与截图验收

---

## 12. 最终结论

Ditto 当前最需要的不是“继续补几个页面”，而是 **把原型落地变成一套受合同约束的工程流程**。

只要继续沿用现在的方式推进，即使每周都新增页面内容，也会不断复发以下问题：

- 文档说完成，代码里却仍在占位
- 页面能打开，但模式选错
- 样式大体相似，但细节持续漂移
- 测试全绿，但产品体验不稳定

因此本轮恢复的本质是：

**先修“如何定义完成”，再修“页面长什么样”。**

这不是减速，而是为了让后续所有页面修复都能真正收口。
