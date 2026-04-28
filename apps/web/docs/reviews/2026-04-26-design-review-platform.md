# Platform Design Cycle Review

**目标**: `/ditto-design-cycle page-platform.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-platform.html`  
**结果**: 9.4 / 10（CSS 原型阶段上限区间，未标记 done）

## 结论

本轮将 Platform Ops Console 从「顶部信息密集、主工作区下半屏过空」推进到更完整的 best 级运维控制台：

- 默认 Data Providers 工作区补齐 `DQ 评分历史` 与 `Incident History` 证据带，承接蓝图中的 DQ 评分历史与 Logs / Incident History。
- Resources / Quotas 表格修复 4 个表头对应 5 个数据单元的语义错位，新增「进度」列。
- DQ 历史图使用容器比例柱高、阈值网格线和健康/降级/故障色，避免空白区域无信息。
- Incident History 按时间、服务、摘要、处理状态四列铺满可用高度，和右侧 Recent Events 形成主/辅信息分层。
- 新增原型结构测试，覆盖表格列契约、DQ 历史采样点、Incident 行数以及柱高 CSS 类完整性。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.4 | 保持 graphite ops-console 克制暗色语法，新增内容使用分隔线和数据色而非装饰卡片 |
| 一致性 | 9.5 | 表格列契约、token 化柱高/颜色、tab/overlay 交互语义保持一致 |
| 高级感 | 9.4 | DQ 历史 + incident stream 增加专业终端记忆点，仍未进入真实交互图表阶段 |
| 品牌方向 | 9.5 | 更接近 Bloomberg/quant desk 的监控台密度，同时保留 Linear/Vercel 的冷静边界 |
| 信息效率 | 9.5 | 标准/紧凑首屏不再留下大面积无信息空区，可扫视数据块明显提升 |
| 综合气质 | 9.4 | P0/P1 为 0；静态 CSS 原型阶段接近当前天花板 |

## 关键修改

1. 新增 `.ops-evidence-strip`，在默认 tab 中承载 DQ score history 与 incident evidence。
2. 新增 12 个 `data-dq-point` 采样点、4 个 DQ 信号摘要和 5 行 `data-incident-row`。
3. 新增 `.dq-h-*` 高度 token 类，并用测试防止 HTML 引用未定义柱高。
4. 修复 Resources / Quotas 表头：新增「进度」列，使每行 `td` 数与 `th` 数一致。
5. 新增 `scripts/page-platform-prototype.test.ts`，锁定表格契约与证据带完整度。

## 验证

```bash
bun run test:run scripts/page-platform-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-platform.html
rg -n "style=|@ts-ignore|@ts-expect-error|\bany\b" docs/designs/specs/prototypes/page-platform.html scripts/page-platform-prototype.test.ts
```

结果：

- Platform prototype test: 2 passed
- Prototype gates: PASS
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/page-platform.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/page-platform.html-VP-COMPACT.png`
- Blocking Issues: None
- Non-Blocking Issues: None
- inline style / ignore / any audit: 0 matches

额外交互抽检：

- 4 个 tab 均可切换，当前 panel 可见。
- 3 个 overlay 均可通过 checkbox 状态显示。

## 未通过全量门禁

`bun run check` 已执行，但在 `tsc -b` 阶段失败。失败集中在既有 `src/` TypeScript / test 配置问题，例如：

- `src/components/chart/chart-components.test.tsx`: Vitest globals / unused import / delete operand 类型错误。
- `src/components/data/data-table/data-table.test.tsx`: `ColumnDef<TestRow>` 与 `Record<string, unknown>` 泛型不匹配。
- 多个 route 文件的 `handle` 字段与当前 TanStack Router 类型不匹配。
- `src/types/index.ts`: duplicate identifier 与导出名漂移。

这些错误不来自本轮修改的 `docs/designs/specs/prototypes/page-platform.html` 或 `scripts/page-platform-prototype.test.ts`，因此本轮只标记为「原型范围验证通过」，不标记 done。

## 未达 10 的原因

目标 10 不应在静态 HTML/CSS 原型里虚报。剩余差距主要来自：

- DQ 历史仍是静态柱图，没有 hover crosshair、区间过滤和服务筛选联动。
- Incident History 不能真实选中事件后驱动右侧 rail、overlay 或日志上下文。
- Health Strip 与主表的数值仍是 mock 层，缺少真实 data freshness aging 和实时更新。

## Benchmark Notes

- Bloomberg Terminal / Launchpad 的强项是可定制动态监控、告警、图表和市场新闻组合，本轮用 DQ 历史 + Incident History 增强主工作区信息密度。
- Linear 最新视觉刷新强调更平静、熟悉、流动的界面，本轮保留细线、弱边界和克制动效，避免把运维页做成装饰型 dashboard。
