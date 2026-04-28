# Factor Analysis Design Cycle Review

**目标**: `/ditto-design-cycle page-factor-analysis.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-factor-analysis.html`  
**结果**: 9.7 / 10（best 级 Object Hub 精修，静态原型阶段未虚报 10）

## 结论

本轮把 Factor Analysis 从“视觉可用但门禁识别失败”的旧 Object Hub 原型推进到可稳定验收状态：

- `object-shell shell-hub` 根结构恢复，prototype gates 可识别 rail/header/main/sidebar。
- `data-contract-slot="main"` / `sidebar` 下沉到真实可见区域，不再挂在 `display: contents` wrapper 上。
- 修复 rail DOM 多余闭合标签，研究域 rail 保持 5 个导航入口。
- Header 三个 CTA 和 2x2 诊断详情都有 default-view 真实 overlay，不再只存在画廊预览。
- Compact 视口隐藏冗余 context strip，IC 统计摘要不再被底部状态条压住。
- SVG 衰减图文字改为 tokenized CSS class，截图审查保持 0 inline style / 0 `font-size` attribute。
- 新增 `scripts/page-factor-analysis-prototype.test.ts` 覆盖 shell、contract slot、overlay、截图稳定性与 compact 可读性。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 修复以结构和信息可达性为主，保留 Graphite Studio 低噪声表达 |
| 一致性 | 9.8 | Object Hub / contract slot / overlay 触发与 Backtest、Strategies Detail 对齐 |
| 高级感 | 9.7 | IC 四象限、右侧研究上下文和 frosted shell 更稳定，compact 视口更完整 |
| 品牌方向 | 9.7 | 符合 Research-heavy 工作流的量化终端密度与克制气质 |
| 信息效率 | 9.8 | 首屏保留 KPI、2x2 diagnostics、侧栏摘要和可触发详情 |
| 综合气质 | 9.7 | Gates 全绿；剩余差距来自静态原型交互上限 |

## 验证

```bash
bunx vitest run scripts/page-factor-analysis-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-factor-analysis.html --out-dir test-results/ditto-design-cycle-gates/factor-analysis-final
bun run check
```

结果：

- Targeted tests: 6 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/factor-analysis-final/page-factor-analysis.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/factor-analysis-final/page-factor-analysis.html-VP-COMPACT.png`
- `bun run check`: 未通过，阻塞在既有 `src/` TypeScript 错误；本轮改动未触碰这些失败文件。代表性错误包括 `src/components/chart/chart-components.test.tsx` 未导入测试全局、`src/components/data/data-table/data-table.test.tsx` 泛型不匹配、多个 route `handle` 类型不被 TanStack Router 当前类型接受、`src/types/index.ts` 重复导出。

## Benchmark Notes

- Bloomberg Terminal UX: 参考“隐藏复杂性”并避免工作流干扰，适合约束 overlay 和 compact 信息密度。<https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/>
- Linear UI redesign: 参考降低视觉噪声、保持 alignment、提升导航层级密度。<https://linear.app/blog/how-we-redesigned-the-linear-ui>
- Linear latest refresh: 参考信息密集界面中“不是所有元素都应有同等视觉重量”的分层原则。<https://linear.app/now/behind-the-latest-design-refresh>

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，缺少真实图表十字线、缩放、tooltip、选区联动、异步加载与后端状态机。进入 React 实现或增强交互原型后，才有合理空间继续冲击 9.8-10。
