import { HttpResponse, http, type RequestHandler } from "msw";
import { mockExperimentSummaryList } from "../fixtures/experiment-live";
import {
	mockExperiments,
	mockFactorAnalysis,
	mockFactorDetail,
	mockFactors,
	mockReviewQueue as mockPrototypeReviewQueue,
	mockResearchPulse,
	mockResearchRuns,
} from "../fixtures/research";
import { mockReviewPacket, mockReviewQueue } from "../fixtures/review-live";

export const researchHandlers: RequestHandler[] = [
	http.get("/api/research/pulse", () => {
		return HttpResponse.json(mockResearchPulse);
	}),

	http.get("/api/factors", ({ request }) => {
		const url = new URL(request.url);
		const page = Number(url.searchParams.get("page") ?? 1);
		const pageSize = Number(url.searchParams.get("pageSize") ?? 20);
		const start = (page - 1) * pageSize;
		const items = mockFactors.items.slice(start, start + pageSize);

		return HttpResponse.json({
			items,
			total: mockFactors.total,
			page,
			pageSize,
		});
	}),

	http.get("/api/factors/:id", () => {
		return HttpResponse.json(mockFactorDetail);
	}),

	http.get("/api/factors/:id/analysis", () => {
		return HttpResponse.json(mockFactorAnalysis);
	}),

	http.get("/api/research/runs", () => {
		return HttpResponse.json(mockResearchRuns);
	}),

	http.get("/api/research/experiments", () => {
		return HttpResponse.json(mockExperiments);
	}),

	http.get("/api/research/review-queue", () => {
		return HttpResponse.json(mockPrototypeReviewQueue);
	}),

	// === R3 live-shape handler（/api/v1/research/experiments，generated DTO + {data} 信封）===
	http.get("/api/v1/research/experiments", () =>
		HttpResponse.json({
			data: mockExperimentSummaryList,
			pagination: { total: mockExperimentSummaryList.length, limit: 50, offset: 0, has_more: false },
		}),
	),
	http.post("/api/v1/research/experiments/:experimentId/preflight", () =>
		HttpResponse.json({
			data: {
				status: "ready",
				plan_hash: "d".repeat(64),
				checks: [],
				candidate_count: 3,
				planned_fold_count: 12,
				budget_run_count: 12,
				estimated_trading_sessions: 2048,
				estimated_disk_bytes: 4096,
				eligible_month_count: 96,
				isolation_width_sessions: 6,
			},
		}),
	),
	http.post("/api/v1/research/experiments", async ({ request }) => {
		const body = (await request.json()) as { experiment_id?: string; confirmed_plan_hash?: string };
		return HttpResponse.json({
			data: {
				experiment_id: body.experiment_id ?? "r3-experiment",
				status: "queued",
				queue_ordinal: 1,
				revision: 1,
				plan_hash: body.confirmed_plan_hash ?? "d".repeat(64),
				candidate_count: 3,
				fold_count: 12,
			},
		});
	}),

	http.get("/api/v1/research/factors/:factorId/diagnostics", ({ params, request }) => {
		const query = new URL(request.url).searchParams;
		return HttpResponse.json({
			data: {
				factor_id: String(params.factorId),
				snapshot_id: query.get("snapshot_id") ?? "snapshot-r3",
				snapshot_hash: "a".repeat(64),
				registry_hash: query.get("registry_hash") ?? "f".repeat(64),
				start_date: query.get("start_date") ?? "2024-01-01",
				end_date: query.get("end_date") ?? "2024-12-31",
				provenance: { dataset_id: "stock_daily" },
				metrics: { coverage: 0.97, rank_ic: 0.08 },
				artifact_id: "factor-diagnostic-1",
				content_hash: "c".repeat(64),
			},
		});
	}),

	// === R3 review queue + review-packet live-shape（generated DTO + {data} 信封）===
	http.get("/api/v1/research/reviews", () => HttpResponse.json({ data: mockReviewQueue })),
	http.get("/api/v1/research/experiments/:experimentId/review-packet", ({ params }) => {
		const experimentId = String(params.experimentId);
		if (experimentId !== mockReviewPacket.experiment_id) {
			return new HttpResponse(null, { status: 404 });
		}
		return HttpResponse.json({ data: mockReviewPacket });
	}),
];
