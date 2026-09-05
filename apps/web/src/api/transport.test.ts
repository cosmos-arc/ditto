import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient, mediaTypeSatisfiesContract, preserveExactJson } from "./transport";

describe("typed API transport", () => {
	it("unwraps the generated API envelope and serializes generated parameters", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(
			Response.json({
				data: [],
				pagination: { total: 0, limit: 10, offset: 0, has_more: false },
			}),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(client.get("/api/v1/strategies", { params: { query: { limit: 10, offset: 0 } } })).resolves.toEqual(
			[],
		);
		const request = fetcher.mock.calls[0]?.[0];
		expect(request?.url).toBe("http://127.0.0.1:8000/api/v1/strategies?limit=10&offset=0");
		expect(request?.headers.get("X-Ditto-API-Contract-Version")).toBe("v1");
	});

	it("normalizes an operation error without treating it as success data", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(
			Response.json(
				{
					error_code: "VALIDATION_ERROR",
					detail: "bad request",
					request_id: "request-1",
					timestamp: "2026-09-04T00:00:00Z",
				},
				{ status: 422 },
			),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		const error = await client.get("/api/v1/status").catch((reason: unknown) => reason);
		expect(error).toBeInstanceOf(ApiError);
		expect(error).toMatchObject({ status: 422, errorCode: "VALIDATION_ERROR", requestId: "request-1" });
	});

	it("preserves typed FastAPI validation issues with a useful field message", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(
			Response.json(
				{
					detail: [
						{
							loc: ["header", "X-Ditto-API-Contract-Version"],
							msg: "Input should be 'v1'",
							type: "literal_error",
							input: "v2",
						},
					],
				},
				{ status: 422 },
			),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v2",
			fetcher,
		});

		const error = await client.get("/api/v1/status").catch((reason: unknown) => reason);

		expect(error).toBeInstanceOf(ApiError);
		expect(error).toMatchObject({
			status: 422,
			message: "header.X-Ditto-API-Contract-Version: Input should be 'v1'",
			validationIssues: [
				{
					location: ["header", "X-Ditto-API-Contract-Version"],
					message: "Input should be 'v1'",
					type: "literal_error",
				},
			],
		});
	});

	it("uses a deterministic HTTP fallback when an error body is not an object", async () => {
		const fetcher = vi
			.fn<(request: Request) => Promise<Response>>()
			.mockResolvedValue(Response.json(17, { status: 500, statusText: "" }));
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(client.get("/api/v1/status")).rejects.toMatchObject({ status: 500, message: "HTTP 500" });
	});

	it("rejects empty or undeclared success responses for the exact operation", async () => {
		const fetcher = vi
			.fn<(request: Request) => Promise<Response>>()
			.mockResolvedValueOnce(new Response(null, { status: 200 }))
			.mockResolvedValueOnce(new Response(null, { status: 204 }));
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(client.get("/api/v1/status")).rejects.toMatchObject({
			errorCode: "API_CONTRACT_MISMATCH",
			message: expect.stringMatching(/media type <missing>/u),
		});
		await expect(client.get("/api/v1/status")).rejects.toThrow(/status 204 is not declared/u);
	});

	it("rejects a response media type that drifts from the declared operation", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(
			new Response("not-json", {
				status: 200,
				headers: { "Content-Type": "text/plain; charset=utf-8" },
			}),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(client.get("/api/v1/status")).rejects.toMatchObject({
			name: "ApiError",
			errorCode: "API_CONTRACT_MISMATCH",
			status: 200,
			message: expect.stringMatching(/text\/plain.*application\/json/u),
		});
	});

	it.each([
		["parseAs", { parseAs: "text" }],
		["baseUrl", { baseUrl: "https://example.invalid" }],
		["headers", { headers: { "X-Ditto-API-Contract-Version": "v2" } }],
		["fetch", { fetch: vi.fn() }],
		["pathSerializer", { pathSerializer: () => "/api/v1/not-the-declared-operation" }],
		["bodySerializer", { bodySerializer: () => "{}" }],
	] as const)("rejects the per-operation %s transport escape hatch at runtime", async (_field, unsafeInit) => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(
			Response.json({
				data: {
					status: "ok",
				},
			}),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(client.get("/api/v1/status", unsafeInit as never)).rejects.toThrow(/request option/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("rejects a Headers object that attempts to override the transport-owned contract version", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(
			Response.json({
				status: "running",
			}),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(
			client.get("/api/v1/status", {
				params: { header: new Headers({ "X-Ditto-API-Contract-Version": "v2" }) },
			} as never),
		).rejects.toThrow(/plain object|transport-owned/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("rejects undeclared nested query parameters carried by a structurally assignable variable", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(Response.json({ data: [] }));
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});
		const query = { limit: 10, offset: 0, undeclared: "sentinel" };

		await expect(client.get("/api/v1/strategies", { params: { query } })).rejects.toThrow(/undeclared.*query/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("rejects duplicate case-insensitive header parameters before serialization", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(Response.json({ data: {} }));
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(
			client.post("/api/v1/strategies", {
				body: {},
				params: { header: { "Idempotency-Key": "first", "idempotency-key": "second" } },
			} as never),
		).rejects.toThrow(/duplicate.*header/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("snapshots each request field once and rejects accessor-based exact JSON substitution", async () => {
		const signedBody = { amount: 1 };
		const unsignedBody = { amount: 2 };
		const exactJson = preserveExactJson(signedBody, '{"amount":1.0}');
		let reads = 0;
		const unsafeInit: Record<string, unknown> = {
			exactJson,
			params: { path: { experiment_id: "experiment-1" } },
		};
		Object.defineProperty(unsafeInit, "body", {
			enumerable: true,
			get() {
				reads += 1;
				return reads === 1 ? unsignedBody : signedBody;
			},
		});
		const fetcher = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(Response.json({ data: {} }));
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(
			client.post("/api/v1/research/experiments/{experiment_id}/preflight", unsafeInit as never),
		).rejects.toThrow(/accessor|semantically identical/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("owns Accept negotiation and refuses automatic redirects", async () => {
		const requests: Request[] = [];
		const fetcher = vi.fn<(request: Request) => Promise<Response>>(async (request) => {
			requests.push(request);
			return request.url.includes("/events")
				? new Response("", { headers: { "Content-Type": "text/event-stream" } })
				: Response.json({ status: "running" });
		});
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await client.get("/api/v1/status");
		const stream = await client.getEventStream("/api/v1/agent/runs/{run_id}/events", {
			params: { path: { run_id: "run-1" } },
		});
		await stream.body?.cancel();

		expect(requests[0]?.headers.get("Accept")).toBe("application/json");
		expect(requests[1]?.headers.get("Accept")).toBe("text/event-stream");
		expect(requests.map((request) => request.redirect)).toEqual(["error", "error"]);
	});

	it("accepts only media types that satisfy the declared essence and parameters", () => {
		expect(mediaTypeSatisfiesContract("text/plain; charset=UTF-8; format=flowed", "text/plain;charset=utf-8")).toBe(
			true,
		);
		expect(mediaTypeSatisfiesContract("text/plain", "text/plain;charset=utf-8")).toBe(false);
		expect(mediaTypeSatisfiesContract("application/problem+json", "application/*")).toBe(true);
		expect(mediaTypeSatisfiesContract("not a media type", "*/*")).toBe(false);
	});

	it("permits an exact JSON spelling only when it remains bound and semantically identical", async () => {
		const body = { amount: 1, nested: { enabled: true } };
		const exactJson = preserveExactJson(body, '{"nested":{"enabled":true},"amount":1.0}');
		expect(exactJson.text).toContain("1.0");
		expect(() => preserveExactJson(body, '{"amount":2,"nested":{"enabled":true}}')).toThrow(/semantically identical/u);
		expect(() => preserveExactJson({ identity: 9_007_199_254_740_992 }, '{"identity":9007199254740993}')).toThrow(
			/unsafe integer/u,
		);

		const fetcher = vi.fn<(request: Request) => Promise<Response>>();
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});
		body.amount = 2;
		await expect(client.get("/api/v1/status", { body, exactJson } as never)).rejects.toThrow(/semantically identical/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("uses the declared default response only for an undeclared error status", async () => {
		const fetcher = vi
			.fn<(request: Request) => Promise<Response>>()
			.mockResolvedValue(Response.json({ error_code: "TEAPOT", detail: "not brewing" }, { status: 418 }));
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});

		await expect(client.get("/api/v1/status")).rejects.toMatchObject({
			name: "ApiError",
			errorCode: "TEAPOT",
			status: 418,
		});
	});

	it("rejects non-positive and non-finite timeout budgets before network access", () => {
		for (const timeoutMs of [0, -1, Number.POSITIVE_INFINITY]) {
			expect(() =>
				createApiClient({ apiBaseUrl: "http://127.0.0.1:8000", apiContractVersion: "v1", timeoutMs }),
			).toThrow(/positive finite/u);
		}
	});

	it("aborts a stalled request at the transport timeout", async () => {
		vi.useFakeTimers();
		const fetcher = vi.fn<(request: Request) => Promise<Response>>(
			(request) =>
				new Promise((_resolve, reject) => {
					request.signal.addEventListener("abort", () => reject(request.signal.reason), { once: true });
				}),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
			timeoutMs: 25,
		});

		const request = client.get("/api/v1/status");
		const assertion = expect(request).rejects.toMatchObject({ name: "ApiTimeoutError", timeoutMs: 25 });
		await vi.advanceTimersByTimeAsync(25);
		await assertion;
		vi.useRealTimers();
	});

	it("does not invoke the network seam when the caller signal is already aborted", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>();
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});
		const controller = new AbortController();
		controller.abort(new DOMException("caller stopped", "AbortError"));

		await expect(client.get("/api/v1/status", { signal: controller.signal })).rejects.toMatchObject({
			name: "AbortError",
		});
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("keeps the timeout active until a response body finishes", async () => {
		vi.useFakeTimers();
		let bodyController: ReadableStreamDefaultController<Uint8Array> | undefined;
		const fetcher = vi.fn<(request: Request) => Promise<Response>>(
			async () =>
				new Response(
					new ReadableStream<Uint8Array>({
						start(controller) {
							bodyController = controller;
						},
					}),
					{ headers: { "Content-Type": "application/json" } },
				),
		);
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
			timeoutMs: 25,
		});
		const request = client.get("/api/v1/status");
		const observed = Promise.race([
			request.catch((error: unknown) => error),
			new Promise<"still-pending">((resolve) => setTimeout(() => resolve("still-pending"), 50)),
		]);

		try {
			await vi.advanceTimersByTimeAsync(50);
			expect(await observed).toMatchObject({ name: "ApiTimeoutError", timeoutMs: 25 });
		} finally {
			try {
				bodyController?.error(new Error("test cleanup"));
			} catch {}
			await request.catch(() => undefined);
			vi.useRealTimers();
		}
	});

	it("keeps the caller abort signal bound after event-stream headers arrive", async () => {
		let downstreamSignal: AbortSignal | undefined;
		const fetcher = vi.fn<(request: Request) => Promise<Response>>(async (request) => {
			downstreamSignal = request.signal;
			return new Response(new ReadableStream<Uint8Array>({}), {
				headers: { "Content-Type": "text/event-stream" },
			});
		});
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher,
		});
		const controller = new AbortController();
		const response = await client.getEventStream("/api/v1/agent/runs/{run_id}/events", {
			params: { path: { run_id: "run-1" } },
			signal: controller.signal,
		});

		controller.abort(new DOMException("caller stopped", "AbortError"));
		expect(downstreamSignal?.aborted).toBe(true);
		await response.body?.cancel().catch(() => undefined);
	});
});
