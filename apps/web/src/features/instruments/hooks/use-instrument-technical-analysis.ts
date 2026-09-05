import { useQuery } from "@tanstack/react-query";
import { type InstrumentIdentity, parseInstrumentId } from "../api/instrument-workspace";
import {
	queryTechnicalAnalysis,
	type TechnicalAnalysisQueryBody,
	type TechnicalAnalysisSpecRequest,
} from "../api/technical-analysis";
import { instrumentKeys, useInstrumentDetail } from "./use-instrument-workspace";

export interface InstrumentTechnicalSelectionCandidate {
	readonly factor_contributions: readonly {
		readonly contribution: number;
		readonly factor_name: string;
	}[];
	readonly instrument_id: number;
	readonly instrument_name: string;
	readonly rank: number;
	readonly score: number;
}

export interface InstrumentTechnicalSelectionExclusion {
	readonly detail: string;
	readonly instrument_id: number;
	readonly instrument_name: string;
	readonly reason_code: string;
	readonly stage: string;
}

export interface InstrumentTechnicalSelectionRun {
	readonly as_of: string;
	readonly candidates: readonly InstrumentTechnicalSelectionCandidate[];
	readonly exclusions: readonly InstrumentTechnicalSelectionExclusion[];
	readonly knowledge_cutoff: string;
	readonly publication_cutoff: string;
	readonly run_id: string;
}

export interface InstrumentTechnicalDependencies {
	readonly fetchSourceEvidence: (
		datasetId: string,
		profile: string,
	) => Promise<{ readonly snapshot_ids: readonly string[] }>;
	readonly getSelectionRun: (runId: string) => Promise<InstrumentTechnicalSelectionRun>;
	readonly selectionRunKey: (runId: string) => readonly unknown[];
}

const V1_SPEC = {
	algorithm_version: "technical-analysis.v1",
	atr_window: 14,
	donchian_window: 20,
	macd_fast: 12,
	macd_signal: 9,
	macd_slow: 26,
	return_window: 20,
	rsi_window: 14,
	slope_window: 5,
	spec_id: "technical-analysis-core",
	spec_version: "1",
	support_resistance_window: 60,
	timeframes: ["daily", "weekly"],
	trend_window: 20,
	volatility_window: 20,
	volume_window: 20,
} as const satisfies TechnicalAnalysisSpecRequest;

function instrumentCode(identity: InstrumentIdentity): string {
	const exchangeSuffix = { BSE: "BJ", SSE: "SH", SZSE: "SZ" }[identity.exchange] ?? identity.exchange;
	return `${identity.ticker}.${exchangeSuffix}`;
}

export function useInstrumentTechnicalAnalysis(
	id: string,
	selectionRunId: string | undefined,
	dependencies: InstrumentTechnicalDependencies,
) {
	const identity = useInstrumentDetail(id);
	const selection = useQuery({
		queryKey: dependencies.selectionRunKey(selectionRunId ?? "none"),
		queryFn: () => dependencies.getSelectionRun(selectionRunId ?? ""),
		enabled: Boolean(selectionRunId),
		staleTime: Number.POSITIVE_INFINITY,
	});

	let instrumentId: number | null = null;
	try {
		instrumentId = parseInstrumentId(id);
	} catch {
		instrumentId = null;
	}
	const candidate = selection.data?.candidates.find((item) => item.instrument_id === instrumentId) ?? null;
	const exclusion = selection.data?.exclusions.find((item) => item.instrument_id === instrumentId) ?? null;
	const sourceEvidence = useQuery({
		queryKey: [...instrumentKeys.all, id, "technical-source-evidence", identity.data?.asset_class ?? "unknown"],
		queryFn: () =>
			dependencies.fetchSourceEvidence(
				identity.data?.asset_class === "etf" ? "etf_daily" : "stock_daily",
				"technical_daily",
			),
		enabled: Boolean(identity.data && selection.data && (candidate || exclusion)),
		staleTime: Number.POSITIVE_INFINITY,
	});
	const body: TechnicalAnalysisQueryBody | null =
		identity.data &&
		selection.data &&
		instrumentId !== null &&
		(candidate || exclusion) &&
		sourceEvidence.data?.snapshot_ids.length
			? {
					as_of: selection.data.as_of,
					instrument_code: instrumentCode(identity.data),
					instrument_id: instrumentId,
					instrument_name: candidate?.instrument_name ?? exclusion?.instrument_name ?? identity.data.name,
					knowledge_cutoff: selection.data.knowledge_cutoff,
					portfolio_snapshot_id: null,
					publication_cutoff: selection.data.publication_cutoff,
					research_case_id: null,
					selection_run_id: selection.data.run_id,
					source_snapshot_ids: [...sourceEvidence.data.snapshot_ids],
					spec: V1_SPEC,
				}
			: null;

	const analysis = useQuery({
		queryKey: [...instrumentKeys.all, id, "technical-analysis", selectionRunId ?? "none", body],
		queryFn: () => {
			if (!body) throw new Error("technical analysis requires an exact SelectionRun context");
			return queryTechnicalAnalysis(body);
		},
		enabled: body !== null,
		staleTime: Number.POSITIVE_INFINITY,
	});

	return { analysis, candidate, exclusion, identity, selection, sourceEvidence };
}
