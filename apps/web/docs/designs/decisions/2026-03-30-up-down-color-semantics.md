# Up/Down 色彩语义规范

**日期**: 2026-03-30
**来源**: Design Review — Cross-Market Overview (R10 AUTO-DECISION #3/#4)
**状态**: 已采纳

## 背景

Cross-Market Matrix 中，利率上行（+7bp）导致成长股估值承压（利空），但数值显示为绿色（positive）。DXY（美元指数）下跌（-0.4%）但美元走弱对非美资产是利好。金融产品中"涨跌"和"利多利空"的语义取决于资产类型和上下文，不能简单地用颜色统一。

## 决策

**坚持数值语义（涨=绿/跌=红），不按金融语义（利好=绿/利空=红）着色。**

具体规则：
- 正数值（+X%）→ 绿色（`market-up-fg`）
- 负数值（-X%）→ 红色（`market-down-fg`）
- 中性判断 → `text-tertiary`

## 理由

1. **行业惯例**: Bloomberg Terminal、TradingView、Wind 等主流金融终端均采用数值语义着色
2. **可理解性**: 用户看到 +7bp 绿色，理解为"利率涨了 7bp"，而非"这是好事"
3. **一致性**: 统一规则避免不同资产类型需要不同的色彩逻辑
4. **结论文案补全语义**: 结论区用文字补充金融语义（如"长端承压，降息预期降温"），弥补纯色彩的信息缺失

## 影响

- 所有使用 `market-up-fg` / `market-down-fg` 的页面和组件
- Cross-Market Matrix、Market Card、Driver Strip 等模块
