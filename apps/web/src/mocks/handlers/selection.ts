import { HttpResponse, http } from "msw";
import type { AssembledSelectionRunResponse, AssembleSelectionRunBody } from "@/features/selection/api";
import {
	researchCaseFixture,
	selectionDiffFixture,
	selectionReceiptFixture,
	selectionRotationFixture,
	selectionRunFixtures,
} from "../fixtures/selection";

export const ASSEMBLED_UNIVERSE_SNAPSHOT_ID = `universe:sha256:${"6".repeat(64)}`;

/** Deterministic assembled facts echoing the submitted policy; mirrors the server's assemble endpoint. */
export function assembledSelectionRunResponse(body: AssembleSelectionRunBody): AssembledSelectionRunResponse {
	return {
		admission: {
			allowed: true,
			fields: [
				{
					allowed_uses: ["formal_research"],
					certification_report_id: "certification-mock",
					consumer_field: "instruments.average_turnover",
					covered_from: "2015-01-05",
					covered_to: body.as_of.slice(0, 10),
					dataset_id: "stock_daily",
					evidence_uri: "mock://evidence/amount",
					field: "amount",
					license_record_id: "license-mock",
					reason_codes: [],
					snapshot_id: "stock-daily:sha256:mock",
					time_precision: "day",
				},
			],
			purpose: "formal_research",
			rule_version: "field-admission-v2",
		},
		request: {
			as_of: body.as_of,
			data_fields: [],
			data_from: "2015-01-05",
			data_to: body.as_of.slice(0, 10),
			industries: [],
			instruments: [
				{ declared_missing_inputs: [], factor_values: [], instrument_id: 600519, instrument_name: "贵州茅台" },
				{ declared_missing_inputs: [], factor_values: [], instrument_id: 300750, instrument_name: "宁德时代" },
			],
			knowledge_cutoff: body.knowledge_cutoff ?? body.as_of,
			market_context_feature_set_id: null,
			membership_version: "sw-l1:mock",
			publication_cutoff: body.publication_cutoff ?? body.as_of,
			rotation_algorithm_version: "industry-rotation-v1",
			rotation_missing_inputs: [],
			rotation_source_snapshot_ids: ["stock-daily:sha256:mock"],
			seed: body.seed,
			selection_source_snapshot_ids: ["stock-daily:sha256:mock"],
			selection_spec: {
				asset_kind: "stock",
				excluded_limit_states: body.excluded_limit_states,
				factor_weights: body.factor_weights,
				min_average_turnover: body.min_average_turnover,
				min_listing_days: body.min_listing_days,
				spec_id: body.spec_id,
				spec_version: body.spec_version,
				top_k: body.top_k,
			},
			universe_snapshot_id: ASSEMBLED_UNIVERSE_SNAPSHOT_ID,
			universe_sources: null,
		},
	};
}

export const selectionHandlers = [
	http.post("/api/v1/selections/admission", () =>
		HttpResponse.json({
			data: {
				allowed: false,
				purpose: "formal_research",
				rule_version: "field-admission-v2",
				fields: [
					{
						dataset_id: "stock_daily",
						field: "amount",
						snapshot_id: "synthetic-snapshot",
						consumer_field: "instruments.average_turnover",
						allowed_uses: [],
						reason_codes: ["FIELD_EVIDENCE_MISSING"],
						license_record_id: null,
						certification_report_id: null,
						covered_from: null,
						covered_to: null,
						time_precision: "unknown",
						evidence_uri: null,
					},
				],
			},
		}),
	),
	http.get("/api/v1/selections/runs", ({ request }) => {
		const specId = new URL(request.url).searchParams.get("spec_id");
		return HttpResponse.json({ data: selectionRunFixtures.filter((run) => run.spec_id === specId) });
	}),
	http.get("/api/v1/selections/runs/:before/compare/:after", () => HttpResponse.json({ data: selectionDiffFixture })),
	http.get("/api/v1/selections/runs/:runId", ({ params }) => {
		const run = selectionRunFixtures.find((item) => item.run_id === params["runId"]);
		return run ? HttpResponse.json({ data: run }) : HttpResponse.json({ detail: "not found" }, { status: 404 });
	}),
	http.get("/api/v1/selections/industry-rotations/:snapshotId", ({ params }) =>
		params["snapshotId"] === selectionRotationFixture.snapshot_id
			? HttpResponse.json({ data: selectionRotationFixture })
			: HttpResponse.json({ detail: "not found" }, { status: 404 }),
	),
	http.post("/api/v1/selections/runs", () => HttpResponse.json({ data: selectionReceiptFixture }, { status: 201 })),
	http.post("/api/v1/selections/runs:assembled", async ({ request }) => {
		const body = (await request.json()) as AssembleSelectionRunBody;
		const names = body.factor_weights.map((factor) => factor.name);
		const weightSum = body.factor_weights.reduce((sum, factor) => sum + factor.weight, 0);
		if (new Set(names).size !== names.length || Math.abs(weightSum - 1) > 1e-12)
			return HttpResponse.json({ detail: "因子权重不得重复且权重之和必须为 1" }, { status: 422 });
		return HttpResponse.json({ data: assembledSelectionRunResponse(body) });
	}),
	http.post("/api/v1/selections/runs/:runId/research-cases", async ({ params, request }) => {
		const run = selectionRunFixtures.find((item) => item.run_id === params["runId"]);
		if (!run) return HttpResponse.json({ detail: "not found" }, { status: 404 });
		const body = (await request.json()) as { objective: string; candidate_instrument_ids: number[] };
		const payload = {
			as_of: run.as_of,
			asset_kind: run.asset_kind,
			candidate_instrument_ids: body.candidate_instrument_ids,
			industry_rotation_snapshot_id: run.industry_rotation_snapshot_id,
			knowledge_cutoff: run.knowledge_cutoff,
			missing_inputs: run.missing_inputs,
			objective: body.objective,
			publication_cutoff: run.publication_cutoff,
			selection_input_hash: run.input_hash,
			selection_run_hash: run.run_id.split(":sha256:")[1] ?? "",
			selection_run_id: run.run_id,
			selection_spec_hash: run.spec_hash,
			selection_status: run.status,
			source_snapshot_ids: run.source_snapshot_ids,
			universe_snapshot_id: run.universe_snapshot_id,
		};
		return HttpResponse.json(
			{
				data: {
					...researchCaseFixture,
					...payload,
					case_id: `research-case:sha256:${mockCaseHash(payload)}`,
					content_hash: mockCaseHash(payload),
					schema_version: 1,
				},
			},
			{ status: 201 },
		);
	}),
];

function mockCaseHash(payload: unknown): string {
	const text = JSON.stringify(payload);
	let first = 0x811c9dc5;
	let second = 0x01000193;
	for (let index = 0; index < text.length; index++) {
		first = Math.imul(first ^ text.charCodeAt(index), 0x01000193) >>> 0;
		second = Math.imul(second + text.charCodeAt(index) * (index + 1), 0x85ebca6b) >>> 0;
	}
	return (first.toString(16).padStart(8, "0") + second.toString(16).padStart(8, "0")).repeat(4);
}
