import { useInstrumentDetail } from "../hooks";
import { Metric } from "@/components/data/metric";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

interface InstrumentMetaStripProps {
	readonly id: string;
}

export function InstrumentMetaStrip({ id }: InstrumentMetaStripProps) {
	const { data, isLoading, refetch } = useInstrumentDetail(id);

	if (isLoading) {
		return (
			<div className="flex gap-4 px-4 py-3">
				{Array.from({ length: 6 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex items-center gap-4 px-4 py-3">
					<div className="flex flex-col">
						<span className="text-lg font-bold">{data.name}</span>
						<span className="text-xs text-(--color-foreground-tertiary)">{data.code}</span>
					</div>
					<StatusBadge
						variant={data.status === "active" ? "healthy" : "warning"}
						label={data.status}
						size="sm"
					/>
					<div className="flex gap-4">
						<Metric
							variant="strip"
							label="价格"
							value={data.price.toFixed(2)}
							trend={data.change >= 0 ? "up" : "down"}
							sub={`${data.change >= 0 ? "+" : ""}${data.changePercent.toFixed(2)}%`}
						/>
						<Metric variant="strip" label="PE" value={data.pe.toFixed(1)} />
						<Metric variant="strip" label="PB" value={data.pb.toFixed(1)} />
						<Metric variant="strip" label="行业" value={data.industry} />
						<Metric
							variant="strip"
							label="市值"
							value={data.marketCap >= 1_000_000_000_000
								? `${(data.marketCap / 1_000_000_000_000).toFixed(1)}万亿`
								: `${(data.marketCap / 100_000_000).toFixed(0)}亿`}
						/>
					</div>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
