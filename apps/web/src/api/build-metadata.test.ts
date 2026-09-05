import { describe, expect, it } from "vitest";
import {
	materializeCohortCompatibilityPolicy,
	validateWebBuildMetadata,
	type WebBuildMetadata,
} from "./build-metadata";

const current = {
	productVersion: "1.2.0",
	gitSha: "a".repeat(40),
	apiContractVersion: "v1",
	apiContractSha256: "b".repeat(64),
} as const;

const source = {
	schema: "ditto.cohort-compatibility-policy",
	schema_version: 1,
	api_contract_version: "v1",
	current: { source: "web_build" },
	previous: [],
};

describe("cohort compatibility build metadata", () => {
	it("materializes the exact build identity and checked policy hash", () => {
		expect(materializeCohortCompatibilityPolicy(source, "c".repeat(64), current)).toEqual({
			schema: "ditto.cohort-compatibility-policy",
			schemaVersion: 1,
			policySha256: "c".repeat(64),
			current,
			previous: [],
		});
	});

	it.each([
		["schema", { ...source, schema: "ditto.compatible-by-major" }, undefined],
		["schema version", { ...source, schema_version: 2 }, undefined],
		["API contract", { ...source, api_contract_version: "v2" }, undefined],
		["policy hash", source, "short"],
		[
			"at most one previous cohort",
			{
				...source,
				previous: [
					{
						product_version: "1.1.0",
						git_sha: "d".repeat(40),
						api_contract_version: "v1",
						api_contract_sha256: "e".repeat(64),
					},
					{
						product_version: "1.0.0",
						git_sha: "f".repeat(40),
						api_contract_version: "v1",
						api_contract_sha256: "0".repeat(64),
					},
				],
			},
			undefined,
		],
	] as const)("rejects invalid %s", (_label, policy, policyHash) => {
		const checkedHash: string = policyHash ?? "c".repeat(64);
		expect(() => materializeCohortCompatibilityPolicy(policy, checkedHash, current)).toThrow();
	});

	it.each([
		["product version", { product_version: "v1.1.0" }],
		["Git SHA", { git_sha: "deadbeef" }],
		["contract version", { api_contract_version: "v2" }],
		["contract SHA", { api_contract_sha256: "weak" }],
	] as const)("rejects a previous cohort with an invalid %s", (_label, override) => {
		const previous = {
			product_version: "1.1.0",
			git_sha: "d".repeat(40),
			api_contract_version: "v1",
			api_contract_sha256: "e".repeat(64),
			...override,
		};
		expect(() =>
			materializeCohortCompatibilityPolicy({ ...source, previous: [previous] }, "c".repeat(64), current),
		).toThrow();
	});

	it.each([
		["exact identity", {}],
		["product version", { git_sha: "d".repeat(40) }],
		["Git SHA", { product_version: "1.1.0" }],
	] as const)("rejects a duplicate current/previous %s", (_label, override) => {
		const duplicate = {
			product_version: current.productVersion,
			git_sha: current.gitSha,
			api_contract_version: current.apiContractVersion,
			api_contract_sha256: current.apiContractSha256,
			...override,
		};
		expect(() =>
			materializeCohortCompatibilityPolicy({ ...source, previous: [duplicate] }, "c".repeat(64), current),
		).toThrow(/duplicate/iu);
	});

	it("produces a metadata shape that can represent either side of the allowed pair", () => {
		const policy = materializeCohortCompatibilityPolicy(source, "c".repeat(64), current);
		const metadata: WebBuildMetadata = { ...current, compatibilityPolicy: policy };
		expect(metadata.compatibilityPolicy.current).toEqual(current);
	});

	it("rejects undeclared fields inside an embedded cohort identity", () => {
		const policy = materializeCohortCompatibilityPolicy(source, "c".repeat(64), current);
		const metadata = {
			...current,
			compatibilityPolicy: {
				...policy,
				current: { ...policy.current, compatibilityByMajor: true },
			},
		};

		expect(() => validateWebBuildMetadata(metadata)).toThrow(/invalid fields/iu);
	});
});
