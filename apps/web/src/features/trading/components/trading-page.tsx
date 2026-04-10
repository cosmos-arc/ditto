import { useState } from "react";
import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { DecisionBanner } from "@/components/domain/decision-banner";
import { ContextSection } from "@/components/domain/context-section";
import { TradingSessionStrip } from "./trading-session-strip";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";

/* ── Color / Label Maps ── */

type Severity = "critical" | "warning" | "ok";

const SEVERITY_DOT: Record<Severity, string> = {
	critical: "bg-(--color-risk-critical-fg)",
	warning: "bg-(--color-risk-high-fg)",
	ok: "bg-(--color-system-healthy-fg)",
};

const SEVERITY_TEXT: Record<Severity, string> = {
	critical: "text-(--color-risk-critical-fg)",
	warning: "text-(--color-risk-high-fg)",
	ok: "text-(--color-system-healthy-fg)",
};

const SEVERITY_BAR: Record<Severity, string> = {
	critical: "bg-(--color-risk-critical-fg)",
	warning: "bg-(--color-risk-high-fg)",
	ok: "bg-(--color-risk-high-fg)",
};

type SignalPriority = "p1" | "p2" | "p3";
type SignalDirection = "buy" | "sell" | "hold";

const PRIORITY_DOT: Record<SignalPriority, string> = {
	p1: "bg-(--color-risk-critical-fg)",
	p2: "bg-(--color-risk-high-fg)",
	p3: "bg-(--color-foreground-muted)",
};

const DIRECTION_COLOR: Record<SignalDirection, string> = {
	sell: "text-(--color-market-down-fg)",
	buy: "text-(--color-market-up-fg)",
	hold: "text-(--color-foreground-muted)",
};

const DIRECTION_LABEL: Record<SignalDirection, string> = {
	sell: "卖出信号",
	buy: "买入信号",
	hold: "持有信号",
};

function confidenceColor(confidence: number): string {
	if (confidence >= 85) return "text-(--color-market-up-fg)";
	if (confidence >= 70) return "text-(--color-risk-high-fg)";
	return "text-(--color-foreground-muted)";
}

/* ── Mock Data: Decision Banner ── */

const DECISION_BANNER_PROPS = {
	primary: {
		label: "组合净值",
		value: "1.0842",
		sub: "今日 +1.24%",
		trend: "up" as const,
		sparkline: [1.02, 1.04, 1.03, 1.05, 1.06, 1.07, 1.08],
	},
	judgment: {
		text: "当前市场风险偏好上升，建议适度加仓。杠杆率 1.2x，最大回撤 -2.3%。",
		regime: { label: "Risk-On", variant: "regime-on" as const },
		metrics: [
			{ label: "IVIX", value: "18.5", trend: "down" as const },
			{ label: "北向资金", value: "+3.2亿", trend: "up" as const },
		],
	},
	actions: [
		{ label: "执行调仓", variant: "primary" as const },
		{ label: "查看详情", variant: "secondary" as const },
	],
};

/* ── Mock Data: Orders ── */

type OrderSide = "buy" | "sell";

interface MockOrder {
	readonly code: string;
	readonly name: string;
	readonly side: OrderSide;
	readonly qty: number;
	readonly price: number;
	readonly time: string;
}

type OrderTab = "pending" | "filled" | "cancelled";

const ORDERS: Record<OrderTab, readonly MockOrder[]> = {
	pending: [
		{ code: "600519.SH", name: "贵州茅台", side: "buy", qty: 100, price: 1750.0, time: "09:45" },
		{ code: "000858.SZ", name: "五粮液", side: "sell", qty: 500, price: 146.0, time: "10:15" },
	],
	filled: [
		{ code: "300750.SZ", name: "宁德时代", side: "buy", qty: 200, price: 210.5, time: "09:30" },
		{ code: "000001.SZ", name: "平安银行", side: "sell", qty: 5000, price: 12.1, time: "09:35" },
	],
	cancelled: [
		{ code: "601318.SH", name: "中国平安", side: "buy", qty: 1000, price: 45.0, time: "09:20" },
	],
};

const TAB_LABELS: Record<OrderTab, string> = {
	pending: "待成交",
	filled: "已成交",
	cancelled: "已撤单",
};

/* ── Local Component: Orders Panel ── */

function OrdersPanel() {
	const [activeTab, setActiveTab] = useState<OrderTab>("pending");
	const orders = ORDERS[activeTab];

	return (
		<ContextSection title="委托订单" count={orders.length}>
			<div className="flex gap-1 py-2">
				{(Object.keys(TAB_LABELS) as OrderTab[]).map((tab) => (
					<button
						key={tab}
						type="button"
						className={`rounded-(--radius-sm) px-2.5 py-1 text-xs font-medium transition-colors ${
							activeTab === tab
								? "bg-(--color-surface-2) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary)"
						}`}
						onClick={() => setActiveTab(tab)}
					>
						{TAB_LABELS[tab]}
					</button>
				))}
			</div>
			<div className="flex flex-col gap-0.5">
				{orders.map((order) => (
					<div
						key={`${order.code}-${order.time}`}
						className="flex items-center gap-2 rounded-(--radius-sm) px-2 py-1.5 hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						<span
							className={`shrink-0 rounded-(--radius-sm) px-1 py-px text-[10px] font-semibold ${
								order.side === "buy"
									? "bg-(--color-market-up-bg) text-(--color-market-up-fg)"
									: "bg-(--color-market-down-bg) text-(--color-market-down-fg)"
							}`}
						>
							{order.side === "buy" ? "买" : "卖"}
						</span>
						<span className="flex-1 truncate text-xs font-medium text-(--color-foreground)">
							{order.name}
						</span>
						<span className="font-data text-[10px] tabular-nums text-(--color-foreground-tertiary)">
							{order.qty}股
						</span>
						<span className="font-data text-[10px] tabular-nums text-(--color-foreground-secondary)">
							@{order.price.toFixed(2)}
						</span>
						<span className="font-data text-[10px] tabular-nums text-(--color-foreground-muted)">
							{order.time}
						</span>
					</div>
				))}
			</div>
		</ContextSection>
	);
}

/* ── Mock Data: Signals & Risk (activity/analysis panels) ── */

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

/* ── Page Component ── */

export function TradingPage() {
	return (
		<AnalyticalLayout
			strip={<TradingSessionStrip />}
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<EquityPnlBlock />
					<DecisionBanner {...DECISION_BANNER_PROPS} />
					<PositionsSummary />
					<RiskAlertsBlock />
					<OrdersPanel />
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
									<div className={`w-0.5 shrink-0 rounded-full ${PRIORITY_DOT[signal.priority]}`} />
									<div className="flex min-w-0 flex-1 flex-col gap-0.5">
										<div className="flex items-center gap-2">
											<span className="text-xs font-medium text-(--color-foreground)">{signal.name}</span>
											<span className={`text-[10px] font-medium ${DIRECTION_COLOR[signal.direction]}`}>
												{DIRECTION_LABEL[signal.direction]}
											</span>
										</div>
										<span className="text-[10px] text-(--color-foreground-tertiary)">{signal.reason}</span>
										<div className="flex items-center gap-2">
											<span className="font-data text-[10px] tabular-nums text-(--color-foreground-muted)">{signal.time}</span>
											<span className={`font-data text-[10px] tabular-nums ${confidenceColor(signal.confidence)}`}>
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
									<div className={`size-1.5 shrink-0 rounded-full ${SEVERITY_DOT[item.severity]}`} />
									<div className="flex min-w-0 flex-1 flex-col gap-1">
										<div className="flex items-center justify-between">
											<span className="text-xs text-(--color-foreground-secondary)">{item.label}</span>
											<span className={`font-data text-xs tabular-nums ${SEVERITY_TEXT[item.severity]}`}>
												{item.value}
											</span>
										</div>
										{item.progress !== undefined && (
											<div className="h-0.5 w-full overflow-hidden rounded-full bg-(--color-border-subtle)">
												<div
													className={`h-full rounded-full ${SEVERITY_BAR[item.severity]}`}
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
