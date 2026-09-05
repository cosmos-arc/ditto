import { HttpResponse, http, type RequestHandler } from "msw";
import { mockExperimentSummaryList } from "../fixtures/experiment-live";
import {
	mockExperimentArtifacts,
	mockExperimentComparison,
	mockExperimentDetail,
	mockExperimentGates,
	mockExperimentSelectionEvidence,
} from "../fixtures/experiment-workbench";
import { mockFactorCatalog } from "../fixtures/factor-catalog-live";
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
	http.get("/api/v1/research/experiments/:experimentId", () => HttpResponse.json({ data: mockExperimentDetail })),
	http.get("/api/v1/research/experiments/:experimentId/candidates", () =>
		HttpResponse.json({ data: mockExperimentDetail.candidates }),
	),
	http.get("/api/v1/research/experiments/:experimentId/gates", () => HttpResponse.json({ data: mockExperimentGates })),
	http.get("/api/v1/research/experiments/:experimentId/comparison", () =>
		HttpResponse.json({ data: mockExperimentComparison }),
	),
	http.get("/api/v1/research/experiments/:experimentId/artifacts", () =>
		HttpResponse.json({ data: mockExperimentArtifacts }),
	),
	http.get("/api/v1/research/experiments/:experimentId/selection-evidence", () =>
		HttpResponse.json({ data: mockExperimentSelectionEvidence }),
	),
	http.post("/api/v1/research/experiments/:experimentId/:action", async ({ params, request }) => {
		if (!new Set(["pause", "cancel", "resume", "retry-fold"]).has(String(params["action"]))) return undefined;
		const body = (await request.json()) as { expected_revision?: number };
		return HttpResponse.json({
			data: {
				experiment_id: String(params["experimentId"]),
				status: String(params["action"]),
				desired_state: String(params["action"]),
				revision: (body.expected_revision ?? mockExperimentDetail.revision) + 1,
				live_run_ids: [],
				occurred_at: "2026-08-01T00:00:00Z",
			},
		});
	}),
	http.post("/api/v1/research/experiments/:experimentId/candidate-selection", async ({ params, request }) => {
		const body = (await request.json()) as {
			candidate_id: string;
			comparison_payload_hash: string;
			expected_revision: number;
		};
		return HttpResponse.json({
			data: {
				selection_id: "selection-mock-1",
				experiment_id: String(params["experimentId"]),
				candidate_id: body.candidate_id,
				comparison_payload_hash: body.comparison_payload_hash,
				candidate_evidence_artifact_id: "candidate-bundle-2",
				candidate_evidence_content_hash: "2".repeat(64),
				selection_evidence_content_hash: mockExperimentSelectionEvidence.content_hash,
				revision: body.expected_revision + 1,
				event_id: "event-selection-mock-1",
				occurred_at: "2026-08-01T00:00:00Z",
			},
		});
	}),
	http.post("/api/v1/research/experiments/:experimentId/holdout-evaluations", async ({ params, request }) => {
		const body = (await request.json()) as {
			candidate_id: string;
			selection_id: string;
			expected_revision: number;
			expected_candidate_evidence_content_hash: string;
			expected_selection_evidence_hash: string;
		};
		return HttpResponse.json({
			data: {
				selection_id: body.selection_id,
				claim_id: "claim-mock-1",
				experiment_id: String(params["experimentId"]),
				candidate_id: body.candidate_id,
				fold_id: "holdout",
				logical_run_id: "run-holdout-mock-1",
				reproduction_fingerprint: "9".repeat(64),
				candidate_evidence_content_hash: body.expected_candidate_evidence_content_hash,
				selection_evidence_content_hash: body.expected_selection_evidence_hash,
				claim_payload_hash: "8".repeat(64),
				revision: body.expected_revision + 1,
				event_id: "event-holdout-mock-1",
				occurred_at: "2026-08-01T00:01:00Z",
				state: "claimed",
			},
		});
	}),
	http.get("/api/v1/research/candidates/:candidateId/selections", ({ params, request }) => {
		const experimentId = new URL(request.url).searchParams.get("experiment_id") ?? "exp-1042";
		return HttpResponse.json({
			data: {
				candidate_id: String(params["candidateId"]),
				experiment_id: experimentId,
				artifact_id: "candidate-bundle-2",
				content_hash: "2".repeat(64),
				items: [
					{
						fold_id: "fold-1",
						validation_fold_ordinal: 1,
						trade_date: "2021-01-04",
						instrument_id: "000001",
						rank: 1,
						score: 0.9,
						selected: true,
						evidence_hash: "a".repeat(64),
					},
				],
				next_cursor: null,
			},
		});
	}),
	http.get("/api/v1/research/candidates/:candidateId/exclusions", ({ params, request }) => {
		const experimentId = new URL(request.url).searchParams.get("experiment_id") ?? "exp-1042";
		return HttpResponse.json({
			data: {
				candidate_id: String(params["candidateId"]),
				experiment_id: experimentId,
				artifact_id: "candidate-bundle-2",
				content_hash: "2".repeat(64),
				items: [],
				next_cursor: null,
			},
		});
	}),
	http.get("/api/v1/research/candidates/:candidateId/factor-contributions", ({ params, request }) => {
		const experimentId = new URL(request.url).searchParams.get("experiment_id") ?? "exp-1042";
		return HttpResponse.json({
			data: {
				candidate_id: String(params["candidateId"]),
				experiment_id: experimentId,
				artifact_id: "candidate-bundle-2",
				content_hash: "2".repeat(64),
				items: [
					{
						fold_id: "fold-1",
						validation_fold_ordinal: 1,
						trade_date: "2021-01-04",
						instrument_id: "000001",
						factor_id: "momentum",
						rank: 1,
						selected: true,
						contribution: 0.12,
						evidence_hash: "c".repeat(64),
					},
				],
				next_cursor: null,
			},
		});
	}),

	http.get("/api/v1/research/factors/:factorId/diagnostics", ({ params, request }) => {
		const query = new URL(request.url).searchParams;
		return HttpResponse.json({
			data: {
				factor_id: String(params["factorId"]),
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
	http.get("/api/v1/research/factors", () => HttpResponse.json({ data: mockFactorCatalog })),

	// === R3 review queue + review-packet live-shape（generated DTO + {data} 信封）===
	http.get("/api/v1/research/reviews", () => HttpResponse.json({ data: mockReviewQueue })),
	http.get("/api/v1/research/experiments/:experimentId/review-packet", ({ params }) => {
		const experimentId = String(params["experimentId"]);
		if (experimentId !== mockReviewPacket.experiment_id) {
			return new HttpResponse(null, { status: 404 });
		}
		return HttpResponse.json({ data: mockReviewPacket });
	}),
];
