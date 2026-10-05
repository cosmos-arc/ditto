import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchEtfNav } from "./indicator-overlays";

describe("ETF NAV display adapter", () => {
	it.each([
		{
			points: [
				{ nav_date: "2026-09-29", nav: 4.4 },
				{ nav_date: "2026-09-30", nav: 4.5 },
			],
		},
		{ points: [] },
	])("preserves the NAV response points", async ({ points }) => {
		server.use(
			http.post("/api/v1/market/etf-nav", async ({ request }) => {
				expect(await request.json()).toEqual({
					instrument_id: 1,
					start_date: "2026-09-29",
					end_date: "2026-09-30",
				});
				return HttpResponse.json({ data: { instrument_id: 1, points } });
			}),
		);
		expect(await fetchEtfNav("1", { startDate: "2026-09-29", endDate: "2026-09-30" })).toEqual({
			instrument_id: 1,
			points,
		});
	});
});
