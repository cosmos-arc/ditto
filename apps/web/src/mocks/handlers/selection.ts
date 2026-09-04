import { HttpResponse, http } from "msw";
import {
	selectionDiffFixture,
	selectionReceiptFixture,
	selectionRotationFixture,
	selectionRunFixtures,
} from "../fixtures/selection";

export const selectionHandlers = [
	http.get("/api/v1/selections/runs", ({ request }) => {
		const specId = new URL(request.url).searchParams.get("spec_id");
		return HttpResponse.json({ data: selectionRunFixtures.filter((run) => run.spec_id === specId) });
	}),
	http.get("/api/v1/selections/runs/:before/compare/:after", () => HttpResponse.json({ data: selectionDiffFixture })),
	http.get("/api/v1/selections/runs/:runId", ({ params }) => {
		const run = selectionRunFixtures.find((item) => item.run_id === params.runId);
		return run ? HttpResponse.json({ data: run }) : HttpResponse.json({ detail: "not found" }, { status: 404 });
	}),
	http.get("/api/v1/selections/industry-rotations/:snapshotId", ({ params }) =>
		params.snapshotId === selectionRotationFixture.snapshot_id
			? HttpResponse.json({ data: selectionRotationFixture })
			: HttpResponse.json({ detail: "not found" }, { status: 404 }),
	),
	http.post("/api/v1/selections/runs", () => HttpResponse.json({ data: selectionReceiptFixture }, { status: 201 })),
];
