import { Metric } from "@/components/data/metric/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useSignalsQueue } from "../hooks/use-signals-queue";

const SIGNAL_METRIC_KEYS = ["pending", "confirmed", "ignored", "ordered"] as const;

export function SignalsHealthStrip() {
	const { data, isLoading, isError, refetch } = useSignalsQueue();

	if (isLoading) {
		return (
			<div className="grid h-9 grid-cols-2 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 sm:grid-cols-4">
				{SIGNAL_METRIC_KEYS.map((key) => (
					<LoadingSkeleton key={key} variant="metric" />
				))}
			</div>
		);
	}

	if (isError) {
		return (
			<div
				role="alert"
				className="mx-4 flex h-9 flex-col items-start justify-center gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
			>
				<span>信号队列数据加载失败</span>
				<Button variant="outline" size="sm" onClick={() => void refetch()}>
					重试
				</Button>
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div className="grid h-9 grid-cols-2 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 sm:grid-cols-4">
				<div data-info-level="l1" data-info-unit="signal-metric-pending">
					<Metric variant="strip" label="待处理" value={data?.pending ?? "—"} />
				</div>
				<div data-info-level="l1" data-info-unit="signal-metric-confirmed">
					<Metric variant="strip" label="已确认" value={data?.confirmed ?? "—"} />
				</div>
				<div data-info-level="l1" data-info-unit="signal-metric-ignored">
					<Metric variant="strip" label="已忽略" value={data?.ignored ?? "—"} />
				</div>
				<div data-info-level="l1" data-info-unit="signal-metric-ordered">
					<Metric variant="strip" label="已下单" value={data?.ordered ?? "—"} />
				</div>
			</div>
		</DittoErrorBoundary>
	);
}
