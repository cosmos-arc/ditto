# 因子 IC 诊断操作手册

> 对应路线图 [F1-#6](../../../docs/plans/archive/2026-06-14-production-launch-roadmap.md)(Phase 3 首个任务)

## 概述

`ditto ops factor-ic` 命令对单个因子执行 IC 诊断,输出 IC/ICIR/分层回测/多空/换手成本 Markdown 报告,形成「选因子 → 诊断 → 调选股权重」的人机闭环。

诊断底层复用 `FactorEvaluationFacade`(物化 artifact 读取 + 前向收益 + features 层 IC 评估编排),命令只做参数解析与 Markdown 渲染。

## ⚠️ 仅限非生产环境

前向收益计算(`ForwardReturnService`)在**生产环境**默认 fail-closed(避免前瞻偏差泄漏到生产路径)。本命令是离线研究工具,仅在 `development` / `testing` 环境运行;生产环境运行会以 `诊断失败` 退出。

## 命令用法

```bash
uv run --no-sync ditto ops factor-ic <FACTOR> --start <YYYY-MM-DD> --end <YYYY-MM-DD> [OPTIONS]
```

### 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `FACTOR` | 必填 | — | 因子 ID(derived artifact identifier,如 `momentum_1m`) |
| `--start` | 必填 | — | 评估起始日期 `YYYY-MM-DD` |
| `--end` | 必填 | — | 评估结束日期 `YYYY-MM-DD` |
| `--version` | int | active | 因子版本(省略则取当前 active version) |
| `--asset-class` | str | `stock` | 资产类别(`stock` / `etf`,前向收益计算用) |
| `--holding-period` | int | 5 | 前向收益持有天数 |
| `--n-quantiles` | int | 5 | 分层组数 |
| `--regime` | flag | off | 启用情景 IC 分析(市场状态切换下的 IC 稳定性) |
| `--attribution` | flag | off | 启用绩效归因(选股 / 择时 / alpha 分解) |
| `--output` | path | stdout | 写入文件路径(默认输出到 stdout) |

### 前置条件

- 因子已物化(derived artifact 存在;省略 `--version` 时解析 active version,无 active version 会以 `诊断失败` 退出,此时用 `--version` 显式指定)
- 对应 `--asset-class` 的行情数据已摄入(前向收益计算需要 close 价)

## 示例

```bash
# 基础 IC 诊断(默认 stdout)
uv run --no-sync ditto ops factor-ic momentum_1m --start 2024-01-01 --end 2024-06-30

# 写入文件 + 启用情景 IC
uv run --no-sync ditto ops factor-ic momentum_1m \
    --start 2024-01-01 --end 2024-06-30 --regime --output momentum_ic.md

# 指定版本 + ETF 资产 + 绩效归因
uv run --no-sync ditto ops factor-ic value_pe \
    --start 2024-01-01 --end 2024-06-30 --version 2 --asset-class etf --attribution
```

## 输出报告章节

| 章节 | 内容 | 触发条件 |
|------|------|----------|
| Header | 因子 ID / 版本 / 生成时间 / 评估区间 | 总是 |
| Overview | 交易日数 / 观测数 / 持有期 / 分层数 | 总是 |
| IC Summary | Rank IC vs Pearson IC 双列表格(mean / std / ICIR / t_stat / p_value / win_rate) | 总是 |
| IC Decay & Stability | IC 半衰期 + 多滞后 IC 表 + 一阶自相关 | 总是 |
| Sub-period IC | 按年 / 季度的 IC 稳定性 | sub_period_ic 非空 |
| Quantile Returns | 各分位年化收益 + 最高 / 最低分位单调性判断 | 总是 |
| Long-Short Portfolio | 多空年化收益 / 波动 / Sharpe / IR / Sortino / MaxDD / Calmar + 尾部风险(CVaR / 偏度 / 峰度) | 总是 |
| Turnover & Cost | 平均换手 / 成本后净收益 / 换手调整 IR / Grinold-Kahn IR | 总是 |
| Regime IC | 各情景 ICIR / Win Rate + IC 趋势 | `--regime` 且结果非空 |
| Performance Attribution | 总 / 选股 / 择时收益 + alpha / 跟踪误差 / IR | `--attribution` 且结果非空 |

无观测数据(`n_observations == 0`)时输出简短「无可用观测数据」提示。

## 如何用报告调选股权重

闭环核心:根据诊断结果调整 `stock_selection` 策略的 `signal_weights`。

| 诊断信号 | 含义 | 调权建议 |
|----------|------|----------|
| ICIR 高(>0.5)、p_value 低(<0.05) | 因子预测力强且稳定 | 提高权重 |
| 分层单调(top > bottom) | 因子分层区分度好 | 提高权重 |
| 多空 Sharpe > 0、net_return_after_cost > 0 | 扣成本后仍盈利 | 提高权重 |
| IC 半衰期短 | 信号衰减快 | 缩短调仓周期或降低权重 |
| 换手高、net_return_after_cost 接近 0 | 成本吃掉 alpha | 降低权重或加换手约束 |
| 分层非单调 | 因子失效或方向错 | 剔除或反向 |

## 范围与后续

- **本命令覆盖**:核心 IC 诊断 + 情景 IC(`--regime`)+ 绩效归因(`--attribution`)。
- **后续可选**:`--fama-macbeth` / `--exposure`(Fama-MacBeth 横截面回归 + 风险因子暴露)需装配 `RiskFactorProvider`,`EvaluationOptions` 字段已预留,待后续接入。

## 相关

- 路线图 [F1-#6](../../../docs/plans/archive/2026-06-14-production-launch-roadmap.md)
- 评估门面 [evaluation.py](../../application/src/ditto_application/queries/evaluation.py)
- 渲染模块 [factor_ic_report.py](../../application/src/ditto_application/queries/factor_ic_report.py)
- IC 算法 [features/evaluation/metrics/](../src/ditto_features/evaluation/metrics)
