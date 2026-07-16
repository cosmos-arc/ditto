import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useIntelligenceFlow } from "../hooks";

export function IntelligenceFlowView() {
	const { data, isLoading, refetch } = useIntelligenceFlow();

	if (isLoading) {
		return (
			<ContextSection title="资金流向">
				<LoadingSkeleton variant="table" rows={5} columns={3} />
			</ContextSection>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextSection title="资金流向" data-info-level="l1" data-info-unit="intelligence-flow">
				{data && (
					<div className="flex flex-col gap-3">
						<div className="flex flex-col gap-1">
							<span className="text-xs text-(--color-foreground-tertiary)">板块排名</span>
							{data.sectorRankings.map((s) => (
								<div
									key={s.sector}
									className="flex items-center justify-between py-1 border-b border-(--color-border) last:border-b-0"
								>
									<span className="text-sm text-(--color-foreground)">{s.sector}</span>
									<span
										className={`text-sm font-data ${s.netFlow >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}`}
									>
										{s.netFlow > 0 ? "+" : ""}
										{s.netFlow}亿
									</span>
								</div>
							))}
						</div>
						<div className="flex flex-col gap-1">
							<span className="text-xs text-(--color-foreground-tertiary)">北向资金（亿元）</span>
							{data.northbound.slice(0, 3).map((n) => (
								<div key={n.date} className="flex items-center justify-between py-0.5">
									<span className="text-xs text-(--color-foreground-tertiary) font-data">{n.date}</span>
									<span
										className={`text-sm font-data ${n.total >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}`}
									>
										{n.total}
									</span>
								</div>
							))}
						</div>
					</div>
				)}
			</ContextSection>
		</DittoErrorBoundary>
	);
}
