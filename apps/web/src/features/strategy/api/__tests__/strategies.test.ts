// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchStrategies } from "../strategies";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchStrategies", () => {
	it("forwards pagination params when provided and omits them otherwise", async () => {
		const calls: Request[] = [];
		const fetchMock = vi.fn<typeof fetch>(async (input) => {
			calls.push(input as Request);
			return new Response(JSON.stringify({ data: [] }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		await fetchStrategies({ limit: 5, offset: 10 });
		await fetchStrategies();

		expect(new URL(calls[0]!.url).search).toBe("?limit=5&offset=10");
		expect(new URL(calls[1]!.url).search).toBe("");
	});
});
