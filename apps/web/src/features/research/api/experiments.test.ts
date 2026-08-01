import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import {
	buildExperimentPlanningRequest,
	createDefaultExperimentDraft,
	estimateCandidateCount,
	launchExperiment,
	preflightExperiment,
} from "./experiments";

describe("experiment planning adapter", () => {
	it("builds one complete generated planning request", () => {
		const draft = createDefaultExperimentDraft();
		const request = buildExperimentPlanningRequest(draft);

		expect(request.experiment_id).toBe(draft.experimentId);
		expect(request.strategy.version).toBe(draft.strategyVersion);
		expect(request.snapshot.snapshot_id).toBe(draft.snapshotId);
		expect(request.matrix.candidate_limit).toBe(128);
		expect(request.worker_count).toBe(2);
		expect(request.failure_policy).toBe("continue_candidate_failures");
	});

	it("estimates baseline-only and matrix candidate counts against the 128 ceiling", () => {
		expect(estimateCandidateCount("[]")).toBe(1);
		expect(estimateCandidateCount(createDefaultExperimentDraft().axesJson)).toBe(3);
		expect(estimateCandidateCount("not-json")).toBeNull();
	});

	it("preflights without an idempotency header or launch write", async () => {
		const draft = createDefaultExperimentDraft();
		const planning = buildExperimentPlanningRequest(draft);
		let method = "";
		let idempotency = "absent";
		server.use(
			http.post("/api/v1/research/experiments/:experimentId/preflight", ({ request }) => {
				method = request.method;
				idempotency = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({
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
				});
			}),
		);

		const result = await preflightExperiment(planning);

		expect(method).toBe("POST");
		expect(idempotency).toBe("");
		expect(result.plan_hash).toBe("d".repeat(64));
	});

	it("launches the exact confirmed planning document with Idempotency-Key", async () => {
		const planning = buildExperimentPlanningRequest(createDefaultExperimentDraft());
		let idempotency = "";
		let body: Record<string, unknown> = {};
		server.use(
			http.post("/api/v1/research/experiments", async ({ request }) => {
				idempotency = request.headers.get("Idempotency-Key") ?? "";
				body = (await request.json()) as Record<string, unknown>;
				return HttpResponse.json({
					data: {
						experiment_id: planning.experiment_id,
						status: "queued",
						queue_ordinal: 1,
						revision: 1,
						plan_hash: "d".repeat(64),
						candidate_count: 3,
						fold_count: 12,
					},
				});
			}),
		);

		await launchExperiment(planning, "d".repeat(64), "launch-command-1");

		expect(idempotency).toBe("launch-command-1");
		expect(body.confirmed_plan_hash).toBe("d".repeat(64));
		expect(body.experiment_id).toBe(planning.experiment_id);
	});
});
