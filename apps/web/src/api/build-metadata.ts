import { arrayValue, integerValue, recordValue, stringValue } from "./validation.ts";

const POLICY_SCHEMA = "ditto.cohort-compatibility-policy";
const POLICY_SCHEMA_VERSION = 1;
const SUPPORTED_API_CONTRACT_VERSION = "v1";
const POLICY_SOURCE_FIELDS = ["api_contract_version", "current", "previous", "schema", "schema_version"] as const;
const SNAKE_IDENTITY_FIELDS = ["product_version", "git_sha", "api_contract_version", "api_contract_sha256"] as const;
const CAMEL_IDENTITY_FIELDS = ["productVersion", "gitSha", "apiContractVersion", "apiContractSha256"] as const;
const EMBEDDED_POLICY_FIELDS = ["schema", "schemaVersion", "policySha256", "current", "previous"] as const;
const BUILD_METADATA_FIELDS = [...CAMEL_IDENTITY_FIELDS, "compatibilityPolicy"] as const;
const SEMVER =
	/^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/u;
const FULL_GIT_SHA = /^[0-9a-f]{40}$/u;
const FULL_SHA256 = /^[0-9a-f]{64}$/u;

export type CohortIdentity = {
	readonly productVersion: string;
	readonly gitSha: string;
	readonly apiContractVersion: "v1";
	readonly apiContractSha256: string;
};

export type CohortCompatibilityPolicy = {
	readonly schema: "ditto.cohort-compatibility-policy";
	readonly schemaVersion: 1;
	readonly policySha256: string;
	readonly current: CohortIdentity;
	readonly previous: readonly CohortIdentity[];
};

export type WebBuildMetadata = CohortIdentity & {
	readonly compatibilityPolicy: CohortCompatibilityPolicy;
};

declare const __DITTO_WEB_BUILD_METADATA__: unknown;

export class BuildMetadataError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "BuildMetadataError";
	}
}

export function materializeCohortCompatibilityPolicy(
	sourceValue: unknown,
	policySha256: string,
	currentValue: CohortIdentity,
): CohortCompatibilityPolicy {
	const boundary = "cohortCompatibilityPolicy";
	const source = recordValue(sourceValue, boundary);
	requireExactFields(source, POLICY_SOURCE_FIELDS, boundary);
	if (stringValue(source, "schema", boundary) !== POLICY_SCHEMA) {
		throw new BuildMetadataError(`invalid compatibility policy schema; expected ${POLICY_SCHEMA}`);
	}
	if (integerValue(source, "schema_version", boundary, 1) !== POLICY_SCHEMA_VERSION) {
		throw new BuildMetadataError("compatibility policy schema version must equal 1");
	}
	requireV1(stringValue(source, "api_contract_version", boundary), "compatibility policy");
	if (!FULL_SHA256.test(policySha256)) {
		throw new BuildMetadataError("compatibility policy hash must be a full lowercase SHA-256");
	}

	const currentSource = recordValue(source["current"], boundary, "current");
	requireExactFields(currentSource, ["source"], `${boundary}.current`);
	if (stringValue(currentSource, "source", `${boundary}.current`) !== "web_build") {
		throw new BuildMetadataError("compatibility policy current source must be web_build");
	}

	const current = parseCamelIdentity(currentValue, "current Web build", true);
	const rawPrevious = arrayValue(source, "previous", boundary);
	if (rawPrevious.length > 1) {
		throw new BuildMetadataError("compatibility policy allows at most one previous cohort");
	}
	const previous = rawPrevious.map((value) => parseSnakeIdentity(value, "previous cohort"));
	assertDistinctCohorts(current, previous);
	return freezePolicy({
		schema: POLICY_SCHEMA,
		schemaVersion: POLICY_SCHEMA_VERSION,
		policySha256,
		current,
		previous,
	});
}

export function validateWebBuildMetadata(value: unknown): WebBuildMetadata {
	const boundary = "webBuildMetadata";
	const record = recordValue(value, boundary);
	requireExactFields(record, BUILD_METADATA_FIELDS, boundary);
	const identity = parseCamelIdentity(record, boundary);
	const policy = parseEmbeddedPolicy(record["compatibilityPolicy"]);
	if (!cohortEquals(identity, policy.current) && !policy.previous.some((item) => cohortEquals(identity, item))) {
		throw new BuildMetadataError("Web build identity is not present in its embedded compatibility policy");
	}
	return Object.freeze({ ...identity, compatibilityPolicy: policy });
}

export function readWebBuildMetadata(): WebBuildMetadata {
	return validateWebBuildMetadata(__DITTO_WEB_BUILD_METADATA__);
}

function parseEmbeddedPolicy(value: unknown): CohortCompatibilityPolicy {
	const boundary = "webBuildMetadata.compatibilityPolicy";
	const record = recordValue(value, boundary);
	requireExactFields(record, EMBEDDED_POLICY_FIELDS, boundary);
	if (stringValue(record, "schema", boundary) !== POLICY_SCHEMA) {
		throw new BuildMetadataError(`invalid compatibility policy schema; expected ${POLICY_SCHEMA}`);
	}
	if (integerValue(record, "schemaVersion", boundary, 1) !== POLICY_SCHEMA_VERSION) {
		throw new BuildMetadataError("compatibility policy schema version must equal 1");
	}
	const policySha256 = stringValue(record, "policySha256", boundary);
	if (!FULL_SHA256.test(policySha256)) {
		throw new BuildMetadataError("compatibility policy hash must be a full lowercase SHA-256");
	}
	const current = parseCamelIdentity(record["current"], "compatibility policy current cohort", true);
	const rawPrevious = arrayValue(record, "previous", boundary);
	if (rawPrevious.length > 1) {
		throw new BuildMetadataError("compatibility policy allows at most one previous cohort");
	}
	const previous = rawPrevious.map((item) => parseCamelIdentity(item, "compatibility policy previous cohort", true));
	assertDistinctCohorts(current, previous);
	return freezePolicy({
		schema: POLICY_SCHEMA,
		schemaVersion: POLICY_SCHEMA_VERSION,
		policySha256,
		current,
		previous,
	});
}

function parseCamelIdentity(value: unknown, boundary: string, exact = false): CohortIdentity {
	const record = recordValue(value, boundary);
	if (exact) {
		requireExactFields(record, CAMEL_IDENTITY_FIELDS, boundary);
	} else {
		for (const field of CAMEL_IDENTITY_FIELDS) {
			if (!(field in record)) throw new BuildMetadataError(`${boundary}.${field} is required`);
		}
	}
	return validateIdentity(
		{
			productVersion: stringValue(record, "productVersion", boundary),
			gitSha: stringValue(record, "gitSha", boundary),
			apiContractVersion: stringValue(record, "apiContractVersion", boundary),
			apiContractSha256: stringValue(record, "apiContractSha256", boundary),
		},
		boundary,
	);
}

function parseSnakeIdentity(value: unknown, boundary: string): CohortIdentity {
	const record = recordValue(value, boundary);
	requireExactFields(record, SNAKE_IDENTITY_FIELDS, boundary);
	return validateIdentity(
		{
			productVersion: stringValue(record, "product_version", boundary),
			gitSha: stringValue(record, "git_sha", boundary),
			apiContractVersion: stringValue(record, "api_contract_version", boundary),
			apiContractSha256: stringValue(record, "api_contract_sha256", boundary),
		},
		boundary,
	);
}

function validateIdentity(
	value: {
		readonly productVersion: string;
		readonly gitSha: string;
		readonly apiContractVersion: string;
		readonly apiContractSha256: string;
	},
	boundary: string,
): CohortIdentity {
	if (!SEMVER.test(value.productVersion)) {
		throw new BuildMetadataError(`${boundary} product version must be valid SemVer`);
	}
	if (!FULL_GIT_SHA.test(value.gitSha)) {
		throw new BuildMetadataError(`${boundary} Git SHA must be a full lowercase 40-character hash`);
	}
	requireV1(value.apiContractVersion, boundary);
	if (!FULL_SHA256.test(value.apiContractSha256)) {
		throw new BuildMetadataError(`${boundary} contract SHA must be a full lowercase 64-character hash`);
	}
	return Object.freeze({
		productVersion: value.productVersion,
		gitSha: value.gitSha,
		apiContractVersion: SUPPORTED_API_CONTRACT_VERSION,
		apiContractSha256: value.apiContractSha256,
	});
}

function requireV1(value: string, boundary: string): asserts value is "v1" {
	if (value !== SUPPORTED_API_CONTRACT_VERSION) {
		throw new BuildMetadataError(`invalid API contract version ${value} for ${boundary}; expected v1`);
	}
}

function requireExactFields(
	record: Readonly<Record<string, unknown>>,
	expected: readonly string[],
	boundary: string,
): void {
	const actual = Object.keys(record).sort();
	const canonicalExpected = [...expected].sort();
	if (actual.length !== canonicalExpected.length || actual.some((field, index) => field !== canonicalExpected[index])) {
		throw new BuildMetadataError(
			`${boundary} has invalid fields: expected=${canonicalExpected.join(",")}, actual=${actual.join(",")}`,
		);
	}
}

function assertDistinctCohorts(current: CohortIdentity, previous: readonly CohortIdentity[]): void {
	const duplicate = previous.find(
		(item) =>
			cohortEquals(current, item) || item.productVersion === current.productVersion || item.gitSha === current.gitSha,
	);
	if (duplicate) {
		throw new BuildMetadataError(
			`duplicate current/previous cohort identity: version=${duplicate.productVersion}, git=${duplicate.gitSha}`,
		);
	}
}

function cohortEquals(left: CohortIdentity, right: CohortIdentity): boolean {
	return (
		left.productVersion === right.productVersion &&
		left.gitSha === right.gitSha &&
		left.apiContractVersion === right.apiContractVersion &&
		left.apiContractSha256 === right.apiContractSha256
	);
}

function freezePolicy(value: CohortCompatibilityPolicy): CohortCompatibilityPolicy {
	return Object.freeze({
		...value,
		current: Object.freeze({ ...value.current }),
		previous: Object.freeze(value.previous.map((item) => Object.freeze({ ...item }))),
	});
}
