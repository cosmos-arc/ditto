import {
	type CohortCompatibilityPolicy,
	type CohortIdentity,
	validateWebBuildMetadata,
	type WebBuildMetadata,
} from "./build-metadata";
import type { components } from "./generated/schema";
import { booleanValue, hashValue, recordValue, stringValue } from "./validation";

export type SystemStatus = components["schemas"]["SystemStatusResponse"];

export type CompatibilityResult = {
	readonly warnings: readonly string[];
};

export class CompatibilityError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "CompatibilityError";
	}
}

export function parseSystemStatus(value: unknown): SystemStatus {
	const boundary = "systemStatus";
	const record = recordValue(value, boundary);
	if (stringValue(record, "status", boundary) !== "running") {
		throw new CompatibilityError("system status must be running");
	}
	stringValue(record, "version", boundary);
	stringValue(record, "product_version", boundary);
	const gitSha = stringValue(record, "git_sha", boundary);
	if (!/^[0-9a-f]{40}$/u.test(gitSha))
		throw new CompatibilityError("system status git_sha must be a full lowercase hash");
	const apiContractVersion = stringValue(record, "api_contract_version", boundary);
	if (!/^v[1-9]\d*$/u.test(apiContractVersion)) {
		throw new CompatibilityError("system status api_contract_version must use vN syntax");
	}
	hashValue(record, "api_contract_sha256", boundary);
	stringValue(record, "environment", boundary);
	const features = recordValue(record["features"], boundary, "features");
	for (const field of ["data_collection", "data_validation", "backtest", "trading"] as const) {
		booleanValue(features, field, `${boundary}.features`);
	}
	const observability = recordValue(record["observability"], boundary, "observability");
	stringValue(observability, "level", `${boundary}.observability`);
	booleanValue(observability, "structured", `${boundary}.observability`);
	return value as SystemStatus;
}

export function evaluateCompatibility(
	server: SystemStatus,
	web: unknown,
	options: { readonly release: boolean },
): CompatibilityResult {
	const checkedWeb = validateWebBuildMetadata(web);
	if (server.api_contract_version !== checkedWeb.apiContractVersion) {
		throw new CompatibilityError(
			"API contract version is incompatible: Web=" +
				checkedWeb.apiContractVersion +
				", backend=" +
				server.api_contract_version,
		);
	}

	const differences = [
		server.product_version === checkedWeb.productVersion ? undefined : "product version",
		server.git_sha === checkedWeb.gitSha ? undefined : "Git SHA",
		server.api_contract_sha256 === checkedWeb.apiContractSha256 ? undefined : "API contract hash",
	].filter((value): value is string => value !== undefined);
	if (options.release) {
		return evaluateReleaseCompatibility(server, checkedWeb);
	}

	return {
		warnings: differences.map((field) =>
			field === "API contract hash"
				? `API contract hash drift: Web=${checkedWeb.apiContractSha256}, backend=${server.api_contract_sha256}`
				: `development cohort drift (${field})`,
		),
	};
}

function evaluateReleaseCompatibility(server: SystemStatus, web: WebBuildMetadata): CompatibilityResult {
	const backendIdentity: CohortIdentity = {
		productVersion: server.product_version,
		gitSha: server.git_sha,
		apiContractVersion: "v1",
		apiContractSha256: server.api_contract_sha256,
	};
	const webRole = cohortRole(web.compatibilityPolicy, web);
	const backendRole = cohortRole(web.compatibilityPolicy, backendIdentity);
	if (!webRole) {
		throw new CompatibilityError("Web release identity is absent from its compatibility policy");
	}
	if (!backendRole) {
		throw new CompatibilityError(
			`release cohort mismatch: backend ${describeCohort(backendIdentity)} is not explicitly allowed`,
		);
	}
	if (cohortEquals(web, backendIdentity)) return { warnings: [] };
	if (webRole === backendRole) {
		throw new CompatibilityError("release cohort mismatch: different identities claim the same policy role");
	}
	return {
		warnings: [
			"rollback/rolling-upgrade compatibility: " +
				webRole +
				" Web " +
				describeCohort(web) +
				" is connected to explicitly allowed " +
				backendRole +
				" backend " +
				describeCohort(backendIdentity),
		],
	};
}

function cohortRole(policy: CohortCompatibilityPolicy, identity: CohortIdentity): "current" | "previous" | undefined {
	if (cohortEquals(policy.current, identity)) return "current";
	if (policy.previous.some((item) => cohortEquals(item, identity))) return "previous";
	return undefined;
}

function cohortEquals(left: CohortIdentity, right: CohortIdentity): boolean {
	return (
		left.productVersion === right.productVersion &&
		left.gitSha === right.gitSha &&
		left.apiContractVersion === right.apiContractVersion &&
		left.apiContractSha256 === right.apiContractSha256
	);
}

function describeCohort(identity: CohortIdentity): string {
	return `${identity.productVersion}@${identity.gitSha}#${identity.apiContractSha256}`;
}
