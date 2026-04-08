# Art Director 角色设计 — ditto-design-review skill 增强

**日期**: 2026-03-29
**状态**: 已批准

## 背景

多轮 product review 后发现：产品功能、体验、可交付感持续提升，但 UI 风格的高级感和一致性出现下降。

**具体表现**：
- 蓝色描边/高亮过多，从 Graphite Studio（克制/Bloomberg 方向）偏向 SaaS dashboard
- 功能标签感过重（badge、状态块、编号、图标叠加）
- 视觉语言分裂成多套"方言"（顶部条/卡片/矩阵/right rail 各一套语言）
- 留白节奏偏紧，缺少旧版的从容感

**根因**：四个审查角色（UI/UX/Product/Copy）各自视角都偏局部，没有人从整体气质和跨页面一致性的视角审视产品。

## 决策

在现有四角色基础上，新增第 5 个审查角色 **Art Director（艺术总监）**。

## 角色定位

**不看功能，不看文案，只看气质。**

核心 mandate：确保每次修改后，产品仍然是 Bloomberg/high-end quant desk 方向，而不是 SaaS dashboard 方向。

### 三块核心职责

1. **克制度审计（Restraint Audit）**：审计高亮/描边/色彩种类的数量是否在合理范围，判断视觉元素是否"功能标签感"过重
2. **跨页一致性审计（Cross-page Consistency）**：对比多页面，检查视觉语言是否分裂成多套"方言"
3. **品牌方向锚定（Brand DNA Anchor）**：基于 9 项设计决策，确保修改不偏离 Graphite Studio 审美方向

### 否决权规则

- Art Director 可以**降级**某项 polish 变更（如把 bolder 降为 normalize）
- Art Director 可以**移除**过度的 delight/overdrive 效果
- **不可否决**：功能性修复（P0）和可访问性修复

## 审查清单

| 检查项 | 量化方法 | 阈值/标准 |
|--------|---------|-----------|
| 高亮描边密度 | 统计品牌色描边元素数量 | 单页 ≤ 5 处 |
| 强调色面积比 | brand-accent 覆盖面积比 | ≤ 3% |
| 视觉元素层级数 | 不同装饰元素类型数 | ≤ 6 种 |
| 留白节奏比 | 留白区 vs 内容区占比 | 留白 ≥ 35% |
| 色彩种类数 | 语义色彩种类（不含 neutral） | ≤ 4 种 |
| 跨页语言一致性 | 各页面视觉指纹差异度 | ≥ 7/10 |
| 品牌方向评分 | Bloomberg vs SaaS dashboard 偏向 | ≥ 8/10 |

## 流程集成

### Phase 1 BASELINE（新增跨页基线）

1. 读取 .versions/ 下所有页面的最新截图
2. 提取各页面的"视觉指纹"（高亮密度/强调色面积/元素层级/留白比）
3. 生成"跨页一致性基线"

### Phase 2 PARALLEL REVIEW（5 个 agent）

Art Director 作为第 5 个并行 agent，输出 P0/P1/P2/建议。

### Phase 3 CONFLICT RESOLUTION（冲突优先级）

| 冲突场景 | 优先级 |
|---------|--------|
| AD vs UI Designer（装饰 vs Token） | AD 优先 |
| AD vs Product（功能标签 vs 克制） | 协商——AD 可要求更安静的实现 |
| AD vs UX（affordance vs 高级感） | UX 优先——可访问性不妥协 |
| AD vs 所有（整体气质 vs 局部优化） | AD 整体视角优先 |

### Phase 6 POLISH（新增 AD 审批）

```
FIX 完成
  ├─ Art Director 审查 FIX 结果（气质 ≥ 7.5 才允许 POLISH）
  ├─ POLISH 执行
  ├─ Art Director 复审 POLISH 结果（可降级/移除过度效果）
  └─ 输出最终气质评分卡
```

### Phase 7 FINAL（新增气质评分卡）

输出气质评分卡到最终报告中。

## 气质评分卡

```
气质评分卡：
├─ 克制度:    ████████░░ 8.2/10
├─ 一致性:    ███████░░░ 7.5/10
├─ 高级感:    ████████░░ 8.0/10
├─ 品牌方向:  ████████░░ 8.3/10
└─ 综合气质:  ████████░░ 8.0/10
```
