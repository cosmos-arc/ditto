# Backtest Result Design Cycle Review

**目标**: `/ditto-design-cycle page-backtest-result.html --iterate --goal 10 --max-rounds 100 --level best`
**日期**: 2026-04-26
**对象**: `docs/designs/specs/prototypes/page-backtest-result.html`
**结果**: 9.7 / 10（CSS 静态原型阶段上限区间，未标记 done）

## 结论

本轮将 Backtest Result 从「视觉高分但门禁识别失败」推进到可稳定验收的 best 级对象中心原型：

- `bun run prototype:gates` 在 VP-STANDARD 1536x1080 与 VP-COMPACT 1366x768 全绿
- Object Hub DOM 结构恢复，门禁可识别 shell/header/main/sidebar
- `tab-group` 正式进入 shell grid，默认主图区域吃满标准视口，底部空白显著减少
- Header 中 5 个 overlay 触发器均有真实默认视图弹层，不再只存在画廊预览
- Backtest 特有 running / partial 状态补齐到状态画廊
- 静态审计：0 inline style、0 external ref、0 duplicate id、0 `oklch()` 函数引用

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 主图、KPI、成本侧栏和状态条保持低噪声密度；无 prototype tool 污染 |
| 一致性 | 9.7 | Object Shell / contract slot / grid area 与门禁识别口径一致 |
| 高级感 | 9.7 | NAV + drawdown 主画布、成本归因、真实 overlay 形成更完整的专业终端语境 |
| 品牌方向 | 9.6 | Graphite Studio 暗色量化工作台气质稳定，研究域对象中心路径清晰 |
| 信息效率 | 9.7 | Compact 首屏可见 KPI、主图、成本侧栏和关键统计；running/partial 状态覆盖更完整 |
| 综合气质 | 9.7 | P0/P1 为 0，CSS 静态原型阶段已接近天花板 |

## 关键修改

1. 给根节点添加 `object-shell shell-hub`，给默认 main/sidebar 添加合同槽位。
2. 将 `.tab-group` / `.tab-panel` 纳入 shell grid flow，主工作面填满可用高度。
3. 修正 `.panel-shrink` 继承 `flex: 1` 的问题，避免关键统计卡被空白拉伸。
4. 将 Header 的导出、启用信号、AI 解读、加入对比、Compare 视图接入真实 overlay。
5. 补齐 Backtest running / partial 状态：NAV、交易明细、风险图表。
6. 同步 `.edition-manifest.json`：score 9.7、rounds 3、inline after 0、stateVariants 18。

## 验证

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-backtest-result.html --out-dir test-results/ditto-design-cycle-gates/backtest-result-final
```

结果：

- Status: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/backtest-result-final/page-backtest-result.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/backtest-result-final/page-backtest-result.html-VP-COMPACT.png`

交互抽查：

- Tabs: 7/7 可切换
- Default overlays: 5/5 可打开
- State gallery cards: 18
- Overlay gallery cards: 5

## 未达 10 的原因

目标 10 在当前 HTML/CSS 静态原型阶段不宜虚报。剩余差距主要来自：

- 主图仍是静态 SVG，缺少真实十字线、缩放、拖拽选择区间和 tooltip。
- 右侧成本/归因侧栏不会随 tab 与图表选区真实联动。
- running / partial 状态为静态画廊表达，尚未接入真实 Backtest Engine 进度。
