import { afterEach, describe, expect, it, vi } from "vitest";
import { updateIntentStatus } from "../intents";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("updateIntentStatus", () => {
	it("updates intent status through the live trade command endpoint", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			new Response(JSON.stringify({ data: true }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(updateIntentStatus("intent-510300", "filled")).resolves.toBe(true);

		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/intents/intent-510300/status",
			expect.objectContaining({
				method: "PUT",
				body: JSON.stringify({ status: "filled" }),
			}),
		);
	});
});
