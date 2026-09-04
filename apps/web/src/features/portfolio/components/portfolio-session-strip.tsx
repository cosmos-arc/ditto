import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { usePortfolioSession } from "../hooks";

const LOADING_METRIC_IDS = ["phase", "cash", "margin", "risk-budget"] as const;

const PHASE_LABELS: Record<string, string> = {
	continuous: "连续竞价",
	call_auction: "集合竞价",
	closed: "已收盘",
};

function ContextSeparator() {
	return <span aria-hidden="true" className="h-3.5 w-px shrink-0 bg-(--color-border-subtle)" />;
}

function ContextMetric({
	label,
	value,
	tone,
	dot = false,
}: {
	readonly label: string;
	readonly value: string;
	readonly tone?: "healthy" | "warning";
	readonly dot?: boolean;
}) {
	const toneClass =
		tone === "healthy"
			? "text-(--color-status-healthy-fg)"
			: tone === "warning"
				? "text-(--color-risk-high-fg)"
				: "text-(--color-foreground)";

	return (
		<span className="flex shrink-0 items-center gap-1 whitespace-nowrap text-xs">
			{dot && <span aria-hidden="true" className="size-1.5 rounded-full bg-(--color-status-healthy-fg)" />}
			<span className="text-(--color-foreground-tertiary)">{label}</span>
			<span className={`font-data font-medium tabular-nums ${toneClass}`}>{value}</span>
		</span>
	);
}

export function PortfolioSessionStrip() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const { data, isLoading, refetch } = usePortfolioSession({ enabled: usePrototypeMocks });

	if (!usePrototypeMocks) {
		return (
			<div
				data-info-level="l2"
				data-info-unit="session-strip"
				className="flex h-[var(--density-strip-height)] items-center gap-3 border-b border-(--color-border) bg-(--color-surface-strip) px-4"
			>
				<StatusBadge label="manual / paper" variant="trade" size="sm" />
				<span className="text-sm text-(--color-foreground-secondary)">决策范围由 URL 显式选择</span>
			</div>
		);
	}

	if (isLoading) {
		return (
			<div className="flex h-[var(--density-strip-height)] items-center gap-3 border-b border-(--color-border) bg-(--color-surface-strip) px-4">
				{LOADING_METRIC_IDS.map((metricId) => (
					<LoadingSkeleton key={metricId} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div
				data-info-level="l2"
				data-info-unit="session-strip"
				className="flex h-[var(--density-strip-height)] items-center gap-2 overflow-hidden border-b border-(--color-border) bg-(--color-surface-strip) px-4"
			>
				<span className="flex shrink-0 items-center gap-1 rounded-[3px] border border-[color-mix(in_oklch,var(--color-status-healthy-fg)_24%,var(--color-border-subtle))] bg-[color-mix(in_oklch,var(--color-status-healthy-fg)_12%,transparent)] px-1.5 py-0.5 text-xs font-medium text-(--color-status-healthy-fg)">
					<span aria-hidden="true" className="size-1.5 rounded-full bg-(--color-status-healthy-fg)" />
					{data?.phase ? (PHASE_LABELS[data.phase] ?? data.phase) : "阶段不可用"}
				</span>
				<ContextSeparator />
				<ContextMetric
					label="可用资金"
					value={data?.cashBalance != null ? `¥${data.cashBalance.toLocaleString()}` : "—"}
				/>
				<ContextSeparator />
				<ContextMetric
					label="保证金"
					value={data?.margin.usedMargin != null ? `¥${data.margin.usedMargin.toLocaleString()}` : "—"}
				/>
				<ContextSeparator />
				<ContextMetric
					label="担保比例"
					value={data?.margin.maintenanceRatio != null ? `${(data.margin.maintenanceRatio * 100).toFixed(0)}%` : "—"}
					tone="healthy"
				/>
				<ContextSeparator />
				<ContextMetric
					label="风险预算"
					value={data?.riskBudget != null ? `${(data.riskBudget * 100).toFixed(1)}%` : "—"}
					tone={data && data.riskBudget >= 0.5 ? "warning" : undefined}
				/>
				<ContextSeparator />
				<ContextMetric label="账户模式" value="Manual / Paper" tone="healthy" />
				<ContextSeparator />
				<ContextMetric label="数据来源" value="原型快照" />
				<ContextSeparator />
				<span title="当前公开会话合同未提供执行队列统计">
					<ContextMetric label="执行队列" value="暂无可靠数据" />
				</span>
			</div>
		</DittoErrorBoundary>
	);
}
