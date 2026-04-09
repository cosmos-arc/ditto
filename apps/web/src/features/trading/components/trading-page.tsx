import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { TradingSessionStrip } from "./trading-session-strip";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";

const MOCK_SIGNALS = [
	{ name: "贵州茅台", direction: "sell" as const, reason: "RSI背离+放量, Alpha v3", time: "3分钟前", confidence: 87, priority: "p1" as const },
	{ name: "宁德时代", direction: "buy" as const, reason: "均值回归 v2", time: "12分钟前", confidence: 72, priority: "p2" as const },
	{ name: "中国平安", direction: "hold" as const, reason: "市场状态过滤", time: "28分钟前", confidence: 91, priority: "p3" as const },
	{ name: "美的集团", direction: "sell" as const, reason: "动量反转, Alpha v3", time: "45分钟前", confidence: 68, priority: "p3" as const },
];

const MOCK_RISK_ITEMS = [
	{ label: "行业集中度", value: "科技 37.2%", annotation: "超限 +2.2%", severity: "critical" as const, progress: 68.2 },
	{ label: "风险预算", value: "68.2%", severity: "warning" as const, progress: 68.2 },
	{ label: "最大持仓", value: "贵州茅台 14.2%", severity: "ok" as const },
	{ label: "日内回撤", value: "-0.12%", severity: "ok" as const },
];

export function TradingPage() {
	return (
		<AnalyticalLayout
			strip={<TradingSessionStrip />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<EquityPnlBlock />
					<PositionsSummary />
					<RiskAlertsBlock />
				</div>
			}
			activity={
				<Panel>
					<PanelHeader title="信号队列" />
					<PanelBody className="p-3">
						<div className="flex flex-col gap-1">
							{MOCK_SIGNALS.map((signal) => (
								<div
									key={signal.name}
									className="flex gap-2 rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className={`w-0.5 shrink-0 rounded-full ${signal.priority === "p1" ? "bg-(--color-risk-critical-fg)" : signal.priority === "p2" ? "bg-(--color-risk-high-fg)" : "bg-(--color-foreground-muted)"}`} />
									<div className="flex min-w-0 flex-1 flex-col gap-0.5">
										<div className="flex items-center gap-2">
											<span className="text-xs font-medium text-(--color-foreground)">{signal.name}</span>
											<span className={`text-[10px] font-medium ${signal.direction === "sell" ? "text-(--color-market-down-fg)" : signal.direction === "buy" ? "text-(--color-market-up-fg)" : "text-(--color-foreground-muted)"}`}>
												{signal.direction === "sell" ? "卖出信号" : signal.direction === "buy" ? "买入信号" : "持有信号"}
											</span>
										</div>
										<span className="text-[10px] text-(--color-foreground-tertiary)">{signal.reason}</span>
										<div className="flex items-center gap-2">
											<span className="text-[10px] tabular-nums text-(--color-foreground-muted)">{signal.time}</span>
											<span className={`text-[10px] tabular-nums ${signal.confidence >= 85 ? "text-(--color-market-up-fg)" : signal.confidence >= 70 ? "text-(--color-risk-high-fg)" : "text-(--color-foreground-muted)"}`}>
												置信度 {signal.confidence}%
											</span>
										</div>
									</div>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
			analysis={
				<Panel>
					<PanelHeader
						title="风控监控"
						count={2}
					/>
					<PanelBody className="p-3">
						<div className="flex flex-col gap-1">
							{MOCK_RISK_ITEMS.map((item) => (
								<div
									key={item.label}
									className="flex items-center gap-2 rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className={`size-1.5 shrink-0 rounded-full ${item.severity === "critical" ? "bg-(--color-risk-critical-fg)" : item.severity === "warning" ? "bg-(--color-risk-high-fg)" : "bg-(--color-system-healthy-fg)"}`} />
									<div className="flex min-w-0 flex-1 flex-col gap-1">
										<div className="flex items-center justify-between">
											<span className="text-xs text-(--color-foreground-secondary)">{item.label}</span>
											<span className={`text-xs tabular-nums ${item.severity === "critical" ? "text-(--color-risk-critical-fg)" : item.severity === "warning" ? "text-(--color-risk-high-fg)" : "text-(--color-system-healthy-fg)"}`}>
												{item.value}
											</span>
										</div>
										{item.progress !== undefined && (
											<div className="h-0.5 w-full overflow-hidden rounded-full bg-(--color-border-subtle)">
												<div
													className={`h-full rounded-full ${item.severity === "critical" ? "bg-(--color-risk-critical-fg)" : "bg-(--color-risk-high-fg)"}`}
													style={{ width: `${item.progress}%` }}
												/>
											</div>
										)}
									</div>
								</div>
							))}
						</div>
					</PanelBody>
				</Panel>
			}
		/>
	);
}
