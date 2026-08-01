import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components, operations } from "@/types/generated/api";

type FactorDiagnosticsOperation = operations["design_research_factor_diagnostics"];
type FactorDiagnosticsPath = FactorDiagnosticsOperation["parameters"]["path"];
type FactorDiagnosticsQuery = FactorDiagnosticsOperation["parameters"]["query"];
export type FactorDiagnosticsResponse = components["schemas"]["FactorDiagnosticsResponse"];

export type FactorDiagnosticsScope = {
	readonly snapshotId: string;
	readonly startDate: string;
	readonly endDate: string;
	readonly registryHash: string;
};

export type FactorDiagnostics = {
	readonly factorId: string;
	readonly snapshotId: string;
	readonly snapshotHash: string;
	readonly registryHash: string;
	readonly startDate: string;
	readonly endDate: string;
	readonly provenance: Readonly<Record<string, unknown>>;
	readonly metrics: Readonly<Record<string, unknown>>;
	readonly artifactId: string;
	readonly contentHash: string;
};

/** 按完整 artifact identity 读取一个不可变因子诊断。 */
export function fetchFactorDiagnostics(
	factorId: FactorDiagnosticsPath["factor_id"],
	scope: FactorDiagnosticsScope,
): Promise<FactorDiagnosticsResponse> {
	const query: FactorDiagnosticsQuery = {
		snapshot_id: scope.snapshotId,
		start_date: scope.startDate,
		end_date: scope.endDate,
		registry_hash: scope.registryHash,
	};
	return apiClient.get<FactorDiagnosticsResponse>(
		withQueryParams(`/v1/research/factors/${encodeURIComponent(factorId)}/diagnostics`, query),
	);
}

export function mapFactorDiagnostics(dto: FactorDiagnosticsResponse): FactorDiagnostics {
	return {
		factorId: dto.factor_id,
		snapshotId: dto.snapshot_id,
		snapshotHash: dto.snapshot_hash,
		registryHash: dto.registry_hash,
		startDate: dto.start_date,
		endDate: dto.end_date,
		provenance: { ...dto.provenance },
		metrics: { ...dto.metrics },
		artifactId: dto.artifact_id,
		contentHash: dto.content_hash,
	};
}
