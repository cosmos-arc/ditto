# 阶段 A：日级人工交易闭环深化 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把日级 A 股人工交易主线从「能跑」做成「好用、可信、全品类」，综合功能完整度 2.9★ → 3.5★，达成里程碑①「可商用的日级 A 股全品类人工交易平台」。

**Architecture:** 六个工作项分四批推进。小修与撮合补全走纯 TDD；组合优化与风控连续性因涉及新依赖（cvxpy）与状态机重构，先做 mini-design 再原子化；数据 promotion 复用已有治理 CLI 走运营流程；前端在 ditto-app 仓库独立推进。

**Tech Stack:** polars / numpy / cvxpy(新增) / sqlite / FastAPI / Typer / pytest / basedpyright / ruff / pixi

**背景文档:** `docs/plans/2026-07-10-capability-benchmark-design.md`（能力评级与路线图）

---

## 探索修正（写计划前的关键发现，避免返工）

| 项 | 原认知 | 代码实证 | 对计划的影响 |
|---|---|---|---|
| A2 涨跌停 | 「缺」 | `AShareFillModel`（`simulation/fill.py:123-204`）**已完整实现**涨跌停规则矩阵（`limit_up_no_buy`/`limit_down_no_sell`/停牌/收盘竞价） | A2 缩减为**仅手数取整**，工作量 ↓↓ |
| A2 手数字段 | 未知 | `DEFAULT_LOT_SIZE=100`（`kernel/trading.py:34`）+ `TradingRuleSet.lot_size`（`trading.py:79`）已存在 | A2 = 在订单规整化点补 round-down 逻辑 |
| A3 均值方差 | 「有框架」 | `MeanVarianceAllocator` 注释明说「deliberately avoids a solver dependency」——是反方差+water filling 的**伪均值方差**（只用对角协方差） | A3 = 引 cvxpy 做**真**优化，工作量 ↑ |
| A6-2 策略定义 | 「小修」 | application/apps **无任何** `strategy_definition`/`register_strategy`；CLI 无 `publish-strategy-definition`；定义存于 `SEED_STRATEGY_SPECS`（`strategy/alpha/seeds.py:161`）+ catalog 查询契约 | A6-2 = **新建** publish 流程 |
| A4 风控状态 | 「全缺」 | `DrawdownStateSnapshot`+`restore`（`drawdown/rules.py:72`）已有状态快照起点 | A4 = 统一状态/审计/恢复，drawdown 可复用 |

---

## 执行策略

### 四批推进（依赖 + 并行）

```
第 0 批（即日，无依赖，解锁 Wave1a 残留）
  └─ A6-1 wave1_env TUSHARE_TOKEN export

第 1 批（并行，独立）
  ├─ A2  手数取整（涨跌停已有）
  ├─ A1  数据 promotion（stock/macro/fx/commodity，运营+治理）
  └─ A6-2 策略定义 publish 流程（新建）

第 2 批（需 mini-design 先行，可并行）
  ├─ A3  cvxpy 组合优化（真均值方差/风险平价/有效前沿）
  └─ A4  风控连续性（状态机+审计持久化+恢复）

第 3 批（依赖 A1-A4 API 稳定，跨仓库）
  └─ A5  ditto-app trading 域 production
```

### 工作量估算（单人）

| 批 | Task | 估算 |
|---|---|---|
| 0 | A6-1 | 0.5 天 |
| 1 | A2 / A1 / A6-2 | 1-2 / 3-5 / 2-3 天 |
| 2 | A3 / A4 | 5-8 / 5-8 天（含 mini-design） |
| 3 | A5 | 5-10 天（跨仓库） |
| | **合计** | **~3-5 周** |

### 里程碑①验收标准（阶段 A 完成）

- [ ] A1：stock/macro/fx/commodity 至少 stock + macro 经 promotion 闭环提级 initial-focus（`ditto ops status --json` 无 experimental warning for these）
- [ ] A2：回测买入量规整到 `lot_size` 倍数，golden e2e 含手数场景
- [ ] A3：`cvxpy` 入 pixi.toml；风险平价 + 带约束均值方差 allocator 可用，单测 + 回测验证
- [ ] A4：`RiskGate` 连续状态快照/恢复 + typed audit 持久化（sqlite）+ 崩溃恢复 e2e
- [ ] A5：ditto-app `/trading` 决策 banner/信号详情/下单 intent/组合归因 tab 全 live 可用
- [ ] A6-1/A6-2：`source scripts/acceptance/wave1_env.sh` 后 server 启动无 `data_source_validation` 失败；`publish-signals <strategy_id>` 不再报「未找到策略定义」
- [ ] `pixi run -e dev check` 全绿（lint+fmt+type+test --fast）+ 37 架构合约全绿

---

## Task 详细拆解

### A6-1：wave1_env.sh 补 TUSHARE_TOKEN export（第 0 批，完整 TDD）

**背景：** Wave1a smoke 发现 server 启动 `data_source_validation` 失败，因 `wave1_env.sh` 未导出 `TUSHARE_TOKEN`（CLI 用 keyring 不受影响，server 启动校验需要环境变量）。

**Files:**
- Modify: `scripts/acceptance/wave1_env.sh:28-32`

**Step 1: 写失败测试**

创建 `scripts/acceptance/test_wave1_env_unit.sh`（或并入现有 acceptance 测试）：
```bash
#!/usrovy/env bash
# 验证 wave1_env.sh 导出 TUSHARE_TOKEN（当外部已设置时透传）
set -euo pipefail
export TUSHARE_TOKEN="test_token_xyz"
source "$(dirname "$0")/wave1_env.sh" .tmp/test-rc1
test "${TUSHARE_TOKEN:-}" = "test_token_xyz" || { echo "FAIL: TUSHARE_TOKEN not preserved"; exit 1; }
echo "PASS"
```

**Step 2: 验证失败** — 运行测试，预期 FAIL（当前脚本不处理 TUSHARE_TOKEN 透传虽默认保留，但需显式文档化 + FRED_API_KEY 同理）。

**Step 3: 最小实现** — 在 `wave1_env.sh` 的 export 块（line 28-32 后）追加注释 + 显式透传（bash source 默认保留外部 env，这里补文档 + 确保 keyring 回退提示）：
```bash
# 数据源凭证透传：CLI 走 keyring，server 启动校验需要环境变量。
# 若未设置，提示从 keyring 读取（不硬编码 token）。
: "${TUSHARE_TOKEN:=$(python -c "import keyring; print(keyring.get_password('tushare','token') or '')" 2>/dev/null || true)}"
: "${FRED_API_KEY:=$(python -c "import keyring; print(keyring.get_password('fred','api_key') or '')" 2>/dev/null || true)}"
export TUSHARE_TOKEN FRED_API_KEY
```

**Step 4: 验证通过** — `source scripts/acceptance/wave1_env.sh` 后 `echo $TUSHARE_TOKEN` 非空（本机 keyring 有 token 时）；无 token 时为空字符串不报错。

**Step 5: smoke 验证** — `source scripts/acceptance/wave1_env.sh && pixi run -e dev server`（或启动命令）不再 `data_source_validation` 失败。

**Step 6: Commit**
```bash
git add scripts/acceptance/wave1_env.sh
git commit -m "fix(acceptance): wave1_env export TUSHARE_TOKEN/FRED_API_KEY with keyring fallback"
```

---

### A2：手数取整（第 1 批，完整 TDD）

**背景：** 涨跌停/停牌/收盘竞价已由 `AShareFillModel` 完整实现。A 股买入量须为 `lot_size`（默认 100）倍数，当前订单规整化缺失。

**Files:**
- Modify: 订单规整化点（探索确认：`packages/backtest/src/ditto_backtest/steps/planning.py` 或 `execution.py`，订单从 target weight → quantity 处）
- Test: `packages/backtest/tests/unit/test_board_lot_unit.py`（新建）

**Step 1: 写失败测试**
```python
# test_board_lot_unit.py
import polars as pl
from ditto_backtest.steps.planning import _round_to_board_lot  # 探索确认实际模块/函数

def test_buy_quantity_rounds_down_to_lot_size():
    # 资金 15000, 价格 12.5 → 1200 股 (100 的倍数), 非 1200.x
    qty = _round_to_board_lot(target_value=15000.0, price=12.5, lot_size=100, side="buy")
    assert qty % 100 == 0
    assert qty == 1200

def test_sell_allows_odd_shares_to_clear_position():
    # 卖出允许零股（清持仓），不强制取整
    qty = _round_to_board_lot(target_value=1500.0, price=12.5, lot_size=100, side="sell", available=153)
    assert qty == 153  # 清仓允许零股

def test_below_one_lot_buy_returns_zero():
    qty = _round_to_board_lot(target_value=500.0, price=12.5, lot_size=100, side="buy")
    assert qty == 0  # 不足 1 手不买
```

**Step 2: 验证失败** — `pytest packages/backtest/tests/unit/test_board_lot_unit.py -v` → FAIL（`_round_to_board_lot` 未定义）。

**Step 3: 探索 + 最小实现** — 先 `Read planning.py`/`execution.py` 确认 target_weight→quantity 的规整化点，在该点引入 `_round_to_board_lot`：买入向下取整到 `lot_size`，卖出允许零股清仓，不足 1 手买入返回 0。

**Step 4: 验证通过** — 单测 PASS。

**Step 5: golden e2e** — 在 `packages/apps/tests/integration/test_golden_e2e.py` 增加手数场景断言（或新建 fixture），验证全链路买入量为 100 倍数。`pixi run -e dev test --integration -q`。

**Step 6: Commit**
```bash
git add packages/backtest/src/ditto_backtest/steps/planning.py packages/backtest/tests/unit/test_board_lot_unit.py
git commit -m "feat(backtest): A-share board lot round-down for buy orders"
```

---

### A6-2：策略定义 publish 流程（第 1 批，task 级 + 探索点）

**背景：** `publish-signals <strategy_id>` 报 `AppBuilderError: 未找到策略定义`。定义存于 `SEED_STRATEGY_SPECS`（内置）+ catalog 查询契约（`strategy/contracts.py:35`）+ `StrategySpecRecord`。需建 publish 流程让 strategy_id 能被解析。

**Files（探索后定）:**
- Explore: `packages/apps/src/ditto_apps/cli/commands/strategy.py:100-140`（`_build_run_config` 如何解析 strategy_id）
- Explore: `packages/strategy/src/ditto_strategy/contracts.py`（catalog 查询契约）+ `alpha/seeds.py`（SEED_STRATEGY_SPECS）
- Modify/Create: `packages/application/src/ditto_application/...`（strategy definition 注册/publish command handler）
- Modify: `packages/apps/src/ditto_apps/cli/commands/strategy.py`（新增 `publish-strategy-definition` 命令，或修正 publish-signals 的 strategy_id 解析）

**Task 级拆解：**
1. **探索** — `Read strategy.py` 的 `_build_run_config` + `_build_run_config` 调用链，定位「未找到策略定义」的确切抛错点与期望数据源（SEED vs catalog 持久化）。
2. **设计决策** — 策略定义 publish 是：(a) 把 SEED_STRATEGY_SPECS 注册到 catalog 持久化（StrategySpecRecord 写入），还是 (b) publish-signals 直接接受 SEED strategy_id（内置免注册）。倾向 (a)：显式 publish 让 strategy_id 进入 catalog，支持后续自定义策略。
3. **TDD** — 写 `test_publish_strategy_definition_unit.py`：publish 一个 SEED strategy_id → catalog 查询返回 StrategySpecRecord → publish-signals 不再报错。
4. **实现** — application 层 publish handler（写 StrategySpecRecord 到 catalog）+ CLI `publish-strategy-definition` 命令。
5. **smoke** — `ditto ops publish-strategy-definition etf_rotation && ditto ops publish-signals etf_rotation --trade-date <date>` 全绿。

**Commit:** `feat(application): strategy definition publish flow to catalog`

> ⚠️ 此 task 启动前需先 `Read` 完整调用链确认设计决策 (a)/(b)，可能需 mini-design。

---

### A1：数据 promotion（第 1 批，运营 + 治理流程）

**背景：** `ditto ops promotion-collect/review/revoke` 治理闭环已完备（绝不自造通过）。stock/macro/fx/commodity 当前 experimental，需收集真实 evidence 提级。

**流程（非纯代码，运营驱动）：**

| 数据集 | 现状 | 提级路径 |
|---|---|---|
| stock（个股行情/元数据） | experimental | `promotion-collect` 收 3 条 criteria evidence → `promotion-review` ×3 → 自动 assess 提级 |
| macro（FRED realtime PIT 已就绪） | experimental | 同上（PIT evidence 已强） |
| fx / commodity | experimental | 同上（优先级低于 stock/macro，可后置） |

**代码工作（如有）：**
- 若 evidence criteria 对某些数据集不满足，补 `PromotionEvidenceCollector` 的 criteria 收集逻辑（参考 F2-#1 模式）
- golden governance 闭环测试覆盖新提级数据集

**验收：** `ditto ops status --json` 对 stock/macro 无 experimental warning（或显式 `allow_experimental_data` 不再必需）。

**Commit（分数据集）:** `docs(promotion): record stock/macro promotion evidence + maturity override`

> 注：memory 记录 backfill 写瓶颈（SQLite 写锁，全年不可行→近期 2 月）。promotion evidence 收集用近期数据即可，不需全年 backfill。

---

### A3：cvxpy 组合优化（第 2 批，需 mini-design）

**背景：** 当前 `MeanVarianceAllocator` 是反方差+water filling 伪实现（无 solver）。引 `cvxpy` 做真优化。

**⚠️ 前置：mini-design**（先写 `docs/plans/2026-07-10-a3-portfolio-optimizer-design.md`）
- 依赖变更：`pixi.toml` 加 `cvxpy`；`packages/portfolio/CLAUDE.md` 外部依赖 polars → polars+numpy+cvxpy（**架构边界：cvxpy 仅 portfolio 包用，禁止向上泄漏**）
- portfolio 包当前**禁止依赖 data/execution/risk**——协方差矩阵/预期收益须由调用方（application/backtest）注入为 Protocol，optimizer 只接收 frame + provider
- 约束模型：max_weight / 行业上限 / 个股权重上限 / 换手约束 / cash_target

**Files:**
- Modify: `packages/portfolio/src/ditto_portfolio/rebalancing/optimization.py`（新增 `RiskParityAllocator`、`ConstrainedMeanVarianceAllocator`、`EfficientFrontierScanner`）
- Modify: `packages/portfolio/CLAUDE.md`（外部依赖声明）
- Modify: `pixi.toml`（cvxpy 依赖）
- Test: `packages/portfolio/tests/unit/rebalancing/test_optimization_unit.py`（扩展）

**Task 级拆解（mini-design 后原子化）：**
1. mini-design 文档 + 依赖变更（pixi.toml + CLAUDE.md）→ `pixi install` 验证
2. TDD `RiskParityAllocator`（等风险贡献，cvxpy 求解）→ 单测（权重 × 协方差行和相等）
3. TDD `ConstrainedMeanVarianceAllocator`（max variance 或 max sharpe，带约束）→ 单测（约束满足 + 权重和=1）
4. TDD `EfficientFrontierScanner`（扫描风险/收益点）→ 单测（前沿单调）
5. application 层 DI 注入新 allocator（`providers_portfolio.py`）→ 回测 e2e 验证
6. 架构检查：`pixi run -e dev arch-check`（cvxpy 不泄漏到其他包）

**Commit（分 task）:** `feat(portfolio): risk parity allocator (cvxpy)` / `...constrained mean-variance...` / `...efficient frontier...`

---

### A4：风控连续性（第 2 批，需 mini-design）

**背景：** 规则齐全（集中度/最大回撤/单笔止损/市场异常/kill_switch）+ `RiskGate` Protocol。`DrawdownStateSnapshot`+`restore` 是状态起点。缺统一连续状态机 + typed audit 持久化 + 崩溃恢复。

**⚠️ 前置：mini-design**（先写 `docs/plans/2026-07-10-a4-risk-continuity-design.md`）
- 统一 `RiskGateStateSnapshot`（聚合 drawdown/exposure/各规则状态）
- typed audit payload（`RiskAuditEvent` → sqlite，复用 execution audit 模式）
- 崩溃恢复（回测 checkpoint + paper runtime 崩溃后从 snapshot 恢复）
- 与 OMS 对账层打通（risk event 进 execution operating timeline）

**Files:**
- Modify: `packages/risk/src/ditto_risk/contracts.py`（`RiskGate` 扩展 state_snapshot/restore）
- Create: `packages/risk/src/ditto_risk/state.py`（统一状态聚合）+ `audit.py`（typed audit）
- Modify: `packages/backtest/src/ditto_backtest/steps/risk_scan.py` + `pre_trade.py`（消费连续状态）
- Test: `packages/risk/tests/unit/test_risk_state_unit.py` + `test_risk_audit_unit.py`；`packages/backtest/tests/integration/test_risk_integration.py`（崩溃恢复 e2e）

**Task 级拆解（mini-design 后原子化）：**
1. mini-design + `RiskGateStateSnapshot` 聚合模型（复用 DrawdownStateSnapshot 模式）
2. TDD 各规则 state_snapshot/restore 一致性 → 单测
3. TDD typed `RiskAuditEvent` + sqlite 持久化 → 单测（参考 execution audit sink）
4. TDD 崩溃恢复（回测 checkpoint 含 risk state，resume 后风控状态连续）→ integration e2e
5. paper runtime 接入（`paper_trading_process.py`）
6. 架构检查 + 文档

**Commit（分 task）:** `feat(risk): unified RiskGateStateSnapshot` / `...typed risk audit (sqlite)...` / `...crash recovery e2e`

---

### A5：ditto-app trading 域 production（第 3 批，跨仓库）

**背景：** Wave1a 已 live smoke 接线（`feat/wave1-backend-wiring` 分支，`docs/acceptance/wave1a-trading-live.png`）。需从「接线验证」做到「production 可用」。

**仓库：** `/home/chevy/projects/ditto-app`（独立 git repo，独立分支）

**Task 级拆解（参考 `docs/plans/2026-07-02-wave1-frontend-wiring-design.md`）：**
1. 决策 banner（daily-decision 信号展示）production 化
2. 信号详情面板（SignalDetailPanel AI Review）
3. 下单 intent 流（Signal-to-Order Pipeline Strip，依赖 A6-2 策略定义 publish）
4. 组合归因 tab（comparison，依赖 A3 组合优化）
5. riskCheck deviation 第 5 项展示（依赖 A4 风控）
6. 降级空态 + 错误边界 production 化
7. e2e（playwright）+ vitest 全绿

> ⚠️ A5 强依赖 A6-2（策略定义）、A3（组合归因）、A4（riskCheck）。须在第 2 批完成后启动。

**Commit:** 在 ditto-app 仓库 `feat/wave1-backend-wiring` 分支提交。

---

## 风险与前置确认

| 风险 | 缓解 |
|---|---|
| A3 cvxpy 依赖可能拖慢 CI/安装 | mini-design 评估 cvxpy 安装成本；备选 scipy.optimize（项目允许 httpx 等但未列 scipy，需确认）|
| A3/A4 mini-design 延期 | 第 1 批（A2/A1/A6）不阻塞，可先行出价值 |
| A1 数据 promotion evidence 需真实数据 | 近期 2 月数据（避开 backfill 写瓶颈），用 `ingest` 非 `backfill` |
| A6-2 设计决策 (a)/(b) 未定 | task 启动时先 Read 调用链确认，必要时 mini-design |
| A5 跨仓库协调 | 等 A1-A4 API 稳定后启动，避免前端反复适配 |

## 验证（每 task 完成前）

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 架构合约（cvxpy 不泄漏 / risk-audit 边界）
```

阶段 A 全部完成：`pixi run -e dev ci`（完整 CI）+ 里程碑①验收清单全绿。
