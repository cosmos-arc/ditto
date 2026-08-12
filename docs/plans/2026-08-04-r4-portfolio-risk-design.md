# R4 完整设计：cvxpy 组合优化 + 连续风控 + G3 收口

> **已取代（2026-08-10）**：最终范围、架构与发布门禁以
> [R4 Portfolio / Risk / G3 最终执行计划](2026-08-10-r4-portfolio-risk-g3-execution-plan.md)
> 为准。本文中的静态 allocator 注入、risk 直接依赖 platform、Black–Litterman
> 首发及任何静默 fallback 设计均不得继续实施。

> **日期**：2026-08-04
> **状态**：设计稿（待评审）
> **关联**：[roadmap-status](../reviews/2026-08-04-roadmap-status.md)（R4 = 阶段 II 收尾，冲 G3）、[comprehensive-architecture-audit](../reviews/2026-08-04-comprehensive-architecture-audit.md)（CAP-001/RiskGate 短板）、[boundaries-and-abstraction-standards](../architecture/boundaries-and-abstraction-standards.md)
> **brainstorm 决策**：① 范围=完整 R4 内部分段（R4a→R4b→G3）；② 优化器=MVO+CVaR-opt+风险平价(+BL 可选)+交易成本 L1 罚项；③ 风险模型=收缩协方差(基线)+因子风险模型(解释)；④ 频率边界=EOD+pre-trade+daily-scan 可恢复状态机，intraday 留 R6

---

## 1. 背景与目标

R4 是 roadmap 阶段 II（研究产品化）的收尾，冲 **G3 决策工作台 Beta**。当前短板（benchmark 十维）：⑥组合优化 5.0/10（无真凸求解器，仅对角反方差）、⑦风险管理 5.0/10（规则齐全但无统一运行时/VaR/压力）、⑨AI 0★ 推 R5。

**R4 交付**：
- **R4a 组合优化**：cvxpy 凸家族（MVO/CVaR-opt/风险平价/+BL），复用既有 `CovarianceProvider`/`WeightAllocator`/`Constraint` Protocol，交易成本感知。
- **R4b 连续风控**：统一 `RiskGate` 运行时（pre/EOD/daily-scan + 可恢复状态机）+ VaR/CVaR/ES + 压力测试 + 因子风险。
- **G3 收口**：组合/风险解释 + 账本对账 + 运行手册 + SLO/告警。

**北极星定位**：当下 A 股 ETF + 个股 + 选股，目标全资产 + AI 现代化平台。R4 的 cvxpy + 连续风控是 agentic AI（Phase C/D）能"建议/执行"而非"空谈"的根基（见 [roadmap-status §4](../reviews/2026-08-04-roadmap-status.md)）。

---

## 2. 架构与归属（严守分层）

```
┌─────────────────────────────────────────────────────────────┐
│ apps（G3 工作台 API：风险报告/解释/告警 surface）            │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ application（编排：RiskGate 接 EngineLoop + EOD；风险读模型）│
└────┬──────────────────────┬──────────────────────────┬──────┘
     │                      │                          │
┌────▼───────┐    ┌─────────▼────────┐    ┌────────────▼──────────┐
│ portfolio  │    │ risk             │    │ features（计算平面）  │
│ cvxpy 求解 │    │ RiskGate 运行时   │    │ ShrinkageCovariance   │
│ (新依赖)   │    │ VaR/CVaR/压力    │◄──►│ FactorRiskModel       │
│ CovProvider│◄───│ 因子风险(消费)    │    │ (BARRA 式，PIT 物化)  │
│ 注入       │    │ 状态机/审计      │    │ 复用 attribution/     │
└────────────┘    └──────────────────┘    │ fama_macbeth/因子集   │
                                          └───────────────────────┘
```

**依赖方向（合规）**：
- portfolio → kernel + platform（+ 新增 cvxpy）。不依赖 features；`CovarianceProvider` 由 application 注入（features 产出的协方差）。
- risk → kernel + portfolio（窄依赖，既有）+ platform。因子模型经 Protocol 注入，不直依赖 features。
- features 产出 `ShrinkageCovarianceProvider` + `FactorRiskModel`（计算平面），由 application 注入 portfolio/risk。
- 无新增跨包 forbidden；cvxpy 限 portfolio 内（**不向上泄漏**）。

---

## 3. R4a — cvxpy 组合优化

### 3.1 新依赖
`portfolio/pyproject.toml` 增 `cvxpy >= 1.5`（**已批准 2026-08-04**）。cvxpy 不向 portfolio 之外泄漏（架构测试守）。

### 3.2 求解器（均为 `WeightAllocator` 实现，注入 `CovarianceProvider`）

| 求解器 | 问题 | 用途 |
|--------|------|------|
| `ConstrainedMVOSolver` | `min wᵀΣw` / `max wᵀμ − λwᵀΣw` | 最小方差 / 最大 Sharpe / 收益-风险 |
| `CVaROptimizer` | Rockafellar-Uryasev：`min ζ + (1/(1-α))·max(0, −r+wᵀμ−ζ)` | 尾部风险优化（CVaR 约束/目标） |
| `RiskParityAllocator` | Spinu/Maillard 凸风险平价 | 等风险贡献 / 风险预算 |
| `BlackLittermanPrior`（前置） | 后验 μ = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹[...] | views 融合先验，喂 MVO（可选） |

所有问题：long-only（`w≥0`）+ 全金（`Σw=1`）+ **硬约束烘进 cvxpy** + **交易成本 L1 罚项** `+ λ_tc·‖w−w_prev‖₁`。

### 3.3 约束映射（`ConstraintCvxpyAdapter`）

既有 7 个 dataclass `Constraint` → cvxpy 表达式（烘进问题，非 post-resize）：

| 既有 Constraint | cvxpy 表达式 |
|----------------|--------------|
| MaxWeight | `w ≤ w_max` |
| MinWeight | `w ≥ w_min`（对可投资集） |
| MaxPositions | `card(w) ≤ N` —— 需 MIQP（bool 辅助）或先选 top-N 再 QP |
| IndustryMaxWeight | `Σ_{i∈行业g} w_i ≤ cap_g` |
| Liquidity | `w_i ≤ cap·ADV_i` |
| Tradability | 可投资掩码（`w_i=0` for 不可投资） |
| MaxTurnover | `‖w−w_prev‖₁ ≤ τ_max` |

> MaxPositions 的基数约束是组合优化里唯一的非凸/整数难点；采用"先按得分选 top-N，再在子集上 QP"的两步法保持全凸（业界常见近似），或用 cvxpy MIQP 求解器（ECOS_BB/GLPK_MI）。YAGNI：MVP 用两步法。

### 3.4 协方差来源（features 产出）
`ShrinkageCovarianceProvider`（Ledoit-Wolf 常数相关收缩）：从 PIT returns 估计 Σ_sample，收缩到结构先验，解决大 N（个股选股 universe）下的病态。PIT-aware（knowledge_date 对齐，避免前瞻）。实现 `CovarianceProvider` Protocol，由 application 注入 portfolio。

---

## 4. 因子风险模型（features 产出，R4a+R4b+G3 共用地基）

**BARRA 式多因子风险模型**（复用 features 现有因子集 + `fama_macbeth`）：
```
r_i = Σ_k β_ik·f_k + ε_i
Σ ≈ B·Σ_f·Bᵀ + diag(σ_ε²)
```
- `B`：因子暴露矩阵（features 因子集：style/industry/...）。
- `Σ_f`：因子收益协方差（从因子收益序列估计 + 收缩）。
- `σ_ε²`：个股残差波动。
- 产出 `FactorRiskModel`（frozen dataclass + Protocol），服务：
  - R4b 因子 VaR / 因子压力测试（shock `f_k`）。
  - G3 组合风险解释（风险分解到因子贡献 + 残差）。

**两阶段**：R4a 先用 `ShrinkageCovarianceProvider` 解锁 MVO；因子模型随 R4b 落地（G3 解释依赖它）。

---

## 5. R4b — 连续风控（daily/EOD/pre-trade，可恢复状态机）

### 5.1 统一 RiskGate 运行时 Protocol（risk 包，取代散落 facade）

```python
class RiskGate(Protocol):
    def pre_trade(self, order, snapshot: RiskState) -> RiskDecision: ...    # ACCEPT/REJECT/RESIZE
    def post_trade(self, fills, snapshot: RiskState) -> RiskState: ...       # 更新状态
    def daily_scan(self, snapshot: RiskState) -> DailyRiskReport: ...        # EOD 全量
    def snapshot(self) -> RiskState: ...
    def restore(self, snap: RiskState) -> None: ...                          # 跨重启恢复
    # intraday_check(...) — 预留给 R6，R4 不实现
```
- 现有 6 `PreTradeCheck` + `CompositePreTradeCheck` 成为 `pre_trade` 的实现。
- `post_trade`/`daily_scan` 整合 `post_trade.py` + `drawdown` + `exposure` scan。
- **RiskState**：持久化（positions/realized PnL/drawdown 状态/限额用量），snapshot/restore 跨重启可恢复（durable，复用 platform 存储或新 namespace）。
- **事件审计**：每个 gate 决策落 audit event（谁/何时/Decision/原因）。

### 5.2 VaR/CVaR 引擎（risk 包）

| 方法 | 公式/数据 | 用途 |
|------|----------|------|
| **历史 VaR/CVaR**（主） | 经验 returns 分位数 | 假设最少，主指标 |
| 参数 VaR | `wᵀΣw` 正态 | 需 Σ（收缩协方差） |
| Monte Carlo VaR | 模拟 paths（Σ 或因子模型） | 非线性/因子 |
| **CVaR/ES**（头条） | 尾部条件期望 | 取代 VaR 成头条（业界趋势） |

置信水平/窗口可配（如 99%/20d）。回测 VaR（Kupiec/Christoffersen 检验）纳入 G3 风险报告。

### 5.3 压力测试（risk 包，情景库）
- **历史情景**（A 股本土）：2015 股灾、2024-01 小盘流动性、COVID-2020、2008。
- **假设情景**：利率冲击、行业暴跌、流动性挤兑、单因子崩塌。
- **因子感知**：情景 shock 作用于因子收益 `f_k`（经因子模型），投影组合损失。
- 情景库为可配置 dataclass 集，PIT-aware（历史情景用当时真实 returns）。

### 5.4 频率边界
R4 交付 pre-trade（每单）+ EOD 全量重算 + daily-scan；持久化可恢复状态机。**不做 intraday/实时流**（属 R6，需分钟级数据）。Protocol 预留 `intraday_check` 接口。

---

## 6. G3 收口（决策工作台 Beta）

| G3 要求 | 落地 | 归属 |
|---------|------|------|
| **组合/风险解释** | 风险归因报告（因子分解 + VaR/CVaR 分解 + 压力投影），复用 features `attribution` + 因子风险模型 | application 读模型 + apps API |
| **账本对账** | execution 既有 `reconciliation/executor.py` 接入 EOD：持仓 vs broker vs RiskState 三方对账 | application 编排 |
| **运行手册** | `docs/operations/risk-runbook.md`：风险事件处置（kill switch/回撤 breach/压力失败）的 SOP | docs |
| **SLO/告警** | platform `AlertManager`（既有）接风险事件（回撤 breach/VaR 限额/压力失败）→ 告警；EOD VaR 计算延迟 SLO | platform + application |

---

## 7. 分段与门禁

| 段 | 内容 | 独立价值 | 门禁贡献 |
|----|------|---------|---------|
| **R4a** | cvxpy 求解器 + 收缩协方差 + 约束映射 | 更优组合（CAP-001 闭环） | — |
| **R4b** | RiskGate 运行时 + VaR/CVaR + 压力 + 因子风险 | 真实风险能力 | — |
| **G3** | 解释 + 对账 + 运行手册 + SLO/告警 | 决策工作台 Beta | **G3 PASS** |

每段独立可交付；R4a 不阻塞 R4b（R4b 可先用历史 VaR 不需 cvxpy）。R4 完成后进入 R5（AI Phase B-D 依赖 R4 的组合/风险写入靶点）。

---

## 8. 测试策略

| 层 | 策略 |
|----|------|
| cvxpy 求解器 | 已知解单元测试（2 资产解析解、3 资产数值对照）+ 约束满足断言（每约束一测）+ 与 EqualWeight A/B 回测 |
| 协方差/因子模型 | PIT 对齐断言 + 收缩正定性 + 因子回归残差无显著性 |
| RiskGate | 状态机转换全路径 + snapshot/restore 往返一致 + pre/post/daily_scan 覆盖 |
| VaR/CVaR | 三法交叉对照（历史 vs 参数 vs MC 在正态下应收敛）+ Kupiec 回测 |
| 压力测试 | 历史情景复现已知回撤 + 假设情景线性叠加校验 |
| 集成 | EngineLoop 接 RiskGate 全链路 golden（回测跑通，风控事件可重放） |
| 架构 | cvxpy 不泄漏出 portfolio（新 forbidden 契约）；risk 不直依赖 features（Protocol 注入） |

---

## 9. 风险与开放问题

| 风险/问题 | 缓解/待决 |
|----------|----------|
| cvxpy 求解器性能（大 universe） | 两步法 MaxPositions；ECOS/CLARABEL 默认，大问题可配求解器；个股 universe 用因子模型降维 |
| 收缩协方差窗口选择 | 可配 lookback（如 250 日），PIT 物化；窗口敏感性纳入风险报告 |
| MaxPositions 基数非凸 | MVP 两步法（先 top-N 再 QP）；MIQP 留后续 |
| VaR 模型风险（历史法尾部分布） | 三法交叉 + Kupiec 回测 + CVaR 头条（CVaR 对尾部更稳健） |
| ~~cvxpy 新依赖~~ | ✅ 已批准（限 portfolio，2026-08-04） |
| ~~RiskState 存储位置~~ | ✅ **risk 自有 SQLite**（经 platform `SQLitePool` 基建，独立路径 `<data_root>/risk/risk_state.sqlite`），仿 analysis `research.sqlite` 隔离范式；不塞 `data.metadata`、非泛化 namespace；durable/可恢复/审计 append-friendly |

---

## 10. 相关文档

- 路线图状态：`docs/reviews/2026-08-04-roadmap-status.md`
- 全量审计：`docs/reviews/2026-08-04-comprehensive-architecture-audit.md`（§2.6 portfolio、§2.7 risk）
- 当前 R5 设计：`docs/plans/2026-08-12-r5-governed-quant-research-agent-design.md`（R4 是 R5 evidence 与 shadow decision 的确定性宿主）
- 边界标准：`docs/architecture/boundaries-and-abstraction-standards.md`
