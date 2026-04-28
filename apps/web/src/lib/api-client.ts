const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

type RequestOptions = {
	readonly method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
	readonly body?: unknown;
	readonly headers?: Record<string, string>;
	readonly signal?: AbortSignal;
};

class ApiError extends Error {
	readonly status: number;

	constructor(status: number, message: string) {
		super(message);
		this.status = status;
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

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
	const { method = "GET", body, headers = {}, signal } = options;

	const response = await fetch(`${API_BASE_URL}${path}`, {
		method,
		headers: {
			"Content-Type": "application/json",
			...headers,
		},
		body: body !== undefined ? JSON.stringify(body) : undefined,
		signal,
	});

	if (!response.ok) {
		const message = await response.text().catch(() => response.statusText);
		throw new ApiError(response.status, message);
	}

	return response.json() as Promise<T>;
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
