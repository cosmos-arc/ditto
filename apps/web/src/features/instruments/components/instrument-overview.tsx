import { useInstrumentFundamentals } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

interface InstrumentOverviewProps {
	readonly id: string;
}

export function InstrumentOverview({ id }: InstrumentOverviewProps) {
	const { data, isLoading, refetch } = useInstrumentFundamentals(id);

	return (
		<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
			<div data-info-level="l2" data-info-unit="financial-statements">
				<ContextSection title="财务报表">
					{isLoading && <LoadingSkeleton variant="table" rows={4} />}
					<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
						{data && (
							<div className="space-y-1">
								{data.income.map((stmt) => (
									<div
										key={stmt.period}
										data-info-level="l3"
										data-info-unit="income-statement-item"
										className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<span className="font-medium">{stmt.period}</span>
										<div className="flex gap-4 text-(--color-foreground-tertiary)">
											<span>营收 {stmt.revenue.toLocaleString()}万</span>
											<span>净利润 {stmt.netProfit.toLocaleString()}万</span>
											<span>毛利率 {stmt.grossMargin.toFixed(1)}%</span>
											<span>净利率 {stmt.netMargin.toFixed(1)}%</span>
										</div>
									</div>
								))}
							</div>
						)}
					</DittoErrorBoundary>
				</ContextSection>
			</div>

			<div data-info-level="l2" data-info-unit="fundamentals">
				<ContextSection title="基本面">
					{isLoading && <LoadingSkeleton variant="table" rows={5} />}
					<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
						{data && (
							<div className="grid grid-cols-2 gap-4">
								<div className="space-y-1">
									{data.ratios.map((r) => (
										<div
											key={r.name}
											data-info-level="l3"
											data-info-unit="fundamental-ratio-item"
											className="flex items-center justify-between rounded-md px-3 py-2 text-sm"
										>
											<span className="text-(--color-foreground-tertiary)">{r.name}</span>
											<span className="font-medium">{r.value.toFixed(2)}</span>
										</div>
									))}
								</div>
								<div className="space-y-1">
									{data.peers.map((p) => (
										<div
											key={p.code}
											data-info-level="l3"
											data-info-unit="peer-comparison-item"
											className="flex items-center justify-between rounded-md px-3 py-2 text-sm"
										>
											<span className="font-medium">{p.name}</span>
											<div className="flex gap-3 text-(--color-foreground-tertiary)">
												<span>PE {p.pe.toFixed(1)}</span>
												<span>PB {p.pb.toFixed(1)}</span>
											</div>
										</div>
									))}
								</div>
							</div>
						)}
					</DittoErrorBoundary>
				</ContextSection>
			</div>
		</div>
	);
}
