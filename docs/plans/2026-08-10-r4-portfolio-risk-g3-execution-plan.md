# R4 Portfolio / Risk / G3 最终执行计划

> 日期：2026-08-10
> 状态：执行基线
> 取代：`2026-08-04-r4-portfolio-risk-design.md`、
> `2026-08-04-r4a-cvxpy-portfolio-optimization-plan.md`

## 最终范围

R4 首发 MVO、Historical CVaR 与风险平价；Black–Litterman 延后至 R4.1。
优化器是策略候选组合之后、订单规划之前的独立 portfolio-construction 步骤。
未绑定 policy 的 strategy/sleeve 保持 legacy 行为；绑定后的 shadow/enforced 模式
均记录版本、digest、solver、输入快照与约束证据。任一模式的优化或证据失败均禁止
发布或回退；shadow 仅在优化成功后保留候选权重用于对照。

实盘、模拟盘和 EOD fail closed。回测把失败保存为结构化 artifact，不采用等权或
旧优化器替代。Daily Decision V2 保持原契约，V3 新增组合构造、VaR/ES、因子风险、
压力测试、对账、阻断原因与 provenance。

## 架构边界

- `features`：无 I/O 的 PIT 收益矩阵、收缩协方差与股票因子风险估计。
- `portfolio`：policy/request/result/optimizer 公共契约；CVXPY 与 solver 细节不泄漏。
- `risk`：连续 RiskGate、尾部风险、压力场景及纯状态规则。
- `backtest`：自有可注入 construction/risk ports、失败 artifact、V3 checkpoint。
- `application`：PIT 输入编排、EOD/backtest adapters、持久化 ports、对账与 V3 查询。
- `apps.registry.infra`：SQLite append-only 事件、CAS 快照、日报适配器与唯一装配点。

上述方向由 `.importlinter` 验证。当前处于开发阶段，metadata 初始化流程直接、幂等
创建 R4 SQLite 表，不生成数据迁移脚本；真实生产数据写入仍不属于本次代码交付。

## 数值与风险合同

- 默认 lookback 250 个交易日，至少 60 个完整观测；decision time、knowledge
  cutoff、publication cutoff、source snapshot 缺一即拒绝。
- MVO 固定 OSQP；Historical CVaR 与风险平价固定 CLARABEL；仅 `OPTIMAL` 可发布。
- CVaR 默认 ES99、单日损失、10 bps L1 换手惩罚；风险平价必须通过风险贡献对账。
- 容量上限 500；过滤与稳定 MaxPositions 在求解前完成，MinWeight 使用确定性
  active-set 重求解；所有约束以 `1e-6` 统一复验。
- 非有限输入、证据不足、timeout、不可行、不可修复非 PSD、贡献误差超限均返回
  结构化失败。
- headline 风险为正损失口径 Historical ES99，并报告 Historical VaR99、参数 VaR、
  固定 seed Monte Carlo；必须满足 ES ≥ VaR。

## 执行波次与退出门

1. PR0：`osx-arm64` Pixi 平台、CVXPY 依赖、`macos-15` ARM64 required CI、
   OSQP/CLARABEL smoke；Linux 保留完整 `ci`。
2. PR1：PIT 风险输入与三类优化器；数值、约束、失败和未来哨兵测试通过。
3. PR2：EOD、研究、paper 与 backtest 垂直链路；legacy、shadow、enforced 可区分。
4. PR3：连续 RiskGate、幂等成交、CAS 状态、V3 checkpoint 与恢复等价。
5. PR4：ES/VaR、版本化压力目录、股票六风格+行业因子分解、ETF partial/unavailable。
6. PR5：三层 EOD 对账、V3 驾驶舱、幂等告警、指标与运行手册。

每波运行目标测试与 changed-scope 门禁。高风险合并前运行 `pytest -m pit`、
`arch-check`、`check`；最终运行 `ci` 与 `git diff --check`。Linux 与 macOS ARM64
required CI 均为发布条件。

## SLO 与发布策略

- 50/200/500 标的固定基准；500 标的优化 p95 ≤ 5 秒。
- 纯内存盘前 RiskGate p95 ≤ 50 ms。
- 单账户 EOD 风险与对账 p95 ≤ 60 秒；V3 查询 p95 ≤ 2 秒。
- readiness blocked、报告过期、状态恢复失败、VaR/ES 越限或任一对账差异均告警并
  阻止下一次建议。
- shadow 数据满足确定性、约束、PIT 与 SLO 后，只按 strategy/sleeve 逐一切换
  enforced，禁止全局自动迁移。

## 不纳入 R4

Black–Litterman、MIQP/整数手数优化、ETF 持仓穿透因子、自动对账修复、真实券商
操作、生产数据迁移及 `ditto-app` 前端改造。
