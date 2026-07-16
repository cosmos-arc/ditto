import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/features/shell/components/panel";
import type { Signal, SignalDirection } from "@/types";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useSignals } from "../hooks";

type SignalPriority = "p1" | "p2" | "p3";
type MockSignalDirection = "buy" | "sell" | "hold";

const PRIORITY_DOT: Record<SignalPriority, string> = {
	p1: "bg-(--color-risk-critical-fg)",
	p2: "bg-(--color-risk-high-fg)",
	p3: "bg-(--color-foreground-muted)",
};

const DIRECTION_COLOR: Record<MockSignalDirection | SignalDirection, string> = {
	sell: "text-(--color-market-down-fg)",
	buy: "text-(--color-market-up-fg)",
	hold: "text-(--color-foreground-muted)",
	SELL: "text-(--color-market-down-fg)",
	BUY: "text-(--color-market-up-fg)",
	HOLD: "text-(--color-foreground-muted)",
};

const DIRECTION_LABEL: Record<MockSignalDirection | SignalDirection, string> = {
	sell: "卖出信号",
	buy: "买入信号",
	hold: "持有信号",
	SELL: "卖出信号",
	BUY: "买入信号",
	HOLD: "持有信号",
};

const MOCK_SIGNALS = [
	{
		name: "贵州茅台",
		direction: "sell" as const,
		reason: "RSI背离+放量, Alpha v3",
		time: "3分钟前",
		confidence: 87,
		priority: "p1" as const,
	},
	{
		name: "宁德时代",
		direction: "buy" as const,
		reason: "均值回归 v2",
		time: "12分钟前",
		confidence: 72,
		priority: "p2" as const,
	},
	{
		name: "中国平安",
		direction: "hold" as const,
		reason: "市场状态过滤",
		time: "28分钟前",
		confidence: 91,
		priority: "p3" as const,
	},
	{
		name: "美的集团",
		direction: "sell" as const,
		reason: "动量反转, Alpha v3",
		time: "45分钟前",
		confidence: 68,
		priority: "p3" as const,
	},
];

function confidenceColor(confidence: number): string {
	if (confidence >= 85) return "text-(--color-market-up-fg)";
	if (confidence >= 70) return "text-(--color-risk-high-fg)";
	return "text-(--color-foreground-muted)";
}

function liveConfidenceColor(confidence: number): string {
	return confidenceColor(Math.round(confidence * 100));
}

function priorityFromSignal(signal: Signal): SignalPriority {
	if (signal.confidence == null) return "p3";
	if (signal.confidence >= 0.85) return "p1";
	if (signal.confidence >= 0.7) return "p2";
	return "p3";
}

function MockSignalsQueue() {
	return (
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
							<span className={`text-xs font-medium ${DIRECTION_COLOR[signal.direction]}`}>
								{DIRECTION_LABEL[signal.direction]}
							</span>
						</div>
						<span className="text-xs text-(--color-foreground-tertiary)">{signal.reason}</span>
						<div className="flex items-center gap-2">
							<span className="font-data text-xs tabular-nums text-(--color-foreground-muted)">{signal.time}</span>
							<span className={`font-data text-xs tabular-nums ${confidenceColor(signal.confidence)}`}>
								置信度 {signal.confidence}%
							</span>
						</div>
					</div>
				</div>
			))}
		</div>
	);
}

function LiveSignalsQueue() {
	const { data, isLoading, isError, refetch } = useSignals({ tab: "pending", limit: 4 });
	const signals = data?.items ?? [];

	if (isLoading) {
		return (
			<div role="status" aria-label="信号队列加载中">
				<LoadingSkeleton variant="panel" rows={4} />
			</div>
		);
	}

	if (isError) {
		return (
			<div
				role="alert"
				className="flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
			>
				<span>信号队列加载失败</span>
				<Button variant="outline" size="sm" onClick={() => void refetch()}>
					重试
				</Button>
			</div>
		);
	}

	if (signals.length === 0) {
		return (
			<div
				role="status"
				aria-label="信号队列状态"
				className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-4 text-sm text-(--color-foreground-secondary)"
			>
				暂无待复核信号
			</div>
		);
	}

	return (
		<>
			<span role="status" aria-label="信号队列加载完成" className="sr-only">
				信号队列已加载，共 {signals.length} 条
			</span>
			<div className="flex flex-col gap-1">
				{signals.map((signal) => (
					<div
						key={signal.id}
						className="flex gap-2 rounded-(--radius-sm) px-2 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						<div className={`w-0.5 shrink-0 rounded-full ${PRIORITY_DOT[priorityFromSignal(signal)]}`} />
						<div className="flex min-w-0 flex-1 flex-col gap-0.5">
							<div className="flex items-center gap-2">
								<span className="text-xs font-medium text-(--color-foreground)">{signal.instrument}</span>
								<span className={`text-xs font-medium ${DIRECTION_COLOR[signal.direction]}`}>
									{DIRECTION_LABEL[signal.direction]}
								</span>
							</div>
							<span className="text-xs text-(--color-foreground-tertiary)">{signal.source}</span>
							<div className="flex items-center gap-2">
								<span className="font-data text-xs tabular-nums text-(--color-foreground-muted)">
									{new Date(signal.time).toISOString().slice(0, 10)}
								</span>
								{signal.confidence != null && (
									<span className={`font-data text-xs tabular-nums ${liveConfidenceColor(signal.confidence)}`}>
										置信度 {Math.round(signal.confidence * 100)}%
									</span>
								)}
							</div>
						</div>
					</div>
				))}
			</div>
		</>
	);
}

export function TradingOverviewSignalsPanel() {
	const usePrototypeMocks = shouldUsePrototypeMocks();

	return (
		<Panel data-info-level="l2" data-info-unit="signals-queue">
			<PanelHeader title="信号队列" />
			<PanelBody className="p-3">{usePrototypeMocks ? <MockSignalsQueue /> : <LiveSignalsQueue />}</PanelBody>
		</Panel>
	);
}
