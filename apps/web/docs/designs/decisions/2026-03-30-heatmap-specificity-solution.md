# Heat Map 跨域特异性解决方案

**日期**: 2026-03-30
**来源**: Design Review — Cross-Market Overview (R10 FIX-04)
**状态**: 已采纳

## 背景

Cross-Market Matrix 的行级背景（row-lead/row-lag ambient tint）与热区背景（heat map）存在 CSS 特异性冲突。

行 tint 使用 `.matrix-table tr.row-lead td`（specificity 0-3-0），热区使用 `.matrix-table td[data-heat]`（specificity 0-2-0）。由于行 tint 特异性更高，热区背景被覆盖，导致所有 lead/lag 行中的 heat cell 只显示行 tint 颜色，无法展示热区颜色。

## 决策

为所有热区选择器添加行类型限定，将特异性提升至 0-4-0（4 个 class/attribute 选择器），覆盖行 tint 的 0-3-0：

```css
/* Full cross-domain coverage: all heat levels in both row types */
.matrix-table tr.row-lead td[data-heat="3"] { background: oklch(0.670 0.170 20 / 0.17); }
.matrix-table tr.row-lead td[data-heat="2"] { background: oklch(0.670 0.170 20 / 0.10); }
/* ... (10 rules total: 5 heat levels × 2 row types) */
.matrix-table tr.row-lag td[data-heat="-2"] { background: oklch(0.680 0.120 175 / 0.10); }
```

## 理由

- 不使用 `!important`（破坏可维护性）
- 不降低行 tint 特异性（影响其他行级样式）
- 显式声明 10 条规则而非用通用选择器 + inherit hack（之前 inherit 方案导致反向透明）

## 影响

- `page-cross-market.html` — 10 条 CSS 规则
- 5 级 alpha 梯度: 0.05 / 0.10 / 0.17（R12 收敛值，R10 初始值 0.06/0.14/0.22）
