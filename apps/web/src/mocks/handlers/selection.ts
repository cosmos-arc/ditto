import { HttpResponse, http } from "msw";
import {
	selectionDiffFixture,
	selectionReceiptFixture,
	selectionRotationFixture,
	selectionRunFixtures,
} from "../fixtures/selection";

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
];
