"""BacktestReportRenderer — 将回测报告渲染为 HTML."""

from __future__ import annotations

from string import Template

from ditto_backtest.statistics import BacktestReport

_HTML_TEMPLATE = Template(
    """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>回测报告 — $run_id</title>
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 2rem; background: #f5f5f5; color: #333;
  }
  .container {
    max-width: 960px; margin: 0 auto; background: #fff;
    padding: 2rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1);
  }
  h1 { border-bottom: 2px solid #4a90d9; padding-bottom: .5rem; }
  h2 { color: #4a90d9; margin-top: 2rem; }
  table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
  th, td { padding: .5rem .75rem; text-align: left; border-bottom: 1px solid #e0e0e0; }
  th { background: #f0f4f8; font-weight: 600; }
  .metric {
    display: inline-block; width: 30%; margin: .5rem 1% .5rem 0;
    padding: 1rem; background: #f9f9f9; border-radius: 4px;
  }
  .metric .value { font-size: 1.5rem; font-weight: 700; }
  .metric .label { font-size: .85rem; color: #666; }
  .positive { color: #2e7d32; } .negative { color: #c62828; }
</style>
</head>
<body>
<div class="container">
<h1>回测报告</h1>

<h2>概览</h2>
<div class="metric">
  <div class="value">$annualized_return%</div>
  <div class="label">年化收益率</div>
</div>
<div class="metric">
  <div class="value">$sharpe_ratio</div>
  <div class="label">夏普比率</div>
</div>
<div class="metric">
  <div class="value">$max_drawdown%</div>
  <div class="label">最大回撤</div>
</div>

<h2>基本信息</h2>
<table>
<tr><th>运行 ID</th><td>$run_id</td></tr>
<tr><th>回测期间</th><td>$start_date ~ $end_date</td></tr>
<tr><th>初始资金</th><td>$initial_cash</td></tr>
<tr><th>最终净值</th><td>$final_nav</td></tr>
<tr><th>年化收益率</th><td>$annualized_return%</td></tr>
<tr><th>年化波动率</th><td>$annualized_volatility%</td></tr>
<tr><th>索提诺比率</th><td>$sortino_ratio</td></tr>
<tr><th>卡玛比率</th><td>$calmar_ratio</td></tr>
<tr><th>换手率</th><td>$total_turnover%</td></tr>
</table>

<h2>交易统计</h2>
<table>
<tr><th>总交易</th><td>$total_trades</td></tr>
<tr><th>胜率</th><td>$win_rate%</td></tr>
<tr><th>盈亏比</th><td>$profit_factor</td></tr>
<tr><th>平均盈利</th><td>$avg_win</td></tr>
<tr><th>平均亏损</th><td>$avg_loss</td></tr>
<tr><th>最大连续盈利</th><td>$max_consecutive_wins</td></tr>
<tr><th>最大连续亏损</th><td>$max_consecutive_losses</td></tr>
</table>

</div>
</body>
</html>"""
)


class BacktestReportRenderer:
    """将 BacktestReport 渲染为 HTML 字符串。"""

    def render(self, report: BacktestReport) -> str:
        """渲染回测报告为 HTML。"""
        a = report.alpha_stats
        t = report.aggregated_trade_stats

        return _HTML_TEMPLATE.substitute(
            run_id=report.run_id,
            start_date=report.period[0],
            end_date=report.period[1],
            initial_cash=f"{report.initial_cash:,.2f}",
            final_nav=f"{report.final_nav:,.4f}",
            annualized_return=f"{self._fmt(a.annualized_return)}",
            annualized_volatility=f"{self._fmt(a.annualized_volatility)}",
            sharpe_ratio=f"{a.sharpe_ratio:.2f}",
            sortino_ratio=f"{a.sortino_ratio:.2f}",
            max_drawdown=f"{self._fmt(a.max_drawdown)}",
            calmar_ratio=f"{a.calmar_ratio:.2f}",
            total_turnover=f"{self._fmt(a.total_turnover)}",
            total_trades=t.total_trades,
            win_rate=f"{t.win_rate:.1f}",
            profit_factor=f"{t.profit_factor:.2f}",
            avg_win=f"{t.avg_win:,.2f}",
            avg_loss=f"{t.avg_loss:,.2f}",
            max_consecutive_wins=t.max_consecutive_wins,
            max_consecutive_losses=t.max_consecutive_losses,
        )

    @staticmethod
    def _fmt(value: float) -> str:
        return f"{value:+.2f}" if value >= 0 else f"{value:.2f}"
