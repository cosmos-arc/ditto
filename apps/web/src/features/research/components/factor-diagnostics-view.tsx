import { ApiError } from "@/api/errors";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { useFactorDiagnostics } from "../hooks/use-factor-detail";
import { FactorSeriesCharts } from "./factor-series-charts";

interface FactorDiagnosticsViewProps {
	readonly factorId: string;
	readonly scope: FactorDiagnosticsScope;
}

function formatValue(value: unknown): string {
	if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
	return JSON.stringify(value);
}

function EvidenceRow({ label, value }: { readonly label: string; readonly value: string }) {
	return (
		<div className="grid gap-1 py-1 text-xs sm:grid-cols-[9rem_1fr]">
			<dt className="text-(--color-foreground-tertiary)">{label}</dt>
			<dd className="font-data break-all text-(--color-foreground-secondary)">{value}</dd>
		</div>
	);
}

/** 图表走查询时序列（仅依赖窗口）；不可变诊断制品独立加载（404 = 无实验证据的诚实空态）。 */
export function FactorDiagnosticsView({ factorId, scope }: FactorDiagnosticsViewProps) {
	const query = useFactorDiagnostics(factorId, scope);

	const artifactSection = query.isLoading ? (
		<LoadingSkeleton variant="table" rows={4} />
	) : query.error ? (
		<div
			data-state="diagnostics-unavailable"
			className="rounded-(--radius-md) border border-(--color-border-subtle) p-4 text-xs"
		>
			<p role="alert" className="text-(--color-foreground-secondary)">
				{query.error instanceof ApiError
					? `${query.error.status} ${query.error.errorCode ?? "FACTOR_DIAGNOSTICS_ERROR"}: ${query.error.message}`
					: query.error.message}
			</p>
			<p className="mt-1 text-(--color-foreground-tertiary)">
				该 scope 没有不可变诊断制品（无实验证据）；上方图表为查询时计算，不受影响。
			</p>
			<button type="button" className="mt-2 underline" onClick={() => void query.refetch()}>
				重试诊断
			</button>
		</div>
	) : query.data ? (
		<>
			<div data-info-level="l2" data-info-unit="factor-diagnostics">
				<ContextSection title="诊断指标" count={Object.keys(query.data.metrics).length}>
					<dl className="divide-y divide-(--color-border-subtle)">
						{Object.entries(query.data.metrics).map(([key, value]) => (
							<div key={key} data-info-level="l3" data-info-unit="diagnostic-item">
								<EvidenceRow label={key} value={formatValue(value)} />
							</div>
						))}
					</dl>
				</ContextSection>
			</div>
			<div data-info-level="l2" data-info-unit="factor-provenance">
				<ContextSection title="Provenance">
					<dl className="divide-y divide-(--color-border-subtle)">
						<EvidenceRow label="factor" value={query.data.factorId} />
						<EvidenceRow label="snapshot" value={query.data.snapshotId} />
						<EvidenceRow label="snapshot hash" value={query.data.snapshotHash} />
						<EvidenceRow label="window" value={`${query.data.startDate} → ${query.data.endDate}`} />
						<EvidenceRow label="registry hash" value={query.data.registryHash} />
						<EvidenceRow label="artifact" value={query.data.artifactId} />
						<EvidenceRow label="content hash" value={query.data.contentHash} />
						{Object.entries(query.data.provenance).map(([key, value]) => (
							<EvidenceRow key={key} label={`source.${key}`} value={formatValue(value)} />
						))}
					</dl>
				</ContextSection>
			</div>
		</>
	) : null;

	return (
		<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
			<div data-info-level="l2" data-info-unit="factor-series">
				<ContextSection title="研究图表" count={3}>
					<p className="mb-3 text-xs text-(--color-foreground-tertiary)">
						IC/滚动 IR、分位分层与多空 spread、月度 IC 热力图——查询时按同一评估函数族计算；
						不可变诊断制品仅含窗口级标量。
					</p>
					<FactorSeriesCharts endDate={scope.endDate} factorId={factorId} startDate={scope.startDate} />
				</ContextSection>
			</div>
			{artifactSection}
		</div>
	);
}
