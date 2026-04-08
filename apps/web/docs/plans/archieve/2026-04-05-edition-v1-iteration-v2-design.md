# Edition v1 Iteration v2 — 设计文档

> 目标：在 CSS/HTML 原型媒介内，将 17 个页面全部推到 ≥ 9.0 分

## 1. 背景

Edition v1 已完成首轮迭代，17 个页面平均分 8.3/10：
- Tier S（8.5+）：6 页 — instrument-hub 9.0, home/platform/research/markets-screener/regime-monitor 8.5
- Tier A（8.0）：11 页 — cross-market, trading-overview, strategy-studio, signals-inbox, orders-ledger, risk-center, ai-overview, markets-intelligence, ai-copilot, agent-console, token-showcase

本轮迭代（v2）以 **每个页面最低 9.0 分** 为硬性退出条件，预算 30 轮，quality level = best。

CSS 原型理论天花板 9.0-9.5（instrument-hub 已验证 9.0 可达）。

## 2. 策略：四阶段强制达标

### Phase 1: 快速收割（R1-R11）

11 个 Tier A 页面各 1 轮首轮深度评审 + 定向修复。预期 +0.5~1.0。

页面分组：

**Group A：数据密集分析页（R1-R3）**
- cross-market, trading-overview, markets-intelligence
- 共性弱点：信息密度不足、数据可视化深度不够
- 策略：对标 instrument-hub（9.0 标杆），补强信息效率维度
- 定向修复：数据卡片密度 → 表格/矩阵 → 热力图 → 多层信息叠压

**Group B：工作流管理页（R4-R7）**
- strategy-studio, signals-inbox, orders-ledger, risk-center
- 共性弱点：模块层级模糊、交互元素视觉权重不当
- 策略：强化 L1/L2/L3 层级梯度，优化可扫描性
- 定向修复：模块边框/间距梯度 → 行动按钮视觉层级 → 状态标签一致性

**Group C：AI 系列页（R8-R10）**
- ai-overview, ai-copilot, agent-console
- 共性弱点：内容填充不充分、AI 特有交互模式缺失
- 策略：定义 AI 页面的专属设计语言（对话气泡、思考链、置信度条）
- 定向修复：AI 输出可视化 → 人机协作模式 → 置信度/来源标注

**Group D：工具展示页（R11）**
- token-showcase
- 特殊性：设计系统展示页，需在自我一致性上完美
- 策略：作为 Token 合规的最终检验场

### Phase 2: 差距补强（R12-R20）

Phase 1 未达 9.0 的页面各 1 轮。

- 策略：针对最弱维度突破 + 创意方向 pivot
- 启用突破协议加强版：单页面连续 2 轮提升 < 0.2 → 自动维度 pivot
- 连续 3 轮停滞 → 触发「结构重评」（重新审视信息架构）

### Phase 3: 标杆突破（R21-R25）

全部 17 页中，已达标的 Tier S 页面（含 Phase 1/2 升入的）从 8.5-9.0 推到 9.0+。

- 策略：创意突破 + 基准对标研究
- 对标 instrument-hub 的具体设计手法

### Phase 4: 天花板冲刺（R26-R30）

仍未达 9.0 的页面优先。若全部达标，将最高潜力页面推向 9.5。

- 策略：最大创意野心 + 突破协议
- 信息可视化创新

### 动态重分配

- 页面在某阶段提前达标（≥ 9.0），其预算轮次转入下阶段池
- Phase 4 结束时仍有页面 < 9.0 → 输出诊断报告

## 3. 每轮执行流程

```
ROUND N
│
├─ 1. REVIEW（并行 6 角色评审）
│   ├─ UI Designer: Token/视觉层级/色彩
│   ├─ UX Reviewer: 可达性/交互/视口完整性
│   ├─ PM: Spec 合规/功能层级/产品边界
│   ├─ IA Specialist: 信息分组/导航/标签
│   ├─ Copy Editor: 标签/文案/数值格式
│   └─ Art Director: 高级感/品牌方向/整体气质
│
├─ 2. CREATIVE DIRECTION
│   ├─ 读取上轮 REFLECT
│   ├─ 选择策略等级 (1-5)
│   └─ 若触发突破协议 → 执行 pivot
│
├─ 3. FIX（定向修复 P0/P1 问题）
│   ├─ 每个问题: 诊断 → 方案对比 → 执行
│   └─ 禁止批量正则操作（HTML 安全规则）
│
├─ 4. POLISH（impeccable 技能链）
│   └─ level=best: polish → typeset → arrange
│
├─ 5. SCORE（5 维度打分）
│   └─ 克制度/一致性/高级感/品牌方向/信息效率
│
└─ 6. REFLECT（结构化反思）
    ├─ What worked: 有效策略
    ├─ What failed: 无效尝试
    └─ Dead ends: 避免重复的路径
```

## 4. 5 维度突破策略矩阵

| 维度 | 瓶颈信号 | Pivot 策略 | 技术手段 |
|------|---------|-----------|---------|
| 克制度 | 字号/装饰 > 8 种 | 减法收敛 | Token 审计 → 合并 → 消除 |
| 一致性 | 跨组件间距方差 > 4px | 间距网格强制 | spacing scale 锚定 |
| 高级感 | 评分 < 8.5 且其他维度已达标 | 材质/光影/微动效 | CSS gradient + box-shadow 精细调校 |
| 品牌方向 | 偏离 Bloomberg/quant DNA | 数据密度 + 专业工具感 | 参考标杆 → 模仿 → 超越 |
| 信息效率 | chars/Kpx < 12 | 信息可视化加法 | 引入小型图表/指标/状态标记 |

## 5. 退出条件

**硬性退出**（全部满足才结束）：
1. 17/17 页面 composite score ≥ 9.0
2. P0 问题 = 0（所有页面）
3. Token 合规：deprecated = 0, hardcoded oklch = 0, var() ≥ 80%

**保护退出**（安全阀）：
1. 30 轮用尽 → 输出最终报告 + 未达标页面诊断
2. 单页面连续 4 轮停滞在 8.5-8.9 → 标记为「需 React 突破」，跳过
3. 全局平均分连续 3 轮 < 0.1 变化 → 全局突破协议

## 6. 质量控制

### 跨轮防退化
- 每轮修复后检查：已达标维度是否退化（下降 > 0.3 → 回滚 + 重新评估）
- Anti-oscillation：记录每轮决策集，禁止后续轮次推翻

### Anti-oscillation
- 记录每轮采纳的决策集（D1, D2, D3...）
- 后续轮次不得推翻已采纳决策，除非新证据明确证伪
- 连续轮次不得使用相同策略 pivot

### 突破协议加强版（Phase 2+ 启用）
- 单页面连续 2 轮提升 < 0.2 → 自动维度 pivot
- 连续 3 轮停滞 → 结构重评
- 策略 pivot 矩阵：减法 → 信息可视化加法 → 材质升级 → 布局重构

## 7. 输出物

### 更新的原型文件
- 17 个 HTML 页面（每个 ≥ 9.0 分）
- shared CSS/JS（token 合规）
- inline styles 数量显著降低

### 更新的 Manifest
```json
{
  "edition": "v1",
  "status": "iterating-v2",
  "pages": [{
    "id": "cross-market",
    "score": 9.0,
    "rounds": 3,
    "roundsV2": 2,
    "status": "done"
  }],
  "iterationV2": {
    "startedAt": "2026-04-05",
    "goalScore": 9.0,
    "maxRounds": 30,
    "phases": ["quick-harvest", "gap-fill", "benchmark-push", "ceiling-chase"]
  }
}
```

### 迭代日志
- 路径：`docs/reviews/2026-04-05-edition-v1-iteration-v2.md`
- 每轮记录：页面、策略、5 维度分数、修复摘要、REFLECT

### Git 标签
- 完成时打 tag：`edition-v1-iter-v2`

## 8. 完成标准 Checklist

```
✅ 17/17 页面 composite score ≥ 9.0
✅ P0 问题 = 0（所有页面）
✅ Token 合规：deprecated = 0, hardcoded oklch = 0
✅ 视口验证：VP-STANDARD + VP-COMPACT 通过
✅ 跨页一致性：颜色/字体/间距 token 一致
✅ Manifest 更新完毕
✅ 迭代日志完整
✅ bun run check 通过（如有相关 runtime 代码变更）
```

## 9. 风险预案

| 风险 | 触发条件 | 应对 |
|------|---------|------|
| CSS 天花板 | 某页面连续 4 轮停滞在 8.5-8.9 | 输出诊断报告，标记为「需 React 突破」 |
| 预算不足 | 30 轮用完但仍有页面 < 9.0 | 输出优先级排序，建议追加轮次或降级为 React 迁移前置准备 |
| 策略穷尽 | 突破协议 3 次 pivot 仍无进展 | 启动基准对标研究（竞品分析），寻找新维度 |

## 10. 执行参数

```yaml
edition: v1
mode: iterate
goalScore: 9.0
maxRounds: 30
level: best
impeccable_chain: [polish, typeset, arrange]
exit_condition: all_pages_ge_9.0
strategy: low-score-first
phases:
  - name: quick-harvest
    rounds: 1-11
    target: Tier A pages (8.0)
  - name: gap-fill
    rounds: 12-20
    target: pages still < 9.0
  - name: benchmark-push
    rounds: 21-25
    target: all pages ≥ 9.0
  - name: ceiling-chase
    rounds: 26-30
    target: highest potential → 9.5
```
