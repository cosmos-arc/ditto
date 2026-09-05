import { describe, expect, it, vi } from "vitest";
import { verifyBackendCompatibility } from "./bootstrap";
import type { WebBuildMetadata } from "./build-metadata";
import { installRuntimeConfig, resetRuntimeConfigForTests } from "./runtime-config";
import type { ApiClient } from "./transport";

const buildIdentity = {
	productVersion: "0.1.0",
	gitSha: "a".repeat(40),
	apiContractVersion: "v1",
	apiContractSha256: "b".repeat(64),
} as const;

const build: WebBuildMetadata = {
	...buildIdentity,
	compatibilityPolicy: {
		schema: "ditto.cohort-compatibility-policy",
		schemaVersion: 1,
		policySha256: "c".repeat(64),
		current: buildIdentity,
		previous: [],
	},
};

const status = {
	status: "running",
	version: "0.1.0",
	product_version: "0.1.0",
	git_sha: "a".repeat(40),
	api_contract_version: "v1",
	api_contract_sha256: "b".repeat(64),
	environment: "development",
	features: { data_collection: true, data_validation: true, backtest: true, trading: true },
	observability: { level: "INFO", structured: true },
};

describe("compatibility bootstrap", () => {
	it("uses the client-level embedded contract assertion for the status handshake", async () => {
		const get = vi.fn().mockResolvedValue(status);
		await expect(
			verifyBackendCompatibility({
				release: true,
				build,
				client: { get: get as ApiClient["get"] },
			}),
		).resolves.toEqual({ warnings: [] });
		expect(get).toHaveBeenCalledWith("/api/v1/status");
	});

	it("uses installed runtime and embedded build metadata when no test doubles are supplied", async () => {
		installRuntimeConfig(
			{ schemaVersion: 1, runtime: "live", apiOrigin: "http://127.0.0.1:8000" },
			{ production: false },
		);
		const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ data: status }));
		vi.stubGlobal("fetch", fetchMock);

		await expect(verifyBackendCompatibility({ release: true })).resolves.toEqual({ warnings: [] });
		expect(fetchMock).toHaveBeenCalledOnce();
		vi.unstubAllGlobals();
		resetRuntimeConfigForTests();
	});
});
