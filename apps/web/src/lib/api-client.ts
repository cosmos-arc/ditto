const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

type ApiPagination = {
	readonly total: number;
	readonly limit: number;
	readonly offset: number;
	readonly has_more: boolean;
};

export type ApiResponse<T> = {
	readonly data: T;
	readonly pagination?: ApiPagination;
};

type RequestOptions = {
	readonly method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
	readonly body?: unknown;
	readonly headers?: Record<string, string>;
	readonly signal?: AbortSignal;
};

class ApiError extends Error {
	readonly status: number;
	readonly errorCode?: string;
	readonly requestId?: string;
	readonly detail?: string;
	readonly timestamp?: string;

	constructor(params: {
		readonly status: number;
		readonly message: string;
		readonly errorCode?: string;
		readonly requestId?: string;
		readonly detail?: string;
		readonly timestamp?: string;
	}) {
		const { status, message, errorCode, requestId, detail, timestamp } = params;
		super(message);
		this.status = status;
		this.errorCode = errorCode;
		this.requestId = requestId;
		this.detail = detail;
		this.timestamp = timestamp;
		this.name = "ApiError";
	}
}

function serializeQueryValue(value: unknown): string | undefined {
	if (value == null) return undefined;
	if (
		typeof value === "string" ||
		typeof value === "number" ||
		typeof value === "boolean"
	) {
		return String(value);
	}
	return JSON.stringify(value);
}

function withQueryParams<TParams extends object>(
	path: string,
	params?: TParams,
): string {
	if (!params) return path;

	const searchParams = new URLSearchParams();
	for (const key of Object.keys(params)) {
		const serializedValue = serializeQueryValue(params[key as keyof TParams]);
		if (serializedValue !== undefined) {
			searchParams.set(key, serializedValue);
		}
	}

	const queryString = searchParams.toString();
	if (!queryString) return path;

	const separator = path.includes("?") ? "&" : "?";
	return `${path}${separator}${queryString}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

function buildApiUrl(path: string): string {
	if (/^https?:\/\//u.test(path)) return path;

	const base = API_BASE_URL.endsWith("/") ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
	const normalizedPath = path.startsWith("/") ? path : `/${path}`;
	return `${base}${normalizedPath}`;
}

async function parseJsonResponse(response: Response): Promise<unknown> {
	const text = await response.text();
	if (!text) return undefined;

	try {
		return JSON.parse(text) as unknown;
	} catch {
		return text;
	}
}

function unwrapApiResponse<T>(payload: unknown): T {
	if (isRecord(payload) && "data" in payload) {
		return payload.data as T;
	}

	return payload as T;
}

function readStringField(record: Record<string, unknown>, key: string): string | undefined {
	const value = record[key];
	return typeof value === "string" ? value : undefined;
}

function toApiError(response: Response, payload: unknown): ApiError {
	if (!isRecord(payload)) {
		const message = typeof payload === "string" && payload ? payload : response.statusText;
		return new ApiError({ status: response.status, message });
	}

	const detail = readStringField(payload, "detail");
	const error = readStringField(payload, "error");
	const message = detail ?? error ?? response.statusText;

	return new ApiError({
		status: response.status,
		message,
		errorCode: readStringField(payload, "error_code"),
		requestId: readStringField(payload, "request_id"),
		detail,
		timestamp: readStringField(payload, "timestamp"),
	});
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
	const { method = "GET", body, headers = {}, signal } = options;

	const response = await fetch(buildApiUrl(path), {
		method,
		headers: {
			"Content-Type": "application/json",
			...headers,
		},
		body: body !== undefined ? JSON.stringify(body) : undefined,
		signal,
	});
	const payload = await parseJsonResponse(response);

	if (!response.ok) {
		throw toApiError(response, payload);
	}

	return unwrapApiResponse<T>(payload);
}

export const apiClient = {
	get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),

	post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
		request<T>(path, { ...options, method: "POST", body }),

	put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
		request<T>(path, { ...options, method: "PUT", body }),

	patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
		request<T>(path, { ...options, method: "PATCH", body }),

	delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
} as const;

export { ApiError, withQueryParams };
