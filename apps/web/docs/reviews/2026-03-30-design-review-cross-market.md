# Design Review: Cross-Market Overview

**Date**: 2026-03-30
**Target**: `docs/designs/specs/prototypes/style-b-graphite-studio/page-cross-market.html`
**Quality Level**: best
**Review Roles**: UI Designer / UX Reviewer / Product Manager / Copy Editor / Art Director
**Mode**: 自主迭代（goal: 9.5, max-rounds: 3）

## Version Info
- **Tag (final)**: `review/round-3`
- **Commits**: `7c821b4` → `69e2190` → `ad64175`
- **变更查看**: `git diff review/round-1..review/round-3 -- page-cross-market.html`

## Summary
- P0 问题: 28 个（已修复 28 个）
- P1 问题: 35 个（采纳 22 个）
- P2 建议: 45 个（采纳 6 个）
- 设计决策变更: 1 个（text-tertiary 对比度提升）
- Lighthouse 评分: A11y 96, Best Practices 100
- **最终综合气质: 9.2/10**（目标 9.5，差距 0.3）

## 迭代历程

| 轮次 | 综合分 | P0 | 采纳建议 | 关键改动 | 状态 |
|------|--------|----|---------|---------|------|
| R1 | 7.75 | 10→0 | 18 | Token 一致性、消除硬编码 px、中文标签初版 | 继续 |
| R2 | 8.90 | 18→0 | 22 | 留白优化(32px gap)、中文标签全覆盖、terminal 字体、matrix 去accent bar | 继续 |
| R3 | 9.20 | — | 6 | ambient row tint、brand signature glow、premium elevation shadow | 达标 ✗（max-rounds） |

**评分快照**:
```
┌─────────────┬─────────┬─────────┬─────────┬─────────┐
│ 指标         │ Round 1 │ Round 2 │ Round 3 │ 趋势     │
├─────────────┼─────────┼─────────┼─────────┼─────────┤
│ 克制度       │  8.0    │  9.0    │  9.0    │  ↑→     │
│ 一致性       │  7.0    │  8.5    │  9.2    │  ↑↑     │
│ 高级感       │  8.0    │  8.5    │  9.0    │  ↑↑     │
│ 品牌方向     │  8.0    │  9.0    │  9.2    │  ↑↑     │
│ 综合气质     │  7.75   │  8.90   │  9.20   │  ↑↑     │
│ P0 残留      │  10     │  0      │  0      │  ✓      │
│ Lighthouse   │ 82/90   │ 96/100  │  96/100 │  ↑→     │
│ 状态         │ 继续    │ 继续    │ 终止    │         │
└─────────────┴─────────┴─────────┴─────────┴─────────┘
```

**自动裁决记录**:
- R2-Conflict-01: UX-106 vs AD: Matrix section accent bar → 移除（UX 胜，减少视觉噪音）
- R2-Conflict-02: PM-002 vs AD: 恢复 Scope Strip 双层 → 驳回（AD 整体视角优先，留白更关键）
- R2-Conflict-03: PM-001 vs AD: 恢复商品卡片 → 延后 R3（架构变更过大，R3 未执行）
- R2-Conflict-04: CE-009 vs PM: Regime 标签中文化 → 采纳（中文优先定位）
- R2-Conflict-05: CE-014: 结论引用原油 → 改为引用利率（与 L1 卡片一致）

## 气质评分卡（Art Director — Final R3）

| 维度 | 评分 | 说明 |
|------|------|------|
| 克制度 | 9.0/10 | 装饰元素极简，7 种类型略超 ≤6 阈值但可接受。无冗余视觉元素 |
| 一致性 | 9.2/10 | inline style 全部清零，token 体系统一。中英文标签统一为中文 |
| 高级感 | 9.0/10 | ambient row tint + elevation shadow + conclusion glow 显著提升。仍差 Bloomberg 级别的"重量感" |
| 品牌方向 | 9.2/10 | context bar brand glow 成功建立品牌签名。terminal letter-spacing 全局统一 |
| **综合气质** | **9.2/10** | |

**视觉指纹对比**（Phase 1 基线 → R3 最终）:
| 指标 | 基线 (R1前) | R2 后 | R3 最终 | 变化 |
|------|-----------|-------|--------|------|
| Hardcoded px | 42 | 6 | 0 | -42 ✓ |
| Inline styles | 4 | 0 | 0 | -4 ✓ |
| Decorative types | 9 | 7 | 7 | -2 |
| text-tertiary L | 0.43 | 0.55 | 0.55 | +0.12 ✓ |
| Card grid gap | 8px | 12px | 12px | +4px ✓ |
| Main section gap | 16px | 32px | 32px | +16px ✓ |
| Card padding | 10/12px | 12/16px | 12/16px | +2/+4px ✓ |

**Art Director 裁决记录**:
- R1: 移除 card hover translateY(-1px)（SaaS 浮起效果，不符合 terminal 克制感）
- R2: 移除 matrix section accent bar（与 card lead/lag 竞争视觉注意力）
- R2: Tab band 去除 background fill（L3 补充视角不应有 L1 级视觉权重）
- R3: 全部 polish 变更保留（ambient tint + glow 在克制框架内）

## Key Decisions

### DD-001: text-tertiary 对比度提升
- **决策**: `--text-tertiary` L 值从 0.430 提升至 0.550
- **理由**: 原值在 surface-app 上仅 2.42:1 对比度，远低于 WCAG AA 4.5:1。提升至 0.550 后约 4.0:1，接近 AA 阈值
- **影响**: 28 个使用 text-tertiary 的标签元素可读性显著改善

### DD-002: Context Bar 标签统一中文
- **决策**: Regime→市态, Vol→波动, DXY→美元, Alerts→预警
- **理由**: 产品定位中文为主，英文缩写标签破坏第一印象的专业度
- **影响**: 8 个 context bar 标签全部中文化

### DD-003: Regime 标签中文化
- **决策**: Risk-On→风险偏好, High Beta→高弹性, Mixed→分化, Rate Pressure→利率承压, Dollar Soft→美元偏弱, Safe Haven→避险
- **理由**: 与 Context Bar 中文化保持一致，6 张卡片 regime 全部中文化
- **影响**: 页面文案语言统一性显著提升

## Changes Made

### Round 1 累计变更
| ID | 类型 | 描述 |
|----|----|------|
| UI-001~010 | P0 | Token 一致性修复（42 个硬编码 px → CSS 变量） |
| UX-001~003 | P0 | 可访问性修复（skip link, ARIA, focus-visible） |
| CE-001~007 | P1 | 文案优化（Drilldown CTA、Context Bar 值、判断句更新） |
| AD-001~003 | P1 | 视觉精修（scope strip 合并、accent bar、badge 动画） |

### Round 2 累计变更
| ID | 类型 | 描述 |
|----|----|------|
| UI-201~208 | P0/P1 | 缺失变量、inline style 清零、border-radius token 化、字号统一 |
| UX-101~108 | P0/P1 | text-tertiary 对比度、tr role 修复、card 间距、rail 间距、fade-out |
| PM-003 | P1 | Macro Drivers 添加 CN10Y |
| CE-008~015 | P0/P1 | Context Bar 标签中文、Regime 标签中文、纳判断句、AI beta 中文化、结论原油→利率 |
| AD-001~008 | P0/P1 | 留白优化(32px gap)、rail padding、matrix 行密度、drivers strip 独立化、accent bar 3px、conclusion surface、tab band 降权 |

### Round 3 累计变更
| ID | 类型 | 描述 |
|----|----|------|
| AD-R3-001 | Polish | Matrix lead/lag ambient row tint (3%/6%) |
| AD-R3-002 | Polish | Matrix lead/lag 全行着色 + semibold market name |
| AD-R3-003 | Polish | Context bar brand-accent box-shadow glow |
| AD-R3-004 | Polish | Market card hover elevation shadow |
| AD-R3-005 | Polish | Card index 20→24px, letter-spacing -0.02em |
| AD-R3-006 | Polish | Section titles unified: semibold + 0.06em letter-spacing |

## Updated Specs
- `tokens-style.css`: `--text-tertiary` L 值 0.430 → 0.550（对比度修复）

## 待同步清单

> 以下变更已通过验收，可使用 `/ditto-design-review page-cross-market.html --sync` 同步到设计文档。

### `docs/designs/specs/`
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 修正 | `--text-tertiary` 对比度提升至 oklch(0.55) | UX-101 |
| 2 | 新增 | 页面级 `--space-3`(0.1875rem), `--radius-3`, `--font-size-9`(9px) | UI-201 |
| 3 | 修正 | Context Bar 标签统一中文规范（市态/波动/美元/强势/承压/风格/事件/预警） | CE-008 |
| 4 | 新增 | Regime 标签中文映射表（风险偏好/高弹性/分化/利率承压/美元偏弱/避险） | CE-009 |
| 5 | 修正 | Macro Drivers 固定 7 项（DXY/US10Y/**CN10Y**/VIX/XAU/WTI/USD/CNH） | PM-003 |
| 6 | 修正 | Market Card 判断句信息密度标准（≥2 独立信号） | CE-010 |
| 7 | 修正 | Matrix 结论仅引用 L1 已展示市场 | CE-014 |

### `docs/designs/decisions/`
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 新增 | ADR: text-tertiary 对比度提升至 0.550 | UX-101 |
| 2 | 新增 | ADR: 跨市场概览 Context Bar 标签中文化 | CE-008 |
| 3 | 新增 | ADR: Regime 标签中文化映射表 | CE-009 |

## 未达目标分析

**目标**: 9.5/10 综合气质
**实际**: 9.2/10
**差距**: 0.3 分，主要来自**高级感**维度（9.0 vs 9.5 目标）

**差距原因**:
1. **Surface depth 不够丰富**: Bloomberg Terminal 的"重量感"来自多年的视觉语言积累，原型在单轮迭代中难以完全复制
2. **数据可视化 sophistication**: Matrix 表格仍是传统 HTML table，缺少 Bloomberg 级别的条件格式（如热力图渐变、sparkline）
3. **微交互层级**: 原型为静态 HTML，无法展示真实产品中的流畅过渡动画

**建议后续方向**:
- 在 React 实现阶段引入条件格式热力图（Matrix 单元格背景色按值映射）
- 增加 sparkline 微图表（Market Card 内嵌小型趋势线）
- 考虑自定义字体或调整字重配置，增强"终端感"的 typographic 签名
