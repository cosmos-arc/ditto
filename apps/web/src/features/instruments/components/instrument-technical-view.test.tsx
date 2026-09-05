import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { selectionRunFixtures } from "@/mocks/fixtures/selection";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";
import { selectionHandlers } from "@/mocks/handlers/selection";
import { server } from "@/mocks/server";
import { InstrumentTechnicalView } from "@/workflows/instrument-analysis";
import type { TechnicalAnalysisQueryBody, TechnicalAnalysisSnapshot } from "../api/technical-analysis";

const run = selectionRunFixtures[0];
const certifiedTechnicalSnapshotId = `snapshot:tushare:stock_daily:sha256:${"9".repeat(64)}`;
let receivedBody: TechnicalAnalysisQueryBody | null = null;

const snapshot = {
	as_of: run.as_of,
	conflicts: [{ daily: "bullish", dimension: "trend", reason_code: "daily_weekly_disagreement", weekly: "bearish" }],
	input_hash: "e".repeat(64),
	instrument_id: 600519,
	instrument_name: "贵州茅台",
	knowledge_cutoff: run.knowledge_cutoff,
	last_computed_bar_at: "2026-08-31T07:00:00Z",
	last_visible_bar_at: "2026-08-31T07:00:00Z",
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
	portfolio_snapshot_id: null,
	publication_cutoff: run.publication_cutoff,
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
	research_case_id: null,
	selection_run_id: run.run_id,
	snapshot_id: `technical-analysis:sha256:${"f".repeat(64)}`,
	source_snapshot_ids: [...run.source_snapshot_ids],
	spec_hash: "a".repeat(64),
	status: "ready",
	timeframe_summaries: [
		{ breakout: "neutral", momentum: "bullish", timeframe: "daily", trend: "bullish" },
		{ breakout: "neutral", momentum: "neutral", timeframe: "weekly", trend: "bearish" },
	],
	warnings: [],
} satisfies TechnicalAnalysisSnapshot;

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => {
	receivedBody = null;
	server.use(
		...instrumentsHandlers,
		...selectionHandlers,
		http.get("/api/v1/data-products/stock_daily/evidence", ({ request }) => {
			expect(new URL(request.url).searchParams.get("profile")).toBe("technical_daily");
			return HttpResponse.json({
				data: {
					content_hash: "8".repeat(64),
					dataset_id: "stock_daily",
					fallback_history: [],
					override_history: [],
					profile: "technical_daily",
					report_id: `certification:${"7".repeat(64)}`,
					schema_versions: ["market.stock_daily.v1"],
					snapshot_ids: [certifiedTechnicalSnapshotId],
					source_ids: ["tushare"],
				},
			});
		}),
		http.post("/api/v1/technical-analysis/snapshots/query", async ({ request }) => {
			receivedBody = (await request.json()) as TechnicalAnalysisQueryBody;
			return HttpResponse.json({
				data: {
					...snapshot,
					instrument_id: receivedBody.instrument_id,
					instrument_name: receivedBody.instrument_name,
					source_snapshot_ids: receivedBody.source_snapshot_ids,
				},
			});
		}),
	);
});

describe("InstrumentTechnicalView", () => {
	it("binds the exact SelectionRun context and renders auditable technical evidence", async () => {
		const onSnapshotIdentity = vi.fn();
		render(
			<InstrumentTechnicalView id="600519" onSnapshotIdentity={onSnapshotIdentity} selectionRunId={run.run_id} />,
			{ wrapper: wrapper() },
		);

		await expect(screen.findByText("技术证据快照")).resolves.toBeInTheDocument();
		expect(screen.getByText("#1")).toBeInTheDocument();
		expect(screen.getByText("0.7800")).toBeInTheDocument();
		expect(screen.getByText("1,718.00")).toBeInTheDocument();
		expect(screen.getByText("日线 / 周线冲突")).toBeInTheDocument();
		expect(screen.getByText("technical-indicator-registry.v1")).toBeInTheDocument();

		await waitFor(() => {
			expect(onSnapshotIdentity).toHaveBeenLastCalledWith(snapshot.snapshot_id);
			expect(receivedBody).toMatchObject({
				as_of: run.as_of,
				instrument_code: "600519.SH",
				instrument_id: 600519,
				knowledge_cutoff: run.knowledge_cutoff,
				publication_cutoff: run.publication_cutoff,
				selection_run_id: run.run_id,
				source_snapshot_ids: [certifiedTechnicalSnapshotId],
			});
		});
	});

	it("fails closed when no exact snapshot-bearing context is supplied", () => {
		render(<InstrumentTechnicalView id="600519" selectionRunId={undefined} />, { wrapper: wrapper() });

		expect(screen.getByText("需要精确证据上下文")).toBeInTheDocument();
		expect(receivedBody).toBeNull();
	});

	it("keeps excluded SelectionRun members connected to certified technical evidence", async () => {
		server.use(
			http.get("/api/v1/metadata/instruments/600001", () =>
				HttpResponse.json({
					data: {
						asset_class: "stock",
						exchange: "SSE",
						instrument_id: 600001,
						is_active: false,
						list_date: "1998-01-22",
						name: "邯郸钢铁",
						ticker: "600001",
					},
				}),
			),
		);

		render(<InstrumentTechnicalView id="600001" selectionRunId={run.run_id} />, { wrapper: wrapper() });

		await expect(screen.findByText("技术证据快照")).resolves.toBeInTheDocument();
		expect(screen.getByText("insufficient_liquidity")).toBeInTheDocument();
		expect(screen.getByText("average_turnover below 20000000")).toBeInTheDocument();
		await waitFor(() => {
			expect(receivedBody).toMatchObject({
				instrument_id: 600001,
				instrument_name: "邯郸钢铁",
				source_snapshot_ids: [certifiedTechnicalSnapshotId],
			});
		});
	});

	it("uses the exact technical profile for ETF technical evidence", async () => {
		const etfSnapshotId = `snapshot:tushare:etf_daily:sha256:${"6".repeat(64)}`;
		server.use(
			http.get("/api/v1/metadata/instruments/2001724", () =>
				HttpResponse.json({
					data: {
						asset_class: "etf",
						exchange: "SSE",
						instrument_id: 2001724,
						is_active: true,
						list_date: "2013-07-29",
						name: "华安易富黄金ETF",
						ticker: "518880",
					},
				}),
			),
			http.get("/api/v1/selections/runs/:runId", () =>
				HttpResponse.json({
					data: {
						...run,
						asset_kind: "etf",
						candidates: [
							{
								...run.candidates[0],
								instrument_id: 2001724,
								instrument_name: "华安易富黄金ETF",
							},
						],
						exclusions: [],
					},
				}),
			),
			http.get("/api/v1/data-products/etf_daily/evidence", ({ request }) => {
				expect(new URL(request.url).searchParams.get("profile")).toBe("technical_daily");
				return HttpResponse.json({
					data: {
						content_hash: "5".repeat(64),
						dataset_id: "etf_daily",
						fallback_history: [],
						override_history: [],
						profile: "technical_daily",
						report_id: `certification:${"4".repeat(64)}`,
						schema_versions: ["etf.daily.v1"],
						snapshot_ids: [etfSnapshotId],
						source_ids: ["tushare"],
					},
				});
			}),
			http.post("/api/v1/technical-analysis/snapshots/query", async ({ request }) => {
				receivedBody = (await request.json()) as TechnicalAnalysisQueryBody;
				return HttpResponse.json({
					data: {
						...snapshot,
						instrument_id: receivedBody.instrument_id,
						instrument_name: receivedBody.instrument_name,
						source_snapshot_ids: receivedBody.source_snapshot_ids,
					},
				});
			}),
		);

		render(<InstrumentTechnicalView id="2001724" selectionRunId={run.run_id} />, { wrapper: wrapper() });

		await expect(screen.findByText("技术证据快照")).resolves.toBeInTheDocument();
		await waitFor(() => {
			expect(receivedBody).toMatchObject({
				instrument_code: "518880.SH",
				instrument_id: 2001724,
				source_snapshot_ids: [etfSnapshotId],
			});
		});
	});

	it("renders the exact reasons when a technical snapshot is degraded", async () => {
		server.use(
			http.post("/api/v1/technical-analysis/snapshots/query", async ({ request }) => {
				receivedBody = (await request.json()) as TechnicalAnalysisQueryBody;
				return HttpResponse.json({
					data: {
						...snapshot,
						missing_inputs: ["daily:relative_return_benchmark:missing_reference_series"],
						status: "degraded",
					},
				});
			}),
		);

		render(<InstrumentTechnicalView id="600519" selectionRunId={run.run_id} />, { wrapper: wrapper() });

		await expect(screen.findByText("MISSING INPUTS")).resolves.toBeInTheDocument();
		expect(screen.getByText("daily:relative_return_benchmark:missing_reference_series")).toBeInTheDocument();
	});
});
