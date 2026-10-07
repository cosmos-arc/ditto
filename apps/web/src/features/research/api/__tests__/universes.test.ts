// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest, requestJson } from "@/test/request";
import { createUniverse, fetchUniverses, updateUniverse } from "../universes";

afterEach(() => {
	vi.unstubAllGlobals();
});

const universeRow = {
	universe_id: "u-1",
	name: "Custom",
	universe_type: "custom",
	description: null,
	source_ref: null,
};

function jsonResponse(data: unknown, status = 200): Response {
	return new Response(JSON.stringify({ data }), {
		status,
		headers: { "Content-Type": "application/json" },
	});
}

describe("universes api", () => {
	it("maps null description/source_ref to empty strings", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse([universeRow]));
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchUniverses()).resolves.toEqual([
			{
				universeId: "u-1",
				name: "Custom",
				universeType: "custom",
				description: "",
				sourceRef: "",
			},
		]);
	});

	it("sends explicit description and member list on update", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse(universeRow));
		vi.stubGlobal("fetch", fetchMock);

		await updateUniverse("u-1", {
			name: "Renamed",
			description: "with text",
			effectiveDate: "2026-10-07",
			members: ["000001.SZ"],
		});
		await expect(requestJson(capturedRequest(fetchMock.mock.calls))).resolves.toEqual({
			name: "Renamed",
			description: "with text",
			effective_date: "2026-10-07",
			members: ["000001.SZ"],
		});
	});

	it("nulls out optional create fields when omitted", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse(universeRow, 201));
		vi.stubGlobal("fetch", fetchMock);

		await createUniverse({ universeId: "u-2", name: "Bare" });
		await expect(requestJson(capturedRequest(fetchMock.mock.calls))).resolves.toEqual({
			universe_id: "u-2",
			name: "Bare",
			description: null,
		});
	});
});
