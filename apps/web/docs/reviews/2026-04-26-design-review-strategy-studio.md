# Strategy Studio Design Cycle Review

**目标**: `/ditto-design-cycle page-strategy-studio.html --iterate --goal 10 --max-rounds 100 --level best`  
**日期**: 2026-04-26  
**对象**: `docs/designs/specs/prototypes/page-strategy-studio.html`  
**结果**: 9.7 / 10（best 级结构修复 + 日志抽屉恢复，未标记 done）

## 结论

本轮将 Strategy Studio 从「截图可见但 shell 结构门禁失败」推进到可稳定验收的 best 级原型：

- 修复 `.shell-studio` 未被门禁脚本识别的问题，补齐 `.shell-studio` shell selector 回归测试。
- 修复 Rail 导航中提前闭合的 `</div>`，让 Header / Sources / Main / Inspector / Logs 全部回到 shell grid 内。
- 将 Logs 行从 `--shell-status-bar-height` 恢复为 `minmax(128px, 15vh)`，避免只剩 tab 条、日志正文不可见。
- 反馈后追加 R5：因子预处理管道改为 2x2 紧凑网格，避免横向溢出和 compact 视口遮挡。
- 反馈后追加 R5：底部 `Dry Run` / `编译日志` 接入 `data-tabs` 交互系统，三个日志面板可真实切换。
- 移除默认视图 `data-ticker` 数值动画属性，视觉验收截图保持确定性。
- 新增 `scripts/page-strategy-studio-prototype.test.ts`，覆盖 shell 结构、日志抽屉高度和默认视图确定性。
- 静态审计：0 inline style、0 duplicate id、状态画廊 20 cards、弹层画廊 5 cards。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.7 | 三栏 Studio、日志抽屉、右侧 Inspector 都回到克制终端密度，无额外装饰膨胀 |
| 一致性 | 9.7 | Shell grid、contract slot、门禁脚本识别口径和 manifest 指标已同步 |
| 高级感 | 9.6 | 参数矩阵、因子权重、绩效卡、日志台形成专业策略开发语境 |
| 品牌方向 | 9.7 | Graphite Studio 暗色金融终端、A 股策略研究语义与 Research 域一致 |
| 信息效率 | 9.8 | 首屏可同时扫视因子、策略参数、AI 建议、风险提示和校验日志 |
| 综合气质 | 9.7 | P0/P1 为 0；剩余差距主要来自静态 HTML 阶段的真实交互上限 |

## 验证

```bash
bunx vitest run .claude/skills/ditto-design-cycle/scripts/verify-gates-core.test.mjs scripts/page-strategy-studio-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-strategy-studio.html --out-dir test-results/ditto-design-cycle-gates/strategy-studio-feedback-fix-r2
```

结果：

- Targeted tests: 12 tests passed
- Prototype gates: PASS
- Blocking Issues: None
- Non-Blocking Issues: None
- VP-STANDARD screenshot: `test-results/ditto-design-cycle-gates/strategy-studio-feedback-fix-r2/page-strategy-studio.html-VP-STANDARD.png`
- VP-COMPACT screenshot: `test-results/ditto-design-cycle-gates/strategy-studio-feedback-fix-r2/page-strategy-studio.html-VP-COMPACT.png`

静态审计：

- inline styles: 0
- duplicate ids: 0
- default contract slots: 2
- state gallery cards: 20
- overlay gallery cards: 5
- default-view `data-ticker` / `data-counter`: 0

交互抽查：

- Form Builder / Code Editor mode 切换通过
- 保存策略 overlay 打开 / 关闭通过
- default / states / overlays 三区 radio 切换通过
- 因子预处理管道浏览器实测 `scrollWidth <= clientWidth`
- `Dry Run` 与 `编译日志` 点击切换通过

## 未达 10 的原因

不虚报 10。当前仍是 HTML/CSS 静态原型，距离真实顶级策略工作室还有三类差距：

- 表单、代码编辑器、校验日志和回测提交仍是 mock 状态，缺少真实状态机与错误回放。
- Inspector tabs 与主编辑区尚未根据选中因子、参数行和日志行做真实上下文联动。
- 绩效卡、稳定性 sparkline、参数矩阵仍是静态展示，缺少可交互的时间窗口、归因 drilldown 和回测对比。
