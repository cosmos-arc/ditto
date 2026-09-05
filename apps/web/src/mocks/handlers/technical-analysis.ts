import { HttpResponse, http } from "msw";
import type {
	TechnicalAnalysisQueryBody as QueryBody,
	TechnicalAnalysisSnapshot as Snapshot,
} from "@/features/instruments/api/technical-analysis";

export const technicalAnalysisHandlers = [
	http.post("/api/v1/technical-analysis/snapshots/query", async ({ request }) => {
		const body = (await request.json()) as QueryBody;
		const snapshot = {
			as_of: body.as_of,
			conflicts: [
				{ daily: "bullish", dimension: "trend", reason_code: "daily_weekly_disagreement", weekly: "bearish" },
			],
			input_hash: "e".repeat(64),
			instrument_id: body.instrument_id,
			instrument_name: body.instrument_name,
			knowledge_cutoff: body.knowledge_cutoff,
			last_computed_bar_at: body.as_of,
			last_visible_bar_at: body.as_of,
			levels: [
				{
					algorithm_version: "support-resistance.v1",
					confidence: 0.82,
					kind: "support",
					price: 1718,
					timeframe: "daily",
					touches: 3,
					window: 60,
				},
				{
					algorithm_version: "support-resistance.v1",
					confidence: 0.74,
					kind: "resistance",
					price: 1808,
					timeframe: "daily",
					touches: 2,
					window: 60,
				},
			],
			missing_inputs: [],
			portfolio_snapshot_id: body.portfolio_snapshot_id ?? null,
			publication_cutoff: body.publication_cutoff,
			readings: [
				{
					indicator_version: "sma.v1",
					name: "sma",
					parameters: [{ name: "window", value: 20 }],
					reason: null,
					status: "ready",
					timeframe: "daily",
					value: 1742.35,
					window: 20,
				},
				{
					indicator_version: "rsi.v1",
					name: "rsi",
					parameters: [{ name: "window", value: 14 }],
					reason: null,
					status: "ready",
					timeframe: "weekly",
					value: 61.24,
					window: 14,
				},
			],
			registry_version: "technical-indicator-registry.v1",
			research_case_id: body.research_case_id ?? null,
			selection_run_id: body.selection_run_id ?? null,
			snapshot_id: `technical-analysis:sha256:${"f".repeat(64)}`,
			source_snapshot_ids: body.source_snapshot_ids,
			spec_hash: "a".repeat(64),
			status: "ready",
			timeframe_summaries: [
				{ breakout: "neutral", momentum: "bullish", timeframe: "daily", trend: "bullish" },
				{ breakout: "neutral", momentum: "neutral", timeframe: "weekly", trend: "bearish" },
			],
			warnings: [],
		} satisfies Snapshot;
		return HttpResponse.json({ data: snapshot });
	}),
];
