import createOpenApiClient, { type Client, type ClientPathsWithMethod, type MaybeOptionalInit } from "openapi-fetch";
import { readWebBuildMetadata } from "./build-metadata";
import { operationRequestContracts, operationResponseContracts } from "./generated/operation-contracts";
import type { paths } from "./generated/schema";
import { readRuntimeConfig, resolveApiBaseUrl } from "./runtime-config";

type HttpMethod = "get" | "put" | "post" | "delete" | "options" | "head" | "patch" | "trace";
type OpenApiClient = Client<paths>;
type ApiPath<Method extends HttpMethod> = ClientPathsWithMethod<OpenApiClient, Method>;
type RawOperationInit<Method extends HttpMethod, Path extends ApiPath<Method>> = Method extends keyof paths[Path]
	? MaybeOptionalInit<paths[Path], Method>
	: never;
type DefinedRawOperationInit<Method extends HttpMethod, Path extends ApiPath<Method>> = Exclude<
	RawOperationInit<Method, Path>,
	undefined
>;
type OperationRequestShape<Method extends HttpMethod, Path extends ApiPath<Method>> = Pick<
	DefinedRawOperationInit<Method, Path>,
	Extract<keyof DefinedRawOperationInit<Method, Path>, "params" | "body">
>;
type OperationBody<Method extends HttpMethod, Path extends ApiPath<Method>> =
	DefinedRawOperationInit<Method, Path> extends { body?: infer Body } ? Body : never;

const exactJsonRepresentationBrand: unique symbol = Symbol("ditto.exact-json-representation");
const JSON_NUMBER_AT_CURSOR = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/u;

export type ExactJsonRepresentation<Body> = {
	readonly body: Body;
	readonly text: string;
	readonly [exactJsonRepresentationBrand]: true;
};

type SafeRequestControls<Method extends HttpMethod, Path extends ApiPath<Method>> = {
	readonly signal?: AbortSignal;
	readonly exactJson?: ExactJsonRepresentation<OperationBody<Method, Path>>;
};

export type OperationInit<Method extends HttpMethod, Path extends ApiPath<Method>> =
	undefined extends RawOperationInit<Method, Path>
		? (OperationRequestShape<Method, Path> & SafeRequestControls<Method, Path>) | undefined
		: OperationRequestShape<Method, Path> & SafeRequestControls<Method, Path>;
type InitArguments<Method extends HttpMethod, Path extends ApiPath<Method>> =
	undefined extends OperationInit<Method, Path>
		? [init?: Exclude<OperationInit<Method, Path>, undefined>]
		: [init: OperationInit<Method, Path>];
type UnwrapApiEnvelope<Value> = Value extends { data: infer Data } ? Data : Value;
type OperationDefinition<Method extends HttpMethod, Path extends ApiPath<Method>> = Method extends keyof paths[Path]
	? paths[Path][Method]
	: never;
type ResponseMap<Method extends HttpMethod, Path extends ApiPath<Method>> =
	OperationDefinition<Method, Path> extends { responses: infer Responses } ? Responses : never;
type DecimalDigit = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9";
export type SuccessStatusKey<Status> = Status extends number
	? `${Status}` extends `2${DecimalDigit}${DecimalDigit}`
		? Status
		: never
	: Status extends "2XX"
		? Status
		: never;
type SuccessStatus<Responses> = {
	[Status in keyof Responses]: SuccessStatusKey<Status>;
}[keyof Responses];
type SuccessResponse<Method extends HttpMethod, Path extends ApiPath<Method>> = ResponseMap<Method, Path>[Extract<
	keyof ResponseMap<Method, Path>,
	SuccessStatus<ResponseMap<Method, Path>>
>];
type ErrorStatus<Method extends HttpMethod, Path extends ApiPath<Method>> = Exclude<
	keyof ResponseMap<Method, Path>,
	SuccessStatus<ResponseMap<Method, Path>>
>;
type ResponseContent<Value> = Value extends { content: infer Content }
	? Content extends Readonly<Record<string, unknown>>
		? Content[keyof Content]
		: undefined
	: undefined;
type ResponseMediaTypes<Value> = Value extends { content: infer Content } ? keyof Content : never;
export type EventStreamPath = {
	[Path in ApiPath<"get">]: "text/event-stream" extends ResponseMediaTypes<SuccessResponse<"get", Path>> ? Path : never;
}[ApiPath<"get">];
type CallableApiPath<Method extends HttpMethod> = Method extends "get"
	? Exclude<ApiPath<Method>, EventStreamPath>
	: ApiPath<Method>;

export type OperationSuccess<Method extends HttpMethod, Path extends ApiPath<Method>> = UnwrapApiEnvelope<
	ResponseContent<SuccessResponse<Method, Path>>
>;
export type OperationPayload<Method extends HttpMethod, Path extends ApiPath<Method>> = ResponseContent<
	SuccessResponse<Method, Path>
>;
export type OperationError<Method extends HttpMethod, Path extends ApiPath<Method>> = ResponseContent<
	ResponseMap<Method, Path>[ErrorStatus<Method, Path>]
>;

type TypedMethod<Method extends HttpMethod> = <Path extends CallableApiPath<Method>>(
	path: Path,
	...init: InitArguments<Method, Path>
) => Promise<OperationSuccess<Method, Path>>;

type TypedPayloadMethod<Method extends HttpMethod> = <Path extends CallableApiPath<Method>>(
	path: Path,
	...init: InitArguments<Method, Path>
) => Promise<OperationPayload<Method, Path>>;

export type EventStreamRequest = <Path extends EventStreamPath>(
	path: Path,
	...init: InitArguments<"get", Path>
) => Promise<Response>;

export type ApiClient = {
	readonly get: TypedMethod<"get">;
	readonly getPayload: TypedPayloadMethod<"get">;
	readonly getEventStream: EventStreamRequest;
	readonly post: TypedMethod<"post">;
	readonly put: TypedMethod<"put">;
	readonly patch: TypedMethod<"patch">;
	readonly delete: TypedMethod<"delete">;
};

export type ApiValidationIssue = {
	readonly location: readonly (string | number)[];
	readonly message: string;
	readonly type: string;
};

export class ApiError extends Error {
	readonly status: number;
	readonly errorCode: string | undefined;
	readonly requestId: string | undefined;
	readonly detail: string | undefined;
	readonly timestamp: string | number | undefined;
	readonly validationIssues: readonly ApiValidationIssue[];
	readonly payload: unknown;

	constructor(params: {
		readonly status: number;
		readonly message: string;
		readonly payload: unknown;
		readonly errorCode?: string | undefined;
		readonly requestId?: string | undefined;
		readonly detail?: string | undefined;
		readonly timestamp?: string | number | undefined;
		readonly validationIssues?: readonly ApiValidationIssue[] | undefined;
	}) {
		super(params.message);
		this.status = params.status;
		this.errorCode = params.errorCode;
		this.requestId = params.requestId;
		this.detail = params.detail;
		this.timestamp = params.timestamp;
		this.validationIssues = params.validationIssues ?? [];
		this.payload = params.payload;
		this.name = "ApiError";
	}
}

export const DEFAULT_API_TIMEOUT_MS = 10_000;

export class ApiTimeoutError extends Error {
	readonly timeoutMs: number;

	constructor(timeoutMs: number) {
		super(`API request exceeded the ${timeoutMs} ms timeout`);
		this.timeoutMs = timeoutMs;
		this.name = "ApiTimeoutError";
	}
}

type ApiFetchResult = {
	readonly data?: unknown;
	readonly error?: unknown;
	readonly response: Response;
};

type UntypedRequest = (
	method: HttpMethod,
	path: string,
	init?: Readonly<Record<string, unknown>>,
) => Promise<ApiFetchResult>;
type RuntimeResponseContract = Readonly<Record<string, readonly string[]>>;
type RuntimeOperationContracts = Readonly<Record<string, RuntimeResponseContract>>;
type RequestParameterLocation = "cookie" | "header" | "path" | "query";
type RuntimeRequestContract = Readonly<{
	parameters: Readonly<Partial<Record<RequestParameterLocation, readonly string[]>>>;
}>;
type RuntimeOperationRequestContracts = Readonly<Record<string, RuntimeRequestContract>>;

const runtimeOperationContracts: RuntimeOperationContracts = Object.freeze(
	Object.fromEntries(
		Object.entries(operationResponseContracts).map(([operation, responses]) => [
			operation,
			Object.freeze(
				Object.fromEntries(
					Object.entries(responses).map(([status, mediaTypes]) => [status, Object.freeze([...mediaTypes])]),
				),
			),
		]),
	),
);

const runtimeOperationRequestContracts: RuntimeOperationRequestContracts = Object.freeze(
	Object.fromEntries(
		Object.entries(operationRequestContracts).map(([operation, request]) => [
			operation,
			Object.freeze({
				parameters: Object.freeze(
					Object.fromEntries(
						Object.entries(request.parameters).map(([location, names]) => [location, Object.freeze([...names])]),
					),
				),
			}),
		]),
	),
);

function jsonEquivalent(left: unknown, right: unknown, ancestors = new Set<object>()): boolean {
	if (left === null || right === null) return left === right;
	if (typeof left !== typeof right) return false;
	if (typeof left === "string" || typeof left === "boolean") return left === right;
	if (typeof left === "number") {
		return typeof right === "number" && Number.isFinite(left) && Number.isFinite(right) && left === right;
	}
	if (typeof left !== "object" || typeof right !== "object") return false;
	if (ancestors.has(left) || ancestors.has(right)) return false;
	ancestors.add(left);
	ancestors.add(right);
	try {
		if (Array.isArray(left) || Array.isArray(right)) {
			return (
				Array.isArray(left) &&
				Array.isArray(right) &&
				left.length === right.length &&
				left.every((value, index) => jsonEquivalent(value, right[index], ancestors))
			);
		}
		const leftRecord = left as Record<string, unknown>;
		const rightRecord = right as Record<string, unknown>;
		const leftKeys = Object.keys(leftRecord).sort();
		const rightKeys = Object.keys(rightRecord).sort();
		return (
			leftKeys.length === rightKeys.length &&
			leftKeys.every(
				(key, index) => key === rightKeys[index] && jsonEquivalent(leftRecord[key], rightRecord[key], ancestors),
			)
		);
	} finally {
		ancestors.delete(left);
		ancestors.delete(right);
	}
}

function assertNoUnsafeJsonIntegers(text: string): void {
	let quoted = false;
	let escaped = false;
	for (let index = 0; index < text.length; index += 1) {
		const character = text[index];
		if (character === undefined) continue;
		if (quoted) {
			if (escaped) escaped = false;
			else if (character === "\\") escaped = true;
			else if (character === '"') quoted = false;
			continue;
		}
		if (character === '"') {
			quoted = true;
			continue;
		}
		if (character !== "-" && (character < "0" || character > "9")) continue;
		const token = JSON_NUMBER_AT_CURSOR.exec(text.slice(index))?.[0];
		if (!token) continue;
		const numeric = Number(token);
		if (Number.isInteger(numeric) && !Number.isSafeInteger(numeric)) {
			throw new TypeError(`exact JSON representation contains an unsafe integer: ${token}`);
		}
		index += token.length - 1;
	}
}

function ownPlainDataProperties(value: unknown, boundary: string): ReadonlyMap<string, unknown> {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		throw new TypeError(`${boundary} must be a plain object`);
	}
	const prototype = Object.getPrototypeOf(value) as unknown;
	if (prototype !== Object.prototype && prototype !== null) {
		throw new TypeError(`${boundary} must be a plain object`);
	}
	const descriptors = Object.getOwnPropertyDescriptors(value);
	const properties = new Map<string, unknown>();
	for (const key of Reflect.ownKeys(descriptors)) {
		if (typeof key !== "string") throw new TypeError(`${boundary} must not contain symbol properties`);
		const descriptor = descriptors[key];
		if (!descriptor?.enumerable) throw new TypeError(`${boundary}.${key} must be enumerable`);
		if (!("value" in descriptor)) throw new TypeError(`${boundary}.${key} must not be an accessor property`);
		properties.set(key, descriptor.value);
	}
	return properties;
}

function snapshotJsonValue(value: unknown, boundary: string, ancestors = new Set<object>()): unknown {
	if (value === null || value === undefined || typeof value === "string" || typeof value === "boolean") return value;
	if (typeof value === "number") {
		if (!Number.isFinite(value)) throw new TypeError(`${boundary} must contain only finite JSON numbers`);
		if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
			throw new TypeError(`${boundary} contains an unsafe integer`);
		}
		return value;
	}
	if (typeof value !== "object") throw new TypeError(`${boundary} must contain only JSON-compatible values`);
	if (ancestors.has(value)) throw new TypeError(`${boundary} must not contain cyclic values`);
	ancestors.add(value);
	try {
		if (Array.isArray(value)) {
			const descriptors = Object.getOwnPropertyDescriptors(value);
			const keys = Reflect.ownKeys(descriptors);
			for (const key of keys) {
				if (typeof key !== "string" || (key !== "length" && !/^(?:0|[1-9]\d*)$/u.test(key))) {
					throw new TypeError(`${boundary} must be a plain JSON array`);
				}
			}
			return Array.from({ length: value.length }, (_unused, index) => {
				const descriptor = descriptors[String(index)];
				if (!descriptor?.enumerable || !("value" in descriptor)) {
					throw new TypeError(`${boundary}[${index}] must be an enumerable data property`);
				}
				return snapshotJsonValue(descriptor.value, `${boundary}[${index}]`, ancestors);
			});
		}
		const snapshot = Object.create(null) as Record<string, unknown>;
		for (const [key, propertyValue] of ownPlainDataProperties(value, boundary)) {
			snapshot[key] = snapshotJsonValue(propertyValue, `${boundary}.${key}`, ancestors);
		}
		return snapshot;
	} finally {
		ancestors.delete(value);
	}
}

function exactJsonText<Body>(representation: ExactJsonRepresentation<Body>, body: Body, bodySnapshot: unknown): string {
	if (typeof representation !== "object" || representation === null) {
		throw new TypeError("exact JSON representation is not bound to the operation body");
	}
	const descriptors = Object.getOwnPropertyDescriptors(representation);
	const bodyDescriptor = descriptors.body;
	const textDescriptor = descriptors.text;
	const brandDescriptor = descriptors[exactJsonRepresentationBrand];
	if (
		Reflect.ownKeys(descriptors).length !== 3 ||
		!bodyDescriptor ||
		!("value" in bodyDescriptor) ||
		bodyDescriptor.value !== body ||
		!textDescriptor ||
		!("value" in textDescriptor) ||
		typeof textDescriptor.value !== "string" ||
		!brandDescriptor ||
		!("value" in brandDescriptor) ||
		brandDescriptor.value !== true
	) {
		throw new TypeError("exact JSON representation is not bound to the operation body");
	}
	const text = textDescriptor.value;
	let decoded: unknown;
	try {
		decoded = JSON.parse(text) as unknown;
	} catch (error) {
		throw new TypeError("exact JSON representation must be valid JSON", { cause: error });
	}
	assertNoUnsafeJsonIntegers(text);
	if (!jsonEquivalent(decoded, bodySnapshot)) {
		throw new TypeError("exact JSON representation must be semantically identical to the operation body");
	}
	return text;
}

export function preserveExactJson<Body>(body: Body, text: string): ExactJsonRepresentation<Body> {
	const representation = Object.freeze({
		body,
		text,
		[exactJsonRepresentationBrand]: true as const,
	});
	exactJsonText(representation, body, snapshotJsonValue(body, "exact JSON body"));
	return representation;
}

function record(value: unknown): Record<string, unknown> | undefined {
	return typeof value === "object" && value !== null && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: undefined;
}

function optionalString(value: unknown): string | undefined {
	return typeof value === "string" ? value : undefined;
}

function optionalTimestamp(value: unknown): string | number | undefined {
	return typeof value === "string" || typeof value === "number" ? value : undefined;
}

function validationIssues(value: unknown): readonly ApiValidationIssue[] {
	if (!Array.isArray(value)) return [];
	return value.flatMap((candidate) => {
		const issue = record(candidate);
		if (
			!issue ||
			!Array.isArray(issue["loc"]) ||
			issue["loc"].some((part) => typeof part !== "string" && typeof part !== "number")
		) {
			return [];
		}
		const message = optionalString(issue["msg"]);
		const type = optionalString(issue["type"]);
		if (!message || !type) return [];
		return [{ location: issue["loc"] as readonly (string | number)[], message, type }];
	});
}

function apiError(result: ApiFetchResult): ApiError {
	const payload = record(result.error);
	const detail = optionalString(payload?.["detail"]);
	const issues = validationIssues(payload?.["detail"]);
	const error = optionalString(payload?.["error"]);
	return new ApiError({
		status: result.response.status,
		message:
			detail ??
			(issues[0] ? `${issues[0].location.join(".")}: ${issues[0].message}` : undefined) ??
			error ??
			(result.response.statusText || `HTTP ${result.response.status}`),
		payload: result.error,
		errorCode: optionalString(payload?.["error_code"]),
		requestId: optionalString(payload?.["request_id"]),
		detail,
		timestamp: optionalTimestamp(payload?.["timestamp"]),
		validationIssues: issues,
	});
}

function contractMismatch(
	result: ApiFetchResult,
	message: string,
	payload: Readonly<Record<string, unknown>>,
): ApiError {
	return new ApiError({
		status: result.response.status,
		message,
		payload,
		errorCode: "API_CONTRACT_MISMATCH",
		requestId: result.response.headers.get("X-Request-ID") ?? undefined,
	});
}

function responseContract(result: ApiFetchResult, method: HttpMethod, path: string): readonly string[] {
	const operation = `${method} ${path}`;
	const responses = runtimeOperationContracts[operation];
	if (!responses) {
		throw contractMismatch(result, `operation ${operation} is absent from the runtime contract`, {
			method,
			path,
			status: result.response.status,
		});
	}
	const status = result.response.status;
	const exact = responses[String(status)];
	if (exact) return exact;
	const wildcard = status >= 100 && status <= 599 ? responses[`${Math.floor(status / 100)}XX`] : undefined;
	if (wildcard) return wildcard;
	const isSuccess = status >= 200 && status <= 299;
	if (!isSuccess && responses["default"]) return responses["default"];
	throw contractMismatch(result, `status ${status} is not declared for ${operation}`, {
		declaredStatuses: Object.keys(responses),
		method,
		path,
		status,
	});
}

type ParsedMediaType = {
	readonly type: string;
	readonly subtype: string;
	readonly parameters: ReadonlyMap<string, string>;
};

const MEDIA_TOKEN = /^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/u;

function mediaTypeSections(value: string): readonly string[] | undefined {
	const sections: string[] = [];
	let start = 0;
	let quoted = false;
	let escaped = false;
	for (let index = 0; index < value.length; index += 1) {
		const character = value[index];
		if (character === undefined || (character.charCodeAt(0) < 32 && character !== "\t")) return undefined;
		if (escaped) {
			escaped = false;
			continue;
		}
		if (quoted && character === "\\") {
			escaped = true;
			continue;
		}
		if (character === '"') {
			quoted = !quoted;
			continue;
		}
		if (character === ";" && !quoted) {
			sections.push(value.slice(start, index).trim());
			start = index + 1;
		}
	}
	if (quoted || escaped) return undefined;
	sections.push(value.slice(start).trim());
	return sections;
}

function mediaParameterValue(value: string): string | undefined {
	if (!value.startsWith('"')) return MEDIA_TOKEN.test(value) ? value : undefined;
	if (value.length < 2 || !value.endsWith('"')) return undefined;
	let decoded = "";
	let escaped = false;
	for (const character of value.slice(1, -1)) {
		if (escaped) {
			decoded += character;
			escaped = false;
		} else if (character === "\\") {
			escaped = true;
		} else if (character === '"' || character.charCodeAt(0) < 32) {
			return undefined;
		} else {
			decoded += character;
		}
	}
	return escaped ? undefined : decoded;
}

function parseMediaType(value: string): ParsedMediaType | undefined {
	const sections = mediaTypeSections(value.trim());
	const essence = sections?.[0];
	if (!sections || !essence || essence.split("/").length !== 2) return undefined;
	const [rawType, rawSubtype] = essence.split("/", 2).map((part) => part.trim());
	if (
		!rawType ||
		!rawSubtype ||
		(rawType !== "*" && !MEDIA_TOKEN.test(rawType)) ||
		(rawSubtype !== "*" && !MEDIA_TOKEN.test(rawSubtype)) ||
		(rawType === "*" && rawSubtype !== "*")
	) {
		return undefined;
	}
	const parameters = new Map<string, string>();
	for (const section of sections.slice(1)) {
		const separator = section.indexOf("=");
		if (separator <= 0) return undefined;
		const name = section.slice(0, separator).trim().toLowerCase();
		const value = mediaParameterValue(section.slice(separator + 1).trim());
		if (!MEDIA_TOKEN.test(name) || value === undefined || parameters.has(name)) return undefined;
		parameters.set(name, name === "charset" ? value.toLowerCase() : value);
	}
	return { type: rawType.toLowerCase(), subtype: rawSubtype.toLowerCase(), parameters };
}

export function mediaTypeSatisfiesContract(actualValue: string, declaredValue: string): boolean {
	const actual = parseMediaType(actualValue);
	const declared = parseMediaType(declaredValue);
	if (!actual || !declared) return false;
	if (declared.type !== "*" && declared.type !== actual.type) return false;
	if (declared.subtype !== "*" && declared.subtype !== actual.subtype) return false;
	for (const [name, value] of declared.parameters) {
		if (actual.parameters.get(name) !== value) return false;
	}
	return true;
}

function validateResponseMediaType(
	result: ApiFetchResult,
	method: HttpMethod,
	path: string,
	declaredMediaTypes: readonly string[],
): void {
	const raw = result.response.headers.get("Content-Type");
	const actual = raw?.trim();
	const payload = result.response.ok ? result.data : result.error;
	if (declaredMediaTypes.length === 0) {
		if ((payload !== undefined && payload !== "") || actual) {
			throw contractMismatch(result, `response body is not declared for ${method} ${path}`, {
				actualMediaType: actual,
				method,
				path,
				status: result.response.status,
			});
		}
		return;
	}
	if (!actual || !declaredMediaTypes.some((declared) => mediaTypeSatisfiesContract(actual, declared))) {
		throw contractMismatch(
			result,
			`response media type ${actual ?? "<missing>"} is not declared for ${method} ${path}; expected ${declaredMediaTypes.join(
				", ",
			)}`,
			{
				actualMediaType: actual,
				declaredMediaTypes,
				method,
				path,
				status: result.response.status,
			},
		);
	}
}

function decodeResponsePayload(
	result: ApiFetchResult,
	method: HttpMethod,
	path: string,
	declaredMediaTypes: readonly string[],
): ApiFetchResult {
	validateResponseMediaType(result, method, path, declaredMediaTypes);
	const rawPayload = result.response.ok ? result.data : result.error;
	if (declaredMediaTypes.length === 0) {
		return result.response.ok
			? { data: undefined, response: result.response }
			: { error: undefined, response: result.response };
	}
	if (rawPayload === undefined || rawPayload === "") {
		throw contractMismatch(result, `response body is missing for ${method} ${path}`, {
			declaredMediaTypes,
			method,
			path,
			status: result.response.status,
		});
	}
	const actual = result.response.headers.get("Content-Type")?.trim();
	const actualMediaType = actual ? parseMediaType(actual) : undefined;
	let decoded: unknown = rawPayload;
	if (actualMediaType?.subtype === "json" || actualMediaType?.subtype.endsWith("+json")) {
		if (typeof rawPayload === "string") {
			try {
				decoded = JSON.parse(rawPayload) as unknown;
			} catch (error) {
				throw contractMismatch(result, `response JSON is invalid for ${method} ${path}`, {
					actualMediaType: actual,
					method,
					path,
					status: result.response.status,
					parseError: error instanceof Error ? error.message : String(error),
				});
			}
		}
	} else if (typeof rawPayload !== "string") {
		throw contractMismatch(result, `response body parser is unsupported for ${method} ${path}`, {
			actualMediaType: actual,
			method,
			path,
			status: result.response.status,
		});
	}
	return result.response.ok
		? { data: decoded, response: result.response }
		: { error: decoded, response: result.response };
}

function unwrap(result: ApiFetchResult, unwrapEnvelope: boolean, method: HttpMethod, path: string): unknown {
	const declaredMediaTypes = responseContract(result, method, path);
	const decoded = decodeResponsePayload(result, method, path, declaredMediaTypes);
	if (!decoded.response.ok) {
		throw apiError(decoded);
	}
	if (decoded.data === undefined && declaredMediaTypes.length > 0) {
		throw contractMismatch(result, "API success response did not contain typed data", {
			declaredMediaTypes,
			method,
			path,
			status: result.response.status,
		});
	}
	if (!unwrapEnvelope) return decoded.data;
	const payload = record(decoded.data);
	return payload && Object.hasOwn(payload, "data") ? payload["data"] : decoded.data;
}

const SAFE_OPERATION_REQUEST_KEYS = new Set(["params", "body", "signal", "exactJson"]);
const REQUEST_PARAMETER_LOCATIONS = new Set<RequestParameterLocation>(["cookie", "header", "path", "query"]);
const TRANSPORT_CONTRACT_HEADER = "x-ditto-api-contract-version";

function operationRequestContract(method: HttpMethod, path: string): RuntimeRequestContract {
	const operation = `${method} ${path}`;
	const contract = runtimeOperationRequestContracts[operation];
	if (!contract) throw new TypeError(`operation ${operation} is absent from the runtime request contract`);
	return contract;
}

function snapshotOperationParams(
	value: unknown,
	method: HttpMethod,
	path: string,
): Readonly<Record<string, Readonly<Record<string, unknown>>>> {
	const contract = operationRequestContract(method, path);
	const locations = ownPlainDataProperties(value, "operation params");
	const params: Record<string, Readonly<Record<string, unknown>>> = Object.create(null) as Record<
		string,
		Readonly<Record<string, unknown>>
	>;
	for (const [rawLocation, rawValues] of locations) {
		if (!REQUEST_PARAMETER_LOCATIONS.has(rawLocation as RequestParameterLocation)) {
			throw new TypeError(`undeclared operation parameter location: ${rawLocation}`);
		}
		const location = rawLocation as RequestParameterLocation;
		const declared = contract.parameters[location];
		if (!declared) throw new TypeError(`undeclared ${location} parameters for ${method} ${path}`);
		const allowed = new Set(declared.map((name) => (location === "header" ? name.toLowerCase() : name)));
		const seen = new Set<string>();
		const values = ownPlainDataProperties(rawValues, `operation params.${location}`);
		const snapshot: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
		for (const [name, parameterValue] of values) {
			const comparableName = location === "header" ? name.toLowerCase() : name;
			if (location === "header" && comparableName === TRANSPORT_CONTRACT_HEADER) {
				throw new TypeError("API contract version is transport-owned, not a per-operation request option");
			}
			if (!allowed.has(comparableName)) {
				throw new TypeError(`undeclared ${location} parameter for ${method} ${path}: ${name}`);
			}
			if (seen.has(comparableName)) {
				throw new TypeError(`duplicate ${location} parameter for ${method} ${path}: ${name}`);
			}
			seen.add(comparableName);
			snapshot[name] = snapshotJsonValue(parameterValue, `operation params.${location}.${name}`);
		}
		params[location] = snapshot;
	}
	return params;
}

function sanitizedRequestInit(
	init: Readonly<Record<string, unknown>> | undefined,
	parseAs: "text" | "stream",
	method: HttpMethod,
	path: string,
): Readonly<Record<string, unknown>> {
	const sanitized: Record<string, unknown> = {
		headers: { Accept: parseAs === "stream" ? "text/event-stream" : "application/json" },
		parseAs,
	};
	if (init === undefined) {
		operationRequestContract(method, path);
		return sanitized;
	}
	const properties = ownPlainDataProperties(init, "operation request");
	for (const key of properties.keys()) {
		if (!SAFE_OPERATION_REQUEST_KEYS.has(key)) {
			throw new TypeError(`unsupported per-operation request option: ${key}`);
		}
	}
	if (properties.has("params")) {
		sanitized["params"] = snapshotOperationParams(properties.get("params"), method, path);
	} else {
		operationRequestContract(method, path);
	}
	if (properties.has("signal")) {
		const signal = properties.get("signal");
		if (!(signal instanceof AbortSignal)) throw new TypeError("operation request signal must be an AbortSignal");
		sanitized["signal"] = signal;
	}
	const hasBody = properties.has("body");
	const body = properties.get("body");
	if (hasBody) sanitized["body"] = snapshotJsonValue(body, "operation request body");
	if (properties.has("exactJson")) {
		if (!hasBody) {
			throw new TypeError("exact JSON representation requires an operation body");
		}
		const representation = properties.get("exactJson") as ExactJsonRepresentation<unknown>;
		const text = exactJsonText(representation, body, sanitized["body"]);
		sanitized["bodySerializer"] = () => text;
	}
	return sanitized;
}

function typedMethod<Method extends HttpMethod>(
	request: UntypedRequest,
	method: Method,
	unwrapEnvelope: boolean,
): TypedMethod<Method> | TypedPayloadMethod<Method> {
	const invoke = async (path: string, init?: Readonly<Record<string, unknown>>): Promise<unknown> =>
		unwrap(await request(method, path, sanitizedRequestInit(init, "text", method, path)), unwrapEnvelope, method, path);
	return invoke as TypedMethod<Method> | TypedPayloadMethod<Method>;
}

function eventStreamMethod(request: UntypedRequest): EventStreamRequest {
	const invoke = async (path: string, init?: Readonly<Record<string, unknown>>): Promise<Response> => {
		const result = await request("get", path, sanitizedRequestInit(init, "stream", "get", path));
		const declaredMediaTypes = responseContract(result, "get", path);
		validateResponseMediaType(result, "get", path, declaredMediaTypes);
		if (result.response.ok && !declaredMediaTypes.includes("text/event-stream")) {
			throw contractMismatch(result, `operation get ${path} is not an event stream`, {
				declaredMediaTypes,
				method: "get",
				path,
				status: result.response.status,
			});
		}
		return result.response;
	};
	return invoke as EventStreamRequest;
}

function responseWithLifecycle(
	response: Response,
	signal: AbortSignal,
	setBodyAbort: (abort: (reason: unknown) => void) => void,
	cleanup: () => void,
): Response {
	if (!response.body) {
		cleanup();
		return response;
	}
	const reader = response.body.getReader();
	let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
	let settled = false;
	const abort = (reason: unknown): void => {
		if (settled) return;
		settled = true;
		controller?.error(reason);
		cleanup();
		void reader.cancel(reason).catch(() => undefined);
	};
	const body = new ReadableStream<Uint8Array>({
		start(streamController) {
			controller = streamController;
			setBodyAbort(abort);
			if (signal.aborted) abort(signal.reason);
		},
		async pull(streamController) {
			try {
				const chunk = await reader.read();
				if (settled) return;
				if (chunk.done) {
					settled = true;
					streamController.close();
					cleanup();
					return;
				}
				streamController.enqueue(chunk.value);
			} catch (error) {
				if (settled) return;
				settled = true;
				streamController.error(error);
				cleanup();
			}
		},
		cancel(reason) {
			if (settled) return undefined;
			settled = true;
			cleanup();
			return reader.cancel(reason);
		},
	});
	return new Response(body, {
		headers: response.headers,
		status: response.status,
		statusText: response.statusText,
	});
}

function withTimeout(
	fetcher: (request: Request) => Promise<Response>,
	timeoutMs: number,
): (request: Request) => Promise<Response> {
	if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
		throw new TypeError("API timeout must be a positive finite number");
	}
	return async (request) => {
		if (request.signal.aborted) throw request.signal.reason;
		const controller = new AbortController();
		let bodyAbort: ((reason: unknown) => void) | undefined;
		let rejectBeforeResponse: (reason: unknown) => void = () => undefined;
		const forwardAbort = () => controller.abort(request.signal.reason);
		const abort = new Promise<never>((_resolve, reject) => {
			rejectBeforeResponse = reject;
		});
		const handleControlledAbort = () => {
			const reason = controller.signal.reason;
			rejectBeforeResponse(reason);
			bodyAbort?.(reason);
		};
		controller.signal.addEventListener("abort", handleControlledAbort, { once: true });
		if (request.signal.aborted) forwardAbort();
		else request.signal.addEventListener("abort", forwardAbort, { once: true });
		const timeout = setTimeout(() => controller.abort(new ApiTimeoutError(timeoutMs)), timeoutMs);
		let cleaned = false;
		const cleanup = () => {
			if (cleaned) return;
			cleaned = true;
			clearTimeout(timeout);
			request.signal.removeEventListener("abort", forwardAbort);
			controller.signal.removeEventListener("abort", handleControlledAbort);
		};
		try {
			const response = await Promise.race([fetcher(new Request(request, { signal: controller.signal })), abort]);
			if (!(response instanceof Response)) throw new TypeError("API fetcher must return a Response");
			return responseWithLifecycle(
				response,
				controller.signal,
				(abortBody) => {
					bodyAbort = abortBody;
				},
				cleanup,
			);
		} catch (error) {
			cleanup();
			throw error;
		}
	};
}

export function createApiClient(options: {
	readonly apiBaseUrl: string;
	readonly apiContractVersion: string;
	readonly fetcher?: (request: Request) => Promise<Response>;
	readonly timeoutMs?: number;
}): ApiClient {
	const fetcher = withTimeout(
		options.fetcher ?? ((request) => fetch(request)),
		options.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,
	);
	const openApiClient = createOpenApiClient<paths>({
		baseUrl: options.apiBaseUrl,
		headers: { "X-Ditto-API-Contract-Version": options.apiContractVersion },
		fetch: fetcher,
		redirect: "error",
	});
	const request = openApiClient.request as unknown as UntypedRequest;
	return Object.freeze({
		get: typedMethod(request, "get", true) as TypedMethod<"get">,
		getPayload: typedMethod(request, "get", false) as TypedPayloadMethod<"get">,
		getEventStream: eventStreamMethod(request),
		post: typedMethod(request, "post", true) as TypedMethod<"post">,
		put: typedMethod(request, "put", true) as TypedMethod<"put">,
		patch: typedMethod(request, "patch", true) as TypedMethod<"patch">,
		delete: typedMethod(request, "delete", true) as TypedMethod<"delete">,
	});
}

let singleton: ApiClient | undefined;
let singletonIdentity = "";

export function getApiClient(): ApiClient {
	const runtime = readRuntimeConfig();
	const build = readWebBuildMetadata();
	const identity = `${resolveApiBaseUrl(runtime)}\0${build.apiContractVersion}`;
	if (!singleton || singletonIdentity !== identity) {
		singleton = createApiClient({
			apiBaseUrl: resolveApiBaseUrl(runtime),
			apiContractVersion: build.apiContractVersion,
		});
		singletonIdentity = identity;
	}
	return singleton;
}

/** Stable facade whose methods resolve the runtime-configured client lazily after bootstrap. */
export const apiClient: ApiClient = new Proxy(Object.create(null) as ApiClient, {
	get(_target, property) {
		if (typeof property !== "string" || !Object.hasOwn(getApiClient(), property)) return undefined;
		return getApiClient()[property as keyof ApiClient];
	},
});
