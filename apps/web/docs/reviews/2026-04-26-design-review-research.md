# Design Review: Research Workspace

日期: 2026-04-26
原型: `docs/designs/specs/prototypes/page-research.html`
命令: `/ditto-design-cycle page-research.html --iterate --goal 10 --max-rounds 100 --level best`

## 结论

本轮从 9.20 提升到 9.45。`goal 10` 属于理论满分，本轮未伪造满分；在 HTML/CSS 原型介质内，当前主要瓶颈已经从布局正确性转为更细的真实产品交互与 React 实现阶段的动态数据细节。

## 创意方向

- 策略: 基础门禁修复 + best 级精修收敛
- 重点区域: Analytical shell contract、默认视图底部错位、字距系统、因子分析入口、交互可用性
- 标杆参考: Bloomberg Terminal 的高密度专业工作台；Linear 的克制边界、低噪声层次与稳定交互反馈
- 约束: 不新增 spec 外产品模块，不改 Design Token，不引入新依赖

## 修复清单

- 将 shell slot 对齐到 `strip/main/activity/analysis`。
- 为右侧活动区保留 `activity-stack` 样式，同时补充 `right-rail` 识别类，让门禁能识别二级区。
- 隐藏与 Research 蓝图冲突且视觉错位的 legacy tab 条。
- 将负字距和非零字距统一为 `letter-spacing: 0`。
- 将相关性矩阵数值从 `font-size-8` 提升到 `font-size-10`。
- 将「进入因子分析」从静态文本改为真实链接。
- R12: 将底部 analysis band 四个 tab 改为指标/内容分栏，压缩图表安全区、宽度条、相关性热力图和备注列表，消除 compact 高度下的拥挤与遮挡。
- R13: 将 `因子宽度` 改为双列小条形网格；将 `相关性` 改为居中的 micro heatmap，隐藏底部 band 内拥挤行标签，详情保留在 hover title。
- R14: 按业界热力图模式补强 `相关性`：矩阵保留强相关焦点点位，右侧增加 `动量 / 情绪 0.72` callout 与 -1/+1 色阶，弱化自相关对角线，避免底部 band 里出现空洞色块。

## 评分卡

| 维度 | 分数 | 依据 |
|------|------|------|
| 克制度 | 9.4 | 去掉错位 tab 和负字距后，默认视图噪声下降 |
| 一致性 | 9.5 | contract slot 与 analytical shell 映射一致 |
| 高级感 | 9.3 | 维持材质、热力背景、图表层次，未过度装饰 |
| 品牌方向 | 9.4 | 量化研究终端气质清晰，信息密度稳定 |
| 信息效率 | 9.6 | 主表、右 rail、analysis band 均可扫视且可切换 |
| 综合 | 9.45 | 五维均值 |

## 验证

- `bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-research.html --out-dir test-results/ditto-design-cycle-gates/research-round1`
  - 结果: PASS
  - VP-STANDARD: `test-results/ditto-design-cycle-gates/research-round1/page-research.html-VP-STANDARD.png`
  - VP-COMPACT: `test-results/ditto-design-cycle-gates/research-round1/page-research.html-VP-COMPACT.png`
- Playwright 交互抽检:
  - `strip/main/activity/analysis` 全部可见
  - legacy tab 条不可见
  - 三区切换通过
  - analysis band 四个 tab 通过
  - 5 个 overlay 打开通过
- R12 底部 tab 几何检查:
  - compact/standard 下 `IC 趋势`、`因子宽度`、`相关性`、`备注` 的可见元素均无 top/bottom/left/right 溢出
  - 截图输出: `test-results/research-bottom-tabs-fixed/`
- `bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-research.html --out-dir test-results/ditto-design-cycle-gates/research-bottom-tabs-fixed`
  - 结果: PASS
- R13 底部 tab 复核:
  - `因子宽度`、`相关性` 在 compact/standard 下 top/bottom/left/right 溢出均为 0
  - 截图输出: `test-results/research-bottom-tabs-r13/`
- `bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-research.html --out-dir test-results/ditto-design-cycle-gates/research-bottom-tabs-r13`
  - 结果: PASS
- R14 相关性矩阵截图:
  - `test-results/correlation-matrix-polish/research-corr-band.png`
- `bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-research.html --out-dir test-results/ditto-design-cycle-gates/research-correlation-polish`
  - 结果: PASS

## 剩余天花板

- 真实排序、筛选、行级跳转仍需 React 实现阶段完成。
- `goal 10` 需要真实数据流、键盘完整路径和动态状态联动后再评估。
