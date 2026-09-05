import { describe, expect, it, vi } from "vitest";
import { createApiClient, mediaTypeSatisfiesContract, preserveExactJson } from "./transport";

describe("untrusted transport boundary inputs", () => {
	it.each([
		"",
		"application",
		"application/json/extra",
		"/json",
		"application/",
		"*/json",
		"app lication/json",
		"application/js on",
		"application/json;broken",
		"application/json;=value",
		"application/json;bad name=x",
		"application/json;x=a b",
		"application/json;x=a;x=b",
		'application/json;x="unfinished',
		'application/json;x="escaped\\',
		'application/json;x="a"b"',
		'application/json;x="a\tb"',
		"application/json;\u0001=x",
	])("rejects malformed media declarations: %j", (value) => {
		expect(mediaTypeSatisfiesContract("application/json", value)).toBe(false);
		expect(mediaTypeSatisfiesContract(value, "*/*")).toBe(false);
	});

	it("handles quoted parameters, escaping, wildcards and mismatches", () => {
		expect(mediaTypeSatisfiesContract('text/plain; profile="a;b"', 'text/plain;profile="a;b"')).toBe(true);
		expect(mediaTypeSatisfiesContract('text/plain; profile="a\\"b"', 'text/plain;profile="a\\"b"')).toBe(true);
		expect(mediaTypeSatisfiesContract("text/plain", "*/*")).toBe(true);
		expect(mediaTypeSatisfiesContract("text/plain", "application/json")).toBe(false);
		expect(mediaTypeSatisfiesContract("application/xml", "application/json")).toBe(false);
	});

	it.each([
		[null, "true"],
		[true, "false"],
		["one", '"two"'],
		[1, '"1"'],
		[undefined, "null"],
		[[1], "{}"],
		[{}, "[]"],
		[[1], "[1,2]"],
		[{ a: 1 }, '{"b":1}'],
		[{ a: 1 }, '{"a":1,"b":2}'],
		[{}, "{"],
		[1e20, "100000000000000000001"],
		[1.25, "9007199254740993"],
		[Number.NaN, "null"],
		[Number.POSITIVE_INFINITY, "null"],
		[1n, "1"],
		[() => 1, "1"],
		[Symbol("not-json"), "null"],
	] as const)("rejects a non-equivalent or non-JSON exact representation %#", (body, text) => {
		expect(() => preserveExactJson(body, text)).toThrow(TypeError);
	});

	it("preserves arrays, quoted numeric strings and shared non-cyclic subobjects", () => {
		const shared = { value: 2.5 };
		const body = { a: shared, b: shared, values: [null, true, 1.25, '9007199254740993\\"'] };
		const text = JSON.stringify(body);
		expect(preserveExactJson(body, text).text).toBe(text);
	});

	it("rejects cycles, sparse arrays and array accessors without invoking them", () => {
		const cyclic: Record<string, unknown> = {};
		cyclic["self"] = cyclic;
		const accessor = vi.fn(() => 1);
		const accessorArray: number[] = [];
		Object.defineProperty(accessorArray, "0", { enumerable: true, get: accessor });
		const extended = Object.assign([1], { extra: 2 });
		const symbolArray = Object.assign([1], { [Symbol("extra")]: 2 });
		for (const body of [cyclic, Array(1), accessorArray, extended, symbolArray]) {
			expect(() => preserveExactJson(body, "[]")).toThrow(TypeError);
		}
		expect(accessor).not.toHaveBeenCalled();
	});

	it.each([
		null,
		[],
		new Date(),
		{ [Symbol("option")]: 1 },
		Object.defineProperty({}, "body", { value: {}, enumerable: false }),
		Object.defineProperty({}, "body", { get: () => ({}), enumerable: true }),
		{ signal: {} },
		{ exactJson: {} },
		{ body: {}, exactJson: null },
		{ body: {}, exactJson: { body: {}, text: "{}" } },
		{ params: { nowhere: {} } },
		{ params: { cookie: {} } },
		{ params: { query: new Map() } },
	])("rejects malformed operation options before network access %#", async (init) => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>();
		const client = createApiClient({ apiBaseUrl: "http://127.0.0.1:8000", apiContractVersion: "v1", fetcher });
		await expect(client.get("/api/v1/status", init as never)).rejects.toThrow(TypeError);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("rejects an unknown operation before network access", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>();
		const client = createApiClient({ apiBaseUrl: "http://127.0.0.1:8000", apiContractVersion: "v1", fetcher });
		await expect(client.get("/not-declared" as never)).rejects.toThrow(/absent/u);
		expect(fetcher).not.toHaveBeenCalled();
	});

	it("retains valid issue details and rejects malformed validation issue entries", async () => {
		const fetcher = vi.fn<(request: Request) => Promise<Response>>(async () =>
			Response.json(
				{
					detail: [
						null,
						1,
						{ loc: "body" },
						{ loc: [null], msg: "bad", type: "bad" },
						{ loc: [], msg: "", type: "bad" },
						{ loc: [], msg: "bad", type: 1 },
						{ loc: ["body", 0], msg: "required", type: "missing" },
					],
					timestamp: 123,
				},
				{ status: 422 },
			),
		);
		const client = createApiClient({ apiBaseUrl: "http://127.0.0.1:8000", apiContractVersion: "v1", fetcher });
		await expect(client.get("/api/v1/status")).rejects.toMatchObject({
			timestamp: 123,
			validationIssues: [{ location: ["body", 0], message: "required", type: "missing" }],
		});
	});

	it.each(["", "{"])("rejects missing or malformed declared JSON: %j", async (body) => {
		const client = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher: async () => new Response(body, { headers: { "Content-Type": "application/json" } }),
		});
		await expect(client.get("/api/v1/status")).rejects.toMatchObject({ errorCode: "API_CONTRACT_MISMATCH" });
	});

	it("rejects an invalid fetch seam and a JSON operation used as SSE", async () => {
		const invalid = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher: async () => ({}) as Response,
		});
		await expect(invalid.get("/api/v1/status")).rejects.toThrow(/must return a Response/u);
		const json = createApiClient({
			apiBaseUrl: "http://127.0.0.1:8000",
			apiContractVersion: "v1",
			fetcher: async () => Response.json({ status: "running" }),
		});
		await expect(json.getEventStream("/api/v1/status" as never)).rejects.toThrow(/not an event stream/u);
	});
});
