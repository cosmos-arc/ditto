import { describe, expect, it } from "vitest";
import type { WebBuildMetadata } from "./build-metadata";
import { evaluateCompatibility, parseSystemStatus } from "./compatibility";

const currentCohort = {
	productVersion: "1.2.0",
	gitSha: "a".repeat(40),
	apiContractVersion: "v1",
	apiContractSha256: "b".repeat(64),
} as const;

const previousCohort = {
	productVersion: "1.1.0",
	gitSha: "c".repeat(40),
	apiContractVersion: "v1",
	apiContractSha256: "d".repeat(64),
} as const;

const web: WebBuildMetadata = {
	...currentCohort,
	compatibilityPolicy: {
		schema: "ditto.cohort-compatibility-policy",
		schemaVersion: 1,
		policySha256: "e".repeat(64),
		current: currentCohort,
		previous: [previousCohort],
	},
};

const status = {
	status: "running",
	version: "0.1.0",
	product_version: currentCohort.productVersion,
	git_sha: currentCohort.gitSha,
	api_contract_version: currentCohort.apiContractVersion,
	api_contract_sha256: currentCohort.apiContractSha256,
	environment: "development",
	features: { data_collection: true, data_validation: true, backtest: true, trading: true },
	observability: { level: "INFO", structured: true },
};

describe("backend compatibility", () => {
	it("accepts an exact release cohort", () => {
		expect(evaluateCompatibility(parseSystemStatus(status), web, { release: true })).toEqual({ warnings: [] });
	});

	it("allows only the explicitly listed previous backend with a transition warning", () => {
		const previousBackend = {
			...status,
			product_version: previousCohort.productVersion,
			git_sha: previousCohort.gitSha,
			api_contract_sha256: previousCohort.apiContractSha256,
		};

		expect(evaluateCompatibility(parseSystemStatus(previousBackend), web, { release: true })).toEqual({
			warnings: [expect.stringMatching(/rollback\/rolling-upgrade.*current Web.*previous backend/iu)],
		});
	});

	it("applies the explicit current/previous pair in the reverse deployment direction", () => {
		const previousWeb: WebBuildMetadata = { ...web, ...previousCohort };

		expect(evaluateCompatibility(parseSystemStatus(status), previousWeb, { release: true })).toEqual({
			warnings: [expect.stringMatching(/rollback\/rolling-upgrade.*previous Web.*current backend/iu)],
		});
	});

	it.each([
		["product_version", "1.2.1"],
		["git_sha", "f".repeat(40)],
		["api_contract_sha256", "f".repeat(64)],
	] as const)("fails a release cohort when %s differs", (field, value) => {
		expect(() =>
			evaluateCompatibility(parseSystemStatus({ ...status, [field]: value }), web, { release: true }),
		).toThrow(/cohort/i);
	});

	it("warns explicitly about a development contract hash drift", () => {
		const result = evaluateCompatibility(parseSystemStatus({ ...status, api_contract_sha256: "f".repeat(64) }), web, {
			release: false,
		});
		expect(result.warnings).toEqual([expect.stringMatching(/contract hash.*drift/i)]);
	});

	it("reports non-contract development cohort drift without mislabeling it as schema drift", () => {
		const result = evaluateCompatibility(parseSystemStatus({ ...status, product_version: "1.2.1" }), web, {
			release: false,
		});
		expect(result.warnings).toEqual(["development cohort drift (product version)"]);
	});

	it("fails closed on any incompatible API contract version in every environment", () => {
		expect(() =>
			evaluateCompatibility(parseSystemStatus({ ...status, api_contract_version: "v2" }), web, { release: false }),
		).toThrow(/API contract version/i);
	});

	it("fails closed when Web build metadata itself contains an invalid API version", () => {
		expect(() =>
			evaluateCompatibility(parseSystemStatus(status), { ...web, apiContractVersion: "latest" }, { release: false }),
		).toThrow(/invalid API contract version latest/u);
	});

	it.each([
		{ ...status, status: "ready" },
		{ ...status, git_sha: "weak" },
		{ ...status, api_contract_version: "latest" },
		{ ...status, api_contract_sha256: "not-a-hash" },
		{ ...status, features: { trading: "yes" } },
	])("rejects malformed status payloads %#", (payload) => {
		expect(() => parseSystemStatus(payload)).toThrow(/status/i);
	});
});
