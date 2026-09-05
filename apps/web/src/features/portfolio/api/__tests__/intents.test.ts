import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest, requestJson, requestPath } from "@/test/request";
import { updateIntentStatus } from "../intents";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("updateIntentStatus", () => {
	it("updates intent status through the live trade command endpoint", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(JSON.stringify({ data: true }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(updateIntentStatus("intent-510300", "filled")).resolves.toBe(true);

		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe("/api/v1/manual/intents/intent-510300/status");
		expect(request.method).toBe("PUT");
		expect(await requestJson(request)).toEqual({ status: "filled" });
	});
});
