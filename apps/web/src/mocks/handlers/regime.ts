import { HttpResponse, http, type RequestHandler } from "msw";
import { mockRegimeDiagnostics } from "../fixtures/regime";

const REQUIRED_QUERY = [
	"snapshot_id",
	"snapshot_manifest_hash",
	"benchmark_instrument_id",
	"start_date",
	"end_date",
	"knowledge_cutoff",
] as const;

export const regimeHandlers: RequestHandler[] = [
	http.get("/api/v1/market/regime", ({ request }) => {
		const query = new URL(request.url).searchParams;
		if (REQUIRED_QUERY.some((key) => !query.get(key))) {
			return HttpResponse.json(
				{ detail: "complete exact scope is required", error_code: "REGIME_DIAGNOSTICS_INVALID" },
				{ status: 422 },
			);
		}
		return HttpResponse.json({ data: mockRegimeDiagnostics });
	}),
];
