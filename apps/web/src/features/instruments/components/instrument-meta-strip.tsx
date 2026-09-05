import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { ErrorState } from "@/lib/error-boundary";
import { useInstrumentDetail } from "../hooks";

const LOADING_METRIC_IDS = ["identity", "status", "asset", "listed"] as const;

interface InstrumentMetaStripProps {
	readonly id: string;
}

export function InstrumentMetaStrip({ id }: InstrumentMetaStripProps) {
	const query = useInstrumentDetail(id);

	if (query.isLoading) {
		return (
			<div className="flex gap-4 px-4 py-3">
				{LOADING_METRIC_IDS.map((metricId) => (
					<LoadingSkeleton key={metricId} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}
	if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;
	if (!query.data) {
		return <div className="px-4 py-5 text-sm text-(--color-foreground-tertiary)">标的 ID 无效或身份不可用</div>;
	}

	const instrument = query.data;
	return (
		<div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
			<div className="min-w-48">
				<div className="text-lg font-bold text-(--color-foreground)">{instrument.name}</div>
				<div className="font-mono text-xs text-(--color-foreground-tertiary)">
					{instrument.ticker} · {instrument.exchange}
				</div>
			</div>
			<StatusBadge
				variant={instrument.is_active ? "healthy" : "warning"}
				label={instrument.is_active ? "交易中" : "非活跃"}
				size="sm"
			/>
			<div className="flex flex-1 flex-wrap gap-6">
				<Metric variant="strip" label="资产类别" value={instrument.asset_class} />
				<Metric variant="strip" label="交易所" value={instrument.exchange} />
				<Metric variant="strip" label="上市日期" value={instrument.list_date ?? "未报告"} />
				<Metric variant="strip" label="内部 ID" value={String(instrument.instrument_id)} />
			</div>
		</div>
	);
}
