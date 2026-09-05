import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
	initializeRuntimeConfig,
	installRuntimeConfig,
	isMockRuntime,
	loadRuntimeConfig,
	parseRuntimeConfig,
	readRuntimeConfig,
	resetRuntimeConfigForTests,
	resolveApiBaseUrl,
} from "./runtime-config";

describe("runtime config", () => {
	it.each(["headers", "body"])("bounds stalled %s with one deadline and aborts the request", async (stage) => {
		vi.useFakeTimers();
		try {
			let signal: AbortSignal | undefined;
			const fetcher = (request: Request): Promise<Response> => {
				signal = request.signal;
				return stage === "headers" ? new Promise(() => {}) : Promise.resolve(new Response(new ReadableStream()));
			};
			const outcomes: unknown[] = [];
			const completion = loadRuntimeConfig({ fetcher, production: true }).then(
				(value) => outcomes.push(value),
				(error: unknown) => outcomes.push(error),
			);
			await vi.advanceTimersByTimeAsync(10_001);
			expect(outcomes).toHaveLength(1);
			expect(outcomes[0]).toMatchObject({ name: "RuntimeConfigError", message: "runtime config request timed out" });
			expect(signal?.aborted).toBe(true);
			await completion;
			expect(vi.getTimerCount()).toBe(0);
		} finally {
			vi.useRealTimers();
		}
	});

	it("ships a live standalone artifact pointed at the local API default", () => {
		const artifact = JSON.parse(
			readFileSync(resolve(import.meta.dirname, "../../public/ditto-runtime-config.json"), "utf8"),
		) as unknown;
		expect(parseRuntimeConfig(artifact, { production: true })).toEqual({
			schemaVersion: 1,
			runtime: "live",
			apiOrigin: "http://127.0.0.1:8000",
		});
	});

	it("accepts the exact public live configuration", () => {
		expect(parseRuntimeConfig({ schemaVersion: 1, runtime: "live", apiOrigin: "" }, { production: true })).toEqual({
			schemaVersion: 1,
			runtime: "live",
			apiOrigin: "",
		});
	});

	it.each([
		null,
		{ schemaVersion: 1, runtime: "live" },
		{ schemaVersion: 1, runtime: "preview", apiOrigin: "" },
		{ schemaVersion: 2, runtime: "live", apiOrigin: "" },
		{ schemaVersion: 1, runtime: "live", apiOrigin: "https://api.example.com" },
		{ schemaVersion: 1, runtime: "live", apiOrigin: "http://user:secret@127.0.0.1:8000" },
		{ schemaVersion: 1, runtime: "live", apiOrigin: "", apiToken: "secret" },
	])("rejects invalid or secret-bearing configuration %#", (input) => {
		expect(() => parseRuntimeConfig(input, { production: false })).toThrow();
	});

	it("rejects a non-string API origin before attempting URL parsing", () => {
		expect(() =>
			parseRuntimeConfig({ schemaVersion: 1, runtime: "live", apiOrigin: 8000 }, { production: false }),
		).toThrow(/apiOrigin must be a string/u);
	});

	it("rejects mock mode in a production build", () => {
		expect(() =>
			parseRuntimeConfig({ schemaVersion: 1, runtime: "mock", apiOrigin: "" }, { production: true }),
		).toThrow(/mock/i);
	});

	it("loads with no-store semantics and fails closed on HTTP errors", async () => {
		const fetcher = vi
			.fn<(request: Request) => Promise<Response>>()
			.mockResolvedValueOnce(Response.json({ schemaVersion: 1, runtime: "live", apiOrigin: "http://127.0.0.1:8000" }))
			.mockResolvedValueOnce(new Response("missing", { status: 404 }));

		await expect(loadRuntimeConfig({ fetcher, production: false })).resolves.toEqual({
			schemaVersion: 1,
			runtime: "live",
			apiOrigin: "http://127.0.0.1:8000",
		});
		const request = fetcher.mock.calls[0]?.[0];
		expect(request?.url).toBe("http://localhost:3000/ditto-runtime-config.json");
		expect(request?.cache).toBe("no-store");
		await expect(loadRuntimeConfig({ fetcher, production: false })).rejects.toThrow(/404/u);
	});

	it("does not expose an implicit runtime before bootstrap", () => {
		resetRuntimeConfigForTests();
		expect(() => readRuntimeConfig()).toThrow(/initialized/u);
		installRuntimeConfig({ schemaVersion: 1, runtime: "mock", apiOrigin: "" }, { production: false });
		expect(readRuntimeConfig().runtime).toBe("mock");
	});

	it("initializes from the default fetcher and resolves same-origin API requests", async () => {
		const fetchMock = vi
			.fn<typeof fetch>()
			.mockResolvedValue(Response.json({ schemaVersion: 1, runtime: "live", apiOrigin: "" }));
		vi.stubGlobal("fetch", fetchMock);
		vi.stubEnv("VITE_USE_MOCK", "false");

		await expect(initializeRuntimeConfig({ production: false })).resolves.toMatchObject({ runtime: "live" });
		expect(resolveApiBaseUrl()).toBe(location.origin);
		expect(isMockRuntime()).toBe(false);
		vi.unstubAllGlobals();
		vi.unstubAllEnvs();
	});
});
