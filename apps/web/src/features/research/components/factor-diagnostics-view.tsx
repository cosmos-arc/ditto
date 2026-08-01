import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ApiError } from "@/lib/api-client";
import type { FactorDiagnosticsScope } from "../api/factor-diagnostics";
import { useFactorDiagnostics } from "../hooks/use-factor-detail";

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

/** 只展示后端已验证的 immutable diagnostics artifact，不从 catalog 合成结果。 */
export function FactorDiagnosticsView({ factorId, scope }: FactorDiagnosticsViewProps) {
	const query = useFactorDiagnostics(factorId, scope);

	if (query.isLoading) return <LoadingSkeleton variant="table" rows={8} />;
	if (query.error) {
		const message =
			query.error instanceof ApiError
				? `${query.error.status} ${query.error.errorCode ?? "FACTOR_DIAGNOSTICS_ERROR"}: ${query.error.message}`
				: query.error.message;
		return (
			<div role="alert" className="flex flex-col gap-2 p-(--density-panel-padding) text-sm text-(--color-led-danger)">
				<p>{message}</p>
				<button type="button" className="self-start underline" onClick={() => void query.refetch()}>
					重试诊断
				</button>
			</div>
		);
	}
	if (!query.data) return null;

	const data = query.data;
	return (
		<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
			<div data-info-level="l2" data-info-unit="factor-diagnostics">
				<ContextSection title="诊断指标" count={Object.keys(data.metrics).length}>
					<dl className="divide-y divide-(--color-border-subtle)">
						{Object.entries(data.metrics).map(([key, value]) => (
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
						<EvidenceRow label="factor" value={data.factorId} />
						<EvidenceRow label="snapshot" value={data.snapshotId} />
						<EvidenceRow label="snapshot hash" value={data.snapshotHash} />
						<EvidenceRow label="window" value={`${data.startDate} → ${data.endDate}`} />
						<EvidenceRow label="registry hash" value={data.registryHash} />
						<EvidenceRow label="artifact" value={data.artifactId} />
						<EvidenceRow label="content hash" value={data.contentHash} />
						{Object.entries(data.provenance).map(([key, value]) => (
							<EvidenceRow key={key} label={`source.${key}`} value={formatValue(value)} />
						))}
					</dl>
				</ContextSection>
			</div>
		</div>
	);
}
