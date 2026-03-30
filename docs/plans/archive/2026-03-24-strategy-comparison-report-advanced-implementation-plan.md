# Strategy Comparison Report Advanced Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前基础版 `StrategyComparisonReport` 从“两个回测报告的 delta 函数”升级为“带统计检验、结构化解释、artifact 落盘与控制面语义”的完整比较能力。

**Architecture:** 保持 Core 中的比较逻辑纯函数化，但拆分为三层：基础指标对比、统计检验分析、结构化结论生成。Port 层新增 comparison orchestration，负责从 run/report/artifact 组织输入、调用 Core 分析并持久化 comparison artifact。DataHub 先复用现有 artifact 存储体系，不强制首版引入新 comparison 表。

**Tech Stack:** Python 3.13, dataclasses, polars, orjson, pytest, sqlite, basedpyright

---

## 1. 问题说明

### 1.1 当前实现到底做到了什么

当前 `portfolio/comparison.py` 已经具备一个干净可用的基础版比较器：

- 输入两个 `BacktestReportView`
- 计算指标差值 `MetricsDelta`
- 按高优/低优方向给出 `improved` / `degraded`

见 [comparison.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/portfolio/comparison.py)。

这是一个合格的 Core pure function，但它仍然只是“差值比较器”，还不是“策略实验对比系统”。

### 1.2 当前缺口

根据 v3 设计稿与当前实现对照，缺口至少有四类：

1. **没有统计显著性**
   - 当前只能说 delta 是正还是负
   - 不能回答“收益提升是否显著，还是只是样本噪音”

2. **没有结构化解释**
   - 当前 `improved=("annualized_return", "sharpe_ratio")`
   - 但不能回答“改善主要来自哪一段时间、是否以更高换手/更高回撤为代价”

3. **没有 artifact 闭环**
   - 当前 `compare_reports()` 只返回内存对象
   - 没有 `comparison_report.json`、滚动对比数据、returns spread 等可落盘产物

4. **没有控制面语义**
   - `baseline_run_id` 只是模型字段
   - Port / DataHub 没有“以 run_id 对 run_id 形成 comparison”这一层编排

### 1.3 为什么这不是“多加几个字段”就够

如果只在当前 dataclass 上继续堆字段，会产生三个问题：

- Core pure function 会被迫承担 artifact / persistence 责任
- 显著性检验会需要时间序列输入，但现有 `BacktestReportView` 只暴露了少量聚合字段
- 解释逻辑会和 delta 逻辑缠在一起，难以演进和测试

所以应当把“比较”拆成明确的分析层次，而不是继续在 `compare_reports()` 中线性堆功能。

---

## 2. 目标与非目标

### 2.1 目标

1. 保留当前 `compare_reports()` 的纯函数优点
2. 为 comparison 引入统计显著性结果
3. 形成可机器消费、可 UI 展示、可 artifact 落盘的结构化报告
4. 建立 `baseline_run_id / compare_run_id` 的产品化语义

### 2.2 非目标

- 本轮不规划 API / job flow 入口
- 本轮不做 LLM 自动生成自然语言评论
- 本轮不追求完整研究平台级 attribution 系统

---

## 3. 方案比较

### 方案 A：继续扩展 `compare_reports()`

**优点**
- 改动集中
- 接口简单

**缺点**
- Core 函数会同时承担 delta、统计、解释、artifact 前置结构
- 测试边界混乱

**结论**
- 不推荐

### 方案 B：只做 artifact 化，不做统计检验

**优点**
- 交付快
- 很容易接 DataHub artifact store

**缺点**
- 依旧无法区分“真实改善”和“噪音改善”
- 与 v3 设计目标仍有明显差距

**结论**
- 只能作为临时补丁

### 方案 C：**推荐**，分层比较体系

三层职责：

1. **Core 基础对比层**
   - 指标矩阵、delta、direction

2. **Core 分析层**
   - 统计检验、rolling diff、findings

3. **Port orchestration 层**
   - run/report 组装、artifact 落盘、control-plane 关联

**结论**
- 最适合长期演进，也与当前架构边界一致

---

## 4. 推荐设计

## 4.1 Core 层模型拆分

建议保留 `MetricsDelta`，但将 `StrategyComparisonReport` 升级为更结构化的模型：

```python
@dataclass(frozen=True)
class ComparedMetric:
    name: str
    baseline_value: float
    compare_value: float
    delta: float
    delta_pct: float | None
    preference: Literal["higher_is_better", "lower_is_better", "neutral"]
    direction: Literal["improved", "degraded", "unchanged"]

@dataclass(frozen=True)
class SignificanceResult:
    metric_name: str
    method: str
    p_value: float | None
    ci_low: float | None
    ci_high: float | None
    verdict: Literal[
        "significant_improvement",
        "significant_degradation",
        "not_significant",
        "not_applicable",
    ]

@dataclass(frozen=True)
class ComparisonFinding:
    finding_id: str
    severity: Literal["info", "warning", "critical"]
    category: str
    summary: str
    evidence_keys: tuple[str, ...]

@dataclass(frozen=True)
class StrategyComparisonReport:
    baseline_run_id: str
    compare_run_id: str
    metrics: tuple[ComparedMetric, ...]
    significance: tuple[SignificanceResult, ...]
    findings: tuple[ComparisonFinding, ...]
    improved: tuple[str, ...]
    degraded: tuple[str, ...]
```

### 4.2 输入协议升级

显著性分析需要的不只是聚合值，还需要时间序列。建议新增更丰富的 protocol：

```python
class BacktestComparisonView(Protocol):
    run_id: str
    final_nav: float
    alpha_stats: AlphaStatsView
    aggregated_trade_stats: AggregatedTradeStatsView
    nav_series: tuple[tuple[str, float], ...]
```

如有必要，可额外提供：

- `trade_log`
- `fill_log`
- `risk_log`

但 V1 不应强制全部暴露。最小可用输入是 `nav_series`，因为：

- 日收益差异显著性检验需要它
- rolling relative performance 需要它

### 4.3 统计检验方法

推荐 V1 不直接上脆弱的公式化 Sharpe 检验，而使用更稳健的时间序列 bootstrap：

1. **日收益差异显著性**
   - 基于两条 `nav_series` 计算 paired daily returns
   - 对 return spread 使用 moving block bootstrap
   - 产出 mean spread CI 与 p-value

2. **Sharpe 差异显著性**
   - 在同一 bootstrap 样本上重新计算两侧 Sharpe
   - 估计 `Sharpe(compare) - Sharpe(baseline)` 的置信区间

3. **不做显著性检验的指标**
   - `total_fees`
   - `total_turnover`
   - `cost_drag`
   - `total_trades`
   - `max_drawdown`

这些指标可以给 direction，但显著性标记为 `not_applicable`。

### 4.4 解释层（findings）

V1 建议采用 rule-based findings，而不是自由文本生成。最小可落地规则包括：

- `return_improved_but_not_significant`
- `return_improved_with_higher_turnover`
- `sharpe_improved_with_worse_drawdown`
- `fees_increased_without_return_gain`
- `performance_concentrated_in_single_window`

每条 finding 必须是结构化对象，而不是直接拼中文段落。这样后续 UI、CLI、API 都能复用。

### 4.5 Artifact 设计

推荐新增以下 comparison artifact：

| 文件 | 用途 |
|---|---|
| `comparison_report.json` | 主报告，含 metrics / significance / findings |
| `daily_return_spread.parquet` | 两个 run 的每日收益与差值 |
| `rolling_comparison.parquet` | 滚动 NAV / drawdown / rolling sharpe |

建议同步扩展 `ArtifactKind`：

- `COMPARISON_REPORT`
- `COMPARISON_RETURNS`
- `COMPARISON_ROLLING`

### 4.6 控制面建议

V1 可以不新增独立 comparison 表，先复用 `StrategyArtifactRecord.metadata` 记录：

```json
{
  "baseline_run_id": "run-a",
  "compare_run_id": "run-b",
  "strategy_id": "momentum-etf",
  "summary": {
    "annualized_return_delta": 0.023,
    "sharpe_delta": 0.18,
    "verdict": "significant_improvement"
  }
}
```

如果后续 comparison 成为高频运营对象，再升级为独立 `StrategyComparisonRecord`。

---

## 5. 推荐实施路径

### Task 1：整理 Core 比较边界类型

**Files**
- Modify: `packages/core/src/ditto_core/portfolio/report_views.py`
- Modify: `packages/core/src/ditto_core/portfolio/comparison.py`
- Test: `packages/core/tests/unit/portfolio/test_comparison_unit.py`

**目标**
- 从“只接受聚合指标”升级为“可接受时间序列视图”
- 保持现有基础 delta 行为不回退

### Task 2：新增统计检验模块

**Files**
- Create: `packages/core/src/ditto_core/portfolio/significance.py`
- Create: `packages/core/src/ditto_core/portfolio/findings.py`
- Modify: `packages/core/src/ditto_core/portfolio/__init__.py`
- Test: `packages/core/tests/unit/portfolio/test_significance_unit.py`
- Test: `packages/core/tests/unit/portfolio/test_findings_unit.py`

**目标**
- 将统计检验和 findings 与 `compare_reports()` 主函数解耦

### Task 3：重构 `StrategyComparisonReport`

**Files**
- Modify: `packages/core/src/ditto_core/portfolio/comparison.py`
- Test: `packages/core/tests/unit/portfolio/test_comparison_unit.py`

**目标**
- 输出结构化 metrics / significance / findings
- 保留 `improved / degraded` 以兼容现有消费方

### Task 4：引入 comparison artifact

**Files**
- Modify: `packages/datahub/src/ditto_datahub/models/strategy.py`
- Modify: `packages/datahub/tests/unit/stores/metadata/test_strategy_artifact_store_unit.py`
- Create: `apps/port/src/ditto_port/services/strategy/comparison_writer.py`
- Test: `apps/port/tests/unit/services/strategy/test_comparison_writer_unit.py`

**目标**
- 将 comparison 结果落成 artifact，而不是只存在内存

### Task 5：Port 编排层新增 comparison service

**Files**
- Create: `apps/port/src/ditto_port/services/strategy/comparison_service.py`
- Modify: `apps/port/src/ditto_port/services/strategy/factory.py`
- Modify: `apps/port/src/ditto_port/services/strategy/__init__.py`
- Modify: `apps/port/src/ditto_port/registry/port/strategy.py`
- Test: `apps/port/tests/unit/services/strategy/test_comparison_service_unit.py`
- Test: `apps/port/tests/registry/test_strategy_provider_unit.py`

**目标**
- 让 comparison 具备明确的 Port orchestration 入口
- 输入可以是 `baseline_run_id + compare_run_id` 或两个 `BacktestReport`

### Task 6：文档与控制面收尾

**Files**
- Modify: `docs/plans/2026-03-21-strategy-engine-system-design-v3.md`
- Modify: `packages/core/src/ditto_core/portfolio/README.md`
- Modify: `docs/plans/2026-03-24-strategy-engine-v3-completion-audit-refresh.md`

---

## 6. 测试与验证策略

### 6.1 必须覆盖的测试场景

1. 相同报告比较 → 所有 delta 为 0，显著性为 `not_significant`/`not_applicable`
2. return 改善但置信区间穿过 0 → 不显著
3. return 改善且 bootstrap CI 全为正 → `significant_improvement`
4. fees/turnover 变化 → direction 正确，但显著性为 `not_applicable`
5. findings 正确识别“收益提升但成本上升”
6. comparison artifact metadata 正确记录 `baseline_run_id / compare_run_id`

### 6.2 建议命令

```bash
pixi run -e dev pytest packages/core/tests/unit/portfolio/test_comparison_unit.py -v
pixi run -e dev pytest packages/core/tests/unit/portfolio/test_significance_unit.py -v
pixi run -e dev pytest apps/port/tests/unit/services/strategy/test_comparison_service_unit.py -v
pixi run -e dev check
```

---

## 7. 风险与控制

### 风险 1：统计方法过度复杂

**控制**
- V1 只做 daily return spread + Sharpe delta bootstrap
- 不把所有指标都强行显著性化

### 风险 2：Core 比较逻辑与 Port artifact 编排耦合

**控制**
- Core 只产出结构化对象
- 落盘与 run_id 关联放在 Port/DataHub

### 风险 3：解释逻辑沦为硬编码文本

**控制**
- findings 必须是结构化对象
- 文本渲染放到消费侧，而不是 Core 模型层

---

## 8. 结论

当前 `StrategyComparisonReport` 已经是一个不错的基础版比较器，但它距离“实验评估系统”还差三步：

1. 从纯 delta 升级为 `metrics + significance + findings`
2. 从内存对象升级为 artifact-first 结果
3. 从函数调用升级为 run-to-run 的控制面语义

建议下一轮按“先 Core 分析层、再 Port artifact 编排”的顺序推进，而不是直接在当前 `compare_reports()` 上继续堆字段。
