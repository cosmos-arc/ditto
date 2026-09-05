import { describe, expect, test } from "bun:test";

const architecture = await import("../frontend_architecture.mjs");

function findings(
	source,
	relativeWebPath = "src/components/network-bypass.ts",
) {
	return architecture.findNetworkBoundaryViolations(source, relativeWebPath);
}

function rules(source, relativeWebPath) {
	return findings(source, relativeWebPath).map(({ rule }) => rule);
}

describe("frontend network boundary", () => {
	test("keeps every typed transport method inside feature API adapters", () => {
		expect(
			rules(`
import { apiClient as client } from "@/api";
await client.getEventStream("/api/v1/agent/runs/{run_id}/events", { params: { path: { run_id: "run" } } });
`),
		).toContain("typed-client-location");

		expect(
			rules(
				`apiClient.getEventStream("/api/v1/agent/runs/{run_id}/events", { params: { path: { run_id: "run" } } });`,
				"src/features/agent/api/agent-event-stream.ts",
			),
		).not.toContain("typed-client-location");
		expect(
			rules(
				`apiClient.getEventStream<Response>("/api/v1/agent/runs/{run_id}/events", { params: { path: { run_id: "run" } } });`,
				"src/features/agent/api/agent-event-stream.ts",
			),
		).toContain("caller-selected-response-type");

		expect(
			rules(`
import { apiClient as original } from "@/lib/forbidden-reexport";
const aliased = original;
aliased["g" + "et"]("/api/v1/status");
`),
		).toContain("typed-client-location");

		expect(
			rules(`
import { apiClient as client } from "@/api";
const hiddenMethod = Reflect.get(client, "getEventStream");
hiddenMethod("/api/v1/agent/runs/run/events");
`),
		).toContain("typed-client-location");
		expect(
			rules(`
const { getEventStream: hiddenMethod } = apiClient;
hiddenMethod("/api/v1/agent/runs/run/events");
`),
		).toContain("typed-client-location");
		expect(
			rules(`
import type { ApiClient } from "@/api";
export function useInjectedClient(client: ApiClient) {
	return client.getEventStream("/api/v1/agent/runs/run/events");
}
`),
		).toContain("typed-client-location");
	});

	test("rejects client factories and dynamic core API imports outside src/api", () => {
		const staticFactory = findings(`
import { createApiClient as makeClient } from "@/api/transport";
makeClient({ apiBaseUrl: "http://127.0.0.1:8000" });
`);
		expect(staticFactory.map(({ rule }) => rule)).toContain(
			"api-client-factory-location",
		);

		const dynamicFactory = findings(`
const api = await import("@/" + "api");
api.getApiClient();
`);
		expect(dynamicFactory.map(({ rule }) => rule)).toEqual(
			expect.arrayContaining([
				"dynamic-core-api-import",
				"api-client-factory-location",
			]),
		);
		expect(rules(`await import("/src/api/transport?worker");`)).toContain(
			"dynamic-core-api-import",
		);
		expect(
			rules(`
import { "createApiClient" as hiddenFactory } from "@/lib/forbidden-reexport";
hiddenFactory({});
`),
		).toContain("api-client-factory-location");
		expect(
			rules(`
import createRawClient from "openapi-fetch";
const rawClient = createRawClient({ baseUrl: "http://127.0.0.1:8000" });
`),
		).toContain("raw-transport-import");
		expect(rules(`await import("openapi-" + "fetch");`)).toContain(
			"raw-transport-import",
		);
	});

	test("rejects every browser network primitive across production source", () => {
		const result = findings(`
await fetch("/api/v1/status");
new XMLHttpRequest();
new EventSource("/api/v1/events");
new WebSocket("ws://127.0.0.1/events");
navigator.sendBeacon("/api/v1/audit", "payload");
globalThis["fet" + "ch"]("/api/v1/hidden");
`);

		expect(
			result
				.filter(({ rule }) => rule === "direct-network-access")
				.map(({ capability }) => capability),
		).toEqual([
			"fetch",
			"XMLHttpRequest",
			"EventSource",
			"WebSocket",
			"sendBeacon",
		]);
		expect(
			findings(`
import { "fetch" as hiddenRequest } from "network-shim";
hiddenRequest("/api/v1/status");
`).map(({ rule }) => rule),
		).toContain("direct-network-access");
	});

	test("rejects dynamic imports of generated runtime contracts", () => {
		expect(
			rules(`await import("@/api/generated/operation-" + "contracts");`),
		).toContain("generated-runtime-contract-location");
		expect(
			rules(`const moduleName = "@/api"; await import(moduleName);`),
		).toContain("opaque-dynamic-import");
		expect(rules(`await import("@/lib/" + "api-client");`)).toContain(
			"legacy-api-client-import",
		);
	});

	test("does not mistake comments and string data for network access", () => {
		expect(
			findings(`
// fetch("/api/v1/status")
const documentation = "new WebSocket and navigator.sendBeacon are forbidden here";
`),
		).toEqual([]);
		expect(
			findings(`.fetch { content: "WebSocket"; }`, "src/styles/example.css"),
		).toEqual([]);
	});

	test("allows browser networking only in src/api and explicit test or mock scopes", () => {
		const source = `
const client = createApiClient({ apiBaseUrl: "http://127.0.0.1:8000" });
await fetch("/api/v1/status");
new XMLHttpRequest();
new EventSource("/api/v1/events");
new WebSocket("ws://127.0.0.1/events");
navigator.sendBeacon("/api/v1/audit", "payload");
`;

		expect(findings(source, "src/api/transport.ts")).toEqual([]);
		expect(findings(source, "src/mocks/prototype-api.ts")).toEqual([]);
		expect(
			findings(source, "src/features/agent/api/agent-event-stream.test.ts"),
		).toEqual([]);
		expect(
			findings(source, "src/features/agent/api/__tests__/stream.ts"),
		).toEqual([]);
	});

	test("does not let feature API adapter placement expose client factories or raw fetch", () => {
		const result = findings(
			`createApiClient({}); fetch("/api/v1/status");`,
			"src/features/system/api/status.ts",
		);
		expect(result.map(({ rule }) => rule)).toEqual(
			expect.arrayContaining([
				"api-client-factory-location",
				"direct-network-access",
			]),
		);
	});
});
