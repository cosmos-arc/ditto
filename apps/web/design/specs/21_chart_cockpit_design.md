# Chart Cockpit 图表工作台设计

> **设计日期**: 2026-09-17
> **关联 Spec**: 00_ditto_visual_constitution.md, 04_interaction_state_spec.md, 12_ditto_data_views_spec.md, 15_ditto_token_stabilization_spec.md, 19_ditto_shell_chrome_contract.md, 20_interaction_ux_audit.md
> **状态**: 定稿（Brief v1 + v2 合并；实施规格见 GitHub issue cosmos-arc/ditto#208，切片 #209–#215）
> **承接**: 原型→React 遗留 Epic「Chart Cockpit」的产品化

---

## 一、设计目标与原则

1. **图表是第一生产力界面**：系统已计算出的每个关键数字（净值、IC、分位、偏差）都必须有对应的可视化，不再以文本行呈现。
2. **诚实性优先**：图表与表格同源同语义；数据缺失渲染为断口（不插值、不补零）；PIT 语义显式可见（as_of 水位线）；无任何装饰性假数据。
3. **一套基础件，三个场景**：Chart Cockpit 组件族同时服务标的页 / 回测页 / 研究页，指标叠加、十字线、缩放行为全局一致。
4. **专业密度**：默认 dense 档，图表区最大化、chrome 最小化；键盘可达（方向键平移、+/- 缩放、Home/End 跳首尾，容器可聚焦有焦点环）。

## 二、基础件规范

- **引擎**：lightweight-charts 5.x 承担全部时序图（K 线/成交量/净值/叠加曲线/markers/水下曲线）；recharts 仅保留给非时序统计图（分位 bar、月度热力图）。不引入第三库。
- **跨 pane 联动**：主图+副图共享时间轴，十字线与 tooltip 同步；区间框选缩放，双击回全区间。
- **as_of 水位线（本产品特有）**：图表右缘显示 knowledge cutoff 竖线 + stale 徽标；与数据新鲜度透明度时变（live 1.0 → recent 0.85 → aging 0.65 → stale 0.40 → expired 0.25）合并为同一新鲜度体系，不另造第二套。
- **状态语义**：loading（带坐标轴占位骨架）/ empty（引导入口）/ error（重试）/ stale（水位线+badge）/ partial（区间缺失渲染断口，标注缺口范围）映射进 04 号 spec 的 15 状态语义与页面合同 requiredStates。
- **导出**：PNG（footer 溯源五字段：as_of、source snapshot id 截断、数据源名、导出时间、产品版本）+ CSV（同名列附带）。

## 三、视觉令牌

在设计 token 体系新增 `chart.*` 语义层（OKLCH only）：

- 涨跌遵循 A 股心智：默认红涨绿跌，属 Market 业务语义域、禁跨域复用；国际配色切换入口在 **View Preferences**（全局偏好层，不放图表控制条），全局即时生效（对齐 15 号 spec §5）。
- 三组合固定专属色（Model/Paper/Manual，与域签名色体系对齐）；多 run 叠加用 8 色顺序色板 + 图例开关。
- Q1–Q5 分位用单色渐进色带，LS 用对比强调色；双主题 WCAG AA（复用既有对比度审计脚本）。
- Light Mode 图表色板随本设计一并迁入产品 token 层（20 号审计遗留项）。

## 四、页面设计

### 标的页图表 tab（M1）

K 线主图 + 成交量副图；指标叠加首期 MA(5/20/60)、BOLL、MACD、RSI、ATR（取自技术分析 registry 既有 18 指标，无新指标实现），可多开副图；控制条含周期切换（日/周/月）与复权切换（原始/前复权/后复权，复权价一律本地自算结果）；ETF 特化叠加净值线（数据可得时，不可得时显式降级提示）；指标选择页面级持久化。

### 回测详情页（M2）

净值 vs 基准叠加（数据已在，补画）+ 超额收益副图 + 回撤水下曲线与主图区间底色；**买卖点下钻链**：报告/图表成交 → 审计证据抽屉 → 跳转标的 K 线定位到该日并高亮该笔——作为 D9「证据链签名」的第一个完整交互示范，跳转携带对象、原因、知识时间。多 run 对比：净值多色叠加 + 图例开关 + 指标差异表。

### 研究图表（M3）

因子详情：IC 时序 + 滚动 IR 双轴、Q1–Q5 分位分层净值、LS spread、月度 IC 热力图；组合对比页：三组合净值曲线 + 差异可视化（数据来自既有 comparison query，零新后端语义）。

## 五、数值纪律与 Primary Answer

图表页仍受 5 秒原则约束（主图 + 一句话判断 + 关键数字）；轴/十字线读数/图例数字遵守 12 号 spec 数值六纪律（tabular-nums、精度统一、正负号、时间格式），与表格同口径。

## 六、实施分期与验收

| 期 | 内容 | 切片票 |
| --- | --- | --- |
| M1 | 基础件 + 标的页 K 线（含 token 落地）→ 指标与 ETF 叠加 | #209 → #210 → #211 |
| M2 | 回测页叠加/水下曲线 → 买卖点下钻链 | #212 → #213（依赖 #210） |
| M3 | 因子图表 + 三组合对比 + 多 run 对比 | #214、#215 |

验收硬门：`reactParityVerified`；测试接缝全部复用既有三层（tests/system E2E 最高缝、feature 组件 vitest、页面合同校验），只断言外部行为；每期独立可验收、独立合并。

## 七、裁决记录（2026-09-17，默认裁决可推翻）

1. 红涨绿跌确认 + 切换入口在 View Preferences。
2. 指标首期 6 个确认（MA/BOLL/MACD/RSI/ATR + 量）。
3. 回测下钻流确认（报告→证据→K 线定位高亮）。
4. PNG footer 溯源五字段确认。
