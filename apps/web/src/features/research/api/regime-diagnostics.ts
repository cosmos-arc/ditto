import { apiClient } from "@/api";
import type { components, operations } from "@/api/generated/schema";

export type RegimeDiagnosticsDto = components["schemas"]["RegimeDiagnosticsResponse"];
type RegimeObservationDto = components["schemas"]["RegimeObservationResponse"];
type RegimeQuery = operations["market_get_regime"]["parameters"]["query"];

export type RegimeLabel = RegimeObservationDto["label"];

export interface RegimeDiagnosticsScope {
	readonly snapshotId: string;
	readonly snapshotManifestHash: string;
	readonly benchmarkInstrumentId: number;
	readonly startDate: string;
	readonly endDate: string;
	readonly knowledgeCutoff: string;
}

export interface RegimeIndicatorValue {
	readonly name: string;
	readonly normalizedScore: number;
}

export interface RegimeObservation {
	readonly observedAt: string;
	readonly score: number;
	readonly label: RegimeLabel;
	readonly positionRatio: number;
	readonly indicators: readonly RegimeIndicatorValue[];
}

export interface RegimeTransition {
	readonly observedAt: string;
	readonly fromLabel: RegimeLabel;
	readonly toLabel: RegimeLabel;
}

export interface RegimeDiagnostics {
	readonly scope: RegimeDiagnosticsScope;
	readonly datasetId: string;
	readonly sourceSnapshotIds: readonly string[];
	readonly builderVersion: string;
	readonly knownAtPolicy: string;
	readonly modelId: string;
	readonly lookbackObservations: number;
	readonly bearThreshold: number;
	readonly bullThreshold: number;
	readonly barsInputId: string;
	readonly barsContentHash: string;
	readonly barsSchemaHash: string;
	readonly current: RegimeObservation;
	readonly observations: readonly RegimeObservation[];
	readonly transitions: readonly RegimeTransition[];
}

function mapObservation(dto: RegimeObservationDto): RegimeObservation {
	return {
		observedAt: dto.observed_at,
		score: dto.score,
		label: dto.label,
		positionRatio: dto.position_ratio,
		indicators: dto.indicators.map((indicator) => ({
			name: indicator.name,
			normalizedScore: indicator.normalized_score,
		})),
	};
}

function mapDiagnostics(dto: RegimeDiagnosticsDto): RegimeDiagnostics {
	return {
		scope: {
			snapshotId: dto.snapshot_id,
			snapshotManifestHash: dto.snapshot_manifest_hash,
			benchmarkInstrumentId: dto.benchmark_instrument_id,
			startDate: dto.start_date,
			endDate: dto.end_date,
			knowledgeCutoff: dto.knowledge_cutoff,
		},
		datasetId: dto.dataset_id,
		sourceSnapshotIds: dto.source_snapshot_ids,
		builderVersion: dto.builder_version,
		knownAtPolicy: dto.known_at_policy,
		modelId: dto.model_id,
		lookbackObservations: dto.lookback_observations,
		bearThreshold: dto.bear_threshold,
		bullThreshold: dto.bull_threshold,
		barsInputId: dto.bars_input_id,
		barsContentHash: dto.bars_content_hash,
		barsSchemaHash: dto.bars_schema_hash,
		current: mapObservation(dto.current),
		observations: dto.observations.map(mapObservation),
		transitions: dto.transitions.map((transition) => ({
			observedAt: transition.observed_at,
			fromLabel: transition.from_label,
			toLabel: transition.to_label,
		})),
	};
}

export async function fetchRegimeDiagnostics(scope: RegimeDiagnosticsScope): Promise<RegimeDiagnostics> {
	const query: RegimeQuery = {
		snapshot_id: scope.snapshotId,
		snapshot_manifest_hash: scope.snapshotManifestHash,
		benchmark_instrument_id: scope.benchmarkInstrumentId,
		start_date: scope.startDate,
		end_date: scope.endDate,
		knowledge_cutoff: scope.knowledgeCutoff,
	};
	return mapDiagnostics(await apiClient.get("/api/v1/market/regime", { params: { query } }));
}
