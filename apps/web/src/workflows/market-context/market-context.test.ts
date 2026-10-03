import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchCurrentMarketContext } from "./market-context";

describe("current MarketContext workflow", () => {
	it("propagates PIT cutoffs and lets the server resolve the observed snapshot set", async () => {
		let requestedUrl = "";
		server.use(
			http.get("/api/v1/market/context", ({ request }) => {
				requestedUrl = request.url;
				return HttpResponse.json({ data: { status: "ready" } });
			}),
		);

		await fetchCurrentMarketContext("2026-08-31T09:00:00Z");

		const query = new URL(requestedUrl).searchParams;
		expect(query.getAll("source_snapshot_id")).toEqual([]);
		expect(query.get("as_of")).toBe("2026-08-31T09:00:00Z");
		expect(query.get("knowledge_cutoff")).toBe("2026-08-31T09:00:00Z");
		expect(query.get("publication_cutoff")).toBe("2026-08-31T09:00:00Z");
	});
});
