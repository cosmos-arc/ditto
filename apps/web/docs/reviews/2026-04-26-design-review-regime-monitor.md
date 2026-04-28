# Regime Monitor Design Cycle Review

**目标**: `/ditto-design-cycle page-regime-monitor.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-regime-monitor.html`  
**结果**: 9.65 / 10（静态 HTML/CSS 原型阶段上限区间，未标记 done）

## 结论

本轮将 Regime Monitor 从结构门禁失败推进到可稳定验收的 best 级原型。没有虚标 10：剩余差距主要来自真实图表交互、模型参数切换、策略上下文联动等 React 实现阶段能力。

## 创意方向

- 策略: 基础门禁修复 + chart-first 数据语义精修
- 重点区域: analytical shell 识别、status bar 遮挡、compact 右 rail、Regime Timeline 数据语义
- 标杆参考: Bloomberg Charts 的跨资产图表分析语境；TradingView Heatmaps 的快速趋势/异常扫视模型
- 约束: 不新增 spec 外产品模块，不改 Design Token，不引入新依赖

## 关键修改

1. 给页面根 shell 补齐 `shell-analytical` 识别类，让门禁按 analytical workspace 口径识别。
2. 将 status bar 从 fixed 改入 shell grid 的 `status` 行，消除标准/紧凑视口遮挡。
3. 将右侧驱动面板标记为 `data-contract-slot="right-rail"`，避免和左侧 shell rail 混淆。
4. 修复共享 analytical 规则对嵌套 `activity-stack` 的串扰，显式定义 `regime-layout` grid areas。
5. 改为右 rail 自然高度 + 内部滚动，紧凑视口不再裁切 Key Drivers / Regime Composition。
6. 补齐 chart body 高度规则，让 Regime Timeline 占满 chart-first 主工作面。
7. 将趋势线、事件点、crosshair 调整到与 72% 置信度一致的数据语义高度。
8. 将本页显式 `letter-spacing` 归零，符合当前前端排版约束。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.6 | 去除 fixed 遮挡与错位后，页面仍保持低噪声终端气质 |
| 一致性 | 9.7 | shell family、contract slot、status flow 与现有门禁口径一致 |
| 高级感 | 9.6 | 主图、概率 donut、状态矩阵和因子 radial 形成统一分析语境 |
| 品牌方向 | 9.7 | Graphite Studio 暗色金融终端、A 股红涨绿跌语义清晰 |
| 信息效率 | 9.65 | 标准视口全量可扫视，紧凑视口右 rail 可滚动且不裁切内容 |
| 综合 | 9.65 | 五维均值，P0/P1/P2 门禁为 0 |

## 验证

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-regime-monitor.html --out-dir test-results/ditto-design-cycle-gates/regime-monitor-round4
```

结果:

- Status: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/regime-monitor-round4/page-regime-monitor.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/regime-monitor-round4/page-regime-monitor.html-VP-COMPACT.png`

Playwright 交互抽检:

- tab: Regime Status / Switch History / Strategy Impact 均可切换
- overlay: AI Regime 解读可打开和关闭
- zones: default / states / overlays 均可切换
- compact right rail: 可滚动，内容不再被 flex 裁切

静态审计:

- inline styles: 0
- duplicate ids: 0
- explicit page letter-spacing: 0
- state gallery cards: 20
- overlay gallery cards: 1

## 未达 10 的原因

- Regime Timeline 仍是静态 CSS 图表，缺少真实缩放、hover crosshair、时间粒度切换和数据点详情。
- `1M/3M/6M/1Y` 与筛选按钮仍是静态原型控件，尚未驱动真实数据重算。
- Strategy Impact 与 AI 解读没有和当前 Regime 选择、右 rail 选中因子形成真实上下文联动。

## Benchmark Notes

- Bloomberg Charts: 强调跨资产图表分析、策略验证和更快形成交易观点。参考: https://www.bloomberg.com/professional/product/charts/
- TradingView Heatmaps: 热力图用于从全局趋势快速下钻到细节，颜色和分组帮助发现市场变化、趋势和异常。参考: https://www.tradingview.com/support/solutions/43000766446-tradingview-heatmaps-from-global-trends-to-details/
