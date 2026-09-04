import { afterEach, describe, expect, it, vi } from "vitest";
import { type ApiError, apiClient, withQueryParams } from "./api-client";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("withQueryParams", () => {
	it("appends scalar query params and skips empty values", () => {
		expect(
			withQueryParams("/system/pipelines", {
				page: 2,
				pageSize: 20,
				search: "",
				enabled: true,
				empty: undefined,
			}),
		).toBe("/system/pipelines?page=2&pageSize=20&search=&enabled=true");
	});

	it("serializes structured params for GET-backed filters", () => {
		expect(
			withQueryParams("/screener/run", {
				filters: [{ field: "pe", operator: "lt", value: 20 }],
			}),
		).toBe("/screener/run?filters=%5B%7B%22field%22%3A%22pe%22%2C%22operator%22%3A%22lt%22%2C%22value%22%3A20%7D%5D");
	});
});

describe("apiClient", () => {
	it("unwraps successful APIResponse data and prefixes the /api base path once", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(JSON.stringify({ data: { status: "ready" } }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(apiClient.get<{ readonly status: string }>("/v1/manual/daily-decision")).resolves.toEqual({
			status: "ready",
		});

		expect(fetchMock).toHaveBeenCalledWith("/api/v1/manual/daily-decision", expect.objectContaining({ method: "GET" }));
	});

	it("preserves the response envelope when pagination is part of the consumer contract", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(
				async () =>
					new Response(
						JSON.stringify({
							data: [{ id: "run-1" }],
							pagination: { total: 21, limit: 20, offset: 0, has_more: true },
						}),
						{ status: 200, headers: { "Content-Type": "application/json" } },
					),
			),
		);

		await expect(apiClient.getResponse<readonly { readonly id: string }[]>("/v1/agent/runs")).resolves.toEqual({
			data: [{ id: "run-1" }],
			pagination: { total: 21, limit: 20, offset: 0, has_more: true },
		});
	});

	it("maps backend error responses to ApiError metadata", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						status_code: 409,
						error: "Conflict",
						detail: "invalid transition",
						error_code: "TRADE_STATE_CONFLICT",
						request_id: "req-123",
						timestamp: "2026-07-02T12:00:00Z",
					}),
					{
						status: 409,
						headers: { "Content-Type": "application/json" },
					},
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(apiClient.get("/v1/manual/intents")).rejects.toMatchObject({
			name: "ApiError",
			status: 409,
			message: "invalid transition",
			errorCode: "TRADE_STATE_CONFLICT",
			requestId: "req-123",
			detail: "invalid transition",
		} satisfies Partial<ApiError>);
	});
});
